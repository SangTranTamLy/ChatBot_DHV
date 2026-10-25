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

from src.supabase_auth import AuthServiceError, change_password
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
    chat_keys = ("messages", "chats", "active_chat", "next_chat", "conversation_state", "state")
    previous_owner = st.session_state.get("chat_owner")
    if "chat_owner" in st.session_state and previous_owner != owner:
        if previous_owner:
            sessions[previous_owner] = {key: deepcopy(st.session_state[key])
                                        for key in chat_keys if key in st.session_state}
        for key in (*chat_keys, "chat_input", "pending_question", "saved_items", "admission_checklist"):
            st.session_state.pop(key, None)
        if st.session_state.get("account_page") != "chat":
            st.session_state.account_page = "explore"
        if owner in sessions:
            st.session_state.update(deepcopy(sessions[owner]))
    st.session_state.chat_owner = owner
    if st.session_state.get("messages"):
        st.session_state.setdefault("account_page", "chat")
    else:
        st.session_state.setdefault("account_page", "explore")
    st.session_state.setdefault("admission_checklist", {})
    st.session_state.setdefault("saved_items", [])
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

    for index, message in enumerate(st.session_state.messages):
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
        if role == "assistant" and st.button(
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
        if not st.session_state.chats:
            st.caption("Các cuộc trò chuyện đã lưu sẽ xuất hiện ở đây.")
            return
        groups = {"Hôm nay": [], "Hôm qua": [], "Trước đó": []}
        for chat_id, chat in st.session_state.chats.items():
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
                title = next(
                    (row["content"] for row in chat["messages"] if row.get("role") == "user"),
                    "Cuộc trò chuyện",
                )
                st.button(
                    str(title)[:70], icon=":material/chat_bubble_outline:", type="tertiary",
                    key=f"{key}_chat_{chat_id}", help=str(title), width="stretch",
                    on_click=_open_chat, args=(chat_id,),
                )


def _render_topbar() -> None:
    page = st.session_state.get("account_page", "explore")
    chat_active = page == "chat"
    explore_active = page == "explore"
    brand = (
        '<div class="dhv-brand-lockup" aria-label="DHV, trợ lý tuyển sinh">'
        '<span class="dhv-brand-cap material-symbols-rounded" aria-label="Mũ tốt nghiệp">school</span>'
        '<span class="dhv-brand-words"><b>DHV</b><small>TRỢ LÝ TUYỂN SINH</small></span>'
        '<span class="dhv-brand-divider"></span><span class="dhv-brand-context">Không gian tuyển sinh</span></div>'
    )
    with st.container(key="topbar"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.html(brand)
            st.button(
                "Khám phá DHV", key="top_nav_explore",
                type="primary" if explore_active else "tertiary",
                on_click=_navigate_to, args=("explore",),
            )
            st.button(
                "Hỏi DHV", key="top_nav_chat",
                type="primary" if chat_active else "tertiary",
                on_click=_navigate_to, args=("chat",),
            )
            st.button(
                "Lộ trình của tôi", icon=":material/check_circle:", key="top_nav_journey",
                type="primary" if page == "checklist" else "tertiary",
                on_click=_navigate_to, args=("checklist",),
            )
            with st.popover("Tìm nhanh", icon=":material/search:", key="quick_search", help="Tìm nhanh thông tin tuyển sinh DHV"):
                with st.form("quick_search_form", clear_on_submit=True, border=False):
                    query = st.text_input(
                        "Tìm trong tuyển sinh DHV",
                        placeholder="Ngành, xét tuyển, học phí…",
                        label_visibility="collapsed",
                    )
                    if st.form_submit_button("Hỏi trợ lý DHV", icon=":material/arrow_forward:", width="stretch") and query.strip():
                        st.session_state.pending_question = query.strip()
                        st.session_state.account_page = "chat"
                        st.rerun()
                st.caption("Tìm nhanh các thông tin trong dữ liệu tuyển sinh DHV.")
            _history_picker(key="history_picker_top")
            st.link_button(
                "Đăng ký xét tuyển ↗",
                DHV_OFFICIAL_URLS["apply"],
                type="primary",
                help="Mở Cổng đăng ký xét tuyển trực tuyến DHV",
            )
            if st.session_state.auth_user:
                name = st.session_state.auth_user["name"]
                initials = "".join(part[0] for part in name.split()[-2:]).upper() or "U"
                with st.popover(initials, key="header_account", help=name):
                    st.caption(name)
                    st.button("Tài khoản", icon=":material/person:", key="account_settings",
                              on_click=_open_profile, width="stretch")
                    st.button("Đăng xuất", icon=":material/logout:", key="logout",
                              on_click=_logout_account, width="stretch")
            else:
                st.button("Đăng nhập", icon=":material/person:", key="open_login", on_click=open_auth)


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
        st.session_state.chats[st.session_state.active_chat] = {
            "messages": deepcopy(st.session_state.messages),
            "conversation_state": deepcopy(st.session_state.conversation_state),
            "updated_at": st.session_state.chats.get(st.session_state.active_chat, {}).get("updated_at"),
        }


def _new_chat() -> None:
    st.session_state.account_page = "chat"
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
    st.session_state.account_page = "chat"
    _save_current_chat()
    saved = st.session_state.chats[chat_id]
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
    """Render the admissions sidebar navigation with clean branding and full-width links."""
    _save_current_chat()
    page = st.session_state.get("account_page", "explore")
    with st.sidebar:
        st.html(
            '<div class="dhv-sidebar-brand" title="Trường Đại học Hùng Vương TP.HCM">'
            '<div class="dhv-sidebar-badge">'
            '<span class="dhv-sidebar-badge-icon material-symbols-rounded">school</span>'
            '</div>'
            '<div class="dhv-sidebar-brand-info">'
            '<b class="dhv-sidebar-brand-name">DHV ADMISSIONS</b>'
            '<small class="dhv-sidebar-brand-sub">ĐẠI HỌC HÙNG VƯƠNG</small>'
            '</div>'
            '</div>'
        )
        for label, icon, target in (
            ("Khám phá", ":material/dashboard:", "explore"),
            ("Hỏi DHV", ":material/forum:", "chat"),
            ("Ngành học", ":material/school:", "majors"),
            ("So sánh ngành", ":material/compare_arrows:", "compare"),
            ("Lộ trình của tôi", ":material/task_alt:", "checklist"),
            ("Sổ tay tuyển sinh", ":material/bookmark:", "notebook"),
        ):
            active = page == target
            st.button(
                label, icon=icon, key=f"rail_{target}",
                type="primary" if active else "tertiary", width="stretch",
                on_click=_navigate_to, args=(target,),
            )
        with st.container(key="rail_official_links"):
            st.html('<div class="dhv-sidebar-sec-label"><span>LIÊN KẾT NHANH</span></div>')
            st.link_button(
                "Đăng ký xét tuyển ↗",
                DHV_OFFICIAL_URLS["apply"],
                type="primary",
                width="stretch",
                help="Mở Cổng đăng ký xét tuyển trực tuyến DHV",
            )
            st.link_button(
                "Cổng tuyển sinh ↗",
                DHV_OFFICIAL_URLS["portal"],
                type="tertiary",
                width="stretch",
                help="Mở Cổng thông tin tuyển sinh chính thức",
            )
        with st.container(key="rail_bottom"):
            st.button(
                "Trợ giúp & Hỗ trợ", icon=":material/help_outline:", key="rail_help",
                type="primary" if page == "help" else "tertiary", width="stretch",
                on_click=_navigate_to, args=("help",),
            )
            if st.session_state.auth_user:
                name = st.session_state.auth_user["name"]
                st.button(
                    name, icon=":material/person:", key="rail_profile",
                    type="primary" if page == "profile" else "tertiary", width="stretch",
                    on_click=_open_profile, help=f"Tài khoản: {name}",
                )
            else:
                st.button(
                    "Đăng nhập", icon=":material/login:", key="rail_login",
                    type="tertiary", width="stretch", on_click=open_auth,
                    help="Đăng nhập tài khoản",
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


def _render_profile_view() -> None:
    with st.container(key="profile_workspace"):
        with st.container(key="page_breadcrumb", horizontal=True, vertical_alignment="center"):
            st.markdown(":material/home:  Không gian DHV  ›  **Tài khoản**")
            st.button("Quay lại trò chuyện", icon=":material/arrow_back:", key="profile_back_to_chat", type="tertiary", on_click=_return_to_chat)
        _render_profile_page()


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
if st.session_state.pop("auth_session_expired_notice", False):
    st.toast("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", icon=":material/info:", duration=5)

from src.chatbot.chat_service import ask_chatbot
from src.chatbot.query_analysis import ConversationState
from src.chatbot.warmup import start_background_warmup, wait_for_warmup

start_background_warmup()
_init_session_state()
_render_sidebar()
_render_topbar()
_render_mobile_nav()

if st.session_state.get("messages") and st.session_state.get("account_page") == "explore":
    st.session_state.account_page = "chat"
page = st.session_state.get("account_page", "explore")
show_profile = bool(st.session_state.auth_user) and page == "profile"
selected_question: str | None = None
typed_question: str | None = None

if show_profile:
    _render_profile_view()
elif page == "chat":
    _render_conversation()
    typed_question = st.chat_input(
        "Hỏi thêm về điều bạn quan tâm…",
        key="chat_input",
        submit_mode="disable",
    )
    with st.container(key="chat_note"):
        st.caption(
            "Đối chiếu kênh chính thức: [Cổng tuyển sinh](https://tuyensinh.dhv.edu.vn/) · "
            "[Đăng ký trực tuyến](https://tuyensinh.dhv.edu.vn/dangky) · "
            "Hotline: [028 7100 0888](tel:02871000888) · "
            "[Zalo Tuyển sinh](https://zalo.me/1822829687649866202)"
        )
elif page in {"majors", "compare", "checklist", "notebook", "help"}:
    selected_question = _render_workspace_page(page)
else:
    selected_question = _render_welcome()

queued_question = st.session_state.pop("pending_question", None)
question_to_send = queued_question or typed_question or selected_question
if isinstance(question_to_send, str) and question_to_send.strip():
    st.session_state.account_page = "chat"
    _record_and_render_exchange(question_to_send.strip())
    _save_current_chat()
    st.rerun()

if st.session_state.auth_view and not st.session_state.auth_user:
    render_auth_dialog()
