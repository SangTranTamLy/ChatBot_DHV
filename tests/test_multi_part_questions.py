"""Câu hỏi nhiều ý: sửa lỗi gõ, tách vế theo câu gốc và trả lời đủ đếm + liệt kê."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.query_semantics import correct_domain_typos
from src.chatbot.scholarship_formatters import _evidence_scholarship_catalog_answer


SCREENSHOT_QUESTION = (
    "trường có bao nhiêu phương thức xét tuyển hãy nêu những Phước thực xét tuyển và dieefu kiện"
)


class DomainTypoTests(unittest.TestCase):
    def test_common_admission_typos_are_corrected(self) -> None:
        cases = {
            SCREENSHOT_QUESTION: (
                "trường có bao nhiêu phương thức xét tuyển hãy nêu những "
                "Phương thức xét tuyển và điều kiện"
            ),
            "dieuf kieenj trúng tuyển": "điều kiện trúng tuyển",
            "phương thuốc xét tuyển": "phương thức xét tuyển",
            "Phuong thuwc nào?": "Phương thức nào?",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(correct_domain_typos(question), expected)

    def test_valid_words_are_left_unchanged(self) -> None:
        for question in (
            "dieu kien xet tuyen la gi",
            "hỗ trợ hồ sơ",
            "Bình Phước có học bổng không",
            "học bằng tiếng anh",
            "xét duyệt hồ sơ",
            "Điểm chuẩn ngành Công nghệ thông tin",
        ):
            with self.subTest(question=question):
                self.assertEqual(correct_domain_typos(question), question)


class MultiPartRoutingTests(unittest.TestCase):
    def test_misspelled_count_list_conditions_question_is_list_and_count(self) -> None:
        analysis = analyze_question(SCREENSHOT_QUESTION)
        self.assertEqual(analysis.entities.get("query_mode"), "LIST_AND_COUNT")
        self.assertIn("dieu kien", analysis.normalized_question)

    def test_name_them_marks_a_list_request(self) -> None:
        for question in ("có bao nhiêu học bổng, kể tên", "có bao nhiêu ngành, kể tên giúp mình"):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).entities.get("query_mode"), "LIST_AND_COUNT")

    def test_subplans_keep_each_original_clause(self) -> None:
        plan = route_question(analyze_question("trường có bao nhiêu ngành và hạn nộp hồ sơ khi nào"))
        self.assertEqual(
            [subplan.intent for subplan in plan.subplans],
            ["DANH_SACH_NGANH", "HOI_LICH_TUYEN_SINH"],
        )
        self.assertIn("hạn nộp hồ sơ khi nào", plan.subplans[1].retrieval_query)


class ScholarshipCountTests(unittest.TestCase):
    def setUp(self) -> None:
        metadata = {
            "record_type": "page_text",
            "category": "hoc_bong",
            "school_code": "DHV",
            "status": "verified",
            "year": 2026,
            "source_url": "https://dhv.edu.vn/hoc-bong",
        }
        self.evidence = SimpleNamespace(chunks=[SimpleNamespace(
            metadata=metadata,
            text="1.1. Học bổng Tài năng\n1.2. Học bổng Đôi bạn cùng tiến",
        )])

    def test_count_question_gets_a_count(self) -> None:
        answer = _evidence_scholarship_catalog_answer(analyze_question("có mấy học bổng"), self.evidence)
        self.assertEqual(answer, "Tài liệu tuyển sinh DHV 2026 có 2 đề mục/chính sách học bổng được nêu rõ.")

    def test_count_and_list_question_gets_both(self) -> None:
        answer = _evidence_scholarship_catalog_answer(
            analyze_question("có bao nhiêu học bổng, kể tên"), self.evidence
        ) or ""
        self.assertIn("có 2 đề mục", answer)
        self.assertIn("2. Học bổng Đôi bạn cùng tiến", answer)


if __name__ == "__main__":
    unittest.main()
