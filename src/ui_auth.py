"""Supabase-backed login and registration dialogs for Streamlit."""

from __future__ import annotations

import logging
import threading
import time

import streamlit as st

from src.supabase_auth import (
    AuthServiceError,
    PASSWORD_RECOVERY_SESSION_TTL_SECONDS,
    is_supabase_configured,
    login_user,
    logout_user,
    register_user,
    request_password_recovery,
    reset_password_with_recovery,
    restore_auth_session,
    validate_email,
    validate_name,
    validate_password,
    verify_password_recovery,
)


_REGISTRATION_PASSWORD_KEY = "register_password_live"
_REGISTRATION_CONFIRMATION_KEY = "register_confirmation_live"
_LOGIN_SUCCESS_DISPLAY_SECONDS = 2
_RECOVERY_BRIDGE_KEY = "password_recovery_link_bridge"
_RECOVERY_PASSWORD_KEY = "password_recovery_password_live"
_RECOVERY_CONFIRMATION_KEY = "password_recovery_confirmation_live"
_RECOVERY_NOTICE = (
    "Đã tiếp nhận yêu cầu. Nếu email này đã đăng ký, liên kết đặt lại mật khẩu "
    "sẽ được gửi đến hộp thư của bạn. Vui lòng kiểm tra cả mục Thư rác."
)


def _dispatch_password_recovery(email: str) -> None:
    """Send the recovery request off the Streamlit render path.

    Supabase may take several seconds to respond. The UI can show its generic
    privacy-preserving acknowledgement immediately while this daemon worker
    performs the request without touching Streamlit session state.
    """

    def _send() -> None:
        try:
            request_password_recovery(email)
        except Exception as exc:
            # The visible response intentionally stays the same for all valid
            # addresses. Keep logs free of email addresses and provider payloads.
            logging.getLogger(__name__).warning(
                "Password recovery dispatch failed (%s)", type(exc).__name__
            )

    threading.Thread(
        target=_send,
        name="password-recovery-dispatch",
        daemon=True,
    ).start()

_LIVE_PASSWORD_HTML = """
<div class="password-control">
  <div class="input-shell">
    <svg class="leading-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="10" width="14" height="11" rx="2"></rect>
      <path d="M8 10V7a4 4 0 0 1 8 0v3"></path>
      <path d="M12 14v3"></path>
    </svg>
    <input id="password" type="password" maxlength="72" autocomplete="new-password"
           placeholder="Mật khẩu" aria-label="Mật khẩu">
    <span id="counter" class="counter" hidden></span>
    <button id="toggle" class="toggle" type="button" aria-label="Hiện mật khẩu" aria-pressed="false">
      <svg class="eye-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"></path>
        <circle cx="12" cy="12" r="3"></circle>
      </svg>
      <svg class="eye-off-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 3l18 18"></path>
        <path d="M10.6 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a16 16 0 0 1-3.1 3.9"></path>
        <path d="M6.2 6.3C3.5 8.2 2 12 2 12s3.6 7 10 7c1.2 0 2.3-.2 3.3-.6"></path>
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path>
      </svg>
    </button>
  </div>
  <div id="feedback" class="feedback" aria-live="polite" hidden>
    <span id="level" class="badge"></span>
    <span id="meter" class="meter" aria-hidden="true">
      <i></i><i></i><i></i><i></i>
    </span>
    <span id="message" class="message"></span>
  </div>
</div>
"""

