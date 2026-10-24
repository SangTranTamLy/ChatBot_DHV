"""Supabase Auth integration for the Streamlit account flow.

The module keeps Supabase's mutable auth client scoped to one operation. Only
the short-lived access/refresh tokens and verified profile are kept in the
server-side Streamlit session; passwords are never persisted by this module.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from collections.abc import Mapping
from typing import Any, Callable

import streamlit as st


class AuthServiceError(Exception):
    """A safe, user-facing authentication error."""


class AuthConfigurationError(AuthServiceError):
    """Supabase connection settings are missing or the SDK is unavailable."""


_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")
_CLIENT_FACTORY: Callable[..., Any] | None = None


def _read_setting(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value is None or not str(value).strip():
        value = os.getenv(name)
    return str(value).strip() if value is not None and str(value).strip() else None


def get_supabase_config() -> tuple[str, str] | None:
    """Return the public project URL and publishable/anon key when configured."""
    url = _read_setting("SUPABASE_URL")
    key = _read_setting("SUPABASE_PUBLISHABLE_KEY") or _read_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return url, key


def is_supabase_configured() -> bool:
    return get_supabase_config() is not None


def validate_name(value: str) -> str:
    """Normalize a personal name and allow only Unicode letters and spaces."""
    name = unicodedata.normalize("NFC", value.strip())
    if not 2 <= len(name) <= 50:
        raise AuthServiceError("Tên cần có từ 2 đến 50 ký tự.")

    saw_letter = False
    previous_was_letter_or_mark = False
    for character in name:
        category = unicodedata.category(character)
        if category.startswith("L"):
            saw_letter = True
            previous_was_letter_or_mark = True
        elif category.startswith("M") and previous_was_letter_or_mark:
            previous_was_letter_or_mark = True
        elif character == " ":
            previous_was_letter_or_mark = False
        else:
            raise AuthServiceError("Tên chỉ được gồm chữ cái và dấu cách.")

    if not saw_letter:
        raise AuthServiceError("Tên cần có ít nhất một chữ cái.")
    return name


def validate_email(value: str) -> str:
    """Trim and lowercase an email address, enforcing the app's input limits."""
    email = value.strip().lower()
    if len(email) > 254:
        raise AuthServiceError("Địa chỉ email không được dài quá 254 ký tự.")
    if not _EMAIL_RE.fullmatch(email):
        raise AuthServiceError("Địa chỉ email không hợp lệ.")
    return email


def validate_password(value: str) -> str:
    """Validate Auth's minimum length and bcrypt's 72-byte input ceiling."""
    if len(value) < 8:
        raise AuthServiceError("Mật khẩu cần có ít nhất 8 ký tự.")
    try:
        password_bytes = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AuthServiceError("Mật khẩu có ký tự không hợp lệ.") from exc
    if len(password_bytes) > 72:
        raise AuthServiceError("Mật khẩu không được vượt quá 72 byte UTF-8.")
    return value


def validate_password_pair(password: str, confirmation: str) -> None:
    validate_password(password)
    if password != confirmation:
        raise AuthServiceError("Mật khẩu nhập lại chưa khớp.")


def _create_client() -> Any:
    config = get_supabase_config()
    if config is None:
        raise AuthConfigurationError("Chưa cấu hình kết nối Supabase cho ứng dụng.")
    if _CLIENT_FACTORY is not None:
        return _CLIENT_FACTORY(*config)
    try:
        from supabase import create_client
        from supabase.lib.client_options import SyncClientOptions
    except ImportError as exc:
        raise AuthConfigurationError(
            "Chưa cài thư viện Supabase. Cài các dependencies của dự án rồi thử lại."
        ) from exc

    # Prevent the SDK from starting a refresh thread or persisting auth state
    # outside the current Streamlit session.
    options = SyncClientOptions(auto_refresh_token=False, persist_session=False)
    return create_client(*config, options=options)


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _auth_session(client: Any) -> Any:
    auth = client.auth
    getter = getattr(auth, "get_session", None)
    return getter() if callable(getter) else None


def _token_state(session: Any) -> dict[str, Any]:
    access_token = _value(session, "access_token")
    refresh_token = _value(session, "refresh_token")
    if not access_token or not refresh_token:
        raise AuthServiceError("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")
    expires_at = _value(session, "expires_at")
    if not expires_at:
        expires_in = _value(session, "expires_in")
        expires_at = int(time.time()) + int(expires_in or 3600)
    return {
        "access_token": str(access_token),
        "refresh_token": str(refresh_token),
        "expires_at": int(expires_at),
    }


def _user_from_response(response: Any) -> Any:
    user = _value(response, "user")
    if user is not None:
        return user
    session = _value(response, "session")
    return _value(session, "user") if session is not None else None


