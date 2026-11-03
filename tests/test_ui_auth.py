"""Input validation and Streamlit auth-flow tests for the Supabase integration."""

from pathlib import Path
import os
import tempfile
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.supabase_auth import AuthServiceError, validate_email, validate_name, validate_password, validate_password_pair


APP = Path(__file__).resolve().parents[1] / "app.py"
PROJECT_ROOT = APP.parent
_TEST_TEMP_ROOT = PROJECT_ROOT / ".qa_tmp"
_TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class AuthValidationTests(TestCase):
    def test_name_normalizes_trimmed_unicode_letters(self):
        self.assertEqual(validate_name("  Nguyễn Văn An  "), "Nguyễn Văn An")
        self.assertEqual(validate_name("a\u0301b"), "áb")
        self.assertEqual(validate_name("A" * 50), "A" * 50)

    def test_name_rejects_bad_lengths_and_nonletters(self):
        for name in ("A", "A" * 51, "An 2", "An!", "An🙂", "   "):
            with self.subTest(name=name), self.assertRaises(AuthServiceError):
                validate_name(name)

    def test_email_is_trimmed_lowercased_and_limited(self):
        self.assertEqual(validate_email("  AN@Example.COM  "), "an@example.com")
        self.assertEqual(validate_email("a" * 249 + "@b.co"), "a" * 249 + "@b.co")
        for email in ("bad-mail", "a@b", "a" * 250 + "@x.co"):
            with self.subTest(email=email), self.assertRaises(AuthServiceError):
                validate_email(email)

    def test_password_limits_use_character_count_and_utf8_bytes(self):
        self.assertEqual(validate_password("a" * 8), "a" * 8)
        self.assertEqual(validate_password("ắ" * 24), "ắ" * 24)
        for password in ("short12", "ắ" * 25):
            with self.subTest(password_length=len(password)), self.assertRaises(AuthServiceError):
                validate_password(password)
        with self.assertRaises(AuthServiceError):
            validate_password_pair("password1", "password2")
        validate_password_pair("password1", "password1")