_LIVE_PASSWORD_CSS = """
.password-control, .password-control * { box-sizing: border-box; }
.password-control { width: 100%; font-family: "Segoe UI", Arial, sans-serif; color: #10264d; }
.input-shell {
  position: relative; display: flex; align-items: center; gap: 12px;
  width: 100%; height: 52px; padding: 0 12px;
  border: 1px solid #d7e2f2; border-radius: 12px; background: #fffffff5;
  box-shadow: 0 1px 2px #10264d03; transition: border-color 150ms, box-shadow 150ms;
}
.input-shell:focus-within { border-color: #087bff; box-shadow: 0 0 0 3px #087bff15; }
.leading-icon { width: 16px; height: 16px; flex: 0 0 16px; fill: none; stroke: #718099; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.input-shell input {
  width: 100%; min-width: 0; height: 100%; padding: 0 48px 0 0;
  border: 0; outline: 0; background: transparent; color: #10264d;
  font: 400 15px/1.5 "Segoe UI", Arial, sans-serif;
}
.input-shell input::placeholder { color: #718099; opacity: 1; }
.counter { position: absolute; right: 48px; bottom: 2px; color: #718099; font-size: 11px; line-height: 14px; pointer-events: none; }
.toggle { display: flex; flex: 0 0 22px; align-items: center; justify-content: center; width: 22px; height: 28px; margin: 0; padding: 0; border: 0; background: transparent; color: #10264d; cursor: pointer; }
.eye-icon, .eye-off-icon { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.eye-icon { display: none; }
.eye-off-icon { display: block; }
.toggle[aria-pressed="true"] .eye-icon { display: block; }
.toggle[aria-pressed="true"] .eye-off-icon { display: none; }
.feedback { display: flex; align-items: center; gap: 8px; min-height: 22px; margin-top: 7px; }
.feedback[hidden], .counter[hidden] { display: none; }
.badge { flex: 0 0 auto; padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 600; line-height: 16px; }
.meter { display: flex; flex: 0 0 auto; gap: 3px; }
.meter i { width: 9px; height: 4px; border-radius: 4px; background: #dbe4f0; }
.message { min-width: 0; color: #65758d; font-size: 11px; line-height: 1.4; }
.feedback[data-level="weak"] .badge { color: #a65300; background: #fff1d8; }
.feedback[data-level="medium"] .badge { color: #075bb5; background: #e8f2ff; }
.feedback[data-level="strong"] .badge { color: #137547; background: #e5f7ee; }
.feedback[data-level="invalid"] .badge { color: #a71931; background: #ffe8ec; }
.meter[data-level="weak"] i:nth-child(-n+1) { background: #ed9b25; }
.meter[data-level="medium"] i:nth-child(-n+2) { background: #2782e6; }
.meter[data-level="strong"] i { background: #20a365; }
.meter[data-level="invalid"] i:nth-child(-n+1) { background: #d9364f; }
@media (max-width: 520px) {
  .feedback { gap: 6px; }
  .message { font-size: 10px; }
}
"""

_LIVE_PASSWORD_JS = """
export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const input = parentElement.querySelector("#password");
  const counter = parentElement.querySelector("#counter");
  const feedback = parentElement.querySelector("#feedback");
  const badge = parentElement.querySelector("#level");
  const meter = parentElement.querySelector("#meter");
  const message = parentElement.querySelector("#message");
  const toggle = parentElement.querySelector("#toggle");
  if (!input || !counter || !feedback || !badge || !meter || !message || !toggle) return;

  const incomingValue = typeof data?.value === "string" ? data.value : "";
  if (input.value !== incomingValue) input.value = incomingValue;

  function getFeedback(value) {
    const characters = Array.from(value);
    const byteLength = new TextEncoder().encode(value).length;
    if (characters.length < 8) {
      return { level: "weak", label: "Yếu", message: "Cần ít nhất 8 ký tự." };
    }
    if (byteLength > 72) {
      return { level: "invalid", label: "Vượt giới hạn", message: "Mật khẩu tối đa 72 byte UTF-8." };
    }

    const hasLower = characters.some(char => char !== char.toUpperCase() && char === char.toLowerCase());
    const hasUpper = characters.some(char => char !== char.toLowerCase() && char === char.toUpperCase());
    const hasDigit = characters.some(char => /\\p{N}/u.test(char));
    const hasSymbol = characters.some(char => !/[\\p{L}\\p{M}\\p{N}]/u.test(char));
    const types = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length;

    if (characters.length >= 16 || (characters.length >= 12 && types >= 3)) {
      return { level: "strong", label: "Mạnh", message: "Mật khẩu đủ dài và khó đoán hơn." };
    }
    if (types >= 2) {
      return { level: "medium", label: "Khá", message: "Thêm độ dài hoặc kiểu ký tự để khó đoán hơn." };
    }
    return { level: "weak", label: "Yếu", message: "Nên dùng 12+ ký tự và phối hợp chữ, số, ký hiệu." };
  }

  function renderFeedback(visible) {
    const value = input.value;
    const hasValue = value.length > 0;
    const show = visible && hasValue;
    counter.textContent = `${Array.from(value).length}/72`;
    counter.hidden = !show;
    feedback.hidden = !show;
    if (!show) return;
    const result = getFeedback(value);
    feedback.dataset.level = result.level;
    meter.dataset.level = result.level;
    badge.textContent = result.label;
    message.textContent = result.message;
  }

  renderFeedback(input.matches(":focus"));
  input.oninput = () => {
    setStateValue("value", input.value);
    renderFeedback(true);
  };
  input.onfocus = () => renderFeedback(true);
  input.onblur = () => renderFeedback(false);
  toggle.onmousedown = event => event.preventDefault();
  toggle.onclick = () => {
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    toggle.setAttribute("aria-label", showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    toggle.setAttribute("aria-pressed", String(showPassword));
    input.focus();
    renderFeedback(true);
  };
}
"""

