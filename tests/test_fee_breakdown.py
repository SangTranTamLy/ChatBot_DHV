"""HKI fee-table reasoning: totals, other fees, credits, scholarship-adjusted amounts, payment."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question
from src.chatbot.rag_chain import ask_chatbot


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("fee answers must come from the verified fee table")


class FeeQuestionRoutingTests(unittest.TestCase):
    def test_fee_questions_mentioning_enrollment_or_scholarship_stay_single_issue(self) -> None:
        for question in (
            "Ngoài tiền học phí của học kỳ I, lúc nhập học em còn phải đóng thêm những khoản nào ạ?",
            "Khoản 14,5 triệu khi nhập học có phải toàn bộ đều là học phí không?",
            "Nếu được học bổng 70% học phí chuẩn HK1, tôi phải đóng bao nhiêu?",
            "Em thấy thông tin cũ có số tài khoản ngân hàng để đóng học phí, năm 2026 em chuyển vào số đó luôn được không?",
            "Phí nhập học bao nhiêu?",
        ):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).intent, "HOI_HOC_PHI")

    def test_genuine_two_topic_question_is_still_split(self) -> None:
        self.assertEqual(analyze_question("Hồ sơ nhập học và học phí như thế nào?").intent, "MULTI_ISSUE")


class FeeAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _answer(self, question: str) -> str:
        result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "ok", msg=result.get("answer"))
        return str(result["answer"])

    def test_semester_totals_with_and_without_english_test(self) -> None:
        with_test = self._answer("Nếu có kiểm tra năng lực tiếng Anh thì số tiền học kỳ I theo bảng sẽ thành bao nhiêu?")
        self.assertIn("14.500.000", with_test)
        without = self._answer("Nếu em không thuộc diện kiểm tra tiếng Anh thì tổng các khoản học kỳ I trong bảng là bao nhiêu?")
        self.assertIn("14.250.000", without)
        self.assertNotIn("tổng cộng 14.500.000", without)

    def test_other_fees_and_containment(self) -> None:
        listing = self._answer("Ngoài học phí, khi nhập học DHV tôi còn phải đóng những khoản gì?")
        for amount in ("12.500.000", "1.500.000", "250.000"):
            self.assertIn(amount, listing)
        self.assertIn("học liệu", listing)
        contained = self._answer("Khoản phí nhập học 1,5 triệu đồng có nằm trong 12,5 triệu đồng học phí học kỳ I không ạ?")
        self.assertTrue(contained.startswith("Không."))

    def test_credit_arithmetic(self) -> None:
        self.assertIn("12.500.000", self._answer("Em đăng ký 10 tín chỉ thì có thể ước tính tiền học khoảng bao nhiêu?"))
        self.assertIn("10 tín chỉ", self._answer("Học phí 12,5 triệu của học kỳ I tương ứng với bao nhiêu tín chỉ?"))

    def test_scholarship_adjusted_amount_payable(self) -> None:
        answer = self._answer("Nếu được học bổng 70% học phí chuẩn HK1, tôi phải đóng bao nhiêu?")
        self.assertIn("8.750.000", answer)
        self.assertIn("3.750.000", answer)

    def test_published_fees_are_before_scholarships(self) -> None:
        before = self._answer("Mức học phí 1,25 triệu một tín chỉ có phải là con số đã trừ học bổng chưa?")
        self.assertTrue(before.startswith("Chưa."))
        self.assertIn("chưa áp dụng học bổng", before)
        unchanged = self._answer("Học bổng có làm thay đổi mức học phí 1.250.000 đồng mỗi tín chỉ không ạ?")
        self.assertTrue(unchanged.startswith("Không."))

    def test_payment_channel_without_invented_bank_account(self) -> None:
        answer = self._answer(
            "Em thấy thông tin cũ có số tài khoản ngân hàng để đóng học phí, năm 2026 em chuyển vào số đó luôn được không?"
        )
        self.assertIn("UniZone", answer)
        self.assertIn("chưa nêu số tài khoản ngân hàng", answer)
        self.assertNotIn("Vietcom", answer)


if __name__ == "__main__":
    unittest.main()
