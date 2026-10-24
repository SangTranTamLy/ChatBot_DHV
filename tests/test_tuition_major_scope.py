"""Học phí áp dụng chung vẫn trả lời được khi câu hỏi nêu tên một ngành."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from evaluation.run_evaluation import _retriever
from src.chatbot.rag_chain import ask_chatbot
from src.retrieval.retriever import _entity_matches


CNTT = {"major_name": "Công nghệ thông tin", "candidate_majors": ["Công nghệ thông tin"]}
MARKETING = {"major_name": "Marketing", "candidate_majors": ["Marketing"]}


def _tuition(text: str, **metadata: object) -> Document:
    return Document(page_content=text, metadata={"category": "hoc_phi", "record_type": "tuition", **metadata})


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("tuition answer must come from verified evidence, not generation")


class TuitionEntityFilterTests(unittest.TestCase):
    def test_general_tuition_record_passes_a_major_filter(self) -> None:
        general = _tuition("Học phí HKI (10 tín chỉ): 12.500.000 đồng")
        self.assertTrue(_entity_matches(general, CNTT, ("hoc_phi",)))

    def test_other_major_specific_tuition_is_not_borrowed(self) -> None:
        cntt_only = _tuition("Học phí ngành Công nghệ thông tin: 15.000.000 đồng",
                             major_name="Công nghệ thông tin")
        self.assertFalse(_entity_matches(cntt_only, MARKETING, ("hoc_phi",)))

    def test_general_documents_of_another_type_or_category_still_need_the_major(self) -> None:
        page = _tuition("Học phí HKI (10 tín chỉ): 12.500.000 đồng", record_type="page_text")
        self.assertFalse(_entity_matches(page, CNTT, ("hoc_phi",)))
        other_category = _tuition("Học phí HKI (10 tín chỉ): 12.500.000 đồng", category="hoc_bong")
        self.assertFalse(_entity_matches(other_category, CNTT, ("hoc_bong",)))


class TuitionAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _ask(self, question: str) -> dict[str, object]:
        return ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())

    def test_major_and_plain_tuition_questions_get_the_general_rule(self) -> None:
        for question in ("Học phí ngành CNTT bao nhiêu?", "Học phí bao nhiêu?"):
            with self.subTest(question=question):
                result = self._ask(question)
                self.assertEqual(result["status"], "ok")
                self.assertIn("12.500.000", str(result["answer"]))
                audit = result["trace"]["retrieval"]
                self.assertTrue(any(hit.get("category") == "hoc_phi" for hit in audit["hits"]))


if __name__ == "__main__":
    unittest.main()