_LIVE_PASSWORD_INPUT = st.components.v2.component(
    "dhv_registration_live_password",
    html=_LIVE_PASSWORD_HTML,
    css=_LIVE_PASSWORD_CSS,
    js=_LIVE_PASSWORD_JS,
)

_LIVE_CONFIRMATION_HTML = """
<div class="confirm-control">
  <div class="input-shell">
    <svg class="leading-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9"></circle>
      <path d="M12 7v5l3 2"></path>
      <path d="M5 5 3 8h3"></path>
    </svg>
    <input id="confirmation" type="password" maxlength="72" autocomplete="new-password"
           placeholder="Nhập lại mật khẩu" aria-label="Nhập lại mật khẩu">
    <button id="toggle-confirmation" class="toggle" type="button" aria-label="Hiện mật khẩu" aria-pressed="false">
      <svg class="eye-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"></path>
        <circle cx="12" cy="12" r="3"></circle>
      </svg>
      <svg class="eye-off-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 3l18 18"></path>
        <path d="M10.6 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a16 16 0 0 1-3.1 3.9"></path>
        <path d="M6.2 6.3C3.5 8.2 2 12 2 12s3.6 7 10 7c1.2 0 2.3-.2 3.3-.6"></path>
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path>
      </svg>
    </button>
  </div>
  <div id="match-status" class="match-status" aria-live="polite" hidden></div>
</div>
"""

_LIVE_CONFIRMATION_CSS = """
.confirm-control, .confirm-control * { box-sizing: border-box; }
.confirm-control { width: 100%; font-family: "Segoe UI", Arial, sans-serif; color: #10264d; }
.input-shell {
  position: relative; display: flex; align-items: center; gap: 12px;
  width: 100%; height: 52px; padding: 0 12px;
  border: 1px solid #d7e2f2; border-radius: 12px; background: #fffffff5;
  box-shadow: 0 1px 2px #10264d03; transition: border-color 150ms, box-shadow 150ms;
}
.input-shell:focus-within { border-color: #087bff; box-shadow: 0 0 0 3px #087bff15; }
.leading-icon { width: 16px; height: 16px; flex: 0 0 16px; fill: none; stroke: #718099; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.input-shell input {
  width: 100%; min-width: 0; height: 100%; padding: 0 36px 0 0;
  border: 0; outline: 0; background: transparent; color: #10264d;
  font: 400 15px/1.5 "Segoe UI", Arial, sans-serif;
}
.input-shell input::placeholder { color: #718099; opacity: 1; }
.toggle { display: flex; flex: 0 0 22px; align-items: center; justify-content: center; width: 22px; height: 28px; margin: 0; padding: 0; border: 0; background: transparent; color: #10264d; cursor: pointer; }
.eye-icon, .eye-off-icon { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.eye-icon { display: none; }
.eye-off-icon { display: block; }
.toggle[aria-pressed="true"] .eye-icon { display: block; }
.toggle[aria-pressed="true"] .eye-off-icon { display: none; }
.match-status { min-height: 20px; margin-top: 6px; font-size: 12px; line-height: 20px; }
.match-status[hidden] { display: none; }
.match-status[data-match="true"] { color: #16834b; }
.match-status[data-match="false"] { color: #c52842; }
"""

