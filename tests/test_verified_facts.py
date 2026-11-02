from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.chatbot.facts import (
    FactProvenance,
    ResolvedContext,
    VerifiedFact,
    facts_from_chunks,
    facts_from_score_facts,
)
from src.prompts.rag_prompt import build_rag_prompt


class VerifiedFactTests(unittest.TestCase):
    def test_prompt_serialization_excludes_internal_provenance_and_file_metadata(self) -> None:
        chunk = SimpleNamespace(
            text="Học phí là 1.250.000 đồng/tín chỉ.",
            metadata={
                "status": "verified",
                "category": "hoc_phi",
                "year": 2026,
                "chunk_id": "internal-chunk-1",
                "document_id": "internal-doc-1",
                "source_file": "C:/private/admissions.pdf",
                "source_url": "https://private.example/file.pdf",
                "title": "Tài liệu tuyển sinh DHV 2026",
            },
        )

        (fact,) = facts_from_chunks((chunk,))
        prompt_fact = fact.to_dict(for_prompt=True)
        audit_fact = fact.to_dict()

        self.assertEqual(prompt_fact["status"], "VERIFIED")
        self.assertNotIn("provenance", prompt_fact)
        self.assertNotIn("source_file", str(prompt_fact))
        self.assertNotIn("private.example", str(prompt_fact))
        self.assertIn("provenance", audit_fact)
        self.assertEqual(audit_fact["provenance"]["chunk_id"], "internal-chunk-1")

    def test_score_facts_with_conflicting_values_are_marked_conflict(self) -> None:
        rows = [
            {
                "source_status": "verified",
                "score_type": "admission_score",
                "major_name": "Công nghệ thông tin",
                "major_code": "7480201",
                "method": "thpt",
                "category": "diem_trung_tuyen",
                "raw_value": "18",
                "year": 2026,
                "document_id": "doc-a",
            },
            {
                "source_status": "verified",
                "score_type": "admission_score",
                "major_name": "Công nghệ thông tin",
                "major_code": "7480201",
                "method": "thpt",
                "category": "diem_trung_tuyen",
                "raw_value": "19",
                "year": 2026,
                "document_id": "doc-b",
            },
        ]

        facts = facts_from_score_facts(rows)

        self.assertEqual([fact.status for fact in facts], ["CONFLICT", "CONFLICT"])

    def test_resolved_context_is_a_separate_contract_and_prompt_has_both_questions(self) -> None:
        context = ResolvedContext(
            original_question="Học phí ngành đó bao nhiêu?",
            resolved_question="Học phí ngành Công nghệ thông tin bao nhiêu?",
            method="history_entity_resolution",
            entities={"major_name": "Công nghệ thông tin"},
        )
        fact = VerifiedFact(
            fact_id="fee-1",
            fact_type="tuition.rate",
            subject={"major_name": "Công nghệ thông tin"},
            value=1_250_000,
            unit="VND/tín chỉ",
            academic_year=2026,
            provenance=FactProvenance(
                source_id="internal-source",
                document_id="internal-document",
                public_url="https://private.example/source.pdf",
            ),
        )

        prompt = build_rag_prompt(
            context.resolved_question,
            "Học phí DHV năm 2026 là 1.250.000 đồng/tín chỉ.",
            original_question=context.original_question,
            resolved_context=context.to_dict(),
            verified_facts=[fact.to_dict(for_prompt=True)],
        )

        self.assertIn("<ORIGINAL_QUESTION>\nHọc phí ngành đó bao nhiêu?", prompt)
        self.assertIn("Học phí ngành Công nghệ thông tin bao nhiêu?", prompt)
        self.assertIn("1.250.000", prompt)
        self.assertNotIn("internal-source", prompt)
        self.assertNotIn("private.example", prompt)
        self.assertNotIn("private/source.pdf", prompt)


if __name__ == "__main__":
    unittest.main()
