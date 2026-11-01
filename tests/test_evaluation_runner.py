from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from evaluation.evaluator import EvaluationCase
from evaluation.run_evaluation import _retrieve_for_case, _retriever, run_evaluation
from src.config.settings import settings


class EvaluationRunnerTests(unittest.TestCase):
    def test_offline_corpus_uses_configured_processed_data_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            processed_path = Path(temp_dir) / "alternate-corpus"
            configured = replace(settings, processed_data_dir=processed_path)
            load_result = SimpleNamespace(documents=())
            with patch(
                "evaluation.run_evaluation.load_verified_documents",
                return_value=load_result,
            ) as loader, patch(
                "evaluation.run_evaluation.split_documents", return_value=[]
            ):
                retriever = _retriever(settings_obj=configured)

        loader.assert_called_once_with(processed_path)
        self.assertIs(retriever.settings, configured)

    def test_top_k_and_same_settings_reach_retrieval_and_metrics(self) -> None:
        configured = replace(settings, retriever_top_k=3)
        case = EvaluationCase(
            case_id="top-k-spy",
            question="Học phí DHV 2026 là bao nhiêu?",
            expected_categories=("hoc_phi",),
            evidence_contains=("1.250.000",),
        )
        calls: dict[str, object] = {}

        class RetrieverSpy:
            def retrieve_with_audit(self, question: str, **kwargs: object) -> object:
                calls["question"] = question
                calls["retrieval"] = kwargs
                return ()

        def capture_retrieval(cases, retrieve, *, top_k: int):
            calls["metric_top_k"] = top_k
            calls["retrieved"] = retrieve(case)
            return {"top_k": top_k}

        with patch("evaluation.run_evaluation.validate_dataset", return_value={}), patch(
            "evaluation.run_evaluation.load_cases", return_value=(case,)
        ), patch(
            "evaluation.run_evaluation._retriever", return_value=RetrieverSpy()
        ) as retriever_factory, patch(
            "evaluation.run_evaluation.evaluate_intents", return_value={}
        ), patch(
            "evaluation.run_evaluation.evaluate_retrieval", side_effect=capture_retrieval
        ), patch(
            "evaluation.run_evaluation.evaluate_answers", return_value={}
        ):
            report = run_evaluation(
                "dev",
                top_k=7,
                settings_obj=configured,
            )

        retriever_factory.assert_called_once_with(settings_obj=configured)
        self.assertEqual(calls["retrieval"]["top_k"], 7)
        self.assertEqual(calls["metric_top_k"], 7)
        self.assertEqual(report["retrieval"]["top_k"], 7)

    def test_multi_issue_evaluation_retrieves_each_issue_and_interleaves_top_k(self) -> None:
        case = EvaluationCase(
            case_id="multi-issue-spy",
            question="CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?",
            expected_categories=("hoc_phi", "hoc_bong", "nganh_dao_tao"),
        )
        calls: list[dict[str, object]] = []

        class RetrieverSpy:
            def retrieve_with_audit(self, question: str, **kwargs: object) -> object:
                calls.append({"question": question, **kwargs})
                category = tuple(kwargs["categories"])[0]
                index = len(calls)
                return SimpleNamespace(
                    documents=(
                        Document(
                            page_content=f"evidence for {category}",
                            metadata={"category": category, "chunk_id": f"chunk-{index}"},
                        ),
                    )
                )

        result = _retrieve_for_case(RetrieverSpy(), case, top_k=5)

        self.assertEqual(len(calls), 3)
        self.assertEqual(
            [tuple(call["categories"])[0] for call in calls],
            ["hoc_phi", "hoc_bong", "nganh_dao_tao"],
        )
        self.assertTrue(all(call["top_k"] == 5 for call in calls))
        scholarship_call = calls[1]
        self.assertNotIn("major_name", scholarship_call["entity_filters"])
        self.assertEqual(
            [document.metadata["category"] for document in result],
            ["hoc_phi", "hoc_bong", "nganh_dao_tao"],
        )


if __name__ == "__main__":
    unittest.main()