_LIVE_CONFIRMATION_JS = """
export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const input = parentElement.querySelector("#confirmation");
  const status = parentElement.querySelector("#match-status");
  const toggle = parentElement.querySelector("#toggle-confirmation");
  if (!input || !status || !toggle) return;

  const incomingValue = typeof data?.value === "string" ? data.value : "";
  const password = typeof data?.password === "string" ? data.password : "";
  if (input.value !== incomingValue) input.value = incomingValue;

  function renderStatus() {
    if (!input.value) {
      status.hidden = true;
      return;
    }
    const matches = input.value === password;
    status.hidden = false;
    status.dataset.match = String(matches);
    status.textContent = matches ? "Mật khẩu khớp." : "Mật khẩu chưa khớp.";
  }

  renderStatus();
  input.oninput = () => {
    setStateValue("value", input.value);
    renderStatus();
  };
  toggle.onmousedown = event => event.preventDefault();
  toggle.onclick = () => {
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    toggle.setAttribute("aria-label", showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    toggle.setAttribute("aria-pressed", String(showPassword));
    input.focus();
  };
}
"""

_LIVE_CONFIRMATION_INPUT = st.components.v2.component(
    "dhv_registration_live_confirmation",
    html=_LIVE_CONFIRMATION_HTML,
    css=_LIVE_CONFIRMATION_CSS,
    js=_LIVE_CONFIRMATION_JS,
)

_RECOVERY_BRIDGE_HTML = '<div aria-hidden="true" style="display:none"></div>'
_RECOVERY_BRIDGE_JS = """
const processedParents = new WeakSet();

export default function (component) {
  const { parentElement, setStateValue } = component;
  if (processedParents.has(parentElement)) return;
  processedParents.add(parentElement);

  const rawFragment = window.location.hash || "";
  const values = new URLSearchParams(rawFragment.startsWith("#")
    ? rawFragment.slice(1)
    : rawFragment);
  const payload = {
    type: values.get("type") || "",
    access_token: values.get("access_token") || "",
    refresh_token: values.get("refresh_token") || "",
    error_code: values.get("error_code") || values.get("error") || "",
  };

  // Remove Supabase's implicit-flow credentials from the address bar before
  // forwarding them to the Streamlit server-side session.
  if (rawFragment) {
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search
    );
  }
  setStateValue("payload", payload);
}
"""

_RECOVERY_LINK_BRIDGE = st.components.v2.component(
    "dhv_password_recovery_link_bridge",
    html=_RECOVERY_BRIDGE_HTML,
    js=_RECOVERY_BRIDGE_JS,
)


_PASSWORD_KEYS = (
    "login_password",
    "register_password",
    "register_confirmation",
    _REGISTRATION_PASSWORD_KEY,
    _REGISTRATION_CONFIRMATION_KEY,
    "change_current_password",
    "change_new_password",
    "change_password_confirmation",
    _RECOVERY_PASSWORD_KEY,
    _RECOVERY_CONFIRMATION_KEY,
)


def _clear_password_inputs() -> None:
    for key in _PASSWORD_KEYS:
        st.session_state.pop(key, None)


def _clear_auth_state() -> None:
    st.session_state.auth_user = None
    st.session_state.auth_tokens = None
    st.session_state.auth_view = None
    _clear_password_inputs()


def logout() -> None:
    tokens = st.session_state.get("auth_tokens")
    logout_user(tokens)
    _clear_auth_state()


def init_auth() -> None:
    """Initialize the UI state and refresh a session when it is near expiry."""
    # Remove accounts created by the old in-session prototype. They are not
    # Supabase users and must not remain usable after the auth upgrade.
    st.session_state.pop("auth_accounts", None)
    st.session_state.pop("register_password", None)
    st.session_state.pop("register_confirmation", None)
    st.session_state.setdefault("auth_user", None)
    st.session_state.setdefault("auth_tokens", None)
    st.session_state.setdefault("auth_view", None)
    tokens = st.session_state.get("auth_tokens")
    if not tokens:
        st.session_state.auth_user = None
        return

    try:
        expires_at = int(tokens.get("expires_at", 0))
    except (AttributeError, TypeError, ValueError):
        expires_at = 0
    if st.session_state.get("auth_user") is not None and expires_at > int(time.time()):
        return

    try:
        user, updated_tokens = restore_auth_session(tokens)
    except AuthServiceError:
        _clear_auth_state()
        st.session_state.auth_session_expired_notice = True
    except Exception:
        _clear_auth_state()
        st.session_state.auth_session_expired_notice = True
    else:
        st.session_state.auth_user = user
        st.session_state.auth_tokens = updated_tokens


