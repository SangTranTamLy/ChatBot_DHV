"""Regression tests for Task L answer planning and natural-response boundaries."""

from __future__ import annotations

import unittest

from src.chatbot.answer_planner import ANSWER_MODES, AnswerPlanner, plan_answer
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from src.prompts.rag_prompt import build_rag_prompt

from tests.test_task_f import EchoEvidenceLLM, RecordingRetriever, _fixture_chunks, _retriever


class TaskLPlannerTests(unittest.TestCase):
    def test_planner_exposes_all_required_modes(self) -> None:
        self.assertEqual(
            ANSWER_MODES,
            (
                "DIRECT_SHORT",
                "EXPLANATION",
                "OVERVIEW",
                "COMPARISON",
                "TABLE",
                "STEP_BY_STEP",
                "RECOMMENDATION",
                "CLARIFICATION",
                "NO_DATA",
                "OUT_OF_SCOPE",
            ),
        )

    def test_modes_follow_question_shape_without_major_specific_hard_coding(self) -> None:
        cases = (
            ("Tổng quan về ngành Công nghệ thông tin?", "OVERVIEW"),
            ("So sánh Công nghệ thông tin với Kỹ thuật máy tính", "COMPARISON"),
            ("CNTT có bao nhiêu chương trình đào tạo?", "DIRECT_SHORT"),
            ("Hồ sơ xét tuyển cần những gì?", "STEP_BY_STEP"),
            ("Tôi thích edit video nên chọn ngành nào?", "RECOMMENDATION"),
            ("Công nghệ thông tin lấy bao nhiêu điểm?", "CLARIFICATION"),
            ("Thời tiết hôm nay?", "OUT_OF_SCOPE"),
        )
        planner = AnswerPlanner()
        for question, expected in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(planner.plan(analysis).mode, expected)

    def test_no_data_status_is_a_boundary_mode(self) -> None:
        analysis = analyze_question("Học bổng DHV 2026")
        plan = plan_answer(analysis, status="no_data")
        self.assertEqual(plan.mode, "NO_DATA")
        self.assertFalse(plan.related_questions)
        self.assertFalse(plan.evidence_required)

    def test_prompt_contains_plan_but_keeps_facts_in_evidence_blocks(self) -> None:
        analysis = analyze_question("Tổng quan về ngành Công nghệ thông tin?")
        plan = plan_answer(analysis)
        prompt = build_rag_prompt(
            analysis.question,
            "Công nghệ thông tin có các chương trình đã được kiểm chứng.",
            intent=analysis.intent,
            entities=analysis.entities,
            answer_plan=plan,
        )
        self.assertIn("<ANSWER_PLAN>", prompt)
        self.assertIn('"mode": "OVERVIEW"', prompt)
        self.assertIn("Chỉ dùng facts/evidence bên dưới", prompt)
        self.assertIn("<CONTEXT>", prompt)
        self.assertIn("Không tạo, đoán hoặc chép URL", prompt)

    def test_runtime_trace_records_plan_and_related_questions(self) -> None:
        result = ask_chatbot(
            "Tổng quan về ngành Công nghệ thông tin?",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer_plan"]["mode"], "OVERVIEW")
        self.assertEqual(result["trace"]["answer_plan"]["mode"], "OVERVIEW")
        related = result["related_questions"]
        self.assertGreaterEqual(len(related), 2)
        self.assertLessEqual(len(related), 3)
        self.assertTrue(all("http" not in question for question in related))

    def test_multi_issue_has_outer_and_subplan_contracts(self) -> None:
        retriever = RecordingRetriever(_fixture_chunks())
        result = ask_chatbot(
            "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?",
            retriever=retriever,
            llm=EchoEvidenceLLM(),
        )
        self.assertEqual(result["answer_plan"]["mode"], "EXPLANATION")
        subplans = result["trace"]["multi_issue"]["answer_plans"]
        self.assertEqual(len(subplans), 3)
        self.assertEqual(
            [subplan["intent"] for subplan in subplans],
            ["HOI_HOC_PHI", "HOI_HOC_BONG", "DANH_SACH_CHUONG_TRINH"],
        )
        self.assertGreaterEqual(len(result["related_questions"]), 2)

    def test_llm_receives_the_selected_mode_for_comparison(self) -> None:
        class PromptRecordingLLM:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                # A grounded sentence is enough to exercise the validator.
                return "Công nghệ thông tin và Kỹ thuật máy tính là hai lựa chọn trong dữ liệu DHV."

        llm = PromptRecordingLLM()
        result = ask_chatbot(
            "So sánh Công nghệ thông tin với Kỹ thuật máy tính",
            retriever=_retriever(),
            llm=llm,
        )
        self.assertEqual(result["answer_plan"]["mode"], "COMPARISON")
        self.assertTrue(llm.prompts)
        self.assertIn('"mode": "COMPARISON"', llm.prompts[0])
        self.assertIn("đặt các lựa chọn cạnh nhau", llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
