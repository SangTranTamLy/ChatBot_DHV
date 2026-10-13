# -*- coding: utf-8 -*-
"""
DHV Chatbot - Answer cache for repeated questions.

Matches the architecture of VietLabor AI:
- Exact match after normalization (NFC, lowercase, whitespace collapsed, punctuation stripped).
- In-process thread-safe LRU cache with TTL.
- Caches grounded, final answers to deliver sub-millisecond responses for repeated queries.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from typing import Any, Dict, Optional

MAX_ENTRIES = 256
TTL_SECONDS = 6 * 3600  # 6 hours

_lock = threading.Lock()
_store: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()


def enabled() -> bool:
    return os.environ.get("DHV_ANSWER_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFC", question or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" ?.!…")


def make_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def is_cacheable(payload: Dict[str, Any]) -> bool:
    return bool(
        payload.get("answer")
        and not payload.get("is_smalltalk")
        and payload.get("status") == "ok"
    )


def get(question_or_key: str) -> Optional[Dict[str, Any]]:
    if not enabled():
        return None
    key = make_key(question_or_key) if len(question_or_key) != 64 else question_or_key
    now = time.monotonic()
    with _lock:
        item = _store.get(key)
        if item is None:
            return None
        stored_at, payload = item
        if now - stored_at > TTL_SECONDS:
            del _store[key]
            return None
        _store.move_to_end(key)
        return copy.deepcopy(payload)


def put(question_or_key: str, payload: Dict[str, Any]) -> None:
    if not enabled() or not is_cacheable(payload):
        return
    key = make_key(question_or_key) if len(question_or_key) != 64 else question_or_key
    with _lock:
        _store[key] = (time.monotonic(), copy.deepcopy(payload))
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def evict_question(question: str) -> None:
    """Drops a cached answer."""
    with _lock:
        _store.pop(make_key(question), None)


def clear() -> None:
    with _lock:
        _store.clear()


def size() -> int:
    with _lock:
        return len(_store)