def open_auth(view: str = "login") -> None:
    if view in {"login", "register", "forgot"}:
        st.session_state.auth_view = view


def _close_auth() -> None:
    st.session_state.auth_view = None
    _clear_password_inputs()
    st.session_state.pop("password_recovery_request_result", None)


def _recovery_password_value(key: str) -> str:
    component_state = st.session_state.get(key, {})
    value = component_state.get("value", "") if isinstance(component_state, dict) else ""
    return value if isinstance(value, str) else ""


def _clear_recovery_form_error() -> None:
    st.session_state.pop("password_recovery_form_error", None)


def _recovery_password_changed() -> None:
    _clear_recovery_form_error()


def _recovery_confirmation_changed() -> None:
    _clear_recovery_form_error()


def _recovery_password_input() -> str:
    value = _recovery_password_value(_RECOVERY_PASSWORD_KEY)
    result = _LIVE_PASSWORD_INPUT(
        key=_RECOVERY_PASSWORD_KEY,
        data={"value": value},
        default={"value": ""},
        on_value_change=_recovery_password_changed,
        width="stretch",
        height="content",
    )
    result_value = getattr(result, "value", None)
    return result_value if isinstance(result_value, str) else value


def _recovery_confirmation_input(password: str) -> str:
    value = _recovery_password_value(_RECOVERY_CONFIRMATION_KEY)
    result = _LIVE_CONFIRMATION_INPUT(
        key=_RECOVERY_CONFIRMATION_KEY,
        data={"value": value, "password": password},
        default={"value": ""},
        on_value_change=_recovery_confirmation_changed,
        width="stretch",
        height="content",
    )
    result_value = getattr(result, "value", None)
    return result_value if isinstance(result_value, str) else value


def _accept_recovery_link_payload() -> None:
    bridge_state = st.session_state.get(_RECOVERY_BRIDGE_KEY, {})
    payload = bridge_state.get("payload") if isinstance(bridge_state, dict) else None
    st.session_state.password_recovery_link_checked = True
    if not isinstance(payload, dict):
        st.session_state.password_recovery_link_error = True
        st.session_state.pop(_RECOVERY_BRIDGE_KEY, None)
        return

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if (
        payload.get("type") != "recovery"
        or not isinstance(access_token, str)
        or not isinstance(refresh_token, str)
        or not access_token
        or not refresh_token
    ):
        st.session_state.password_recovery_link_error = True
        st.session_state.pop(_RECOVERY_BRIDGE_KEY, None)
        return

    st.session_state.password_recovery_tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    st.session_state.password_recovery_link_error = False
    # Keep the credentials in only one server-side state key.
    st.session_state.pop(_RECOVERY_BRIDGE_KEY, None)


def _clear_password_recovery_state(*, keep_status: bool = False) -> None:
    for key in (
        "password_recovery_link_checked",
        "password_recovery_link_error",
        "password_recovery_tokens",
        "password_recovery_verified_user_id",
        "password_recovery_expires_at",
        "password_recovery_started_at",
        "password_recovery_form_error",
        _RECOVERY_BRIDGE_KEY,
    ):
        st.session_state.pop(key, None)
    _clear_password_inputs()
    if not keep_status:
        st.session_state.pop("password_recovery_status", None)


def _leave_password_recovery(view: str = "login") -> None:
    _clear_password_recovery_state()
    st.session_state.auth_view = view
    st.query_params.clear()
    st.rerun()


def _submit_password_recovery() -> None:
    tokens = st.session_state.get("password_recovery_tokens")
    password = _recovery_password_value(_RECOVERY_PASSWORD_KEY)
    confirmation = _recovery_password_value(_RECOVERY_CONFIRMATION_KEY)
    try:
        user_id = reset_password_with_recovery(tokens or {}, password, confirmation)
    except AuthServiceError as exc:
        st.session_state.password_recovery_form_error = str(exc)
        return
    except Exception:
        st.session_state.password_recovery_form_error = (
            "Không thể đặt lại mật khẩu lúc này. Hãy thử yêu cầu liên kết mới."
        )
        return

    current_user = st.session_state.get("auth_user")
    if isinstance(current_user, dict) and str(current_user.get("id") or "") == user_id:
        _clear_auth_state()
    _clear_password_recovery_state(keep_status=True)
    st.session_state.password_recovery_status = "success"
    st.session_state.password_recovery_success_toast_pending = True