class AuthScreenTests(TestCase):
    def setUp(self):
        history_directory = tempfile.TemporaryDirectory(
            dir=_TEST_TEMP_ROOT
        )
        self.addCleanup(history_directory.cleanup)
        history_env = patch.dict(
            os.environ,
            {"CHAT_HISTORY_PATH": str(Path(history_directory.name) / "history.json")},
        )
        history_env.start()
        self.addCleanup(history_env.stop)

    def test_chat_rejects_more_than_500_characters_before_backend_call(self):
        with patch(
            "src.chatbot.chat_service.ask_chatbot",
            return_value={"answer": "Không nên được gọi.", "status": "ok"},
        ) as backend:
            at = AppTest.from_file(str(APP))
            at.session_state["account_page"] = "chat"
            at.run(timeout=30)
            at.chat_input[0].set_value("x" * 501).run(timeout=30)

        self.assertFalse(at.exception)
        self.assertFalse(backend.called)
        self.assertEqual(at.session_state["messages"], [])
        self.assertTrue(any("tối đa 500 ký tự" in warning.value for warning in at.warning))

    def test_chat_accepts_exactly_500_characters(self):
        question = "x" * 500
        with patch(
            "src.chatbot.chat_service.ask_chatbot",
            return_value={"answer": "Đã nhận câu hỏi.", "status": "ok"},
        ) as backend:
            at = AppTest.from_file(str(APP))
            at.session_state["account_page"] = "chat"
            at.run(timeout=30)
            at.chat_input[0].set_value(question).run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"][0]["content"], question)
        backend.assert_called_once()

    def test_guest_can_chat_without_login_or_saved_history(self):
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Thông tin học phí.", "status": "ok"}) as backend:
            at = AppTest.from_file(str(APP))
            at.session_state["account_page"] = "chat"
            at.run(timeout=30)
            at.chat_input[0].set_value("Học phí bao nhiêu?").run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_view"])
        self.assertEqual(at.session_state["messages"][-1]["content"], "Thông tin học phí.")
        self.assertEqual(at.session_state["chats"], {})
        self.assertEqual(at.session_state["account_chat_sessions"], {})
        backend.assert_called_once()
        at.button(key="new_chat").click().run(timeout=30)
        self.assertEqual(at.session_state["messages"], [])
        self.assertEqual(at.session_state["chats"], {})

    def test_register_login_profile_and_logout_flow_uses_supabase_service(self):
        user = {"id": "user-1", "name": "Nguyễn An", "email": "an@example.com"}
        tokens = {"access_token": "access", "refresh_token": "refresh", "expires_at": 4_000_000_000}
        with (
            patch("src.ui_auth.is_supabase_configured", return_value=True),
            patch("src.ui_auth.register_user") as register,
            patch("src.ui_auth.login_user", return_value=(user, tokens)) as login,
            patch("src.ui_auth.logout_user") as remote_logout,
            # AppTest cannot mount Components v2; the stand-ins render nothing
            # and the values arrive through component state as in the browser.
            patch("src.ui_auth._LIVE_PASSWORD_INPUT", return_value=SimpleNamespace(value=None)),
            patch("src.ui_auth._LIVE_CONFIRMATION_INPUT", return_value=SimpleNamespace(value=None)),
        ):
            at = AppTest.from_file(str(APP)).run(timeout=30)
            at.button(key="rail_login").click().run(timeout=30)
            at.button(key="auth_register").click().run(timeout=30)
            at.text_input(key="register_name").set_value("Nguyễn An")
            at.text_input(key="register_email").set_value("AN@example.com")
            # The live password fields are custom components; AppTest cannot type
            # into them, so set their component state the way the frontend does.
            at.session_state["register_password_live"] = {"value": "DemoPass123"}
            at.session_state["register_confirmation_live"] = {"value": "DemoPass123"}
            at.button(key="submit_register").click().run(timeout=30)
            self.assertTrue(any("Đăng ký thành công" in message.value for message in at.success))
            self.assertIsNone(at.session_state["auth_user"])
            register.assert_called_once_with("Nguyễn An", "AN@example.com", "DemoPass123", "DemoPass123")

            at.button(key="auth_back_login").click().run(timeout=30)
            at.text_input(key="login_email").set_value("AN@example.com")
            at.text_input(key="login_password").set_value("DemoPass123")
            at.button(key="submit_login").click().run(timeout=30)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["auth_user"], user)
            self.assertEqual(at.session_state["auth_tokens"], tokens)
            self.assertNotIn("DemoPass123", repr(at.session_state["auth_user"]))
            login.assert_called_once_with("an@example.com", "DemoPass123")

            at.session_state["messages"] = [{"role": "user", "content": "Private chat"}]
            at.button(key="chat_account_logout").click().run(timeout=30)
            self.assertFalse(at.exception)
            self.assertIsNone(at.session_state["auth_user"])
            self.assertIsNone(at.session_state["auth_tokens"])
            remote_logout.assert_called_once_with(tokens)

    def test_wrong_credentials_show_one_generic_message(self):
        with (
            patch("src.ui_auth.is_supabase_configured", return_value=True),
            patch("src.ui_auth.login_user", side_effect=AuthServiceError("Email hoặc mật khẩu chưa đúng.")),
        ):
            at = AppTest.from_file(str(APP)).run(timeout=30)
            at.button(key="rail_login").click().run(timeout=30)
            at.text_input(key="login_email").set_value("unknown@example.com")
            at.text_input(key="login_password").set_value("WrongPass123")
            at.button(key="submit_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_user"])
        self.assertEqual(at.session_state["auth_view"], "login")
        self.assertTrue(any("Email hoặc mật khẩu chưa đúng" in message.value for message in at.error))

    def test_forgot_password_shows_generic_notice_even_when_provider_sends_no_email(self):
        with (
            patch("src.ui_auth.is_supabase_configured", return_value=True),
            patch("src.ui_auth.request_password_recovery", return_value=False) as request_reset,
        ):
            at = AppTest.from_file(str(APP))
            at.run(timeout=30)
            at.button(key="rail_login").click().run(timeout=30)
            at.button(key="auth_forgot_password").click().run(timeout=30)
            at.text_input(key="password_recovery_email").set_value("unknown@example.com")
            at.button(key="submit_password_recovery_request").click().run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["auth_view"], "forgot")
        self.assertTrue(any("Nếu email này đã đăng ký" in message.value for message in at.success))
        self.assertFalse(any("không tồn tại" in message.value.lower() for message in at.error))
        request_reset.assert_called_once_with("unknown@example.com")

    def test_forgot_password_request_has_a_60_second_session_cooldown(self):
        request_started = Event()

        def send_reset(_email):
            request_started.set()
            return False

        with (
            patch("src.ui_auth.is_supabase_configured", return_value=True),
            patch("src.ui_auth.request_password_recovery", side_effect=send_reset) as request_reset,
        ):
            at = AppTest.from_file(str(APP))
            at.run(timeout=30)
            at.button(key="rail_login").click().run(timeout=30)
            at.button(key="auth_forgot_password").click().run(timeout=30)
            at.text_input(key="password_recovery_email").set_value("unknown@example.com")
            at.button(key="submit_password_recovery_request").click().run(timeout=30)
            self.assertTrue(request_started.wait(timeout=2))
            at.button(key="submit_password_recovery_request").click().run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(request_reset.call_count, 1)
        self.assertTrue(any("Vui lòng chờ" in warning.value for warning in at.warning))

    def test_invalid_recovery_callback_shows_retry_without_loading_chat(self):
        at = AppTest.from_file(str(APP))
        at.query_params["auth"] = "recovery"
        at.session_state["password_recovery_link_checked"] = True
        at.session_state["password_recovery_link_error"] = True
        at.run(timeout=30)

        self.assertFalse(at.exception)
        self.assertTrue(any("Liên kết không hợp lệ hoặc đã hết hạn" in item.value for item in at.error))
        self.assertTrue(any(button.key == "password_recovery_retry" for button in at.button))
        self.assertFalse(any(button.key == "new_chat" for button in at.button))

    def test_verified_recovery_callback_can_set_password_and_return_success(self):
        tokens = {"access_token": "recovery-access", "refresh_token": "recovery-refresh"}
        with (
            patch("src.ui_auth.verify_password_recovery", return_value={
                "user_id": "user-1", "expires_at": 4_000_000_000,
            }),
            patch("src.ui_auth.reset_password_with_recovery", return_value="user-1") as reset,
            patch("src.ui_auth._LIVE_PASSWORD_INPUT", return_value=SimpleNamespace(value=None)),
            patch("src.ui_auth._LIVE_CONFIRMATION_INPUT", return_value=SimpleNamespace(value=None)),
        ):
            at = AppTest.from_file(str(APP))
            at.query_params["auth"] = "recovery"
            at.session_state["password_recovery_link_checked"] = True
            at.session_state["password_recovery_tokens"] = tokens
            at.session_state["password_recovery_password_live"] = {"value": "NewPass123"}
            at.session_state["password_recovery_confirmation_live"] = {"value": "NewPass123"}
            at.run(timeout=30)
            at.button(key="submit_password_recovery").click().run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["password_recovery_status"], "success")
        self.assertTrue(any("Mật khẩu đã được đặt lại thành công" in item.value for item in at.toast))
        self.assertIsNone(at.session_state["password_recovery_tokens"])
        reset.assert_called_once_with(tokens, "NewPass123", "NewPass123")

    def test_guest_chat_and_account_chat_remain_isolated(self):
        at = AppTest.from_file(str(APP))
        at.session_state["account_page"] = "chat"
        at.run(timeout=30)
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Guest answer", "status": "ok"}):
            at.chat_input[0].set_value("Guest question").run(timeout=30)
        at.session_state["auth_user"] = {"id": "a", "name": "Account A", "email": "a@example.com"}
        at.session_state["auth_tokens"] = {"access_token": "a", "refresh_token": "a", "expires_at": 4_000_000_000}
        at.run(timeout=30)
        self.assertEqual(at.session_state["messages"], [])
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Account A answer", "status": "ok"}):
            at.chat_input[0].set_value("Account A question").run(timeout=30)
        self.assertTrue(at.session_state["chats"])
        at.session_state["auth_user"] = {"id": "b", "name": "Account B", "email": "b@example.com"}
        at.session_state["auth_tokens"] = {"access_token": "b", "refresh_token": "b", "expires_at": 4_000_000_000}
        at.run(timeout=30)
        self.assertEqual(at.session_state["messages"], [])
        at.session_state["auth_user"] = {"id": "a", "name": "Account A", "email": "a@example.com"}
        at.session_state["auth_tokens"] = {"access_token": "a", "refresh_token": "a", "expires_at": 4_000_000_000}
        at.run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"][-1]["content"], "Account A answer")
        self.assertNotIn("Guest question", repr(at.session_state["account_chat_sessions"]))

    def test_chat_history_survives_logout_login_and_is_scoped_by_auth_user_id(self):
        user_a = {"id": "history-user-a", "name": "Account A", "email": "a@example.com"}
        user_b = {"id": "history-user-b", "name": "Account B", "email": "b@example.com"}
        tokens_a = {
            "access_token": "test-access-a",
            "refresh_token": "test-refresh-a",
            "expires_at": 4_000_000_000,
        }
        tokens_b = {
            "access_token": "test-access-b",
            "refresh_token": "test-refresh-b",
            "expires_at": 4_000_000_000,
        }

        with tempfile.TemporaryDirectory(
            dir=_TEST_TEMP_ROOT
        ) as directory:
            history_path = Path(directory) / "history.json"
            with (
                patch.dict(os.environ, {"CHAT_HISTORY_PATH": str(history_path)}),
                patch("src.ui_auth.logout_user"),
            ):
                first = AppTest.from_file(str(APP))
                first.session_state["auth_user"] = user_a
                first.session_state["auth_tokens"] = tokens_a
                first.run(timeout=30)
                first.session_state["messages"] = [
                    {"role": "user", "content": "Học phí ngành CNTT năm 2026?"},
                    {"role": "assistant", "content": "Theo dữ liệu năm 2026.", "status": "ok"},
                ]
                first.session_state["conversation_state"] = {
                    "previous_intent": "HOI_HOC_PHI",
                    "current_year": 2026,
                }
                first.run(timeout=30)
                self.assertFalse(first.exception)

                serialized_history = history_path.read_text(encoding="utf-8")
                for secret in ("test-access-a", "test-refresh-a", "test-access-b", "test-refresh-b"):
                    self.assertNotIn(secret, serialized_history)
                self.assertNotIn("access_token", serialized_history)
                self.assertNotIn("refresh_token", serialized_history)

                first.button(key="chat_account_logout").click().run(timeout=30)
                self.assertIsNone(first.session_state["auth_user"])
                self.assertEqual(first.session_state["messages"], [])

                first.session_state["auth_user"] = user_a
                first.session_state["auth_tokens"] = tokens_a
                first.run(timeout=30)
                self.assertEqual(
                    first.session_state["messages"][-1]["content"], "Theo dữ liệu năm 2026."
                )
                self.assertEqual(
                    first.session_state["conversation_state"]["previous_intent"],
                    "HOI_HOC_PHI",
                )

                second_account = AppTest.from_file(str(APP))
                second_account.session_state["auth_user"] = user_b
                second_account.session_state["auth_tokens"] = tokens_b
                second_account.run(timeout=30)
                self.assertFalse(second_account.exception)
                self.assertEqual(second_account.session_state["messages"], [])
                self.assertEqual(second_account.session_state["chats"], {})

    def test_history_write_path_error_warns_without_crashing_the_chat(self):
        with tempfile.TemporaryDirectory(
            dir=_TEST_TEMP_ROOT
        ) as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("keep this file", encoding="utf-8")
            history_path = blocker / "history.json"
            with patch.dict(os.environ, {"CHAT_HISTORY_PATH": str(history_path)}):
                at = AppTest.from_file(str(APP))
                at.session_state["auth_user"] = {
                    "id": "history-error-user",
                    "name": "Account A",
                    "email": "a@example.com",
                }
                at.session_state["auth_tokens"] = {
                    "access_token": "test-access",
                    "refresh_token": "test-refresh",
                    "expires_at": 4_000_000_000,
                }
                at.run(timeout=30)
                at.session_state["messages"] = [
                    {"role": "user", "content": "Câu hỏi cần lưu"},
                    {"role": "assistant", "content": "Câu trả lời", "status": "ok"},
                ]
                at.run(timeout=30)

            self.assertFalse(at.exception)
            self.assertTrue(at.session_state["chat_history_storage_error"])
            self.assertTrue(any("Chưa thể đọc hoặc lưu lịch sử chat" in warning.value for warning in at.warning))
            self.assertEqual(blocker.read_text(encoding="utf-8"), "keep this file")
