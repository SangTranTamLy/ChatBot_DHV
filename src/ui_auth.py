"""Session-only registration/login for the requested prototype; no email or persistence."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import MutableMapping

import streamlit as st


def _identity(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def valid_email(email: str) -> bool:
    return len(email.strip()) <= 254 and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def register_account(accounts: MutableMapping, name: str, email: str,
                     password: str, confirmation: str) -> str | None:
    """Validate before storing a salted password hash in this session only."""
    name = unicodedata.normalize("NFC", name.strip())
    email = email.strip()
    if not 2 <= len(name) <= 60 or "@" in name:
        return "Tên cần từ 2 đến 60 ký tự và không chứa ký tự @."
    if not valid_email(email):
        return "Bạn nhập địa chỉ email hợp lệ nhé."
    if not 8 <= len(password) <= 128:
        return "Mật khẩu cần từ 8 đến 128 ký tự."
    if password != confirmation:
        return "Mật khẩu nhập lại chưa khớp."
    if any(_identity(row["name"]) == _identity(name) or _identity(row["email"]) == _identity(email)
           for row in accounts.values()):
        return "Tên hoặc email này đã được đăng ký trong phiên hiện tại."
    salt = secrets.token_bytes(16)
    accounts[_identity(email)] = {
        "name": name, "email": email, "salt": salt,
        "password_hash": hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000),
    }
    return None


def authenticate(accounts: MutableMapping, identifier: str, password: str) -> dict[str, str] | None:
    if not identifier.strip() or not 8 <= len(password) <= 128:
        return None
    wanted = _identity(identifier)
    account = next((row for row in accounts.values()
                    if wanted in {_identity(row["name"]), _identity(row["email"])}), None)
    if account is None:
        return None
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), account["salt"], 310_000)
    if not hmac.compare_digest(digest, account["password_hash"]):
        return None
    return {"name": account["name"], "email": account["email"]}


def logout() -> None:
    st.session_state.auth_user = None
    st.session_state.auth_view = None


def init_auth() -> None:
    st.session_state.setdefault("auth_accounts", {})
    st.session_state.setdefault("auth_user", None)
    st.session_state.setdefault("auth_view", None)


def open_auth(view: str = "login") -> None:
    st.session_state.auth_view = view


def _close_auth() -> None:
    st.session_state.auth_view = None


def _switch_auth(label: str, view: str, *, key: str, icon: str | None = None) -> None:
    if st.button(label, type="tertiary", key=key, width="content", icon=icon):
        open_auth(view)
        st.rerun()


def _auth_footer(prompt: str, label: str, view: str, *, key: str) -> None:
    with st.container(horizontal=True, horizontal_alignment="center", vertical_alignment="center",
                      gap="xsmall", key="auth_footer"):
        st.caption(prompt, width="content")
        _switch_auth(label, view, key=key)


def _auth_input(label: str, key: str, icon: str, *, password: bool = False,
                placeholder: str | None = None, max_chars: int = 128) -> str:
    return st.text_input(label, key=key, type="password" if password else "default",
                         placeholder=placeholder or label, icon=f":material/{icon}:",
                         max_chars=max_chars, label_visibility="collapsed")


@st.dialog("DHV · Trợ lý tuyển sinh", icon=":material/school:", on_dismiss=_close_auth)
def render_auth_dialog() -> None:
    """Shared modal shell and inputs; the logo and native password toggles stay intact."""
    view = st.session_state.auth_view
    titles = {"login": "Đăng nhập", "register": "Đăng ký tài khoản", "forgot": "Quên mật khẩu"}
    descriptions = {
        "login": "Đăng nhập để sử dụng trợ lý tuyển sinh DHV.",
        "register": "Tạo tài khoản để sử dụng trợ lý tuyển sinh DHV.",
        "forgot": "Nhập email của bạn để nhận liên kết đặt lại mật khẩu.",
    }
    with st.container(key="auth_panel"):
        with st.container(key="auth_intro", gap="xsmall"):
            st.header(titles[view])
            if view == "login":
                st.markdown("Chào mừng bạn quay trở lại!")
            st.caption(descriptions[view])
        if view == "login":
            with st.form("login_form", clear_on_submit=True, border=False):
                identifier = _auth_input("Tên hoặc email", "login_identifier", "mail",
                                          placeholder="Email hoặc tên đăng nhập", max_chars=254)
                password = _auth_input("Mật khẩu", "login_password", "lock", password=True)
                submitted = st.form_submit_button("Đăng nhập", key="submit_login", type="primary", width="stretch")
            if submitted:
                if not identifier.strip() or not password:
                    st.error("Bạn nhập tên/email và mật khẩu nhé.")
                elif "@" in identifier and not valid_email(identifier):
                    st.error("Bạn nhập địa chỉ email hợp lệ nhé.")
                else:
                    user = authenticate(st.session_state.auth_accounts, identifier, password)
                    if user is None:
                        st.error("Tên/email hoặc mật khẩu chưa đúng.")
                    else:
                        st.session_state.auth_user = user
                        st.session_state.auth_login_notice = True
                        _close_auth()
                        st.rerun()
            with st.container(horizontal=True, horizontal_alignment="right", key="auth_secondary"):
                _switch_auth("Quên mật khẩu?", "forgot", key="auth_forgot")
            st.divider()
            _auth_footer("Chưa có tài khoản?", "Đăng ký ngay", "register", key="auth_register")
        elif view == "register":
            with st.form("register_form", clear_on_submit=True, border=False):
                name = _auth_input("Họ và tên", "register_name", "person", max_chars=60)
                email = _auth_input("Email", "register_email", "mail", max_chars=254)
                password = _auth_input("Mật khẩu", "register_password", "lock", password=True,
                                        placeholder="Mật khẩu (tối thiểu 8 ký tự)")
                confirmation = _auth_input("Xác nhận mật khẩu", "register_confirmation", "lock_reset", password=True)
                submitted = st.form_submit_button("Đăng ký", key="submit_register", type="primary", width="stretch")
            if submitted:
                error = register_account(st.session_state.auth_accounts, name, email, password, confirmation)
                if error:
                    st.error(error)
                else:
                    st.success("Đăng ký thành công. Bạn có thể đăng nhập ngay.")
            st.divider()
            _auth_footer("Đã có tài khoản?", "Đăng nhập", "login", key="auth_back_login")
        else:
            with st.form("forgot_form", clear_on_submit=True, border=False):
                email = _auth_input("Email", "forgot_email", "mail", max_chars=254)
                submitted = st.form_submit_button("Gửi liên kết đặt lại mật khẩu", key="submit_forgot",
                                                  type="primary", width="stretch")
            if submitted:
                if not valid_email(email):
                    st.error("Bạn nhập địa chỉ email hợp lệ nhé.")
                else:
                    st.success("Yêu cầu hợp lệ. Đây là bản dùng thử nên chưa gửi email đặt lại mật khẩu.")
            st.divider()
            with st.container(horizontal=True, horizontal_alignment="center", key="auth_footer"):
                _switch_auth("Quay lại đăng nhập", "login", key="auth_back_login", icon=":material/arrow_back:")
        with st.container(key="auth_note"):
            st.caption("Bản dùng thử: chưa gửi email thực tế." if view == "forgot"
                       else "Tài khoản dùng thử chỉ được giữ trong phiên đang mở.")