def render_password_recovery_page() -> None:
    """Handle the local Supabase callback without restoring a normal app session."""

    st.session_state.setdefault("password_recovery_link_checked", False)
    st.session_state.setdefault("password_recovery_link_error", False)
    st.session_state.setdefault("password_recovery_tokens", None)
    st.session_state.setdefault("password_recovery_status", None)
    st.title("Đặt lại mật khẩu")

    if st.session_state.get("password_recovery_status") == "success":
        if st.session_state.pop("password_recovery_success_toast_pending", False):
            st.toast("Mật khẩu đã được đặt lại thành công.", icon=":material/check_circle:", duration=5)
        st.caption("Bạn có thể đăng nhập bằng mật khẩu mới.")
        st.button(
            "Quay lại đăng nhập", key="password_recovery_return_login",
            type="primary", on_click=_leave_password_recovery, args=("login",),
        )
        return

    if not st.session_state.password_recovery_link_checked:
        _RECOVERY_LINK_BRIDGE(
            key=_RECOVERY_BRIDGE_KEY,
            data={},
            default={"payload": None},
            on_payload_change=_accept_recovery_link_payload,
            width="content",
            height="content",
        )
        st.info("Đang xác minh liên kết đặt lại mật khẩu…")
        return

    tokens = st.session_state.get("password_recovery_tokens")
    if st.session_state.get("password_recovery_link_error") or not tokens:
        st.error("Liên kết không hợp lệ hoặc đã hết hạn. Hãy yêu cầu gửi liên kết mới.")
        st.button(
            "Yêu cầu liên kết mới", key="password_recovery_retry",
            type="primary", on_click=_leave_password_recovery, args=("forgot",),
        )
        return

    if not st.session_state.get("password_recovery_verified_user_id"):
        try:
            verified = verify_password_recovery(tokens)
        except AuthServiceError:
            _clear_password_recovery_state()
            st.session_state.password_recovery_link_checked = True
            st.session_state.password_recovery_link_error = True
            st.rerun()
        except Exception:
            _clear_password_recovery_state()
            st.session_state.password_recovery_link_checked = True
            st.session_state.password_recovery_link_error = True
            st.rerun()
        else:
            st.session_state.password_recovery_verified_user_id = verified["user_id"]
            st.session_state.password_recovery_expires_at = min(
                int(verified["expires_at"]),
                int(time.time()) + PASSWORD_RECOVERY_SESSION_TTL_SECONDS,
            )
            st.session_state.password_recovery_started_at = int(time.time())

    expires_at = int(st.session_state.get("password_recovery_expires_at") or 0)
    if expires_at <= int(time.time()):
        _clear_password_recovery_state()
        st.session_state.password_recovery_link_checked = True
        st.session_state.password_recovery_link_error = True
        st.rerun()

    st.caption("Liên kết đã được xác minh. Hãy tạo mật khẩu mới cho tài khoản.")
    password = _recovery_password_input()
    _recovery_confirmation_input(password)
    form_error = st.session_state.get("password_recovery_form_error")
    if form_error:
        st.error(form_error)
    st.button(
        "Xác nhận đổi mật khẩu", key="submit_password_recovery",
        type="primary", width="stretch", on_click=_submit_password_recovery,
    )


def _clear_registration_error(field: str, *dependent_fields: str) -> None:
    errors = dict(st.session_state.get("register_field_errors", {}))
    for key in (field, *dependent_fields):
        errors.pop(key, None)
    st.session_state.register_field_errors = errors
    st.session_state.pop("register_result", None)


def _registration_password_value() -> str:
    component_state = st.session_state.get(_REGISTRATION_PASSWORD_KEY, {})
    value = component_state.get("value", "") if isinstance(component_state, dict) else ""
    return value if isinstance(value, str) else ""


def _registration_confirmation_value() -> str:
    component_state = st.session_state.get(_REGISTRATION_CONFIRMATION_KEY, {})
    value = component_state.get("value", "") if isinstance(component_state, dict) else ""
    return value if isinstance(value, str) else ""


