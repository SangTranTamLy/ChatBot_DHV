"""Stable service boundary for the future Streamlit UI (Task D)."""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from src.config.settings import Settings, settings

from .rag_chain import ask_chatbot as _ask_chatbot
from .query_analysis import ConversationState


class ChatService:
    """UI-facing service that owns the Task C RAG dependencies."""

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
        """Compatibility alias for callers using the service method name."""

        return self.ask(question, conversation_state=conversation_state)


_default_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Lazily create the default service so importing the UI stays cheap."""

    global _default_service
    if _default_service is None:
        _default_service = ChatService()
    return _default_service


def ask_chatbot(
    question: str,
    *,
    conversation_state: ConversationState | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Public API used by the UI and simple scripts."""

    return get_chat_service().ask(question, conversation_state=conversation_state)


__all__ = ["ChatService", "ask_chatbot", "get_chat_service"]
