"""Hồi quy cho đợt rà soát: rò rỉ prompt, học bổng theo danh hiệu, định tuyến ý định dự phòng."""

from __future__ import annotations

import unittest

from src.chatbot.output_validator import has_prompt_leak, sanitize_answer
from src.chatbot.query_analysis import analyze_question


class PromptLeakTests(unittest.TestCase):
    def test_context_reference_is_detected_and_stripped(self) -> None:
        self.assertTrue(has_prompt_leak("Theo thông tin từ CONTEXT, học phí không tăng."))
        cleaned = sanitize_answer("Theo thông tin từ CONTEXT, học phí không tăng.")
        self.assertNotIn("CONTEXT", cleaned)

    def test_retry_instruction_echo_is_detected_with_or_without_diacritics(self) -> None:
        leaked_prefixes = (
            "BẢN ĐÁP ÁN TRƯỚC ĐÃ BỎ SÓT NỘI DUNG BẮT BUỘC. "
            "Ở lần trả lời này, hãy bao gồm đầy đủ các cụm/tiêu đề sau.",
            "Ban dap an truoc da bo sot noi dung bat buoc; khong bo bat ky muc nao.",
            "Bản đáp án mới: Tổng các khoản cơ bản học kỳ I là 14.250.000 đồng.",
            "BẢN NHÁP CẦN KIỂM TRA: Tổng các khoản cơ bản học kỳ I là 14.250.000 đồng.",
            "CÂU TRẢ LỜI MỚI: Học phí HKI là 12.500.000 đồng.",
        )
        for answer in leaked_prefixes:
            with self.subTest(answer=answer):
                self.assertTrue(has_prompt_leak(answer))


class FallbackIntentTests(unittest.TestCase):
    def test_program_existence_is_not_out_of_scope(self) -> None:
        for question in ("DHV có ngành An ninh mạng không?", "DHV có đào tạo ngành Du lịch không?"):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).intent, "HOI_NGANH")

    def test_hsca_routes_to_admission_methods(self) -> None:
        self.assertEqual(
            analyze_question("Em có điểm H-SCA thì DHV có nhận không ạ?").intent,
            "HOI_PHUONG_THUC_XET_TUYEN",
        )

    def test_hoc_ba_which_grades_is_a_method_rule(self) -> None:
        self.assertEqual(
            analyze_question("Xét học bạ năm 2026 lấy điểm của lớp nào vậy ạ?").intent,
            "HOI_PHUONG_THUC_XET_TUYEN",
        )

    def test_unrelated_question_stays_out_of_scope(self) -> None:
        self.assertEqual(analyze_question("hôm nay thời tiết thế nào").intent, "OUT_OF_SCOPE")


if __name__ == "__main__":
    unittest.main()
