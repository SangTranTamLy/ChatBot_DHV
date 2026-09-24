"""Phase 4 regressions for deterministic score answers and bounded state."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.query_analysis import (
    analyze_question,
    select_relevant_score_facts,
)
from src.chatbot.rag_chain import ask_chatbot
from src.models.local_llm import LocalLLM

from tests.test_task_f import EchoEvidenceLLM, _retriever


SOURCE_URL = "https://dhv.edu.vn/phase-4"


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError(f"deterministic score branch called the LLM: {prompt[:80]}")


def _score_document(
    *,
    score_type: str,
    method: str,
    value: int,
    major_name: str | None = None,
) -> Document:
    label = major_name or "toàn bộ chương trình"
    return Document(
        page_content=f"{label}: {method} {value} điểm.",
        metadata={
            "title": "Phase 4 score rule",
            "category": "nguong_dau_vao",
            "year": 2026,
            "school_code": "DHV",
            "source_url": SOURCE_URL,
            "status": "verified",
            "chunk_id": f"{score_type}-{method}-{major_name or 'global'}",
            "record_type": score_type,
            "score_type": score_type,
            "method": method,
            "major_name": major_name,
            "raw_value": str(value),
            "value": value,
        },
    )


class Phase4AnswerBehaviorTests(unittest.TestCase):
    def test_application_threshold_lookup_is_deterministic_and_validated(self) -> None:
        result = ask_chatbot(
            "Điểm sàn CNTT 2026?",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["trace"]["entities"]["score_query_type"],
            "application_threshold_lookup",
        )
        self.assertEqual(result["trace"]["deterministic_branch"], "application_threshold_lookup")
        self.assertEqual(result["trace"]["deterministic_validation"]["status"], "ok")
        self.assertIn("600", result["answer"])
        self.assertIn("15,00", result["answer"])
        self.assertEqual(result["trace"]["final_status"], "ok")

    def test_supplementary_lookup_supports_paraphrases_without_threshold_mixing(self) -> None:
        questions = (
            "Điểm nhận hồ sơ bổ sung CNTT?",
            "Điểm bổ sung CNTT bao nhiêu?",
            "Ngưỡng xét tuyển bổ sung CNTT?",
            "Xét bổ sung CNTT cần bao nhiêu điểm?",
        )
        for question in questions:
            with self.subTest(question=question):
                result = ask_chatbot(
                    question,
                    retriever=_retriever(),
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(result["status"], "ok")
                self.assertEqual(
                    result["trace"]["entities"]["score_query_type"],
                    "supplementary_threshold_lookup",
                )
                self.assertEqual(
                    result["trace"]["deterministic_branch"],
                    "supplementary_threshold_lookup",
                )
                self.assertIn("18.0", result["answer"])
                self.assertIn("15.0", result["answer"])
                self.assertNotIn("600", result["answer"])

    def test_major_specific_fact_overrides_global_only_for_its_method(self) -> None:
        evidence = build_evidence(
            [
                _score_document(
                    score_type="application_threshold",
                    method="thpt",
                    value=15,
                ),
                _score_document(
                    score_type="application_threshold",
                    method="dgnl",
                    value=600,
                ),
                _score_document(
                    score_type="application_threshold",
                    method="thpt",
                    value=18,
                    major_name="Công nghệ thông tin",
                ),
            ]
        )
        analysis = analyze_question("Điểm sàn Công nghệ thông tin 2026")
        selected = select_relevant_score_facts(analysis, evidence.score_facts)
        by_method = {str(fact["method"]): fact["raw_value"] for fact in selected}

        self.assertEqual(by_method, {"thpt": "18", "dgnl": "600"})

    def test_candidates_are_preserved_and_missing_method_is_clarified(self) -> None:
        first = ask_chatbot(
            "Em phân vân Công nghệ thông tin và Marketing",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )
        second = ask_chatbot(
            "Em được 18 điểm",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
            conversation_state=first["conversation_state"],
        )

        self.assertEqual(second["status"], "clarification")
        self.assertEqual(
            second["state"]["candidate_majors"],
            ["Marketing", "Công nghệ thông tin"],
        )
        self.assertIsNone(second["state"]["current_major"])
        self.assertIn("phương thức", second["answer"])

    def test_method_and_score_are_preserved_for_related_turns(self) -> None:
        state: dict[str, object] = {}
        first = ask_chatbot(
            "Em xét bằng ĐGNL",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
            conversation_state=state,
        )
        second = ask_chatbot(
            "720 điểm",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
            conversation_state=first["state"],
        )
        third = ask_chatbot(
            "CNTT thì sao?",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
            conversation_state=second["state"],
        )

        self.assertEqual(second["state"]["current_method"], "dgnl")
        self.assertEqual(second["state"]["student_scores"]["dgnl"], 720)
        self.assertEqual(third["trace"]["entities"]["admission_method"], "dgnl")
        self.assertEqual(third["trace"]["entities"]["student_scores"]["dgnl"], 720)
        self.assertIn("600", third["answer"])
        self.assertIn("không phải kết luận trúng tuyển", third["answer"])
        self.assertNotIn("chắc chắn đậu", third["answer"].casefold())

    def test_score_then_related_major_preserves_score_and_asks_for_method(self) -> None:
        first = ask_chatbot(
            "Em được 19 điểm",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
        )
        second = ask_chatbot(
            "Marketing thì sao?",
            retriever=_retriever(),
            llm=_NeverCalledLLM(),
            conversation_state=first["state"],
        )

        self.assertEqual(first["status"], "clarification")
        self.assertEqual(second["status"], "clarification")
        self.assertEqual(second["trace"]["entities"]["major_name"], "Marketing")
        self.assertEqual(second["state"]["student_scores"]["unspecified"], 19)
        self.assertIn("phương thức", second["answer"])

    def test_score_state_is_ignored_by_tuition_turn(self) -> None:
        first = ask_chatbot(
            "Em được 720 ĐGNL",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )

        class InvalidLocalLLM(LocalLLM):
            def generate(self, prompt: str) -> str:
                del prompt
                return "Câu trả lời không có trong bằng chứng."

        result = ask_chatbot(
            "À em hỏi học phí học kỳ 1 bao nhiêu?",
            retriever=_retriever(),
            llm=InvalidLocalLLM(),
            conversation_state=first["state"],
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["entities"]["student_scores"], {})
        self.assertIsNone(result["trace"]["entities"]["score_type"])
        self.assertIn("12.500.000", result["answer"])
        self.assertEqual(result["state"]["student_scores"]["dgnl"], 720)


if __name__ == "__main__":
    unittest.main()
