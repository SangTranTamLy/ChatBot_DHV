"""End-to-end regressions for question focus and independent issue failures."""

import unittest
from types import SimpleNamespace

from src.chatbot.evidence import build_evidence
from src.chatbot.answer_cache import is_cacheable
from src.chatbot.output_validator import validate_model_answer
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.school_info_formatters import _evidence_contact_phone_answer
from src.models.local_llm import LocalLLM, OllamaTimeoutError
from src.retrieval.retriever import RetrieverEmbeddingError
from tests.test_runtime_contact import ContactRetriever
from tests.test_task_f import _retriever, _fixture_chunks, RecordingRetriever


class NeverGenerate:
    def generate(self, prompt):
        raise AssertionError("Verified enrollment facts must not require generation")


class QueryUnderstandingTests(unittest.TestCase):
    def test_approved_document_topics_route_to_their_reviewed_roles(self):
        cases = (
            ("Thông tin liên hệ của trường là gì?", "HOI_CO_SO_LIEN_HE", ("co_so_va_kenh_lien_he",)),
            ("Hồ sơ nhập học cần giấy tờ gì?", "HOI_HO_SO", ("ho_so_nhap_hoc",)),
            ("Sau khi nhập học được nhận quà gì?", "HOI_NHAP_HOC", ("thu_tuc_va_quyen_loi_nhap_hoc",)),
            ("Học phí HKI bao nhiêu?", "HOI_HOC_PHI", ("hoc_phi_nhap_hoc",)),
            ("Điều kiện học bổng Ngành Tiên phong là gì?", "HOI_HOC_BONG", ("chinh_sach_hoc_bong",)),
            ("UniBridge hỗ trợ tài chính bao nhiêu?", "HOI_HOC_BONG", ("unibridge_ho_tro_tai_chinh",)),
            ("Lịch tuyển sinh đợt 1 năm 2026 như thế nào?", "HOI_LICH_TUYEN_SINH", ("lich_tuyen_sinh_dot_1",)),
            ("Hạn nhận hồ sơ xét tuyển bổ sung là ngày nào?", "HOI_XET_TUYEN_BO_SUNG", ("xet_tuyen_bo_sung",)),
            ("Điểm trúng tuyển ngành Công nghệ thông tin là bao nhiêu?", "HOI_DIEM_TRUNG_TUYEN", ("diem_trung_tuyen_dot_1",)),
            ("Điểm sàn CNTT 2026?", "HOI_NGUONG_DAU_VAO", ("catalog", "admission_conditions_and_methods")),
            ("Có những ngành đào tạo nào?", "DANH_SACH_NGANH", ("catalog",)),
            ("Phương thức xét tuyển của DHV gồm những gì?", "HOI_PHUONG_THUC_XET_TUYEN", ("admission_conditions_and_methods",)),
            ("Cơ cấu tổ chức DHV gồm những đơn vị nào?", "SCHOOL_INFO", ("co_cau_to_chuc_va_lanh_dao",)),
            ("Môi trường học tập tại DHV ra sao?", "SCHOOL_INFO", ("moi_truong_hoc_tap_va_co_hoi_nghe_nghiep",)),
            ("DHV hợp tác quốc tế với trường nào?", "SCHOOL_INFO", ("hop_tac_quoc_te_va_doanh_nghiep",)),
            ("Lịch sử hình thành DHV như thế nào?", "SCHOOL_INFO", ("gioi_thieu_triet_ly_va_lich_su",)),
        )
        for question, expected_intent, expected_roles in cases:
            with self.subTest(question=question):
                plan = route_question(analyze_question(question))
                self.assertEqual(plan.intent, expected_intent)
                self.assertEqual(plan.data_roles, expected_roles)

    def test_social_channel_followups_stay_in_contact_scope(self):
        for question in (
            "Tôi theo dõi ở đâu để biết thêm thông tin?",
            "Những kênh mạng xã hội của trường là gì?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_CO_SO_LIEN_HE")
                self.assertEqual(analysis.entities["scope_reason"], "in_scope_dhv")
                self.assertTrue(analysis.entities["verified_school_info_scope"])
                self.assertIn("co_so_lien_he", plan.categories)

    def test_paperwork_and_hours_are_distinct_requests(self):
        for question, intent, request in (
            ("Hồ sơ cần gì?", "HOI_HO_SO", "documents"),
            ("Trong ngày, trường nhận hồ sơ nhập học vào khung giờ nào?", "HOI_NHAP_HOC", "reception_hours"),
            ("Hạn nộp hồ sơ là khi nào?", "HOI_LICH_TUYEN_SINH", "deadline"),
            ("Nộp hồ sơ nhập học trực tuyến được không?", "HOI_NHAP_HOC", "submission_mode"),
            ("Nộp hồ sơ lúc nào trong ngày?", "HOI_NHAP_HOC", "reception_hours"),
            ("Trường nhận hồ sơ vào giờ nào?", "HOI_NHAP_HOC", "reception_hours"),
            ("Cần giấy tờ gì?", "HOI_HO_SO", "documents"),
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, intent)
                self.assertEqual(analysis.entities["request_type"], request)

    def test_paperwork_and_weekend_reception_keep_both_requests(self):
        plan = route_question(analyze_question("Cần giấy tờ gì và có nhận hồ sơ chủ nhật không?"))
        self.assertEqual([part.intent for part in plan.subplans], ["HOI_HO_SO", "HOI_NHAP_HOC"])
        self.assertEqual([part.issue_entities["request_type"] for part in plan.subplans],
                         ["documents", "reception_hours"])

    def test_comma_separates_submission_location_from_hotline(self):
        plan = route_question(analyze_question("Nộp hồ sơ ở đâu, hotline là gì?"))
        self.assertEqual([part.intent for part in plan.subplans],
                         ["HOI_NHAP_HOC", "HOI_CO_SO_LIEN_HE"])
        self.assertIn("hotline", plan.subplans[1].issue_question)

    def test_hours_and_paperwork_use_verified_sources_without_generation(self):
        for question, expected in (
            ("Trong ngày, trường nhận hồ sơ nhập học vào khung giờ nào?", ("06:00", "18:00")),
            ("Hồ sơ cần gì?", ("Học bạ", "Căn cước")),
            ("Hồ sơ cần gì, nộp ở đâu?", ("Học bạ", "Căn cước", "194 Lê Đức Thọ", "37 Kinh Dương Vương")),
            ("Hồ sơ cần gì, nộp ở đâu và học phí bao nhiêu?", ("Học bạ", "194 Lê Đức Thọ", "1.250.000 đồng/tín chỉ")),
            ("Nộp hồ sơ nhập học ở đâu và nhận hồ sơ nhập học vào khung giờ nào?", ("194 Lê Đức Thọ", "06:00", "18:00")),
            ("Hồ sơ cần gì và nhận hồ sơ nhập học vào khung giờ nào?", ("Học bạ", "06:00", "18:00")),
            ("Nộp hồ sơ lúc nào trong ngày?", ("06:00", "18:00")),
            ("Cần giấy tờ gì và có nhận hồ sơ chủ nhật không?", ("Học bạ", "06:00", "18:00")),
        ):
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())
                self.assertEqual(result["status"], "ok")
                for marker in expected:
                    self.assertIn(marker, result["answer"])
                if "### Hồ sơ" in result["answer"]:
                    section = result["answer"].split("### Hồ sơ", 1)[1].split("###", 1)[0]
                    self.assertNotIn("12.500.000", section)

    def test_submission_location_and_hotline_are_answered_without_generation(self):
        documents = ContactRetriever().documents
        result = ask_chatbot("Nộp hồ sơ ở đâu, hotline là gì?",
                             retriever=RecordingRetriever(documents), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        for marker in ("194 Lê Đức Thọ", "37 Kinh Dương Vương", "0287 1000 888"):
            self.assertIn(marker, result["answer"])
        self.assertNotIn("736 Nguyễn Trãi", result["answer"])
        self.assertEqual(result["trace"]["multi_issue"]["statuses"], ["ok", "ok"])

    def test_hotline_needs_a_label_and_never_borrows_advisor_or_faculty_numbers(self):
        for question, category, text in (
            ("Hotline là gì?", "thong_tin_truong", "Tư vấn viên: 0848189507"),
            ("Hotline là gì?", "ho_so", "Hotline: 0848189507"),
            ("Số điện thoại Khoa Luật là gì?", "thong_tin_truong", "Tổng đài: 0287 1000 888"),
        ):
            with self.subTest(question=question, category=category):
                evidence = SimpleNamespace(chunks=[SimpleNamespace(text=text, metadata={"category": category})])
                self.assertIsNone(_evidence_contact_phone_answer(analyze_question(question), evidence))

    def test_supported_fee_is_rejected_when_question_asks_for_documents(self):
        evidence = build_evidence(_fixture_chunks())
        result = validate_model_answer("Học phí học kỳ I: 12.500.000 đồng.", evidence,
                                       question="Hồ sơ cần gì?", analysis=analyze_question("Hồ sơ cần gì?"))
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "requested_information_mismatch")
        mixed = validate_model_answer("Học bạ THPT. Học phí học kỳ I: 12.500.000 đồng.", evidence,
                                      question="Hồ sơ cần gì?", analysis=analyze_question("Hồ sơ cần gì?"))
        self.assertEqual(mixed["status"], "no_data")
        self.assertEqual(mixed["_validation_reason"], "requested_information_mismatch")

    def test_missing_hours_do_not_fall_back_to_paperwork(self):
        documents = [d for d in _fixture_chunks() if d.metadata.get("record_type") == "enrollment_document"]
        result = ask_chatbot("Nhận hồ sơ nhập học vào khung giờ nào?",
                             retriever=RecordingRetriever(documents), llm=NeverGenerate())
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])

    def test_clear_training_phrasings_keep_the_correct_route(self):
        for question, expected in (
            ("Ngưỡng nhận hồ sơ vào DHV là bao nhiêu?", "HOI_NGUONG_DAU_VAO"),
            ("Điểm tối thiểu để đăng ký ngành này", "HOI_NGUONG_DAU_VAO"),
            ("Điểm xét tuyển tối thiểu đối với các ngành Luật là bao nhiêu (tính theo thang 30)?", "HOI_NGUONG_DAU_VAO"),
            ("Lịch đăng ký xét tuyển DHV", "HOI_LICH_TUYEN_SINH"),
            ("Thủ tục đăng ký nhập học cần gì?", "HOI_HO_SO"),
            ("Nộp hồ sơ đăng ký xét tuyển DHV", "HOI_DANG_KY_XET_TUYEN"),
            ("Ngành Marketing trúng tuyển bao nhiêu điểm?", "HOI_DIEM_TRUNG_TUYEN"),
        ):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).intent, expected)

    def test_english_certificate_eligibility_uses_the_scoped_official_rule(self):
        question = (
            "Cho em hỏi ngành Ngôn ngữ Anh có nhận xét tuyển đối với thí sinh "
            "có chứng chỉ tiếng Anh quốc tế từ B1 trở lên không?"
        )
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")
        self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))

        result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertIn("phương thức 5", result["answer"])
        self.assertIn("> B1", result["answer"])
        self.assertIn("không xác nhận chứng chỉ đúng mức B1 là đủ", result["answer"])
        self.assertNotIn("lịch tuyển sinh", result["answer"].casefold())

    def test_score_minimum_with_inserted_descriptor_does_not_ask_for_clarification(self):
        question = "Điểm xét tuyển tối thiểu đối với các ngành Luật là bao nhiêu (tính theo thang 30)?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
        self.assertEqual(analysis.entities["score_type"], "application_threshold")
        result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())
        self.assertNotEqual(result["status"], "clarification")

    def test_law_economics_threshold_uses_typed_threshold_evidence(self):
        question = "Luật Kinh tế điểm đầu vào là bao nhiêu?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
        self.assertEqual(analysis.entities["major_name"], "Luật Kinh tế")
        self.assertEqual(analysis.entities["candidate_majors"], ["Luật Kinh tế"])
        plan = route_question(analysis)
        self.assertIn("nguong_dau_vao", plan.categories)
        result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertIn("18 điểm", result["answer"])

    def test_explicit_law_and_law_economics_remain_two_entities(self):
        analysis = analyze_question("So sánh ngành Luật và Luật Kinh tế")
        self.assertCountEqual(analysis.entities["candidate_majors"], ["Luật", "Luật Kinh tế"])

    def test_ambiguous_commitment_policy_asks_a_clarifying_question(self):
        result = ask_chatbot("Chính sách cam kết", retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "clarification")
        self.assertIn("không tăng học phí", result["answer"])
        self.assertIn("học bổng cam kết hoàn học phí", result["answer"])

    def test_retrieval_failure_in_one_issue_keeps_other_answers(self):
        base = _retriever()

        class FailingTuition:
            def retrieve_with_audit(self, question, **kwargs):
                if "hoc_phi" in kwargs["categories"]:
                    raise RetrieverEmbeddingError("embedding unavailable for this issue")
                return base.retrieve_with_audit(question, **kwargs)

        result = ask_chatbot("Hồ sơ cần gì, nộp ở đâu và học phí bao nhiêu?",
                             retriever=FailingTuition(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["partial"])
        self.assertIn("Học bạ", result["answer"])
        self.assertIn("194 Lê Đức Thọ", result["answer"])
        self.assertEqual(result["trace"]["multi_issue"]["statuses"], ["ok", "ok", "ollama_offline"])

    def test_multi_issue_scholarship_conditions_use_complete_verified_policy(self):
        class UnexpectedGeneration:
            def generate(self, prompt):
                raise AssertionError("Complete verified scholarship policies should not need generation")

        question = "Hồ sơ cần gì và học bổng có những điều kiện gì?"
        result = ask_chatbot(question, retriever=_retriever(), llm=UnexpectedGeneration())
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["partial"])
        self.assertIn("Học bạ", result["answer"])
        self.assertIn("Học bổng Tài năng", result["answer"])
        self.assertIn("thành tích nổi bật", result["answer"])
        self.assertEqual(result["trace"]["multi_issue"]["statuses"], ["ok", "ok"])

    def test_mixed_tuition_and_scholarship_question_answers_both_topics(self):
        for question in (
            "Học phí và học bổng DHV năm 2026 như thế nào?",
            "Học phí và học bổng DHV năm 2026 thế nào?",
        ):
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())

                self.assertEqual(result["status"], "ok")
                self.assertFalse(result["partial"])
                self.assertIn("1.250.000 đồng/tín chỉ", result["answer"])
                self.assertIn("### Học bổng", result["answer"])
                self.assertIn("75 tỷ đồng", result["answer"])
                self.assertIn("Học bổng Tài năng", result["answer"])
                self.assertIn("30% đến 100%", result["answer"])
                self.assertNotIn("Mình chưa có thông tin chính xác về học bổng", result["answer"])
                self.assertEqual(result["trace"]["multi_issue"]["statuses"], ["ok", "ok"])

    def test_broad_single_topic_scholarship_question_gets_overview(self):
        result = ask_chatbot(
            "Học bổng DHV năm 2026 như thế nào?",
            retriever=_retriever(),
            llm=NeverGenerate(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("Các chính sách học bổng DHV 2026 (tóm tắt)", result["answer"])
        self.assertIn("Học bổng Tài năng", result["answer"])
        self.assertIn("Học bổng Cam kết hoàn học phí", result["answer"])
        self.assertNotIn("Mình chưa có thông tin chính xác", result["answer"])

    def test_client_timeout_is_not_reported_as_offline(self):
        class Client:
            def chat(self, **kwargs):
                raise TimeoutError("slow server")

        with self.assertRaises(OllamaTimeoutError):
            LocalLLM(client=Client()).generate("A question")

    def test_partial_answer_is_not_cached_as_a_complete_success(self):
        self.assertFalse(is_cacheable({"answer": "One issue succeeded", "status": "ok", "partial": True}))
        self.assertTrue(is_cacheable({"answer": "Complete answer", "status": "ok", "partial": False}))

    def test_generic_admission_method_request_lists_each_method_once(self):
        result = ask_chatbot("Phương thức xét tuyển", retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        for number in range(1, 6):
            self.assertIn(f"{number}.", result["answer"])
        self.assertNotIn("6.", result["answer"])

    def test_method_count_followup_resolves_to_the_methods_just_counted(self):
        first = ask_chatbot(
            "Có bao nhiêu phương thức xét tuyển?",
            retriever=_retriever(), llm=NeverGenerate(),
        )
        second = ask_chatbot(
            "Nêu rõ những phương thức đó là gì.",
            retriever=_retriever(), llm=NeverGenerate(),
            conversation_state=first["state"],
        )
        self.assertEqual(first["status"], "ok")
        self.assertIn("5 phương thức", first["answer"])
        self.assertEqual(second["status"], "ok")
        for marker in (
            "tốt nghiệp THPT", "học bạ", "Đánh giá năng lực", "H-SCA", "trung cấp",
        ):
            self.assertIn(marker.casefold(), second["answer"].casefold())
        self.assertEqual(second["state"]["last_listed_methods"], [
            "thpt", "hoc_ba", "dgnl", "h_sca", "trung_cap",
        ])


if __name__ == "__main__":
    unittest.main()
