# -*- coding: utf-8 -*-
"""
DHV Admissions Chatbot - Chat Service Adapter
Thin integration adapter providing structured UI responses, fast-track conversational
handling (<1ms) and answer caching for repeated queries.
Matches the architectural pattern of VietLabor AI (app/chat_service.py).
"""
from __future__ import annotations

import logging
import time
import unicodedata
from collections.abc import Mapping
from typing import Any, Dict, Optional

from src.config.settings import Settings, settings
from .answer_cache import (
    enabled as cache_enabled,
    get as cache_get,
    is_cacheable,
    make_key as cache_make_key,
    put as cache_put,
)
from .conversational import detect_smalltalk
from .query_analysis import ConversationState
from .rag_chain import ask_chatbot as _ask_chatbot
from .history_context import bounded_history, resolve_history_question

logger = logging.getLogger(__name__)


def answer_smalltalk(question: str, has_history: bool = False) -> Optional[Dict[str, Any]]:
    """Instant UI response for greetings/thanks/identity, or None for real questions.

    Needs no retriever, embedding model or Ollama, so social turns like "Xin chào",
    "Bạn là ai?", "Cảm ơn bạn" answer immediately (<1ms) with a warm admissions counselor voice.
    """
    norm_q = unicodedata.normalize("NFC", question or "").strip()
    reply = detect_smalltalk(norm_q, has_history=has_history)
    if reply is None:
        return None
    return {
        "answer": reply.answer,
        "sources": [],
        "status": "ok",
        "state": {},
        "conversation_state": {},
        "is_smalltalk": True,
        "smalltalk_intent": reply.intent,
        "suggested_followups": list(reply.suggestions),
        "latency_ms": 0.0,
        "cache_hit": False,
    }


class ChatService:
    """Thin adapter providing structured UI responses with conversational fast-track and caching."""

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
        bypass_cache: bool = False,
        conversation_history: object = None,
    ) -> dict[str, object]:
        """Executes RAG inference and maps output to clean UI response schema."""
        t0 = time.perf_counter()
        norm_q = unicodedata.normalize("NFC", question or "").strip()
        state = ConversationState.from_value(conversation_state, default_year=self.settings.target_year)
        history = bounded_history(conversation_history, norm_q)
        has_history = bool(
            history
            or
            state.current_major
            or state.current_program
            or state.previous_intent
            or state.candidate_majors
        )

        # Stage 0: Conversational fast-track (greetings, identity, capabilities, thanks, goodbye)
        # Bypasses retriever and LLM entirely for instant UI response (<1ms)
        if self.retriever is None and self.llm is None:
            fast = answer_smalltalk(norm_q, has_history=has_history)
            if fast is not None:
                state_dict = state.to_dict()
                fast["state"] = state_dict
                fast["conversation_state"] = state_dict
                fast["latency_ms"] = (time.perf_counter() - t0) * 1000
                return fast

        # Stage 0b: Answer cache for repeated first-turn questions
        use_cache = (
            cache_enabled()
            and not has_history
            and self.retriever is None
            and self.llm is None
            and not bypass_cache
        )
        cache_key = cache_make_key(norm_q) if use_cache else ""
        if use_cache:
            cached = cache_get(cache_key)
            if cached is not None:
                cached["latency_ms"] = (time.perf_counter() - t0) * 1000
                cached["cache_hit"] = True
                return cached

        # Stage 1: Fallback to full grounded RAG pipeline
        resolution = resolve_history_question(norm_q, history, settings_obj=self.settings, llm=self.llm)
        if resolution.clarification:
            return {"answer": resolution.clarification, "status": "clarification", "sources": [],
                    "state": state.to_dict(), "conversation_state": state.to_dict(), "cache_hit": False,
                    "trace": {"history_resolution": {"method": resolution.method, "messages_used": len(history)}},
                    "latency_ms": (time.perf_counter() - t0) * 1000}
        payload = _ask_chatbot(
            resolution.question,
            retriever=self.retriever,
            llm=self.llm,
            settings_obj=self.settings,
            conversation_state=state,
        )
        if history:
            payload.setdefault("trace", {})["history_resolution"] = {
                "method": resolution.method, "messages_used": len(history),
                "original_question": norm_q, "resolved_question": resolution.question,
            }
        payload.setdefault("cache_hit", False)
        payload.setdefault("latency_ms", (time.perf_counter() - t0) * 1000)

        if use_cache and is_cacheable(payload):
            cache_put(cache_key, payload)

        return payload

    def ask_chatbot(
        self,
        question: str,
        *,
        conversation_state: ConversationState | Mapping[str, object] | None = None,
        bypass_cache: bool = False,
        conversation_history: object = None,
    ) -> dict[str, object]:
        """Bí danh tương thích cho các hàm gọi sử dụng tên phương thức của dịch vụ."""
        return self.ask(question, conversation_state=conversation_state, bypass_cache=bypass_cache,
                        conversation_history=conversation_history)


_default_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Khởi tạo trễ dịch vụ mặc định để việc import UI không tốn nhiều tài nguyên."""
    global _default_service
    if _default_service is None:
        _default_service = ChatService()
        try:
            from .warmup import start_background_warmup
            start_background_warmup()
        except Exception:
            pass
    return _default_service


def ask_chatbot(
    question: str,
    *,
    conversation_state: ConversationState | Mapping[str, object] | None = None,
    bypass_cache: bool = False,
    conversation_history: object = None,
) -> dict[str, object]:
    """API công khai được sử dụng bởi giao diện (UI) và các script đơn giản."""
    return get_chat_service().ask(
        question,
        conversation_state=conversation_state,
        bypass_cache=bypass_cache,
        conversation_history=conversation_history,
    )


__all__ = ["ChatService", "ask_chatbot", "get_chat_service", "answer_smalltalk"]
