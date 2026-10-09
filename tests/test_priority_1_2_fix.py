"""Targeted regressions for SEC-001, CORE-001 and STATE-001."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import validate_model_answer
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
