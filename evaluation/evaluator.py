"""Deterministic evaluation helpers for retrieval and answer contracts.

The evaluator deliberately does not use an LLM judge.  It scores the parts that
can be checked from the fixed gold contract (status, required/forbidden claims,
and evidence coverage) and leaves stylistic review to a human rubric.  This
keeps the holdout set report-only and makes regressions reproducible offline.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable, Mapping, Sequence

from src.chatbot.output_validator import validate_model_answer


DATASET_DIR = Path(__file__).resolve().parent
_YEAR_RE = re.compile(r"\b20\d{2}\b")
_TOKEN_RE = re.compile(r"\d[\d.,]*|[A-Za-zÀ-ỹĐđ]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "va",
        "la",
        "cua",
        "cho",
        "toi",
        "ban",
        "mot",
        "nhung",
        "duoc",
        "theo",
        "trong",
        "nam",
        "nay",
        "co",
        "ve",
        "cac",
        "gi",
        "nao",
        "bao",
        "nhieu",
    }
)


@dataclass(frozen=True)
class EvaluationCase:
    """One immutable gold case shared by the dev and holdout reports."""

    case_id: str
    question: str
    state: Mapping[str, object] = field(default_factory=dict)
    expected_intent: str = ""
    expected_status: str = "ok"
    expected_categories: tuple[str, ...] = ()
    expected_entities: Mapping[str, object] = field(default_factory=dict)
    evidence_contains: tuple[str, ...] = ()
    relevant_chunk_ids: tuple[str, ...] = ()
    answer_contains: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "EvaluationCase":
        expected_evidence = value.get("expected_evidence")
        evidence = expected_evidence if isinstance(expected_evidence, Mapping) else {}
        category_value = value.get("expected_categories", value.get("expected_category"))
        categories = _string_tuple(category_value)
        if not categories:
            category = evidence.get("category")
            categories = _string_tuple(evidence.get("categories"))
            if category and str(category).casefold() != "none":
                categories = (str(category),)
        relevant_chunk_ids = _string_tuple(
            value.get("relevant_chunk_ids", evidence.get("chunk_ids"))
        )
        evidence_contains = _string_tuple(
            value.get("evidence_contains", evidence.get("contains"))
        )
        answer_contains = _string_tuple(value.get("answer_contains"))
        return cls(
            case_id=str(value.get("id") or value.get("case_id") or "").strip(),
            question=str(value.get("question") or "").strip(),
            state=dict(value.get("state") or {})
            if isinstance(value.get("state") or {}, Mapping)
            else {},
            expected_intent=str(value.get("expected_intent") or ""),
            expected_status=str(value.get("expected_status") or "ok"),
            expected_categories=tuple(categories),
            expected_entities=dict(value.get("expected_entities") or {})
            if isinstance(value.get("expected_entities") or {}, Mapping)
            else {},
            evidence_contains=evidence_contains,
            relevant_chunk_ids=relevant_chunk_ids,
            answer_contains=answer_contains,
            forbidden_claims=_string_tuple(value.get("forbidden_claims")),
        )

    @property
    def has_retrieval_gold(self) -> bool:
        return bool(self.expected_categories and (self.evidence_contains or self.relevant_chunk_ids))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.case_id,
            "question": self.question,
            "state": dict(self.state),
            "expected_intent": self.expected_intent,
            "expected_status": self.expected_status,
            "expected_category": list(self.expected_categories),
            "expected_entities": dict(self.expected_entities),
            "expected_evidence": {
                "categories": list(self.expected_categories),
                "contains": list(self.evidence_contains),
                "chunk_ids": list(self.relevant_chunk_ids),
            },
            "answer_contains": list(self.answer_contains),
            "forbidden_claims": list(self.forbidden_claims),
        }


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, Sequence) and not isinstance(value, str) else (value,)
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.lower().replace("đ", "d")).strip()


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_fold(value))
        if token not in _STOPWORDS and (len(token) >= 3 or token.isdigit())
    }


def _load_jsonl(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"Evaluation row must be an object in {path}:{line_number}")
        cases.append(EvaluationCase.from_mapping(value))
    return cases


def load_cases(
    split: str = "all",
    *,
    dataset_dir: Path = DATASET_DIR,
) -> tuple[EvaluationCase, ...]:
    """Load the fixed dev/holdout files; ``holdout`` is never used for tuning."""

    if split not in {"dev", "holdout", "all"}:
        raise ValueError("split must be 'dev', 'holdout', or 'all'")
    names = ("dev", "holdout") if split == "all" else (split,)
    cases: list[EvaluationCase] = []
    for name in names:
        path = Path(dataset_dir) / f"{name}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(path)
        cases.extend(_load_jsonl(path))
    return tuple(cases)


def validate_dataset(
    *,
    dataset_dir: Path = DATASET_DIR,
) -> dict[str, object]:
    """Validate the fixed 80/20 split and return an audit-friendly summary."""

    dev = load_cases("dev", dataset_dir=dataset_dir)
    holdout = load_cases("holdout", dataset_dir=dataset_dir)
    all_cases = dev + holdout
    ids = [case.case_id for case in all_cases]
    if not all(ids):
        raise ValueError("Evaluation case ids must not be empty")
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation case ids must be unique across splits")
    if len(all_cases) < 5 or len(dev) * 5 != len(all_cases) * 4:
        raise ValueError(
            f"Expected an exact 80/20 split, got dev={len(dev)}, holdout={len(holdout)}"
        )
    return {
        "dataset_dir": str(Path(dataset_dir)),
        "total_cases": len(all_cases),
        "dev_cases": len(dev),
        "holdout_cases": len(holdout),
        "dev_ids": [case.case_id for case in dev],
        "holdout_ids": [case.case_id for case in holdout],
        "disjoint": True,
        "holdout_policy": "report_only_not_used_for_tuning",
    }


def _documents(value: object) -> list[object]:
    if value is None:
        return []
    documents = getattr(value, "documents", None)
    if documents is None and isinstance(value, Mapping):
        documents = value.get("documents")
    if documents is None and isinstance(value, tuple) and len(value) == 2:
        documents = value[0]
    if isinstance(documents, Iterable) and not isinstance(documents, (str, bytes, Mapping)):
        return list(documents)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return list(value)
    return []


def _metadata(document: object) -> Mapping[str, object]:
    metadata = getattr(document, "metadata", None)
    if metadata is None and isinstance(document, Mapping):
        metadata = document.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _content(document: object) -> str:
    value = getattr(document, "page_content", None)
    if value is None and isinstance(document, Mapping):
        value = document.get("page_content", document.get("text", ""))
    return str(value or "")


def _document_is_relevant(document: object, case: EvaluationCase) -> bool:
    metadata = _metadata(document)
    if case.relevant_chunk_ids:
        chunk_id = str(metadata.get("chunk_id") or "")
        return chunk_id in case.relevant_chunk_ids
    category = str(metadata.get("category") or "")
    if case.expected_categories and category not in case.expected_categories:
        return False
    if not case.evidence_contains:
        return bool(category)
    text = _fold(_content(document))
    return any(_fold(term) in text for term in case.evidence_contains)


def calculate_retrieval_metrics(
    case: EvaluationCase,
    retrieved: object,
    *,
    top_k: int = 5,
) -> dict[str, object]:
    """Calculate Hit/Precision/Recall/MRR for one case at a fixed k."""

    k = max(1, int(top_k))
    if not case.has_retrieval_gold:
        return {
            "case_id": case.case_id,
            "eligible": False,
            "skip_reason": "no_retrieval_gold_or_boundary_case",
            "top_k": k,
        }
    hits = _documents(retrieved)[:k]
    relevant_ranks = [index for index, document in enumerate(hits, 1) if _document_is_relevant(document, case)]
    if case.relevant_chunk_ids:
        gold_units = set(case.relevant_chunk_ids)
        matched_units = {
            str(_metadata(document).get("chunk_id") or "")
            for document in hits
            if str(_metadata(document).get("chunk_id") or "") in gold_units
        }
    else:
        gold_units = set(case.evidence_contains)
        matched_units = {
            unit
            for unit in gold_units
            if any(_fold(unit) in _fold(_content(document)) for document in hits)
        }
    relevant_count = len(relevant_ranks)
    first_rank = min(relevant_ranks) if relevant_ranks else None
    return {
        "case_id": case.case_id,
        "eligible": True,
        "top_k": k,
        "returned_count": len(hits),
        "relevant_count": relevant_count,
        "gold_unit_count": len(gold_units),
        "matched_unit_count": len(matched_units),
        "hit_at_k": 1.0 if relevant_ranks else 0.0,
        "precision_at_k": relevant_count / k,
        "recall_at_k": len(matched_units) / len(gold_units) if gold_units else 0.0,
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "first_relevant_rank": first_rank,
    }


def aggregate_retrieval_metrics(case_metrics: Iterable[Mapping[str, object]]) -> dict[str, object]:
    eligible = [item for item in case_metrics if item.get("eligible") is True]
    keys = ("hit_at_k", "precision_at_k", "recall_at_k", "mrr")
    return {
        "eligible_cases": len(eligible),
        **{
            key: round(mean(float(item[key]) for item in eligible), 4) if eligible else 0.0
            for key in keys
        },
    }


def evaluate_retrieval(
    cases: Iterable[EvaluationCase],
    retrieve: Callable[[EvaluationCase], object],
    *,
    top_k: int = 5,
) -> dict[str, object]:
    per_case: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for case in cases:
        try:
            per_case.append(calculate_retrieval_metrics(case, retrieve(case), top_k=top_k))
        except Exception as exc:  # pragma: no cover - defensive report boundary
            errors.append({"case_id": case.case_id, "error": str(exc)})
    return {
        "top_k": max(1, int(top_k)),
        "cases": per_case,
        "metrics": aggregate_retrieval_metrics(per_case),
        "errors": errors,
    }


def _answer_value(result: object, key: str, default: object = None) -> object:
    if isinstance(result, Mapping):
        return result.get(key, default)
    return getattr(result, key, default)


def score_answer_case(
    case: EvaluationCase,
    result: object,
    *,
    evidence: object | None = None,
    analysis: object | None = None,
) -> dict[str, object]:
    """Score a response without judging style or inventing a reference answer."""

    status = str(_answer_value(result, "status", "") or "")
    answer = str(_answer_value(result, "answer", _answer_value(result, "content", "")) or "")
    normalized_answer = _fold(answer)
    required_hits = [term for term in case.answer_contains if _fold(term) in normalized_answer]
    forbidden_hits = [term for term in case.forbidden_claims if _fold(term) in normalized_answer]
    status_correct = status == case.expected_status
    content_correct = len(required_hits) == len(case.answer_contains) and not forbidden_hits
    answer_correct = status_correct and content_correct

    question_overlap = _tokens(case.question) & _tokens(answer)
    relevance = bool(status_correct and (question_overlap or required_hits or case.expected_status != "ok"))
    validator_status: str | None = None
    validator_reason: str | None = None
    if evidence is not None and case.expected_status == "ok":
        validation = validate_model_answer(
            answer,
            evidence,
            question=case.question,
            analysis=analysis,
        )
        validator_status = str(validation.get("status") or "")
        validator_reason = str(validation.get("_validation_reason") or "") or None
        faithfulness = validator_status == "ok"
    else:
        faithfulness = bool(status_correct and not forbidden_hits)

    return {
        "case_id": case.case_id,
        "expected_status": case.expected_status,
        "actual_status": status,
        "status_correct": status_correct,
        "required_hits": required_hits,
        "required_count": len(case.answer_contains),
        "forbidden_hits": forbidden_hits,
        "answer_correctness": 1.0 if answer_correct else 0.0,
        "relevance": 1.0 if relevance else 0.0,
        "faithfulness": 1.0 if faithfulness else 0.0,
        "abstention_accuracy": 1.0 if status_correct else 0.0,
        "hallucination": 1.0 if forbidden_hits else 0.0,
        "critical_factual_hallucination": bool(forbidden_hits),
        "critical_failure": bool(case.expected_status == "ok" and forbidden_hits),
        "validator_status": validator_status,
        "validator_reason": validator_reason,
    }


def aggregate_answer_metrics(case_metrics: Iterable[Mapping[str, object]]) -> dict[str, object]:
    values = list(case_metrics)
    keys = (
        "answer_correctness",
        "relevance",
        "faithfulness",
        "abstention_accuracy",
        "hallucination",
    )
    return {
        "cases": len(values),
        **{
            key: round(mean(float(item[key]) for item in values), 4) if values else 0.0
            for key in keys
        },
        "critical_factual_hallucinations": sum(
            bool(item.get("critical_factual_hallucination")) for item in values
        ),
    }


def evaluate_answers(
    cases: Iterable[EvaluationCase],
    answer: Callable[[EvaluationCase], object],
) -> dict[str, object]:
    per_case: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for case in cases:
        try:
            per_case.append(score_answer_case(case, answer(case)))
        except Exception as exc:  # pragma: no cover - defensive report boundary
            errors.append({"case_id": case.case_id, "error": str(exc)})
    return {"cases": per_case, "metrics": aggregate_answer_metrics(per_case), "errors": errors}


def evaluate_intents(
    cases: Iterable[EvaluationCase],
    predict: Callable[[EvaluationCase], str],
) -> dict[str, object]:
    per_case: list[dict[str, object]] = []
    for case in cases:
        actual = str(predict(case) or "")
        per_case.append(
            {
                "case_id": case.case_id,
                "expected_intent": case.expected_intent,
                "actual_intent": actual,
                "correct": actual == case.expected_intent,
            }
        )
    return {
        "cases": per_case,
        "metrics": {
            "accuracy": round(
                mean(bool(item["correct"]) for item in per_case), 4
            )
            if per_case
            else 0.0,
            "count": len(per_case),
        },
    }


__all__ = [
    "DATASET_DIR",
    "EvaluationCase",
    "aggregate_answer_metrics",
    "aggregate_retrieval_metrics",
    "calculate_retrieval_metrics",
    "evaluate_answers",
    "evaluate_intents",
    "evaluate_retrieval",
    "load_cases",
    "score_answer_case",
    "validate_dataset",
]
