"""Deterministic regressions for the full-question-sweep P1 defects."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.query_analysis import (
    ConversationState,
    analyze_question,
    enrich_analysis_from_evidence,
    route_question,
    select_relevant_score_facts,
    update_conversation_state,
)
from src.chatbot.evidence import EvidenceBundle, EvidenceChunk, build_evidence
from src.chatbot.rag_chain import (
    _application_documents_missing_evidence,
    _evidence_admission_bonus_answer,
    _evidence_admission_combination_answer,
    _evidence_admission_method_presence_answer,
    _evidence_applicant_support_answer,
    _evidence_application_registration_answer,
    _evidence_date_comparison_answer,
    _evidence_exam_subject_count_answer,
    _evidence_eligibility_answer,
    _evidence_enrollment_answer,
    _evidence_optional_english_fee_answer,
    _evidence_overview_answer,
    _prioritize_enrollment_document_records,
    _prioritize_result_notification_documents,
    _evidence_required_document_answer,
    _evidence_result_notification_answer,
    _remove_unresolved_url_label,
    _evidence_school_code_answer,
    _evidence_catalog_answer,
    _evidence_school_info_answer,
    _evidence_score_list_answer,
    _evidence_scholarship_answer,
    _evidence_subject_minimum_answer,
    _evidence_supplementary_majors_answer,
    _evidence_score_comparison_reason_answer,
    _evidence_tuition_per_credit_answer,
    _evidence_tuition_total_answer,
    _prioritize_admission_date_comparison_documents,
    _named_unit_relation_missing_evidence,
    _retrieve,
    _school_info_detail_missing_evidence,
    ask_chatbot,
)
from src.chatbot.output_validator import _has_required_supplementary_date, validate_model_answer
from src.chatbot.scope_guard import detect_target_school
from src.retrieval.retriever import requested_year


class _CountingRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: tuple[str, ...],
        retrieval_query: str,
        **_: object,
    ) -> dict[str, object]:
        del question, categories, retrieval_query
        self.calls += 1
        return {"documents": []}


class _TopKRecordingRetriever(_CountingRetriever):
    def __init__(self) -> None:
        super().__init__()
        self.top_k: int | None = None

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: tuple[str, ...],
        retrieval_query: str,
        **kwargs: object,
    ) -> dict[str, object]:
        self.top_k = kwargs.get("top_k") if isinstance(kwargs.get("top_k"), int) else None
        return super().retrieve_with_audit(
            question,
            categories=categories,
            retrieval_query=retrieval_query,
        )


class ScopeResolverSweepTests(unittest.TestCase):
    def test_all_canonical_dhv_legal_name_variants_resolve_to_dhv(self) -> None:
        questions = (
            "Trường Đại học Hùng Vương TP. Hồ Chí Minh có bao nhiêu ngành?",
            "Trường Đại học Hùng Vương TP.HCM có bao nhiêu ngành?",
            "Đại học Hùng Vương TP. Hồ Chí Minh học phí bao nhiêu?",
            "Đại học Hùng Vương TP.HCM học phí bao nhiêu?",
            "TRUONG   DAI HOC HUNG VUONG TP HCM hoc phi bao nhieu?",
            "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh học phí bao nhiêu?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertEqual(detect_target_school(question)["target_school"], "DHV")

    def test_bare_hung_vuong_stays_ambiguous(self) -> None:
        self.assertEqual(detect_target_school("Điểm chuẩn Hùng Vương?")["target_school"], "AMBIGUOUS")

    def test_generic_school_nouns_and_objects_do_not_become_external_targets(self) -> None:
        questions = (
            "Trường có những ngành nào?",
            "Trường lấy mấy môn?",
            "Nhà trường có học bổng không?",
            "Khi đến trường làm thủ tục nhập học, tôi cần mang giấy tờ nào?",
            "Thông tin chi tiết về hồ sơ được trường công bố ở đâu?",
            "Sinh viên có cơ hội làm việc trong môi trường doanh nghiệp không?",
            "Trường DHV có kết nối và giao lưu với các trường khác không ạ?",
            "Trường DHV có làm đồ án như các trường khác không?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertIn(detect_target_school(question)["target_school"], {"UNSPECIFIED", "DHV"})

    def test_explicit_generic_external_phrases_remain_external(self) -> None:
        questions = (
            "Điểm chuẩn trường đại học khác?",
            "Điểm chuẩn đại học khác?",
            "Điểm chuẩn trường khác?",
            "Học phí trường khác?",
            "Đại học khác có xét học bạ không?",
            "diem chuan truong dai hoc khac?",
            "hoc phi truong khac?",
        )
        for question in questions:
            with self.subTest(question=question):
                retriever = _CountingRetriever()
                result = ask_chatbot(question, retriever=retriever)
                self.assertEqual(result["trace"]["entities"]["target_school"], "OTHER_SCHOOL")
                self.assertEqual(retriever.calls, 0)
                self.assertEqual(result["trace"]["retrieval_calls"], 0)
                self.assertEqual(result["trace"]["retrieved_docs_count"], 0)
                self.assertEqual(result["trace"]["evidence_count"], 0)

    def test_mixed_requires_comparison_not_dhv_subject_with_external_object(self) -> None:
        self.assertEqual(detect_target_school("So sánh DHV và Văn Hiến")["target_school"], "MIXED")
        self.assertEqual(detect_target_school("So sánh DHV với trường đại học khác")["target_school"], "MIXED")
        self.assertEqual(
            detect_target_school("DHV có ký hợp tác với Đại học Chosun không?")["target_school"],
            "DHV",
        )


class IntentAndYearSweepTests(unittest.TestCase):
    def _bundle(self, text: str, *, category: str) -> EvidenceBundle:
        metadata = {
            "record_type": "page_text",
            "category": category,
            "status": "verified",
            "year": 2026,
            "school_code": "DHV",
            "source_url": "https://tuyensinh.dhv.edu.vn/",
        }
        return EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )

    def test_admission_method_wording_is_in_scope_and_list_mode(self) -> None:
        analysis = analyze_question("DHV năm 2026 có những cách xét tuyển nào vậy ạ?")
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_PHUONG_THUC_XET_TUYEN")
        self.assertEqual(analysis.entities["query_mode"], "LIST")
        self.assertFalse(plan.needs_clarification)
        self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))

    def test_admissions_formulas_bonus_and_applicant_support_are_not_out_of_scope(self) -> None:
        cases = (
            ("Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ?", "HOI_PHUONG_THUC_XET_TUYEN"),
            ("Trường mình có chính sách cộng điểm khuyến khích cho chứng chỉ MOS không?", "HOI_CACH_TINH_DIEM"),
            ("Giải Nhì học sinh giỏi cấp tỉnh được cộng bao nhiêu điểm khi xét tuyển?", "HOI_CACH_TINH_DIEM"),
            ("Đạt giải Khuyến khích cấp quốc gia thì được cộng bao nhiêu điểm?", "HOI_CACH_TINH_DIEM"),
            ("Đối với thí sinh khuyết tật, trường có chính sách hỗ trợ nào?", "HOI_DANG_KY_XET_TUYEN"),
        )
        for question, expected_intent in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, expected_intent)
                self.assertNotEqual(analysis.entities["scope_reason"], "general_out_of_scope")
        combo = analyze_question(cases[0][0])
        self.assertTrue(combo.entities["admission_combination_detail"])
        self.assertEqual(route_question(combo).categories, ("phuong_thuc_xet_tuyen",))

    def test_explicit_thpt_method_and_law_eligibility_do_not_ask_wrong_clarification(self) -> None:
        questions = (
            "Tổng điểm 3 môn thi tốt nghiệp của tôi được 15 điểm thì có đủ điều kiện nộp hồ sơ vào trường không?",
            "Phần lớn các ngành còn lại lấy bao nhiêu điểm theo kết quả thi tốt nghiệp?",
            "Em được 18,5 điểm ba môn nhưng học lực lớp 12 không Giỏi thì có xét Luật được không ạ?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertFalse(plan.needs_clarification)
        law = analyze_question(questions[-1])
        self.assertEqual(law.entities["major_name"], "Luật")
        self.assertEqual(law.intent, "HOI_NGUONG_DAU_VAO")
        self.assertEqual(route_question(law).categories, ("phuong_thuc_xet_tuyen",))

    def test_subject_level_minimum_is_not_misread_as_method_count(self) -> None:
        question = (
            "Các tổ hợp xét tuyển có môn Toán và Ngữ văn, hoặc Toán, hoặc Ngữ văn, "
            "điểm môn đó phải đạt tối thiểu bao nhiêu điểm?"
        )
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
        self.assertEqual(analysis.entities["score_type"], "application_threshold")
        self.assertEqual(analysis.entities["query_mode"], "SINGLE_FACT")
        self.assertEqual(route_question(analysis).categories, ("phuong_thuc_xet_tuyen",))

        rule = (
            "Riêng đối với các ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng các điều kiện: "
            "Tổng điểm 03 môn thi tốt nghiệp THPT đạt từ 18 điểm trở lên, "
            "trong đó điểm Ngữ văn hoặc Toán từ 6 điểm trở lên."
        )
        evidence = self._bundle(rule, category="phuong_thuc_xet_tuyen")
        answer = _evidence_subject_minimum_answer(analysis, evidence)
        self.assertIn("6 điểm", str(answer))
        self.assertIn("Luật và Luật Kinh tế", str(answer))
        self.assertIn("không nêu mức sàn", str(answer))

    def test_major_and_method_threshold_questions_use_specific_published_score_row(self) -> None:
        cases = (
            "Ngưỡng học bạ của ngành Tâm lý học trong bảng điểm là bao nhiêu?",
            "Muốn xét tuyển vào ngành Tâm lý học bằng điểm ĐGNL thì cần đạt tối thiểu bao nhiêu điểm ạ?",
        )
        for question in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["major_name"], "Tâm lý học")
                self.assertEqual(analysis.entities["score_type"], "admission_score")
                self.assertEqual(analysis.entities["score_query_type"], "admission_score_lookup")
                self.assertEqual(analysis.intent, "HOI_DIEM_TRUNG_TUYEN")
                self.assertEqual(route_question(analysis).categories, ("diem_trung_tuyen",))

        facts = tuple(
            {
                "major_name": "Tâm lý học",
                "major_code": "7310401",
                "score_type": "admission_score",
                "method": method,
                "raw_value": value,
                "value": float(value),
                "status": "verified",
            }
            for method, value in (("thpt", "20"), ("hoc_ba", "22.5"), ("dgnl", "762"))
        )
        for question, expected_method, expected_value in (
            (cases[0], "hoc_ba", "22.5"),
            (cases[1], "dgnl", "762"),
        ):
            analysis = analyze_question(question)
            selected = select_relevant_score_facts(analysis, facts)
            self.assertEqual([fact["method"] for fact in selected], [expected_method])
            self.assertEqual(selected[0]["raw_value"], expected_value)

        generic = analyze_question("Ngưỡng ĐGNL chung cần tối thiểu bao nhiêu điểm?")
        self.assertEqual(generic.entities["score_type"], "application_threshold")
        self.assertEqual(generic.intent, "HOI_NGUONG_DAU_VAO")

    def test_score_reason_question_reports_only_published_comparison_not_cause(self) -> None:
        question = "Điểm trúng tuyển ngành Tâm lý học DHV 2026 cao hơn các ngành khác vì sao?"
        analysis = analyze_question(question)
        text = (
            "Theo thông báo của Hội đồng tuyển sinh, điểm trúng tuyển của DHV trong đợt 1 năm 2026 "
            "dao động từ 15 đến 20 điểm. Trong đó, các ngành Tâm lý học, Luật và Luật Kinh tế "
            "dẫn đầu với mức điểm chuẩn là 20.0 điểm. Các ngành/chương trình đào tạo còn lại "
            "giữ mức điểm trúng tuyển là 15.0 điểm."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata={
                "category": "diem_trung_tuyen", "record_type": "page_text",
                "status": "verified", "year": 2026, "school_code": "DHV",
                "source_url": "https://dhv.edu.vn/",
            }),),
            context=text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_score_comparison_reason_answer(analysis, evidence)
        self.assertIn("Tâm lý học, Luật và Luật Kinh tế", str(answer))
        self.assertIn("20,0 điểm", str(answer))
        self.assertIn("15,0 điểm", str(answer))
        self.assertIn("không nêu nguyên nhân cụ thể", str(answer))
        self.assertEqual(
            validate_model_answer(str(answer), evidence, question=question, analysis=analysis)["status"],
            "ok",
        )
        unsupported = EvidenceBundle(
            chunks=(EvidenceChunk(text="Điểm trúng tuyển ngành Tâm lý học là 20 điểm.", metadata={
                "category": "diem_trung_tuyen", "record_type": "page_text",
                "status": "verified", "year": 2026, "school_code": "DHV",
            }),),
            context="Điểm trúng tuyển ngành Tâm lý học là 20 điểm.",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertIsNone(_evidence_score_comparison_reason_answer(analysis, unsupported))

    def test_explicit_threshold_method_validates_without_requiring_other_methods(self) -> None:
        question = "Phần lớn các ngành còn lại lấy bao nhiêu điểm theo kết quả thi tốt nghiệp?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.entities["admission_method"], "thpt")
        evidence = self._bundle(
            "Ngưỡng nhận hồ sơ tối thiểu theo thi tốt nghiệp THPT là 15,00 điểm. "
            "Ngưỡng Đánh giá năng lực là 600 điểm.",
            category="phuong_thuc_xet_tuyen",
        )
        evidence = EvidenceBundle(
            chunks=evidence.chunks,
            context=evidence.context,
            sources=evidence.sources,
            score_facts=(
                {
                    "major_name": None,
                    "score_type": "application_threshold",
                    "method": "thpt",
                    "raw_value": "15,00",
                    "status": "verified",
                    "year": 2026,
                },
                {
                    "major_name": None,
                    "score_type": "application_threshold",
                    "method": "dgnl",
                    "raw_value": "600",
                    "status": "verified",
                    "year": 2026,
                },
            ),
        )
        answer = (
            "Ngưỡng nhận hồ sơ cho phần lớn chương trình theo dữ liệu DHV: "
            "thi tốt nghiệp THPT: 15,00 điểm. Đây là ngưỡng nhận hồ sơ, không phải điểm trúng tuyển."
        )
        validated = validate_model_answer(answer, evidence, question=question, analysis=analysis)
        self.assertEqual(validated["status"], "ok")
        self.assertEqual(
            validated.get("_validation_reason"),
            None,
        )

    def test_full_major_list_survives_evidence_enrichment(self) -> None:
        majors = tuple(f"Ngành {index:02d}" for index in range(1, 21))
        state = {
            "current_year": 2026,
            "last_listed_majors": list(majors),
            "previous_intent": "DANH_SACH_NGANH",
        }
        analysis = analyze_question("Điểm sàn các ngành nêu trên?", state=state)
        self.assertEqual(analysis.entities["entity_type"], "major_list")
        self.assertEqual(analysis.intent, "HOI_DIEM_TRUNG_TUYEN")
        self.assertEqual(analysis.entities["score_type"], "admission_score")
        self.assertEqual(route_question(analysis).categories, ("diem_trung_tuyen",))
        self.assertEqual(len(analysis.entities["candidate_majors"]), 20)
        enriched = enrich_analysis_from_evidence(analysis, self._bundle("", category="diem_trung_tuyen"))
        self.assertEqual(enriched.entities["candidate_majors"], list(majors))
        score_facts = tuple(
            {
                "major_name": major,
                "major_code": f"{index:07d}",
                "score_type": "admission_score",
                "method": "thpt",
                "raw_value": "15",
                "status": "verified",
            }
            for index, major in enumerate(majors, start=1)
        )
        full_table_evidence = EvidenceBundle(
            chunks=(),
            context="",
            sources=(),
            score_facts=score_facts,
        )
        answer = _evidence_score_list_answer(enriched, full_table_evidence)
        self.assertIsNotNone(answer)
        self.assertEqual(
            sum(
                1
                for line in str(answer).splitlines()
                if line.startswith("| Ngành ") and not line.startswith("| Ngành |")
            ),
            20,
        )
        self.assertTrue(all(major in str(answer) for major in majors))

    def test_explicit_major_catalogue_group_is_extracted_semantically(self) -> None:
        cases = (
            ("DHV có bao nhiêu ngành đào tạo nhóm kinh tế?", "economics"),
            ("DHV có bao nhiêu ngành đào tạo nhóm ngôn ngữ?", "languages"),
            ("DHV có bao nhiêu ngành đào tạo nhóm công nghệ?", "technology"),
        )
        for question, expected_group in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "DANH_SACH_NGANH")
                self.assertEqual(analysis.entities["major_group"], expected_group)
                self.assertEqual(analysis.entities["query_mode"], "COUNT")

    def test_basic_admission_eligibility_routes_to_verified_conditions(self) -> None:
        question = (
            "Muốn xét tuyển vào Trường Đại học Hùng Vương TP.HCM thì "
            "điều kiện cơ bản là gì?"
        )
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")
        self.assertEqual(route_question(analysis).categories, ("phuong_thuc_xet_tuyen",))

    def test_thpt_subject_count_uses_method_evidence_not_score_threshold(self) -> None:
        question = "Nếu xét bằng điểm thi tốt nghiệp thì trường lấy mấy môn ạ?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_CACH_TINH_DIEM")
        self.assertEqual(route_question(analysis).categories, ("phuong_thuc_xet_tuyen",))

    def test_explicit_dhv_school_switch_keeps_only_the_prior_method_topic(self) -> None:
        state = ConversationState()
        first = analyze_question("Văn Hiến có xét học bạ không?", state)
        self.assertEqual(first.entities["target_school"], "OTHER_SCHOOL")
        state = update_conversation_state(state, first)
        self.assertEqual(state.current_method, "hoc_ba")

        followup = analyze_question("Còn DHV thì sao?", state)
        self.assertEqual(followup.entities["target_school"], "DHV")
        self.assertEqual(followup.intent, "HOI_PHUONG_THUC_XET_TUYEN")
        self.assertEqual(followup.entities["admission_method"], "hoc_ba")
        plan = route_question(followup, state)
        self.assertFalse(plan.needs_clarification)
        self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))

        next_state = update_conversation_state(state, followup)
        self.assertEqual(next_state.current_school, "DHV")
        self.assertEqual(next_state.current_method, "hoc_ba")
        self.assertIsNone(next_state.current_major)
        self.assertEqual(next_state.candidate_majors, ())

    def test_thpt_exam_completion_phrase_does_not_override_labeled_dgnl_score(self) -> None:
        question = (
            "Tôi thi tốt nghiệp xong. Toán 8, Văn 7, Anh 7.5, "
            "ĐGNL 720, thích edit video nhưng chưa biết chọn ngành nào"
        )
        analysis = analyze_question(question)
        self.assertEqual(analysis.entities["admission_method"], "dgnl")
        self.assertEqual(analysis.entities["student_scores"].get("dgnl"), 720)

    def test_graduation_eligibility_year_is_not_misread_as_admission_method(self) -> None:
        question = (
            "Nếu thí sinh có bằng tốt nghiệp THPT từ năm 2025 trở về trước, "
            "có được tham gia xét tuyển năm 2026 không?"
        )
        analysis = analyze_question(question)
        self.assertEqual(analysis.entities["year"], 2026)
        self.assertIsNone(analysis.entities["admission_method"])
        self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")
        plan = route_question(analysis)
        self.assertFalse(plan.needs_clarification)
        self.assertEqual(
            plan.categories,
            ("phuong_thuc_xet_tuyen",),
        )

    def test_admissions_dates_and_enrollment_notifications_use_relevant_intents(self) -> None:
        intake_date = analyze_question("Trường bắt đầu tiếp nhận tân sinh viên từ ngày nào?")
        self.assertEqual(intake_date.intent, "HOI_LICH_TUYEN_SINH")
        milestone = analyze_question("Mốc 13/8 và mốc 21/8 trong hướng dẫn có cùng ý nghĩa không?")
        self.assertEqual(milestone.intent, "HOI_LICH_TUYEN_SINH")
        notice = analyze_question("Khi trúng tuyển thì trường sẽ thông báo vào đâu?")
        self.assertEqual(notice.intent, "HOI_DANG_KY_XET_TUYEN")

    def test_supplementary_major_list_is_list_mode_and_does_not_require_unasked_deadline(self) -> None:
        question = "DHV xét tuyển bổ sung năm 2026 những ngành nào?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
        self.assertEqual(analysis.entities["query_mode"], "LIST")
        self.assertTrue(_has_required_supplementary_date("Danh sách ngành có dữ liệu.", EvidenceBundle((), "", ()), question))

    def test_supplementary_program_list_preserves_all_programs_from_verified_prose(self) -> None:
        question = "DHV xét tuyển bổ sung năm 2026 những ngành nào?"
        analysis = analyze_question(question)
        names = (
            "Ngôn ngữ Anh, Ngôn ngữ Trung Quốc, Ngôn ngữ Nhật, Ngôn ngữ Hàn Quốc, "
            "Quản trị Logistics, Thương mại điện tử, Công nghệ tài chính, Luật, "
            "Luật kinh tế, Trí tuệ nhân tạo, Công nghệ thông tin và Quản trị Khách sạn"
        )
        evidence = self._bundle(
            f"Trong đợt xét tuyển bổ sung, DHV tuyển sinh tại 12 chương trình đào tạo, gồm: {names}. "
            "Với phương thức thi tốt nghiệp THPT, phần lớn chương trình nhận hồ sơ từ 15 điểm.",
            category="xet_tuyen_bo_sung",
        )
        answer = str(_evidence_supplementary_majors_answer(analysis, evidence))
        self.assertIn("12 chương trình", answer)
        self.assertIn("Quản trị Khách sạn", answer)
        self.assertIn("Công nghệ thông tin", answer)
        self.assertEqual(len([line for line in answer.splitlines() if line[:1].isdigit()]), 12)

    def test_result_notification_evidence_is_prioritized_before_context_budget(self) -> None:
        irrelevant = Document(page_content="Thông tin tuyển sinh chung.", metadata={})
        invitation = Document(
            page_content="Thư mời nhập học hoặc tin nhắn Zalo xác nhận nhập học.", metadata={}
        )
        website = Document(
            page_content="Chi tiết công bố trên website tuyển sinh tuyensinh.dhv.edu.vn.", metadata={}
        )
        ministry = Document(
            page_content="Xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung của Bộ Giáo dục.", metadata={}
        )
        ordered = _prioritize_result_notification_documents([irrelevant, invitation, website, ministry])
        self.assertEqual(ordered[:3], [ministry, website, invitation])
        self.assertEqual(ordered[3], irrelevant)

    def test_enrollment_checklist_records_precede_long_page_text(self) -> None:
        long_page = Document(
            page_content="2.2 Chuẩn Bị Hồ Sơ Nhập Học DHV " + ("nội dung dài " * 800),
            metadata={"record_type": "page_text"},
        )
        checklist = Document(
            page_content="Hồ sơ nhập học: Học bạ THPT.",
            metadata={"record_type": "enrollment_document"},
        )
        ordered = _prioritize_enrollment_document_records([long_page, checklist])
        self.assertEqual(ordered, [checklist, long_page])

    def test_admission_date_documents_are_prioritized_by_milestone_meaning(self) -> None:
        unrelated = Document(page_content="Thông tin tổng quan.", metadata={})
        deadline = Document(
            page_content="Thời gian xác nhận nhập học trên cổng Bộ đến 21/08/2026.", metadata={}
        )
        benefit = Document(
            page_content="Hoàn tất xác nhận trước ngày 13/08/2026 để hưởng ưu đãi cao nhất.", metadata={}
        )
        ordered = _prioritize_admission_date_comparison_documents(
            [unrelated, deadline, benefit],
            "Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng một ý nghĩa không?",
        )
        self.assertEqual(ordered, [benefit, deadline, unrelated])

    def test_admission_date_prioritization_recognizes_written_month_dates(self) -> None:
        unrelated = Document(page_content="Thông tin tuyển sinh chung.", metadata={})
        deadline = Document(
            page_content=(
                "Thời gian xác nhận nhập học trên cổng Bộ từ ngày 14 tháng 8 năm 2026 "
                "đến 17 giờ ngày 21 tháng 8 năm 2026."
            ),
            metadata={},
        )
        benefit = Document(
            page_content=(
                "Tân sinh viên hoàn tất xác nhận trước ngày 13/8/2026 "
                "sẽ được hưởng mức ưu đãi cao nhất."
            ),
            metadata={},
        )
        ordered = _prioritize_admission_date_comparison_documents(
            [unrelated, deadline, benefit],
            "Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng một ý nghĩa không?",
        )
        self.assertEqual(ordered, [benefit, deadline, unrelated])

    def test_event_dates_are_not_admission_score_or_schedule_questions(self) -> None:
        questions = (
            "Khoa Quản trị Kinh doanh Marketing tổ chức tọa đàm CO-OP vào thời điểm nào?",
            "Chương trình Khởi nghiệp cùng Sinh viên DHV 2026 diễn ra vào thời điểm nào?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "OUT_OF_SCOPE")
                self.assertFalse(plan.needs_clarification)

    def test_school_event_support_question_is_not_a_chatbot_scope_request(self) -> None:
        event = analyze_question(
            "Workshop la ban nghe nghiep cua khoa BAM ho tro sinh vien ve noi dung gi?"
        )
        assistant_scope = analyze_question("Bạn hỗ trợ được những gì?")
        self.assertEqual(event.intent, "OUT_OF_SCOPE")
        self.assertEqual(assistant_scope.intent, "SYSTEM_SCOPE")

    def test_school_history_dates_do_not_route_as_admission_score_or_contact(self) -> None:
        questions = (
            "Mốc thành lập chính thức của Trường Đại học Hùng Vương TP.HCM là ngày nào?",
            "Trường Đại học Hùng Vương được phép đổi tên thành Trường Đại học Hùng Vương TP.HCM vào thời điểm nào?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "SCHOOL_INFO")
                self.assertEqual(route_question(analysis).categories, ("thong_tin_truong",))

    def test_verified_school_overview_and_partnership_topics_are_routed_narrowly(self) -> None:
        supported_topics = (
            "Giới thiệu về trường",
            "Ba giá trị cốt lõi của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì?",
            "Triết lý giáo dục của Trường Đại học Hùng Vương TP. Hồ Chí Minh được thể hiện bằng những từ khóa nào?",
            "Năm 2026, DHV có ký hợp tác với Đại học Chosun của Hàn Quốc không?",
            "Trường DHV có kết nối và giao lưu với các trường khác không ạ?",
            "Thực tập thì trường có hỗ trợ kết nối sinh viên với doanh nghiệp không?",
            "Thực tập thì trường sẽ giới thiệu cho hay là sinh viên phải tự đi kiếm doanh nghiệp?",
        )
        for question in supported_topics:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "SCHOOL_INFO")
                self.assertTrue(analysis.entities["verified_school_info_scope"])
                self.assertEqual(analysis.entities["scope_reason"], "in_scope_dhv")
                self.assertEqual(route_question(analysis).categories, ("thong_tin_truong",))

    def test_unknown_company_specific_claim_is_not_opened_as_verified_school_info(self) -> None:
        analysis = analyze_question(
            "Việc hợp tác giữa trường và Công ty Công nghệ PREP năm 2026 hướng tới lợi ích nào?"
        )
        self.assertFalse(analysis.entities["verified_school_info_scope"])
        self.assertEqual(analysis.entities["scope_reason"], "general_out_of_scope")

    def test_unindexed_institute_details_do_not_retrieve_general_school_overview(self) -> None:
        question = "Viện IATAI có kết nối đối tác trong lĩnh vực an toàn thông tin không?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "OUT_OF_SCOPE")
        self.assertFalse(analysis.entities["verified_school_info_scope"])
        retriever = _CountingRetriever()
        result = ask_chatbot(question, retriever=retriever)
        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["retrieval_calls"], 0)

    def test_school_info_fact_fallback_quotes_only_matching_verified_evidence(self) -> None:
        question = (
            "Trường Đại học Dân lập Hùng Vương được phép đổi tên thành "
            "Trường Đại học Hùng Vương TP. Hồ Chí Minh vào thời điểm nào?"
        )
        evidence_text = (
            "Ngày 14/05/2008, Bộ trưởng Bộ Giáo dục và Đào tạo ban hành văn bản "
            "số 4167/BGDĐT-PC cho phép Trường Đại học Dân lập Hùng Vương đổi tên "
            "thành Trường Đại học Hùng Vương Thành phố Hồ Chí Minh."
        )
        analysis = analyze_question(question)
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=evidence_text, metadata={}),),
            context=evidence_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_school_info_answer(analysis, evidence)
        self.assertIsNotNone(answer)
        self.assertIn("14/05/2008", str(answer))
        self.assertIn("đổi tên", str(answer))

    def test_school_info_named_fund_question_returns_its_amount_not_generic_overview(self) -> None:
        question = "Quỹ Vườn ươm Khởi nghiệp của trường được giới thiệu với quy mô ban đầu bao nhiêu?"
        analysis = analyze_question(question)
        evidence_text = (
            'Với quỹ "Vườn ươm Khởi nghiệp" có giá trị ban đầu 1 TRIỆU USD '
            "cùng đội ngũ Mentor kinh nghiệm sẽ là nơi ươm mầm những ý tưởng sáng tạo."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=evidence_text, metadata={"record_type": "page_text"}),),
            context=evidence_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )

        answer = _evidence_school_info_answer(analysis, evidence)

        self.assertIsNotNone(answer)
        self.assertIn("1 TRIỆU USD", str(answer))
        self.assertIn("Vườn ươm Khởi nghiệp", str(answer))

    def test_thpt_subject_count_skips_unrelated_scholarship_three_subject_fact(self) -> None:
        question = "Nếu xét bằng điểm thi tốt nghiệp thì trường lấy mấy môn ạ?"
        analysis = analyze_question(question)
        scholarship_line = (
            "CÁCH 2. Xét học bổng bằng kết quả học tập 3 môn theo 2 nhóm tổ hợp."
        )
        thpt_line = (
            "Tổng điểm 03 môn thi tốt nghiệp THPT dùng để xét tuyển theo tổ hợp."
        )
        evidence = EvidenceBundle(
            chunks=(
                EvidenceChunk(text=scholarship_line, metadata={"record_type": "page_text"}),
                EvidenceChunk(text=thpt_line, metadata={"record_type": "page_text"}),
            ),
            context=f"{scholarship_line}\n{thpt_line}",
            sources=({"url": "https://dhv.edu.vn/"},),
        )

        answer = _evidence_exam_subject_count_answer(analysis, evidence)

        self.assertIn("3 môn", str(answer))
        self.assertIn("thi tốt nghiệp THPT", str(answer))
        self.assertNotIn("học bổng", str(answer).casefold())

    def test_school_unit_detail_requires_unit_specific_evidence(self) -> None:
        question = "Mạng lưới đối tác của Khoa Ngôn ngữ gồm những đơn vị nào?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "SCHOOL_INFO")
        generic_evidence = EvidenceBundle(
            chunks=(EvidenceChunk(
                text="DHV đẩy mạnh hợp tác với các trường và doanh nghiệp.",
                metadata={"record_type": "page_text"},
            ),),
            context="DHV đẩy mạnh hợp tác với các trường và doanh nghiệp.",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertTrue(_school_info_detail_missing_evidence(analysis, generic_evidence))

        unit_evidence = EvidenceBundle(
            chunks=(EvidenceChunk(
                text="Khoa Ngôn ngữ có hoạt động hợp tác với Đại học Chosun.",
                metadata={"record_type": "page_text"},
            ),),
            context="Khoa Ngôn ngữ có hoạt động hợp tác với Đại học Chosun.",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertFalse(_school_info_detail_missing_evidence(analysis, unit_evidence))

    def test_specific_location_or_event_detail_cannot_borrow_generic_partner_evidence(self) -> None:
        question = "DHV hợp tác với đơn vị nào để mở rộng cơ hội thực tập tại Hoa Kỳ?"
        analysis = analyze_question(question)
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(
                text="DHV hợp tác với Đại học Chosun và Trường Đại học Hyogo.",
                metadata={"record_type": "page_text"},
            ),),
            context="DHV hợp tác với Đại học Chosun và Trường Đại học Hyogo.",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertTrue(_school_info_detail_missing_evidence(analysis, evidence))

    def test_school_overview_rejoins_wrapped_source_sentences(self) -> None:
        analysis = analyze_question("Giới thiệu về trường")
        evidence_text = (
            "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh (DHV) được thành lập\n"
            "từ năm 1995, là một trường đại học ngoài công lập.\n"
            "Với triết lý ‘Giá trị thật – Tương lai thật’, DHV chú trọng thực học – thực hành.\n"
            "Sinh viên tiếp cận môi trường Doanh nghiệp ngay từ năm thứ nhất."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=evidence_text, metadata={"record_type": "page_text"}),),
            context=evidence_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_overview_answer(analysis, evidence)
        self.assertIn("được thành lập từ năm 1995", str(answer))
        self.assertIn("Giá trị thật", str(answer))
        self.assertIn("tiếp cận môi trường Doanh nghiệp", str(answer))

    def test_school_code_can_be_read_across_wrapped_native_lines(self) -> None:
        analysis = analyze_question("Mã trường dùng trong tuyển sinh là gì?")
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(
                text="Trường Đại học Hùng Vương TP. Hồ Chí Minh (Mã trường\nDHV) chính thức công bố tuyển sinh.",
                metadata={"record_type": "page_text"},
            ),),
            context="Trường Đại học Hùng Vương TP. Hồ Chí Minh (Mã trường DHV)",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertEqual(_evidence_school_code_answer(analysis, evidence), "Mã trường dùng trong tuyển sinh là DHV.")

    def test_admission_bonus_and_law_eligibility_join_wrapped_evidence(self) -> None:
        bonus_question = "Đạt giải Khuyến khích cấp quốc gia thì được cộng bao nhiêu điểm?"
        bonus_analysis = analyze_question(bonus_question)
        bonus_text = (
            "Thí sinh đạt giải trong các kỳ thi, cuộc thi trong 03 năm gần nhất được cộng điểm như sau:\n"
            "• Giải từ Khuyến khích cấp Quốc gia hoặc giải Nhất/Nhì cấp tỉnh: +1,50\nđiểm"
        )
        bonus_evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=bonus_text, metadata={"record_type": "page_text"}),),
            context=bonus_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        self.assertIn("+1,50", str(_evidence_admission_bonus_answer(bonus_analysis, bonus_evidence)))

        law_question = "Em được 18,5 điểm ba môn nhưng học lực lớp 12 không Giỏi thì có xét Luật được không?"
        law_analysis = analyze_question(law_question)
        law_text = (
            "Riêng đối với ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng các điều kiện:\n"
            "• Học lực lớp 12 đạt loại Giỏi trở lên, điểm trung bình môn lớp 12 từ 8,0 trở lên\n"
            "• Tổng điểm 03 môn thi tốt nghiệp THPT dùng để xét tuyển đạt từ 18 điểm trở lên,\n"
            "trong đó điểm Ngữ văn hoặc Toán từ 6 điểm trở lên"
        )
        law_evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=law_text, metadata={"record_type": "page_text"}),),
            context=law_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_eligibility_answer(law_analysis, law_evidence)
        self.assertIsNone(answer)
        from src.chatbot.rag_chain import _evidence_major_eligibility_answer
        answer = _evidence_major_eligibility_answer(law_analysis, law_evidence)
        self.assertIn("học lực lớp 12", str(answer))
        self.assertIn("không thay thế điều kiện học lực", str(answer))

    def test_admission_combination_detail_is_not_answered_with_method_catalogue(self) -> None:
        question = "Tổ hợp môn xét tuyển của trường gồm những môn nào?"
        analysis = analyze_question(question)
        evidence_text = (
            "Khối công nghệ:\n• Toán + 2 môn điểm cao nhất (Văn, Ngoại ngữ, Lý, Hóa, Sinh, Sử, Địa,\n"
            "Tin học, GD kinh tế & PL, Công nghệ)\n"
            "Khối Kinh tế - Quản trị truyền thông – Dịch vụ - Ngôn ngữ:\n"
            "• Chọn 1 trong 2: Toán + 2 môn điểm cao nhất, Văn + 2 môn điểm cao nhất"
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=evidence_text, metadata={"record_type": "page_text"}),),
            context=evidence_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_admission_combination_answer(analysis, evidence)
        self.assertIn("Toán + 2 môn điểm cao nhất", str(answer))
        # The verified source labels this subject "Văn"; do not manufacture
        # a more specific label that is absent from the evidence.
        self.assertIn("Văn", str(answer))
        self.assertNotIn("Ngành Ngôn ngữ Anh", str(answer))
        self.assertNotIn("thiểu 15,00 điểm", str(answer))

    def test_official_combination_page_extracts_only_two_subject_structures(self) -> None:
        question = "Tổ hợp môn xét tuyển của trường gồm những môn nào?"
        analysis = analyze_question(question)
        source_text = (
            "Tổ hợp xét tuyển được xây dựng theo hai cấu trúc:\n"
            "Toán + 02 môn có điểm cao nhất trong các môn: Ngữ văn, Ngoại ngữ, Vật lý,\n"
            "Hóa học, Sinh học, Lịch sử, Địa lý, Tin học, Giáo dục kinh tế và pháp luật, Công nghệ công\n"
            "nghiệp.\n"
            "Ngữ văn + 02 môn có điểm cao nhất trong các môn: Toán, Ngoại ngữ, Vật lý,\n"
            "Hóa học, Sinh học, Lịch sử, Địa lý, Tin học, Giáo dục kinh tế và pháp luật, Công nghệ công\n"
            "nghiệp.\nCác tổ hợp xét tuyển được thiết kế linh hoạt.\n"
            "Riêng đối với ngành Luật: ngưỡng 15 điểm."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=source_text, metadata={
                "category": "phuong_thuc_xet_tuyen", "record_type": "page_text", "page": 4,
                "status": "verified", "year": 2026, "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
            }),),
            context=source_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = str(_evidence_admission_combination_answer(analysis, evidence))
        self.assertIn("Toán + 02 môn có điểm cao nhất", answer)
        self.assertIn("Ngữ văn + 02 môn có điểm cao nhất", answer)
        self.assertNotIn("Riêng đối với ngành Luật", answer)

    def test_natural_language_subject_combination_question_uses_official_structure(self) -> None:
        question = "Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ?"
        analysis = analyze_question(question)
        source_text = (
            "Toán + 02 môn có điểm cao nhất trong các môn: Ngữ văn, Ngoại ngữ, Vật lý, Hóa học.\n"
            "Ngữ văn + 02 môn có điểm cao nhất trong các môn: Toán, Ngoại ngữ, Vật lý, Hóa học."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=source_text, metadata={
                "category": "phuong_thuc_xet_tuyen", "record_type": "page_text", "page": 4,
                "status": "verified", "year": 2026, "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
            }),),
            context=source_text,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )
        answer = str(_evidence_admission_combination_answer(analysis, evidence))
        self.assertTrue(answer.startswith("Có."))
        self.assertIn("Toán + 02 môn có điểm cao nhất", answer)
        self.assertIn("Ngữ văn + 02 môn có điểm cao nhất", answer)
        validated = validate_model_answer(answer, evidence, question=question, analysis=analysis)
        self.assertEqual(validated["status"], "ok")

    def test_explicit_dhv_school_switch_answers_inherited_method_from_dhv_evidence(self) -> None:
        external_state = ConversationState.from_value({
            "current_method": "hoc_ba",
            "previous_intent": "HOI_PHUONG_THUC_XET_TUYEN",
            "current_school": "OTHER_SCHOOL",
            "school_scope": "OTHER_SCHOOL",
            "school_mentions": ["Văn Hiến"],
        }, default_year=2026)
        analysis = analyze_question("Còn DHV thì sao?", state=external_state)
        self.assertEqual(analysis.intent, "HOI_PHUONG_THUC_XET_TUYEN")
        self.assertEqual(analysis.entities["target_school"], "DHV")
        self.assertEqual(analysis.entities["admission_method"], "hoc_ba")
        plan = route_question(analysis, state=external_state)
        self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))

        source_text = "1.4. Xét tuyển kết quả học tập THPT (học bạ)."
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=source_text, metadata={
                "category": "phuong_thuc_xet_tuyen", "record_type": "page_text",
                "status": "verified", "year": 2026, "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
            }),),
            context=source_text,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )
        answer = _evidence_admission_method_presence_answer(analysis, evidence)
        self.assertIn("học bạ", str(answer))
        self.assertEqual(
            validate_model_answer(str(answer), evidence, question="Còn DHV thì sao?", analysis=analysis)["status"],
            "ok",
        )
        irrelevant = EvidenceBundle(
            chunks=(EvidenceChunk(text="Học bổng hỗ trợ học phí theo điểm thi.", metadata={
                "category": "phuong_thuc_xet_tuyen", "record_type": "page_text",
                "status": "verified", "year": 2026, "school_code": "DHV",
            }),),
            context="Học bổng hỗ trợ học phí theo điểm thi.",
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )
        self.assertIsNone(_evidence_admission_method_presence_answer(analysis, irrelevant))

    def test_optional_english_exam_total_uses_only_explicit_verified_page_text_sum(self) -> None:
        question = "Tổng chi phí học kỳ I bao gồm kiểm tra năng lực tiếng Anh là bao nhiêu?"
        analysis = analyze_question(question)
        metadata = {
            "record_type": "page_text", "category": "ho_so", "page": 4,
            "status": "verified", "year": 2026, "school_code": "DHV",
            "source_url": "https://dhv.edu.vn/",
        }
        exact_row = "TỔNG CHI PHÍ HỌC KỲ I\n14.250.000 đồng + 250.000 đồng"
        incorrect_record = (
            "Học phí HKI: 12.500.000 đồng\nKiểm tra năng lực Tiếng Anh: 5.000.000 đồng\n"
            "Tổng chi phí học kỳ I: 14.250.000 đồng"
        )
        evidence = EvidenceBundle(
            chunks=(
                EvidenceChunk(text=exact_row, metadata=metadata),
                EvidenceChunk(text=incorrect_record, metadata={**metadata, "record_type": "tuition"}),
            ),
            context=exact_row + "\n" + incorrect_record,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_tuition_total_answer(analysis, evidence)
        self.assertIn("14.500.000", str(answer))
        validated = validate_model_answer(str(answer), evidence, question=question, analysis=analysis)
        self.assertEqual(validated["status"], "ok")

        stale_only = EvidenceBundle(
            chunks=(EvidenceChunk(text=incorrect_record, metadata={**metadata, "record_type": "tuition"}),),
            context=incorrect_record,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        rejected = validate_model_answer(
            "Tổng chi phí học kỳ I là 14.500.000 đồng.",
            stale_only,
            question=question,
            analysis=analysis,
        )
        self.assertEqual(rejected["status"], "no_data")
        self.assertEqual(rejected["_validation_reason"], "optional_fee_total_unverified")

        natural_question = (
            "Nếu có kiểm tra năng lực tiếng Anh thì số tiền học kỳ I theo bảng sẽ thành bao nhiêu?"
        )
        natural_analysis = analyze_question(natural_question)
        natural_answer = _evidence_tuition_total_answer(natural_analysis, evidence)
        self.assertIn("14.500.000", str(natural_answer))
        self.assertEqual(
            validate_model_answer(
                str(natural_answer), evidence, question=natural_question, analysis=natural_analysis
            )["status"],
            "ok",
        )

    def test_optional_english_fee_keeps_table_cell_amount_after_duplicate_line_dedup(self) -> None:
        question = "Kiểm tra năng lực tiếng Anh có phải ai cũng đóng 250.000 đồng không?"
        analysis = analyze_question(question)
        evidence = self._bundle(
            "Tài khoản học liệu điện tử\n250.000 đồng\n"
            "Kiểm tra năng lực Tiếng Anh (nếu có)\n250.000 đồng\n",
            category="ho_so",
        )
        evidence = EvidenceBundle(
            chunks=(
                *evidence.chunks,
                EvidenceChunk(
                    text="Kiểm tra năng lực Tiếng Anh: 5.000.000 đồng",
                    metadata={
                        "record_type": "tuition",
                        "category": "hoc_phi",
                        "status": "verified",
                        "year": 2026,
                        "school_code": "DHV",
                        "source_url": "https://dhv.edu.vn/",
                    },
                ),
            ),
            context=evidence.context + "\nKiểm tra năng lực Tiếng Anh: 5.000.000 đồng",
            sources=evidence.sources,
        )
        answer = _evidence_optional_english_fee_answer(analysis, evidence)
        self.assertIn("250.000 đồng", str(answer))
        self.assertIn("nếu có", str(answer))
        self.assertNotIn("5.000.000", str(answer))

    def test_enrollment_document_answer_keeps_complete_checklist_and_not_application_docs(self) -> None:
        question = "Hồ sơ nhập học gồm những gì?"
        analysis = analyze_question(question)
        names = (
            "Căn cước/Căn cước công dân.",
            "Học bạ THPT.",
            "Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học.",
            "Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026.",
        )
        evidence = EvidenceBundle(
            chunks=tuple(
                EvidenceChunk(
                    text=f"Hồ sơ nhập học: {name}",
                    metadata={"record_type": "enrollment_document", "page": 3},
                )
                for name in names
            ),
            context="\n".join(f"Hồ sơ nhập học: {name}" for name in names),
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_enrollment_answer(analysis, evidence)
        self.assertIsNotNone(answer)
        for name in names:
            self.assertIn(name, str(answer))

        application_question = analyze_question("Hồ sơ xét tuyển gồm những gì?")
        self.assertIsNone(_evidence_enrollment_answer(application_question, evidence))
        self.assertTrue(_application_documents_missing_evidence(application_question, evidence))

    def test_enrollment_start_date_question_returns_reception_window_not_promotion_deadline(self) -> None:
        question = "Trường bắt đầu tiếp nhận tân sinh viên từ ngày nào?"
        analysis = analyze_question(question)
        evidence = self._bundle(
            "Dhv tiếp nhận nhập học 06:00 – 18:00 Từ 11/08/2026 đến 10/09/2026.\n"
            "Hoàn tất xác nhận trước ngày 13/8/2026 để được hưởng ưu đãi học bổng.",
            category="ho_so",
        )
        answer = _evidence_enrollment_answer(analysis, evidence)
        self.assertIn("11/08/2026", str(answer))
        self.assertIn("10/09/2026", str(answer))
        self.assertNotIn("13/8/2026", str(answer))
        self.assertIn("từ ngày nào", question)

    def test_highest_benefit_question_uses_promotion_deadline_not_reception_window(self) -> None:
        question = "Muốn hưởng mức ưu đãi cao nhất thì em nên hoàn tất xác nhận trước mốc nào?"
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "HOI_NHAP_HOC")
        evidence = self._bundle(
            "Hoàn tất xác nhận trước ngày 13/8/2026 để được hưởng mức ưu đãi cao nhất "
            "theo chính sách tuyển sinh.\n"
            "DHV tiếp nhận nhập học 06:00 – 18:00 từ 11/08/2026 đến 10/09/2026.",
            category="ho_so",
        )
        answer = _evidence_enrollment_answer(analysis, evidence)
        self.assertIn("13/8/2026", str(answer))
        self.assertIn("ưu đãi cao nhất", str(answer))
        self.assertNotIn("11/08/2026", str(answer))

    def test_scholarship_score_lines_are_deduplicated_and_drop_incomplete_amount_fragments(self) -> None:
        question = "Học bổng theo tổng điểm 3 môn được tính như thế nào?"
        analysis = analyze_question(question)
        evidence = self._bundle(
            "• Tổng điểm 3 môn > 25.5 điểm ➝ Hỗ trợ 70% học phí chuẩn HK1 (tương\n"
            "8.750.000 VNĐ)\n"
            "• Tổng điểm 3 môn 21 ≤ 25.5 điểm ➝ Hỗ trợ 50% học phí chuẩn HK1 (tương\n"
            "đương 6.250.000 VNĐ)\n"
            "Chính sách học bổng: Tổng đi ểm 3 môn 21 ≤ 25.5 đi ểm ➝ Hỗ trợ 50% học phí chu ẩn HK1 (tương",
            category="hoc_bong",
        )
        answer = str(_evidence_scholarship_answer(analysis, evidence))
        self.assertIn("70%", answer)
        self.assertIn("50%", answer)
        self.assertEqual(answer.count("70%"), 1)
        self.assertEqual(answer.count("50%"), 1)
        self.assertNotIn("tương đương", answer)
        self.assertNotIn("đi ểm", answer)
        self.assertNotIn("chu ẩn", answer)
        self.assertIn("Tổng điểm 3 môn từ 21 đến 25.5 điểm", answer)

    def test_admission_scholarship_max_does_not_confuse_talent_award(self) -> None:
        question = "Học bổng tuyển sinh DHV 2026 dành cho tân sinh viên đạt mức tối đa bao nhiêu?"
        analysis = analyze_question(question)
        evidence = self._bundle(
            "• Điểm thi > 700 ➝ Hỗ trợ 80% học phí chuẩn HK1 (tương đương\n"
            "10.000.000 VNĐ)\n"
            "• Điểm thi từ 650 đến 700 ➝ Hỗ trợ 60% học phí chuẩn HK1\n"
            "Học bổng Tài năng có mức hỗ trợ từ 30% đến 100% học phí toàn khóa.",
            category="hoc_bong",
        )
        answer = str(_evidence_scholarship_answer(analysis, evidence))
        self.assertIn("80%", answer)
        self.assertIn("10.000.000 VNĐ", answer)
        self.assertNotIn("h ọc", answer)
        self.assertNotIn("100%", answer)

    def test_enrollment_fee_and_timing_answers_exclude_duplicates_and_promo_deadlines(self) -> None:
        evidence = EvidenceBundle(
            chunks=(
                EvidenceChunk(
                    text=(
                        "Phí nhập học: 1.500.000 đồng\n"
                        "Tài khoản học liệu điện tử: 250.000 đồng\n"
                        "Phí nhập học\nTài khoản học liệu điện tử\n"
                        "Dhv tiếp nhận nhập học 06:00 – 18:00 Từ 11/08/2026 đến 10/09/2026\n"
                        "Hoàn tất xác nhận trước ngày 13/8/2026 để được hưởng ưu đãi học bổng."
                    ),
                    metadata={"record_type": "page_text", "category": "ho_so"},
                ),
            ),
            context="verified enrollment page text",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        fee_analysis = analyze_question("Phí nhập học bao nhiêu?")
        fee_answer = _evidence_enrollment_answer(fee_analysis, evidence)
        self.assertIn("1.500.000 đồng", str(fee_answer))
        self.assertIn("250.000 đồng", str(fee_answer))
        self.assertEqual(str(fee_answer).count("1.500.000"), 1)
        self.assertNotIn("\n- Phí nhập học\n", str(fee_answer))

        timing_analysis = analyze_question("Nhập học khi nào?")
        timing_answer = _evidence_enrollment_answer(timing_analysis, evidence)
        self.assertIn("11/08/2026", str(timing_answer))
        self.assertNotIn("13/8/2026", str(timing_answer))

    def test_generic_internship_followup_does_not_pick_a_specific_faculty_fact(self) -> None:
        question = "Thực tập thì trường sẽ giới thiệu cho hay là sinh viên phải tự đi kiếm doanh nghiệp?"
        analysis = analyze_question(question)
        evidence_text = (
            "Khoa Luật hợp tác với các tổ chức trong lĩnh vực pháp lý nhằm hỗ trợ sinh viên thực tập.\n\n"
            "Các khoa của DHV hợp tác với doanh nghiệp và tổ chức chuyên môn nhằm tạo điều kiện "
            "cho sinh viên kiến tập, thực hành, thực tập và tìm kiếm cơ hội việc làm."
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=evidence_text, metadata={}),),
            context=evidence_text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_school_info_answer(analysis, evidence)
        self.assertIn("Các khoa của DHV", str(answer))
        self.assertNotIn("Khoa Luật", str(answer))

    def test_unverified_school_events_and_major_career_claims_stay_out_of_scope(self) -> None:
        questions = (
            "Chương trình Khởi nghiệp cùng Sinh viên DHV 2026 diễn ra vào thời điểm nào?",
            "Một hướng việc làm sau ngành Quản trị kinh doanh có phải là chuyên viên nhân sự không?",
            "Ba phòng thí nghiệm công nghệ trọng điểm được DHV đưa vào vận hành năm 2026 gồm những phòng nào?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "OUT_OF_SCOPE")

    def test_admission_year_wins_over_graduation_year(self) -> None:
        cases = (
            "Nếu thí sinh tốt nghiệp từ năm 2025 trở về trước, có được xét tuyển năm 2026 không?",
            "tốt nghiệp 2024 có xét tuyển năm 2026 không?",
            "học sinh tốt nghiệp 2025 đăng ký DHV 2026 được không?",
            "điểm thi 2025 có dùng xét tuyển 2026 không?",
            "tốt nghiệp trước 2026 có đăng ký tuyển sinh 2026 không?",
        )
        for question in cases:
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).entities["year"], 2026)
                self.assertEqual(requested_year(question), 2026)
        graduation_only = "Tốt nghiệp năm 2025 có được đăng ký xét tuyển không?"
        self.assertEqual(analyze_question(graduation_only).entities["year"], 2026)
        self.assertIsNone(requested_year(graduation_only))

    def test_count_and_list_query_modes_are_preserved(self) -> None:
        cases = (
            ("DHV có mấy phương thức xét tuyển?", "COUNT"),
            ("Liệt kê tất cả phương thức xét tuyển", "LIST"),
            ("Có bao nhiêu ngành?", "COUNT"),
            ("Liệt kê tất cả ngành", "LIST"),
        )
        for question, mode in cases:
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).entities["query_mode"], mode)
        major_count = analyze_question(
            "Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh đào tạo bao nhiêu ngành đại học chính quy?"
        )
        self.assertEqual(
            route_question(major_count).categories,
            ("nganh_dao_tao", "thong_tin_truong", "phuong_thuc_xet_tuyen"),
        )

    def test_enumeration_mode_expands_retrieval_candidate_limit(self) -> None:
        retriever = _TopKRecordingRetriever()
        ask_chatbot("Liệt kê tất cả phương thức xét tuyển", retriever=retriever)
        self.assertEqual(retriever.top_k, 64)

        major_count = _TopKRecordingRetriever()
        ask_chatbot(
            "Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh đào tạo bao nhiêu ngành đại học chính quy?",
            retriever=major_count,
        )
        self.assertEqual(major_count.top_k, 96)

    def test_school_code_question_expands_retrieval_only_for_code_fact(self) -> None:
        retriever = _TopKRecordingRetriever()
        ask_chatbot(
            "Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì?",
            retriever=retriever,
        )
        self.assertEqual(retriever.top_k, 8)

        generic_contact = _TopKRecordingRetriever()
        ask_chatbot("Địa chỉ trường ở đâu?", retriever=generic_contact)
        self.assertIsNone(generic_contact.top_k)

    def test_combination_detail_expands_candidate_limit_narrowly(self) -> None:
        retriever = _TopKRecordingRetriever()
        ask_chatbot(
            "Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ?",
            retriever=retriever,
        )
        self.assertEqual(retriever.top_k, 16)


class SweepEvidenceBoundaryTests(unittest.TestCase):
    def _bundle(self, text: str, *, category: str = "thong_tin_truong") -> EvidenceBundle:
        metadata = {
            "record_type": "page_text",
            "category": category,
            "status": "verified",
            "year": 2026,
            "school_code": "DHV",
            "source_url": "https://tuyensinh.dhv.edu.vn/",
        }
        return EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )

    def test_multiline_admission_table_cells_become_verified_score_facts(self) -> None:
        text = (
            "22\n7810103\nQuản trị Dịch vụ Du lịch\nvà Lữ hành\n15\n18\n600\n"
            "23\n7810201\nQuản trị Khách sạn\n15\n18\n600"
        )
        document = Document(
            page_content=text,
            metadata={
                "chunk_id": "multiline-score-table",
                "record_type": "document_text",
                "category": "diem_trung_tuyen",
                "year": 2026,
                "status": "verified",
                "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
            },
        )
        evidence = build_evidence([document])
        by_major = {
            name: {
                fact["method"]: fact["raw_value"]
                for fact in evidence.score_facts
                if fact["major_name"] == name
            }
            for name in ("Quản trị Dịch vụ Du lịch và Lữ hành", "Quản trị Khách sạn")
        }
        self.assertEqual(by_major["Quản trị Dịch vụ Du lịch và Lữ hành"], {
            "thpt": "15", "hoc_ba": "18", "dgnl": "600",
        })
        self.assertEqual(by_major["Quản trị Khách sạn"], {
            "thpt": "15", "hoc_ba": "18", "dgnl": "600",
        })
        self.assertTrue(all(fact["status"] == "verified" for fact in evidence.score_facts))

    def test_major_count_includes_adjacent_program_count_only_from_matching_verified_source(self) -> None:
        question = (
            "Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh "
            "đào tạo bao nhiêu ngành đại học chính quy?"
        )
        analysis = analyze_question(question)
        source_text = (
            "Năm 2026, DHV triển khai đào tạo 20 ngành học với hơn 50 chương trình đào\n"
            "tạo, trải rộng trên nhiều lĩnh vực."
        )
        facts = tuple(
            {
                "category": "nganh_dao_tao",
                "major_name": f"Ngành mẫu {index}",
                "major_code": f"700{index:04d}",
                "status": "verified",
            }
            for index in range(1, 21)
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=source_text, metadata={
                "category": "phuong_thuc_xet_tuyen", "record_type": "page_text",
                "status": "verified", "year": 2026, "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
            }),),
            context=source_text,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
            score_facts=facts,
        )
        result = _evidence_catalog_answer(
            analysis, evidence, ConversationState.from_value(None, default_year=2026)
        )
        self.assertIsNotNone(result)
        self.assertIn("20 ngành chính", str(result["answer"]))
        self.assertIn("hơn 50 chương trình đào tạo", str(result["answer"]))

    def test_group_counts_filter_verified_major_catalogue_by_code_family(self) -> None:
        rows = (
            ("Quản trị kinh doanh", "7340101"),
            ("Kinh tế quốc tế", "7310106"),
            ("Marketing", "7340115"),
            ("Thương mại điện tử", "7340122"),
            ("Tài chính ngân hàng", "7340201"),
            ("Kế toán", "7340301"),
            ("Công nghệ tài chính", "7340205"),
            ("Tâm lý học", "7310401"),
            ("Ngôn ngữ Anh", "7220201"),
            ("Ngôn ngữ Nhật", "7220209"),
            ("Ngôn ngữ Trung Quốc", "7220204"),
            ("Ngôn ngữ Hàn Quốc", "7220210"),
            ("Kỹ thuật máy tính", "7480106"),
            ("Trí tuệ nhân tạo", "7480107"),
            ("Công nghệ thông tin", "7480201"),
        )
        facts = tuple(
            {
                "category": "nganh_dao_tao",
                "major_name": name,
                "major_code": code,
                "status": "verified",
            }
            for name, code in rows
        )
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text="Danh mục ngành DHV 2026.", metadata={"year": 2026}),),
            context="Danh mục ngành DHV 2026.",
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
            score_facts=facts,
        )
        expected = {
            "economics": (7, ("Kinh tế quốc tế", "Công nghệ tài chính")),
            "languages": (4, ("Ngôn ngữ Anh", "Ngôn ngữ Hàn Quốc")),
            "technology": (3, ("Kỹ thuật máy tính", "Công nghệ thông tin")),
        }
        for group, (count, included_names) in expected.items():
            with self.subTest(group=group):
                analysis = analyze_question(
                    {
                        "economics": "DHV có bao nhiêu ngành đào tạo nhóm kinh tế?",
                        "languages": "DHV có bao nhiêu ngành đào tạo nhóm ngôn ngữ?",
                        "technology": "DHV có bao nhiêu ngành đào tạo nhóm công nghệ?",
                    }[group]
                )
                result = _evidence_catalog_answer(
                    analysis,
                    evidence,
                    ConversationState.from_value(None, default_year=2026),
                )
                self.assertIsNotNone(result)
                answer = str(result["answer"])
                self.assertIn(f"{count} ngành", answer)
                for name in included_names:
                    self.assertIn(name, answer)
                if group == "economics":
                    self.assertNotIn("Tâm lý học", answer)

    def test_applicant_support_uses_only_verified_disability_policy(self) -> None:
        analysis = analyze_question("Đối với thí sinh khuyết tật, trường có những chính sách hỗ trợ nào?")
        evidence = self._bundle(
            "Nhà trường thực hiện miễn, giảm học phí cho thí sinh thuộc diện khuyết tật."
        )
        answer = _evidence_applicant_support_answer(analysis, evidence)
        self.assertIn("khuyết tật", str(answer))
        self.assertIn("miễn, giảm học phí", str(answer))
        self.assertNotIn("hồ sơ y tế", str(answer))
        self.assertNotIn("can thiệp", str(answer))

    def test_supplementary_application_answer_requires_both_documented_routes(self) -> None:
        analysis = analyze_question("Xét bổ sung em phải đến trường nộp hay đăng ký online được ạ?")
        text = (
            "Thí sinh có thể đăng ký trực tuyến tại cổng thông tin tuyển sinh của Trường, "
            "hoặc nộp hồ sơ trực tiếp tại một trong hai cơ sở của Nhà trường.\n"
            "Cơ sở 1: Số 194 Lê Đức Thọ, TP.HCM.\n"
            "Cơ sở 2: Số 37 Kinh Dương Vương, TP.HCM."
        )
        evidence = self._bundle(text, category="xet_tuyen_bo_sung")
        answer = _evidence_application_registration_answer(analysis, evidence)
        self.assertIn("đăng ký trực tuyến", str(answer))
        self.assertIn("Cơ sở 1", str(answer))
        self.assertIn("Cơ sở 2", str(answer))
        partial = self._bundle(text.splitlines()[0], category="xet_tuyen_bo_sung")
        self.assertIsNone(_evidence_application_registration_answer(analysis, partial))

    def test_result_notification_answer_does_not_invent_contact_channels(self) -> None:
        analysis = analyze_question("Khi trúng tuyển thì trường sẽ thông báo vào đâu ạ?")
        evidence = self._bundle(
            "Thí sinh nhận thư mời nhập học hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. "
            "Thí sinh trúng tuyển phải xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung "
            "của Bộ Giáo dục và Đào tạo. Chi tiết về hồ sơ, thời gian, địa điểm và các bước "
            "nhập học được công bố trên website tuyển sinh www.tuyensinh.dhv.edu.vn.",
            category="ho_so",
        )
        answer = _evidence_result_notification_answer(analysis, evidence)
        self.assertIn("Zalo", str(answer))
        self.assertIn("Hệ thống hỗ trợ xét tuyển chung", str(answer))
        self.assertIn("www.tuyensinh.dhv.edu.vn", str(answer))
        self.assertIn("website tuyển sinh của DHV", str(answer))
        self.assertNotIn("email", str(answer).casefold())
        self.assertNotIn("fanpage", str(answer).casefold())

        without_website = self._bundle(
            "Thí sinh nhận thư mời nhập học hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. "
            "Thí sinh trúng tuyển phải xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung "
            "của Bộ Giáo dục và Đào tạo.",
            category="ho_so",
        )
        answer_without_website = _evidence_result_notification_answer(analysis, without_website)
        self.assertNotIn("tuyensinh.dhv.edu.vn", str(answer_without_website))

    def test_two_admission_dates_are_compared_only_when_both_meanings_are_evidenced(self) -> None:
        question = "Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng ý nghĩa không?"
        analysis = analyze_question(question)
        text = (
            "Tân sinh viên hoàn tất xác nhận trước ngày 13/8/2026 sẽ được hưởng mức ưu đãi cao nhất "
            "theo chính sách hiện hành.\n"
            "Thí sinh trúng tuyển thực hiện xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung "
            "của Bộ Giáo dục và Đào tạo. Thời gian xác nhận nhập học trên cổng Bộ từ ngày 14 tháng "
            "8 năm 2026 đến 17 giờ ngày 21 tháng 8 năm 2026."
        )
        answer = _evidence_date_comparison_answer(analysis, self._bundle(text, category="ho_so"))
        self.assertIn("hai mốc khác nhau", str(answer))
        self.assertIn("13/8/2026", str(answer))
        self.assertIn("21 tháng 8 năm 2026", str(answer))
        self.assertNotIn("UniBridge", str(answer))
        self.assertIsNone(_evidence_date_comparison_answer(analysis, self._bundle(text.splitlines()[0])))

    def test_admission_date_comparison_can_join_verified_facts_across_chunks(self) -> None:
        question = "Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng một ý nghĩa không?"
        analysis = analyze_question(question)
        metadata = {"category": "diem_trung_tuyen", "source_file": "admission.pdf"}
        evidence = EvidenceBundle(
            chunks=(
                EvidenceChunk(
                    text="Tân sinh viên hoàn tất xác nhận trước ngày 13/8/2026 sẽ được hưởng mức ưu đãi cao nhất.",
                    metadata=metadata,
                ),
                EvidenceChunk(
                    text="Thời gian xác nhận nhập học trên cổng Bộ từ ngày 14 tháng 8 năm 2026 đến 17 giờ ngày 21 tháng 8 năm 2026.",
                    metadata=metadata,
                ),
                EvidenceChunk(
                    text="Thí sinh trúng tuyển thực hiện xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung của Bộ Giáo dục và Đào tạo.",
                    metadata=metadata,
                ),
            ),
            context="verified date evidence",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        answer = _evidence_date_comparison_answer(analysis, evidence)
        self.assertIn("hai mốc khác nhau", str(answer))
        self.assertIn("13/08/2026", str(answer))
        self.assertIn("21/08/2026", str(answer))

    def test_named_unit_relation_must_be_supported_in_a_unit_specific_sentence(self) -> None:
        question = "Viện Công nghệ Tiên tiến và Trí tuệ Nhân tạo có đào tạo ngành Trí tuệ nhân tạo không?"
        analysis = analyze_question(question)
        unrelated_major = self._bundle(
            "DHV đào tạo ngành Trí tuệ nhân tạo ở bậc đại học."
        )
        self.assertTrue(_named_unit_relation_missing_evidence(analysis, unrelated_major))
        supported = self._bundle(
            "Viện Công nghệ Tiên tiến và Trí tuệ Nhân tạo đào tạo chương trình Trí tuệ nhân tạo bậc đại học."
        )
        self.assertFalse(_named_unit_relation_missing_evidence(analysis, supported))

    def test_unit_existence_query_is_not_mistaken_for_a_missing_activity_relation(self) -> None:
        analysis = analyze_question("DHV có Viện Đào tạo Sau đại học không?")
        unrelated = self._bundle("DHV có các khoa và viện đào tạo.")
        self.assertFalse(_named_unit_relation_missing_evidence(analysis, unrelated))

    def test_faculty_question_uses_general_faculty_evidence_without_claiming_unique_detail(self) -> None:
        question = (
            "Khoa Ngôn ngữ hợp tác với doanh nghiệp nhằm hỗ trợ sinh viên "
            "trong những hoạt động học tập nào?"
        )
        analysis = analyze_question(question)
        evidence = self._bundle(
            "Các khoa của DHV hợp tác với doanh nghiệp và tổ chức chuyên môn nhằm tạo điều kiện "
            "cho sinh viên kiến tập, thực hành, thực tập và tìm kiếm cơ hội việc làm."
        )
        answer = _evidence_school_info_answer(analysis, evidence)
        self.assertIn("Các khoa của DHV", str(answer))
        self.assertIn("kiến tập, thực hành, thực tập", str(answer))
        self.assertFalse(_named_unit_relation_missing_evidence(analysis, evidence))

    def test_language_faculty_partner_fields_are_returned_as_evidenced(self) -> None:
        question = "Mạng lưới đối tác của Khoa Ngôn ngữ trải rộng ở những nhóm lĩnh vực nào?"
        analysis = analyze_question(question)
        text = (
            "Khoa Ngôn ngữ có các đối tác thuộc lĩnh vực giáo dục, thương mại, tài chính và\n"
            "đào tạo như Glenn College, Woori Bank và nhiều đơn vị khác."
        )
        evidence = self._bundle(text)
        self.assertFalse(_school_info_detail_missing_evidence(analysis, evidence))
        self.assertFalse(_named_unit_relation_missing_evidence(analysis, evidence))
        answer = _evidence_school_info_answer(analysis, evidence)
        self.assertIn("giáo dục, thương mại, tài chính", str(answer))
        self.assertNotIn("xuất nhập khẩu", str(answer))

    def test_explicit_place_count_and_date_constraints_need_matching_school_info(self) -> None:
        cases = (
            (
                "DHV hợp tác với đơn vị nào để mở rộng cơ hội thực tập tại Hoa Kỳ cho sinh viên?",
                "Nhà trường hợp tác với doanh nghiệp để mở rộng cơ hội thực tập cho sinh viên.",
            ),
            (
                "Lễ ký kết với 6 doanh nghiệp ngày 26/06/2026 mang lại cơ hội nào?",
                "Lễ ký kết với doanh nghiệp mang lại cơ hội thực tập cho sinh viên.",
            ),
        )
        for question, text in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "SCHOOL_INFO")
                self.assertTrue(_school_info_detail_missing_evidence(analysis, self._bundle(text)))

    def test_broken_source_url_placeholder_is_removed_not_shown_as_an_address(self) -> None:
        sentence = (
            "Thí sinh xác nhận nhập học trên Hệ thống hỗ trợ xét tuyển chung "
            "của Bộ Giáo dục và Đào tạo tại địa chỉ: và hoàn tất thủ tục theo hướng dẫn DHV."
        )
        cleaned = _remove_unresolved_url_label(sentence)
        self.assertNotIn("địa chỉ:", cleaned)
        self.assertIn("sau đó hoàn tất thủ tục", cleaned)


if __name__ == "__main__":
    unittest.main()
