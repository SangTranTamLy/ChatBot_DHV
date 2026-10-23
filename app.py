"""Giao diện chat Streamlit cho chatbot tuyển sinh DHV.

Giao diện này chỉ có một điểm giao tiếp duy nhất với backend: ``ask_chatbot`` từ Task C.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
import re
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from src.ui_auth import init_auth, logout, open_auth, render_auth_dialog


load_dotenv()

st.set_page_config(
    page_title="Chatbot tuyển sinh DHV",
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_chat_styles() -> None:
    """Apply the DHV chat layout without rendering user content as HTML."""
    css = Path(__file__).parent / "assets" / "chat.css"
    st.html("<style>" + css.read_text(encoding="utf-8") + "</style>")


DISCLAIMER = (
    "Chatbot chỉ cung cấp thông tin dựa trên dữ liệu tuyển sinh DHV đã được "
    "thu thập và kiểm chứng. Với thông tin quan trọng hoặc có thể thay đổi, "
    "vui lòng kiểm tra lại tại kênh chính thức của nhà trường."
)
PRIVACY_REMINDER = (
    "Không nhập CCCD, số điện thoại, email, địa chỉ hoặc dữ liệu hồ sơ cá nhân "
    "vào khung chat."
)
GENERIC_ERROR_ANSWER = "Xin lỗi, tôi chưa thể xử lý câu hỏi này lúc này. Bạn vui lòng thử lại sau."
STARTER_QUESTIONS = {
    "Ngành đào tạo": (":material/menu_book:", "DHV có những ngành đào tạo nào?"),
    "Học phí & học bổng": (":material/payments:", "Học phí và học bổng DHV năm 2026 như thế nào?"),
    "Hồ sơ nhập học": (":material/description:", "Hồ sơ nhập học DHV cần những giấy tờ gì?"),
}


KNOWN_STATUSES = frozenset(
    {"ok", "clarification", "no_data", "out_of_scope", "ollama_offline", "vector_db_error", "error"}
)
_DISPLAY_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(\s*(?:https?://|www\.)[^)]+\)", re.IGNORECASE
)
_DISPLAY_URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>]+", re.IGNORECASE)


def _strip_display_urls(value: str) -> str:
    """Ẩn URL/provenance khỏi UI nhưng không thay đổi payload backend."""

    cleaned = _DISPLAY_MARKDOWN_LINK_RE.sub(r"\1", value)
    cleaned = _DISPLAY_URL_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _is_direct_website_result(result: Mapping[str, Any]) -> bool:
    """Chỉ cho phép URL đi ra UI khi backend xác định đây là câu hỏi website."""

    trace = result.get("trace")
    if not isinstance(trace, Mapping):
        return False
    entities = trace.get("entities")
    return isinstance(entities, Mapping) and bool(entities.get("website_request"))


def _is_verified_contact_channel_result(result: Mapping[str, Any]) -> bool:
    """Allow social URLs only for a successful answer backed by the contact file."""
    if result.get("status") != "ok":
        return False
    trace = result.get("trace")
    if not isinstance(trace, Mapping) or trace.get("intent") != "HOI_CO_SO_LIEN_HE":
        return False
    selection = trace.get("evidence_selection")
    if not isinstance(selection, Mapping):
        return False
    selected = selection.get("selected")
    return isinstance(selected, list) and any(
        isinstance(item, Mapping)
        and item.get("selected") is True
        and item.get("category") == "co_so_lien_he"
        for item in selected
    )


def _init_session_state() -> None:
    """Khởi tạo toàn bộ trạng thái chat của người dùng tại một nơi."""

    user = st.session_state.get("auth_user")
    owner = user["email"].strip().casefold() if user else None
    sessions = st.session_state.setdefault("account_chat_sessions", {})
    chat_keys = ("messages", "chats", "active_chat", "next_chat", "conversation_state", "state")
    previous_owner = st.session_state.get("chat_owner")
    if "chat_owner" in st.session_state and previous_owner != owner:
        if previous_owner:
            sessions[previous_owner] = {key: deepcopy(st.session_state[key])
                                        for key in chat_keys if key in st.session_state}
        for key in (*chat_keys, "chat_input"):
            st.session_state.pop(key, None)
        if owner in sessions:
            st.session_state.update(deepcopy(sessions[owner]))
    st.session_state.chat_owner = owner
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("chats", {})
    if not owner:
        st.session_state.chats = {}
    st.session_state.setdefault("active_chat", 0)
    st.session_state.setdefault("next_chat", 0)
    initial_state = ConversationState().to_dict()
    st.session_state.setdefault("conversation_state", dict(initial_state))
    # Giữ đồng bộ cả hai tên biến dùng cho service để các câu trả lời làm rõ (clarification)
    # hoặc danh sách không bị mất ngữ cảnh giới hạn ở lần chạy lại (rerun) tiếp theo của Streamlit.
    st.session_state.setdefault(
        "state", dict(st.session_state.get("conversation_state") or initial_state)
    )


def _normalise_result(result: object) -> dict[str, object]:
    """Ngăn các payload service bị lỗi làm hỏng giao diện."""

    if not isinstance(result, Mapping):
        return {"answer": GENERIC_ERROR_ANSWER, "status": "error"}

    status = result.get("status")
    if not isinstance(status, str) or status not in KNOWN_STATUSES:
        status = "error"

    answer = result.get("answer")
    allow_direct_website_url = _is_direct_website_result(result)
    allow_contact_channel_urls = _is_verified_contact_channel_result(result)
    if not isinstance(answer, str) or not answer.strip():
        answer = GENERIC_ERROR_ANSWER
    else:
        if not (allow_direct_website_url or allow_contact_channel_urls):
            answer = _strip_display_urls(answer)
        if not answer:
            answer = GENERIC_ERROR_ANSWER

    normalised = {
        "answer": answer.strip(),
        "status": status,
    }
    if allow_direct_website_url:
        normalised["allow_direct_website_url"] = True
    if allow_contact_channel_urls:
        normalised["allow_contact_channel_urls"] = True
    return normalised


def _ask_question(question: str) -> dict[str, object]:
    """Chỉ gọi service của Task C và phân loại các lỗi bất ngờ ở ranh giới UI."""

    try:
        wait_for_warmup(timeout=5.0)
        result = ask_chatbot(
            question,
            conversation_state=st.session_state.get("conversation_state"),
            conversation_history=st.session_state.get("messages", []),
        )
        next_state = None
        if isinstance(result, Mapping):
            next_state = result.get("state") or result.get("conversation_state")
        if isinstance(next_state, Mapping):
            state_dict = dict(next_state)
            st.session_state["conversation_state"] = state_dict
            st.session_state["state"] = dict(state_dict)
        return _normalise_result(result)
    except Exception:
        # Người dùng sẽ thấy một thông báo an toàn; chi tiết lỗi kỹ thuật được giữ lại ở backend.
        return {
            "answer": GENERIC_ERROR_ANSWER,
            "status": "error",
        }


_TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
_MAJOR_LIST_ROW_RE = re.compile(
    r"^\s*(\d+)[.)]\s+(.+?)\s+[—–-]\s+mã ngành\s+(\d{7})\s*\.?\s*$",
    re.IGNORECASE,
)


def _format_major_list_table(answer: str) -> str:
    """Present existing name/code lists as tables without changing stored answers."""
    lines = answer.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        if not _MAJOR_LIST_ROW_RE.fullmatch(lines[index]):
            output.append(lines[index])
            index += 1
            continue
        end = index
        rows = []
        while end < len(lines):
            match = _MAJOR_LIST_ROW_RE.fullmatch(lines[end])
            if match:
                rows.append(match.groups())
            elif lines[end].strip():
                break
            end += 1
        if len(rows) < 2:
            output.extend(lines[index:end])
        else:
            output.extend(["", "| STT | Ngành đào tạo | Mã ngành |", "| ---: | --- | --- |"])
            output.extend(f"| {number} | {name.replace('|', '&#124;')} | {code} |"
                          for number, name, code in rows)
            output.append("")
        index = end
    return "\n".join(output)


def _is_markdown_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return len(cells) >= 2 and all(_TABLE_SEPARATOR_RE.fullmatch(cell) for cell in cells)


def _split_markdown_table(answer: str) -> tuple[str, str | None, str]:
    """Tách phần bảng khỏi phần diễn giải để chỉ bảng nằm trong container."""

    lines = answer.splitlines()
    for index in range(len(lines) - 1):
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if "|" not in header or not _is_markdown_table_separator(separator):
            continue

        end = index + 2
        while end < len(lines):
            row = lines[end]
            if not row.strip() or "|" not in row:
                break
            end += 1

        before = "\n".join(lines[:index]).strip()
        table = "\n".join(lines[index:end]).strip()
        after = "\n".join(lines[end:]).strip()
        return before, table, after

    return answer.strip(), None, ""


def _render_answer_markdown(answer: str) -> None:
    """Render text directly and isolate a Markdown table when one is present."""

    before, table, after = _split_markdown_table(_format_major_list_table(answer))
    if before:
        st.markdown(before, unsafe_allow_html=False)
    if table:
        st.markdown(table, unsafe_allow_html=False)
    if after:
        st.markdown(after, unsafe_allow_html=False)


def _render_assistant_content(message: Mapping[str, Any]) -> None:
    """Hiển thị nội dung trả lời an toàn bên trong khung tin nhắn."""

    answer = str(
        message.get("content")
        or message.get("answer")
        or GENERIC_ERROR_ANSWER
    )
    if not (message.get("allow_direct_website_url") or message.get("allow_contact_channel_urls")):
        answer = _strip_display_urls(answer)
    if not answer:
        answer = GENERIC_ERROR_ANSWER
    _render_answer_markdown(answer)


def _render_chat_history() -> None:
    """Hiển thị các tin nhắn đã lưu của người dùng và trợ lý bằng giao diện chat bubble."""

    for message in st.session_state.messages:
        if not isinstance(message, Mapping):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue

        with st.chat_message(
            role,
            avatar=":material/school:" if role == "assistant" else None,
        ):
            if role == "user":
                st.markdown(str(message.get("content") or ""), unsafe_allow_html=False)
            else:
                _render_assistant_content(message)


def _render_welcome() -> str | None:
    """Show conversation starters only while the current chat is empty."""
    if st.session_state.messages:
        return None
    with st.container(key="welcome"):
        st.markdown(":material/school:")
        user = st.session_state.auth_user
        first_name = user["name"].split()[-1] if user else "bạn"
        st.html(
            '<h1 class="dhv-greeting">'
            f'<span>Chào {escape(first_name)},</span>'
            '<span>mình có thể giúp gì?</span></h1>'
        )
        st.caption("Cùng tìm hiểu hành trình trở thành sinh viên DHV.")
    with st.container(key="starters"):
        st.markdown("**Bạn có thể bắt đầu với**")
        for index, (label, (icon, question)) in enumerate(STARTER_QUESTIONS.items()):
            with st.container(key=f"starter_row_{index}", horizontal=True, vertical_alignment="center"):
                if st.button(question, icon=icon, key=f"starter_{index}",
                             type="tertiary", width="stretch"):
                    return question
                st.markdown(":material/arrow_forward:")
        st.caption("Hoặc đặt câu hỏi theo cách của bạn.")
    return None


def _save_current_chat() -> None:
    """Keep conversations local to this browser session, with their own context."""
    if st.session_state.auth_user and st.session_state.messages:
        st.session_state.chats[st.session_state.active_chat] = {
            "messages": deepcopy(st.session_state.messages),
            "conversation_state": deepcopy(st.session_state.conversation_state),
            "updated_at": st.session_state.chats.get(st.session_state.active_chat, {}).get("updated_at"),
        }


def _new_chat() -> None:
    _save_current_chat()
    st.session_state.next_chat += 1
    st.session_state.active_chat = st.session_state.next_chat
    st.session_state.messages = []
    state = ConversationState().to_dict()
    st.session_state.conversation_state = state
    st.session_state.state = dict(state)


def _open_chat(chat_id: int) -> None:
    if not st.session_state.auth_user:
        return
    _save_current_chat()
    saved = st.session_state.chats[chat_id]
    st.session_state.active_chat = chat_id
    st.session_state.messages = deepcopy(saved["messages"])
    st.session_state.conversation_state = deepcopy(saved["conversation_state"])
    st.session_state.state = deepcopy(saved["conversation_state"])


def _render_sidebar() -> None:
    with st.sidebar:
        with st.container(key="brand"):
            st.markdown("## :material/school: DHV")
            st.caption("TƯ VẤN TUYỂN SINH")
        st.button("Cuộc trò chuyện mới", icon=":material/add:", type="primary",
                  width="stretch", key="new_chat", on_click=_new_chat)
        _save_current_chat()
        with st.container(key="history_list"):
            st.caption("LỊCH SỬ TRÒ CHUYỆN")
            groups = {"Hôm nay": [], "Hôm qua": [], "Trước đó": []}
            for chat_id, chat in st.session_state.chats.items():
                stamp = chat.get("updated_at")
                day = date.fromisoformat(stamp[:10]) if stamp else None
                group = "Hôm nay" if day == date.today() else "Hôm qua" if day == date.today() - timedelta(days=1) else "Trước đó"
                groups[group].append((chat_id, chat))
            for group, chats in groups.items():
                if not chats:
                    continue
                st.caption(group)
                for chat_id, chat in sorted(chats, key=lambda item: item[1].get("updated_at") or "", reverse=True):
                    title = next((row["content"] for row in chat["messages"] if row.get("role") == "user"), "Cuộc trò chuyện")
                    with st.container(key=f"history_row_{'active' if chat_id == st.session_state.active_chat else 'saved'}_{chat_id}"):
                        st.button(title[:80], icon=":material/chat_bubble_outline:", type="tertiary",
                                  help=title, width="stretch", key=f"history_{chat_id}", on_click=_open_chat, args=(chat_id,))
            if not st.session_state.auth_user:
                st.caption("Bạn có thể trò chuyện ngay. Đăng nhập để lưu lịch sử.")
            elif not st.session_state.chats:
                st.caption("Các cuộc trò chuyện đã lưu sẽ xuất hiện ở đây.")
        with st.container(key="sidebar_footer"):
            with st.expander("Trợ giúp", icon=":material/help_outline:"):
                st.caption("Chọn một chủ đề hoặc nhập câu hỏi để bắt đầu. Lịch sử chỉ được giữ trong phiên đang mở.")
                st.caption(DISCLAIMER)
                st.caption(PRIVACY_REMINDER)
            if st.session_state.auth_user:
                name = st.session_state.auth_user["name"]
                initials = "".join(part[0] for part in name.split()[-2:]).upper()
                with st.container(key="account_row"):
                    avatar, identity, menu = st.columns([0.2, 0.62, 0.18], gap="small", vertical_alignment="center")
                    with avatar:
                        st.html(f'<div class="dhv-account-avatar" aria-hidden="true">{escape(initials)}</div>')
                    with identity:
                        st.text(name)
                        st.caption("Tài khoản cá nhân")
                    with menu:
                        with st.popover("Tùy chọn tài khoản", key="account_menu", type="tertiary"):
                            st.button("Đăng xuất", icon=":material/logout:", key="logout", on_click=logout, width="stretch")


def _record_and_render_exchange(question: str) -> None:
    """Lưu trữ và hiển thị một lượt hỏi đáp, bao gồm xử lý lỗi service an toàn."""

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question, unsafe_allow_html=False)

    with st.chat_message("assistant", avatar=":material/school:"):
        with st.spinner("Đang tra cứu thông tin tuyển sinh..."):
            result = _ask_question(question)
        _render_assistant_content(result)

    message = {
        "role": "assistant",
        "content": result["answer"],
        "status": result["status"],
    }
    if result.get("allow_direct_website_url"):
        message["allow_direct_website_url"] = True
    if result.get("allow_contact_channel_urls"):
        message["allow_contact_channel_urls"] = True
    st.session_state.messages.append(message)
    if st.session_state.auth_user:
        _save_current_chat()
        st.session_state.chats[st.session_state.active_chat]["updated_at"] = datetime.now().isoformat(timespec="seconds")


_inject_chat_styles()
init_auth()
if st.session_state.pop("auth_login_notice", False):
    st.toast("Đăng nhập thành công.", icon=":material/check_circle:", duration=4)

from src.chatbot.chat_service import ask_chatbot
from src.chatbot.query_analysis import ConversationState
from src.chatbot.warmup import start_background_warmup, wait_for_warmup

start_background_warmup()
_init_session_state()
_render_sidebar()

with st.container(key="topbar", horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
    st.markdown(":material/school: **Trợ lý tuyển sinh DHV**")
    if st.session_state.auth_user:
        st.caption("Trường Đại học Hùng Vương TP.HCM")
    else:
        st.button("Đăng nhập", icon=":material/person:", key="open_login", on_click=open_auth)

typed_question = st.chat_input(
    "Nhắn tin cho trợ lý DHV…",
    key="chat_input",
    submit_mode="disable",
)
has_typed_question = isinstance(typed_question, str) and bool(typed_question.strip())

selected_starter = _render_welcome() if not has_typed_question else None
_render_chat_history()

if has_typed_question:
    _record_and_render_exchange(typed_question.strip())
    _save_current_chat()
    st.rerun()
elif selected_starter:
    _record_and_render_exchange(selected_starter)
    _save_current_chat()
    st.rerun()

with st.container(key="chat_note"):
    st.caption("Thông tin tư vấn mang tính tham khảo. Bạn có thể kiểm tra lại qua kênh tuyển sinh chính thức của trường.")

if st.session_state.auth_view and not st.session_state.auth_user:
    render_auth_dialog()
