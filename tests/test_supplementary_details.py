"""Xét tuyển bổ sung: trả đúng chi tiết được hỏi (chỉ tiêu, hạn nộp, lệ phí)."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import analyze_question
from src.chatbot.rag_chain import ask_chatbot


QUOTA = "Chỉ tiêu xét tuyển bổ sung năm 2026 của DHV là bao nhiêu?"
DEADLINE = "Hạn nộp hồ sơ xét tuyển bổ sung là khi nào?"
FEE = "Xét tuyển bổ sung có mất lệ phí không?"
SCORE = "Luật xét bổ sung bằng thi tốt nghiệp THPT bao nhiêu điểm?"
CNTT_HOC_BA_THRESHOLD = (
    "Ngưỡng điểm nhận hồ sơ xét tuyển bổ sung bằng học bạ đối với ngành "
    "Công nghệ thông tin năm 2026 là bao nhiêu?"
)


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("supplementary details must come from verified evidence")


class _FixedRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def retrieve_with_audit(self, question: str, **_: object) -> dict[str, object]:
        return {"documents": list(self.documents)}


class SupplementaryDetailAnalysisTests(unittest.TestCase):
    def test_requested_detail_is_recognised_and_not_treated_as_a_score(self) -> None:
        for question, expected in (
            (QUOTA, "supplementary_quota"),
            (DEADLINE, "supplementary_deadline"),
            (FEE, "supplementary_fee"),
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "HOI_XET_TUYEN_BO_SUNG")
                self.assertEqual(analysis.entities["request_type"], expected)
                self.assertIsNone(analysis.entities["score_query_type"])

    def test_score_question_keeps_the_threshold_lookup(self) -> None:
        analysis = analyze_question(SCORE)
        self.assertEqual(analysis.entities["score_query_type"], "supplementary_threshold_lookup")
        self.assertEqual(analysis.entities["request_type"], "")


class SupplementaryDetailAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _ask(self, question: str) -> dict[str, object]:
        return ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM())

    def test_each_detail_gets_its_own_verified_fact(self) -> None:
        for question, expected, foreign in (
            (QUOTA, ("345 chỉ tiêu", "12 chương trình"), ("21/8/2026", "Cơ sở 1")),
            (DEADLINE, ("21/8/2026",), ("345", "Cơ sở 1")),
            (FEE, ("miễn phí xét tuyển",), ("345", "Cơ sở 1")),
        ):
            with self.subTest(question=question):
                result = self._ask(question)
                self.assertEqual(result["status"], "ok")
                answer = str(result["answer"])
                for text in expected:
                    self.assertIn(text, answer)
                for text in foreign:
                    self.assertNotIn(text, answer)
                self.assertNotIn("đang mở", answer)

    def test_supplementary_score_answer_is_unchanged(self) -> None:
        result = self._ask(SCORE)
        self.assertEqual(result["trace"]["deterministic_branch"], "supplementary_threshold_lookup")
        self.assertIn("20 điểm", str(result["answer"]))

    def test_threshold_question_with_intake_wording_uses_its_method_specific_fact(self) -> None:
        result = self._ask(CNTT_HOC_BA_THRESHOLD)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["deterministic_branch"], "supplementary_threshold_lookup")
        self.assertIn("18 điểm", str(result["answer"]))
        self.assertNotIn("15 điểm", str(result["answer"]))
        self.assertNotIn("21/8/2026", str(result["answer"]))

    def test_missing_detail_evidence_returns_no_data_instead_of_guessing(self) -> None:
        unrelated = Document(
            page_content="Thí sinh có thể đăng ký trực tuyến tại cổng thông tin tuyển sinh.",
            metadata={
                "category": "xet_tuyen_bo_sung", "record_type": "page_text", "year": 2026,
                "school_code": "DHV", "status": "verified", "chunk_id": "supplementary-route",
                "source_url": "https://dhv.edu.vn/dhv-nhan-ho-so-xet-tuyen-bo-sung/",
            },
        )
        result = ask_chatbot(QUOTA, retriever=_FixedRetriever([unrelated]), llm=_NeverCalledLLM())
        self.assertEqual(result["status"], "no_data")


if __name__ == "__main__":
    unittest.main()
