"""Task J regressions for score intent separation and deterministic score safety."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.query_analysis import (
    ADMISSION_SCORE,
    APPLICATION_THRESHOLD,
    SCORE_ENGINE_INSUFFICIENT_DATA,
    analyze_question,
    deterministic_score_comparisons,
    deterministic_score_evaluation,
    route_question,
)
from src.chatbot.rag_chain import ask_chatbot


SOURCE_URL = "https://dhv.edu.vn/task-j"


def _document(category: str, text: str, *, status: str = "verified") -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": f"Task J {category}",
            "category": category,
            "year": 2026,
            "school_code": "DHV",
            "source_url": SOURCE_URL,
            "status": status,
            "chunk_id": f"task-j-{category}-{status}",
        },
    )


class RecordingRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def retrieve_with_audit(self, question: str, *, categories: tuple[str, ...], retrieval_query: str) -> dict[str, object]:
        return {"documents": list(self.documents)}


class NeverCalledLLM:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        raise AssertionError("missing verified score rule must not call the LLM")


class ScoreIntentRegressionTests(unittest.TestCase):
    def test_required_score_questions_are_separated(self) -> None:
        cases = (
            (
                "Cách tính điểm xét tuyển học bạ ngành Luật?",
                "HOI_CACH_TINH_DIEM",
                None,
                "hoc_ba",
                ("cach_tinh_diem",),
            ),
            (
                "Điểm xét tuyển học bạ ngành Luật bao nhiêu?",
                "HOI_NGUONG_DAU_VAO",
                APPLICATION_THRESHOLD,
                "hoc_ba",
                ("nganh_dao_tao",),
            ),
            (
                "Ngành Luật xét học bạ bao nhiêu điểm?",
                "HOI_NGUONG_DAU_VAO",
                APPLICATION_THRESHOLD,
                "hoc_ba",
                ("nganh_dao_tao",),
            ),
            (
                "Luật học bạ lấy bao nhiêu?",
                "HOI_NGUONG_DAU_VAO",
                APPLICATION_THRESHOLD,
                "hoc_ba",
                ("nganh_dao_tao",),
            ),
            (
                "Điểm chuẩn ngành Luật năm 2026 bao nhiêu?",
                "HOI_DIEM_TRUNG_TUYEN",
                ADMISSION_SCORE,
                None,
                ("diem_trung_tuyen",),
            ),
            (
                "Ngành Luật xét bổ sung bao nhiêu điểm?",
                "HOI_XET_TUYEN_BO_SUNG",
                "supplementary_threshold",
                None,
                ("xet_tuyen_bo_sung",),
            ),
        )
        for question, intent, score_type, method, categories in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, intent)
                self.assertEqual(analysis.entities["score_type"], score_type)
                self.assertEqual(analysis.entities["admission_method"], method)
                self.assertEqual(plan.categories, categories)

    def test_law_hoc_ba_missing_rule_does_not_fall_back_to_other_score_types(self) -> None:
        documents = [
            _document("nganh_dao_tao", "Luật\n7380101\n-\n-\n-"),
            _document(
                "nguong_dau_vao",
                "Xét kết quả học tập THPT (học bạ): từ 18 điểm.",
            ),
            _document("diem_trung_tuyen", "• Luật: 20,0 điểm."),
            _document(
                "xet_tuyen_bo_sung",
                "Thi tốt nghiệp THPT 2026: Luật từ 20 điểm.",
            ),
        ]
        llm = NeverCalledLLM()
        result = ask_chatbot(
            "Điểm xét tuyển học bạ ngành Luật bao nhiêu?",
            retriever=RecordingRetriever(documents),
            llm=llm,
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["trace"]["score_engine"]["status"], SCORE_ENGINE_INSUFFICIENT_DATA)
        self.assertEqual(llm.calls, 0)
        self.assertNotIn("18", result["answer"])
        self.assertNotIn("20", result["answer"])

    def test_score_engine_compares_only_verified_thresholds(self) -> None:
        verified = _document(
            "nganh_dao_tao",
            "Công nghệ thông tin\n7480201\nCông nghệ phần mềm\n15\n18\n600",
        )
        unverified = _document(
            "nganh_dao_tao",
            "Công nghệ thông tin\n7480201\n99\n99\n999",
            status="unverified",
        )
        evidence = build_evidence([verified, unverified])
        analysis = analyze_question("Tôi có ĐGNL 720, thích công nghệ")
        comparisons = deterministic_score_comparisons(analysis, evidence)
        self.assertEqual(
            comparisons,
            ({
                "method": "dgnl",
                "student_value": 720,
                "threshold_value": 600,
                "operator": ">=",
                "meets_threshold": True,
            },),
        )
        evaluation = deterministic_score_evaluation(
            analyze_question("Điểm sàn Công nghệ thông tin 2026"),
            evidence,
        )
        self.assertEqual(evaluation["status"], "ok")
        self.assertEqual({fact["raw_value"] for fact in evaluation["facts"]}, {"15", "18", "600"})

    def test_supplementary_law_rule_stays_separate_from_initial_threshold(self) -> None:
        evidence = build_evidence(
            [
                _document(
                    "xet_tuyen_bo_sung",
                    "Thi tốt nghiệp THPT 2026: phần lớn chương trình nhận hồ sơ từ 15 điểm; Luật và Luật kinh tế từ 20 điểm.\n"
                    "Học bạ THPT: phần lớn chương trình từ 18 điểm; Luật và Luật kinh tế có điều kiện riêng.",
                ),
                _document(
                    "nganh_dao_tao",
                    "Luật\n7380101\n-\n-\n-",
                ),
            ]
        )
        analysis = analyze_question("Luật xét bổ sung bằng thi tốt nghiệp THPT bao nhiêu điểm?")
        evaluation = deterministic_score_evaluation(analysis, evidence)
        self.assertEqual(evaluation["status"], "ok")
        self.assertEqual(evaluation["facts"][0]["major_name"], "Luật")
        self.assertEqual(evaluation["facts"][0]["raw_value"], "20")
        self.assertEqual(evaluation["facts"][0]["score_type"], "supplementary_threshold")


if __name__ == "__main__":
    unittest.main()