def _profile_name(client: Any, user_id: str) -> str:
    result = (
        client.table("profiles")
        .select("display_name")
        .eq("id", user_id)
        .single()
        .execute()
    )
    data = _value(result, "data")
    name = _value(data, "display_name")
    if not isinstance(name, str) or not name:
        raise AuthServiceError("Không tải được hồ sơ tài khoản. Vui lòng thử đăng nhập lại.")
    return name


def _authenticated_user(client: Any, user: Any) -> dict[str, str]:
    user_id = _value(user, "id")
    email = _value(user, "email")
    if not user_id or not email:
        raise AuthServiceError("Không xác nhận được tài khoản. Vui lòng đăng nhập lại.")
    return {
        "id": str(user_id),
        "name": _profile_name(client, str(user_id)),
        "email": str(email).strip().lower(),
    }


def _safe_sign_out(client: Any) -> None:
    try:
        client.auth.sign_out()
    except Exception:
        pass


def register_user(name: str, email: str, password: str, confirmation: str) -> None:
    """Create an Auth user and let the database trigger create its profile."""
    clean_name = validate_name(name)
    clean_email = validate_email(email)
    validate_password_pair(password, confirmation)
    client = _create_client()
    try:
        response = client.auth.sign_up({
            "email": clean_email,
            "password": password,
            "options": {"data": {"display_name": clean_name}},
        })
        # Confirm-email is disabled by project configuration. Discard any
        # session returned by sign_up because signup must not log the user in.
        if _value(response, "session") is not None:
            _safe_sign_out(client)
    except AuthServiceError:
        raise
    except Exception as exc:
        raise AuthServiceError(
            "Đăng ký chưa thành công. Hãy kiểm tra thông tin hoặc thử lại sau."
        ) from exc


def login_user(email: str, password: str) -> tuple[dict[str, str], dict[str, Any]]:
    clean_email = validate_email(email)
    validate_password(password)
    client = _create_client()
    try:
        response = client.auth.sign_in_with_password({"email": clean_email, "password": password})
        user = _user_from_response(response)
        session = _value(response, "session") or _auth_session(client)
        if user is None or session is None:
            raise AuthServiceError("Email hoặc mật khẩu chưa đúng.")
        auth_user = _authenticated_user(client, user)
        return auth_user, _token_state(session)
    except AuthServiceError:
        raise
    except Exception as exc:
        # Keep the same message for unknown email, wrong password, and account
        # state errors so the login screen does not confirm account existence.
        raise AuthServiceError("Email hoặc mật khẩu chưa đúng.") from exc


def _client_for_session(tokens: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    client = _create_client()
    try:
        client.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        refreshed = _auth_session(client)
        return client, _token_state(refreshed or tokens)
    except Exception as exc:
        raise AuthServiceError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.") from exc


def restore_auth_session(tokens: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    """Refresh if needed, verify the user with Auth, and reload their profile."""
    client, updated_tokens = _client_for_session(tokens)
    try:
        response = client.auth.get_user()
        user = _value(response, "user") or response
        auth_user = _authenticated_user(client, user)
        return auth_user, updated_tokens
    except Exception as exc:
        raise AuthServiceError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.") from exc


def change_password(tokens: Mapping[str, Any], current_password: str,
                    new_password: str, confirmation: str) -> dict[str, Any]:
    validate_password(current_password)
    validate_password_pair(new_password, confirmation)
    if current_password == new_password:
        raise AuthServiceError("Mật khẩu mới cần khác mật khẩu hiện tại.")
    client, updated_tokens = _client_for_session(tokens)
    try:
        current_user_response = client.auth.get_user()
        current_user = _value(current_user_response, "user") or current_user_response
        user_id = _value(current_user, "id")
        email = _value(current_user, "email")
        if not user_id or not email:
            raise AuthServiceError("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")

        # Verify the password through Auth before updating it. The server-side
        # current_password check remains enabled as a second enforcement layer.
        reauthenticated = client.auth.sign_in_with_password({
            "email": str(email),
            "password": current_password,
        })
        reauthenticated_user = _user_from_response(reauthenticated)
        if str(_value(reauthenticated_user, "id") or "") != str(user_id):
            raise AuthServiceError("Mật khẩu hiện tại chưa đúng hoặc phiên đã hết hạn.")

        client.auth.update_user({
            "password": new_password,
            "current_password": current_password,
        })
        return _token_state(_auth_session(client) or updated_tokens)
    except AuthServiceError:
        raise
    except Exception as exc:
        raise AuthServiceError(
            "Không đổi được mật khẩu. Hãy kiểm tra mật khẩu hiện tại và thử lại."
        ) from exc


def logout_user(tokens: Mapping[str, Any] | None) -> None:
    """Revoke the current refresh session when possible; callers always clear state."""
    if not tokens:
        return
    try:
        client, _ = _client_for_session(tokens)
        client.auth.sign_out()
    except Exception:
        # Local logout must work even if the network or Supabase is unavailable.
        return
