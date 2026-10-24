"""“Điểm nhận hồ sơ” là cách gọi ngưỡng điểm, không phải câu hỏi về giấy tờ hồ sơ."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot


THRESHOLD_ONLY = ("Mức điểm sàn (điểm nhận hồ sơ) là bao nhiêu?", "Ngưỡng nhận hồ sơ là bao nhiêu?")
TWO_ISSUES = "Điểm sàn bao nhiêu và hồ sơ cần giấy tờ gì?"


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("threshold answers must come from verified score rules")


class ThresholdIntakePhraseRuleTests(unittest.TestCase):
    def test_intake_phrase_is_one_threshold_issue(self) -> None:
        for question in THRESHOLD_ONLY:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
                self.assertNotIn("HOI_HO_SO", analysis.entities["issue_intents"])
                self.assertEqual(route_question(analysis).subplans, ())

    def test_real_documents_question_still_splits(self) -> None:
        analysis = analyze_question(TWO_ISSUES)
        self.assertEqual(analysis.intent, "MULTI_ISSUE")
        self.assertEqual(
            [plan.intent for plan in route_question(analysis).subplans], ["HOI_NGUONG_DAU_VAO", "HOI_HO_SO"]
        )

    def test_supplementary_intake_phrase_keeps_its_route(self) -> None:
        analysis = analyze_question("Điểm nhận hồ sơ bổ sung CNTT?")
        self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
        self.assertEqual(analysis.entities["score_query_type"], "supplementary_threshold_lookup")


class ThresholdIntakePhraseAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def test_full_flow_answers_only_the_threshold(self) -> None:
        for question in THRESHOLD_ONLY:
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())
                self.assertEqual(result["status"], "ok")
                answer = str(result["answer"])
                self.assertIn("15", answer)
                self.assertNotIn("giấy tờ", answer)
                self.assertNotIn("### Hồ sơ", answer)


if __name__ == "__main__":
    unittest.main()
