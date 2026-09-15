"""Bộ phân loại ý định (intent classifier) huấn luyện offline được sử dụng bởi query router.

Bộ phân loại này cố tình được thiết kế nhỏ gọn và không có thư viện phụ thuộc để chatbot
có thể chạy cùng Ollama mà không cần thêm service nào khác. Dữ liệu huấn luyện và model
đã được tuần tự hóa được quản lý phiên bản độc lập với corpus tuyển sinh. Model sử dụng thuật toán
Multinomial Naive Bayes trên các n-gram từ (word) và ký tự (character); nó không phải là một
bảng từ khóa và có trả về điểm tự tin (confidence score) để router kiểm tra. Mô hình
kết hợp perceptron đa lớp đã học với Naive Bayes dự phòng.
"""

from __future__ import annotations

import json
import math
import random
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "intent" / "samples.jsonl"
DEFAULT_TRAIN_PATH = PROJECT_ROOT / "data" / "intent" / "train.jsonl"
DEFAULT_TEST_PATH = PROJECT_ROOT / "data" / "intent" / "test.jsonl"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "intent_classifier.json"
MODEL_VERSION = 1

_WORD_RE = re.compile(r"\d+|[a-z]+", re.IGNORECASE)


def normalize_training_text(value: str) -> str:
    """Loại bỏ dấu và chuẩn hóa dấu câu một cách nhất quán cho cả huấn luyện và suy luận."""

    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    folded = folded.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", folded).strip()


def _features(value: str) -> tuple[str, ...]:
    """Tạo các đặc trưng từ (word)/bigram/ký tự giới hạn từ một câu hỏi."""

    normalized = normalize_training_text(value)
    words = _WORD_RE.findall(normalized)
    features: list[str] = [f"w:{word}" for word in words]
    features.extend(
        f"b:{left}_{right}" for left, right in zip(words, words[1:])
    )
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    for size in (3, 4):
        features.extend(f"c{size}:{compact[index:index + size]}" for index in range(len(compact) - size + 1))
    return tuple(features)


@dataclass(frozen=True)
class IntentPrediction:
    """Kết quả model được sử dụng bởi phân tích truy vấn (query analysis) và đầu ra trace."""

    intent: str
    confidence: float
    margin: float
    source: str = "trained_intent_model"

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 6),
            "margin": round(self.margin, 6),
            "source": self.source,
        }


