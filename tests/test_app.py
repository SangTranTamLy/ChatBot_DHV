"""Headless UI regression tests for the Task D Streamlit entry point."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"


def _signed_in_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH))
    at.session_state["account_page"] = "chat"
    at.session_state["auth_user"] = {"name": "Test User", "email": "test@example.com"}
    # init_auth signs out a user that has no tokens.
    at.session_state["auth_tokens"] = {"access_token": "a", "refresh_token": "r", "expires_at": 4_000_000_000}
    return at


def _app() -> AppTest:
    return _signed_in_app().run(timeout=30)


class StreamlitAppTests(unittest.TestCase):
    def test_major_list_renders_as_table_without_changing_history(self):
        answer = ("Các ngành đào tạo:\n\n"
                  "1. Kỹ thuật máy tính — mã ngành 7480106\n\n"
                  "2. Trí tuệ nhân tạo — mã ngành 7480107\n\n"
                  "Bạn muốn tìm hiểu ngành nào?")
        at = _signed_in_app()
        at.session_state["messages"] = [{"role": "assistant", "content": answer}]
        at.run(timeout=30)
        self.assertFalse(at.exception)
        rendered = "\n".join(element.value for element in at.markdown)
        self.assertIn("| STT | Ngành đào tạo | Mã ngành |", rendered)
        self.assertIn("| 1 | Kỹ thuật máy tính | 7480106 |", rendered)
        self.assertIn("| 2 | Trí tuệ nhân tạo | 7480107 |", rendered)
        self.assertIn("Bạn muốn tìm hiểu ngành nào?", rendered)
        self.assertNotIn("1. Kỹ thuật máy tính —", rendered)
        self.assertEqual(at.session_state["messages"][0]["content"], answer)

    def test_sidebar_groups_real_history_and_active_chat_hides_welcome(self):
        at = _signed_in_app()
        now = datetime.now()
        at.session_state["chats"] = {
            1: {"messages": [{"role": "user", "content": "Câu hỏi hôm nay"}],
                "conversation_state": {}, "updated_at": now.isoformat()},
            2: {"messages": [{"role": "user", "content": "Câu hỏi hôm qua"}],
                "conversation_state": {}, "updated_at": (now - timedelta(days=1)).isoformat()},
        }
        at.run(timeout=30)
        self.assertFalse(at.exception)
        captions = [element.value for element in at.sidebar.caption]
        self.assertIn("Hôm nay", captions)
        self.assertIn("Hôm qua", captions)
        at.button(key="history_2").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"][0]["content"], "Câu hỏi hôm qua")
        self.assertEqual(len(at.title), 0)
        self.assertFalse(any(button.key.startswith("starter_") for button in at.button))

    def test_ui_passes_previous_questions_and_answers_to_backend(self):
        previous = [
            {"role": "user", "content": "Hồ sơ nhập học cần gì?"},
            {"role": "assistant", "content": "Bạn mang học bạ và căn cước.", "status": "ok"},
        ]
        at = _signed_in_app()
        at.session_state["messages"] = previous.copy()
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Bạn mang bản gốc nhé.", "status": "ok"}) as backend:
            at.run(timeout=30)
            at.chat_input[0].set_value("Cần mang gì?").run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(backend.call_args.kwargs["conversation_history"][:2], previous)

    def test_empty_state_has_welcome_quick_questions_chat_input_and_privacy_notice(self) -> None:
        at = _app()
        self.assertFalse(at.exception)
        self.assertTrue(any("Chào User," in element.proto.body and "mình có thể giúp gì?" in element.proto.body for element in at.get("html")))
        self.assertEqual(len(at.chat_message), 0)
        self.assertEqual(len(at.chat_input), 1)
        labels = [button.label for button in at.button]
        for label in ("Cuộc trò chuyện mới", "DHV có những ngành đào tạo nào?", "Học phí và học bổng DHV năm 2026 như thế nào?", "Hồ sơ nhập học DHV cần những giấy tờ gì?"):
            self.assertIn(label, labels)
        self.assertTrue(any("Không nhập CCCD" in element.value for element in at.caption))

    def test_new_chat_clears_context_and_saved_chat_restores_its_own_state(self) -> None:
        at = _signed_in_app()
        messages = [{"role": "user", "content": "Hồ sơ cần gì?"},
                    {"role": "assistant", "content": "Bạn mang học bạ.", "status": "ok"}]
        state = {"previous_intent": "HOI_HO_SO", "current_year": 2026}
        at.session_state["messages"] = messages.copy()
        at.session_state["conversation_state"] = state.copy()
        at.run(timeout=30)
        at.button(key="new_chat").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"], [])
        self.assertIsNone(at.session_state["conversation_state"]["previous_intent"])
        at.button(key="history_0").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"], messages)
        self.assertEqual(at.session_state["conversation_state"], state)

    def test_table_answer_uses_only_a_bordered_table_container(self) -> None:
        table = "| Tiêu chí | Giá trị |\n|---|---|\n| Mã ngành | 7480201 |"
        at = _signed_in_app()
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
        self.assertTrue(any(element.value == table for element in at.markdown))
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

    def test_starter_question_sends_its_full_query_to_chat_service(self) -> None:
        with patch(
            "src.chatbot.chat_service.ask_chatbot",
            return_value={"answer": "Học phí theo dữ liệu DHV.", "status": "ok"},
        ) as ask_chatbot:
            at = _app()
            next(button for button in at.button if button.label == "Học phí và học bổng DHV năm 2026 như thế nào?").click().run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(
            at.session_state["messages"][-2:],
            [
                {"role": "user", "content": "Học phí và học bổng DHV năm 2026 như thế nào?"},
                {
                    "role": "assistant",
                    "content": "Học phí theo dữ liệu DHV.",
                    "status": "ok",
                },
            ],
        )
        self.assertEqual(ask_chatbot.call_args.args[0], "Học phí và học bổng DHV năm 2026 như thế nào?")
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
        at = _signed_in_app()
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
        at = _signed_in_app()
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

    def test_verified_contact_channel_links_render_and_persist_in_history(self) -> None:
        url = "https://www.tiktok.com/@dhv.official"
        website_url = "https://dhv.edu.vn/"
        backend_result = {
            "answer": (
                "Bạn có thể theo dõi thông tin chính thức của DHV tại các kênh sau:\n\n"
                f"**Website DHV:** [dhv.edu.vn]({website_url})\n\n"
                f"**TikTok:** [@dhv.official]({url})"
            ),
            "status": "ok",
            "trace": {
                "intent": "HOI_CO_SO_LIEN_HE",
                "entities": {"website_request": False},
                "evidence_selection": {
                    "selected": [{"selected": True, "category": "co_so_lien_he"}],
                },
            },
        }
        at = _signed_in_app()
        with patch("src.chatbot.chat_service.ask_chatbot", return_value=backend_result):
            at.run(timeout=30)
            at.chat_input[0].set_value("Thông tin liên hệ").run(timeout=30)

        self.assertFalse(at.exception)
        rendered_text = "\n".join(element.value for element in at.markdown)
        self.assertIn(url, rendered_text)
        self.assertIn(website_url, rendered_text)
        self.assertIn("Website DHV", rendered_text)
        self.assertIn("@dhv.official", rendered_text)
        self.assertTrue(at.session_state["messages"][-1]["allow_contact_channel_urls"])

    def test_account_avatar_and_name_are_display_only(self) -> None:
        at = _app()
        self.assertFalse(at.exception)
        keys = {button.key for button in at.button}
        self.assertTrue({"account_settings", "logout"} <= keys)
        for key in ("account_avatar_button", "account_profile_button", "popup_avatar", "popup_name"):
            self.assertNotIn(key, keys)
        self.assertNotIn("Test User", [button.label for button in at.button])

    def test_settings_opens_profile_and_back_returns_to_chat(self) -> None:
        at = _app()
        at.button(key="account_settings").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["account_page"], "profile")
        self.assertIn("### Đổi mật khẩu", [element.value for element in at.markdown])
        at.button(key="profile_back_to_chat").click().run(timeout=30)
        self.assertEqual(at.session_state["account_page"], "chat")
        self.assertTrue(at.chat_input)

    def test_logout_from_account_menu_clears_session(self) -> None:
        with patch("src.ui_auth.logout_user") as remote_logout:
            at = _app()
            at.button(key="logout").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_user"])
        self.assertIsNone(at.session_state["auth_tokens"])
        remote_logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
