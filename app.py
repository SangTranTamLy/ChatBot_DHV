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

from src.supabase_auth import AuthServiceError, change_password, is_supabase_configured
from src.ui_auth import (
    init_auth,
    logout,
    open_auth,
    render_auth_dialog,
    render_password_recovery_page,
)


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
    "Phương thức xét tuyển": (":material/fact_check:", "DHV có những phương thức xét tuyển nào năm 2026?"),
}

# Danh mục liên kết chính thức trích xuất từ Cổng tuyển sinh DHV (https://tuyensinh.dhv.edu.vn/)
DHV_OFFICIAL_URLS: dict[str, str] = {
    "portal": "https://tuyensinh.dhv.edu.vn/",
    "apply": "https://tuyensinh.dhv.edu.vn/dangky",
    "home": "https://dhv.edu.vn/",
    "about": "https://dhv.edu.vn/gioi-thieu/",
    "news": "https://dhv.edu.vn/category/tin-dhv/",
    "programs": "https://dhv.edu.vn/dao-tao/",
    "hotline": "tel:02871000888",
    "hotline_display": "028 7100 0888",
    "zalo": "https://zalo.me/1822829687649866202",
    "facebook_admissions": "https://www.facebook.com/kenhtuyensinhDHV",
    "facebook_uni": "https://www.facebook.com/hungvuonguni",
    "youtube": "https://www.youtube.com/@kenhtuyensinhDHV",
    "tiktok": "https://www.tiktok.com/@tuyensinhdhv",
}

# 20 chương trình đào tạo đại học chính quy và đường dẫn website chính thức
OFFICIAL_MAJOR_URLS: dict[str, str] = {
    "7340101": "https://bam.dhv.edu.vn/educational-program/quan-tri-kinh-doanh?program=dai-hoc",
    "7340115": "https://bam.dhv.edu.vn/educational-program/marketing?program=dai-hoc",
    "7340122": "https://bam.dhv.edu.vn/educational-program/thuong-mai-dien-tu?program=dai-hoc",
    "7310106": "https://bam.dhv.edu.vn/educational-program/kinh-te-quoc-te?program=dai-hoc",
    "7340201": "https://fba.dhv.edu.vn/educational-program/tai-chinh-ngan-hang?program=dai-hoc",
    "7340205": "https://fba.dhv.edu.vn/educational-program/fintech?program=dai-hoc",
    "7340301": "https://fba.dhv.edu.vn/educational-program/ke-toan?program=dai-hoc",
    "7480201": "https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc",
    "7480106": "https://tec.dhv.edu.vn/educational-program/ky-thuat-may-tinh?program=dai-hoc",
    "7480107": "https://iatai.dhv.edu.vn/",
    "7380101": "https://law.dhv.edu.vn/educational-program/luat?program=dai-hoc",
    "7380107": "https://law.dhv.edu.vn/educational-program/luat-kinh-te?program=dai-hoc",
    "7220201": "https://lan.dhv.edu.vn/educational-program/ngon-ngu-anh?program=dai-hoc",
    "7220204": "https://lan.dhv.edu.vn/educational-program/ngon-ngu-trung-quoc?program=dai-hoc",
    "7220209": "https://lan.dhv.edu.vn/educational-program/ngon-ngu-nhat?program=dai-hoc",
    "7220210": "https://lan.dhv.edu.vn/educational-program/ngon-ngu-han-quoc?program=dai-hoc",
    "7720701": "https://heal.dhv.edu.vn/educational-program/quan-ly-benh-vien?program=dai-hoc",
    "7310401": "https://heal.dhv.edu.vn/educational-program/tam-ly-hoc?program=dai-hoc",
    "7810201": "https://host.dhv.edu.vn/educational-program/quan-tri-khach-san?program=dai-hoc",
    "7810103": "https://host.dhv.edu.vn/educational-program/quan-tri-dich-vu-du-lich-lu-hanh?program=dai-hoc",
}

# Tên và mã lấy từ tài liệu ngành năm 2026 và website chính thức của DHV
VERIFIED_MAJORS_2026 = (
    ("Quản trị kinh doanh", "7340101"),
    ("Marketing", "7340115"),
    ("Thương mại điện tử", "7340122"),
    ("Kinh tế quốc tế", "7310106"),
    ("Tài chính - Ngân hàng", "7340201"),
    ("Công nghệ tài chính", "7340205"),
    ("Kế toán", "7340301"),
    ("Công nghệ thông tin", "7480201"),
    ("Kỹ thuật máy tính", "7480106"),
    ("Trí tuệ nhân tạo", "7480107"),
    ("Luật", "7380101"),
    ("Luật kinh tế", "7380107"),
    ("Ngôn ngữ Anh", "7220201"),
    ("Ngôn ngữ Trung Quốc", "7220204"),
    ("Ngôn ngữ Nhật", "7220209"),
    ("Ngôn ngữ Hàn Quốc", "7220210"),
    ("Quản lý bệnh viện", "7720701"),
    ("Tâm lý học", "7310401"),
    ("Quản trị khách sạn", "7810201"),
    ("Quản trị dịch vụ du lịch và lữ hành", "7810103"),
)


KNOWN_STATUSES = frozenset(
    {
        "ok",
        "clarification",
        "no_data",
        "out_of_scope",
        "ollama_offline",
        "model_timeout",
        "vector_db_error",
        "error",
    }
)
_OFFICIAL_URL_DOMAIN_RE = re.compile(
    r"^(?:https?://)?(?:[a-zA-Z0-9-]+\.)*(?:dhv\.edu\.vn|zalo\.me|facebook\.com|tiktok\.com|youtube\.com)(?:/|$)",
    re.IGNORECASE,
)


def _is_official_url(url: str) -> bool:
    clean_url = url.strip()
    return bool(_OFFICIAL_URL_DOMAIN_RE.match(clean_url)) or clean_url.startswith("tel:")


