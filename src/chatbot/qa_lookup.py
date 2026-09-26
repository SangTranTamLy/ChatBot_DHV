"""Deterministic keyword lookup for the imported 2026 Q&A workbook."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"\d+|[a-zA-ZÀ-ỹĐđ]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a", "anh", "ban", "cach", "cho", "co", "cua", "em", "gi", "hay",
        "la", "nao", "nhe", "nhi", "toi", "trong", "tu", "va", "vay", "voi",
    }
)


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return " ".join(folded.lower().replace("đ", "d").split())


def _keywords(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_normalize(value))
        if token not in _STOPWORDS and (len(token) >= 2 or token.isdigit())
    }


@lru_cache(maxsize=4)
def _load_records(path: str) -> tuple[dict[str, Any], ...]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("year") != 2026:
        return ()
    return tuple(
        dict(record)
        for record in document.get("records", [])
        if record.get("record_type") == "qa_pair"
        and str(record.get("question", "")).strip()
        and str(record.get("answer", "")).strip()
    )


def find_keyword_answer(
    question: str,
    *,
    processed_data_dir: str | Path,
    target_year: int = 2026,
) -> dict[str, Any] | None:
    """Return the strongest sufficiently close Q&A record, if one exists."""

    if target_year != 2026 or not question.strip():
        return None
    path = Path(processed_data_dir) / "qa_tuyen_sinh" / "qa_tuyen_sinh_2026.json"
    if not path.is_file():
        return None
    query = _normalize(question)
    query_terms = _keywords(query)
    if not query_terms:
        return None

    best: tuple[float, dict[str, Any]] | None = None
    for record in _load_records(str(path)):
        candidate = _normalize(str(record["question"]))
        if candidate == query:
            return record
        candidate_terms = _keywords(candidate)
        overlap = query_terms & candidate_terms
        if len(overlap) < 2:
            continue
        query_coverage = len(overlap) / len(query_terms)
        candidate_coverage = len(overlap) / len(candidate_terms)
        if query_coverage < 0.5 or candidate_coverage < 0.25:
            continue
        score = query_coverage * 0.7 + candidate_coverage * 0.3
        if best is None or score > best[0]:
            best = (score, record)
    return best[1] if best is not None else None


__all__ = ["find_keyword_answer"]