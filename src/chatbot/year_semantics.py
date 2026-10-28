"""Role-aware extraction of a question's requested year.

Natural-language questions may mention a graduation/document year as well as
the year for which admission information is requested. Admission cues take
precedence; a year used only to describe a qualification is not treated as a
request to query that historical year's corpus.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone


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


def current_admission_window_answer(question: str, evidence: object, *, today: date | None = None) -> dict[str, object] | None:
    """Answer current availability only from a dated, matching admission window."""
    text = _normalize(question)
    asks_about_now = any(
        term in text
        for term in (
            "bay gio", "hien tai", "hien nay", "hom nay", "con nhan", "con nop",
            "con dang ky", "con kip", "het han chua", "qua han chua", "dang mo",
        )
    )
    # Accent normalization makes both ``lúc này`` (right now) and ``lúc nãy``
    # (a moment ago) become ``luc nay``. A reference to something just said is
    # not a request to check whether an admission window is currently open.
    just_mentioned_reference = bool(re.search(r"\bvua\b.{0,40}\bluc nay\b", text))
    if "luc nay" in text and not just_mentioned_reference:
        asks_about_now = True
    if not asks_about_now:
        return None
    if not any(term in text for term in ("ho so", "nhap hoc", "xet tuyen", "dang ky", "xac nhan")):
        return None
    supplementary = any(term in text for term in ("bo sung", "dot bo sung"))
    confirmation = "xac nhan" in text
    marker = (
        r"thoi gian nhan ho so|han (?:nhan|nop) ho so" if supplementary else
        r"thoi gian xac nhan nhap hoc" if confirmation else
        r"tiep nhan nhap hoc|thoi gian nhan ho so|thoi gian dang ky xet tuyen|han (?:nhan|nop) ho so"
    )
    windows: set[tuple[date | None, date]] = set()
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        category = str(metadata.get("category") or "")
        if supplementary and category != "xet_tuyen_bo_sung":
            continue
        if not supplementary and category not in {"ho_so", "nhap_hoc", "lich_tuyen_sinh", "phuong_thuc_xet_tuyen", "diem_trung_tuyen"}:
            continue
        content = _normalize(str(getattr(chunk, "text", "")))
        # Keep a sentence boundary so scholarship dates cannot become intake dates.
        for match in re.finditer(r"(?:" + marker + r")[^.!?\n]{0,240}", content):
            segment = match.group()
            if not re.search(r"\bden\b|\bket thuc\b|\bhan\b", segment):
                continue
            dates = []
            for day, month, year in re.findall(r"\b(\d{1,2})(?:/|-|\s+thang\s+)(\d{1,2})(?:/|-|\s+nam\s+)(20\d{2})\b", segment):
                try:
                    dates.append(date(int(year), int(month), int(day)))
                except ValueError:
                    dates = []
                    break
            if dates:
                start = dates[0] if len(dates) > 1 and "tu " in segment else None
                if start is None or start <= dates[-1]:
                    windows.add((start, dates[-1]))
    if len(windows) != 1:
        return {
            "answer": "Mình chưa xác nhận được hiện còn nhận hồ sơ hay không. Bạn nên hỏi bộ phận tuyển sinh DHV trước khi đăng ký nhé.",
            "status": "no_data",
            "sources": [],
            "temporal_checked": True,
        }

    sources = [dict(source) for source in getattr(evidence, "sources", ()) or ()]
    start, end = next(iter(windows))
    current = today or datetime.now(timezone(timedelta(hours=7))).date()
    label = "Đợt xét tuyển bổ sung này" if supplementary else "Đợt xác nhận nhập học này" if confirmation else "Đợt nhận hồ sơ này"
    if current > end:
        answer = f"{label} đã hết hạn ngày {end:%d/%m/%Y}. Mình chưa có thông tin về đợt mới đang mở."
    elif current == end:
        answer = f"Hôm nay là ngày cuối của đợt này ({end:%d/%m/%Y}). Bạn cần kiểm tra giờ chốt và việc tiếp nhận trước khi nộp nhé."
    elif start and current < start:
        answer = f"{label} bắt đầu từ {start:%d/%m/%Y}, nên hiện chưa đến thời gian đăng ký."
    elif start:
        answer = f"Về thời hạn, {label[0].lower() + label[1:]} diễn ra từ {start:%d/%m/%Y} đến {end:%d/%m/%Y}. Hôm nay vẫn trong khoảng thời gian này."
    else:
        answer = f"Hạn của đợt này là {end:%d/%m/%Y}. Mình chưa xác nhận được đợt này hiện còn nhận hồ sơ hay không."
    return {"answer": answer, "status": "ok", "sources": sources, "temporal_checked": True}


__all__ = ["extract_requested_year", "current_admission_window_answer"]
