"""Task K regressions for hybrid retrieval, evidence selection and decomposition."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence, select_evidence_documents
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import analyze_question, route_question
from src.retrieval.retriever import DHVRetriever

from tests.test_task_f import (
    EchoEvidenceLLM,
    RecordingRetriever,
    _fixture_chunks,
    _retriever,
)


class TaskKRetrievalTests(unittest.TestCase):
    def test_hybrid_audit_exposes_bm25_dense_rrf_and_candidate_filters(self) -> None:
        result = _retriever().retrieve_with_audit(
            "7480201 là ngành gì?",
            categories=("nganh_dao_tao",),
            retrieval_query="7480201 là ngành gì?",
        )

        self.assertEqual(result.audit.fusion_method, "bm25+dense+rrf")
        self.assertTrue(result.audit.candidates)
        self.assertIn("bm25_rank", result.audit.hits[0])
        self.assertIn("dense_rank", result.audit.hits[0])
        self.assertIn("rrf_score", result.audit.hits[0])
        self.assertTrue(all(hit["rrf_score"] > 0 for hit in result.audit.hits))

    def test_evidence_selection_filters_metadata_and_table_rows_by_entity(self) -> None:
        selection = select_evidence_documents(
            _fixture_chunks(),
            categories=("nganh_dao_tao", "nguong_dau_vao"),
            entities={
                "candidate_majors": ["Công nghệ thông tin", "Kỹ thuật máy tính"],
            },
            target_year=2026,
        )
        evidence = build_evidence(selection.documents)
        context = evidence.context.casefold()

        self.assertIn("công nghệ thông tin", context)
        self.assertIn("kỹ thuật máy tính", context)
        self.assertNotIn("tài chính ngân hàng", context)
        self.assertNotIn("kế toán", context)
        self.assertNotIn("luật", context)
        self.assertTrue(
            any(
                item["filter_reason"] == "entity_not_in_document"
                for item in selection.filtered
            )
        )

    def test_selection_rejects_unverified_wrong_year_institution_and_source(self) -> None:
        base = next(
            document
            for document in _fixture_chunks()
            if document.metadata.get("category") == "nganh_dao_tao"
        )

        def clone(**metadata: object) -> Document:
            return Document(
                page_content=base.page_content,
                metadata={**base.metadata, **metadata},
            )

        documents = [
            base,
            clone(status="unverified", chunk_id="unverified"),
            clone(year=2025, chunk_id="old-year"),
            clone(school_code="OTHER", chunk_id="other-school"),
            clone(source_url="https://example.test/not-official", chunk_id="other-source"),
        ]
        selection = select_evidence_documents(
            documents,
            categories=("nganh_dao_tao",),
            target_year=2026,
        )

        reasons = {item["filter_reason"] for item in selection.filtered}
        self.assertIn("status_not_verified", reasons)
        self.assertIn("year_mismatch", reasons)
        self.assertIn("target_institution_mismatch", reasons)
        self.assertIn("source_url_invalid", reasons)

    def test_multi_issue_uses_independent_subqueries_and_deduped_merge(self) -> None:
        question = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
        retriever = RecordingRetriever(_fixture_chunks())
        result = ask_chatbot(question, retriever=retriever, llm=EchoEvidenceLLM())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(retriever.calls), 3)
        queries = [str(call["retrieval_query"]) for call in retriever.calls]
        self.assertEqual(len(set(queries)), 3)
        self.assertIn("học phí", queries[0].casefold())
        self.assertNotIn("học bổng", queries[0].casefold())
        self.assertIn("học bổng", queries[1].casefold())
        self.assertNotIn("học phí", queries[1].casefold())
        self.assertIn("chương trình đào tạo", queries[2].casefold())
        self.assertEqual(len(result["trace"]["multi_issue"]["evidence_selections"]), 3)
        merged = result["trace"]["multi_issue"]["merged_evidence"]
        self.assertEqual(len(merged["chunk_ids"]), len(set(merged["chunk_ids"])))

    def test_dgnl_dhqg_hcm_is_score_source_while_target_remains_dhv(self) -> None:
        question = "ĐGNL ĐHQG-HCM của DHV cần bao nhiêu điểm?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        result = ask_chatbot(
            question,
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )

        self.assertEqual(plan.categories, ("nganh_dao_tao", "nguong_dau_vao"))
        self.assertEqual(result["trace"]["entities"]["target_institution"], "DHV")
        self.assertEqual(result["trace"]["entities"]["score_source"], "ĐHQG-HCM")
        self.assertTrue(
            all(
                document.metadata.get("school_code") == "DHV"
                for document in _retriever().retrieve(question)
            )
        )


class TaskKConversationRegressionTests(unittest.TestCase):
    def test_score_interest_recommendation_keeps_only_candidate_rows(self) -> None:
        question = (
            "Tôi có ĐGNL 720, thích edit video và đang phân vân giữa "
            "Truyền thông đa phương tiện với Kỹ thuật máy tính, nên chọn hướng nào?"
        )
        result = ask_chatbot(question, retriever=_retriever(), llm=EchoEvidenceLLM())
        context = " ".join(
            item.get("content_preview", "")
            for item in result["trace"]["evidence_selection"]["selected"]
        ).casefold()

        self.assertIn("đgnl", str(result["answer"]).casefold())
        self.assertIn("truyền thông đa phương tiện", context)
        self.assertIn("kỹ thuật máy tính", context)
        self.assertNotIn("tài chính ngân hàng", context)
        self.assertNotIn("kế toán", context)
        self.assertNotIn("luật", context)


if __name__ == "__main__":
    unittest.main()
