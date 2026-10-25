"""Input validation and Streamlit auth-flow tests for the Supabase integration."""

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.supabase_auth import AuthServiceError, validate_email, validate_name, validate_password, validate_password_pair


APP = Path(__file__).resolve().parents[1] / "app.py"


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
    def test_guest_can_chat_without_login_or_saved_history(self):
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Thông tin học phí.", "status": "ok"}) as backend:
            at = AppTest.from_file(str(APP)).run(timeout=30)
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
            at.button(key="open_login").click().run(timeout=30)
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
            at.button(key="logout").click().run(timeout=30)
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
            at.button(key="open_login").click().run(timeout=30)
            at.text_input(key="login_email").set_value("unknown@example.com")
            at.text_input(key="login_password").set_value("WrongPass123")
            at.button(key="submit_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_user"])
        self.assertEqual(at.session_state["auth_view"], "login")
        self.assertTrue(any("Email hoặc mật khẩu chưa đúng" in message.value for message in at.error))

    def test_guest_chat_and_account_chat_remain_isolated(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
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
