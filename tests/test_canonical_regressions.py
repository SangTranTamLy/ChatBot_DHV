"""Regressions from the canonical 500-question run: facts present in data/processed must be answered."""

import unittest

from evaluation.run_evaluation import EvidenceEchoLLM
from scripts.evaluate_phase5 import setup_runtime
from src.chatbot.output_validator import _contains_numeric_literal
from src.chatbot.rag_chain import _ask_chatbot_core


class CanonicalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever, _ = setup_runtime()

    def ask(self, question: str) -> dict[str, object]:
        return _ask_chatbot_core(question, retriever=self.retriever, llm=EvidenceEchoLLM())

    def assertAnswers(self, question: str, *expected: str) -> None:
        result = self.ask(question)
        self.assertEqual(result["status"], "ok", question)
        for text in expected:
            self.assertIn(text, str(result["answer"]), question)

    def test_major_without_programs_is_stated_not_missing(self) -> None:
        self.assertAnswers("Ngành Trí tuệ nhân tạo tại DHV có những chuyên ngành nào?", "7480107", "chưa chia")
        self.assertAnswers("Ngành Luật và Luật kinh tế tại DHV có bao nhiêu chuyên ngành?", "7380101", "7380107")

    def test_general_admission_condition_reads_bulleted_law_rules(self) -> None:
        self.assertAnswers(
            "Muốn xét tuyển vào trường đại học Hùng Vương Tp.Hồ Chí Minh thì điều kiện cơ bản là gì?",
            "tốt nghiệp trung học phổ thông",
            "Học lực lớp 12 đạt loại Giỏi",
        )

    def test_score_reason_accepts_zero_decimal(self) -> None:
        self.assertAnswers("Điểm trúng tuyển ngành Tâm lý học DHV 2026 cao hơn các ngành khác vì sao?", "20,0", "15,0")
        self.assertTrue(_contains_numeric_literal("là 20,0 điểm", "20"))
        self.assertFalse(_contains_numeric_literal("1.500.000 đồng", "1.500"))

    def test_school_facts_are_not_replaced_by_overview_or_heading(self) -> None:
        self.assertAnswers("DHV được thành lập vào năm nào và có bao nhiêu tuổi vào năm 2026?", "14/08/1995")
        self.assertAnswers("Quỹ Vườn ươm Khởi nghiệp của trường được giới thiệu với quy mô ban đầu bao nhiêu?", "1 TRIỆU USD")
        self.assertAnswers("Ngày truyền thống hằng năm của Trường là ngày nào?", "9 tháng 3 âm lịch")

    def test_major_or_program_existence_uses_verified_catalog(self) -> None:
        self.assertAnswers("DHV có ngành Công nghệ thông tin không?", "Có.", "7480201")
        self.assertAnswers("DHV có chuyên ngành về IoT không?", "AI và IoT ứng dụng", "7480106")
        self.assertAnswers("DHV có đào tạo ngành về dữ liệu lớn (Big Data) không?", "Phân tích dữ liệu lớn")

    def test_official_enrollment_is_one_issue(self) -> None:
        self.assertAnswers(
            "Sau khi em hoàn tất hồ sơ và học phí, khi nào mới được xem là nhập học chính thức?",
            "xác nhận nhập học chính thức",
        )


if __name__ == "__main__":
    unittest.main()
