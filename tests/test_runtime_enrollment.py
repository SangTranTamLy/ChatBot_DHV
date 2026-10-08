"""Regression coverage for verified enrollment data reaching the runtime RAG path."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import ConversationState, analyze_question, route_question
from src.chatbot.scope_guard import is_in_scope
from src.retrieval.retriever import RetrievalAudit, RetrievalResult


SOURCE_URL = "https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026/"


def _enrollment_document(record_id: str, text: str) -> Document:
    return Document(
        page_content=f"Hồ sơ nhập học DHV 2026\nHồ sơ nhập học: {text}",
        metadata={
            "title": "Hồ sơ nhập học DHV 2026",
            "category": "ho_so",
            "year": 2026,
            "school_code": "DHV",
            "source_url": SOURCE_URL,
            "source_file": "data/raw/ho_so/HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf",
            "status": "verified",
            "record_type": "enrollment_document",
            "structured_record_id": record_id,
            "chunk_id": f"test-{record_id}",
            "page": 3,
        },
    )


class FixtureRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.calls: list[dict[str, object]] = []

    def retrieve_with_audit(self, question: str, **kwargs: object) -> RetrievalResult:
        self.calls.append({"question": question, **kwargs})
        return RetrievalResult(
            documents=tuple(self.documents),
            audit=RetrievalAudit(
                query=question,
                normalized_query=question.casefold(),
                metadata_filter={"year": 2026, "category": "ho_so"},
                top_k=int(kwargs.get("top_k") or 4),
                hits=tuple(
                    {
                        "rank": index,
                        "category": document.metadata.get("category"),
                        "chunk_id": document.metadata.get("chunk_id"),
                    }
                    for index, document in enumerate(self.documents, start=1)
                ),
            ),
        )


class RuntimeEnrollmentTests(unittest.TestCase):
    def test_enrollment_semantic_alias_routes_to_verified_category(self) -> None:
        analysis = analyze_question("Nhập học cần những gì", ConversationState())
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_NHAP_HOC")
        self.assertEqual(plan.categories, ("ho_so", "nhap_hoc"))

    def test_enrollment_question_uses_evidence_without_model_generation(self) -> None:
        retriever = FixtureRetriever(
            [
                _enrollment_document("enrollment_document_008", "Học bạ THPT."),
                _enrollment_document(
                    "enrollment_document_009", "Căn cước/Căn cước công dân."
                ),
            ]
        )
        result = ask_chatbot("nhập học cần những gì", retriever=retriever)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["retrieval_calls"], 1)
        self.assertGreater(result["trace"]["evidence_count"], 0)
        self.assertIn("Học bạ THPT", str(result["answer"]))
        self.assertIn("Căn cước", str(result["answer"]))

    def test_enrollment_related_terms_are_in_scope(self) -> None:
        self.assertTrue(is_in_scope("Tân sinh viên cần chuẩn bị gì?"))
        self.assertTrue(is_in_scope("Học liệu điện tử bao nhiêu?"))

    def test_enrollment_followup_keeps_topic_scope_without_major_slot(self) -> None:
        retriever = FixtureRetriever(
            [_enrollment_document("enrollment_document_009", "Căn cước/Căn cước công dân.")]
        )
        first = ask_chatbot("nhập học cần những gì", retriever=retriever)
        second = ask_chatbot(
            "còn phí thì sao?",
            retriever=retriever,
            conversation_state=first["conversation_state"],
        )
        self.assertNotEqual(second["status"], "out_of_scope")
        self.assertEqual(second["trace"]["entities"]["scope_reason"], "in_scope_dhv")
        self.assertGreater(second["trace"]["retrieval_calls"], 0)

    def test_enrollment_document_followup_keeps_topic_scope(self) -> None:
        retriever = FixtureRetriever(
            [_enrollment_document("enrollment_document_010", "Giấy chứng nhận kết quả thi.")]
        )
        first = ask_chatbot("hồ sơ nhập học gồm những gì", retriever=retriever)
        second = ask_chatbot(
            "cần nộp khi nào?",
            retriever=retriever,
            conversation_state=first["conversation_state"],
        )
        self.assertNotEqual(second["status"], "out_of_scope")
        self.assertEqual(second["trace"]["entities"]["scope_reason"], "in_scope_dhv")
        self.assertGreater(second["trace"]["retrieval_calls"], 0)

    def test_generic_admissions_schedule_question_routes_to_schedule(self) -> None:
        analysis = analyze_question("Khi nào tuyển sinh?", ConversationState())
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_LICH_TUYEN_SINH")
        self.assertEqual(plan.categories, ("lich_tuyen_sinh",))


if __name__ == "__main__":
    unittest.main()
