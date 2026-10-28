"""Câu hỏi về một khoản phí cụ thể trả đúng dòng trong bảng chi phí nhập học."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.rag_chain import ask_chatbot


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("fee items must come from the verified fee table")


class FeeItemAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _answer(self, question: str) -> str:
        result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "ok", question)
        return str(result["answer"])

    def test_learning_materials_fee_is_a_separate_item(self) -> None:
        answer = self._answer("Phí học liệu có thu riêng không?")
        self.assertIn("Tài khoản học liệu điện tử", answer)
        self.assertIn("250.000 đồng", answer)
        self.assertIn("khoản riêng", answer)
        for other in ("12.500.000", "1.250.000", "1.500.000", "Tiếng Anh"):
            self.assertNotIn(other, answer)

    def test_other_fee_questions_keep_their_own_item(self) -> None:
        for question, expected, foreign in (
            ("Học phí bao nhiêu?", "1.250.000 đồng/tín chỉ", "học liệu"),
            ("Phí nhập học bao nhiêu?", "1.500.000", "12.500.000"),
            ("Phí kiểm tra năng lực tiếng Anh là bao nhiêu?", "250.000", "12.500.000"),
        ):
            with self.subTest(question=question):
                answer = self._answer(question)
                self.assertIn(expected, answer)
                self.assertNotIn(foreign, answer)

    def test_english_fee_answer_names_the_english_test(self) -> None:
        answer = self._answer("Phí kiểm tra năng lực tiếng Anh là bao nhiêu?")
        self.assertIn("Tiếng Anh", answer)
        self.assertNotIn("học liệu", answer)


if __name__ == "__main__":
    unittest.main()
