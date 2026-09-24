"""Phase 2 regressions for scope, score semantics and deterministic recovery."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.scope_guard import is_in_scope


SOURCE_URL = "https://dhv.edu.vn/phase-2"


def _document(category: str, text: str) -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": f"Phase 2 {category}",
            "category": category,
            "year": 2026,
            "school_code": "DHV",
            "source_url": SOURCE_URL,
            "status": "verified",
            "chunk_id": f"phase-2-{category}",
        },
    )


class _RecordingRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
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
        return {"documents": list(self.documents)}


class _NeverCalledLLM:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        del prompt
        self.calls += 1
        raise AssertionError("this phase-2 branch must not call the LLM")


class Phase2ScopeAndScoreTests(unittest.TestCase):
    def test_admission_method_and_tuition_unit_questions_are_in_scope(self) -> None:
        for question in (
            "Trường có xét học bạ không?",
            "DHV nhận xét tuyển học bạ chứ?",
            "Dùng điểm học bạ nộp được không?",
            "ĐGNL có được dùng để xét tuyển không?",
            "1 tín chỉ năm 2026 bao nhiêu tiền?",
            "Phí mỗi tín chỉ là bao nhiêu?",
        ):
            with self.subTest(question=question):
                self.assertTrue(is_in_scope(question))

    def test_unrelated_questions_stay_out_of_scope(self) -> None:
        self.assertFalse(is_in_scope("Giá vàng hôm nay bao nhiêu?"))
        self.assertFalse(is_in_scope("Thời tiết hôm nay thế nào?"))

    def test_in_scope_without_evidence_is_no_data_and_retrieves(self) -> None:
        retriever = _RecordingRetriever([])
        llm = _NeverCalledLLM()
        for question in (
            "Trường có xét học bạ không?",
            "1 tín chỉ năm 2026 bao nhiêu tiền?",
        ):
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=retriever, llm=llm)
                self.assertEqual(result["status"], "no_data")
                self.assertNotEqual(result["status"], "out_of_scope")
        self.assertEqual(retriever.calls, 2)
        self.assertEqual(llm.calls, 0)

    def test_score_semantics_are_four_distinct_query_shapes(self) -> None:
        cases = (
            (
                "Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu?",
                "HOI_DIEM_TRUNG_TUYEN",
                "admission_score",
                "admission_score_lookup",
                ("diem_trung_tuyen",),
            ),
            (
                "Điểm sàn ngành Công nghệ thông tin năm 2026 là bao nhiêu?",
                "HOI_NGUONG_DAU_VAO",
                "application_threshold",
                "application_threshold_lookup",
                ("nganh_dao_tao", "nguong_dau_vao"),
            ),
            (
                "Điểm nhận hồ sơ bổ sung CNTT là bao nhiêu?",
                "HOI_XET_TUYEN_BO_SUNG",
                "supplementary_threshold",
                "supplementary_threshold_lookup",
                ("xet_tuyen_bo_sung",),
            ),
            (
                "Em được 18 điểm có chắc chắn đậu CNTT không?",
                "HOI_NGUONG_DAU_VAO",
                "application_threshold",
                "personal_score_comparison",
                ("nganh_dao_tao", "nguong_dau_vao"),
            ),
        )
        for question, intent, score_type, semantic_type, categories in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, intent)
                self.assertEqual(analysis.entities["score_type"], score_type)
                self.assertEqual(analysis.entities["score_query_type"], semantic_type)
                self.assertEqual(plan.categories, categories)

    def test_admission_lookup_recovers_from_native_table_rows_deterministically(self) -> None:
        retriever = _RecordingRetriever(
            [
                _document(
                    "diem_trung_tuyen",
                    "20 7480201 Công nghệ Thông tin 15 18 600",
                )
            ]
        )
        llm = _NeverCalledLLM()

        result = ask_chatbot(
            "Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu?",
            retriever=retriever,
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["deterministic_branch"], "admission_score_lookup")
        self.assertEqual(result["trace"]["final_status"], "ok")
        self.assertEqual(len(result["trace"]["selected_score_facts"]), 3)
        self.assertIn("15 điểm", str(result["answer"]))
        self.assertIn("18 điểm", str(result["answer"]))
        self.assertIn("600 điểm", str(result["answer"]))
        self.assertEqual(llm.calls, 0)

    def test_personal_score_comparison_is_not_an_admission_decision(self) -> None:
        retriever = _RecordingRetriever(
            [
                _document(
                    "nguong_dau_vao",
                    "Xét kết quả kỳ thi đánh giá năng lực: từ 600 điểm.",
                )
            ]
        )
        result = ask_chatbot(
            "Em được 720 ĐGNL có đậu không?",
            retriever=retriever,
            llm=_NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("720", str(result["answer"]))
        self.assertIn("600", str(result["answer"]))
        self.assertIn("không phải kết luận trúng tuyển", str(result["answer"]))
        self.assertNotIn("chắc chắn đậu", str(result["answer"]).casefold())

    def test_provenance_comes_from_metadata_not_embedded_pdf_url(self) -> None:
        evidence = build_evidence(
            [
                _document(
                    "hoc_phi",
                    "Học phí được công bố trong tài liệu PDF; xem https://example.invalid/embedded nếu cần.",
                )
            ]
        )
        self.assertTrue(evidence.is_usable)
        self.assertEqual(evidence.sources, ({"title": "Phase 2 hoc_phi", "url": SOURCE_URL},))
        self.assertNotIn("https://", evidence.context)


if __name__ == "__main__":
    unittest.main()