def _strip_display_urls(value: str) -> str:
    """Ẩn URL/provenance nội bộ khỏi UI nhưng bảo tồn link chính thức của DHV."""

    def _strip_md_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)
        if _is_official_url(url):
            return match.group(0)
        return label

    def _strip_raw_url(match: re.Match[str]) -> str:
        url = match.group(0)
        if _is_official_url(url):
            return url
        return ""

    cleaned = re.sub(
        r"\[([^\]]+)\]\(\s*((?:https?://|www\.|tel:)[^)]+)\)",
        _strip_md_link,
        value,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?<!\()(?<!\[)(?:https?://|www\.)[^\s)>]+",
        _strip_raw_url,
        cleaned,
        flags=re.IGNORECASE,
    )
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
    chat_keys = (
        "messages", "chats", "active_chat", "next_chat", "conversation_state", "state",
    )
    previous_owner = st.session_state.get("chat_owner")
    if "chat_owner" in st.session_state and previous_owner != owner:
        if previous_owner:
            sessions[previous_owner] = {key: deepcopy(st.session_state[key])
                                        for key in chat_keys if key in st.session_state}
        for key in (*chat_keys, "chat_input", "pending_question", "chat_request_in_progress",
                    "saved_items", "admission_checklist"):
            st.session_state.pop(key, None)
        if st.session_state.get("account_page") != "chat":
            st.session_state.account_page = "chat"
        if owner in sessions:
            st.session_state.update(deepcopy(sessions[owner]))
    st.session_state.chat_owner = owner
    if st.session_state.get("messages"):
        st.session_state.setdefault("account_page", "chat")
    else:
        st.session_state.setdefault("account_page", "chat")
    st.session_state.setdefault("admission_checklist", {})
    st.session_state.setdefault("saved_items", [])
    st.session_state.setdefault("messages", [])
    # Clean legacy editing widget state from sessions created before editing was removed.
    legacy_edit_state = {
        "editing_message_index", "message_edit_error", "message_branches",
        "message_branch_view",
    }
    for key in list(st.session_state):
        if key in legacy_edit_state or key.startswith("message_edit_input_"):
            st.session_state.pop(key, None)
    st.session_state.setdefault("chat_request_in_progress", False)
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


def _current_chat_user_avatar() -> str:
    """Return a Streamlit-supported private avatar for the current chat user."""
    # Streamlit treats arbitrary strings as image paths; initials such as "T"
    # therefore raise an image-loading exception. A material icon is valid for
    # both guest and signed-in conversations and does not expose profile data.
    return ":material/person:"


def _render_user_message(message: Mapping[str, Any]) -> None:
    with st.chat_message("user", avatar=_current_chat_user_avatar()):
        st.markdown(str(message.get("content") or ""), unsafe_allow_html=False)


def _render_chat_history() -> None:
    """Display the current conversation history."""

    for index, message in enumerate(st.session_state.messages):
        if not isinstance(message, Mapping):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue

        if role == "user":
            _render_user_message(message)
        else:
            with st.chat_message("assistant", avatar=":material/school:"):
                _render_assistant_content(message)
            if st.button(
                "Lưu vào sổ tay", icon=":material/bookmark_add:", key=f"save_answer_{index}",
                type="tertiary",
            ):
                _save_answer(message)
                st.toast("Đã lưu trong phiên hiện tại.", icon=":material/bookmark:")


def _navigate_to(page: str) -> None:
    st.session_state.account_page = page


def _save_answer(message: Mapping[str, Any]) -> None:
    """Save a response to the current browser session only (no backend write)."""
    content = str(message.get("content") or "").strip()
    if content and content not in {item.get("content") for item in st.session_state.saved_items}:
        st.session_state.saved_items.insert(0, {
            "title": content.splitlines()[0][:90],
            "content": content,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })


def _history_picker(*, key: str = "history_picker") -> None:
    with st.popover("Lịch sử", icon=":material/history:", key=key, help="Mở lịch sử trò chuyện"):
        if not st.session_state.auth_user:
            st.caption("Đăng nhập để xem và lưu các cuộc trò chuyện.")
            if st.button("Đăng nhập", key=f"{key}_login", icon=":material/person:", width="stretch"):
                open_auth()
                st.rerun()
            return
        visible_chat_ids = _active_chat_ids()
        if not visible_chat_ids:
            st.caption("Các cuộc trò chuyện đã lưu sẽ xuất hiện ở đây.")
            return
        groups = {"Hôm nay": [], "Hôm qua": [], "Trước đó": []}
        for chat_id in visible_chat_ids:
            chat = st.session_state.chats[chat_id]
            stamp = chat.get("updated_at")
            try:
                day = date.fromisoformat(stamp[:10]) if stamp else None
            except (TypeError, ValueError):
                day = None
            group = "Hôm nay" if day == date.today() else (
                "Hôm qua" if day == date.today() - timedelta(days=1) else "Trước đó"
            )
            groups[group].append((chat_id, chat))
        for group, chats in groups.items():
            if not chats:
                continue
            st.caption(group)
            for chat_id, chat in sorted(
                chats, key=lambda item: item[1].get("updated_at") or "", reverse=True
            ):
                title = _chat_title(chat)
                st.button(
                    str(title)[:70], icon=":material/chat_bubble_outline:", type="tertiary",
                    key=f"{key}_chat_{chat_id}", help=str(title), width="stretch",
                    on_click=_open_chat, args=(chat_id,),
                )


def _render_topbar() -> None:
    brand = (
        '<div class="dhv-reference-topbar" aria-label="DHV, trợ lý tuyển sinh">'
        '<div class="dhv-reference-topbar-brand">'
        '<span class="material-symbols-rounded">school</span>'
        '<b>DHV - Trợ lý tuyển sinh</b><i></i>'
        '<small>Đồng hành cùng lựa chọn của bạn</small></div></div>'
    )
    with st.container(key="topbar"):
        st.html(brand)


def _render_mobile_nav() -> None:
    with st.container(key="mobile_nav"):
        with st.container(horizontal=True, gap="small"):
            for label, icon, page in (
                ("Khám phá", ":material/dashboard:", "explore"),
                ("Hỏi DHV", ":material/forum:", "chat"),
                ("Ngành", ":material/school:", "majors"),
                ("Lộ trình", ":material/check_circle:", "checklist"),
                ("Sổ tay", ":material/bookmark:", "notebook"),
            ):
                st.button(label, icon=icon, key=f"mobile_nav_{page}",
                          on_click=_navigate_to, args=(page,))


def _render_welcome() -> str | None:
    """Render the admissions dashboard while the current chat has no messages."""
    if st.session_state.messages:
        return None

    user = st.session_state.auth_user
    first_name = escape(user["name"].split()[-1]) if user else "bạn"
    campus_path = Path(__file__).parent / "static" / "dhv-campus-official.png"
    campus_uri = "/app/static/dhv-campus-official.png" if campus_path.exists() else ""
    hero = (
        '<section class="dhv-home-hero">'
        '<div class="dhv-home-copy"><div class="dhv-eyebrow"><span></span> TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG TP.HCM</div>'
        f'<h1>Tương lai của bạn,<br>bắt đầu tại <em>DHV.</em></h1>'
        f'<p>Chào {first_name}, hãy hỏi điều bạn đang băn khoăn.<br>Khám phá ngành học và chọn hướng đi của mình.</p>'
        '<div class="dhv-hero-caption"><span class="material-symbols-rounded">auto_awesome</span> Đồng hành từng bước đến cánh cửa đại học</div></div>'
        f'<div class="dhv-home-photo"><img src="{campus_uri}" alt="Cơ sở Trường Đại học Hùng Vương TP.HCM"></div>'
        '</section>'
    )

    with st.container(key="home_workspace"):
        with st.container(key="home_breadcrumb", horizontal=True, vertical_alignment="center"):
            st.markdown(":material/home:  Không gian tuyển sinh  ›  **Khám phá**")
            if st.button("Trò chuyện cùng DHV", icon=":material/chat_bubble_outline:", key="home_open_chat", on_click=_new_chat):
                pass

        main, side = st.columns([3.35, 1], gap="medium")
        with main:
            with st.container(key="home_main"):
                st.html(hero)
                with st.container(key="home_composer"):
                    st.html('<div class="dhv-composer-label"><span class="material-symbols-rounded">auto_awesome</span><b>Hỏi DHV, tìm hướng đi của bạn</b></div>')
                    with st.form("welcome_question_form", clear_on_submit=True, border=False):
                        question = st.text_area(
                            "Câu hỏi của bạn", key="welcome_question",
                            placeholder="Mình muốn tìm hiểu ngành học, học phí, xét tuyển…",
                            height=76, label_visibility="collapsed",
                        )
                        left, right = st.columns([5, 1], vertical_alignment="center")
                        with left:
                            st.caption(":material/school:  Tuyển sinh DHV   ·   :material/lock:  Không cần nhập thông tin cá nhân")
                        with right:
                            submitted = st.form_submit_button("Gửi câu hỏi", icon=":material/arrow_upward:", type="primary", width="stretch")
                    if submitted and question.strip():
                        return question.strip()

                with st.container(key="home_official_actions"):
                    o_c1, o_c2, o_c3 = st.columns([1.5, 1.3, 1.2], gap="small")
                    with o_c1:
                        st.link_button(
                            "Đăng ký xét tuyển 2026 ↗",
                            DHV_OFFICIAL_URLS["apply"],
                            type="primary",
                            width="stretch",
                            help="Đăng ký xét tuyển trực tuyến tại https://tuyensinh.dhv.edu.vn/dangky",
                        )
                    with o_c2:
                        st.link_button(
                            "Cổng tuyển sinh DHV ↗",
                            DHV_OFFICIAL_URLS["portal"],
                            type="secondary",
                            width="stretch",
                            help="Cổng thông tin tuyển sinh chính thức DHV",
                        )
                    with o_c3:
                        st.link_button(
                            "Tư vấn Zalo OA ↗",
                            DHV_OFFICIAL_URLS["zalo"],
                            type="secondary",
                            width="stretch",
                            help="Nhắn tin với tư vấn viên tuyển sinh qua Zalo",
                        )

                with st.container(key="home_quick_actions"):
                    with st.container(horizontal=True, wrap=True, gap="small"):
                        for index, (label, (icon, query)) in enumerate(STARTER_QUESTIONS.items()):
                            if st.button(label, icon=icon, key=f"home_question_{index}", type="secondary", width="stretch"):
                                return query

                with st.container(key="home_tools"):
                    st.html('<div class="dhv-section-heading"><div><h2>Chủ động chọn tương lai</h2><p>Những công cụ hữu ích cho hành trình tuyển sinh của bạn.</p></div><span>KHÔNG GIAN DHV</span></div>')
                    with st.container(horizontal=True, gap="medium"):
                        with st.container(key="home_tool_compare"):
                            st.markdown(":material/compare_arrows:")
                            st.markdown("**Đặt hai ngành lên bàn cân**")
                            st.caption("So sánh thông tin trước khi quyết định.")
                            st.button("So sánh ngành", icon=":material/arrow_forward:", key="home_go_compare",
                                      on_click=_navigate_to, args=("compare",), type="tertiary")
                        with st.container(key="home_tool_checklist"):
                            st.markdown(":material/task_alt:")
                            st.markdown("**Việc cần làm, trong tầm tay**")
                            st.caption("Lưu lại các bước bạn muốn chuẩn bị.")
                            st.button("Tạo lộ trình", icon=":material/arrow_forward:", key="home_go_checklist",
                                      on_click=_navigate_to, args=("checklist",), type="tertiary")

        with side:
            with st.container(key="official_channels_card"):
                st.html(
                    '<div class="dhv-side-title"><div><span class="material-symbols-rounded">verified</span><b>Kênh chính thức DHV</b></div>'
                    '<small>Cổng thông tin & hỗ trợ thí sinh</small></div>'
                )
                st.link_button("Đăng ký xét tuyển trực tuyến ↗", DHV_OFFICIAL_URLS["apply"], type="primary", width="stretch")
                st.link_button("Cổng tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["portal"], type="tertiary", width="stretch")
                st.link_button(f"Hotline: {DHV_OFFICIAL_URLS['hotline_display']}", DHV_OFFICIAL_URLS["hotline"], type="tertiary", width="stretch")
                st.link_button("Zalo OA Tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["zalo"], type="tertiary", width="stretch")
                st.link_button("Fanpage Tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["facebook_admissions"], type="tertiary", width="stretch")

            with st.container(key="journey_card"):
                st.html('<div class="dhv-side-title"><div><span class="material-symbols-rounded">conversion_path</span><b>Hành trình vào DHV</b></div><small>Từng bước nhỏ cho một lựa chọn lớn.</small></div>')
                for number, title, subtitle in (
                    ("01", "Khám phá bản thân", "Tìm hiểu ngành phù hợp"),
                    ("02", "Tìm cách xét tuyển", "Đối chiếu thông tin tuyển sinh"),
                    ("03", "Chuẩn bị hồ sơ", "Ghi lại điều cần làm"),
                ):
                    st.html(f'<div class="dhv-journey-step"><span>{number}</span><div><b>{title}</b><small>{subtitle}</small></div></div>')
                st.button("Mở lộ trình của tôi", icon=":material/arrow_forward:", key="journey_open",
                          type="secondary", width="stretch", on_click=_navigate_to, args=("checklist",))

            with st.container(key="interests_card"):
                st.html('<div class="dhv-side-title"><div><span class="material-symbols-rounded">explore</span><b>Bạn đang quan tâm?</b></div></div>')
                for index, (label, (_, query)) in enumerate(STARTER_QUESTIONS.items()):
                    if st.button(label, icon=":material/arrow_outward:", key=f"interest_{index}", type="tertiary", width="stretch"):
                        return query

            student_path = Path(__file__).parent / "static" / "dhv-students-official.jpg"
            if student_path.exists():
                with st.container(key="student_feature"):
                    st.html('<img src="/app/static/dhv-students-official.jpg" alt="Sinh viên tham gia ngày hội tuyển sinh DHV">')
                    st.markdown("**Một hành trình, nhiều cơ hội**")
                    st.caption("Tìm hiểu môi trường học tập tại DHV.")

        st.caption(
            "Thông tin tuyển sinh có thể thay đổi. Hãy đối chiếu trên [Cổng tuyển sinh](https://tuyensinh.dhv.edu.vn/) "
            "hoặc [Đăng ký trực tuyến](https://tuyensinh.dhv.edu.vn/dangky) · Hotline: [028 7100 0888](tel:02871000888)"
        )
    return None


def _save_current_chat() -> None:
    """Keep conversations local to this browser session, with their own context."""
    if st.session_state.auth_user and st.session_state.messages:
        existing = st.session_state.chats.get(st.session_state.active_chat, {})
        st.session_state.chats[st.session_state.active_chat] = {
            "messages": deepcopy(st.session_state.messages),
            "conversation_state": deepcopy(st.session_state.conversation_state),
            "updated_at": existing.get("updated_at"),
            "title": existing.get("title"),
            "deleted_at": existing.get("deleted_at"),
        }


def _chat_title(chat: Mapping[str, Any]) -> str:
    """Return the saved title, falling back to the first user prompt."""

    saved_title = str(chat.get("title") or "").strip()
    if saved_title:
        return saved_title
    for message in chat.get("messages", []):
        if isinstance(message, Mapping) and message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if content:
                return content
    return "Cuộc trò chuyện mới"


def _active_chat_ids() -> list[int]:
    """List visible, non-deleted conversations in recent-first order."""

    chats = [
        (chat_id, chat)
        for chat_id, chat in st.session_state.get("chats", {}).items()
        if isinstance(chat, Mapping) and not chat.get("deleted_at")
    ]
    chats.sort(key=lambda item: item[1].get("updated_at") or "", reverse=True)
    return [chat_id for chat_id, _ in chats]


def _new_chat() -> None:
    st.session_state.account_page = "chat"
    _save_current_chat()
    st.session_state.pop("pending_question", None)
    st.session_state.chat_request_in_progress = False
    st.session_state.next_chat += 1
    st.session_state.active_chat = st.session_state.next_chat
    st.session_state.messages = []
    state = ConversationState().to_dict()
    st.session_state.conversation_state = state
    st.session_state.state = dict(state)


def _open_chat(chat_id: int) -> None:
    if not st.session_state.auth_user:
        return
    st.session_state.account_page = "chat"
    _save_current_chat()
    saved = st.session_state.chats[chat_id]
    if saved.get("deleted_at"):
        return
    st.session_state.active_chat = chat_id
    st.session_state.messages = deepcopy(saved["messages"])
    st.session_state.conversation_state = deepcopy(saved["conversation_state"])
    st.session_state.state = deepcopy(saved["conversation_state"])


def _open_profile() -> None:
    st.session_state.account_page = "profile"


def _return_to_chat() -> None:
    st.session_state.account_page = "chat"


def _logout_account() -> None:
    st.session_state.account_page = "chat"
    logout()


def _render_profile_page() -> None:
    user = st.session_state.auth_user
    if not user:
        return

    name = user["name"]
    email = user["email"]
    initials = "".join(part[0] for part in name.split()[-2:]).upper() or "U"
    with st.container(key="account_profile"):
        st.markdown("## Hồ sơ cá nhân")
        with st.container(key="profile_identity", horizontal=True, vertical_alignment="center"):
            st.html(f'<div class="dhv-profile-avatar" aria-hidden="true">{escape(initials)}</div>')
            with st.container(key="profile_identity_text"):
                st.markdown(f"#### {escape(name)}")
                st.caption(escape(email))

        st.divider()
        st.markdown("### Đổi mật khẩu")
        st.caption("Nhập mật khẩu hiện tại và mật khẩu mới để cập nhật tài khoản.")
        with st.form("change_password_form", clear_on_submit=True, border=False):
            current_password = st.text_input(
                "Mật khẩu hiện tại", type="password", key="change_current_password", max_chars=72,
            )
            new_password = st.text_input(
                "Mật khẩu mới", type="password", key="change_new_password", max_chars=72,
            )
            password_confirmation = st.text_input(
                "Nhập lại mật khẩu mới", type="password",
                key="change_password_confirmation", max_chars=72,
            )
            submitted = st.form_submit_button(
                "Cập nhật mật khẩu", type="primary", width="stretch",
            )
        if submitted:
            try:
                updated_tokens = change_password(
                    st.session_state.get("auth_tokens") or {},
                    current_password,
                    new_password,
                    password_confirmation,
                )
            except AuthServiceError as exc:
                st.error(str(exc))
            except Exception:
                st.error("Không đổi được mật khẩu. Vui lòng thử lại sau.")
            else:
                st.session_state.auth_tokens = updated_tokens
                st.success("Đã đổi mật khẩu.")


def _render_sidebar() -> None:
    """Render the fixed DHV navigation sidebar."""
    _save_current_chat()
    with st.sidebar:
        with st.container(key="dhv_sidebar_v3"):
            st.html(
                '<div class="dhv-sidebar-v3-brand" aria-label="DHV, trợ lý tuyển sinh">'
                '<div class="dhv-sidebar-badge">'
                '<span class="dhv-sidebar-badge-icon material-symbols-rounded">school</span>'
                '</div>'
                '<div><b>DHV</b><small>TRỢ LÝ TUYỂN SINH</small>'
                '</div>'
                '</div>'
            )
            st.button(
                "Cuộc trò chuyện mới",
                icon=":material/add:",
                key="new_chat",
                type="primary", width="stretch", on_click=_new_chat,
            )
            with st.container(key="chat_history_list"):
                st.html(
                    '<div class="dhv-chat-sidebar-label">'
                    '<span><b class="material-symbols-rounded">schedule</b>GẦN ĐÂY</span>'
                    '</div>'
                )
                if not st.session_state.auth_user:
                    st.caption("Đăng nhập để xem các cuộc trò chuyện gần đây.")
                else:
                    visible_chat_ids = _active_chat_ids()
                    if not visible_chat_ids:
                        st.caption("Các cuộc trò chuyện đã lưu sẽ xuất hiện ở đây.")
                    else:
                        for chat_id in visible_chat_ids[:20]:
                            chat = st.session_state.chats[chat_id]
                            title = _chat_title(chat)
                            st.button(
                                title[:52], key=f"sidebar_chat_{chat_id}",
                                type="primary" if chat_id == st.session_state.active_chat else "tertiary",
                                icon=":material/chat_bubble_outline:", width="stretch",
                                on_click=_open_chat, args=(chat_id,),
                            )
            if not st.session_state.auth_user or not _active_chat_ids():
                st.html(
                    '<div class="dhv-sidebar-v3-ornament">'
                    '<span>Kiến tạo<br>tương lai<br>cùng DHV</span><i></i></div>'
                )
            with st.container(key="chat_sidebar_footer"):
                with st.popover("Trợ giúp", icon=":material/help_outline:", key="chat_help_menu"):
                    with st.container(key="chat_help_popup", gap="small"):
                        st.html('<div class="dhv-help-popup-heading">'
                                '<span class="material-symbols-rounded">support_agent</span>'
                                '<div><b>Trợ giúp DHV</b><small>Đồng hành cùng bạn</small></div></div>')
                        st.caption("Hỏi ngay trong khung chat về ngành học, học phí, học bổng và xét tuyển.")
                if st.session_state.auth_user:
                    user = st.session_state.auth_user
                    name = str(user.get("name") or "Tài khoản")
                    initials = "".join(part[0] for part in name.split()[-2:]).upper() or "U"
                    with st.popover(
                        f"**{initials}** {name}", key="chat_account_menu", width="stretch",
                    ):
                        with st.container(key="chat_account_identity"):
                            st.html('<div class="dhv-account-popup-identity">'
                                    f'<span class="dhv-account-avatar">{escape(initials)}</span>'
                                    f'<div><b>{escape(name)}</b><small>Tài khoản cá nhân</small></div></div>')
                        st.button(
                            "Hồ sơ cá nhân", icon=":material/person:", key="chat_account_profile",
                            width="stretch", on_click=_open_profile,
                        )
                        st.button(
                            "Đăng xuất", icon=":material/logout:", key="chat_account_logout",
                            width="stretch", on_click=_logout_account,
                        )
                else:
                    st.button(
                        "Đăng nhập", icon=":material/login:", key="rail_login",
                        type="secondary", width="stretch", on_click=open_auth,
                    )


def _page_heading(kicker: str, title: str, description: str, icon: str) -> None:
    st.html(
        '<div class="dhv-page-heading">'
        f'<div class="dhv-page-icon material-symbols-rounded">{escape(icon)}</div>'
        f'<div><small>{escape(kicker)}</small><h1>{escape(title)}</h1>'
        f'<p>{escape(description)}</p></div></div>'
    )


def _render_workspace_page(page: str) -> str | None:
    """Frontend admissions tools that reuse the existing, verified chat service."""
    page_specs = {
        "majors": ("KHÁM PHÁ DHV", "Ngành học tại DHV", "Tìm một ngành trong danh mục tuyển sinh 2026 hoặc hỏi trợ lý về chương trình.", "school"),
        "compare": ("CÔNG CỤ TUYỂN SINH", "So sánh ngành học", "Đặt hai ngành cạnh nhau rồi hỏi DHV về thông tin trong phương án tuyển sinh.", "compare_arrows"),
        "checklist": ("LỘ TRÌNH CỦA TÔI", "Từng bước chuẩn bị", "Tạo một checklist cá nhân. Các mục dưới đây là gợi ý, không thay thế thông báo chính thức.", "task_alt"),
        "notebook": ("KHÔNG GIAN CỦA BẠN", "Sổ tay tuyển sinh", "Các nội dung bạn lưu trong phiên trò chuyện này.", "bookmarks"),
        "help": ("DHV LUÔN SẴN SÀNG", "Trợ giúp", "Cách sử dụng trợ lý tuyển sinh và bảo vệ thông tin của bạn.", "help"),
    }
    kicker, title, description, icon = page_specs[page]
    with st.container(key=f"workspace_{page}"):
        with st.container(key="page_breadcrumb", horizontal=True, vertical_alignment="center"):
            st.markdown(f":material/home:  Không gian tuyển sinh  ›  **{escape(title)}**")
            if st.button("Hỏi DHV", icon=":material/chat:", key=f"{page}_back_chat", on_click=_navigate_to, args=("chat",)):
                pass
        _page_heading(kicker, title, description, icon)

        if page == "majors":
            with st.container(key="majors_cta_banner"):
                cta_c1, cta_c2 = st.columns([3, 1.4], vertical_alignment="center")
                with cta_c1:
                    st.markdown("**Tuyển sinh Đại học Chính quy năm 2026**")
                    st.caption("20 ngành đào tạo cử nhân và kỹ sư. Nộp hồ sơ xét học bạ online hoặc tra cứu thông tin trên Cổng tuyển sinh.")
                with cta_c2:
                    st.link_button(
                        "Đăng ký xét tuyển trực tuyến ↗",
                        DHV_OFFICIAL_URLS["apply"],
                        type="primary",
                        width="stretch",
                        help="Cổng đăng ký xét tuyển trực tuyến DHV",
                    )

            query = st.text_input(
                "Tìm ngành", placeholder="Tìm theo tên ngành hoặc mã ngành…",
                key="major_search", label_visibility="collapsed",
            )
            term = query.casefold().strip()
            rows = [item for item in VERIFIED_MAJORS_2026 if term in item[0].casefold() or term in item[1]]
            st.caption(f"{len(rows)} ngành phù hợp · Danh mục tham khảo theo tài liệu tuyển sinh 2026")
            with st.container(key="major_catalog"):
                major_columns = st.columns(3, gap="medium")
                for index, (name, code) in enumerate(rows):
                    major_url = OFFICIAL_MAJOR_URLS.get(code, DHV_OFFICIAL_URLS["portal"])
                    with major_columns[index % 3]:
                        with st.container(key=f"major_card_{index}"):
                            st.html(
                                f'<div class="dhv-major-card-top"><span class="material-symbols-rounded">school</span>'
                                f'<small>MÃ NGÀNH {escape(code)}</small></div>'
                                f'<h3>{escape(name)}</h3>'
                            )
                            with st.container(horizontal=True, gap="small"):
                                if st.button("Hỏi ngành", key=f"major_ask_{code}", icon=":material/arrow_forward:", type="tertiary"):
                                    return f"Thông tin tuyển sinh năm 2026 về ngành {name} của DHV"
                                if st.button("So sánh", key=f"major_compare_{code}", icon=":material/compare_arrows:", type="tertiary"):
                                    st.session_state.compare_first = name
                                    st.session_state.account_page = "compare"
                                    st.rerun()
                                st.link_button("CTĐT ↗", major_url, help=f"Xem chương trình đào tạo ngành {name} trên website DHV")
            st.caption(
                "Thông tin chi tiết về đề án tuyển sinh được lấy từ trợ lý DHV. "
                "Xem trực tiếp tại [Cổng tuyển sinh DHV](https://tuyensinh.dhv.edu.vn/) hoặc "
                "[Đăng ký xét tuyển trực tuyến](https://tuyensinh.dhv.edu.vn/dangky)."
            )
            return None

        if page == "compare":
            names = [name for name, _ in VERIFIED_MAJORS_2026]
            left, right = st.columns(2, gap="medium")
            with left:
                with st.container(key="compare_card_a"):
                    st.markdown(":material/school: **Ngành thứ nhất**")
                    first_default = st.session_state.get("compare_first", names[0])
                    first = st.selectbox("Ngành thứ nhất", names, index=names.index(first_default) if first_default in names else 0, key="compare_select_a", label_visibility="collapsed")
                    st.caption("Thông tin ngành lấy theo danh mục tuyển sinh DHV 2026.")
            with right:
                with st.container(key="compare_card_b"):
                    st.markdown(":material/school: **Ngành thứ hai**")
                    second = st.selectbox("Ngành thứ hai", names, index=min(3, len(names) - 1), key="compare_select_b", label_visibility="collapsed")
                    st.caption("Đặt hai ngành cạnh nhau để hỏi thêm điểm bạn quan tâm.")
            st.markdown("### So sánh theo điều bạn đang tìm hiểu")
            with st.container(key="compare_facets", horizontal=True, wrap=True, gap="small"):
                for label, icon in (("Chương trình đào tạo", "menu_book"), ("Phương thức xét tuyển", "fact_check"), ("Mã ngành", "tag")):
                    st.markdown(f":material/{icon}: **{label}**")
            with st.container(key="compare_submit"):
                if st.button("Hỏi DHV để so sánh hai ngành", icon=":material/compare_arrows:", type="primary", key="compare_submit_question"):
                    return f"So sánh ngành {first} và ngành {second} tại DHV theo thông tin tuyển sinh năm 2026."
            st.caption("Kết quả do trợ lý trả lời dựa trên dữ liệu tuyển sinh; màn hình không tính điểm phù hợp hay dự đoán cơ hội trúng tuyển.")
            return None

        if page == "checklist":
            tasks = (
                "Khám phá ngành và chương trình mình quan tâm",
                "Tìm hiểu phương thức và thời gian xét tuyển",
                "Đối chiếu thông tin trên kênh tuyển sinh chính thức",
                "Ghi lại giấy tờ cần chuẩn bị sau khi xác nhận yêu cầu",
                "Theo dõi các thông báo mới từ nhà trường",
            )
            completed = 0
            with st.container(key="checklist_card"):
                st.markdown("### Kế hoạch của bạn")
                st.caption("Checklist lưu trong phiên trình duyệt hiện tại. Các mục là gợi ý chung, không phải danh sách hồ sơ bắt buộc.")
                for index, task in enumerate(tasks):
                    key = f"admission_task_{index}"
                    value = st.checkbox(task, key=key, value=st.session_state.admission_checklist.get(key, False))
                    st.session_state.admission_checklist[key] = value
                    completed += int(value)
                progress = completed / len(tasks) * 100
                st.html(
                    f'<div class="dhv-progress"><small>{completed} / {len(tasks)} bước đã đánh dấu</small>'
                    f'<div class="dhv-progress-track"><span style="width:{progress:.0f}%"></span></div></div>'
                )
                with st.container(key="checklist_official_action"):
                    st.markdown("#### Sẵn sàng nộp hồ sơ xét tuyển?")
                    st.caption("Truy cập Cổng tuyển sinh trực tuyến để điền thông tin đăng ký xét tuyển học bạ hoặc điểm thi THPT:")
                    c_act1, c_act2 = st.columns([1.5, 1], gap="small")
                    with c_act1:
                        st.link_button("Đăng ký xét tuyển trực tuyến ↗", DHV_OFFICIAL_URLS["apply"], type="primary", width="stretch")
                    with c_act2:
                        st.link_button("Cổng tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["portal"], type="secondary", width="stretch")
            st.button("Hỏi DHV về bước tiếp theo", icon=":material/chat:", key="checklist_ask", on_click=_navigate_to, args=("chat",))
            return None

        if page == "notebook":
            with st.container(key="notebook_card"):
                st.markdown("### Nội dung đã lưu")
                st.caption("Sổ tay được giữ trong phiên đang mở; nội dung không đồng bộ lên tài khoản.")
                items = st.session_state.saved_items
                if not items:
                    st.info("Bạn có thể lưu câu trả lời trực tiếp bên dưới mỗi tin nhắn của trợ lý.")
                    if st.button("Bắt đầu trò chuyện", icon=":material/chat:", key="notebook_empty_chat", on_click=_navigate_to, args=("chat",)):
                        pass
                for index, item in enumerate(items):
                    with st.container(key=f"saved_note_{index}"):
                        st.markdown(f"#### {escape(item['title'])}")
                        _render_answer_markdown(str(item["content"]))
                        if st.button("Xóa khỏi sổ tay", icon=":material/delete_outline:", key=f"remove_saved_{index}", type="tertiary"):
                            st.session_state.saved_items.pop(index)
                            st.rerun()
            return None

        if page == "help":
            with st.container(key="help_cards"):
                st.markdown("### Danh mục Kênh tuyển sinh & Hỗ trợ chính thức DHV")
                st.write("Mọi thông tin tuyển sinh, xét tuyển và chương trình đào tạo của Trường Đại học Hùng Vương TP.HCM được công bố chính thức qua các kênh sau:")

                h_col1, h_col2 = st.columns(2, gap="medium")
                with h_col1:
                    with st.container(key="help_portal_box"):
                        st.markdown("#### :material/public: Cổng thông tin & Đăng ký")
                        st.markdown("**Cổng tuyển sinh DHV**")
                        st.caption("Tra cứu đề án tuyển sinh, các phương thức xét tuyển, điểm chuẩn và hướng dẫn nộp hồ sơ.")
                        st.link_button("Mở Cổng tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["portal"], width="stretch")

                        st.markdown("**Đăng ký xét tuyển trực tuyến**")
                        st.caption("Hệ thống đăng ký xét tuyển học bạ THPT và thi tốt nghiệp trực tuyến nhanh chóng.")
                        st.link_button("Đăng ký trực tuyến ngay ↗", DHV_OFFICIAL_URLS["apply"], type="primary", width="stretch")

                        st.markdown("**Trang chủ Trường Đại học Hùng Vương TP.HCM**")
                        st.caption("Cổng thông tin điện tử của nhà trường: lịch sử phát triển, sứ mạng và hoạt động.")
                        st.link_button("Truy cập dhv.edu.vn ↗", DHV_OFFICIAL_URLS["home"], width="stretch")

                        st.markdown("**Tin tức & Sự kiện DHV**")
                        st.caption("Cập nhật tin tức sinh viên, ngày hội Open Day và thông báo mới nhất.")
                        st.link_button("Xem Tin tức tuyển sinh ↗", DHV_OFFICIAL_URLS["news"], width="stretch")

                with h_col2:
                    with st.container(key="help_contact_box"):
                        st.markdown("#### :material/contact_phone: Kênh tư vấn & Mạng xã hội")
                        st.markdown("**Hotline Tư vấn Tuyển sinh 24/7**")
                        st.caption("Số điện thoại đường dây nóng hỗ trợ giải đáp thắc mắc tuyển sinh.")
                        st.link_button(f"Gọi Hotline: {DHV_OFFICIAL_URLS['hotline_display']}", DHV_OFFICIAL_URLS["hotline"], width="stretch")

                        st.markdown("**Zalo Official Account**")
                        st.caption("Kênh Zalo chính thức hỗ trợ thí sinh nhắn tin trực tiếp với cán bộ tuyển sinh.")
                        st.link_button("Nhắn tin Zalo Tuyển sinh ↗", DHV_OFFICIAL_URLS["zalo"], width="stretch")

                        st.markdown("**Fanpage Facebook Tuyển sinh**")
                        st.caption("Cập nhật thông tin xét tuyển, livestream tư vấn và giải đáp câu hỏi.")
                        st.link_button("Fanpage Kênh Tuyển sinh DHV ↗", DHV_OFFICIAL_URLS["facebook_admissions"], width="stretch")

                        st.markdown("**Fanpage Trường Đại học Hùng Vương TP.HCM**")
                        st.caption("Trang cộng đồng chính thức của trường.")
                        st.link_button("Fanpage Trường ĐH Hùng Vương ↗", DHV_OFFICIAL_URLS["facebook_uni"], width="stretch")

                        st.markdown("**Kênh Video Tuyển sinh**")
                        v_col1, v_col2 = st.columns(2, gap="small")
                        with v_col1:
                            st.link_button("YouTube DHV ↗", DHV_OFFICIAL_URLS["youtube"], width="stretch")
                        with v_col2:
                            st.link_button("TikTok DHV ↗", DHV_OFFICIAL_URLS["tiktok"], width="stretch")

                st.divider()
                st.info(DISCLAIMER)
                st.warning(PRIVACY_REMINDER)
                if st.button("Bắt đầu trò chuyện với Trợ lý AI", icon=":material/chat:", type="primary", key="help_start_chat", on_click=_navigate_to, args=("chat",)):
                    pass
    return None


def _render_conversation() -> None:
    with st.container(key="conversation_layout"):
        chat_col, info_col = st.columns([3.35, 1], gap="medium")
        with chat_col:
            with st.container(key="conversation_panel"):
                with st.container(key="conversation_header", horizontal=True, vertical_alignment="center"):
                    st.html('<div><small>TRỢ LÝ AI · TUYỂN SINH DHV</small><h2>Khám phá ngành học phù hợp</h2><p>Cuộc trò chuyện của bạn với trợ lý DHV</p></div>')
                    with st.popover("Tóm tắt", icon=":material/subject:", key="conversation_summary"):
                        questions = [str(row.get("content", "")).strip() for row in st.session_state.messages if isinstance(row, Mapping) and row.get("role") == "user"]
                        st.markdown("### Các ý bạn đã hỏi")
                        if questions:
                            for question in questions[-5:]:
                                st.markdown(f"- {escape(question)}")
                        else:
                            st.caption("Các câu hỏi bạn đã gửi sẽ xuất hiện ở đây.")
                    _history_picker(key="history_picker_chat")
                    st.button("Cuộc trò chuyện mới", icon=":material/add:", key="new_chat", type="secondary", on_click=_new_chat)
                st.divider()
                _render_chat_history()
                if not st.session_state.messages:
                    with st.container(key="empty_conversation"):
                        st.html('<div class="dhv-chat-empty"><span class="material-symbols-rounded">school</span><div><small>TRỢ LÝ TUYỂN SINH DHV</small><h2>Chào bạn, mình có thể giúp gì?</h2><p>Đặt câu hỏi hoặc chọn một chủ đề để cùng tìm hiểu.</p></div></div>')
                        with st.container(horizontal=True, wrap=True, gap="small"):
                            for index, (label, (_, question)) in enumerate(STARTER_QUESTIONS.items()):
                                if st.button(label, key=f"empty_chat_topic_{index}", icon=":material/arrow_forward:", type="secondary"):
                                    st.session_state.pending_question = question
                                    st.rerun()
        with info_col:
            with st.container(key="notebook_panel"):
                st.html('<div class="dhv-side-title"><div><span class="material-symbols-rounded">bookmarks</span><b>Sổ tay tuyển sinh</b></div><small>Thông tin của bạn, ngay bên cạnh.</small></div>')
                recent_user_questions = [str(row.get("content", "")) for row in st.session_state.messages if isinstance(row, Mapping) and row.get("role") == "user"]
                for question in recent_user_questions[-2:]:
                    st.html(f'<div class="dhv-memory-item"><span class="material-symbols-rounded">chat_bubble</span><div><b>{escape(question[:90])}</b><small>Trao đổi trong cuộc trò chuyện</small></div></div>')
                st.button("Mở nội dung đã lưu", icon=":material/bookmark:", key="chat_open_notebook", type="secondary", width="stretch", on_click=_navigate_to, args=("notebook",))
            with st.container(key="chat_topics_card"):
                st.html('<div class="dhv-side-title"><div><span class="material-symbols-rounded">explore</span><b>Bạn đang quan tâm?</b></div></div>')
                for index, (label, (_, question)) in enumerate(STARTER_QUESTIONS.items()):
                    if st.button(label, icon=":material/arrow_outward:", key=f"chat_topic_{index}", type="tertiary", width="stretch"):
                        st.session_state.pending_question = question
                        st.rerun()

            with st.container(key="chat_official_channels_card"):
                st.html(
                    '<div class="dhv-side-title"><div><span class="material-symbols-rounded">verified</span><b>Kênh chính thức</b></div>'
                    '<small>Cổng tuyển sinh & liên hệ</small></div>'
                )
                st.link_button("Đăng ký xét tuyển ↗", DHV_OFFICIAL_URLS["apply"], type="primary", width="stretch")
                st.link_button("Cổng tuyển sinh ↗", DHV_OFFICIAL_URLS["portal"], type="secondary", width="stretch")
                st.link_button(f"Hotline: {DHV_OFFICIAL_URLS['hotline_display']}", DHV_OFFICIAL_URLS["hotline"], type="tertiary", width="stretch")
                st.link_button("Zalo OA Tuyển sinh ↗", DHV_OFFICIAL_URLS["zalo"], type="tertiary", width="stretch")

            st.info(PRIVACY_REMINDER, icon=":material/shield:")


def _render_simple_chat_history() -> None:
    """Render the conversation without per-message editing controls."""
    for message in st.session_state.messages:
        if not isinstance(message, Mapping):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        if role == "user":
            _render_user_message(message)
        else:
            with st.chat_message("assistant", avatar=":material/school:"):
                _render_assistant_content(message)


def _render_clean_conversation() -> None:
    """Render a compact chat-first landing before the first message."""
    if not st.session_state.messages:
        with st.container(key="chat_landing_reference"):
            st.html(
                '<div class="dhv-reference-breadcrumb">'
                '<span class="material-symbols-rounded">home</span>'
                '<span>Trợ lý tuyển sinh</span><i>/</i><b>Trò chuyện cùng DHV</b></div>'
                '<section class="dhv-reference-hero">'
                '<div class="dhv-reference-hero-copy">'
                '<div class="dhv-reference-kicker"><i></i>TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG TP.HCM</div>'
                '<h1>Chọn hướng đi của<br>bạn cùng <em>DHV.</em></h1>'
                '<p>Tìm hiểu ngành học, học phí và phương thức xét tuyển trong một '
                'cuộc trò chuyện. Bắt đầu bằng điều bạn đang quan tâm nhất, '
                'chúng tôi luôn sẵn sàng đồng hành cùng bạn.</p>'
                '<div class="dhv-reference-topics">'
                '<span><b class="material-symbols-rounded">school</b>Ngành học</span>'
                '<span><b class="material-symbols-rounded">description</b>Học phí</span>'
                '<span><b class="material-symbols-rounded">group</b>Xét tuyển</span>'
                '</div></div>'
                '<div class="dhv-reference-hero-photo">'
                '<img src="/app/static/dhv-chat-hero-v1.png" '
                'alt="Sinh viên DHV tại Trường Đại học Hùng Vương TP.HCM">'
                '<div class="dhv-reference-campus-badge">'
                '<span class="material-symbols-rounded">location_on</span>'
                '<div><b>Không gian học tập tại DHV</b><small>Hiện đại · Năng động · Sáng tạo</small></div>'
                '</div>'
                '</div></section>'
            )
            with st.container(key="landing_details_reference"):
                composer_col, official_col = st.columns([.72, .28], gap="medium")
                with composer_col:
                    with st.container(key="landing_composer_reference"):
                        st.html(
                            '<div class="dhv-reference-composer-heading">'
                            '<span class="material-symbols-rounded">auto_awesome</span>'
                            '<div><b>Trợ lý tuyển sinh DHV</b>'
                            '<small>Đặt câu hỏi về ngành học, học phí, phương thức xét tuyển, đời sống sinh viên...</small></div>'
                            '<div class="dhv-reference-ready"><i></i>Luôn sẵn sàng hỗ trợ bạn</div></div>'
                        )
                        st.chat_input(
                            "Bạn muốn hỏi điều gì về tuyển sinh DHV?",
                            key="chat_input", height=96, submit_mode="disable", max_chars=MAX_QUESTION_CHARS,
                            on_submit=_submit_chat_question,
                            disabled=st.session_state.chat_request_in_progress,
                        )
                        st.html(
                            '<div class="dhv-reference-suggestion-title">'
                            '<span class="material-symbols-rounded dhv-reference-suggestion-icon" '
                            'aria-hidden="true">lightbulb</span>'
                            '<b>GỢI Ý CÂU HỎI PHỔ BIẾN</b></div>'
                        )
                        with st.container(key="landing_suggestions_reference",
                                          horizontal=True, gap="small", wrap=True):
                            suggestions = (
                                ("Học phí ngành CNTT năm 2026 là bao nhiêu?", "Học phí ngành Công nghệ thông tin năm 2026 bao nhiêu?"),
                                ("Điều kiện xét tuyển vào DHV?", "Điều kiện xét tuyển vào DHV là gì?"),
                                ("Phương thức xét tuyển năm 2026", "Năm 2026 DHV xét tuyển theo phương thức nào?"),
                                ("Ngành nào phù hợp với năng lực của tôi?", "DHV có những ngành đào tạo nào phù hợp với tôi?"),
                            )
                            for index, (title, question) in enumerate(suggestions):
                                st.button(title, key=f"chat_suggestion_{index}",
                                          type="secondary", on_click=_queue_question,
                                          args=(question,),
                                          disabled=st.session_state.chat_request_in_progress,
                                          width="content")
                with official_col:
                    with st.container(key="landing_official_reference"):
                        st.html(
                            '<div class="dhv-reference-official-heading">'
                            '<span class="material-symbols-rounded">bookmark</span>'
                            '<div><b>Kênh chính thức của DHV</b>'
                            '<small>Cập nhật thông tin tuyển sinh nhanh chóng và chính xác nhất.</small></div></div>'
                        )
                        for icon, label, caption, url in (
                            ("school", "Cổng tuyển sinh DHV", "Thông tin tuyển sinh, đăng ký xét tuyển", DHV_OFFICIAL_URLS["portal"]),
                            ("language", "Website nhà trường", "Khám phá về DHV", DHV_OFFICIAL_URLS["home"]),
                            ("description", "Đăng ký xét tuyển", "Nộp hồ sơ trực tuyến", DHV_OFFICIAL_URLS["apply"]),
                            ("phone_in_talk", "Liên hệ tư vấn", f"Hotline: {DHV_OFFICIAL_URLS['hotline_display']}", DHV_OFFICIAL_URLS["hotline"]),
                        ):
                            st.html(
                                '<a class="dhv-reference-official-link" '
                                f'href="{escape(url)}" target="_blank" rel="noreferrer">'
                                f'<span class="material-symbols-rounded">{icon}</span>'
                                f'<div><b>{escape(label)}</b><small>{escape(caption)}</small></div>'
                                '<span class="material-symbols-rounded">chevron_right</span></a>'
                            )
            st.html(
                '<footer class="dhv-reference-footer">'
                '<div class="dhv-reference-footer-brand"><b>DHV</b>'
                '<span>TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG TP.HCM'
                '<small>KIẾN THỨC · HOẠT ĐỘNG · CỘNG ĐỒNG · HỘI NHẬP</small></span></div>'
                '<div class="dhv-reference-footer-tagline">'
                '<em>Cùng bạn kiến tạo tương lai</em><i></i></div>'
                '<img class="dhv-reference-skyline" src="/app/static/dhv-city-skyline.svg" '
                'alt="" aria-hidden="true"></footer>'
            )

    else:
        with st.container(key="conversation_layout"):
            _render_simple_chat_history()


def _queue_question(question: str) -> None:
    """Record a submission before rerendering, and accept only one pending turn."""
    clean_question = question.strip()
    if (not clean_question or st.session_state.get("chat_request_in_progress")
            or st.session_state.get("pending_question")):
        return
    st.session_state.messages.append({"role": "user", "content": clean_question})
    st.session_state.pending_question = clean_question
    st.session_state.chat_request_in_progress = True
    st.session_state.account_page = "chat"


def _submit_chat_question() -> None:
    question = st.session_state.get("chat_input")
    if isinstance(question, str):
        _queue_question(question)


def _render_profile_view() -> None:
    with st.container(key="profile_workspace"):
        with st.container(key="page_breadcrumb", horizontal=True, vertical_alignment="center"):
            st.markdown(":material/home:  Không gian DHV  ›  **Tài khoản**")
            st.button("Quay lại trò chuyện", icon=":material/arrow_back:", key="profile_back_to_chat", type="tertiary", on_click=_return_to_chat)
        _render_profile_page()


def _is_admin_user() -> bool:
    user = st.session_state.get("auth_user")
    return isinstance(user, Mapping) and user.get("role") == "admin"


def _admin_source_inventory() -> tuple[list[Path], list[str], str, int | None]:
    """Read the current instance's processed knowledge files and Chroma count."""
    from src.config.settings import settings

    root = Path(settings.processed_data_dir)
    files = sorted(root.rglob("*.json")) if root.is_dir() else []
    categories = sorted({path.parent.name for path in files})
    vector_path = Path(settings.chroma_persist_dir) / "chroma.sqlite3"
    vector_status = "Chưa tạo" if not vector_path.is_file() else "Không đọc được"
    vector_count: int | None = None
    if vector_path.is_file():
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
            collection = client.get_collection(settings.chroma_collection)
            vector_count = int(collection.count())
            vector_status = "Sẵn sàng" if vector_count else "Đang trống"
        except Exception:
            vector_status = "Cần kiểm tra"
    return files, categories, vector_status, vector_count


def _render_admin_login_gate() -> None:
    with st.container(key="admin_gate"):
        left, right = st.columns([1.15, .85], gap="large", vertical_alignment="center")
        with left:
            st.html(
                '<div class="dhv-admin-gate-brand"><span class="material-symbols-rounded">school</span>'
                '<div><b>DHV</b><small>QUẢN TRỊ CHATBOT</small></div></div>'
                '<div class="dhv-admin-gate-copy"><small>KHÔNG GIAN RIÊNG CỦA QUẢN TRỊ VIÊN</small>'
                '<h1>Giữ nguồn đúng.<br><em>Giữ câu trả lời tin cậy.</em></h1>'
                '<p>Theo dõi dữ liệu tuyển sinh và kiểm tra chất lượng câu trả lời của trợ lý DHV.</p></div>'
            )
        with right:
            with st.container(key="admin_login_card"):
                st.html('<div class="dhv-admin-card-badge"><span class="material-symbols-rounded">shield</span> KHU VỰC QUẢN TRỊ</div>')
                if not st.session_state.auth_user:
                    st.markdown("### Đăng nhập quản trị")
                    st.caption("Dùng tài khoản Supabase riêng đã được cấp quyền admin.")
                    if not is_supabase_configured():
                        st.warning("Ứng dụng chưa được kết nối Supabase.")
                    if st.button("Đăng nhập", icon=":material/login:", type="primary", key="admin_login", width="stretch"):
                        open_auth("login")
                        st.rerun()
                else:
                    st.markdown("### Tài khoản này chưa có quyền quản trị")
                    st.caption("Đăng xuất tài khoản hiện tại rồi đăng nhập bằng tài khoản admin riêng.")
                    st.button("Đăng xuất tài khoản hiện tại", icon=":material/logout:", key="admin_gate_logout", width="stretch", on_click=_logout_account)


def _render_admin_console() -> None:
    """Admin-only console. The URL is not a permission check; Supabase app_metadata is."""
    if not st.session_state.auth_user or not _is_admin_user():
        _render_admin_login_gate()
        return

    from src.config.settings import settings

    files, categories, vector_status, vector_count = _admin_source_inventory()
    page = st.session_state.get("admin_page", "overview")
    allowed_pages = {"overview", "sources", "quality"}
    if page not in allowed_pages:
        page = "overview"
        st.session_state.admin_page = page

    with st.sidebar:
        st.html(
            '<div class="dhv-admin-side-brand"><span class="material-symbols-rounded">school</span>'
            '<div><b>DHV</b><small>ADMIN CONSOLE</small></div></div>'
        )
        st.html('<div class="dhv-admin-side-label">QUẢN LÝ CHATBOT</div>')
        for label, icon, target in (
            ("Tổng quan", "dashboard", "overview"),
            ("Nguồn tài liệu", "description", "sources"),
            ("Kiểm tra câu trả lời", "fact_check", "quality"),
        ):
            if st.button(
                label, icon=f":material/{icon}:", key=f"admin_nav_{target}",
                type="primary" if page == target else "tertiary", width="stretch",
            ):
                st.session_state.admin_page = target
                st.rerun()
        with st.container(key="admin_sidebar_footer"):
            st.html(
                '<div class="dhv-admin-current-user"><span class="material-symbols-rounded">admin_panel_settings</span>'
                '<div><b>Quản trị viên</b><small>Quyền truy cập đã xác minh</small></div></div>'
            )
            if st.button("Về chatbot", icon=":material/arrow_back:", key="admin_exit", width="stretch"):
                st.query_params.clear()
                st.rerun()
            st.button("Đăng xuất", icon=":material/logout:", key="admin_logout", width="stretch", on_click=_logout_account)

    labels = {
        "overview": ("TỔNG QUAN", "Trung tâm quản trị DHV", "Tình trạng dữ liệu đang được dùng bởi chatbot trên máy chủ này."),
        "sources": ("TRI THỨC DHV", "Nguồn tài liệu", "Danh sách tệp JSON đã xử lý trong kho dữ liệu hiện tại."),
        "quality": ("KIỂM TRA CHATBOT", "Thử câu hỏi", "Gửi câu hỏi thử qua cùng pipeline đang phục vụ người dùng."),
    }
    eyebrow, title, description = labels[page]
    with st.container(key="admin_console"):
        with st.container(key="admin_topbar", horizontal=True, vertical_alignment="center"):
            st.html(
                '<div class="dhv-admin-topbrand"><span class="material-symbols-rounded">shield</span>'
                '<b>Quản trị chatbot tuyển sinh DHV</b></div>'
            )
            st.html('<span class="dhv-admin-live"><i></i> KHU VỰC QUẢN TRỊ</span>')
        st.html(
            f'<div class="dhv-admin-page-heading"><small>{escape(eyebrow)}</small>'
            f'<h1>{escape(title)}</h1><p>{escape(description)}</p></div>'
        )

        if page == "overview":
            vector_value = f"{vector_count:,}" if vector_count is not None else vector_status
            stat_data = (
                ("Tài liệu đã xử lý", str(len(files)), "Tệp JSON trong kho hiện tại", "description"),
                ("Nhóm dữ liệu", str(len(categories)), "Các chủ đề có tài liệu", "category"),
                ("Bản ghi tìm kiếm", vector_value, "Collection Chroma đang cấu hình", "database"),
            )
            with st.container(key="admin_stats", horizontal=True, gap="small"):
                for label, value, caption, icon in stat_data:
                    st.html(
                        '<article class="dhv-admin-stat">'
                        f'<div><span>{escape(label)}</span><i class="material-symbols-rounded">{escape(icon)}</i></div>'
                        f'<strong>{escape(value)}</strong><small>{escape(caption)}</small></article>'
                    )
            col_sources, col_tools = st.columns([1.1, .9], gap="medium")
            with col_sources:
                with st.container(key="admin_overview_sources"):
                    st.markdown("### Nguồn dữ liệu")
                    st.caption(f"{len(files)} tệp · {len(categories)} nhóm · {vector_status}")
                    if files:
                        for path in files[:5]:
                            st.html(
                                '<div class="dhv-admin-file-row"><span class="material-symbols-rounded">description</span>'
                                f'<div><b>{escape(path.stem.replace("_", " "))}</b>'
                                f'<small>{escape(path.parent.name.replace("_", " "))}</small></div></div>'
                            )
                    else:
                        st.info("Chưa tìm thấy tài liệu đã xử lý trên máy chủ này.")
                    if st.button("Mở danh sách nguồn", icon=":material/arrow_forward:", key="admin_overview_sources_open"):
                        st.session_state.admin_page = "sources"
                        st.rerun()
            with col_tools:
                with st.container(key="admin_overview_quality"):
                    st.markdown("### Kiểm tra câu trả lời")
                    st.caption("Thử một câu hỏi bằng chính bộ truy xuất và mô hình hiện tại.")
                    st.html(
                        '<div class="dhv-admin-callout"><span class="material-symbols-rounded">fact_check</span>'
                        '<div><b>Không dùng số liệu minh họa</b><small>Chỉ hiển thị trạng thái đọc được từ tệp và Chroma trên máy chủ.</small></div></div>'
                    )
                    if st.button("Mở công cụ kiểm tra", icon=":material/arrow_forward:", key="admin_overview_quality_open", type="primary"):
                        st.session_state.admin_page = "quality"
                        st.rerun()
            st.caption("Các câu hỏi của user chưa được ghi vào nhật ký tập trung, nên bảng này không tạo số liệu lượt hỏi hoặc hàng chờ giả.")

        elif page == "sources":
            with st.container(key="admin_sources_panel"):
                st.markdown("### Kho tài liệu đã xử lý")
                st.caption(f"Thư mục: `{Path(settings.processed_data_dir)}` · Vector store: {vector_status}")
                if not files:
                    st.info("Kho dữ liệu hiện tại chưa có tệp JSON đã xử lý.")
                else:
                    for index, path in enumerate(files):
                        try:
                            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                            size_kb = max(1, round(path.stat().st_size / 1024))
                        except OSError:
                            modified, size_kb = "Không đọc được", 0
                        st.html(
                            '<div class="dhv-admin-source-row">'
                            '<span class="dhv-admin-file-icon material-symbols-rounded">description</span>'
                            f'<div><b>{escape(path.stem.replace("_", " "))}</b>'
                            f'<small>{escape(path.parent.name.replace("_", " "))} · Cập nhật {escape(modified)}</small></div>'
                            f'<span class="dhv-admin-file-size">{size_kb} KB</span></div>'
                        )
                st.info("Màn hình chỉ đọc. Tệp nguồn chỉ được thêm sau khi qua quy trình xác minh và dựng lại Chroma của dự án.")

        else:
            with st.container(key="admin_quality_panel"):
                st.markdown("### Chạy thử truy vấn")
                st.caption("Kết quả là phản hồi trực tiếp từ pipeline hiện tại; thao tác này không lưu câu hỏi vào dữ liệu người dùng.")
                with st.form("admin_question_form", clear_on_submit=False, border=False):
                    question = st.text_area(
                        "Câu hỏi cần kiểm tra", key="admin_test_question",
                        placeholder="Ví dụ: DHV có học bổng không?", height=100,
                    )
                    submitted = st.form_submit_button("Chạy kiểm tra", icon=":material/play_arrow:", type="primary")
                if submitted:
                    if not question.strip():
                        st.warning("Nhập câu hỏi trước khi chạy.")
                    else:
                        from src.chatbot.chat_service import ask_chatbot
                        from src.chatbot.query_analysis import ConversationState

                        try:
                            with st.spinner("Đang chạy truy xuất và tạo câu trả lời..."):
                                result = ask_chatbot(
                                    question.strip(),
                                    conversation_state=ConversationState().to_dict(),
                                    conversation_history=[],
                                    bypass_cache=True,
                                )
                            st.session_state.admin_quality_result = result
                            st.session_state.admin_quality_question = question.strip()
                        except Exception:
                            st.session_state.admin_quality_result = {
                                "answer": GENERIC_ERROR_ANSWER, "status": "error", "sources": [],
                            }
                            st.session_state.admin_quality_question = question.strip()
                result = st.session_state.get("admin_quality_result")
                if isinstance(result, Mapping):
                    st.divider()
                    st.caption(f"Câu hỏi: {st.session_state.get('admin_quality_question', '')} · Trạng thái: {result.get('status', 'không rõ')}")
                    st.markdown(str(result.get("answer") or GENERIC_ERROR_ANSWER))
                    sources = result.get("sources")
                    if isinstance(sources, list) and sources:
                        st.markdown("**Nguồn được trả về**")
                        for source in sources:
                            if not isinstance(source, Mapping):
                                continue
                            title = str(source.get("title") or "Nguồn DHV")
                            url = str(source.get("url") or "")
                            if _is_official_url(url):
                                st.link_button(title, url, key=f"admin_source_link_{abs(hash(url))}")
                            else:
                                st.markdown(f"- {escape(title)}")
                    trace = result.get("trace")
                    if isinstance(trace, Mapping):
                        with st.expander("Chi tiết truy xuất", expanded=False):
                            st.json(trace, expanded=False)


def _record_and_render_exchange(question: str) -> None:
    """Answer the user turn already recorded by the submission callback."""

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
if st.query_params.get("auth") == "recovery":
    # Recovery callbacks carry short-lived credentials in the URL fragment.
    # Handle this route before normal auth restoration or chat/admin rendering.
    render_password_recovery_page()
    st.stop()

init_auth()
if st.session_state.pop("auth_login_notice", False):
    st.toast("Đăng nhập thành công.", icon=":material/check_circle:", duration=4)
if st.session_state.pop("auth_session_expired_notice", False):
    st.toast("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", icon=":material/info:", duration=5)

from src.chatbot.chat_service import MAX_QUESTION_CHARS, ask_chatbot
from src.chatbot.query_analysis import ConversationState
from src.chatbot.warmup import start_background_warmup, wait_for_warmup

_init_session_state()
admin_console_route = st.query_params.get("console") == "admin"
if admin_console_route:
    _render_admin_console()
else:
    start_background_warmup()
    page = st.session_state.get("account_page", "chat")
    if page not in {"chat", "profile"}:
        page = "chat"
        st.session_state.account_page = page
    _render_sidebar()
    _render_topbar()

    show_profile = bool(st.session_state.auth_user) and page == "profile"
    if show_profile:
        _render_profile_view()
    else:
        _render_clean_conversation()
        if st.session_state.messages:
            st.chat_input(
                "Nhập câu hỏi về tuyển sinh DHV...",
                key="chat_input", submit_mode="disable", max_chars=MAX_QUESTION_CHARS,
                on_submit=_submit_chat_question,
                disabled=st.session_state.chat_request_in_progress,
            )
        with st.container(key="chat_note"):
            st.caption(
                "Thông tin quan trọng vui lòng đối chiếu tại "
                "[Cổng tuyển sinh DHV](https://tuyensinh.dhv.edu.vn/)."
            )

    queued_question = st.session_state.get("pending_question")
    if isinstance(queued_question, str) and queued_question.strip():
        try:
            with st.container(key="conversation_pending_answer"):
                _record_and_render_exchange(queued_question)
            st.session_state.pop("pending_question", None)
            _save_current_chat()
        finally:
            st.session_state.chat_request_in_progress = False
        st.rerun()

if st.session_state.auth_view and (
    not st.session_state.auth_user or st.session_state.auth_view == "forgot"
):
    render_auth_dialog()
