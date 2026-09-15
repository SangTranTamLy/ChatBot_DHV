"""Ranh giới dịch vụ ổn định dành cho giao diện Streamlit (Task D)."""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from src.config.settings import Settings, settings

from .rag_chain import ask_chatbot as _ask_chatbot
from .query_analysis import ConversationState


class ChatService:
    """Dịch vụ cung cấp cho UI, chịu trách nhiệm quản lý các phụ thuộc RAG (Task C)."""

    def __init__(
        self,
        *,
        settings_obj: Settings = settings,
        retriever: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self.settings = settings_obj
        self.retriever = retriever
        self.llm = llm

    def ask(
        self,
        question: str,
        *,
        conversation_state: ConversationState | Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return _ask_chatbot(
            question,
            retriever=self.retriever,
            llm=self.llm,
            settings_obj=self.settings,
            conversation_state=conversation_state,
        )

    def ask_chatbot(
        self,
        question: str,
        *,
        conversation_state: ConversationState | Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Bí danh tương thích cho các hàm gọi sử dụng tên phương thức của dịch vụ."""

        return self.ask(question, conversation_state=conversation_state)


_default_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Khởi tạo trễ dịch vụ mặc định để việc import UI không tốn nhiều tài nguyên."""

    global _default_service
    if _default_service is None:
        _default_service = ChatService()
    return _default_service


def ask_chatbot(
    question: str,
    *,
    conversation_state: ConversationState | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """API công khai được sử dụng bởi giao diện (UI) và các script đơn giản."""

    return get_chat_service().ask(question, conversation_state=conversation_state)


__all__ = ["ChatService", "ask_chatbot", "get_chat_service"]
