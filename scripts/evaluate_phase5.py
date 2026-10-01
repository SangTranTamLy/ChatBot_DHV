"""Evaluate the chatbot against the user-provided canonical 500-row Q&A set.

The workbook supplies the question, reference answer and source text.  This
evaluator never invents labels, paraphrases, evidence IDs or additional rows.
It reports provenance integrity and a transparent lexical/numeric answer-match
proxy; semantic correctness still requires human review of the reference answer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.run_evaluation import EvidenceEchoLLM, OfflineCorpusStore  # noqa: E402
from src.chatbot.rag_chain import ask_chatbot  # noqa: E402
from src.config.settings import settings  # noqa: E402
from src.ingestion.loader import load_verified_documents  # noqa: E402
from src.ingestion.splitter import split_documents  # noqa: E402
from src.retrieval.retriever import DHVRetriever  # noqa: E402


DATA_DIR = ROOT / "data" / "evaluation"
MASTER = DATA_DIR / "qa_master_500.jsonl"
LOCK = DATA_DIR / "qa_master_500.lock"
REPORT_DIR = ROOT / "reports" / "phase5"
TOKEN_RE = re.compile(r"\d[\d.,]*|[A-Za-zÀ-ỹĐđ]+", re.UNICODE)
NUMBER_RE = re.compile(r"\d[\d.,]*")


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.lower().replace("đ", "d")
    return " ".join(TOKEN_RE.findall(text))


def load_rows(path: Path = MASTER) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def dataset_audit(rows: list[dict[str, object]]) -> dict[str, object]:
    ids = [str(row.get("id") or "") for row in rows]
    questions = [fold(row.get("question")) for row in rows]
    lock_matches = (
        LOCK.exists()
        and hashlib.sha256(MASTER.read_bytes()).hexdigest()
        == LOCK.read_text(encoding="utf-8").strip()
    )
    missing_fields = [
        f"{row.get('id')}:{field}"
        for row in rows
        for field in ("id", "tt", "question", "reference_answer", "source", "source_row_sha256")
        if not str(row.get(field) or "").strip()
    ]
    expected_ids = [f"UQ{index:04d}" for index in range(1, 501)]
    duplicate_questions = sorted(
        question for question, count in Counter(questions).items() if question and count > 1
    )
    return {
        "dataset": "user_canonical_500",
        "total": len(rows),
        "expected_total": 500,
        "canonical_only": all(row.get("split") == "canonical" for row in rows),
        "source_rows": sum(bool(str(row.get("source_row_sha256") or "")) for row in rows),
        "unique_ids": len(ids) == len(set(ids)) and "" not in ids,
        "sequential_ids": ids == expected_ids,
        "duplicate_questions": duplicate_questions,
        "missing_fields": missing_fields,
        "lock_matches": lock_matches,
        "valid": (
            len(rows) == 500
            and ids == expected_ids
            and all(row.get("split") == "canonical" for row in rows)
            and len(set(ids)) == 500
            and not duplicate_questions
            and not missing_fields
            and lock_matches
        ),
    }


def setup_runtime() -> tuple[DHVRetriever, dict[str, object]]:
    load_result = load_verified_documents(ROOT / "data" / "processed")
    chunks = tuple(split_documents(load_result.documents))
    OfflineCorpusStore.chunks = chunks
    retriever = DHVRetriever(
        settings_obj=settings,
        store_factory=OfflineCorpusStore,
        embedding_factory=lambda **_: object(),
    )
    return retriever, {
        **load_result.stats.as_dict(),
        "chunks_indexed_for_evaluation": len(chunks),
    }


def _numbers(value: object) -> set[str]:
    return {number.replace(",", "").replace(".", "") for number in NUMBER_RE.findall(str(value or ""))}


def _selected_evidence_count(result: Mapping[str, object]) -> int:
    trace = result.get("trace")
    if not isinstance(trace, Mapping):
        return 0
    selection = trace.get("evidence_selection")
    if not isinstance(selection, Mapping):
        return 0
    selected = selection.get("selected")
    return len(selected) if isinstance(selected, list) else 0


def evaluate_row(row: Mapping[str, object], retriever: DHVRetriever, llm: EvidenceEchoLLM) -> dict[str, object]:
    question = str(row.get("question") or "")
    reference = str(row.get("reference_answer") or "")
    reference_tokens = set(fold(reference).split())
    try:
        result = ask_chatbot(question, retriever=retriever, llm=llm)
        answer = str(result.get("answer") or "")
        actual_tokens = set(fold(answer).split())
        matched_tokens = reference_tokens & actual_tokens
        reference_numbers = _numbers(reference)
        answer_numbers = _numbers(answer)
        number_hits = reference_numbers & answer_numbers
        validator = result.get("trace", {}).get("validator", {}) if isinstance(result.get("trace"), Mapping) else {}
        validator_status = validator.get("status") if isinstance(validator, Mapping) else ""
        return {
            "id": row.get("id"),
            "question": question,
            "reference_answer": reference,
            "source": row.get("source"),
            "status": result.get("status"),
            "answer": answer,
            "answer_nonempty": bool(answer.strip()),
            "selected_evidence_count": _selected_evidence_count(result),
            "validator_status": validator_status,
            "reference_token_recall": round(len(matched_tokens) / len(reference_tokens), 4) if reference_tokens else 0.0,
            "reference_number_recall": round(len(number_hits) / len(reference_numbers), 4) if reference_numbers else 1.0,
            "reference_numbers": sorted(reference_numbers),
            "answer_numbers": sorted(answer_numbers),
            "trace": result.get("trace", {}),
        }
    except Exception as exc:
        return {
            "id": row.get("id"),
            "question": question,
            "reference_answer": reference,
            "source": row.get("source"),
            "status": "error",
            "answer": "",
            "answer_nonempty": False,
            "selected_evidence_count": 0,
            "validator_status": "",
            "reference_token_recall": 0.0,
            "reference_number_recall": 0.0,
            "reference_numbers": sorted(_numbers(reference)),
            "answer_numbers": [],
            "error": str(exc),
            "trace": {},
        }


def write_csv(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields and key != "trace":
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, tuple, set)) else value
                for key, value in row.items()
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("canonical", "all"), default="canonical")
    parser.add_argument("--skip-e2e", action="store_true", help="only validate the canonical dataset")
    args = parser.parse_args()

    rows = load_rows()
    audit = dataset_audit(rows)
    if not audit["valid"]:
        raise RuntimeError(f"canonical dataset is invalid: {json.dumps(audit, ensure_ascii=False)}")

    results: list[dict[str, object]] = []
    runtime_stats: dict[str, object] = {}
    if not args.skip_e2e:
        retriever, runtime_stats = setup_runtime()
        llm = EvidenceEchoLLM()
        results = [evaluate_row(row, retriever, llm) for row in rows]

    status_counts = Counter(str(row.get("status") or "") for row in results)
    summary: dict[str, object] = {
        "dataset_audit": audit,
        "runtime_corpus": runtime_stats,
        "cases": len(rows),
        "status_counts": dict(status_counts),
        "answer_nonempty_rate": round(mean(bool(row.get("answer_nonempty")) for row in results), 4) if results else None,
        "reference_token_recall": round(mean(float(row.get("reference_token_recall", 0.0)) for row in results), 4) if results else None,
        "reference_number_recall": round(mean(float(row.get("reference_number_recall", 0.0)) for row in results), 4) if results else None,
        "evidence_selected_rate": round(mean(bool(row.get("selected_evidence_count")) for row in results), 4) if results else None,
        "evaluation_status": "DATASET_VALIDATED" if args.skip_e2e else "EVALUATED",
        "reference_answer_policy": "reference_answer is copied from the workbook; no generated answer replaces it",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(REPORT_DIR / "evaluation_results.csv", results)
    (REPORT_DIR / "dataset_audit.md").write_text(
        "\n".join(
            [
                "# Phase 5 canonical dataset audit",
                "",
                f"- Dataset: user-provided `Nhóm 4_Thu_Thap_Q&A.xlsx`",
                f"- Rows: {audit['total']}/{audit['expected_total']}",
                f"- Canonical-only rows: {audit['canonical_only']}",
                f"- Duplicate questions: {len(audit['duplicate_questions'])}",
                f"- Lock matches: {audit['lock_matches']}",
                f"- Valid: {audit['valid']}",
                "",
                "No 1,000-row dataset, generated questions, generated answers, or old split is used by this active pipeline.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def mean(values: Any) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


if __name__ == "__main__":
    main()


__all__ = ["dataset_audit", "evaluate_row", "load_rows", "main"]
