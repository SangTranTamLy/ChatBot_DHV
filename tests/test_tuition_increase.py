"""Câu hỏi "học phí có tăng không" phải nhận diện được mọi cách diễn đạt."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.chatbot.output_validator import _has_required_labeled_amount
from src.chatbot.query_analysis import analyze_question
from src.chatbot.query_semantics import is_tuition_increase_question
from src.chatbot.tuition_formatters import _evidence_semester_system_answer


COMMITMENT_LINE = (
    "Học phí được tính 1.250.000 đồng/tín chỉ và cam kết không tăng trong suốt khóa học."
)
PAYMENT_LINE = (
    "Tân sinh viên hoàn tất thủ tục và thanh toán học phí trên hệ thống UniZone bằng tài khoản "
    "được Nhà trường cấp."
)


def _evidence(*lines: str) -> SimpleNamespace:
    return SimpleNamespace(chunks=[SimpleNamespace(text="\n".join(lines), metadata={})])


INCREASE_QUESTIONS = (
    "học phí có tăng hay k",
    "học phí có tăng hay không",
    "học phí có tăng không",
    "Học phí 4 năm có tăng không?",
    "học phí có bị tăng qua các năm không",
    "học phí có ổn định không",
    "học phí có giữ nguyên không",
)


class TuitionIncreaseQuestionTests(unittest.TestCase):
    def test_increase_phrasings_get_commitment_answer(self) -> None:
        for question in INCREASE_QUESTIONS:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "HOI_HOC_PHI")
                answer = _evidence_semester_system_answer(analysis, _evidence(COMMITMENT_LINE)) or ""
                self.assertIn("không tăng trong suốt khóa học", answer)

    def test_commitment_is_never_invented_without_evidence(self) -> None:
        analysis = analyze_question("học phí có tăng không")
        self.assertIsNone(_evidence_semester_system_answer(analysis, _evidence("Học phí HKI: 12.500.000 đồng")))

    def test_payment_channel_comes_from_evidence_and_no_bank_account_is_made_up(self) -> None:
        analysis = analyze_question("Chuyển khoản học phí vào số tài khoản ngân hàng nào?")
        answer = _evidence_semester_system_answer(analysis, _evidence(PAYMENT_LINE)) or ""
        self.assertIn("UniZone", answer)
        self.assertIn("chưa nêu số tài khoản ngân hàng", answer)
        self.assertNotRegex(answer, r"\d{2}\.\d{2}\.\d{2}")
        self.assertIsNone(_evidence_semester_system_answer(analysis, _evidence("Học phí HKI: 12.500.000 đồng")))

    def test_plain_tuition_and_floor_questions_are_not_increase_questions(self) -> None:
        for question in ("học phí bao nhiêu", "học phí HKI bao nhiêu", "học phí đóng ở tầng mấy"):
            with self.subTest(question=question):
                self.assertFalse(is_tuition_increase_question(question))

    def test_validator_does_not_demand_tuition_amount_for_increase_questions(self) -> None:
        evidence = SimpleNamespace(
            chunks=[SimpleNamespace(text="Học phí HKI (10 tín chỉ): 12.500.000 đồng")]
        )
        commitment = COMMITMENT_LINE
        for question in INCREASE_QUESTIONS:
            with self.subTest(question=question):
                self.assertTrue(_has_required_labeled_amount(commitment, evidence, question))
        self.assertFalse(_has_required_labeled_amount(commitment, evidence, "học phí bao nhiêu"))


if __name__ == "__main__":
    unittest.main()
