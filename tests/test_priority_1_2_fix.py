"""Targeted regressions for SEC-001, CORE-001 and STATE-001."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import sanitize_answer, validate_model_answer
from src.chatbot.query_analysis import (
    ConversationState,
    analyze_question,
    route_question,
    should_inherit_context,
    update_conversation_state,
)
from src.chatbot.rag_chain import ask_chatbot


SOURCE_URL = "https://dhv.edu.vn/priority-1-2-fix"


class _RecordingRetriever:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents = documents or []
        self.calls = 0

    def retrieve_with_audit(self, question: str, *, categories: tuple[str, ...], retrieval_query: str, **_: object) -> dict[str, object]:
        del question, categories, retrieval_query
        self.calls += 1
        return {"documents": list(self.documents)}


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError(f"unexpected LLM call: {prompt[:80]}")


class ExternalSchoolBoundaryTests(unittest.TestCase):
    def test_validator_strips_unsafe_link_targets_and_rejects_unsupported_channels(self) -> None:
        self.assertEqual(
            sanitize_answer("Xem [Fanpage](#) hoặc [trang lạ](javascript:alert(1))."),
            "Xem Fanpage hoặc trang lạ.",
        )
        evidence = build_evidence(
            [
                Document(
                    page_content="Học bổng DHV 2026 lên đến 75 tỷ đồng.",
                    metadata={
                        "title": "Học bổng DHV",
                        "category": "hoc_bong",
                        "year": 2026,
                        "school_code": "DHV",
                        "source_url": SOURCE_URL,
                        "status": "verified",
                        "chunk_id": "priority-1-2-scholarship-channel",
                    },
                )
            ]
        )
        result = validate_model_answer(
            "Học bổng DHV lên đến 75 tỷ đồng. Xem Fanpage [tại đây](#).",
            evidence,
            question="DHV có học bổng nào?",
            analysis={"intent": "HOI_HOC_BONG", "entities": {"target_school": "DHV"}},
        )
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "unsupported_contact_channel")

    def test_sanitizer_keeps_only_exact_verified_contact_markdown_links(self) -> None:
        verified_url = "https://www.tiktok.com/@dhv.official"
        answer = sanitize_answer(
            f"**Kênh chính thức:** [TikTok]({verified_url}) · [Facebook](https://evil.example/page)",
            allowed_urls=(verified_url,),
        )
        self.assertEqual(answer, f"**Kênh chính thức:** [TikTok]({verified_url}) · Facebook")

    def test_generic_external_school_matrix_never_retrieves(self) -> None:
        questions = (
            "Điểm chuẩn trường đại học khác?",
            "Điểm chuẩn đại học khác?",
            "Điểm chuẩn trường khác?",
            "Học phí trường khác?",
            "Trường khác có học bổng không?",
            "Đại học khác có xét học bạ không?",
            "diem chuan truong dai hoc khac?",
            "hoc phi truong khac?",
            "Trường ĐH khác có xét học bạ không?",
            "Trường cao đẳng khác có học bổng không?",
            "Học viện khác có xét tuyển không?",
        )
        for question in questions:
            with self.subTest(question=question):
                retriever = _RecordingRetriever(
                    [
                        Document(
                            page_content="DHV factual data must never be used here: 15 điểm.",
                            metadata={"school_code": "DHV"},
                        )
                    ]
                )
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], "OTHER_SCHOOL")
                self.assertEqual(analysis.entities["scope_reason"], "external_school")
                result = ask_chatbot(
                    question,
                    retriever=retriever,
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(retriever.calls, 0)
                self.assertEqual(result["trace"]["retrieval_calls"], 0)
                self.assertEqual(result["trace"]["retrieved_chunks"], 0)
                self.assertEqual(result["trace"]["evidence_count"], 0)
                self.assertEqual(result["status"], "out_of_scope")
                self.assertNotIn("15", str(result["answer"]))

    def test_generic_external_marker_does_not_false_positive_generic_dhv(self) -> None:
        for question in (
            "Điểm chuẩn CNTT?",
            "Trường có những ngành nào?",
            "Học phí của trường bao nhiêu?",
            "Trường xét tuyển bằng phương thức nào?",
            "Điểm chuẩn của trường năm 2026?",
        ):
            with self.subTest(question=question):
                retriever = _RecordingRetriever()
                analysis = analyze_question(question)
                self.assertIn(
                    analysis.entities["target_school"],
                    {"UNSPECIFIED", "DHV"},
                )
                result = ask_chatbot(
                    question,
                    retriever=retriever,
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(retriever.calls, 1)
                self.assertGreater(result["trace"]["retrieval_calls"], 0)

    def test_generic_external_marker_mixes_with_explicit_dhv(self) -> None:
        retriever = _RecordingRetriever()
        question = "So sánh DHV với trường đại học khác"
        analysis = analyze_question(question)
        self.assertEqual(analysis.entities["target_school"], "MIXED")
        result = ask_chatbot(
            question,
            retriever=retriever,
            llm=_NeverCalledLLM(),
        )
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["retrieval_calls"], 0)
        self.assertEqual(result["trace"]["evidence_count"], 0)

    def test_generic_external_school_overrides_previous_dhv_state(self) -> None:
        first = ask_chatbot(
            "Điểm chuẩn CNTT?",
            retriever=_RecordingRetriever(),
            llm=_NeverCalledLLM(),
        )
        retriever = _RecordingRetriever()
        result = ask_chatbot(
            "Còn trường khác?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
            conversation_state=first["state"],
        )
        self.assertEqual(result["trace"]["entities"]["target_school"], "OTHER_SCHOOL")
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["retrieval_calls"], 0)

    def test_generic_external_school_overrides_previous_external_state(self) -> None:
        first = ask_chatbot(
            "Văn Hiến có xét học bạ không?",
            retriever=_RecordingRetriever(),
            llm=_NeverCalledLLM(),
        )
        retriever = _RecordingRetriever()
        result = ask_chatbot(
            "Còn trường khác?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
            conversation_state=first["state"],
        )
        self.assertEqual(result["trace"]["entities"]["target_school"], "OTHER_SCHOOL")
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["evidence_count"], 0)

    def test_named_external_school_matrix_never_retrieves(self) -> None:
        questions = (
            "Điểm chuẩn Văn Hiến?",
            "Học phí Hoa Sen?",
            "Văn Lang có học bổng không?",
            "Nguyễn Tất Thành có xét học bạ không?",
            "Điểm chuẩn Bách Khoa?",
            "diem chuan bach khoa?",
        )
        for question in questions:
            with self.subTest(question=question):
                retriever = _RecordingRetriever()
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], "OTHER_SCHOOL")
                result = ask_chatbot(
                    question,
                    retriever=retriever,
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(retriever.calls, 0)
                self.assertEqual(result["trace"]["retrieval_calls"], 0)
                self.assertEqual(result["trace"]["retrieved_chunks"], 0)
                self.assertEqual(result["trace"]["evidence_count"], 0)
                self.assertNotIn("15", str(result["answer"]))
                self.assertNotIn("600", str(result["answer"]))

    def test_mixed_school_is_a_zero_retrieval_boundary(self) -> None:
        retriever = _RecordingRetriever()
        analysis = analyze_question("So sánh DHV và Văn Hiến")
        self.assertEqual(analysis.entities["target_school"], "MIXED")
        result = ask_chatbot(
            "So sánh DHV và Văn Hiến",
            retriever=retriever,
            llm=_NeverCalledLLM(),
        )
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["retrieval_calls"], 0)
        self.assertEqual(result["trace"]["retrieved_chunks"], 0)
        self.assertEqual(result["trace"]["evidence_count"], 0)

    def test_coequal_dhv_and_external_school_fact_query_is_mixed(self) -> None:
        question = "DHV và Đại học FPT có bao nhiêu website?"
        retriever = _RecordingRetriever()
        analysis = analyze_question(question)

        self.assertEqual(analysis.entities["target_school"], "MIXED")
        result = ask_chatbot(question, retriever=retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["scope_reason"], "mixed_school")
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(result["trace"]["retrieval_calls"], 0)
        self.assertEqual(result["trace"]["evidence_count"], 0)

    def test_external_institution_as_dhv_relationship_object_stays_dhv(self) -> None:
        for question in (
            "DHV có hợp tác với Đại học FPT không?",
            "DHV có kết nối và giao lưu với các trường khác không?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], "DHV")

    def test_default_dhv_and_unspecified_queries_still_retrieve(self) -> None:
        for question, expected_target in (
            ("Điểm chuẩn DHV CNTT?", "DHV"),
            ("Điểm chuẩn CNTT?", "UNSPECIFIED"),
        ):
            with self.subTest(question=question):
                retriever = _RecordingRetriever()
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], expected_target)
                result = ask_chatbot(
                    question,
                    retriever=retriever,
                    llm=_NeverCalledLLM(),
                )
                self.assertEqual(retriever.calls, 1)
                self.assertNotEqual(result["trace"]["retrieval_calls"], 0)

    def test_external_school_state_is_kept_and_explicit_dhv_overrides(self) -> None:
        retriever = _RecordingRetriever()
        first = ask_chatbot(
            "Văn Hiến có xét học bạ không?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
        )
        second = ask_chatbot(
            "Còn điểm chuẩn?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
            conversation_state=first["state"],
        )
        self.assertEqual(retriever.calls, 0)
        self.assertEqual(second["trace"]["entities"]["target_school"], "OTHER_SCHOOL")
        third = ask_chatbot(
            "Còn DHV thì sao?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
            conversation_state=second["state"],
        )
        self.assertEqual(third["trace"]["entities"]["target_school"], "DHV")
        self.assertEqual(retriever.calls, 1)

    def test_validator_rejects_external_scope_even_with_dhv_evidence(self) -> None:
        evidence = build_evidence(
            [
                Document(
                    page_content="Điểm chuẩn DHV: THPT 15 điểm, ĐGNL 600 điểm.",
                    metadata={
                        "title": "verified score",
                        "category": "diem_trung_tuyen",
                        "year": 2026,
                        "school_code": "DHV",
                        "source_url": SOURCE_URL,
                        "status": "verified",
                        "chunk_id": "priority-1-2-score",
                    },
                )
            ]
        )
        result = validate_model_answer(
            "Điểm chuẩn là 15 điểm.",
            evidence,
            question="Điểm chuẩn Bách Khoa?",
            analysis={
                "entities": {
                    "target_school": "OTHER_SCHOOL",
                    "scope_reason": "external_school",
                }
            },
        )
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "school_scope_boundary")

    def test_validator_rejects_unverified_external_partner_with_or_without_accents(self) -> None:
        evidence = build_evidence(
            [
                Document(
                    page_content=(
                        "DHV có hợp tác với các trường đại học quốc tế theo các thỏa thuận chung."
                    ),
                    metadata={
                        "title": "Thông tin hợp tác DHV",
                        "category": "thong_tin_truong",
                        "year": 2026,
                        "school_code": "DHV",
                        "source_url": SOURCE_URL,
                        "status": "verified",
                        "chunk_id": "priority-1-2-generic-partnership",
                    },
                )
            ]
        )

        for answer in (
            "DHV hợp tác với Đại học FPT.",
            "DHV hop tac voi Dai hoc FPT.",
        ):
            with self.subTest(answer=answer):
                result = validate_model_answer(
                    answer,
                    evidence,
                    question="DHV có hợp tác với Đại học FPT không?",
                    analysis={
                        "intent": "SCHOOL_INFO",
                        "entities": {
                            "target_school": "DHV",
                            "scope_reason": "in_scope_dhv",
                        },
                    },
                )
                self.assertEqual(result["status"], "no_data")
                self.assertEqual(result["_validation_reason"], "institution_mismatch")


class ConfirmedHighSweepFailureTests(unittest.TestCase):
    def test_vocational_same_group_question_uses_verified_method_five_without_llm(self) -> None:
        question = "Thí sinh tốt nghiệp trung cấp cùng nhóm ngành có thể vào DHV không?"
        source_text = (
            "1.7. Xét tuyển đối với thí sinh tốt nghiệp trung cấp\n"
            "Áp dụng cho thí sinh đã tốt nghiệp trung cấp nghề cùng nhóm ngành dự tuyển đại học "
            "và đã hoàn thành chương trình văn hóa THPT theo quy định."
        )
        document = Document(
            page_content=source_text,
            metadata={
                "title": "Phương thức xét tuyển DHV 2026",
                "category": "phuong_thuc_xet_tuyen",
                "record_type": "page_text",
                "page": 5,
                "year": 2026,
                "school_code": "DHV",
                "source_url": "https://tuyensinh.dhv.edu.vn/",
                "status": "verified",
                "chunk_id": "verified-method-5-vocational-condition",
            },
        )
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertIn("trung cap nghe cung nhom nganh", plan.retrieval_query)
        self.assertIn("phuong_thuc_xet_tuyen", plan.categories)

        retriever = _RecordingRetriever([document])
        result = ask_chatbot(question, retriever=retriever, llm=_NeverCalledLLM())

        self.assertEqual(retriever.calls, 1)
        self.assertEqual(result["status"], "ok", msg=str(result.get("trace")))
        self.assertIn("đã hoàn thành chương trình văn hóa THPT", result["answer"])
        self.assertNotIn("Đại học Sư phạm TP.HCM", result["answer"])
        self.assertNotIn("H-SCA", result["answer"])


class CoreferenceAndStateTests(unittest.TestCase):
    def test_major_list_reference_resolves_whole_list(self) -> None:
        state = ConversationState(
            last_listed_majors=("Công nghệ thông tin", "Marketing"),
            last_list_count=2,
            previous_intent="DANH_SACH_NGANH",
        )
        analysis = analyze_question("Điểm sàn các ngành nêu trên?", state)
        plan = route_question(analysis, state)
        self.assertEqual(analysis.entities["candidate_majors"], ["Công nghệ thông tin", "Marketing"])
        self.assertIsNone(analysis.entities["major_name"])
        self.assertEqual(plan.entity_filters["candidate_majors"], ["Công nghệ thông tin", "Marketing"])

    def test_single_major_reference_resolves_previous_entity(self) -> None:
        state = ConversationState(
            current_major="Công nghệ thông tin",
            previous_intent="HOI_NGANH",
        )
        analysis = analyze_question("Điểm chuẩn ngành đó?", state)
        self.assertEqual(analysis.entities["major_name"], "Công nghệ thông tin")
        self.assertEqual(analysis.entities["entity_type"], "major")

    def test_program_ordinal_preserves_program_type_and_parent(self) -> None:
        state = ConversationState(
            last_listed_programs=("Digital Marketing", "Truyền thông số"),
            last_listed_program_parents=("Marketing", "Marketing"),
            previous_intent="DANH_SACH_CHUONG_TRINH",
        )
        analysis = analyze_question("Chương trình thứ hai học gì?", state)
        self.assertEqual(analysis.entities["program_name"], "Truyền thông số")
        self.assertEqual(analysis.entities["parent_major"], "Marketing")
        self.assertEqual(analysis.entities["entity_type"], "program")
        self.assertIsNone(analysis.entities["major_name"])

    def test_method_ordinal_resolves_ordered_method_list(self) -> None:
        state = ConversationState(
            last_listed_methods=("hoc_ba", "dgnl"),
            previous_intent="HOI_PHUONG_THUC_XET_TUYEN",
        )
        analysis = analyze_question("Phương thức thứ hai cần bao nhiêu điểm?", state)
        self.assertEqual(analysis.entities["admission_method"], "dgnl")
        self.assertEqual(analysis.entities["score_type"], "application_threshold")
        self.assertEqual(analysis.entities["entity_type"], "method")

    def test_multiple_methods_are_saved_in_mention_order(self) -> None:
        analysis = analyze_question("DHV có xét học bạ và ĐGNL")
        state = update_conversation_state({}, analysis)
        self.assertEqual(state.last_listed_methods, ("hoc_ba", "dgnl"))

    def test_ambiguous_reference_requires_clarification(self) -> None:
        state = ConversationState(
            last_listed_majors=("Công nghệ thông tin", "Marketing"),
            previous_intent="DANH_SACH_NGANH",
        )
        analysis = analyze_question("Còn cái kia?", state)
        plan = route_question(analysis, state)
        self.assertTrue(analysis.entities["coreference_ambiguous"])
        self.assertTrue(plan.needs_clarification)

    def test_tuition_followup_inherits_major_but_generic_tuition_does_not(self) -> None:
        first_analysis = analyze_question("Điểm chuẩn CNTT?")
        state = update_conversation_state({}, first_analysis)

        followup = analyze_question("Còn học phí?", state)
        followup_plan = route_question(followup, state)
        self.assertTrue(
            should_inherit_context(
                followup.normalized_question,
                followup.intent,
                state.previous_intent,
                state,
            )
        )
        # The prior major remains conversational context, but tuition in this
        # corpus is school-level. Do not push an inherited major filter into
        # retrieval and accidentally hide the verified general tuition rows.
        self.assertNotIn("major_name", followup_plan.entity_filters)
        self.assertEqual(state.current_major, "Công nghệ thông tin")

        generic = analyze_question("Học phí của trường bao nhiêu?", state)
        generic_plan = route_question(generic, state)
        self.assertFalse(
            should_inherit_context(
                generic.normalized_question,
                generic.intent,
                state.previous_intent,
                state,
            )
        )
        self.assertNotIn("major_name", generic_plan.entity_filters)

    def test_explicit_major_overrides_previous_major(self) -> None:
        state = update_conversation_state({}, analyze_question("Điểm chuẩn CNTT?"))
        analysis = analyze_question("Còn Luật?", state)
        plan = route_question(analysis, state)
        self.assertEqual(plan.entity_filters["major_name"], "Luật")

    def test_greeting_and_thanks_do_not_reopen_stale_school_scope(self) -> None:
        first = ask_chatbot(
            "Văn Hiến điểm chuẩn bao nhiêu?",
            retriever=_RecordingRetriever(),
            llm=_NeverCalledLLM(),
        )
        for question, intent in (("Xin chào", "GREETING"), ("Cảm ơn", "THANKS")):
            with self.subTest(question=question):
                result = ask_chatbot(
                    question,
                    retriever=_RecordingRetriever(),
                    llm=_NeverCalledLLM(),
                    conversation_state=first["state"],
                )
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["trace"]["intent"], intent)
                self.assertEqual(result["trace"]["retrieval_calls"], 0)
                self.assertNotIn("không thể xác nhận thông tin tuyển sinh của trường khác", result["answer"])


if __name__ == "__main__":
    unittest.main()
