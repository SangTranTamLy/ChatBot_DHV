"""Mocked Supabase Auth service tests; no project or credentials are needed."""

from unittest import TestCase
from unittest.mock import patch

from src.supabase_auth import (
    AuthServiceError,
    PASSWORD_RECOVERY_REDIRECT_URL,
    change_password,
    login_user,
    register_user,
    request_password_recovery,
    reset_password_with_recovery,
    restore_auth_session,
    verify_password_recovery,
)


class _Query:
    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def single(self):
        return self

    def execute(self):
        return {"data": {"display_name": "Nguyễn An"}}


class _Auth:
    def __init__(self):
        self.user = {"id": "user-1", "email": "an@example.com"}
        self.session = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": 4_000_000_000,
            "user": self.user,
        }
        self.signup_args = None
        self.login_args = None
        self.update_args = None
        self.signed_out = False
        self.sign_out_options = None
        self.reset_args = None
        self.reset_error = None
        self.claims = {
            "sub": "user-1",
            "exp": 4_000_000_000,
            "amr": [{"method": "recovery"}],
        }

    def sign_up(self, args):
        self.signup_args = args
        return {"user": self.user, "session": self.session}

    def sign_in_with_password(self, args):
        self.login_args = args
        if args["password"] == "WrongPass123":
            raise ValueError("invalid credentials")
        return {"user": self.user, "session": self.session}

    def sign_out(self, options=None):
        self.signed_out = True
        self.sign_out_options = options

    def reset_password_for_email(self, email, options=None):
        self.reset_args = (email, options)
        if self.reset_error:
            raise self.reset_error

    def get_session(self):
        return self.session

    def set_session(self, access_token, refresh_token):
        self.session = {
            **self.session,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        return self.session

    def get_user(self, _jwt=None):
        return {"user": self.user}

    def get_claims(self, _jwt=None):
        return {"claims": self.claims}

    def update_user(self, args):
        self.update_args = args
        return {"user": self.user}


class _Client:
    def __init__(self):
        self.auth = _Auth()

    def table(self, _name):
        return _Query()


class SupabaseAuthServiceTests(TestCase):
    def setUp(self):
        self.client = _Client()
        self.config_patch = patch("src.supabase_auth.get_supabase_config", return_value=("https://test.supabase.co", "publishable"))
        self.factory_patch = patch("src.supabase_auth._CLIENT_FACTORY", return_value=self.client)
        self.config_patch.start()
        self.factory_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.factory_patch.stop)

    def test_signup_sends_name_as_metadata_and_discards_returned_session(self):
        register_user(" Nguyễn An ", "AN@example.com", "DemoPass123", "DemoPass123")
        self.assertEqual(self.client.auth.signup_args["email"], "an@example.com")
        self.assertEqual(self.client.auth.signup_args["options"]["data"]["display_name"], "Nguyễn An")
        self.assertTrue(self.client.auth.signed_out)

    def test_login_returns_only_verified_profile_and_tokens(self):
        user, tokens = login_user("AN@example.com", "DemoPass123")
        self.assertEqual(user, {"id": "user-1", "name": "Nguyễn An", "email": "an@example.com"})
        self.assertEqual(tokens["access_token"], "access-token")
        self.assertNotIn("password", user)

    def test_restore_checks_auth_and_reads_the_profile(self):
        user, tokens = restore_auth_session({
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": 4_000_000_000,
        })
        self.assertEqual(user["name"], "Nguyễn An")
        self.assertEqual(tokens["refresh_token"], "old-refresh")

    def test_change_password_verifies_current_password_and_sends_it_to_auth(self):
        tokens = change_password(
            {"access_token": "access-token", "refresh_token": "refresh-token", "expires_at": 4_000_000_000},
            "CurrentPass123",
            "NewPassword123",
            "NewPassword123",
        )
        self.assertEqual(self.client.auth.login_args["password"], "CurrentPass123")
        self.assertEqual(self.client.auth.update_args["current_password"], "CurrentPass123")
        self.assertEqual(self.client.auth.update_args["password"], "NewPassword123")
        self.assertEqual(tokens["access_token"], "access-token")

    def test_change_password_does_not_update_when_current_password_is_wrong(self):
        with self.assertRaises(AuthServiceError):
            change_password(
                {"access_token": "access-token", "refresh_token": "refresh-token", "expires_at": 4_000_000_000},
                "WrongPass123",
                "NewPassword123",
                "NewPassword123",
            )
        self.assertIsNone(self.client.auth.update_args)

    def test_password_recovery_request_uses_fixed_callback_and_normalizes_email(self):
        self.assertTrue(request_password_recovery(" AN@example.com "))
        self.assertEqual(
            self.client.auth.reset_args,
            ("an@example.com", {"redirect_to": PASSWORD_RECOVERY_REDIRECT_URL}),
        )

    def test_password_recovery_send_errors_do_not_leak_account_state(self):
        self.client.auth.reset_error = ValueError("mail provider detail")
        self.assertFalse(request_password_recovery("an@example.com"))

    def test_recovery_session_requires_verified_recovery_amr_and_matching_subject(self):
        verified = verify_password_recovery({
            "access_token": "recovery-access",
            "refresh_token": "recovery-refresh",
        })
        self.assertEqual(verified["user_id"], "user-1")

        self.client.auth.claims["amr"] = [{"method": "password"}]
        with self.assertRaises(AuthServiceError):
            verify_password_recovery({
                "access_token": "normal-access",
                "refresh_token": "normal-refresh",
            })

        self.client.auth.claims["amr"] = [{"method": "recovery"}]
        self.client.auth.claims["sub"] = "another-user"
        with self.assertRaises(AuthServiceError):
            verify_password_recovery({
                "access_token": "recovery-access",
                "refresh_token": "recovery-refresh",
            })

        self.client.auth.claims["sub"] = "user-1"
        self.client.auth.claims["exp"] = 1
        with self.assertRaises(AuthServiceError):
            verify_password_recovery({
                "access_token": "expired-access",
                "refresh_token": "expired-refresh",
            })

    def test_recovery_password_update_validates_pair_then_revokes_refresh_sessions(self):
        tokens = {
            "access_token": "recovery-access",
            "refresh_token": "recovery-refresh",
        }
        user_id = reset_password_with_recovery(tokens, "NewPassword123", "NewPassword123")
        self.assertEqual(user_id, "user-1")
        self.assertEqual(self.client.auth.update_args, {"password": "NewPassword123"})
        self.assertEqual(self.client.auth.sign_out_options, {"scope": "global"})

    def test_recovery_does_not_update_when_password_pair_is_invalid(self):
        with self.assertRaises(AuthServiceError):
            reset_password_with_recovery(
                {"access_token": "recovery-access", "refresh_token": "recovery-refresh"},
                "NewPassword123",
                "AnotherPassword123",
            )
        self.assertIsNone(self.client.auth.update_args)

