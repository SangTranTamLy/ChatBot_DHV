"""Fallback Q&A cho các chủ đề DHV chưa có trong corpus ``data/processed``.

Dữ liệu lấy nguyên văn từ workbook của nhóm (``data/supplement``). Chỉ dùng khi
pipeline chính trả ``no_data``/``out_of_scope`` nên không ảnh hưởng câu đã đúng.
File được đọc một lần mỗi tiến trình: sửa JSON xong cần khởi động lại app.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from src.ingestion.structured_json import is_official_dhv_url

from .conversational import fold_vietnamese

SUPPLEMENT_PATH = Path(__file__).resolve().parents[2] / "data" / "supplement" / "hoi_dap_bo_sung_2026.json"
MIN_SCORE = 0.7
UNVERIFIED_NOTE = (
    "\n\nLưu ý: thông tin này do nhóm tổng hợp, chưa có nguồn chính thức kèm theo; "
    "bạn nên xác nhận lại với phòng tuyển sinh DHV."
)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(fold_vietnamese(text).split())


@lru_cache(maxsize=1)
def _entries() -> tuple[tuple[tuple[frozenset[str], dict[str, object]], ...], Counter[str], int | None]:
    if not SUPPLEMENT_PATH.exists():
        return (), Counter(), None
    data = json.loads(SUPPLEMENT_PATH.read_text(encoding="utf-8"))
    # Facts (dates, scores, money) without an official source would bypass the validator.
    entries = tuple(
        (_tokens(entry["question"]), entry)
        for entry in data.get("entries", [])
        if is_official_dhv_url(str(entry.get("source_url") or "")) or not re.search(r"\d", str(entry["answer"]))
    )
    year = data.get("year")
    return entries, Counter(token for tokens, _ in entries for token in tokens), int(year) if year else None


def lookup_supplement(question: str) -> dict[str, object] | None:
    """Trả về kết quả ``ok`` nếu câu hỏi khớp đủ gần một mục bổ sung, ngược lại ``None``."""

    query = _tokens(question)
    if not query:
        return None
    entries, document_frequency, data_year = _entries()

    # IDF weight: names (Khoa Luật, IATAI, ...) outweigh template words (website, là, gì).
    def weight(words: frozenset[str]) -> float:
        return sum(math.log(1 + len(entries) / (document_frequency[word] or 0.5)) for word in words)

    best_score, best = 0.0, None
    for tokens, entry in entries:
        # A year the entry never mentions (2027 vs 2026) means a different event.
        if any(word.isdigit() and len(word) == 4 and word[:2] in {"19", "20"} and word not in tokens for word in query):
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
    url = str(best.get("source_url") or "")
    official = is_official_dhv_url(url)
    return {
        "answer": str(best["answer"]) + ("" if official else UNVERIFIED_NOTE),
        "sources": [{"title": "Nguồn DHV", "url": url}] if official else [],
        "status": "ok",
        "supplement": {"id": best["id"], "score": round(best_score, 3), "year": data_year},
    }


__all__ = ["lookup_supplement"]
