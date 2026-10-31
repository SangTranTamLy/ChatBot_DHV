"""Fallback Q&A cho các chủ đề DHV chưa có trong corpus ``data/processed``.

Dữ liệu lấy nguyên văn từ workbook của nhóm (``data/supplement``); chỉ mục có
``source_url`` chính thức của DHV được dùng. Chỉ dùng khi
pipeline chính trả ``no_data``/``out_of_scope`` nên không ảnh hưởng câu đã đúng.
File được đọc một lần mỗi tiến trình: sửa JSON xong cần khởi động lại app.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

from src.ingestion.structured_json import is_official_dhv_url

from .conversational import fold_vietnamese
from .query_analysis import analyze_question

SUPPLEMENT_PATH = Path(__file__).resolve().parents[2] / "data" / "supplement" / "hoi_dap_bo_sung_2026.json"
MIN_SCORE = 0.7


def _tokens(text: str) -> frozenset[str]:
    return frozenset(fold_vietnamese(text).split())


@lru_cache(maxsize=1)
def _entries() -> tuple[tuple[tuple[frozenset[str], str | None, dict[str, object]], ...], Counter[str], int | None]:
    if not SUPPLEMENT_PATH.exists():
        return (), Counter(), None
    data = json.loads(SUPPLEMENT_PATH.read_text(encoding="utf-8"))
    # Supplement answers bypass the validator, so only rows with an official DHV source are used.
    entries = tuple(
        (_tokens(entry["question"]), _major(entry["question"]), entry)
        for entry in data.get("entries", [])
        if is_official_dhv_url(str(entry.get("source_url") or ""))
    )
    year = data.get("year")
    return entries, Counter(token for tokens, _, _ in entries for token in tokens), int(year) if year else None


def _major(question: str) -> str | None:
    return analyze_question(question).entities.get("major_name") or None


def lookup_supplement(question: str, current_major: str | None = None) -> dict[str, object] | None:
    """Trả về kết quả ``ok`` nếu câu hỏi khớp đủ gần một mục bổ sung, ngược lại ``None``.

    ``current_major`` là ngành trong conversation state đầu vào (câu hỏi nối tiếp).
    """

    query = _tokens(question)
    if not query:
        return None
    entries, document_frequency, data_year = _entries()
    query_major = _major(question) or current_major

    # IDF weight: names (Khoa Luật, IATAI, ...) outweigh template words (website, là, gì).
    def weight(words: frozenset[str]) -> float:
        return sum(math.log(1 + len(entries) / (document_frequency[word] or 0.5)) for word in words)

    best_score, best = 0.0, None
    for tokens, entry_major, entry in entries:
        # A number the entry never mentions (2027, "Mùa Hè Xanh 27") means a different event.
        if any(any(char.isdigit() for char in word) and word not in tokens for word in query):
            continue
        # An entry about one major (Kế toán) must not answer a question about another (Dược).
        if entry_major and entry_major != query_major:
            continue
        # Shared template words dominate the score; a rare name (``Tâm lý học``,
        # ``quốc tế``) of the entry missing from the query means a different subject.
        if any(document_frequency[word] <= 2 and word not in query for word in tokens):
            continue
        score = weight(query & tokens) / weight(query | tokens)
        if score > best_score:
            best_score, best = score, entry
    if best is None or best_score < MIN_SCORE:
        return None
    return {
        "answer": str(best["answer"]),
        "sources": [{"title": "Nguồn DHV", "url": str(best["source_url"])}],
        "status": "ok",
        "supplement": {"id": best["id"], "score": round(best_score, 3), "year": data_year},
    }


__all__ = ["lookup_supplement"]