class IntentClassifier:
    """Bộ phân loại văn bản perceptron đa lớp đã được tuần tự hóa."""

    def __init__(
        self,
        *,
        labels: Sequence[str],
        vocabulary: Sequence[str],
        class_documents: Mapping[str, int],
        feature_counts: Mapping[str, Mapping[str, int]],
        class_feature_totals: Mapping[str, int],
        training_examples: Sequence[Mapping[str, object]] = (),
        linear_weights: Mapping[str, Mapping[str, float]] | None = None,
        linear_bias: Mapping[str, float] | None = None,
        alpha: float = 1.0,
    ) -> None:
        self.labels = tuple(labels)
        self.vocabulary = frozenset(vocabulary)
        self.class_documents = {str(key): int(value) for key, value in class_documents.items()}
        self.feature_counts = {
            str(label): {str(feature): int(count) for feature, count in counts.items()}
            for label, counts in feature_counts.items()
        }
        self.class_feature_totals = {
            str(label): int(value) for label, value in class_feature_totals.items()
        }
        self.training_examples = tuple(
            (
                str(example.get("intent") or ""),
                frozenset(str(feature) for feature in example.get("features", [])),
            )
            for example in training_examples
            if example.get("intent") and example.get("features")
        )
        self.linear_weights = {
            str(label): {str(feature): float(value) for feature, value in weights.items()}
            for label, weights in (linear_weights or {}).items()
        }
        self.linear_bias = {
            str(label): float(value) for label, value in (linear_bias or {}).items()
        }
        self.alpha = float(alpha)
        self.total_documents = sum(self.class_documents.values())

    @classmethod
    def train(cls, records: Iterable[Mapping[str, object]], *, alpha: float = 1.0) -> "IntentClassifier":
        materialized = list(records)
        if not materialized:
            raise ValueError("intent training data is empty")
        labels = tuple(sorted({str(record.get("intent") or "").strip() for record in materialized}))
        if "" in labels or len(labels) < 2:
            raise ValueError("intent training data needs at least two non-empty labels")

        class_documents = {label: 0 for label in labels}
        feature_counts = {label: {} for label in labels}
        class_feature_totals = {label: 0 for label in labels}
        vocabulary: set[str] = set()
        training_examples: list[dict[str, object]] = []
        for record in materialized:
            label = str(record.get("intent") or "").strip()
            text = str(record.get("text") or "")
            features = _features(text)
            if not features:
                raise ValueError(f"empty intent example: {record!r}")
            class_documents[label] += 1
            training_examples.append({"intent": label, "features": sorted(set(features))})
            counts = feature_counts[label]
            for feature in features:
                vocabulary.add(feature)
                counts[feature] = counts.get(feature, 0) + 1
                class_feature_totals[label] += 1
        linear_weights, linear_bias = _train_perceptron(materialized, labels)
        return cls(
            labels=labels,
            vocabulary=sorted(vocabulary),
            class_documents=class_documents,
            feature_counts=feature_counts,
            class_feature_totals=class_feature_totals,
            training_examples=training_examples,
            linear_weights=linear_weights,
            linear_bias=linear_bias,
            alpha=alpha,
        )

    def predict(self, text: str) -> IntentPrediction | None:
        features = tuple(feature for feature in _features(text) if feature in self.vocabulary)
        if not features or not self.labels or not self.total_documents:
            return None
        if self.linear_weights:
            scores = {
                label: self.linear_bias.get(label, 0.0)
                + sum(self.linear_weights.get(label, {}).get(feature, 0.0) for feature in set(features))
                for label in self.labels
            }
        else:
            vocabulary_size = len(self.vocabulary)
            scores = {}
            for label in self.labels:
                prior = (self.class_documents.get(label, 0) + self.alpha) / (
                    self.total_documents + self.alpha * len(self.labels)
                )
                denominator = self.class_feature_totals.get(label, 0) + self.alpha * vocabulary_size
                score = math.log(prior)
                counts = self.feature_counts.get(label, {})
                for feature in features:
                    score += math.log((counts.get(feature, 0) + self.alpha) / denominator)
                scores[label] = score
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_label, top_score = ordered[0]
        second_score = ordered[1][1] if len(ordered) > 1 else top_score

        # A nearest training-example pass makes the small model robust to
        # short paraphrases (for example, ``email tuyển sinh``).  It is still
        # learned from the training split; it does not contain hand-written
        # intent keywords.  Use it only when the linear decision is close;
        # otherwise the learned discriminative weights remain authoritative.
        query_features = set(features)
        label_similarities = {label: 0.0 for label in self.labels}
        query_weight = sum(_feature_weight(feature) for feature in query_features)
        for label, example_features in self.training_examples:
            common_weight = sum(
                _feature_weight(feature)
                for feature in query_features & example_features
            )
            example_weight = sum(_feature_weight(feature) for feature in example_features)
            if common_weight and query_weight and example_weight:
                similarity = common_weight / math.sqrt(query_weight * example_weight)
                label_similarities[label] = max(label_similarities[label], similarity)
        nearest = sorted(label_similarities.items(), key=lambda item: item[1], reverse=True)
        if nearest and nearest[0][1] >= 0.24 and top_score - second_score < 1.5:
            neighbor_label, neighbor_score = nearest[0]
            neighbor_second = nearest[1][1] if len(nearest) > 1 else 0.0
            if neighbor_score - neighbor_second >= 0.035:
                top_label = neighbor_label
                top_score = scores.get(top_label, top_score)
                second_score = max(
                    (score for label, score in scores.items() if label != top_label),
                    default=top_score,
                )
        # Softmax is only used to expose a human-readable confidence.  The
        # router also keeps the margin because short questions can be low
        # probability across every class while still being unambiguous.
        maximum = max(scores.values())
        denominator = sum(math.exp(score - maximum) for score in scores.values())
        confidence = math.exp(scores[top_label] - maximum) / denominator
        return IntentPrediction(
            intent=top_label,
            confidence=confidence,
            margin=scores[top_label] - second_score,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "model_version": MODEL_VERSION,
            "algorithm": "multiclass_perceptron_with_naive_bayes_fallback",
            "feature_set": ["word_unigram", "word_bigram", "character_3gram", "character_4gram"],
            "labels": list(self.labels),
            "vocabulary": sorted(self.vocabulary),
            "class_documents": self.class_documents,
            "feature_counts": self.feature_counts,
            "class_feature_totals": self.class_feature_totals,
            "linear_weights": self.linear_weights,
            "linear_bias": self.linear_bias,
            "training_examples": [
                {"intent": label, "features": sorted(features)}
                for label, features in self.training_examples
            ],
            "alpha": self.alpha,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "IntentClassifier":
        if int(payload.get("model_version", -1)) != MODEL_VERSION:
            raise ValueError("unsupported intent model version")
        return cls(
            labels=[str(value) for value in payload.get("labels", [])],
            vocabulary=[str(value) for value in payload.get("vocabulary", [])],
            class_documents=payload.get("class_documents", {}),
            feature_counts=payload.get("feature_counts", {}),
            class_feature_totals=payload.get("class_feature_totals", {}),
            training_examples=payload.get("training_examples", []),
            linear_weights=payload.get("linear_weights", {}),
            linear_bias=payload.get("linear_bias", {}),
            alpha=float(payload.get("alpha", 1.0)),
        )


def _feature_weight(feature: str) -> float:
    if feature.startswith("b:"):
        return 3.0
    if feature.startswith("w:"):
        return 2.0
    return 0.25


def _linear_features(value: str) -> tuple[str, ...]:
    """Các đặc trưng được sử dụng trong bước huấn luyện phân biệt (discriminative training)."""

    return tuple(feature for feature in _features(value) if feature.startswith(("w:", "b:")))


def _train_perceptron(
    records: Sequence[Mapping[str, object]],
    labels: Sequence[str],
    *,
    epochs: int = 40,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Huấn luyện một perceptron đa lớp (multiclass perceptron) tất định trên tập huấn luyện."""

    weights = {label: {} for label in labels}
    bias = {label: 0.0 for label in labels}
    examples = [
        (str(record["intent"]), set(_linear_features(str(record["text"]))))
        for record in records
    ]
    for epoch in range(epochs):
        ordered = list(examples)
        random.Random(20260915 + epoch).shuffle(ordered)
        for expected, features in ordered:
            scores = {
                label: bias[label] + sum(weights[label].get(feature, 0.0) for feature in features)
                for label in labels
            }
            predicted = max(labels, key=lambda label: (scores[label], label))
            if predicted == expected:
                continue
            bias[expected] += 1.0
            bias[predicted] -= 1.0
            for feature in features:
                weights[expected][feature] = weights[expected].get(feature, 0.0) + 1.0
                weights[predicted][feature] = weights[predicted].get(feature, 0.0) - 1.0
    return weights, bias


def load_records(path: Path) -> list[dict[str, str]]:
    """Đọc các bản ghi ý định JSONL và xác thực cấu trúc (schema) công khai nhỏ gọn của chúng."""

    records: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict) or not payload.get("text") or not payload.get("intent"):
            raise ValueError(f"invalid intent record at {path}:{line_number}")
        records.append(
            {
                "id": str(payload.get("id") or f"row_{line_number}"),
                "text": str(payload["text"]),
                "intent": str(payload["intent"]),
            }
        )
    if not records:
        raise ValueError(f"no intent records found in {path}")
    return records


DEFAULT_SPLIT_SEED = 20260013


def stratified_split(
    records: Sequence[Mapping[str, object]],
    *,
    test_ratio: float = 0.2,
    seed: int = DEFAULT_SPLIT_SEED,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Chia tách mọi nhãn một cách tất định (deterministically) trong khi vẫn giữ nguyên tỷ lệ 80/20."""

    if not 0 < test_ratio < 1:
        raise ValueError("test_ratio must be between zero and one")
    groups: dict[str, list[dict[str, str]]] = {}
    for record in records:
        normalized = {
            "id": str(record.get("id") or ""),
            "text": str(record.get("text") or ""),
            "intent": str(record.get("intent") or ""),
        }
        if not normalized["id"] or not normalized["text"] or not normalized["intent"]:
            raise ValueError(f"invalid record: {record!r}")
        groups.setdefault(normalized["intent"], []).append(normalized)
    if any(len(group) < 2 for group in groups.values()):
        raise ValueError("each intent needs at least two examples for a stratified split")

    train: list[dict[str, str]] = []
    test: list[dict[str, str]] = []
    for label in sorted(groups):
        # Seed each label independently so the split is reproducible and every
        # intent contributes the same 20% holdout.
        group = list(groups[label])
        random.Random(f"{seed}:{label}").shuffle(group)
        test_count = max(1, int(round(len(group) * test_ratio)))
        test.extend(group[:test_count])
        train.extend(group[test_count:])
    train.sort(key=lambda record: record["id"])
    test.sort(key=lambda record: record["id"])
    return train, test


def save_records(records: Iterable[Mapping[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        lines.append(json.dumps(dict(record), ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_model(model: IntentClassifier, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def load_model(path: Path = DEFAULT_MODEL_PATH) -> IntentClassifier:
    return IntentClassifier.from_dict(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=2)
def get_intent_classifier(model_path: str = str(DEFAULT_MODEL_PATH)) -> IntentClassifier | None:
    """Tải model đã được lưu, hoặc huấn luyện từ tập 80% đã được phân chia sẵn."""

    path = Path(model_path)
    try:
        if path.exists():
            return load_model(path)
        if DEFAULT_TRAIN_PATH.exists():
            return IntentClassifier.train(load_records(DEFAULT_TRAIN_PATH))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def predict_intent(text: str) -> IntentPrediction | None:
    classifier = get_intent_classifier()
    return classifier.predict(text) if classifier is not None else None


__all__ = [
    "DEFAULT_DATASET_PATH",
    "DEFAULT_MODEL_PATH",
    "DEFAULT_TEST_PATH",
    "DEFAULT_TRAIN_PATH",
    "IntentClassifier",
    "IntentPrediction",
    "get_intent_classifier",
    "load_records",
    "normalize_training_text",
    "predict_intent",
    "save_model",
    "save_records",
    "stratified_split",
]
