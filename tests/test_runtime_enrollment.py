"""Regression coverage for verified enrollment data reaching the runtime RAG path."""

from __future__ import annotations

import unittest
from unittest.mock import patch

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
            "source_file": "data/raw/ho_so/V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf",
            "status": "verified",
            "record_type": "enrollment_document",
            "structured_record_id": record_id,
            "chunk_id": f"test-{record_id}",
            "page": 3,
        },
    )


def _enrollment_benefits_document(text: str) -> Document:
    return Document(
        page_content=(
            "Thủ tục và quyền lợi nhập học DHV 2026\n"
            "4. Quyền lợi và quà tặng sau nhập học\n"
            "4.1 Quà tặng dành cho tân sinh viên\n"
            "Sau khi hoàn tất nhập học, tân sinh viên DHV được hưởng các quyền lợi và quà tặng theo chính sách hiện hành.\n"
            "4.2 Microsoft Office 365 bản quyền 01 năm\n"
            "• Bao gồm: Word – Excel – PowerPoint – Outlook – OneDrive – Teams – AI Copilot.\n"
            "4.3 Bộ quà tặng tân sinh viên\n"
            "Tân sinh viên được:\n"
            "• Cấp mã số sinh viên.\n"
            "• Nhận Balo DHV.\n"
            "• Nhận Hộp đựng bút.\n"
            "• Nhận Dây đeo thẻ sinh viên.\n"
            + text
        ),
        metadata={
            "title": "Thủ tục và quyền lợi nhập học DHV 2026",
            "category": "ho_so",
            "year": 2026,
            "school_code": "DHV",
            "source_url": SOURCE_URL,
            "source_file": "data/raw/07_THU_TUC_VA_QUYEN_LOI_NHAP_HOC_DHV_2026.pdf",
            "status": "verified",
            "record_type": "document_text",
            "chunk_id": "test-enrollment-benefits",
            "page": 2,
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
    def test_post_enrollment_gifts_and_benefits_use_their_own_verified_route(self) -> None:
        question = "Sau khi nhập học, tân sinh viên được nhận những quyền lợi và quà gì?"
        analysis = analyze_question(question, ConversationState())
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_NHAP_HOC")
        self.assertEqual(analysis.entities["request_type"], "enrollment_benefits")
        self.assertEqual(analysis.entities["requested_information"], ["enrollment_benefits"])
        self.assertEqual(plan.categories, ("ho_so", "nhap_hoc"))
        self.assertIn("microsoft office 365", plan.retrieval_query.casefold())

        class NeverCalled:
            def generate(self, prompt):
                raise AssertionError("Verified post-enrollment benefits should be rendered from evidence")

        result = ask_chatbot(
            question,
            retriever=FixtureRetriever([_enrollment_benefits_document("")]),
            llm=NeverCalled(),
        )
        answer = str(result["answer"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Microsoft Office 365 bản quyền 01 năm", answer)
        self.assertIn("AI Copilot", answer)
        self.assertIn("mã số sinh viên", answer)
        self.assertIn("balo dhv", answer.casefold())
        self.assertIn("hộp đựng bút", answer.casefold())
        self.assertIn("dây đeo thẻ sinh viên", answer.casefold())

    def test_gift_question_returns_the_complete_post_enrollment_benefits_section(self) -> None:
        result = ask_chatbot(
            "Sau khi nhập học được tặng quà gì?",
            retriever=FixtureRetriever([_enrollment_benefits_document("")]),
        )
        answer = str(result["answer"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Microsoft Office 365 bản quyền 01 năm", answer)
        self.assertIn("mã số sinh viên", answer)
        self.assertIn("balo dhv", answer.casefold())
        self.assertIn("hộp đựng bút", answer.casefold())
        self.assertIn("dây đeo thẻ sinh viên", answer.casefold())

    def test_rejected_enrollment_evidence_is_not_retried_or_sent_to_model(self) -> None:
        document = _enrollment_document("enrollment_location", "Cơ sở 1: 194 Lê Đức Thọ.")

        class NeverCalled:
            def generate(self, prompt):
                raise AssertionError("Rejected structured evidence must remain rejected")

        with patch("src.chatbot.rag_chain.validate_model_answer", return_value={
            "answer": "Chưa đủ bằng chứng", "sources": [], "status": "no_data",
            "_validation_reason": "ungrounded",
        }) as validator:
            result = ask_chatbot("Nộp hồ sơ nhập học ở cơ sở nào?",
                                 retriever=FixtureRetriever([document]), llm=NeverCalled())
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["trace"]["validator"]["reason"], "ungrounded")
        self.assertEqual(validator.call_count, 1)

    def test_enrollment_submission_location_is_one_question(self) -> None:
        for question in (
            "nộp hồ sơ nhập học ở cơ sở nào",
            "Em nộp hồ sơ nhập học ở đâu?",
            "Nộp hồ sơ nhập học tại địa chỉ nào?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question, ConversationState())
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_NHAP_HOC")
                self.assertEqual(plan.categories, ("ho_so", "nhap_hoc"))
                self.assertFalse(plan.subplans)

    def test_enrollment_submission_location_returns_only_addresses(self) -> None:
        document = _enrollment_document(
            "enrollment_location",
            "Nhà trường tiếp nhận hồ sơ tại một trong hai cơ sở:\n"
            "Cơ sở 1: 194 Lê Đức Thọ, phường An Nhơn, TP. Hồ Chí Minh\n"
            "Cơ sở 2: 37 Kinh Dương Vương, phường Phú Lâm, TP. Hồ Chí Minh\n"
            "Học phí HKI: 12.500.000 đồng.\nHọc bạ THPT.",
        )
        document.metadata["page"] = 1
        result = ask_chatbot(
            "nộp hồ sơ nhập học ở cơ sở nào",
            retriever=FixtureRetriever([document]),
        )
        self.assertEqual(result["status"], "ok")
        answer = str(result["answer"])
        self.assertIn("194 Lê Đức Thọ", answer)
        self.assertIn("37 Kinh Dương Vương", answer)
        self.assertNotIn("Học bạ", answer)
        self.assertNotIn("12.500.000", answer)
        self.assertNotIn("chưa biết câu trả lời", answer)

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
        self.assertEqual(second["trace"]["entities"]["scope_reason"], "in_scope_dhv")
        self.assertGreater(second["trace"]["retrieval_calls"], 0)

    def test_generic_admissions_schedule_question_routes_to_schedule(self) -> None:
        analysis = analyze_question("Khi nào tuyển sinh?", ConversationState())
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_LICH_TUYEN_SINH")
        self.assertEqual(plan.categories, ("lich_tuyen_sinh",))


if __name__ == "__main__":
    unittest.main()
