"""Task I regressions for the deterministic system router and bounded state."""

from __future__ import annotations

import unittest

from src.chatbot.query_analysis import (
    ConversationState,
    SYSTEM_INTENTS,
    analyze_question,
    route_question,
    update_conversation_state,
)
from src.chatbot.rag_chain import ask_chatbot


class _NeverCalledRetriever:
    def retrieve(self, *_: object, **__: object) -> list[object]:
        raise AssertionError("system turns must not retrieve documents")

    def retrieve_with_audit(self, *_: object, **__: object) -> object:
        raise AssertionError("system turns must not retrieve documents")


class _NeverCalledLLM:
    def generate(self, *_: object, **__: object) -> str:
        raise AssertionError("system turns must not call the LLM")


class TaskISystemRouterTests(unittest.TestCase):
    def test_greeting_identity_and_scope_are_deterministic(self) -> None:
        cases = (
            ("hello", "GREETING"),
            ("Bạn tên gì?", "SYSTEM_IDENTITY"),
            ("Bạn có phải chatbot chính thức không?", "SYSTEM_IDENTITY"),
            ("Bạn có phải toàn bộ thông tin trường không?", "SYSTEM_SCOPE"),
            ("Bạn hỗ trợ được gì?", "SYSTEM_SCOPE"),
        )
        for question, expected_intent in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                result = ask_chatbot(
                    question,
                    retriever=_NeverCalledRetriever(),
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(analysis.intent, expected_intent)
                self.assertIn(expected_intent, SYSTEM_INTENTS)
                self.assertEqual(analysis.intent_source, "deterministic_router")
                self.assertEqual(plan.categories, ())
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["sources"], [])

    def test_identity_does_not_claim_official_status(self) -> None:
        result = ask_chatbot(
            "Bạn có phải chatbot chính thức của trường không?",
            retriever=_NeverCalledRetriever(),
            llm=_NeverCalledLLM(),
        )
        answer = str(result["answer"]).casefold()
        self.assertIn("trợ lý ai", answer)
        self.assertIn("đồ án học tập/nghiên cứu", answer)
        self.assertIn("không phải chatbot", answer)
        self.assertIn("chính thức", answer)

    def test_out_of_scope_stays_outside_retrieval(self) -> None:
        result = ask_chatbot(
            "Thời tiết hôm nay?",
            retriever=_NeverCalledRetriever(),
            llm=_NeverCalledLLM(),
        )
        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["trace"]["intent"], "OUT_OF_SCOPE")

    def test_school_info_has_its_own_retrieval_category(self) -> None:
        analysis = analyze_question("DHV là trường gì?")
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "SCHOOL_INFO")
        self.assertEqual(plan.categories, ("thong_tin_truong",))
        self.assertEqual(plan.metadata_filter["categories"], ["thong_tin_truong"])

    def test_major_followup_can_switch_context_without_stale_program(self) -> None:
        first_analysis = analyze_question("Tôi đang tìm hiểu CNTT")
        first_state = update_conversation_state({}, first_analysis)
        self.assertEqual(first_state.current_major, "Công nghệ thông tin")

        second_analysis = analyze_question("Đổi sang Kỹ thuật máy tính", first_state)
        second_state = update_conversation_state(first_state, second_analysis)
        self.assertEqual(second_analysis.entities["major_name"], "Kỹ thuật máy tính")
        self.assertEqual(second_state.current_major, "Kỹ thuật máy tính")
        self.assertIsNone(second_state.current_program)
        self.assertEqual(second_state.candidate_majors, ("Kỹ thuật máy tính",))

    def test_multi_issue_is_decomposed_into_independent_subplans(self) -> None:
        question = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "MULTI_ISSUE")
        self.assertEqual(
            [subplan.intent for subplan in plan.subplans],
            ["HOI_HOC_PHI", "HOI_HOC_BONG", "DANH_SACH_CHUONG_TRINH"],
        )
        self.assertEqual(
            [subplan.categories for subplan in plan.subplans],
            [("hoc_phi",), ("hoc_bong",), ("nganh_dao_tao",)],
        )
        self.assertEqual(plan.categories, ("hoc_phi", "hoc_bong", "nganh_dao_tao"))


if __name__ == "__main__":
    unittest.main()
