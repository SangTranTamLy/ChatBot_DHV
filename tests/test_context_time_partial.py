"""Conversation focus, date validity and natural partial replies."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from src.chatbot.answer_cache import is_cacheable
from src.chatbot.query_analysis import analyze_question, ConversationState
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import validate_model_answer
from src.chatbot.year_semantics import current_admission_window_answer
from src.prompts.rag_prompt import build_rag_prompt, _response_examples
from tests.test_task_f import _retriever
from tests.test_runtime_contact import ContactRetriever


class NeverGenerate:
    def generate(self, prompt):
        raise AssertionError("These facts must not require generation")


def window(text, category="xet_tuyen_bo_sung"):
    return SimpleNamespace(chunks=(SimpleNamespace(text=text, metadata={"category": category}),),
                           sources=({"title": "Thông báo DHV", "url": "https://dhv.edu.vn/notice"},))


class ContextTimePartialTests(TestCase):
    def test_enrollment_followups_keep_the_topic_then_release_it(self):
        state = None
        for question, markers in (
            ("Hồ sơ nhập học cần những gì?", ("Học bạ",)),
            ("Cần mang gì?", ("Học bạ", "Căn cước")),
            ("Nộp ở đâu?", ("194 Lê Đức Thọ", "37 Kinh Dương Vương")),
            ("Chủ nhật được không?", ("Chủ nhật", "06:00")),
        ):
            with self.subTest(question=question):
                result = ask_chatbot(question, conversation_state=state, retriever=_retriever(), llm=NeverGenerate())
                self.assertEqual(result["status"], "ok")
                for marker in markers:
                    self.assertIn(marker, result["answer"])
                state = result["conversation_state"]
        new_topic = analyze_question("Trường có những cơ sở nào?", state)
        self.assertEqual(new_topic.intent, "HOI_CO_SO_LIEN_HE")
        self.assertNotIn("contextual_question", new_topic.entities)

    def test_no_enrollment_topic_is_invented_after_other_subjects(self):
        for previous in (None, "HOI_HOC_PHI", "OUT_OF_SCOPE", "GREETING"):
            analysis = analyze_question("Chủ nhật được không?", ConversationState(previous_intent=previous))
            self.assertNotIn("contextual_question", analysis.entities)
        external = ConversationState(previous_intent="HOI_NHAP_HOC", current_school="OTHER_SCHOOL")
        self.assertNotIn("contextual_question", analyze_question("Nộp ở đâu?", external).entities)
        switched = analyze_question("Còn DHV học phí bao nhiêu?", ConversationState(
            previous_intent="HOI_PHUONG_THUC_XET_TUYEN", current_school="OTHER_SCHOOL"))
        self.assertEqual(switched.intent, "HOI_HOC_PHI")

    def test_expired_current_application_is_not_advertised_as_open(self):
        evidence = window("Thời gian nhận hồ sơ đến hết ngày 21/8/2026.")
        result = current_admission_window_answer("Bây giờ còn nộp hồ sơ xét tuyển bổ sung được không?", evidence,
                                                today=date(2026, 10, 21))
        self.assertEqual(result["status"], "ok")
        self.assertIn("đã hết hạn ngày 21/08/2026", result["answer"])
        self.assertIn("chưa có thông tin về đợt mới", result["answer"])
        self.assertFalse(is_cacheable(result))

    def test_known_range_before_during_and_after(self):
        evidence = window("DHV tiếp nhận nhập học 06:00 – 18:00 Từ 11/08/2026 đến 10/09/2026", "ho_so")
        for today, expected in ((date(2026, 8, 10), "chưa đến"),
                                (date(2026, 8, 11), "vẫn trong"),
                                (date(2026, 9, 11), "đã hết hạn")):
            with self.subTest(today=today):
                result = current_admission_window_answer("Hiện tại còn nhận hồ sơ nhập học không?", evidence, today=today)
                self.assertIn(expected, result["answer"])

    def test_missing_conflicting_or_unrelated_dates_do_not_prove_open(self):
        for evidence in (
            window("Đăng ký xét tuyển bổ sung trực tuyến."),
            window("Thời gian nhận hồ sơ đến hết ngày 21/8/2026. Hạn nhận hồ sơ đến 22/8/2026."),
            window("Học bổng dành cho nhóm bạn đến hết ngày 31/07/2026."),
        ):
            with self.subTest(text=evidence.chunks[0].text):
                result = current_admission_window_answer("Bây giờ còn nộp hồ sơ bổ sung không?", evidence,
                                                        today=date(2026, 8, 15))
                self.assertEqual(result["status"], "no_data")
                self.assertEqual(result["sources"], [])

    def test_historical_question_and_tuition_do_not_trigger_date_gate(self):
        evidence = window("Thời gian nhận hồ sơ đến hết ngày 21/8/2026.")
        for question in ("Hạn xét tuyển bổ sung năm 2026 là ngày nào?", "Đợt bổ sung năm 2026 hết hạn khi nào?", "Học phí hiện tại bao nhiêu?"):
            self.assertIsNone(current_admission_window_answer(question, evidence))

    def test_deadline_day_does_not_assume_the_cutoff_hour(self):
        evidence = window("Thời gian nhận hồ sơ đến hết ngày 21/8/2026.")
        result = current_admission_window_answer("Bây giờ còn nộp hồ sơ bổ sung không?", evidence,
                                                today=date(2026, 8, 21))
        self.assertIn("kiểm tra giờ chốt", result["answer"])

    def test_expired_reply_uses_the_real_pipeline_without_generation(self):
        with patch("src.chatbot.year_semantics.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 21, tzinfo=timezone.utc)
            result = ask_chatbot("Bây giờ còn nộp hồ sơ xét tuyển bổ sung được không?",
                                 retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertIn("đã hết hạn", result["answer"])
        self.assertTrue(result["sources"])

    def test_current_deadline_in_multi_issue_is_not_cached(self):
        with patch("src.chatbot.year_semantics.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 21, tzinfo=timezone.utc)
            result = ask_chatbot("Bây giờ còn nộp hồ sơ xét tuyển bổ sung được không và học phí HKI bao nhiêu?",
                                 retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertIn("đã hết hạn", result["answer"])
        self.assertIn("12.500.000", result["answer"])
        self.assertTrue(result["temporal_checked"])
        self.assertFalse(is_cacheable(result))

    def test_partial_reply_names_missing_topic_in_plain_language(self):
        result = ask_chatbot("Trường có những cơ sở nào và học phí bao nhiêu?",
                             retriever=ContactRetriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["partial"])
        self.assertIn("736 Nguyễn Trãi", result["answer"])
        self.assertIn("Mình chưa có thông tin chính xác về mức học phí", result["answer"])
        for phrase in ("đã xác minh", "được kiểm chứng", "theo tài liệu", "đang tra"):
            self.assertNotIn(phrase, result["answer"])
        self.assertEqual(result["trace"]["multi_issue"]["issues"][1]["sources"], [])

    def test_style_examples_are_bounded_and_not_a_fact_source(self):
        self.assertGreaterEqual(len(_response_examples()), 6)
        prompt = build_rag_prompt("Học phí?", "Chưa có học phí.", intent="HOI_HOC_PHI")
        self.assertIn("KHÔNG phải nguồn thông tin", prompt)
        self.assertIn("Không chép số liệu", prompt)
        self.assertIn("<STYLE_EXAMPLES>", prompt)
        evidence = build_evidence([])
        result = validate_model_answer("Học phí là 12.500.000 đồng.", evidence,
                                       question="Học phí?", analysis=analyze_question("Học phí?"))
        self.assertEqual(result["status"], "no_data")

    def test_natural_uncertainty_is_not_marked_as_a_complete_answer(self):
        result = validate_model_answer("Mình chưa có thông tin chính xác về mức phí này.",
                                       build_evidence([]), question="Học phí bao nhiêu?")
        self.assertEqual(result["status"], "no_data")
        self.assertFalse(is_cacheable(result))