def _registration_password_changed() -> None:
    _clear_registration_error("password", "confirmation")


def _registration_confirmation_changed() -> None:
    _clear_registration_error("confirmation")


def _registration_password_input() -> str:
    value = _registration_password_value()
    result = _LIVE_PASSWORD_INPUT(
        key=_REGISTRATION_PASSWORD_KEY,
        data={"value": value},
        default={"value": ""},
        on_value_change=_registration_password_changed,
        width="stretch",
        height="content",
    )
    result_value = getattr(result, "value", None)
    return result_value if isinstance(result_value, str) else value


def _registration_confirmation_input(password: str) -> str:
    value = _registration_confirmation_value()
    result = _LIVE_CONFIRMATION_INPUT(
        key=_REGISTRATION_CONFIRMATION_KEY,
        data={"value": value, "password": password},
        default={"value": ""},
        on_value_change=_registration_confirmation_changed,
        width="stretch",
        height="content",
    )
    result_value = getattr(result, "value", None)
    return result_value if isinstance(result_value, str) else value


def _submit_registration() -> None:
    name = st.session_state.get("register_name", "")
    email = st.session_state.get("register_email", "")
    password = _registration_password_value()
    confirmation = _registration_confirmation_value()
    errors: dict[str, str] = {}
    for field, value, validator in (
        ("name", name, validate_name),
        ("email", email, validate_email),
        ("password", password, validate_password),
    ):
        try:
            validator(value)
        except AuthServiceError as exc:
            errors[field] = str(exc)

    if not confirmation:
        errors["confirmation"] = "Vui lòng nhập lại mật khẩu."
    elif password != confirmation:
        errors["confirmation"] = "Mật khẩu nhập lại chưa khớp."

    st.session_state.register_field_errors = errors
    st.session_state.pop("register_result", None)
    if errors:
        return

    try:
        register_user(name, email, password, confirmation)
    except AuthServiceError as exc:
        st.session_state.register_result = ("error", str(exc))
    except Exception:
        st.session_state.register_result = (
            "error",
            "Đăng ký chưa thành công. Hãy kiểm tra thông tin hoặc thử lại sau.",
        )
    else:
        st.session_state.register_result = (
            "success",
            "Đăng ký thành công. Bạn có thể đăng nhập ngay.",
        )
        for key in ("register_name", "register_email"):
            st.session_state[key] = ""
        st.session_state.pop("register_password", None)
        st.session_state.pop(_REGISTRATION_PASSWORD_KEY, None)
        st.session_state.pop("register_confirmation", None)
        st.session_state.pop(_REGISTRATION_CONFIRMATION_KEY, None)


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
                placeholder: str | None = None, max_chars: int = 254,
                on_change=None, args: tuple = ()) -> str:
    return st.text_input(label, key=key, type="password" if password else "default",
                         placeholder=placeholder or label, icon=f":material/{icon}:",
                         max_chars=72 if password else max_chars, label_visibility="collapsed",
                         on_change=on_change, args=args)


def _show_configuration_status() -> bool:
    if is_supabase_configured():
        return True
    st.info(
        "Chức năng tài khoản đang chờ cấu hình Supabase. Cần SUPABASE_URL và "
        "SUPABASE_PUBLISHABLE_KEY (hoặc SUPABASE_ANON_KEY)."
    )
    return False


