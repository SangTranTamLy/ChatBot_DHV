"""Tiện ích trích xuất và tiền xử lý văn bản bằng chứng phục vụ các bộ định dạng câu trả lời."""

from __future__ import annotations

import re
from typing import Any

from .query_analysis import normalize_question


def _evidence_text_lines(evidence: Any) -> list[str]:
    """Lấy các dòng nội dung đã qua Evidence Selection, không lấy metadata prompt."""
    lines: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line and line not in lines:
                lines.append(line)
    return lines


def _split_source_sentences(raw_text: str) -> list[str]:
    """Join layout-wrapped lines, then split source text into usable sentences."""
    sentences: list[str] = []
    text = re.sub(r"\s+", " ", str(raw_text or "")).strip()
    if not text:
        return sentences
    # Protect common Vietnamese name/title abbreviations from being
    # mistaken for sentence boundaries after line-wrap reconstruction.
    protected = re.sub(
        r"\b(TP|TS|ThS|PGS|GS|ĐHQG)\.",
        lambda match: match.group(1) + "<abbr>",
        text,
    )
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9“])", protected):
        candidate = sentence.replace("<abbr>", ".").strip(" •")
        if candidate and candidate not in sentences:
            sentences.append(candidate)
    return sentences


def _evidence_sentences(evidence: Any) -> list[str]:
    sentences: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        for sentence in _split_source_sentences(str(getattr(chunk, "text", "") or "")):
            if sentence not in sentences:
                sentences.append(sentence)
    return sentences


def _remove_unresolved_url_label(sentence: str) -> str:
    """Avoid emitting a dangling 'at address:' when extraction lost its URL."""
    if re.search(r"(?:https?://|www\.)", sentence, re.IGNORECASE):
        return sentence.strip()
    cleaned = re.sub(
        r"\s+(?:tại\s+)?địa\s+chỉ:\s*và\s*",
        "; sau đó ",
        sentence,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:tại\s+)?địa\s+chỉ:\s*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
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
    except (TypeError, ValueError, AttributeError):
        return 0


def _metadata_chunk_index(metadata: Any, fallback: int) -> int:
    try:
        return int(metadata.get("chunk_index"))
    except (TypeError, ValueError, AttributeError):
        return fallback


def _is_official_dhv_source(value: object) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(str(value or "").strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return bool(
        parsed.scheme.lower() == "https"
        and (hostname == "dhv.edu.vn" or hostname.endswith(".dhv.edu.vn"))
    )
