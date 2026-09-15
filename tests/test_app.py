"""Headless UI regression tests for the Task D Streamlit entry point."""

from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"


def _app() -> AppTest:
    return AppTest.from_file(str(APP_PATH)).run(timeout=30)


class StreamlitAppTests(unittest.TestCase):
    def test_empty_state_has_welcome_quick_questions_chat_input_and_privacy_notice(self) -> None:
        at = _app()

        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "CHATBOT TƯ VẤN TUYỂN SINH DHV")
        self.assertEqual(len(at.chat_message), 1)
        self.assertEqual(len(at.chat_input), 1)
        self.assertEqual(
            at.pills[0].options,
            [
                "Học phí DHV 2026",
                "Học bổng DHV 2026",
                "Hồ sơ xét tuyển bổ sung",
                "Lịch tuyển sinh",
                "Thủ tục nhập học",
            ],
        )
        self.assertTrue(any("Không nhập CCCD" in element.value for element in at.info))
        self.assertTrue(any("dữ liệu tuyển sinh DHV" in element.value for element in at.caption))

    def test_chat_input_persists_history_and_handles_out_of_scope(self) -> None:
        at = _app()

        at.chat_input[0].set_value("Thời tiết hôm nay?").run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["state"], at.session_state["conversation_state"])
        self.assertEqual(
            at.session_state["messages"][-2:],
            [
                {"role": "user", "content": "Thời tiết hôm nay?"},
                {
                    "role": "assistant",
                    "content": (
                        "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh "
                        "Trường Đại học Hùng Vương TP.HCM."
                    ),
                    "status": "out_of_scope",
                },
            ],
        )
        self.assertTrue(
            any("chỉ hỗ trợ các câu hỏi liên quan" in element.value for element in at.info)
        )
        self.assertEqual(at.session_state["state"], at.session_state["conversation_state"])
        self.assertEqual(len(at.pills), 0)

    def test_history_hides_backend_sources_and_all_service_statuses(self) -> None:
        messages = [
            {"role": "user", "content": "Học phí?"},
            {
                "role": "assistant",
                "content": "Học phí được cập nhật theo dữ liệu DHV.",
                "status": "ok",
                "sources": [
                    {"title": "Nguồn học phí DHV", "url": "https://dhv.edu.vn/hoc-phi"}
                ],
            },
            {"role": "user", "content": "Câu hỏi thiếu dữ liệu"},
            {
                "role": "assistant",
                "content": "Chưa có dữ liệu.",
                "status": "no_data",
                "sources": [],
            },
            {"role": "user", "content": "Ngoài phạm vi"},
            {
                "role": "assistant",
                "content": "Ngoài phạm vi.",
                "status": "out_of_scope",
                "sources": [],
            },
            {"role": "user", "content": "Ollama"},
            {
                "role": "assistant",
                "content": "Ollama offline.",
                "status": "ollama_offline",
                "sources": [],
            },
            {"role": "user", "content": "Vector DB"},
            {
                "role": "assistant",
                "content": "Vector DB lỗi.",
                "status": "vector_db_error",
                "sources": [],
            },
            {"role": "user", "content": "Lỗi"},
            {"role": "assistant", "content": "Lỗi.", "status": "error", "sources": []},
        ]
        at = AppTest.from_file(str(APP_PATH))
        at.session_state["messages"] = messages
        at.run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(len(at.chat_message), len(messages))
        rendered_text = "\n".join(
            [element.value for element in at.markdown]
            + [element.value for element in at.caption]
            + [element.value for element in at.info]
            + [element.value for element in at.warning]
            + [element.value for element in at.error]
        )
        self.assertNotIn("https://dhv.edu.vn/hoc-phi", rendered_text)
        self.assertNotIn("Nguồn chính thức", rendered_text)
        self.assertNotIn("Mở nguồn chính thức", rendered_text)
        self.assertTrue(any(element.value == "Chưa có dữ liệu." for element in at.warning))
        self.assertTrue(any(element.value == "Ollama offline." for element in at.warning))
        self.assertTrue(any(element.value == "Ngoài phạm vi." for element in at.info))
        self.assertTrue(any(element.value == "Vector DB lỗi." for element in at.error))
        self.assertTrue(any(element.value == "Lỗi." for element in at.error))


if __name__ == "__main__":
    unittest.main()
