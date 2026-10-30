# -*- coding: utf-8 -*-
"""
DHV Chatbot - Answer cache for repeated questions.

Matches the architecture of VietLabor AI:
- Exact match after normalization (NFC, lowercase, whitespace collapsed, trailing ``?.!…`` removed).
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
from pathlib import Path
from typing import Any, Dict, Optional

from src.config.settings import Settings, settings

MAX_ENTRIES = 256
TTL_SECONDS = 6 * 3600  # 6 hours

_lock = threading.Lock()
_fingerprint_lock = threading.Lock()
_store: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()


def enabled() -> bool:
    return os.environ.get("DHV_ANSWER_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def normalize_question(question: str) -> str:
    """Normalize case and spacing, removing only common trailing question punctuation.

    Internal punctuation and meaningful symbols (for example, ``C++``, ``C#``,
    decimal separators, and method names) are preserved.
    """
    text = unicodedata.normalize("NFC", question or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" ?.!…")


_FINGERPRINT_TTL_SECONDS = 5.0
_fingerprint_cache: tuple[float, tuple[str, str, str], str] | None = None


def _compute_fingerprint(
    settings_obj: Settings = settings,
    *,
    cache_version: str | None = None,
) -> str:
    """Fingerprint the active Chroma store and explicit cache version.

    Application code and processed JSON are loaded at startup or when the index is
    built, so scanning those trees cannot make their in-memory versions refresh.
    The retriever opens the configured Chroma store per query, so the SQLite
    database and write-ahead log metadata signal when cached answers may be stale.
    """

    version = (
        os.environ.get("DHV_CACHE_VERSION", "")
        if cache_version is None
        else cache_version
    )
    chroma_directory = Path(settings_obj.chroma_persist_dir).expanduser().resolve()
    chroma_path = chroma_directory / "chroma.sqlite3"
    parts = [
        version,
        repr(settings_obj),
        str(chroma_directory),
    ]
    for path in (chroma_path, chroma_path.with_name(f"{chroma_path.name}-wal")):
        try:
            stat = path.stat()
        except OSError:
            parts.append(f"{path.name}:missing")
        else:
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def data_fingerprint(settings_obj: Settings = settings) -> str:
    global _fingerprint_cache
    now = time.monotonic()
    cache_version = os.environ.get("DHV_CACHE_VERSION", "")
    chroma_directory = Path(settings_obj.chroma_persist_dir).expanduser().absolute()
    identity = (repr(settings_obj), str(chroma_directory), cache_version)
    cached = _fingerprint_cache
    if (
        cached is not None
        and cached[1] == identity
        and now - cached[0] < _FINGERPRINT_TTL_SECONDS
    ):
        return cached[2]

    # Avoid repeating the file stat when several requests arrive as the cache expires.
    with _fingerprint_lock:
        now = time.monotonic()
        cached = _fingerprint_cache
        if (
            cached is not None
            and cached[1] == identity
            and now - cached[0] < _FINGERPRINT_TTL_SECONDS
        ):
            return cached[2]
        value = _compute_fingerprint(settings_obj, cache_version=cache_version)
        _fingerprint_cache = (time.monotonic(), identity, value)
        return value


def make_key(question: str, *, settings_obj: Settings = settings) -> str:
    material = f"{data_fingerprint(settings_obj)}\n{normalize_question(question)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def is_cacheable(payload: Dict[str, Any]) -> bool:
    return bool(
        payload.get("answer")
        and not payload.get("is_smalltalk")
        and payload.get("status") == "ok"
        and not payload.get("partial")
        and not payload.get("temporal_checked")
    )


def _resolve_key(question_or_key: str, *, settings_obj: Settings = settings) -> str:
    """Accept generated SHA-256 keys as-is; otherwise hash the question."""
    if re.fullmatch(r"[0-9a-f]{64}", question_or_key):
        return question_or_key
    return make_key(question_or_key, settings_obj=settings_obj)


def get(
    question_or_key: str,
    *,
    settings_obj: Settings = settings,
) -> Optional[Dict[str, Any]]:
    """Return a copy by question text or a key previously returned by ``make_key``."""
    if not enabled():
        return None
    key = _resolve_key(question_or_key, settings_obj=settings_obj)
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


def put(
    question_or_key: str,
    payload: Dict[str, Any],
    *,
    settings_obj: Settings = settings,
) -> None:
    """Store an isolated copy by question text or a key returned by ``make_key``."""
    if not enabled() or not is_cacheable(payload):
        return
    key = _resolve_key(question_or_key, settings_obj=settings_obj)
    payload_copy = copy.deepcopy(payload)
    with _lock:
        _store[key] = (time.monotonic(), payload_copy)
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def clear() -> None:
    with _lock:
        _store.clear()


def size() -> int:
    with _lock:
        return len(_store)
