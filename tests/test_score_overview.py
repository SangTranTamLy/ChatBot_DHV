"""Admission-score overviews, scholarship score criteria and per-major score comparisons."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question
from src.chatbot.rag_chain import ask_chatbot


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("score answers must come from verified score facts")


class ScoreRoutingTests(unittest.TestCase):
    def test_scholarship_score_questions_route_to_scholarships(self) -> None:
        for question in (
            "Điểm học bạ tối thiểu bao nhiêu để nhận học bổng tuyển sinh DHV?",
            "Sinh viên ngành AI tại DHV cần điểm Toán tối thiểu bao nhiêu để nhận học bổng Tiên phong?",
            "Tôi cần điểm ĐGNL ĐHQG-HCM bao nhiêu để nhận học bổng 60% học phí DHV?",
            "Học bổng tuyển sinh dựa trên điểm tổ hợp 3 môn thi DHV được quy định như thế nào?",
        ):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).intent, "HOI_HOC_BONG")

    def test_score_distribution_questions_route_to_admission_scores(self) -> None:
        for question in (
            "Mức điểm học bạ năm 2026 của DHV có giống nhau ở tất cả các ngành không?",
            "Điểm Đánh giá năng lực ĐHQG TP.HCM trong bảng trúng tuyển DHV năm 2026 được chia thành những mức nào?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "HOI_DIEM_TRUNG_TUYEN")
                self.assertEqual(analysis.entities["score_type"], "admission_score")

    def test_subject_combination_wording_is_not_a_distribution_question(self) -> None:
        question = "Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ?"
        self.assertNotEqual(analyze_question(question).intent, "HOI_DIEM_TRUNG_TUYEN")


class ScoreAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _answer(self, question: str) -> str:
        result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "ok", msg=result.get("answer"))
        return str(result["answer"])

    def test_overview_shows_range_usual_value_and_exceptions(self) -> None:
        answer = self._answer("Điểm chuẩn đợt 1 của DHV năm 2026 khoảng bao nhiêu ạ?")
        self.assertIn("Thi tốt nghiệp THPT: 15–20 điểm", answer)
        self.assertIn("Tâm lý học", answer)
        self.assertIn("ĐGNL: 600–762 điểm", answer)

    def test_overview_respects_requested_method_and_condition_marker(self) -> None:
        answer = self._answer("Mức điểm học bạ năm 2026 của DHV có giống nhau ở tất cả các ngành không?")
        self.assertIn("Học bạ: 18–22,5 điểm", answer)
        self.assertNotIn("ĐGNL", answer)
        self.assertEqual(answer.count("Luật,"), 0, msg="Luật must not be listed twice")

    def test_named_scholarship_policy_answer(self) -> None:
        answer = self._answer("Sinh viên ngành AI tại DHV cần điểm Toán tối thiểu bao nhiêu để nhận học bổng Tiên phong?")
        self.assertIn("Học bổng Ngành Tiên phong", answer)
        self.assertNotIn("Đôi bạn cùng tiến", answer)

    def test_personal_score_is_compared_with_the_named_major(self) -> None:
        answer = self._answer("Em thi ĐGNL được 650 điểm có đăng ký được ngành Tâm lý học không ạ?")
        self.assertIn("ngưỡng nhận hồ sơ 600", answer)
        self.assertIn("762", answer)
        self.assertIn("thấp hơn mức này", answer)

    def test_every_named_major_is_compared_without_a_method_threshold(self) -> None:
        answer = self._answer("Học bạ em được 21 điểm thì có đủ điểm trúng tuyển ngành Luật hoặc Luật kinh tế ở DHV không ạ?")
        self.assertIn("ngành Luật theo học bạ", answer)
        self.assertIn("ngành Luật kinh tế theo học bạ", answer)
        multi = self._answer("18 điểm học bạ có đăng ký được ngành Công nghệ Thông tin, Marketing hay Ngôn ngữ Anh không ạ?")
        for major in ("Công nghệ thông tin", "Marketing", "Ngôn ngữ Anh"):
            self.assertIn(major, multi)


if __name__ == "__main__":
    unittest.main()
