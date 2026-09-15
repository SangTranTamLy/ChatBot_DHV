"""Streamlit chat UI for the DHV admissions chatbot.

The UI deliberately has one backend boundary: ``ask_chatbot`` from Task C.
"""

from __future__ import annotations

from collections.abc import Mapping
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


QUICK_QUESTIONS = (
    "Học phí DHV 2026",
    "Học bổng DHV 2026",
    "Hồ sơ xét tuyển bổ sung",
    "Lịch tuyển sinh",
    "Thủ tục nhập học",
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

STATUS_ICONS = {
    "clarification": ":material/help:",
    "no_data": ":material/search_off:",
    "out_of_scope": ":material/info:",
    "ollama_offline": ":material/cloud_off:",
    "vector_db_error": ":material/storage:",
    "error": ":material/error:",
}
KNOWN_STATUSES = frozenset({"ok", *STATUS_ICONS})


def _init_session_state() -> None:
    """Initialize all per-user chat state in one place."""

    st.session_state.setdefault("messages", [])
    initial_state = ConversationState().to_dict()
    st.session_state.setdefault("conversation_state", dict(initial_state))
    # Keep both service-facing names synchronized so a clarification or list
    # response cannot lose bounded context on the next Streamlit rerun.
    st.session_state.setdefault(
        "state", dict(st.session_state.get("conversation_state") or initial_state)
    )


def _normalise_result(result: object) -> dict[str, object]:
    """Keep malformed service payloads from breaking the rendered UI."""

    if not isinstance(result, Mapping):
        return {"answer": GENERIC_ERROR_ANSWER, "status": "error"}

    status = result.get("status")
    if not isinstance(status, str) or status not in KNOWN_STATUSES:
        status = "error"

    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = GENERIC_ERROR_ANSWER

    return {
        "answer": answer.strip(),
        "status": status,
    }


def _ask_question(question: str) -> dict[str, object]:
    """Call only the Task C service and classify unexpected UI-boundary errors."""

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
        # The user sees a safe message; implementation details stay in the backend.
        return {
            "answer": GENERIC_ERROR_ANSWER,
            "status": "error",
        }


def _render_assistant_content(message: Mapping[str, Any]) -> None:
    """Render answer text and status feedback for one response."""

    answer = str(
        message.get("content")
        or message.get("answer")
        or GENERIC_ERROR_ANSWER
    )
    status = str(message.get("status") or "error")

    if status == "ok":
        # unsafe_allow_html remains false so model output cannot inject HTML.
        st.markdown(answer, unsafe_allow_html=False)
        return

    if status == "out_of_scope":
        st.info(answer, icon=STATUS_ICONS[status])
    elif status == "clarification":
        st.info(answer, icon=STATUS_ICONS[status])
    elif status in {"no_data", "ollama_offline"}:
        st.warning(answer, icon=STATUS_ICONS[status])
    else:
        st.error(answer, icon=STATUS_ICONS.get(status, ":material/error:"))


def _render_chat_history() -> None:
    """Render persisted user and assistant messages with native chat bubbles."""

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


def _render_welcome() -> object | None:
    """Render the empty-chat onboarding state and return a selected quick prompt."""

    if st.session_state.messages:
        return None

    with st.chat_message("assistant", avatar=":material/school:"):
        st.markdown(
            "Chào bạn! Tôi có thể hỗ trợ tra cứu thông tin tuyển sinh DHV đã "
            "được kiểm chứng cho năm 2026. Bạn muốn hỏi điều gì?",
            unsafe_allow_html=False,
        )

    st.caption("Bạn có thể bắt đầu bằng một câu hỏi gợi ý:")
    return st.pills(
        "Câu hỏi gợi ý",
        QUICK_QUESTIONS,
        key="quick_question",
        label_visibility="collapsed",
        width="stretch",
    )


def _record_and_render_exchange(question: str) -> None:
    """Persist and render one exchange, including safe service error handling."""

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question, unsafe_allow_html=False)

    with st.chat_message("assistant", avatar=":material/school:"):
        with st.spinner("Đang tra cứu thông tin tuyển sinh..."):
            result = _ask_question(question)
        _render_assistant_content(result)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "status": result["status"],
        }
    )


_init_session_state()

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
    selected_question = _render_welcome()
    if isinstance(selected_question, str) and selected_question.strip():
        _record_and_render_exchange(selected_question.strip())
        st.rerun()

st.caption(DISCLAIMER)
