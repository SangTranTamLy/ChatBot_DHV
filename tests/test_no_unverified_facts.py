"""Answers must not state facts that the verified corpus does not contain."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.tuition_formatters import _evidence_semester_system_answer


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("these answers must not need generation")


class NoUnverifiedFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _ask(self, question: str) -> dict[str, object]:
        return ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())

    def test_faculty_answer_lists_only_units_named_in_evidence(self) -> None:
        for question in ("DHV có bao nhiêu khoa?", "Trường có những khoa nào?"):
            with self.subTest(question=question):
                result = self._ask(question)
                self.assertEqual(result["status"], "ok")
                answer = str(result["answer"])
                self.assertIn("Khoa Luật", answer)
                self.assertIn("chưa công bố tổng số khoa", answer)
                self.assertNotIn("5 Khoa", answer)
                self.assertNotIn("phụ trách đào tạo", answer)
                self.assertNotIn("**Khoa", answer)

    def test_major_count_has_no_invented_field_summary(self) -> None:
        answer = str(self._ask("DHV có bao nhiêu ngành?")["answer"])
        self.assertIn("20 ngành", answer)
        self.assertNotIn("lĩnh vực", answer)

    def test_semester_count_is_not_invented(self) -> None:
        result = self._ask("Một năm học có mấy học kỳ?")
        self.assertNotIn("3 học kỳ", str(result["answer"]))
        self.assertNotEqual(result["status"], "ok")

    def test_programme_length_and_credit_load_are_not_hard_coded(self) -> None:
        for question in ("Ngành Trí tuệ nhân tạo học mấy năm?", "Mỗi học kỳ đăng ký tối thiểu bao nhiêu tín chỉ?"):
            with self.subTest(question=question):
                self.assertIsNone(_evidence_semester_system_answer(analyze_question(question), None))


if __name__ == "__main__":
    unittest.main()
