"""Tiện ích trích xuất và tiền xử lý văn bản bằng chứng phục vụ các bộ định dạng câu trả lời."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .query_analysis import normalize_question


_WHITESPACE_RE = re.compile(r"\s+")
_URL_IN_TEXT_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_UNRESOLVED_ADDRESS_WITH_VA_RE = re.compile(
    r"\s+(?:tại\s+)?địa\s+chỉ:\s*và\s*",
    re.IGNORECASE,
)
_UNRESOLVED_ADDRESS_RE = re.compile(
    r"\s+(?:tại\s+)?địa\s+chỉ:\s*",
    re.IGNORECASE,
)


def _evidence_text_lines(evidence: Any) -> list[str]:
    """Lấy các dòng nội dung đã qua Evidence Selection, không lấy metadata prompt."""
    lines: list[str] = []
    seen: set[str] = set()
    for chunk in getattr(evidence, "chunks", ()) or ():
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = _WHITESPACE_RE.sub(" ", raw_line).strip()
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    return lines


def _split_source_sentences(raw_text: str) -> list[str]:
    """Join layout-wrapped lines, then split source text into usable sentences."""
    sentences: list[str] = []
    text = _WHITESPACE_RE.sub(" ", str(raw_text or "")).strip()
    if not text:
        return sentences
    # Protect common Vietnamese name/title abbreviations from being
    # mistaken for sentence boundaries after line-wrap reconstruction.
    protected = re.sub(
        r"\b(TP|TS|ThS|PGS|GS|ĐHQG)\.",
        lambda match: match.group(1) + "<abbr>",
        text,
    )
    seen: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9“])", protected):
        candidate = sentence.replace("<abbr>", ".").strip(" •")
        if candidate and candidate not in seen:
            seen.add(candidate)
            sentences.append(candidate)
    return sentences


def _evidence_sentences(evidence: Any) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for chunk in getattr(evidence, "chunks", ()) or ():
        for sentence in _split_source_sentences(str(getattr(chunk, "text", "") or "")):
            if sentence not in seen:
                seen.add(sentence)
                sentences.append(sentence)
    return sentences


def _remove_unresolved_url_label(sentence: str) -> str:
    """Avoid emitting a dangling 'at address:' when extraction lost its URL."""
    if _URL_IN_TEXT_RE.search(sentence):
        return sentence.strip()
    cleaned = _UNRESOLVED_ADDRESS_WITH_VA_RE.sub("; sau đó ", sentence)
    cleaned = _UNRESOLVED_ADDRESS_RE.sub(" ", cleaned)
    return cleaned.strip(" ,;\t")


def _bullet_content_lines(evidence: Any) -> list[str]:
    """Gộp bullet bị ngắt dòng trong chunk để formatter giữ được nguyên fact."""
    result: list[str] = []
    for line in _evidence_text_lines(evidence):
        if line.startswith("•"):
            result.append(line.lstrip("• ").strip())
        elif (
            result
            and not line.startswith("#")
            and not line.lower().startswith(("dhv ", "nguồn ", "quỹ ", "các chính sách"))
        ):
            result[-1] = f"{result[-1]} {line}"
    unique: list[str] = []
    seen: set[str] = set()
    for line in result:
        key = normalize_question(line)
        if key and key not in seen:
            seen.add(key)
            unique.append(line)
    return unique


def _metadata_page(metadata: Any) -> int:
    try:
        return int(metadata.get("page") or 0)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return 0


def _metadata_chunk_index(metadata: Any, fallback: int) -> int:
    try:
        return int(metadata.get("chunk_index"))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return fallback


def _is_official_dhv_source(value: object) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        hostname = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.lower() == "https"
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and (hostname == "dhv.edu.vn" or hostname.endswith(".dhv.edu.vn"))
    )
