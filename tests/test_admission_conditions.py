"""Regressions for semantic routing and evidence-grounded admission conditions."""

from __future__ import annotations

import unittest

from src.chatbot.evidence import EvidenceBundle, EvidenceChunk
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.query_decomposer import should_attempt_decomposition
from src.chatbot.output_validator import validate_model_answer
from src.chatbot.rag_chain import (
    _evidence_admission_combination_answer,
    _evidence_application_registration_answer,
    _evidence_eligibility_answer,
    _evidence_law_grade_eligibility_answer,
    _evidence_method_application_threshold_answer,
    _evidence_method_calculation_answer,
    _evidence_scholarship_catalog_answer,
    _method_details_from_evidence,
)


class AdmissionConditionRoutingTests(unittest.TestCase):
    def test_admission_condition_paraphrases_use_verified_conditions_category(self) -> None:
        questions = (
            "Điều kiện xét tuyển DHV năm 2026 là gì?",
            "Muốn vào DHV thì phải đáp ứng gì?",
            "Điều kiện xét tuyển theo học bạ năm 2026 gồm những gì?",
            "H-SCA cần điều kiện gì?",
            "Điều kiện xét tuyển ngành Luật năm 2026 là gì?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")
                self.assertIn("phuong_thuc_xet_tuyen", plan.categories)
                self.assertEqual(analysis.entities.get("issue_intents"), ["HOI_DANG_KY_XET_TUYEN"])

    def test_admission_condition_paraphrase_about_entering_school_is_not_scholarship(self) -> None:
        analysis = analyze_question("Điều kiện vào trường DHV gồm những gì?")
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")
        self.assertTrue(analysis.entities.get("admission_condition_request"))
        self.assertNotIn("hoc_bong", plan.categories)
        self.assertIn("phuong_thuc_xet_tuyen", plan.categories)

    def test_hsca_abbreviation_resolves_to_method_four(self) -> None:
        analysis = analyze_question("H SCA cần điều kiện gì?")
        self.assertEqual(analysis.entities.get("admission_method"), "h_sca")
        self.assertEqual(analysis.intent, "HOI_DANG_KY_XET_TUYEN")

    def test_scholarship_conditions_do_not_get_stolen_by_admission_intent(self) -> None:
        analysis = analyze_question("Học bổng cần điều kiện gì?")
        self.assertEqual(analysis.intent, "HOI_HOC_BONG")

    def test_method_list_question_stays_a_single_method_list_intent(self) -> None:
        analysis = analyze_question("DHV có những cách xét tuyển nào?")
        self.assertEqual(analysis.intent, "HOI_PHUONG_THUC_XET_TUYEN")
        self.assertEqual(analysis.entities.get("issue_intents"), [])
        self.assertEqual(analysis.entities.get("query_mode"), "LIST")

    def test_natural_three_subject_selection_question_requests_combination_details(self) -> None:
        question = "Xét bằng điểm thi tốt nghiệp thì ba môn chọn như thế nào?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_PHUONG_THUC_XET_TUYEN")
        self.assertTrue(analysis.entities.get("admission_combination_detail"))
        self.assertIn("phuong_thuc_xet_tuyen", plan.categories)

    def test_thpt_score_calculation_paraphrases_use_method_formula_source(self) -> None:
        questions = (
            "Xét kết quả kỳ thi tốt nghiệp THPT thì xét điểm như nào?",
            "Thi THPT được tính điểm ra sao?",
            "Điểm của phương thức tốt nghiệp THPT tính thế nào?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_CACH_TINH_DIEM")
                self.assertEqual(analysis.entities.get("admission_method"), "thpt")
                self.assertEqual(
                    analysis.entities.get("requested_information"), ["score_calculation"]
                )
                self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))

    def test_method_specific_dgnl_threshold_paraphrases_route_to_published_evidence(self) -> None:
        for question in (
            "ĐGNL cần bao nhiêu điểm để đăng ký?",
            "Kết quả ĐGNL tối thiểu để đăng ký xét tuyển là mấy?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
                self.assertEqual(analysis.entities.get("admission_method"), "dgnl")
                self.assertEqual(
                    analysis.entities.get("score_type"), "application_threshold"
                )
                self.assertEqual(
                    plan.categories, ("nganh_dao_tao", "nguong_dau_vao")
                )

    def test_personal_scores_with_advice_request_keep_counselling_intent(self) -> None:
        questions = (
            "Tôi thi tốt nghiệp xong, Toán 8, Văn 7, ĐGNL 720, thích edit video nhưng chưa biết chọn ngành nào",
            "Tôi 19 điểm thích edit video nên chọn ngành nào?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "TU_VAN_CHON_NGANH")
                self.assertEqual(analysis.entities.get("score_query_type"), "personal_score_comparison")
                self.assertIn("nganh_dao_tao", plan.categories)

    def test_supplementary_deadline_paraphrase_is_not_enrollment_schedule(self) -> None:
        question = "Thời hạn nộp hồ sơ đợt bổ sung đến khi nào?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
        self.assertEqual(plan.categories, ("xet_tuyen_bo_sung",))

    def test_adding_documents_is_not_misread_as_supplementary_admission(self) -> None:
        analysis = analyze_question("Hồ sơ cần bổ sung giấy tờ nào?")
        self.assertEqual(analysis.intent, "HOI_HO_SO")

    def test_colloquial_major_method_score_question_uses_published_cutoff(self) -> None:
        for question in (
            "CNTT xét học bạ lấy bao nhiêu điểm?",
            "Ngành CNTT học bạ lấy mấy điểm?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_DIEM_TRUNG_TUYEN")
                self.assertEqual(analysis.entities.get("score_type"), "admission_score")
                self.assertEqual(analysis.entities.get("admission_method"), "hoc_ba")
                self.assertEqual(plan.categories, ("diem_trung_tuyen",))


class AdmissionConditionEvidenceAnswerTests(unittest.TestCase):
    def setUp(self) -> None:
        method_page = (
            "1.1.1. Điều kiện xét tuyển\n"
            "Thí sinh đã tốt nghiệp trung học phổ thông hoặc có trình độ tương đương theo quy định của Bộ Giáo dục và Đào tạo được đăng ký xét tuyển vào Trường.\n"
            "Đối với thí sinh dự thi tốt nghiệp THPT từ năm 2026 trở đi, điều kiện chung để tham gia xét tuyển là tổng điểm 03 môn thi tốt nghiệp THPT theo tổ hợp xét tuyển đạt tối thiểu 15,00 điểm (theo thang điểm 30).\n"
            "Riêng đối với các ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng các điều kiện:\n"
            "1. Học lực lớp 12 đạt loại Giỏi trở lên, điểm trung bình môn lớp 12 từ 8,0 trở lên\n"
            "2. Tổng điểm 03 môn thi tốt nghiệp THPT dùng để xét tuyển đạt từ 18 điểm trở lên, trong đó điểm Ngữ văn hoặc Toán từ 6 điểm trở lên\n"
            "1.1.2. Các phương thức xét tuyển năm 2026\n"
            "Các phương thức xét tuyển gồm:\n"
            "a. Xét kết quả kỳ thi tốt nghiệp THPT năm 2026\n"
            "Thí sinh đăng ký xét tuyển dựa trên tổng điểm 03 môn thi tốt nghiệp THPT theo tổ hợp xét tuyển.\n"
            "Tổ hợp xét tuyển được xây dựng theo hai cấu trúc:\n"
            "• Toán + 02 môn có điểm cao nhất trong các môn: Ngữ văn, Ngoại ngữ, Vật lý, Hóa học, Sinh học, Lịch sử, Địa lý, Tin học, Giáo dục kinh tế và pháp luật, Công nghệ công nghiệp.\n"
            "• Ngữ văn + 02 môn có điểm cao nhất trong các môn: Toán, Ngoại ngữ, Vật lý, Hóa học, Sinh học, Lịch sử, Địa lý, Tin học, Giáo dục kinh tế và pháp luật, Công nghệ công nghiệp.\n"
            "b. Xét tuyển kết quả học tập THPT (học bạ)\n"
            "Thí sinh được xét tuyển dựa trên điểm trung bình kết quả học tập của 03 năm THPT (lớp 10, 11, 12) theo một trong hai cách tính:\n"
            "• Tổng điểm tổ hợp 03 môn xét tuyển theo ngành\n"
            "• Toán hoặc Ngữ văn + (điểm trung bình toàn bộ các môn lớp 10, 11, 12) x 2\n"
            "c. Xét kết quả kỳ thi Đánh giá năng lực\n"
            "Thí sinh dùng kết quả kỳ thi năm 2026 do ĐHQG-HCM tổ chức, từ 600 điểm trở lên.\n"
            "d. Xét kết quả bài thi Đánh giá năng lực chuyên biệt (H-SCA)\n"
            "Thí sinh dùng kết quả H-SCA năm 2026 kết hợp với kết quả học tập THPT.\n"
            "e. Xét tuyển đối với thí sinh tốt nghiệp trung cấp\n"
            "Áp dụng với thí sinh tốt nghiệp trung cấp nghề cùng nhóm ngành dự tuyển đại học và hoàn thành chương trình văn hóa THPT theo quy định.\n"
        )
        metadata = {
            "record_type": "page_text",
            "category": "phuong_thuc_xet_tuyen",
            "year": 2026,
            "school_code": "DHV",
            "status": "verified",
            "source_url": "https://tuyensinh.dhv.edu.vn/",
            "source_file": "V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf",
            "document_id": "condition-fixture",
            "page": 3,
            "chunk_index": 0,
        }
        self.evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=method_page, metadata=metadata),),
            context=method_page,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )

    def test_general_answer_preserves_threshold_and_conjunctive_law_exception(self) -> None:
        analysis = analyze_question("Điều kiện xét tuyển DHV năm 2026 là gì?")
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        self.assertIsNotNone(answer)
        self.assertIn("đã tốt nghiệp trung học phổ thông", answer)
        self.assertIn("15,00 điểm", answer)
        self.assertIn("Luật và Luật Kinh tế", answer)
        self.assertIn("đáp ứng đồng thời", answer)
        self.assertIn("18 điểm", answer)
        self.assertIn("Toán từ 6 điểm trở lên", answer)
        self.assertNotIn("18,5", answer)

    def test_natural_paraphrase_uses_semantic_admission_condition_flag(self) -> None:
        analysis = analyze_question("Muốn vào DHV thì cần đáp ứng những gì?")
        self.assertTrue(analysis.entities.get("admission_condition_request"))
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        self.assertIn("15,00 điểm", answer)
        self.assertIn("Luật và Luật Kinh tế", answer)
        self.assertIn("18 điểm", answer)

    def test_law_condition_question_does_not_require_hoc_luc_wording(self) -> None:
        analysis = analyze_question("Điều kiện xét tuyển ngành Luật năm 2026?")
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        self.assertEqual(analysis.entities.get("major_name"), "Luật")
        self.assertIn("điểm trung bình môn lớp 12 từ 8,0 trở lên", answer)
        self.assertIn("đáp ứng đồng thời", answer)

    def test_hoc_ba_question_returns_only_the_requested_method(self) -> None:
        analysis = analyze_question("Điều kiện xét tuyển theo học bạ gồm những gì?")
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        self.assertIn("03 năm THPT (lớp 10, 11, 12)", answer)
        self.assertIn("Tổng điểm tổ hợp 03 môn", answer)
        self.assertIn("điểm trung bình toàn bộ các môn", answer)
        self.assertNotIn("600 điểm", answer)
        self.assertNotIn("học bổng", answer.casefold())

    def test_hoc_ba_calculation_paraphrase_returns_both_three_year_formulas(self) -> None:
        analysis = analyze_question("Học bạ tính điểm cả ba năm như thế nào?")
        answer = _evidence_method_calculation_answer(analysis, self.evidence)
        self.assertEqual(analysis.entities.get("admission_method"), "hoc_ba")
        self.assertIn("lớp 10, 11, 12", answer)
        self.assertIn("Tổng điểm tổ hợp 03 môn", answer)
        self.assertIn("Toán hoặc Ngữ văn", answer)
        self.assertIn("điểm trung bình toàn bộ các môn", answer)

    def test_method_formula_can_be_found_when_retrieval_omits_previous_page_anchor(self) -> None:
        full_text = self.evidence.chunks[0].text
        start = full_text.index("b. Xét tuyển kết quả học tập THPT (học bạ)")
        end = full_text.index("c. Xét kết quả kỳ thi Đánh giá năng lực")
        page_four_text = full_text[start:end]
        metadata = {**self.evidence.chunks[0].metadata, "page": 4}
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=page_four_text, metadata=metadata),),
            context=page_four_text,
            sources=self.evidence.sources,
        )
        analysis = analyze_question("Học bạ tính điểm cả ba năm như thế nào?")
        answer = _evidence_method_calculation_answer(analysis, evidence)
        self.assertIn("lớp 10, 11, 12", answer)
        self.assertIn("Tổng điểm tổ hợp 03 môn", answer)

    def test_scholarship_method_formula_is_not_misread_as_admission_formula(self) -> None:
        text = "c. Xét học bạ THPT ĐTB 3 năm THPT (10,11,12) theo công thức: Toán hoặc Văn + (ĐTB cả năm lớp 10 + 11 + 12) × 2"
        metadata = {**self.evidence.chunks[0].metadata, "page": 6}
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=self.evidence.sources,
        )
        analysis = analyze_question("Học bạ tính điểm cả ba năm như thế nào?")
        self.assertIsNone(_evidence_method_calculation_answer(analysis, evidence))

    def test_hsca_question_does_not_inherit_another_methods_score(self) -> None:
        analysis = analyze_question("H-SCA cần điều kiện gì?")
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        self.assertIn("H-SCA năm 2026", answer)
        self.assertIn("kết hợp với kết quả học tập THPT", answer)
        self.assertNotIn("600 điểm", answer)

    def test_all_method_conditions_can_be_listed_from_page_evidence(self) -> None:
        analysis = analyze_question("Điều kiện của từng phương thức xét tuyển DHV là gì?")
        answer = _evidence_eligibility_answer(analysis, self.evidence)
        for label in ("Thi tốt nghiệp THPT", "Học bạ THPT", "ĐGNL", "H-SCA", "Tốt nghiệp trung cấp"):
            self.assertIn(label, answer)

    def test_method_conditions_support_numbered_2026_source_headings(self) -> None:
        text = (
            "2 Các phương thức xét tuyển năm 2026\n"
            "2.1 Xét kết quả kỳ thi tốt nghiệp THPT năm 2026\n"
            "Thí sinh đăng ký dựa trên tổng điểm 03 môn thi tốt nghiệp THPT.\n"
            "2.2 Xét tuyển kết quả học tập THPT (học bạ)\n"
            "Xét điểm trung bình kết quả học tập của 03 năm THPT.\n"
            "2.3 Xét kết quả kỳ thi Đánh giá năng lực\n"
            "Sử dụng kết quả kỳ thi Đánh giá năng lực năm 2026 từ 600 điểm trở lên.\n"
            "2.4 Xét kết quả bài thi Đánh giá năng lực chuyên biệt (H-SCA)\n"
            "Kết hợp kết quả H-SCA với kết quả học tập THPT.\n"
            "2.5 Xét tuyển đối với thí sinh tốt nghiệp trung cấp\n"
            "Tốt nghiệp trung cấp nghề cùng nhóm ngành và hoàn thành chương trình văn hóa THPT.\n"
        )
        metadata = dict(self.evidence.chunks[0].metadata)
        numbered_evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=self.evidence.sources,
        )
        analysis = analyze_question("Điều kiện của 5 phương thức xét tuyển DHV là gì?")
        answer = _evidence_eligibility_answer(analysis, numbered_evidence)

        self.assertIsNotNone(answer)
        for detail in (
            "tổng điểm 03 môn thi tốt nghiệp THPT",
            "03 năm THPT",
            "600 điểm trở lên",
            "kết quả học tập THPT",
            "tốt nghiệp trung cấp nghề cùng nhóm ngành",
        ):
            with self.subTest(detail=detail):
                self.assertIn(detail.casefold(), answer.casefold())

    def test_method_details_keep_repeated_bullet_endings_and_do_not_misattribute(self) -> None:
        details = _method_details_from_evidence(self.evidence, target_year=2026)
        self.assertIn("Ngữ văn + 02 môn", details[1])
        self.assertGreaterEqual(details[1].count("Công nghệ công nghiệp."), 2)
        self.assertNotIn("được thiết kế linh hoạt", details[1])
        self.assertNotIn("Khối công nghệ", details[5])
        self.assertIn("cùng nhóm ngành", details[5])

    def test_three_subject_selection_answer_strips_bullets_and_returns_both_rules(self) -> None:
        question = "Xét bằng điểm thi tốt nghiệp thì ba môn chọn như thế nào?"
        analysis = analyze_question(question)
        text = (
            "• Toán + 02 môn có điểm cao nhất trong các môn: Ngữ văn, Ngoại ngữ, Vật lý, Hóa học.\n"
            "• Ngữ văn + 02 môn có điểm cao nhất trong các môn: Toán, Ngoại ngữ, Vật lý, Hóa học.\n"
            "Các tổ hợp xét tuyển được thiết kế linh hoạt."
        )
        metadata = {**self.evidence.chunks[0].metadata, "page": 4}
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=self.evidence.sources,
        )
        answer = _evidence_admission_combination_answer(analysis, evidence)
        self.assertIn("Toán + 02 môn có điểm cao nhất", answer)
        self.assertIn("Ngữ văn + 02 môn có điểm cao nhất", answer)

    def test_dgnl_threshold_is_read_only_from_verified_method_section(self) -> None:
        text = (
            "c. Xét kết quả kỳ thi Đánh giá năng lực\n"
            "Thí sinh dùng kết quả kỳ thi năm 2026 do ĐHQG-HCM tổ chức, từ 600 điểm trở lên.\n"
            "d. Xét kết quả bài thi Đánh giá năng lực chuyên biệt (H-SCA)\n"
            "Thí sinh dùng kết quả H-SCA năm 2026 kết hợp với kết quả học tập THPT."
        )
        metadata = {**self.evidence.chunks[0].metadata, "page": 4}
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=self.evidence.sources,
            score_facts=(
                {
                    "score_type": "application_threshold", "method": "dgnl",
                    "raw_value": "600", "category": "nguong_dau_vao",
                    "status": "verified", "school_code": "DHV", "year": 2026,
                },
            ),
        )
        analysis = analyze_question("ĐGNL cần bao nhiêu điểm để đăng ký?")
        answer = _evidence_method_application_threshold_answer(analysis, evidence)
        self.assertIn("600 điểm trở lên", answer)

    def test_personal_score_question_is_not_replaced_by_generic_method_floor(self) -> None:
        analysis = analyze_question("Em được 720 ĐGNL có đậu không?")
        self.assertIsNone(
            _evidence_method_application_threshold_answer(analysis, self.evidence)
        )

    def test_hsca_threshold_question_never_borrows_dgnl_score(self) -> None:
        analysis = analyze_question("H-SCA cần bao nhiêu điểm để đăng ký?")
        evidence = self.evidence
        answer = _evidence_method_application_threshold_answer(analysis, evidence)
        self.assertIsNone(answer)

    def test_unverified_or_wrong_year_condition_chunk_is_not_used(self) -> None:
        chunk = self.evidence.chunks[0]
        for key, value in (("status", "unverified"), ("year", 2025), ("school_code", "OTHER")):
            with self.subTest(key=key):
                metadata = {**chunk.metadata, key: value}
                evidence = EvidenceBundle(
                    chunks=(EvidenceChunk(text=chunk.text, metadata=metadata),),
                    context=chunk.text,
                    sources=(),
                )
                analysis = analyze_question("Điều kiện xét tuyển DHV năm 2026 là gì?")
                self.assertIsNone(_evidence_eligibility_answer(analysis, evidence))

    def test_supplementary_receipt_timing_is_one_issue_and_uses_its_source(self) -> None:
        question = "Khi nào có xét tuyển bổ sung và nhận hồ sơ?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
        self.assertFalse(should_attempt_decomposition(analysis, plan))
        text = (
            "Thí sinh có thể đăng ký trực tuyến tại cổng thông tin tuyển sinh "
            "www.tuyensinh.dhv.edu.vn hoặc nộp hồ sơ trực tiếp tại một trong hai cơ sở của Nhà trường.\n"
            "• Cơ sở 1: 194 Lê Đức Thọ, phường An Nhơn, TP.HCM.\n"
            "• Cơ sở 2: 37 Kinh Dương Vương, phường Phú Lâm, TP.HCM.\n"
            "Thời gian nhận hồ sơ đến hết ngày 21/8/2026."
        )
        metadata = {
            "record_type": "page_text", "category": "xet_tuyen_bo_sung", "year": 2026,
            "school_code": "DHV", "status": "verified", "source_url": "https://dhv.edu.vn/dhv-nhan-ho-so-xet-tuyen-bo-sung/",
        }
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=({"url": "https://dhv.edu.vn/dhv-nhan-ho-so-xet-tuyen-bo-sung/"},),
            score_facts=(
                {"score_type": "supplementary_threshold", "method": "deadline", "raw_value": "21/8/2026", "status": "verified", "year": 2026},
                {"score_type": "supplementary_threshold", "method": "thpt", "raw_value": "15", "status": "verified", "year": 2026},
                {"score_type": "supplementary_threshold", "method": "hoc_ba", "raw_value": "18", "status": "verified", "year": 2026},
            ),
        )
        answer = _evidence_application_registration_answer(analysis, evidence)
        self.assertIn("Cơ sở 1", answer)
        self.assertIn("Cơ sở 2", answer)
        self.assertIn("21/8/2026", answer)
        validated = validate_model_answer(answer, evidence, question=question, analysis=analysis, target_year=2026)
        self.assertEqual(validated.get("status"), "ok")

    def test_supplementary_deadline_paraphrase_includes_date_from_page_text(self) -> None:
        question = "Thời hạn nộp hồ sơ đợt bổ sung đến khi nào?"
        analysis = analyze_question(question)
        text = (
            "Thí sinh có thể đăng ký trực tuyến tại cổng thông tin tuyển sinh www.tuyensinh.dhv.edu.vn "
            "hoặc nộp hồ sơ trực tiếp tại một trong hai cơ sở của Nhà trường.\n"
            "1. Cơ sở 1: 194 Lê Đức Thọ, TP.HCM.\n"
            "2. Cơ sở 2: 37 Kinh Dương Vương, TP.HCM.\n"
            "Thời gian nhận hồ sơ đến hết ngày 21/8/2026."
        )
        metadata = {
            "record_type": "page_text", "category": "xet_tuyen_bo_sung", "year": 2026,
            "school_code": "DHV", "status": "verified",
            "source_url": "https://dhv.edu.vn/dhv-nhan-ho-so-xet-tuyen-bo-sung/",
        }
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),), context=text,
            sources=({"url": "https://dhv.edu.vn/dhv-nhan-ho-so-xet-tuyen-bo-sung/"},),
        )
        answer = _evidence_application_registration_answer(analysis, evidence)
        self.assertIn("21/8/2026", answer)
        self.assertEqual(
            validate_model_answer(answer, evidence, question=question, analysis=analysis, target_year=2026).get("status"),
            "ok",
        )

    def test_law_known_grade_answers_decisive_condition_without_method_clarification(self) -> None:
        question = "Học lực lớp 12 Khá, 20 điểm thì đủ xét ngành Luật không?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertFalse(plan.needs_clarification)
        self.assertIn("phuong_thuc_xet_tuyen", plan.categories)
        answer = _evidence_law_grade_eligibility_answer(analysis, self.evidence)
        self.assertIn("chưa đáp ứng", answer)
        self.assertIn("Giỏi trở lên", answer)
        self.assertIn("18 điểm trở lên", answer)

    def test_scholarship_list_uses_unique_verified_section_headings(self) -> None:
        analysis = analyze_question("DHV có những học bổng nào?")
        self.assertEqual(analysis.intent, "HOI_HOC_BONG")
        metadata = {
            "record_type": "page_text", "category": "phuong_thuc_xet_tuyen", "year": 2026,
            "school_code": "DHV", "status": "verified", "source_url": "https://tuyensinh.dhv.edu.vn/",
        }
        text = (
            "1.3. Chính sách học bổng Hào khí Hùng Vương dành cho tân sinh viên\n"
            "1.4. Học bổng tuyển sinh\n"
            "1.5. Học bổng Tài năng\n"
            "1.6. Học bổng Ngành Tiên phong"
        )
        duplicate = "1.6. Học bổng Ngành Tiên phong\n"
        evidence = EvidenceBundle(
            chunks=(
                EvidenceChunk(text=text, metadata=metadata),
                EvidenceChunk(text=duplicate, metadata={**metadata, "page": 6}),
            ),
            context=text + "\n" + duplicate,
            sources=({"url": "https://tuyensinh.dhv.edu.vn/"},),
        )
        answer = _evidence_scholarship_catalog_answer(analysis, evidence)
        self.assertEqual(answer.count("Học bổng Ngành Tiên phong"), 1)
        self.assertIn("Hào khí Hùng Vương", answer)
        self.assertIn("Học bổng Tài năng", answer)
        self.assertNotIn("UniBridge", answer)

    def test_program_parent_relation_does_not_prove_personal_interest_fit(self) -> None:
        question = "Tôi thích edit video nên chọn ngành nào?"
        analysis = analyze_question(question)
        text = "Truyền thông đa phương tiện là chương trình thuộc ngành Công nghệ thông tin."
        metadata = {
            "record_type": "page_text",
            "category": "nganh_dao_tao",
            "year": 2026,
            "school_code": "DHV",
            "status": "verified",
            "source_url": "https://dhv.edu.vn/",
        }
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(text=text, metadata=metadata),),
            context=text,
            sources=({"url": "https://dhv.edu.vn/"},),
        )

        unsupported_answers = (
            "Với sở thích edit video, mình nghiêng về Truyền thông đa phương tiện hơn. "
            "Đây là chương trình thuộc ngành Công nghệ thông tin.",
            "Với sở thích edit video, Truyền thông đa phương tiện là chương trình "
            "thuộc ngành Công nghệ thông tin.",
        )
        for answer in unsupported_answers:
            with self.subTest(answer=answer):
                result = validate_model_answer(
                    answer,
                    evidence,
                    question=question,
                    analysis=analysis,
                    target_year=2026,
                )

                self.assertEqual(result["status"], "no_data")
                self.assertEqual(result.get("_validation_reason"), "unsupported_advisory_fit")


if __name__ == "__main__":
    unittest.main()
