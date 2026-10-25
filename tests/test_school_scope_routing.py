"""DHV school-life questions: answer from school-wide documents or admit missing data."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.output_validator import FALLBACK_ANSWER, OUT_OF_SCOPE_ANSWER
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.scope_guard import has_foreign_domain_signal


MAJOR_INTERNSHIP = "Sinh viên ngành CNTT DHV có được thực tập tại doanh nghiệp không?"
LAW_INTERNSHIP = (
    "Sinh viên ngành Luật kinh tế có cơ hội kiến tập hoặc thực tập tại doanh nghiệp "
    "và văn phòng luật không?"
)
LAW_PARTNERS = "Khoa Luật DHV hợp tác với những đơn vị nào?"
DORMITORY = "DHV có ký túc xá không?"
CAMPUS_EVENT = "UniHackfest Unitour × DHV năm 2026 diễn ra vào ngày nào?"
WEATHER = "Thời tiết hôm nay thế nào?"


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("this answer must not need generation")


class _RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Sinh viên DHV được tiếp cận môi trường doanh nghiệp ngay từ năm thứ nhất."


class SchoolWideRoutingTests(unittest.TestCase):
    def test_named_major_does_not_block_school_wide_internship_facts(self) -> None:
        for question in (MAJOR_INTERNSHIP, LAW_INTERNSHIP):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "SCHOOL_INFO")
                self.assertEqual(plan.entity_filters, {})
                self.assertIn("moi_truong_hoc_tap_va_co_hoi_nghe_nghiep", plan.data_roles)
                self.assertIn("hop_tac_quoc_te_va_doanh_nghiep", plan.data_roles)

    def test_foreign_domain_signal_is_narrow(self) -> None:
        self.assertTrue(has_foreign_domain_signal(WEATHER))
        self.assertFalse(has_foreign_domain_signal(DORMITORY))
        self.assertFalse(has_foreign_domain_signal(MAJOR_INTERNSHIP))


class SchoolWideAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def test_internship_question_reaches_generation_with_school_documents(self) -> None:
        llm = _RecordingLLM()
        result = ask_chatbot(MAJOR_INTERNSHIP, retriever=self.retriever, llm=llm)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(llm.prompts)
        # "sinh viên" must not be parsed as an institute ("viện") lookup.
        self.assertNotEqual(result["trace"].get("evidence_boundary"), "named_school_unit_relation_missing")
        self.assertIn("năm thứ nhất", llm.prompts[0])

    def test_named_faculty_partner_types_are_accepted_as_evidence(self) -> None:
        llm = _RecordingLLM()
        result = ask_chatbot(LAW_PARTNERS, retriever=self.retriever, llm=llm)
        self.assertNotEqual(result["trace"].get("evidence_boundary"), "requested_school_info_detail_missing")
        self.assertEqual(result["status"], "ok")

    def test_unsupported_dhv_topics_are_missing_data_not_out_of_scope(self) -> None:
        for question in (DORMITORY, CAMPUS_EVENT):
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())
                self.assertEqual(result["status"], "no_data")
                self.assertEqual(result["answer"], FALLBACK_ANSWER)
                self.assertEqual(result["scope_reason"], "related_no_data")

    def test_foreign_domain_stays_out_of_scope(self) -> None:
        result = ask_chatbot(WEATHER, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["answer"], OUT_OF_SCOPE_ANSWER)


if __name__ == "__main__":
    unittest.main()
