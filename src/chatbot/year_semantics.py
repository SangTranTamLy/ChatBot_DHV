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
# Past only: "học phí năm sau có tăng không" is still answered from this year's commitment.
_RELATIVE_YEAR_RE = re.compile(r"(?<!\d )\bnam (?:ngoai|truoc|roi|qua)\b")
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

    relative = _RELATIVE_YEAR_RE.search(normalized)
    if relative and not _YEAR_RE.search(normalized):
        from src.config.settings import settings

        # Relative to the admission year being served, not to a year inherited from the last turn.
        return settings.target_year - 1

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


_WHEN_RE = re.compile(r"\b(?:khi nao|bao gio|ngay nao|ngay may|luc nao|thoi gian|thoi han|han chot|han|truoc ngay|den ngay|may gio)\b")
# (question pattern, milestone bullet marker) from the official round-1 schedule.
_MILESTONE_TOPICS = (
    (r"\bxac nhan nhap hoc\b", "xac nhan nhap hoc"),
    # Not "công bố điểm chuẩn": 13.8 is the national notice deadline, not DHV's score release date.
    (r"^(?!.*\bdiem\b).*\b(?:thong bao|cong bo|biet|co)\b.{0,20}\btrung tuyen\b", "thong bao thi sinh trung tuyen"),
    (r"\ble phi\b", "nop le phi"),
    (r"\bnguyen vong\b", "dieu chinh nguyen vong"),
    (r"\bxet tuyen thang\b|\buu tien xet tuyen\b", "xet tuyen thang"),
    (r"\bra soat\b", "ra soat ket qua hoc tap"),
    (r"\b(?:nop ho so|dang ky xet tuyen|dang ky du tuyen)\b", "dieu chinh nguyen vong"),
)
# DHV's own plan states a later registration deadline than the national wish window; give both.
_DHV_REGISTRATION_RE = re.compile(r"Thời gian đăng ký xét tuyển:\s*([^\n.]+)")


def schedule_milestone_answer(question: str, *, target_year: int) -> dict[str, object] | None:
    """Answer "khi nào …" from the verified round-1 schedule bullets, whatever intent the router picked."""

    text = _normalize(question)
    if (
        not _WHEN_RE.search(text)
        # "nộp hồ sơ lúc nào trong ngày" asks reception hours, not a schedule milestone.
        or re.search(r"\b(?:bo sung|dot 2|dot hai|nhap hoc truc tiep|trong ngay|gio nao|may gio|thu bay|chu nhat)\b", text)
        or extract_requested_year(text, default_year=target_year) != target_year
    ):
        return None
    if re.search(r"\b(?:tuu truong|khai giang|bat dau hoc|vao hoc)\b", text):
        return _school_start_answer(text, target_year)
    marker = next((marker for pattern, marker in _MILESTONE_TOPICS if re.search(pattern, text)), None)
    if marker is None or (marker == "dieu chinh nguyen vong" and "nhap hoc" in text):
        return None

    milestone = _verified_page_text("lich_tuyen_sinh", target_year)
    if milestone is None:
        return None
    body, source = milestone
    line = next(
        (item for bullet in body.split("•")[1:] if marker in _normalize(item := re.sub(r"\s+", " ", bullet).strip())),
        None,
    )
    if line is None:
        return None
    answer = f"Theo lịch tuyển sinh đợt 1 DHV {target_year}: {line}."
    sources = [source]
    plan = _verified_page_text("phuong_thuc_xet_tuyen", target_year)
    registration = plan and re.search(r"\b(?:nop ho so|dang ky xet tuyen|dang ky du tuyen)\b", text) and _DHV_REGISTRATION_RE.search(plan[0])
    if registration:
        answer = (
            f"Theo phương án tuyển sinh DHV {target_year}, thời gian đăng ký xét tuyển: {registration.group(1).strip()}.\n"
            f"Trên lịch chung đợt 1: {line}."
        )
        sources.append(plan[1])
    return {"answer": answer, "sources": sources, "status": "ok"}


def _school_start_answer(text: str, target_year: int) -> dict[str, object] | None:
    found = _verified_page_text("ho_so", target_year)
    sentence = found and re.search(r"[^.\n]*ngày tựu trường[^.\n]*\d{4}\.?", found[0])
    if not sentence:
        return None
    answer = sentence.group(0).strip().rstrip(".") + "."
    if "tuu truong" not in text:
        # The source dates only the first-day gathering; do not present it as the opening ceremony.
        answer += " Tài liệu tuyển sinh chưa nêu riêng ngày khai giảng hay ngày bắt đầu học."
    return {"answer": answer, "sources": [found[1]], "status": "ok"}


def _verified_page_text(category: str, target_year: int) -> tuple[str, dict[str, str]] | None:
    from pathlib import Path

    from src.config.settings import settings
    from src.ingestion.structured_json import is_official_dhv_url, load_structured_json

    bodies: list[str] = []
    first_source: dict[str, str] | None = None
    for path in sorted((Path(settings.processed_data_dir) / category).glob("*.json")):
        try:
            document = load_structured_json(path)
        except (OSError, ValueError):
            continue
        source = document.get("source") or {}
        if (
            document.get("year") == target_year
            and source.get("status") == "verified"
            and str(source.get("school_code") or "").upper() == "DHV"
            and is_official_dhv_url(source.get("source_url"))
        ):
            bodies.append(unicodedata.normalize("NFC", "\n".join(str(page.get("text") or "") for page in document.get("pages") or ())))
            first_source = first_source or {"title": str(document.get("title") or "Tuyển sinh DHV"), "url": str(source["source_url"])}
    # shortcut: cites the first file of the category; split per file if a category ever mixes sources.
    return ("\n".join(bodies), first_source) if first_source else None


__all__ = ["extract_requested_year", "current_admission_window_answer", "schedule_milestone_answer"]
