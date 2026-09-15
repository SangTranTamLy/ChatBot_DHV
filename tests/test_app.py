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
    def test_empty_state_has_welcome_chat_input_and_privacy_notice_without_suggestions(self) -> None:
        at = _app()

        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "CHATBOT TƯ VẤN TUYỂN SINH DHV")
        self.assertEqual(len(at.chat_message), 1)
        self.assertEqual(len(at.chat_input), 1)
        self.assertEqual(len(at.pills), 0)
        expected_welcome = (
            "Xin chào! Tôi là ChatBot DHV – Trợ lý Tuyển sinh Trường Đại học Hùng Vương TP.HCM.\n\n"
            "Tôi có thể giải đáp nhanh cho bạn về:\n\n"
            "- Phương thức & điều kiện xét tuyển\n"
            "- Chỉ tiêu & ngành đào tạo\n"
            "- Hồ sơ, lịch trình & thủ tục nhập học\n\n"
            "Bạn đang cần hỗ trợ nội dung nào?"
        )
        self.assertTrue(any(element.value == expected_welcome for element in at.markdown))
        rendered_text = "\n".join(
            [element.value for element in at.markdown]
            + [element.value for element in at.caption]
        )
        self.assertNotIn("Gợi ý tiếp theo", rendered_text)
        self.assertNotIn("Câu hỏi gợi ý", rendered_text)
        self.assertTrue(any("Không nhập CCCD" in element.value for element in at.info))
        self.assertTrue(any("dữ liệu tuyển sinh DHV" in element.value for element in at.caption))

    def test_chat_message_styles_do_not_create_user_or_assistant_bubbles(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertNotIn("background: #eef0ff", source)
        self.assertNotIn("border: 1px solid #d5d7f4", source)
        self.assertIn(
            '[data-testid="stChatMessageContent"][aria-label*="user"] {\n'
            "            max-width: 72%;\n"
            "            margin-left: auto;\n"
            "            padding: 0.2rem 0;\n"
            "            border: none;\n"
            "            border-radius: 0;\n"
            "            background: transparent;\n",
            source,
        )

    def test_table_answer_uses_only_a_bordered_table_container(self) -> None:
        table = "| Tiêu chí | Giá trị |\n|---|---|\n| Mã ngành | 7480201 |"
        at = AppTest.from_file(str(APP_PATH))
        at.session_state["messages"] = [
            {"role": "user", "content": "Mã ngành là gì?"},
            {
                "role": "assistant",
                "content": f"Thông tin đã ghi nhận:\n\n{table}\n\nCác dòng trên không phải kết luận trúng tuyển.",
                "status": "ok",
            },
        ]
        at.run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(len(at.container), 1)
        self.assertEqual(at.container[0].markdown[0].value, table)
        self.assertTrue(
            any(element.value == "Thông tin đã ghi nhận:" for element in at.markdown)
        )
        self.assertTrue(
            any(
                element.value == "Các dòng trên không phải kết luận trúng tuyển."
                for element in at.markdown
            )
        )

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
                        "Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong "
                        "phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi "
                        "chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trường."
                    ),
                    "status": "out_of_scope",
                },
            ],
        )
        self.assertTrue(
            any("chỉ hỗ trợ các câu hỏi liên quan" in element.value for element in at.markdown)
        )
        self.assertEqual(at.session_state["state"], at.session_state["conversation_state"])
        self.assertEqual(len(at.pills), 0)

    def test_history_hides_backend_sources_and_renders_all_service_statuses(self) -> None:
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
        self.assertNotIn("Nguồn học phí DHV", rendered_text)
        self.assertNotIn("Nguồn chính thức", rendered_text)
        self.assertTrue(any(element.value == "Chưa có dữ liệu." for element in at.markdown))
        self.assertTrue(any(element.value == "Ollama offline." for element in at.markdown))
        self.assertTrue(any(element.value == "Ngoài phạm vi." for element in at.markdown))
        self.assertTrue(any(element.value == "Vector DB lỗi." for element in at.markdown))
        self.assertTrue(any(element.value == "Lỗi." for element in at.markdown))
        self.assertEqual(len(at.pills), 0)

    def test_direct_website_answer_keeps_requested_url_without_source_card(self) -> None:
        url = "https://tec.dhv.edu.vn/"
        at = AppTest.from_file(str(APP_PATH))
        at.session_state["messages"] = [
            {"role": "user", "content": "website Khoa Kỹ thuật Công nghệ là gì?"},
            {
                "role": "assistant",
                "content": f"Website chính thức của khoa: [{url}]({url})",
                "status": "ok",
                "allow_direct_website_url": True,
            },
        ]
        at.run(timeout=30)

        self.assertFalse(at.exception)
        rendered_text = "\n".join(element.value for element in at.markdown)
        self.assertIn(url, rendered_text)
        self.assertNotIn("Nguồn chính thức", rendered_text)
        self.assertEqual(len(at.pills), 0)


if __name__ == "__main__":
    unittest.main()
