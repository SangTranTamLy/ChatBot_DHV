"""TASK N regressions for validator contracts, evaluation splits and metrics."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from evaluation.evaluator import (
    EvaluationCase,
    calculate_retrieval_metrics,
    score_answer_case,
    validate_dataset,
)
from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import validate_model_answer
from src.chatbot.query_analysis import analyze_question


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://dhv.edu.vn/task-n"


def _evidence(text: str, *, category: str = "hoc_phi"):
    return build_evidence(
        [
            Document(
                page_content=text,
                metadata={
                    "title": "DHV 2026",
                    "category": category,
                    "year": 2026,
                    "school_code": "DHV",
                    "source_url": SOURCE_URL,
                    "status": "verified",
                    "chunk_id": "task-n-1",
                },
            )
        ]
    )


class TaskNEvaluationTests(unittest.TestCase):
    def test_dataset_is_disjoint_exact_80_20_and_holdout_is_report_only(self) -> None:
        summary = validate_dataset(dataset_dir=PROJECT_ROOT / "evaluation")

        self.assertEqual(summary["total_cases"], 20)
        self.assertEqual(summary["dev_cases"], 16)
        self.assertEqual(summary["holdout_cases"], 4)
        self.assertTrue(summary["disjoint"])
        self.assertEqual(summary["holdout_policy"], "report_only_not_used_for_tuning")
        self.assertEqual(summary["provenance"]["verified_sources"], 6)

    def test_date_and_score_markers_match_equivalent_published_formats(self) -> None:
        case = EvaluationCase(
            case_id="semantic-format-contract",
            question="Điểm trúng tuyển Luật và hạn hồ sơ?",
            answer_contains=("20,0", "21/08/2026"),
        )
        score = score_answer_case(
            case,
            {"status": "ok", "answer": "Luật: 20 điểm; hạn hồ sơ 21/8/2026."},
        )
        self.assertEqual(score["answer_correctness"], 1.0)
        self.assertEqual(score["required_hits"], ["20,0", "21/08/2026"])

    def test_numeric_markers_require_an_exact_value_not_a_substring(self) -> None:
        case = EvaluationCase(
            case_id="exact-numeric-contract",
            question="Ngưỡng là bao nhiêu?",
            answer_contains=("15",),
        )
        score = score_answer_case(
            case,
            {"status": "ok", "answer": "Ngưỡng 150 điểm."},
        )
        self.assertEqual(score["answer_correctness"], 0.0)

    def test_dataset_validation_detects_changed_gold_source_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset_dir = root / "evaluation"
            dataset_dir.mkdir()
            source_path = root / "data" / "raw" / "source.pdf"
            source_path.parent.mkdir(parents=True)
            source_bytes = b"audited evidence source"
            source_path.write_bytes(source_bytes)
            provenance = {
                "raw_file": "data/raw/source.pdf",
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
            dev_rows = [
                {
                    "id": "dev-1",
                    "question": "Question?",
                    "expected_evidence": {"provenance": [provenance]},
                },
                {"id": "dev-2", "question": "Question?"},
                {"id": "dev-3", "question": "Question?"},
                {"id": "dev-4", "question": "Question?"},
            ]
            holdout_rows = [{"id": "holdout-1", "question": "Question?"}]
            (dataset_dir / "dev.jsonl").write_text(
                "\n".join(json.dumps(row) for row in dev_rows), encoding="utf-8"
            )
            (dataset_dir / "holdout.jsonl").write_text(
                json.dumps(holdout_rows[0]), encoding="utf-8"
            )

            verified = validate_dataset(dataset_dir=dataset_dir)
            self.assertEqual(verified["provenance"]["verified_sources"], 1)

            source_path.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                validate_dataset(dataset_dir=dataset_dir)

    def test_retrieval_metrics_measure_hit_precision_recall_and_mrr(self) -> None:
        case = EvaluationCase(
            case_id="retrieval-contract",
            question="Học phí DHV 2026?",
            expected_categories=("hoc_phi",),
            evidence_contains=("12.500.000", "14.500.000"),
        )
        docs = [
            Document(
                page_content="Học phí: 12.500.000 đồng.",
                metadata={"category": "hoc_phi", "chunk_id": "right-1"},
            ),
            Document(
                page_content="Thông tin không liên quan.",
                metadata={"category": "hoc_bong", "chunk_id": "wrong-1"},
            ),
        ]

        metrics = calculate_retrieval_metrics(case, docs, top_k=2)

        self.assertEqual(metrics["hit_at_k"], 1.0)
        self.assertEqual(metrics["precision_at_k"], 0.5)
        self.assertEqual(metrics["recall_at_k"], 0.5)
        self.assertEqual(metrics["mrr"], 1.0)

    def test_answer_metrics_flag_forbidden_claim_as_critical_hallucination(self) -> None:
        case = EvaluationCase(
            case_id="answer-contract",
            question="Điểm sàn CNTT 2026?",
            expected_status="ok",
            answer_contains=("15 điểm",),
            forbidden_claims=("chắc chắn đậu",),
        )

        score = score_answer_case(
            case,
            {
                "status": "ok",
                "answer": "Ngưỡng từ 15 điểm, bạn chắc chắn đậu.",
            },
        )

        self.assertEqual(score["answer_correctness"], 0.0)
        self.assertTrue(score["critical_factual_hallucination"])
        self.assertEqual(score["hallucination"], 1.0)


class TaskNValidatorTests(unittest.TestCase):
    def test_validator_rejects_official_status_claim(self) -> None:
        evidence = _evidence("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")
        result = validate_model_answer(
            "Tôi là chatbot chính thức của DHV. Học phí là 1.250.000 đồng/tín chỉ.",
            evidence,
            question="Học phí DHV 2026?",
            analysis=analyze_question("Học phí DHV 2026?"),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "official_status_claim")

    def test_validator_rejects_answer_year_outside_evidence(self) -> None:
        evidence = _evidence("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")
        result = validate_model_answer(
            "Học phí năm 2027 là 1.250.000 đồng/tín chỉ.",
            evidence,
            question="Học phí DHV 2026?",
            analysis=analyze_question("Học phí DHV 2026?"),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "year_mismatch")

    def test_validator_rejects_unrelated_target_institution(self) -> None:
        evidence = _evidence("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")
        result = validate_model_answer(
            "Đại học Xa lạ công bố học phí là 1.250.000 đồng/tín chỉ.",
            evidence,
            question="Học phí DHV 2026?",
            analysis=analyze_question("Học phí DHV 2026?"),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "institution_mismatch")


if __name__ == "__main__":
    unittest.main()
