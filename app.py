"""Giao diện chat Streamlit cho chatbot tuyển sinh DHV.

Giao diện này chỉ có một điểm giao tiếp duy nhất với backend: ``ask_chatbot`` từ Task C.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from src.chatbot.chat_service import ask_chatbot
from src.chatbot.query_analysis import ConversationState


load_dotenv()

st.set_page_config(
    page_title="Chatbot tuyển sinh DHV",
    page_icon=":material/school:",
    layout="centered",
)


def _inject_chat_styles() -> None:
    """Giữ tin nhắn phẳng; chỉ bảng được nhóm trong container có khung."""

    st.html(
        """
        <style>
        [data-testid="stChatMessage"] {
            width: 100%;
            padding: 0.42rem 0;
            gap: 0.55rem;
            background: transparent;
            border: none;
            box-shadow: none;
        }
        [data-testid="stChatMessage"] > [data-testid="stChatMessageContent"] {
            max-width: 84%;
            min-width: 0;
            padding: 0.2rem 0;
            border: none;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
            overflow-wrap: anywhere;
        }
        [data-testid="stChatMessage"]:has(> [data-testid="stChatMessageContent"][aria-label*="user"]) {
            flex-direction: row;
        }
        [data-testid="stChatMessageContent"][aria-label*="user"] {
            max-width: 72%;
            margin-left: auto;
            padding: 0.2rem 0;
            border: none;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
        }
        [data-testid="stChatMessageContent"][aria-label*="assistant"] {
            padding: 0.2rem 0;
            border: none;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
            line-height: 1.62;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:last-child {
            margin-bottom: 0;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ul,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ol {
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
            padding-left: 1.25rem;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
            margin: 0.28rem 0;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] table {
            display: block;
            max-width: 100%;
            overflow-x: auto;
            white-space: nowrap;
            border-collapse: collapse;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] td {
            padding: 0.55rem 0.75rem;
            border: 1px solid #d9e2ec;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th {
            background: #f5f7fa;
            font-weight: 600;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h1,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h2,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h3 {
            margin-top: 0.25rem;
            margin-bottom: 0.55rem;
        }
        [data-testid="stChatMessage"] + [data-testid="stCaptionContainer"] {
            margin-left: 2.8rem;
        }
        </style>
        """
    )


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


def _init_session_state() -> None:
    """Khởi tạo toàn bộ trạng thái chat của người dùng tại một nơi."""

    st.session_state.setdefault("messages", [])
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
    if not isinstance(answer, str) or not answer.strip():
        answer = GENERIC_ERROR_ANSWER
    else:
        if not allow_direct_website_url:
            answer = _strip_display_urls(answer)
        if not answer:
            answer = GENERIC_ERROR_ANSWER

    normalised = {
        "answer": answer.strip(),
        "status": status,
    }
    if allow_direct_website_url:
        normalised["allow_direct_website_url"] = True
    return normalised


def _ask_question(question: str) -> dict[str, object]:
    """Chỉ gọi service của Task C và phân loại các lỗi bất ngờ ở ranh giới UI."""

    try:
        result = ask_chatbot(
            question,
            conversation_state=st.session_state.get("conversation_state"),
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

    before, table, after = _split_markdown_table(answer)
    if before:
        st.markdown(before, unsafe_allow_html=False)
    if table:
        with st.container(border=True):
            st.markdown(table, unsafe_allow_html=False)
    if after:
        st.markdown(after, unsafe_allow_html=False)


def _render_assistant_content(message: Mapping[str, Any]) -> None:
    """Hiển thị mọi trạng thái assistant bằng nội dung phẳng, riêng bảng có khung."""

    answer = str(
        message.get("content")
        or message.get("answer")
        or GENERIC_ERROR_ANSWER
    )
    if not message.get("allow_direct_website_url"):
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


def _render_welcome() -> None:
    """Hiển thị màn hình chào mừng khi cuộc hội thoại chưa có tin nhắn."""

    if st.session_state.messages:
        return

    with st.chat_message("assistant", avatar=":material/school:"):
        st.markdown(
            "Xin chào! Tôi là ChatBot DHV – Trợ lý Tuyển sinh Trường Đại học Hùng Vương TP.HCM.\n\n"
            "Tôi có thể giải đáp nhanh cho bạn về:\n\n"
            "- Phương thức & điều kiện xét tuyển\n"
            "- Chỉ tiêu & ngành đào tạo\n"
            "- Hồ sơ, lịch trình & thủ tục nhập học\n\n"
            "Bạn đang cần hỗ trợ nội dung nào?",
            unsafe_allow_html=False,
        )

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
    st.session_state.messages.append(message)


_init_session_state()
_inject_chat_styles()

st.title("CHATBOT TƯ VẤN TUYỂN SINH DHV", icon=":material/school:")
st.caption("Trợ lý tra cứu thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM")

with st.sidebar:
    st.subheader("Lưu ý")
    st.info(PRIVACY_REMINDER, icon=":material/lock:")
    st.caption("Phạm vi: tuyển sinh DHV, ưu tiên dữ liệu đã kiểm chứng năm 2026.")

typed_question = st.chat_input(
    "Nhập câu hỏi về tuyển sinh DHV...",
    key="chat_input",
)

_render_chat_history()

if isinstance(typed_question, str) and typed_question.strip():
    _record_and_render_exchange(typed_question.strip())
else:
    _render_welcome()

st.caption(DISCLAIMER)
