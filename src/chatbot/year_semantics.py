"""Role-aware extraction of a question's requested year.

Natural-language questions may mention a graduation/document year as well as
the year for which admission information is requested. Admission cues take
precedence; a year used only to describe a qualification is not treated as a
request to query that historical year's corpus.
"""

from __future__ import annotations

import re
import unicodedata


_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_ADMISSION_YEAR_RE = re.compile(
    r"\b(?:"
    r"(?:xet\s+tuyen|tuyen\s+sinh|nam\s+tuyen\s+sinh|dot(?:\s+tuyen\s+sinh)?)"
    r"\s+(?:nam\s+)?"
    r"|(?:tham\s+gia\s+xet\s+tuyen|dang\s+ky|nop\s+ho\s+so|nhan\s+ho\s+so)"
    r"\b[^.!?;\n]{0,48}?\b"
    r")(20\d{2})\b"
)
_GRADUATION_CONTEXT_RE = re.compile(
    r"\b(?:tot\s+nghiep|bang\s+tot\s+nghiep|da\s+tot\s+nghiep)"
    r"[^.!?;\n]{0,24}?\b(20\d{2})\b"
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def extract_requested_year(question: str, *, default_year: int | None = None) -> int | None:
    """Return the admission/query year, ignoring years that only qualify a user.

    The last year attached to an explicit admission cue wins when a question
    compares multiple years. If no admission year is stated, other document or
    event years remain eligible; graduation-only years fall back to
    ``default_year`` (or ``None`` for callers that use their own default).
    """

    normalized = _normalize(question)
    admission_years = [int(match.group(1)) for match in _ADMISSION_YEAR_RE.finditer(normalized)]
    if admission_years:
        return admission_years[-1]

    graduation_spans = [match.span(1) for match in _GRADUATION_CONTEXT_RE.finditer(normalized)]
    candidates = [
        int(match.group(1))
        for match in _YEAR_RE.finditer(normalized)
        if not any(start <= match.start(1) < end for start, end in graduation_spans)
    ]
    if candidates:
        return candidates[0]
    return default_year


__all__ = ["extract_requested_year"]
