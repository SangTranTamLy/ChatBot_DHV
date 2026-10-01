"""Run the Phase 5 dataset audit and end-to-end evaluation.

The evaluator uses the production query-analysis, router, evidence selector, planner,
validator and answer service.  Generation is replaced with the existing deterministic
evidence-echo adapter so the report measures the pipeline without requiring Ollama to
be online.  The final holdout is read-only and is never used to alter rules/configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.run_evaluation import EvidenceEchoLLM, OfflineCorpusStore  # noqa: E402
from src.chatbot.evidence import build_evidence, select_evidence_documents  # noqa: E402
from src.chatbot.intent_classifier import IntentClassifier  # noqa: E402
from src.chatbot.query_analysis import ConversationState, analyze_question, route_question  # noqa: E402
from src.chatbot.rag_chain import ask_chatbot  # noqa: E402
from src.config.settings import settings  # noqa: E402
from src.ingestion.loader import load_verified_documents  # noqa: E402
from src.ingestion.splitter import split_documents  # noqa: E402
from src.retrieval.retriever import (  # noqa: E402
    DHVRetriever,
    _bm25_scores,
    _document_identity,
    _entity_matches,
    _rank_hybrid_candidates_with_audit,
)


DATA_DIR = ROOT / "data" / "evaluation"
REPORT_DIR = ROOT / "reports" / "phase5"
MASTER = DATA_DIR / "qa_master_1000.jsonl"
LOCK = DATA_DIR / "test_200.lock"
INTENT_MODEL = ROOT / "models" / "phase5_intent_classifier.json"
TARGET_YEAR = 2026
TOKEN_RE = re.compile(r"\d[\d.,]*|[A-Za-zÀ-ỹĐđ]+", re.UNICODE)
GUARANTEE_RE = re.compile(
    r"chắc chắn đậu|chắc chắn trúng tuyển|đảm bảo trúng tuyển|bạn sẽ đậu|đủ điều kiện trúng tuyển",
    re.IGNORECASE,
)


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()


def digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def fact_present(answer: object, fact: object) -> bool:
    answer_text = str(answer or "")
    fact_text = str(fact or "").strip()
    if not fact_text:
        return True
    numeric = digits(fact_text)
    if numeric and len(numeric) >= 2:
        return numeric in digits(answer_text)
    return fold(fact_text) in fold(answer_text)


def load_rows(path: Path = MASTER) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def expected_required(row: Mapping[str, object]) -> list[str]:
    payload = row.get("expected_answer")
    if isinstance(payload, Mapping):
        return [str(value) for value in payload.get("required_facts", [])]
    return []


def expected_forbidden(row: Mapping[str, object]) -> list[str]:
    payload = row.get("expected_answer")
    if isinstance(payload, Mapping):
        return [str(value) for value in payload.get("forbidden_facts", [])]
    return []


def compound_record_id(metadata: Mapping[str, object]) -> str:
    document = str(metadata.get("structured_document_id") or metadata.get("document_id") or "")
    record = str(metadata.get("structured_record_id") or "")
    return f"{document}:{record}" if document and record else ""


def verified_record_index() -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for path in sorted((ROOT / "data" / "processed").rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        source = document.get("source") or {}
        if document.get("year") != TARGET_YEAR or source.get("verified") is not True or source.get("status") != "verified":
            continue
        for record in document.get("records") or []:
            if not isinstance(record, Mapping):
                continue
            record_id = str(record.get("record_id") or "")
            if not record_id:
                continue
            key = f"{document.get('document_id')}:{record_id}"
            index[key] = {
                "document_id": document.get("document_id"),
                "record_id": record_id,
                "year": document.get("year"),
                "status": source.get("status"),
                "source_url": source.get("source_url"),
            }
    return index


def dataset_audit(rows: list[dict[str, object]], record_index: Mapping[str, object]) -> dict[str, object]:
    exact_ids = Counter(str(row.get("id") or "") for row in rows)
    exact_questions = Counter(str(row.get("question") or "") for row in rows)
    normalized_questions = Counter(fold(row.get("question")) for row in rows)
    family_splits: defaultdict[str, set[str]] = defaultdict(set)
    train_families: set[str] = set()
    test_families: set[str] = set()
    missing: list[str] = []
    invalid_evidence: list[dict[str, object]] = []
    unsupported_factual: list[str] = []
    wrong_year: list[str] = []
    for row in rows:
        row_id = str(row.get("id") or "")
        family = str(row.get("family_id") or "")
        split = str(row.get("split") or "")
        family_splits[family].add(split)
        if split == "test":
            test_families.add(family)
        if split == "train":
            train_families.add(family)
        for field in ("id", "question", "intent", "category", "expected_status", "evidence_ids", "source_document_ids"):
            if field == "evidence_ids":
                continue
            if row.get(field) in (None, ""):
                missing.append(f"{row_id}:{field}")
        factual = str(row.get("expected_status")) == "ok" and str(row.get("answer_mode")) not in {"system", "abstention", "clarification"}
        evidence_ids = row.get("evidence_ids") if isinstance(row.get("evidence_ids"), list) else []
        if factual and not evidence_ids:
            unsupported_factual.append(row_id)
        for evidence_id in evidence_ids:
            if str(evidence_id) not in record_index:
                invalid_evidence.append({"id": row_id, "evidence_id": evidence_id})
        for source in row.get("source_metadata", []) if isinstance(row.get("source_metadata"), list) else []:
            if isinstance(source, Mapping) and source.get("year") != TARGET_YEAR:
                wrong_year.append(row_id)

    near_duplicates: list[dict[str, object]] = []
    ordered = sorted(rows, key=lambda row: str(row.get("id")))
    for left_index, left in enumerate(ordered):
        left_tokens = set(fold(left.get("question")).split())
        if len(left_tokens) < 3:
            continue
        for right in ordered[left_index + 1 :]:
            if left.get("family_id") == right.get("family_id"):
                continue
            right_tokens = set(fold(right.get("question")).split())
            if not right_tokens:
                continue
            similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if similarity >= 0.90:
                near_duplicates.append({
                    "left_id": left.get("id"),
                    "right_id": right.get("id"),
                    "similarity": round(similarity, 4),
                    "same_split": left.get("split") == right.get("split"),
                })
                if len(near_duplicates) >= 200:
                    break
        if len(near_duplicates) >= 200:
            break

    split_counts = Counter(str(row.get("split")) for row in rows)
    development_counts = Counter(
        str(row.get("development_split"))
        for row in rows
        if row.get("split") == "train"
    )
    family_overlap = sorted(train_families & test_families)
    audit = {
        "total": len(rows),
        "split_counts": dict(split_counts),
        "development_counts": dict(development_counts),
        "unique_ids": len(exact_ids) == len(rows) and "" not in exact_ids,
        "exact_duplicate_ids": {key: value for key, value in exact_ids.items() if value > 1},
        "exact_duplicate_questions": {key: value for key, value in exact_questions.items() if value > 1},
        "normalized_duplicate_questions": {key: value for key, value in normalized_questions.items() if value > 1},
        "near_duplicate_count_capped_at_200": len(near_duplicates),
        "near_duplicates": near_duplicates,
        "family_split_overlap": family_overlap,
        "missing_fields": missing,
        "invalid_evidence": invalid_evidence,
        "unsupported_factual_answers": unsupported_factual,
        "wrong_year_sources": sorted(set(wrong_year)),
        "valid": (
            len(rows) == 1000
            and split_counts == Counter({"train": 800, "test": 200})
            and development_counts == Counter({"train": 640, "dev": 160})
            and len(exact_ids) == len(rows)
            and not audit_value(exact_questions, lambda count: count > 1)
            and not audit_value(normalized_questions, lambda count: count > 1)
            and not family_overlap
            and not missing
            and not invalid_evidence
            and not unsupported_factual
            and not wrong_year
        ),
    }
    return audit


def audit_value(values: Mapping[object, int], predicate: Any) -> bool:
    return any(predicate(count) for count in values.values())


class OfflineDenseRetriever:
    """Local dense baseline used only for the Phase 5 retrieval benchmark.

    The production evaluator deliberately keeps generation deterministic and
    offline.  This class provides a real embedding-based ranking path so the
    report does not mislabel lexical overlap as ``Dense``.  It loads only a
    local SentenceTransformers snapshot and never downloads a model.
    """

    MODEL_NAME = "BAAI/bge-m3"

    def __init__(self, chunks: Iterable[Any]) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment failure
            raise RuntimeError(
                "Phase 5 dense evaluation requires sentence-transformers; "
                "install requirements.txt before running the evaluator."
            ) from exc

        self.chunks = tuple(chunks)
        self._index_by_object_id = {id(document): index for index, document in enumerate(self.chunks)}
        self.model_path = self._resolve_local_model_path()
        try:
            self.model = SentenceTransformer(str(self.model_path), local_files_only=True)
        except Exception as exc:  # pragma: no cover - environment/model failure
            raise RuntimeError(
                "Không tải được model dense cục bộ BAAI/bge-m3. "
                "Đặt PHASE5_DENSE_MODEL_PATH tới một snapshot đã có sẵn."
            ) from exc

        texts = [str(document.page_content or "") for document in self.chunks]
        self.embeddings = self.model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self._query_cache: dict[str, Any] = {}

    @classmethod
    def _resolve_local_model_path(cls) -> Path:
        configured = os.environ.get("PHASE5_DENSE_MODEL_PATH", "").strip()
        if configured:
            path = Path(configured).expanduser()
            if path.is_dir():
                return path
            raise RuntimeError(f"PHASE5_DENSE_MODEL_PATH không tồn tại: {path}")

        snapshots = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3" / "snapshots"
        if snapshots.is_dir():
            candidates = [
                path for path in snapshots.iterdir()
                if path.is_dir() and (path / "config.json").exists()
            ]
            if candidates:
                return max(candidates, key=lambda path: path.stat().st_mtime)

        raise RuntimeError(
            "Không tìm thấy snapshot BAAI/bge-m3 trong cache cục bộ; "
            "evaluator không tự tải model qua mạng."
        )

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "backend": "sentence-transformers",
            "model": self.MODEL_NAME,
            "local_only": True,
            "embedding_dimension": int(self.embeddings.shape[1]),
            "corpus_chunks": len(self.chunks),
        }

    def retrieve(self, query: str, candidates: Iterable[Any], top_k: int = 5) -> list[Any]:
        query_text = str(query or "")
        query_vector = self._query_cache.get(query_text)
        if query_vector is None:
            query_vector = self.model.encode(
                [query_text],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
            self._query_cache[query_text] = query_vector

        candidate_rows = []
        for document in candidates:
            index = self._index_by_object_id[id(document)]
            score = float(self.embeddings[index] @ query_vector)
            candidate_rows.append((score, _document_identity(document), document))
        candidate_rows.sort(key=lambda item: (-item[0], item[1]))
        return [document for _, _, document in candidate_rows[:top_k]]


def setup_runtime() -> tuple[DHVRetriever, dict[str, Any], dict[str, Mapping[str, object]], OfflineDenseRetriever]:
    processed = ROOT / "data" / "processed"
    load_result = load_verified_documents(processed)
    chunks = tuple(split_documents(load_result.documents))
    OfflineCorpusStore.chunks = chunks
    retriever = DHVRetriever(
        settings_obj=settings,
        store_factory=OfflineCorpusStore,
        embedding_factory=lambda **_: object(),
    )
    chunk_index = {str(document.metadata.get("chunk_id")): document.metadata for document in chunks}
    dense_retriever = OfflineDenseRetriever(chunks)
    return retriever, load_result.stats.as_dict(), chunk_index, dense_retriever


def where_matches(metadata: Mapping[str, object], where: Mapping[str, object]) -> bool:
    if "year" in where:
        return metadata.get("year") == where["year"]
    if "$and" in where:
        return all(where_matches(metadata, item) for item in where["$and"] if isinstance(item, Mapping))
    if "$or" in where:
        return any(where_matches(metadata, item) for item in where["$or"] if isinstance(item, Mapping))
    if "category" in where:
        return metadata.get("category") == where["category"]
    return True


def retrieve_variants(
    retriever: DHVRetriever,
    dense_retriever: OfflineDenseRetriever,
    plan: Any,
    question: str,
    top_k: int = 5,
) -> dict[str, list[Any]]:
    query = str(plan.retrieval_query or question)
    where = dict(plan.metadata_filter or {"year": TARGET_YEAR})
    categories = tuple(plan.categories or ())
    entity_filters = dict(plan.entity_filters or {})
    candidates = [
        document
        for document in OfflineCorpusStore.chunks
        if where_matches(document.metadata, where)
        and document.metadata.get("status") == "verified"
        and int(document.metadata.get("year", 0)) == TARGET_YEAR
        and (not categories or document.metadata.get("category") in categories)
        and (not entity_filters or _entity_matches(document, entity_filters))
    ]
    dense = dense_retriever.retrieve(query, candidates, top_k=top_k)
    bm25_scores = _bm25_scores(query, candidates)
    bm25 = sorted(candidates, key=lambda document: (-bm25_scores.get(_document_identity(document), 0.0), _document_identity(document)))[:top_k]
    hybrid_result = retriever.retrieve_with_audit(
        question,
        categories=plan.categories,
        retrieval_query=plan.retrieval_query,
        entity_filters=plan.entity_filters,
        top_k=top_k,
    )
    hybrid = list(hybrid_result.documents)
    return {"Dense": dense, "BM25": bm25, "Hybrid/RRF": hybrid}


def evidence_ids(documents: Iterable[Any]) -> set[str]:
    return {compound_record_id(getattr(document, "metadata", {}) or {}) for document in documents if compound_record_id(getattr(document, "metadata", {}) or {})}


def ranking_metrics(expected: set[str], documents: list[Any], top_k: int) -> dict[str, float]:
    ranks = [index for index, document in enumerate(documents[:top_k], start=1) if compound_record_id(getattr(document, "metadata", {}) or {}) in expected]
    hits = len(ranks)
    matched = {compound_record_id(getattr(document, "metadata", {}) or {}) for document in documents[:top_k]} & expected
    first = min(ranks) if ranks else None
    return {
        "hit_at_k": float(bool(ranks)),
        "recall_at_k": len(matched) / len(expected) if expected else 0.0,
        "mrr": 1.0 / first if first else 0.0,
    }


def trace_selected_ids(trace: Mapping[str, object], chunk_index: Mapping[str, Mapping[str, object]]) -> set[str]:
    selection = trace.get("evidence_selection")
    if not isinstance(selection, Mapping):
        return set()
    selected = selection.get("selected")
    if not isinstance(selected, list):
        return set()
    ids: set[str] = set()
    for item in selected:
        if not isinstance(item, Mapping):
            continue
        chunk_id = str(item.get("chunk_id") or "")
        metadata = chunk_index.get(chunk_id)
        if metadata:
            value = compound_record_id(metadata)
            if value:
                ids.add(value)
    return ids


def metrics_for_response(row: Mapping[str, object], result: Mapping[str, object], chunk_index: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    trace = result.get("trace") if isinstance(result.get("trace"), Mapping) else {}
    answer = str(result.get("answer") or "")
    actual_status = str(result.get("status") or "")
    actual_intent = str(trace.get("intent") or "")
    required = expected_required(row)
    forbidden = expected_forbidden(row)
    required_hits = [fact for fact in required if fact_present(answer, fact)]
    forbidden_hits = [fact for fact in forbidden if fact_present(answer, fact)]
    selected = trace_selected_ids(trace, chunk_index)
    expected = {str(value) for value in row.get("evidence_ids", []) if str(value)}
    status_correct = actual_status == str(row.get("expected_status") or "")
    intent_correct = actual_intent == str(row.get("intent") or "")
    evidence_hit = bool(selected & expected) if expected else str(row.get("expected_status")) != "ok"
    answer_correct = status_correct and len(required_hits) == len(required) and not forbidden_hits
    validator = trace.get("validator") if isinstance(trace.get("validator"), Mapping) else {}
    validator_status = str(validator.get("status") or "")
    factual = str(row.get("expected_status")) == "ok" and str(row.get("answer_mode")) not in {"system", "abstention", "clarification"}
    unsupported = bool(factual and actual_status == "ok" and validator_status not in {"", "ok"})
    entities = trace.get("entities") if isinstance(trace.get("entities"), Mapping) else {}
    state_value = result.get("conversation_state")
    if not isinstance(state_value, Mapping):
        state_value = result.get("state")
    state = state_value if isinstance(state_value, Mapping) else {}
    method_correct = not row.get("admission_method") or str(entities.get("admission_method") or "") == str(row.get("admission_method"))
    major_expected = str(row.get("major") or "")
    major_actual = str(entities.get("major_name") or "")
    major_correct = not major_expected or fold(major_expected) == fold(major_actual) or fact_present(answer, major_expected)
    year_expected = int(row.get("year") or TARGET_YEAR)
    year_actual = entities.get("year")
    try:
        year_correct = int(year_actual) == year_expected if year_expected == TARGET_YEAR else actual_status == "no_data"
    except (TypeError, ValueError):
        year_correct = False
    safety_violation = bool(GUARANTEE_RE.search(answer))
    return {
        "id": row.get("id"),
        "family_id": row.get("family_id"),
        "split": row.get("split"),
        "conversation_id": row.get("conversation_id"),
        "turn_index": row.get("turn_index"),
        "question": row.get("question"),
        "expected_intent": row.get("intent"),
        "actual_intent": actual_intent,
        "expected_status": row.get("expected_status"),
        "actual_status": actual_status,
        "status_correct": status_correct,
        "intent_correct": intent_correct,
        "expected_evidence_count": len(expected),
        "selected_evidence_count": len(selected),
        "evidence_hit": evidence_hit,
        "required_count": len(required),
        "required_hit_count": len(required_hits),
        "forbidden_hit_count": len(forbidden_hits),
        "answer_correct": answer_correct,
        "grounded": bool(not factual or validator_status in {"", "ok"}),
        "faithful": bool(not factual or validator_status in {"", "ok"}),
        "unsupported_claim": unsupported,
        "method_correct": method_correct,
        "major_correct": major_correct,
        "year_correct": year_correct,
        "safety_violation": safety_violation,
        "answer": answer,
        "validator_status": validator_status,
        "validator_reason": validator.get("reason") if isinstance(validator, Mapping) else "",
        "trace": trace,
        "result_state": state,
        "selected_evidence_ids": sorted(selected),
    }


def run_e2e(rows: list[dict[str, object]], retriever: DHVRetriever, chunk_index: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    llm = EvidenceEchoLLM()
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    singletons: list[dict[str, object]] = []
    for row in rows:
        conversation_id = str(row.get("conversation_id") or "")
        if conversation_id:
            grouped[conversation_id].append(row)
        else:
            singletons.append(row)
    output: list[dict[str, object]] = []
    for row in singletons:
        try:
            result = ask_chatbot(
                str(row.get("question") or ""),
                retriever=retriever,
                llm=llm,
                conversation_state=row.get("state_before") if isinstance(row.get("state_before"), Mapping) else None,
            )
            output.append(metrics_for_response(row, result, chunk_index))
        except Exception as exc:
            output.append({
                "id": row.get("id"), "family_id": row.get("family_id"), "split": row.get("split"),
                "conversation_id": row.get("conversation_id"), "turn_index": row.get("turn_index"),
                "question": row.get("question"), "expected_intent": row.get("intent"), "actual_intent": "",
                "expected_status": row.get("expected_status"), "actual_status": "error", "status_correct": False,
                "intent_correct": False, "expected_evidence_count": len(row.get("evidence_ids", [])),
                "selected_evidence_count": 0, "evidence_hit": False, "required_count": len(expected_required(row)),
                "required_hit_count": 0, "forbidden_hit_count": 0, "answer_correct": False,
                "grounded": False, "faithful": False, "unsupported_claim": False, "method_correct": False,
                "major_correct": False, "year_correct": False, "safety_violation": False, "answer": "",
                "validator_status": "", "validator_reason": str(exc), "trace": {}, "result_state": {},
                "selected_evidence_ids": [],
            })
    for conversation_id, conversation_rows in grouped.items():
        state: Mapping[str, object] = {}
        for row in sorted(conversation_rows, key=lambda item: (int(item.get("turn_index") or 0), str(item.get("id")))):
            try:
                result = ask_chatbot(
                    str(row.get("question") or ""),
                    retriever=retriever,
                    llm=llm,
                    conversation_state=state or (row.get("state_before") if isinstance(row.get("state_before"), Mapping) else None),
                )
                item = metrics_for_response(row, result, chunk_index)
                state_value = result.get("conversation_state") or result.get("state") or {}
                if isinstance(state_value, Mapping):
                    state = dict(state_value)
                output.append(item)
            except Exception as exc:
                output.append({
                    "id": row.get("id"), "family_id": row.get("family_id"), "split": row.get("split"),
                    "conversation_id": conversation_id, "turn_index": row.get("turn_index"),
                    "question": row.get("question"), "expected_intent": row.get("intent"), "actual_intent": "",
                    "expected_status": row.get("expected_status"), "actual_status": "error", "status_correct": False,
                    "intent_correct": False, "expected_evidence_count": len(row.get("evidence_ids", [])),
                    "selected_evidence_count": 0, "evidence_hit": False, "required_count": len(expected_required(row)),
                    "required_hit_count": 0, "forbidden_hit_count": 0, "answer_correct": False,
                    "grounded": False, "faithful": False, "unsupported_claim": False, "method_correct": False,
                    "major_correct": False, "year_correct": False, "safety_violation": False, "answer": "",
                    "validator_status": "", "validator_reason": str(exc), "trace": {}, "result_state": dict(state),
                    "selected_evidence_ids": [],
                })
    return sorted(output, key=lambda item: str(item.get("id")))


def run_retrieval(
    rows: list[dict[str, object]],
    retriever: DHVRetriever,
    dense_retriever: OfflineDenseRetriever,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("expected_status")) != "ok" or not row.get("evidence_ids"):
            continue
        state = ConversationState.from_value(row.get("state_before"), default_year=TARGET_YEAR)
        analysis = analyze_question(str(row.get("question") or ""), state, default_year=TARGET_YEAR)
        plan = route_question(analysis, state, target_year=TARGET_YEAR)
        if plan.needs_clarification or not plan.categories:
            continue
        expected = {str(value) for value in row.get("evidence_ids", [])}
        variants = retrieve_variants(retriever, dense_retriever, plan, str(row.get("question") or ""), top_k=5)
        for retriever_name, documents in variants.items():
            metrics = ranking_metrics(expected, documents, 5)
            reports.append({
                "id": row.get("id"),
                "family_id": row.get("family_id"),
                "split": row.get("split"),
                "retriever": retriever_name,
                "eligible": True,
                "expected_evidence_count": len(expected),
                "hit_at_1": ranking_metrics(expected, documents, 1)["hit_at_k"],
                "hit_at_3": ranking_metrics(expected, documents, 3)["hit_at_k"],
                "hit_at_5": metrics["hit_at_k"],
                "recall_at_1": ranking_metrics(expected, documents, 1)["recall_at_k"],
                "recall_at_3": ranking_metrics(expected, documents, 3)["recall_at_k"],
                "recall_at_5": metrics["recall_at_k"],
                "mrr": metrics["mrr"],
            })
    return reports


def classification_metrics(results: list[Mapping[str, object]]) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    labels = sorted({str(item.get("expected_intent") or "") for item in results} | {str(item.get("actual_intent") or "") for item in results})
    rows: list[dict[str, object]] = []
    matrix: list[dict[str, object]] = []
    for label in labels:
        tp = sum(item.get("expected_intent") == label and item.get("actual_intent") == label for item in results)
        fp = sum(item.get("expected_intent") != label and item.get("actual_intent") == label for item in results)
        fn = sum(item.get("expected_intent") == label and item.get("actual_intent") != label for item in results)
        support = sum(item.get("expected_intent") == label for item in results)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({"intent": label, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": support})
    for expected in labels:
        for actual in labels:
            matrix.append({"expected_intent": expected, "actual_intent": actual, "count": sum(item.get("expected_intent") == expected and item.get("actual_intent") == actual for item in results)})
    accuracy = mean(bool(item.get("intent_correct")) for item in results) if results else 0.0
    macro_precision = mean(float(item["precision"]) for item in rows) if rows else 0.0
    macro_recall = mean(float(item["recall"]) for item in rows) if rows else 0.0
    macro_f1 = mean(float(item["f1"]) for item in rows) if rows else 0.0
    return {
        "cases": len(results),
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
    }, rows, matrix


def phase5_intent_model_metrics(rows: list[dict[str, object]], model_path: Path = INTENT_MODEL) -> dict[str, object]:
    """Score the frozen Phase 5 intent model without fitting on evaluation rows."""

    model = IntentClassifier.from_dict(json.loads(model_path.read_text(encoding="utf-8")))

    def score(subset: list[dict[str, object]]) -> dict[str, object]:
        eligible = [
            row for row in subset
            if str(row.get("intent") or "") not in {"GREETING", "SCHOOL_INFO"}
        ]
        predictions: list[tuple[str, str]] = []
        for row in eligible:
            prediction = model.predict(str(row.get("question") or ""))
            predictions.append((str(row.get("intent") or ""), prediction.intent if prediction else ""))
        labels = sorted({expected for expected, _ in predictions} | {actual for _, actual in predictions})
        per_intent: list[dict[str, object]] = []
        for label in labels:
            tp = sum(expected == label and actual == label for expected, actual in predictions)
            fp = sum(expected != label and actual == label for expected, actual in predictions)
            fn = sum(expected == label and actual != label for expected, actual in predictions)
            support = sum(expected == label for expected, _ in predictions)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            per_intent.append({
                "intent": label,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": support,
            })
        return {
            "cases": len(eligible),
            "accuracy": round(mean(expected == actual for expected, actual in predictions), 4) if predictions else 0.0,
            "macro_precision": round(mean(float(item["precision"]) for item in per_intent), 4) if per_intent else 0.0,
            "macro_recall": round(mean(float(item["recall"]) for item in per_intent), 4) if per_intent else 0.0,
            "macro_f1": round(mean(float(item["f1"]) for item in per_intent), 4) if per_intent else 0.0,
            "per_intent": per_intent,
        }

    development_train = [
        row for row in rows
        if row.get("split") == "train" and row.get("development_split") == "train"
    ]
    development_dev = [
        row for row in rows
        if row.get("split") == "train" and row.get("development_split") == "dev"
    ]
    final_test = [row for row in rows if row.get("split") == "test"]
    payload = {
        "model_path": str(model_path),
        "training_examples": sum(int(value) for value in model.class_documents.values()),
        "test_rows_used_for_training": 0,
        "development_train": score(development_train),
        "development_dev": score(development_dev),
        "final_test_200": score(final_test),
    }
    return payload


def aggregate_answer(results: list[Mapping[str, object]]) -> dict[str, object]:
    factual = [item for item in results if item.get("expected_status") == "ok" and item.get("expected_evidence_count", 0)]
    return {
        "cases": len(results),
        "answer_correctness": round(mean(bool(item.get("answer_correct")) for item in results), 4) if results else 0.0,
        "status_accuracy": round(mean(bool(item.get("status_correct")) for item in results), 4) if results else 0.0,
        "groundedness": round(mean(bool(item.get("grounded")) for item in factual), 4) if factual else 0.0,
        "faithfulness": round(mean(bool(item.get("faithful")) for item in factual), 4) if factual else 0.0,
        "unsupported_claim_rate": round(mean(bool(item.get("unsupported_claim")) for item in factual), 4) if factual else 0.0,
        "required_fact_accuracy": round(mean((int(item.get("required_hit_count", 0)) == int(item.get("required_count", 0))) for item in factual), 4) if factual else 0.0,
        "safety_guarantee_violations": sum(bool(item.get("safety_violation")) for item in results),
    }


def binary_status_metrics(results: list[Mapping[str, object]], status: str) -> dict[str, object]:
    expected = [item for item in results if item.get("expected_status") == status]
    predicted = [item for item in results if item.get("actual_status") == status]
    tp = sum(item.get("expected_status") == status and item.get("actual_status") == status for item in results)
    fp = sum(item.get("expected_status") != status and item.get("actual_status") == status for item in results)
    fn = sum(item.get("expected_status") == status and item.get("actual_status") != status for item in results)
    return {
        "expected": len(expected),
        "predicted": len(predicted),
        "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
        "accuracy": round(mean(item.get("actual_status") == status for item in expected), 4) if expected else 0.0,
    }


def aggregate_retrieval(reports: list[Mapping[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for retriever_name in ("Dense", "BM25", "Hybrid/RRF"):
        items = [item for item in reports if item.get("retriever") == retriever_name]
        output.append({
            "retriever": retriever_name,
            "eligible_cases": len(items),
            "hit_at_1": round(mean(float(item["hit_at_1"]) for item in items), 4) if items else 0.0,
            "hit_at_3": round(mean(float(item["hit_at_3"]) for item in items), 4) if items else 0.0,
            "hit_at_5": round(mean(float(item["hit_at_5"]) for item in items), 4) if items else 0.0,
            "recall_at_1": round(mean(float(item["recall_at_1"]) for item in items), 4) if items else 0.0,
            "recall_at_3": round(mean(float(item["recall_at_3"]) for item in items), 4) if items else 0.0,
            "recall_at_5": round(mean(float(item["recall_at_5"]) for item in items), 4) if items else 0.0,
            "mrr": round(mean(float(item["mrr"]) for item in items), 4) if items else 0.0,
        })
    return output


def evidence_metrics(rows: list[dict[str, object]], results: list[Mapping[str, object]]) -> dict[str, object]:
    eligible = [
        item for item in results
        if item.get("expected_status") == "ok" and int(item.get("expected_evidence_count", 0)) > 0
    ]
    precision_values: list[float] = []
    recall_values: list[float] = []
    hit_values: list[float] = []
    for item in eligible:
        expected = set()
        for row in rows:
            if row.get("id") == item.get("id"):
                expected = {str(value) for value in row.get("evidence_ids", [])}
                break
        selected = set(item.get("selected_evidence_ids", []))
        precision_values.append(len(selected & expected) / len(selected) if selected else 0.0)
        recall_values.append(len(selected & expected) / len(expected) if expected else 0.0)
        hit_values.append(float(bool(selected & expected)))
    return {
        "eligible_cases": len(eligible),
        "evidence_precision": round(mean(precision_values), 4) if precision_values else 0.0,
        "evidence_recall": round(mean(recall_values), 4) if recall_values else 0.0,
        "evidence_hit_rate": round(mean(hit_values), 4) if hit_values else 0.0,
    }


def multi_turn_metrics(results: list[Mapping[str, object]], rows: list[dict[str, object]]) -> dict[str, object]:
    row_by_id = {str(row.get("id")): row for row in rows}
    groups: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for result in results:
        if result.get("conversation_id"):
            groups[str(result["conversation_id"])].append(result)
    state_retention: list[bool] = []
    entity_carry: list[bool] = []
    method_carry: list[bool] = []
    score_carry: list[bool] = []
    context_relevance: list[bool] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: int(item.get("turn_index") or 0))
        if len(ordered) < 2:
            continue
        first, second = ordered[0], ordered[1]
        expected = row_by_id.get(str(first.get("id")), {})
        expected_state = expected.get("expected_state") if isinstance(expected.get("expected_state"), Mapping) else {}
        state = second.get("result_state") if isinstance(second.get("result_state"), Mapping) else {}
        expected_major = str(expected_state.get("current_major") or "")
        expected_method = str(expected_state.get("current_method") or "")
        expected_score = digits(expected_state.get("score"))
        state_retention.append(bool(expected_major and fold(state.get("current_major")) == fold(expected_major)))
        entity_carry.append(bool(expected_major and fold(state.get("current_major")) == fold(expected_major)))
        method_carry.append(bool(expected_method and str(state.get("current_method") or "") == expected_method))
        state_text = json.dumps(state, ensure_ascii=False)
        score_carry.append(bool(expected_score and expected_score in digits(state_text)))
        second_answer = str(second.get("answer") or "")
        context_relevance.append(bool(second.get("answer_correct")) and not (expected_score and expected_score in digits(second_answer)))
    return {
        "conversations": len(groups),
        "state_retention_accuracy": round(mean(state_retention), 4) if state_retention else 0.0,
        "entity_carry_over_accuracy": round(mean(entity_carry), 4) if entity_carry else 0.0,
        "method_carry_over_accuracy": round(mean(method_carry), 4) if method_carry else 0.0,
        "score_carry_over_accuracy": round(mean(score_carry), 4) if score_carry else 0.0,
        "context_relevance_accuracy": round(mean(context_relevance), 4) if context_relevance else 0.0,
    }


def classify_failure(row: Mapping[str, object], result: Mapping[str, object]) -> str | None:
    if result.get("intent_correct") is not True:
        return "INTENT_ERROR"
    if row.get("expected_status") == "out_of_scope" and result.get("actual_status") != "out_of_scope":
        return "SCOPE_ERROR"
    if row.get("expected_status") in {"no_data", "clarification"} and result.get("actual_status") != row.get("expected_status"):
        return "ROUTER_ERROR"
    if row.get("expected_status") == "ok" and row.get("evidence_ids") and not result.get("evidence_hit"):
        return "EVIDENCE_ERROR"
    if row.get("expected_status") == "ok" and result.get("method_correct") is not True:
        return "FACT_SELECTION_ERROR"
    if row.get("expected_status") == "ok" and result.get("required_hit_count") != result.get("required_count"):
        validator_reason = str(result.get("validator_reason") or "")
        return "GENERATION_ERROR" if not validator_reason else "VALIDATOR_ERROR"
    if result.get("safety_violation"):
        return "GENERATION_ERROR"
    if result.get("answer_correct") is not True:
        return "GENERATION_ERROR"
    return None


def manual_sample(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_category: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: str(item.get("id"))):
        by_category[str(row.get("category"))].append(row)
    sample: list[dict[str, object]] = []
    for category, category_rows in sorted(by_category.items()):
        sample.extend(category_rows[:3])
    return sample


def write_csv(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, tuple, set)) else value for key, value in row.items()}
            writer.writerow(normalized)


def write_audit_report(audit: Mapping[str, object], rows: list[dict[str, object]], runtime_stats: Mapping[str, object]) -> None:
    lines = [
        "# Phase 5 dataset audit",
        "",
        f"- Total rows: {audit.get('total')}",
        f"- Split: {audit.get('split_counts')}",
        f"- Development split: {audit.get('development_counts')}",
        f"- Unique IDs: {audit.get('unique_ids')}",
        f"- Exact duplicate questions: {len(audit.get('exact_duplicate_questions', {}))}",
        f"- Normalized duplicate questions: {len(audit.get('normalized_duplicate_questions', {}))}",
        f"- Near-duplicate flags (cap 200): {audit.get('near_duplicate_count_capped_at_200')}",
        f"- Train/test family overlap: {len(audit.get('family_split_overlap', []))}",
        f"- Invalid evidence references: {len(audit.get('invalid_evidence', []))}",
        f"- Unsupported factual rows: {len(audit.get('unsupported_factual_answers', []))}",
        f"- Wrong-year source labels: {len(audit.get('wrong_year_sources', []))}",
        "",
        "## Runtime verified corpus",
        "",
        f"{json.dumps(dict(runtime_stats), ensure_ascii=False)}",
        "",
        "## Category distribution",
        "",
        "| Category | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(Counter(str(row.get("category")) for row in rows).items()))
    lines.extend(["", "## Leakage conclusion", ""])
    if audit.get("valid"):
        lines.append("Dataset integrity checks pass: 1,000 rows, 800/200 split, 640/160 development split, no exact/normalized duplicate, no family overlap, and all factual evidence references resolve to verified 2026 records.")
    else:
        lines.append("Dataset integrity checks need review; see summary.json for the exact blocking fields.")
    (REPORT_DIR / "dataset_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_final_report(summary: Mapping[str, object], audit: Mapping[str, object]) -> None:
    def pct(value: object) -> str:
        try:
            return f"{float(value) * 100:.2f}%"
        except (TypeError, ValueError):
            return "n/a"

    intent = summary.get("intent", {}) if isinstance(summary.get("intent"), Mapping) else {}
    intent_model = summary.get("intent_model", {}) if isinstance(summary.get("intent_model"), Mapping) else {}
    retrieval = summary.get("retrieval", []) if isinstance(summary.get("retrieval"), list) else []
    lines = [
        "# PHASE 5 – DATASET AND END-TO-END EVALUATION REPORT",
        "",
        "## 1. Dataset Summary",
        "",
        f"Total: {audit.get('total')} | Development: {audit.get('split_counts', {}).get('train')} | Final test: {audit.get('split_counts', {}).get('test')} | Dev inside development: {audit.get('development_counts', {}).get('dev')}",
        f"Dataset valid: {audit.get('valid')}",
        "",
        "## 2. Data Quality and Split Leakage",
        "",
        f"Exact duplicates: {len(audit.get('exact_duplicate_questions', {}))}; normalized duplicates: {len(audit.get('normalized_duplicate_questions', {}))}; near-duplicate flags: {audit.get('near_duplicate_count_capped_at_200')}; family overlap: {len(audit.get('family_split_overlap', []))}.",
        "",
        "## 3. Intent Evaluation",
        "",
        f"Accuracy: {pct(intent.get('accuracy'))}; Macro Precision: {pct(intent.get('macro_precision'))}; Macro Recall: {pct(intent.get('macro_recall'))}; Macro F1: {pct(intent.get('macro_f1'))}.",
        f"Frozen Phase 5 model — development train: {json.dumps(intent_model.get('development_train', {}), ensure_ascii=False)}; development dev: {json.dumps(intent_model.get('development_dev', {}), ensure_ascii=False)}; final test: {json.dumps(intent_model.get('final_test_200', {}), ensure_ascii=False)}.",
        "Per-intent metrics and confusion matrix are in `intent_metrics.csv` and `confusion_matrix.csv`.",
        "",
        "## 4. Retrieval Evaluation",
        "",
        "| Retriever | Hit@1 | Hit@3 | Hit@5 | Recall@1 | Recall@3 | Recall@5 | MRR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in retrieval:
        lines.append(
            f"| {item.get('retriever')} | {pct(item.get('hit_at_1'))} | "
            f"{pct(item.get('hit_at_3'))} | {pct(item.get('hit_at_5'))} | "
            f"{pct(item.get('recall_at_1'))} | {pct(item.get('recall_at_3'))} | "
            f"{pct(item.get('recall_at_5'))} | {item.get('mrr')} |"
        )
    lines.extend([
        "",
        "## 5. Evidence, Deterministic Facts and Answers",
        "",
        f"Evidence: {json.dumps(summary.get('evidence'), ensure_ascii=False)}",
        f"Deterministic facts: {json.dumps(summary.get('deterministic_facts'), ensure_ascii=False)}",
        f"Answer: {json.dumps(summary.get('answer'), ensure_ascii=False)}",
        "",
        "## 6. Abstention and Clarification",
        "",
        f"NO_DATA: {json.dumps(summary.get('no_data'), ensure_ascii=False)}",
        f"OUT_OF_SCOPE: {json.dumps(summary.get('out_of_scope'), ensure_ascii=False)}",
        f"CLARIFICATION: {json.dumps(summary.get('clarification'), ensure_ascii=False)}",
        "",
        "## 7. Multi-turn, Year Isolation and Safety",
        "",
        f"Multi-turn: {json.dumps(summary.get('multi_turn'), ensure_ascii=False)}",
        f"Wrong-year leakage: {json.dumps(summary.get('year_isolation'), ensure_ascii=False)}",
        f"Admission guarantee violations: {summary.get('answer', {}).get('safety_guarantee_violations') if isinstance(summary.get('answer'), Mapping) else 'n/a'}",
        "",
        "## 8. Failure Breakdown",
        "",
        "| Failure Type | Count | Percentage |",
        "|---|---:|---:|",
    ])
    failures = summary.get("failure_breakdown", {})
    total = sum(int(value) for value in failures.values()) if isinstance(failures, Mapping) else 0
    for key, value in sorted(failures.items()) if isinstance(failures, Mapping) else []:
        lines.append(f"| {key} | {value} | {pct(float(value) / total if total else 0.0)} |")
    lines.extend([
        "",
        "## 9. Environment and Execution Notes",
        "",
        f"Dense retrieval backend: {json.dumps(summary.get('dense_backend'), ensure_ascii=False)}.",
        "Generation was evaluated with the deterministic evidence-echo adapter because this run does not require Ollama. Retrieval/evidence/router/planner/validator call paths were executed. No test-set rule, threshold, prompt, retrieval configuration or model tuning was performed after reading final-test results.",
        "",
        "## 10. Final Test Results",
        "",
        "The final-test section contains only the locked 200-row holdout. Development results are reported separately in `summary.json` under `development_baseline`.",
        "",
        f"## 11. Evaluation Status: {summary.get('evaluation_status', 'BLOCKED')}",
        "",
    ])
    if summary.get("evaluation_status") == "BLOCKED":
        lines.append("BLOCKED: dataset integrity checks did not pass; inspect dataset_audit.md and summary.json.")
    elif not summary.get("final_test_completed"):
        lines.append("BLOCKED: final test did not complete.")
    else:
        lines.append(
            "EVALUATION_READY: dataset valid, split valid, evaluator ran, and final metrics were generated. "
            "See the separate quality verdict below."
        )
    lines.extend([
        "",
        f"## 12. Quality Verdict: {summary.get('quality_status', 'NEEDS_IMPROVEMENT')}",
        "",
        "PASS means no failed holdout cases were reported; NEEDS_IMPROVEMENT means the evaluation completed but the holdout still contains actionable failures; BLOCKED means the evaluation could not be completed.",
    ])
    (REPORT_DIR / "PHASE_5_EVALUATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_split(
    split_name: str,
    rows: list[dict[str, object]],
    retriever: DHVRetriever,
    chunk_index: Mapping[str, Mapping[str, object]],
    dense_retriever: OfflineDenseRetriever,
) -> dict[str, object]:
    results = run_e2e(rows, retriever, chunk_index)
    retrieval_rows = run_retrieval(rows, retriever, dense_retriever)
    intent_summary, intent_rows, matrix = classification_metrics(results)
    answer = aggregate_answer(results)
    row_by_id = {str(row.get("id")): row for row in rows}
    wrong_year_answers = sum(
        int(row_by_id[str(item.get("id"))].get("year") or TARGET_YEAR) != TARGET_YEAR
        and item.get("actual_status") == "ok"
        for item in results
        if str(item.get("id")) in row_by_id
    )
    summary = {
        "split": split_name,
        "cases": len(rows),
        "intent": intent_summary,
        "intent_rows": intent_rows,
        "confusion_matrix": matrix,
        "retrieval_rows": retrieval_rows,
        "retrieval": aggregate_retrieval(retrieval_rows),
        "evidence": evidence_metrics(rows, results),
        "answer": answer,
        "no_data": binary_status_metrics(results, "no_data"),
        "out_of_scope": binary_status_metrics(results, "out_of_scope"),
        "clarification": binary_status_metrics(results, "clarification"),
        "multi_turn": multi_turn_metrics(results, rows),
        "year_isolation": {
            "explicit_non_target_year_cases": sum(int(row.get("year") or TARGET_YEAR) != TARGET_YEAR for row in rows),
            "wrong_year_answers": wrong_year_answers,
        },
        "results": results,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "test", "all"), default="all")
    parser.add_argument("--skip-test", action="store_true")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    record_index = verified_record_index()
    audit = dataset_audit(rows, record_index)
    if LOCK.exists():
        test_rows = [row for row in rows if row.get("split") == "test"]
        test_path_hash = hashlib.sha256((DATA_DIR / "test_200.jsonl").read_bytes()).hexdigest()
        audit["test_lock_matches"] = test_path_hash == LOCK.read_text(encoding="utf-8").strip()
        if not audit["test_lock_matches"]:
            raise RuntimeError("test_200.jsonl does not match test_200.lock")
    retriever, runtime_stats, chunk_index, dense_retriever = setup_runtime()
    intent_model = phase5_intent_model_metrics(rows)
    development_rows = [row for row in rows if row.get("split") == "train"]
    test_rows = [row for row in rows if row.get("split") == "test"]
    development_summary: dict[str, object] | None = None
    final_summary: dict[str, object] | None = None
    if args.split in {"development", "all"}:
        development_summary = evaluate_split("development_baseline", development_rows, retriever, chunk_index, dense_retriever)
    if args.split in {"test", "all"} and not args.skip_test:
        final_summary = evaluate_split("final_test_200", test_rows, retriever, chunk_index, dense_retriever)

    selected = final_summary or development_summary or {}
    result_rows = list(selected.get("results", [])) if isinstance(selected.get("results"), list) else []
    failed_rows: list[dict[str, object]] = []
    row_lookup = {str(row.get("id")): row for row in (test_rows if final_summary else development_rows)}
    for result in result_rows:
        row = row_lookup.get(str(result.get("id")), {})
        failure = classify_failure(row, result)
        if failure:
            failed_rows.append({
                "id": result.get("id"),
                "question": result.get("question"),
                "expected": json.dumps({"intent": row.get("intent"), "status": row.get("expected_status"), "evidence_ids": row.get("evidence_ids", [])}, ensure_ascii=False),
                "actual": json.dumps({"intent": result.get("actual_intent"), "status": result.get("actual_status"), "answer": result.get("answer", "")}, ensure_ascii=False),
                "failure_type": failure,
                "earliest_failing_stage": failure,
                "evidence": json.dumps(result.get("selected_evidence_ids", []), ensure_ascii=False),
            })

    failure_counts = Counter(str(item["failure_type"]) for item in failed_rows)
    combined = {
        "dataset_audit": audit,
        "runtime_corpus": runtime_stats,
        "dense_backend": dense_retriever.metadata,
        "development_baseline": development_summary and {key: value for key, value in development_summary.items() if key not in {"results", "intent_rows", "confusion_matrix", "retrieval_rows"}},
        "final_test": final_summary and {key: value for key, value in final_summary.items() if key not in {"results", "intent_rows", "confusion_matrix", "retrieval_rows"}},
        "intent": selected.get("intent", {}),
        "intent_model": intent_model,
        "retrieval": selected.get("retrieval", []),
        "evidence": selected.get("evidence", {}),
        "deterministic_facts": {
            "fact_selection_accuracy": selected.get("answer", {}).get("required_fact_accuracy") if isinstance(selected.get("answer"), Mapping) else 0.0,
            "method_mapping_accuracy": round(mean(bool(item.get("method_correct")) for item in result_rows), 4) if result_rows else 0.0,
            "major_mapping_accuracy": round(mean(bool(item.get("major_correct")) for item in result_rows), 4) if result_rows else 0.0,
            "year_accuracy": round(mean(bool(item.get("year_correct")) for item in result_rows), 4) if result_rows else 0.0,
        },
        "answer": selected.get("answer", {}),
        "no_data": selected.get("no_data", {}),
        "out_of_scope": selected.get("out_of_scope", {}),
        "clarification": selected.get("clarification", {}),
        "multi_turn": selected.get("multi_turn", {}),
        "year_isolation": selected.get("year_isolation", {}),
        "failure_breakdown": dict(failure_counts),
        "evaluation_status": (
            "EVALUATION_READY"
            if audit.get("valid") and final_summary is not None and len(test_rows) == 200
            else "BLOCKED"
        ),
        "quality_status": "PASS" if not failure_counts else "NEEDS_IMPROVEMENT",
        "final_test_completed": final_summary is not None and len(test_rows) == 200,
        "holdout_policy": "test_200 is locked and report-only; no tuning performed",
    }
    (REPORT_DIR / "summary.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_csv(REPORT_DIR / "evaluation_results.csv", result_rows)
    write_csv(REPORT_DIR / "failed_cases.csv", failed_rows)
    write_csv(REPORT_DIR / "intent_metrics.csv", list(selected.get("intent_rows", [])))
    write_csv(
        REPORT_DIR / "intent_model_metrics.csv",
        [
            {"split": split_name, **metrics}
            for split_name in ("development_train", "development_dev", "final_test_200")
            for metrics in [intent_model.get(split_name, {})]
            if isinstance(metrics, Mapping)
        ],
    )
    write_csv(REPORT_DIR / "confusion_matrix.csv", list(selected.get("confusion_matrix", [])))
    write_csv(REPORT_DIR / "retrieval_metrics.csv", list(selected.get("retrieval_rows", [])))
    write_csv(DATA_DIR / "manual_review_sample.csv", manual_sample(rows))
    write_audit_report(audit, rows, runtime_stats)
    write_final_report(combined, audit)
    print(json.dumps({
        "dataset_valid": audit.get("valid"),
        "development_completed": development_summary is not None,
        "final_test_completed": combined["final_test_completed"],
        "final_cases": len(test_rows),
        "final_intent": combined.get("intent"),
        "final_answer": combined.get("answer"),
        "failure_breakdown": dict(failure_counts),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
