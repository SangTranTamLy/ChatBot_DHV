"""“Bao nhiêu chương trình xét tuyển bổ sung” đếm chương trình của đợt bổ sung, không phải cả danh mục."""

from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot


SUPPLEMENTARY = "DHV mở bao nhiêu chương trình xét tuyển bổ sung?"
CATALOG = "DHV có bao nhiêu chương trình đào tạo?"


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("program counts must come from verified evidence")


class SupplementaryProgramCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def test_supplementary_program_count_is_one_issue(self) -> None:
        analysis = analyze_question(SUPPLEMENTARY)
        self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
        self.assertEqual(analysis.entities["request_type"], "supplementary_program_count")
        self.assertEqual(route_question(analysis).subplans, ())

    def test_supplementary_program_count_uses_the_round_evidence(self) -> None:
        result = ask_chatbot(SUPPLEMENTARY, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "ok")
        self.assertIn("12 chương trình", str(result["answer"]))
        self.assertNotIn("50", str(result["answer"]))
        self.assertIn("xet_tuyen_bo_sung", result["trace"]["router"]["categories"])

    def test_catalog_count_still_uses_the_general_catalogue(self) -> None:
        analysis = analyze_question(CATALOG)
        self.assertEqual(analysis.intent, "DANH_SACH_CHUONG_TRINH")
        result = ask_chatbot(CATALOG, retriever=self.retriever, llm=_NeverCalledLLM())
        self.assertIn("50 chương trình", str(result["answer"]))

    def test_two_separate_clauses_still_split(self) -> None:
        analysis = analyze_question("DHV có bao nhiêu chương trình đào tạo, và chỉ tiêu xét tuyển bổ sung là bao nhiêu?")
        self.assertEqual(analysis.intent, "MULTI_ISSUE")
        self.assertEqual(
            set(analysis.entities["issue_intents"]), {"DANH_SACH_CHUONG_TRINH", "HOI_XET_TUYEN_BO_SUNG"}
        )


if __name__ == "__main__":
    unittest.main()
