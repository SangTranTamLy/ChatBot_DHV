"""Registration, password checks and the session-only Streamlit login flow."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ui_auth import authenticate, register_account


APP = Path(__file__).resolve().parents[1] / "app.py"


class SessionAccountsTests(TestCase):
    def test_register_login_by_name_and_email_without_storing_plain_password(self):
        accounts = {}
        self.assertIsNone(register_account(accounts, "Nguyễn An", "an@example.com", "DemoPass123", "DemoPass123"))
        for identifier in ("NGUYỄN AN", " AN@EXAMPLE.COM "):
            with self.subTest(identifier=identifier):
                self.assertEqual(authenticate(accounts, identifier, "DemoPass123")["name"], "Nguyễn An")
        self.assertNotIn("DemoPass123", repr(accounts))
        self.assertIsNone(authenticate(accounts, "an@example.com", "WrongPass123"))
        self.assertIsNone(authenticate({}, "an@example.com", "DemoPass123"))

    def test_invalid_registration_never_creates_an_account(self):
        for name, email, password, confirmation in (
            ("", "an@example.com", "DemoPass123", "DemoPass123"),
            ("A" * 61, "an@example.com", "DemoPass123", "DemoPass123"),
            ("a@b", "an@example.com", "DemoPass123", "DemoPass123"),
            ("An", "bad-mail", "DemoPass123", "DemoPass123"),
            ("An", "an@example.com", "short", "short"),
            ("An", "an@example.com", "DemoPass123", "Different123"),
            ("An", "an@example.com", "x" * 129, "x" * 129),
        ):
            with self.subTest(name=name, email=email):
                accounts = {}
                self.assertIsNotNone(register_account(accounts, name, email, password, confirmation))
                self.assertEqual(accounts, {})

    def test_duplicate_identity_and_salt_isolation(self):
        accounts = {}
        register_account(accounts, "An", "an@example.com", "DemoPass123", "DemoPass123")
        self.assertIsNotNone(register_account(accounts, "AN", "other@example.com", "DemoPass123", "DemoPass123"))
        self.assertIsNotNone(register_account(accounts, "Other", "AN@example.com", "DemoPass123", "DemoPass123"))
        register_account(accounts, "Binh", "binh@example.com", "DemoPass123", "DemoPass123")
        self.assertNotEqual(accounts["an@example.com"]["password_hash"], accounts["binh@example.com"]["password_hash"])


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

    def test_account_history_is_hidden_after_logout_and_restored_after_login(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
        at.button(key="open_login").click().run(timeout=30)
        at.button(key="auth_register").click().run(timeout=30)
        at.text_input(key="register_name").set_value("Nguyễn An")
        at.text_input(key="register_email").set_value("an@example.com")
        at.text_input(key="register_password").set_value("DemoPass123")
        at.text_input(key="register_confirmation").set_value("DemoPass123")
        at.button(key="submit_register").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any("Đăng ký thành công" in message.value for message in at.success))
        self.assertIsNone(at.session_state["auth_user"])
        at.button(key="auth_back_login").click().run(timeout=30)
        at.text_input(key="login_identifier").set_value("Nguyễn An")
        at.text_input(key="login_password").set_value("DemoPass123")
        at.button(key="submit_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any("Đăng nhập thành công" in message.proto.body for message in at.get("toast")))
        self.assertIsNone(at.session_state["auth_view"])
        self.assertEqual(len(at.text_input), 0)
        self.assertEqual(len(at.chat_input), 1)
        at.session_state["messages"] = [{"role": "user", "content": "Private chat"}]
        at.button(key="logout").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_user"])
        self.assertEqual(at.session_state["messages"], [])
        self.assertEqual(at.session_state["chats"], {})
        self.assertIn("an@example.com", at.session_state["auth_accounts"])
        at.button(key="open_login").click().run(timeout=30)
        at.text_input(key="login_identifier").set_value("an@example.com")
        at.text_input(key="login_password").set_value("DemoPass123")
        at.button(key="submit_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"], [{"role": "user", "content": "Private chat"}])

    def test_wrong_password_stays_in_modal(self):
        at = AppTest.from_file(str(APP))
        accounts = {}
        register_account(accounts, "An", "an@example.com", "DemoPass123", "DemoPass123")
        at.session_state["auth_accounts"] = accounts
        at.run(timeout=30)
        at.button(key="open_login").click().run(timeout=30)
        at.text_input(key="login_identifier").set_value("an@example.com")
        at.text_input(key="login_password").set_value("WrongPass123")
        at.button(key="submit_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["auth_user"])
        self.assertEqual(at.session_state["auth_view"], "login")
        self.assertTrue(at.error)

    def test_forgot_password_switches_inside_popup_and_can_return(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
        at.button(key="open_login").click().run(timeout=30)
        at.button(key="auth_forgot").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["auth_view"], "forgot")
        self.assertEqual(len(at.text_input), 1)
        self.assertEqual(at.text_input[0].label, "Email")
        at.text_input(key="forgot_email").set_value("bad-email")
        at.button(key="submit_forgot").click().run(timeout=30)
        self.assertTrue(any("email hợp lệ" in message.value for message in at.error))
        at.text_input(key="forgot_email").set_value("an@example.com")
        at.button(key="submit_forgot").click().run(timeout=30)
        self.assertTrue(any("chưa gửi email đặt lại" in message.value for message in at.success))
        self.assertIsNone(at.session_state["auth_user"])
        at.button(key="auth_back_login").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["auth_view"], "login")

    def test_registration_has_exactly_four_fields_and_password_confirmation(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
        at.button(key="open_login").click().run(timeout=30)
        at.button(key="auth_register").click().run(timeout=30)
        self.assertEqual([field.label for field in at.text_input],
                         ["Họ và tên", "Email", "Mật khẩu", "Xác nhận mật khẩu"])
        at.text_input(key="register_name").set_value("Nguyễn An")
        at.text_input(key="register_email").set_value("an@example.com")
        at.text_input(key="register_password").set_value("DemoPass123")
        at.text_input(key="register_confirmation").set_value("Mismatch123")
        at.button(key="submit_register").click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any("chưa khớp" in message.value for message in at.error))
        self.assertEqual(at.session_state["auth_accounts"], {})

    def test_empty_login_and_invalid_email_are_validated(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
        at.button(key="open_login").click().run(timeout=30)
        at.button(key="submit_login").click().run(timeout=30)
        self.assertTrue(any("nhập tên/email và mật khẩu" in message.value for message in at.error))
        at.text_input(key="login_identifier").set_value("bad@address")
        at.text_input(key="login_password").set_value("DemoPass123")
        at.button(key="submit_login").click().run(timeout=30)
        self.assertTrue(any("email hợp lệ" in message.value for message in at.error))
        self.assertIsNone(at.session_state["auth_user"])

    def test_guest_chat_is_not_attached_to_login_and_accounts_are_isolated(self):
        at = AppTest.from_file(str(APP)).run(timeout=30)
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Guest answer", "status": "ok"}):
            at.chat_input[0].set_value("Guest question").run(timeout=30)
        at.session_state["auth_user"] = {"name": "Account A", "email": "a@example.com"}
        at.run(timeout=30)
        self.assertEqual(at.session_state["messages"], [])
        self.assertEqual(at.session_state["chats"], {})
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Account A answer", "status": "ok"}):
            at.chat_input[0].set_value("Account A question").run(timeout=30)
        self.assertTrue(at.session_state["chats"])
        at.session_state["auth_user"] = {"name": "Account B", "email": "b@example.com"}
        at.run(timeout=30)
        self.assertEqual(at.session_state["messages"], [])
        self.assertEqual(at.session_state["chats"], {})
        at.session_state["auth_user"] = {"name": "Account A", "email": "a@example.com"}
        at.run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["messages"][-1]["content"], "Account A answer")
        self.assertNotIn("Guest question", repr(at.session_state["account_chat_sessions"]))

    def test_guest_quick_question_also_works_without_login(self):
        with patch("src.chatbot.chat_service.ask_chatbot", return_value={"answer": "Danh sách ngành", "status": "ok"}) as backend:
            at = AppTest.from_file(str(APP)).run(timeout=30)
            next(button for button in at.button if button.label == "DHV có những ngành đào tạo nào?").click().run(timeout=30)
        self.assertFalse(at.exception)
        backend.assert_called_once()
        self.assertIsNone(at.session_state["auth_view"])
        self.assertEqual(at.session_state["chats"], {})
