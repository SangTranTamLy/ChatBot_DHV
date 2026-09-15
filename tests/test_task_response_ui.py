from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.chatbot.rag_chain import ask_chatbot
from src.models.local_llm import LocalLLM

from tests.test_task_f import EchoEvidenceLLM, _retriever


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TaskResponseRegressionTests(unittest.TestCase):
    def _ask(self, question: str) -> tuple[dict[str, object], EchoEvidenceLLM]:
        llm = EchoEvidenceLLM()
        return ask_chatbot(question, retriever=_retriever(), llm=llm), llm

    def test_system_identity_is_deterministic_and_not_official(self) -> None:
        result, llm = self._ask("đây có phải chatbot tuyển sinh của trường không")

        self.assertEqual(result["trace"]["intent"], "SYSTEM_IDENTITY")
        self.assertEqual(result["answer_plan"]["mode"], "DIRECT_SHORT")
        self.assertFalse(llm.prompts)
        self.assertIn("không phải chatbot hay kênh thông tin chính thức", result["answer"])

    def test_school_info_uses_overview_sections(self) -> None:
        result, _ = self._ask("thông tin trường")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer_plan"]["mode"], "OVERVIEW")
        self.assertIn("1995", result["answer"])
        self.assertIn("- ", result["answer"])
        self.assertNotIn("[Evidence", result["answer"])
        self.assertNotIn("Nguồn chính thức", result["answer"])

    def test_major_count_does_not_dump_the_catalogue(self) -> None:
        result, _ = self._ask("DHV có bao nhiêu ngành")

        self.assertEqual(result["answer_plan"]["mode"], "DIRECT_SHORT")
        self.assertIn("20 ngành chính", result["answer"])
        self.assertNotIn("1. Quản trị kinh doanh", result["answer"])

    def test_scholarship_policy_is_structured(self) -> None:
        result, _ = self._ask("Điều kiện nhận học bổng tuyển sinh")

        self.assertEqual(result["answer_plan"]["mode"], "EXPLANATION")
        self.assertGreaterEqual(str(result["answer"]).count("- "), 3)
        self.assertIn("50%", result["answer"])
        self.assertIn("ĐGNL", result["answer"])

    def test_personal_score_is_a_deterministic_threshold_comparison(self) -> None:
        result, llm = self._ask("720 điểm ĐGNL có đủ điều kiện nộp hồ sơ không")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer_plan"]["mode"], "DIRECT_SHORT")
        self.assertFalse(llm.prompts)
        self.assertIn("720", result["answer"])
        self.assertIn("600", result["answer"])
        self.assertIn("không phải kết luận trúng tuyển", result["answer"])
        self.assertNotIn("đủ điều kiện xét tuyển", result["answer"])

    def test_local_generation_failure_keeps_verified_tuition_usable(self) -> None:
        class InvalidLocalLLM(LocalLLM):
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "Một câu trả lời không có trong bằng chứng."

        llm = InvalidLocalLLM()
        result = ask_chatbot(
            "Học phí học kỳ 1 bao nhiêu",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("Học phí HKI (10 tín chỉ): 12.500.000 đồng", result["answer"])
        self.assertEqual(len(llm.prompts), 2)

    def test_local_generation_failure_keeps_scholarship_policy_structured(self) -> None:
        class InvalidLocalLLM(LocalLLM):
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "Một câu trả lời không có trong bằng chứng."

        llm = InvalidLocalLLM()
        result = ask_chatbot(
            "Điều kiện nhận học bổng tuyển sinh",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(str(result["answer"]).count("- "), 3)
        self.assertIn("50%", result["answer"])
        self.assertEqual(len(llm.prompts), 2)

    def test_formula_does_not_turn_into_a_threshold_answer(self) -> None:
        result, _ = self._ask("Cách tính điểm xét tuyển học bạ")

        self.assertEqual(result["answer_plan"]["mode"], "EXPLANATION")
        self.assertIn("Cách 1", result["answer"])
        self.assertIn("Cách 2", result["answer"])
        self.assertNotIn("600", result["answer"])

    def test_comparison_is_side_by_side_and_grounded(self) -> None:
        result, _ = self._ask("so sánh CNTT và Kỹ thuật máy tính")

        self.assertEqual(result["answer_plan"]["mode"], "COMPARISON")
        self.assertIn("| Tiêu chí |", result["answer"])
        self.assertIn("Công nghệ thông tin", result["answer"])
        self.assertIn("Kỹ thuật máy tính", result["answer"])
        self.assertNotIn("điểm trúng tuyển", str(result["answer"]).casefold())

    def test_recommendation_keeps_verified_program_parent_relation(self) -> None:
        result, _ = self._ask("tôi thích dựng video thì nên học ngành nào")

        self.assertEqual(result["answer_plan"]["mode"], "RECOMMENDATION")
        self.assertIn("Truyền thông đa phương tiện", result["answer"])
        self.assertIn("chương trình thuộc ngành Công nghệ thông tin", result["answer"])
        self.assertNotIn("trường khác", str(result["answer"]).casefold())

    def test_unverified_combination_is_no_data_without_generation(self) -> None:
        result, llm = self._ask("Môn A00 của CNTT năm 2026 là gì")

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["answer_plan"]["mode"], "NO_DATA")
        self.assertFalse(llm.prompts)
        self.assertNotIn("15", result["answer"])
        self.assertNotIn("18", result["answer"])
        self.assertNotIn("600", result["answer"])


class TaskResponseSuggestionRemovalTests(unittest.TestCase):
    def test_backend_related_questions_are_not_rendered(self) -> None:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        app.session_state["messages"] = [
            {"role": "user", "content": "Câu hỏi trước"},
            {
                "role": "assistant",
                "content": "Câu trả lời trước",
                "status": "ok",
                "related_questions": ["Thời tiết hôm nay?"],
            },
        ]
        app.run(timeout=30)

        self.assertFalse(app.exception)
        self.assertEqual(len(app.pills), 0)
        self.assertEqual(len(app.chat_input), 1)
        self.assertNotIn("Thời tiết hôm nay?", "\n".join(element.value for element in app.markdown))


if __name__ == "__main__":
    unittest.main()