@st.dialog("DHV · Trợ lý tuyển sinh", icon=":material/school:", on_dismiss=_close_auth)
def render_auth_dialog() -> None:
    """Render the existing login/register modal using Supabase Auth."""
    view = st.session_state.get("auth_view")
    if view not in {"login", "register", "forgot"}:
        return
    configured = _show_configuration_status()
    titles = {
        "login": "Đăng nhập",
        "register": "Đăng ký tài khoản",
        "forgot": "Quên mật khẩu",
    }
    descriptions = {
        "login": "Đăng nhập để sử dụng trợ lý tuyển sinh DHV.",
        "register": "Tạo tài khoản để sử dụng trợ lý tuyển sinh DHV.",
        "forgot": "Nhập email đã đăng ký để nhận liên kết đặt lại mật khẩu.",
    }
    with st.container(key="auth_panel"):
        with st.container(key="auth_intro", gap="xsmall"):
            st.header(titles[view])
            if view == "login":
                st.markdown("Chào mừng bạn quay trở lại!")
            st.caption(descriptions[view])
        if view == "login":
            with st.form("login_form", clear_on_submit=True, border=False):
                email = _auth_input("Email", "login_email", "mail", placeholder="Email", max_chars=254)
                password = _auth_input("Mật khẩu", "login_password", "lock", password=True,
                                       placeholder="Mật khẩu")
                submitted = st.form_submit_button(
                    "Đăng nhập", key="submit_login", type="primary", width="stretch", disabled=not configured
                )
            if submitted:
                try:
                    clean_email = validate_email(email)
                    validate_password(password)
                    with st.spinner("Đang đăng nhập..."):
                        user, tokens = login_user(clean_email, password)
                except AuthServiceError as exc:
                    # Provider failures use a single generic login message.
                    message = str(exc)
                    if message.startswith("Email hoặc mật khẩu"):
                        st.error("Email hoặc mật khẩu chưa đúng.")
                    else:
                        st.error(message)
                except Exception:
                    st.error("Email hoặc mật khẩu chưa đúng.")
                else:
                    st.success("Đăng nhập thành công. Đang mở trợ lý...", icon=":material/check_circle:")
                    time.sleep(_LOGIN_SUCCESS_DISPLAY_SECONDS)
                    st.session_state.auth_user = user
                    st.session_state.auth_tokens = tokens
                    st.session_state.auth_login_notice = True
                    _close_auth()
                    st.rerun()
            st.divider()
            _auth_footer("Chưa có tài khoản?", "Đăng ký ngay", "register", key="auth_register")
            _switch_auth(
                "Quên mật khẩu?", "forgot", key="auth_forgot_password",
                icon=":material/help_outline:",
            )
        elif view == "register":
            errors = st.session_state.get("register_field_errors", {})
            name = _auth_input("Họ và tên", "register_name", "person", max_chars=50,
                               on_change=_clear_registration_error, args=("name",))
            if errors.get("name"):
                st.error(errors["name"])

            email = _auth_input("Email", "register_email", "mail", max_chars=254,
                                on_change=_clear_registration_error, args=("email",))
            if errors.get("email"):
                st.error(errors["email"])

            password = _registration_password_input()
            if errors.get("password"):
                st.error(errors["password"])

            confirmation = _registration_confirmation_input(password)
            confirmation_message = errors.get("confirmation")
            if confirmation_message and not confirmation:
                st.error(confirmation_message)

            st.button(
                "Đăng ký", key="submit_register", type="primary", width="stretch",
                disabled=not configured, on_click=_submit_registration,
            )
            result = st.session_state.get("register_result")
            if result:
                if result[0] == "success":
                    st.success(result[1])
                else:
                    st.error(result[1])
            st.divider()
            _auth_footer("Đã có tài khoản?", "Đăng nhập", "login", key="auth_back_login")
        else:
            with st.form("password_recovery_request_form", clear_on_submit=False, border=False):
                email = _auth_input(
                    "Email", "password_recovery_email", "mail",
                    placeholder="Email đã đăng ký", max_chars=254,
                )
                submitted = st.form_submit_button(
                    "Gửi liên kết đặt lại", key="submit_password_recovery_request",
                    type="primary", width="stretch", disabled=not configured,
                )
            if submitted:
                try:
                    validate_email(email)
                    # Start delivery off the render path so the generic
                    # acknowledgement does not wait on Supabase's response.
                    _dispatch_password_recovery(email)
                except AuthServiceError as exc:
                    st.session_state.password_recovery_request_result = (
                        "error", str(exc)
                    )
                except Exception:
                    st.session_state.password_recovery_request_result = (
                        "error", "Không thể gửi yêu cầu lúc này. Vui lòng thử lại sau."
                    )
                else:
                    st.session_state.password_recovery_request_result = (
                        "success", _RECOVERY_NOTICE
                    )
            result = st.session_state.get("password_recovery_request_result")
            if result:
                if result[0] == "success":
                    st.success(result[1])
                else:
                    st.error(result[1])
            st.divider()
            _auth_footer("Đã nhớ mật khẩu?", "Đăng nhập", "login", key="auth_back_from_forgot")
        with st.container(key="auth_note"):
            st.caption("Tài khoản được xác thực và lưu bằng Supabase.")
