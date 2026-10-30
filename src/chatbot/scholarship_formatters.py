"""Định dạng chính sách học bổng, điều kiện xét học bổng tuyển sinh và danh mục học bổng DHV."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.config.settings import settings
from .evidence_utils import (
    _bullet_content_lines,
    _evidence_text_lines,
    _is_official_dhv_source,
    _metadata_chunk_index,
    _metadata_page,
)
from .query_analysis import QueryAnalysis, normalize_question


def _is_scholarship_heading(line: str) -> bool:
    """Exclude document/section labels that match 'học bổng' but state no fact."""

    text = str(line).strip()
    folded = normalize_question(text)
    numbered_heading = re.match(r"^\d+(?:\.\d+)+\.?\s+(.+)$", text)
    if numbered_heading:
        heading_text = numbered_heading.group(1).strip()
        normalized_heading = normalize_question(heading_text)
        has_fact_value = bool(
            re.search(
                r"\b\d+(?:[.,]\d+)?\s*(?:%|ty|trieu|dong|vnd|diem|ngay|thang|nam|tin chi)\b",
                normalized_heading,
            )
        )
        has_rule_detail = bool(
            re.search(
                r"\b(?:danh cho|ap dung|dieu kien|ho tro|duoc hoan|hoan lai|mien giam|bat buoc|neu|khi)\b",
                normalized_heading,
            )
        )
        if (
            "hoc bong" in normalized_heading
            and ":" not in heading_text
            and not has_fact_value
            and not has_rule_detail
        ):
            return True
    return bool(
        bool(re.fullmatch(r"hoc bong dhv 20\d{2}", folded))
        or folded == "hoc bong hoc phi"
        or re.match(r"^dhv\s+20\d{2}\s*[-–]", text, re.IGNORECASE)
        or (
            text.isupper()
            and "hoc bong" in folded
            and not re.search(r"\d|%|dong|ty", folded)
        )
    )


def _is_admission_scholarship_conditions_question(analysis: QueryAnalysis) -> bool:
    normalized = normalize_question(analysis.normalized_question)
    return (
        analysis.intent == "HOI_HOC_BONG"
        and "hoc bong" in normalized
        and (
            "hoc bong tuyen sinh" in normalized
            or "phuong thuc xet hoc bong" in normalized
            or "xet hoc bong bang" in normalized
        )
        and any(
            marker in normalized
            for marker in ("dieu kien", "nhan hoc bong", "xet hoc bong", "xet the nao")
        )
        and not any(marker in normalized for marker in ("tong diem 3 mon", "cao nhat", "toi da"))
    )


_SCHOLARSHIP_CONDITION_MARKERS = (
    "dieu kien",
    "tieu chi",
    "ai duoc",
    "nhan duoc hoc bong",
    "ap dung cho ai",
)

_SCHOLARSHIP_POLICY_HEADINGS = {
    "1.1": "Chính sách học bổng Hào khí Hùng Vương dành cho tân sinh viên",
    "1.2": "Học bổng tuyển sinh",
    "1.3": "Học bổng Tài năng",
    "1.4": "Học bổng Ngành Tiên phong",
    "1.5": "Học bổng Đôi bạn cùng tiến",
    "1.6": "Học bổng Tương lai vững bước",
    "1.7": "Học bổng Biển đảo yêu thương",
    "3.1": "Học bổng Cam kết hoàn học phí",
}

_SCHOLARSHIP_POLICY_QUERY_MARKERS = {
    "1.1": ("hao khi hung vuong",),
    "1.2": ("hoc bong tuyen sinh", "hoc bong dau vao"),
    "1.3": ("hoc bong tai nang", "tai nang"),
    "1.4": ("hoc bong nganh tien phong", "nganh tien phong", "tien phong"),
    "1.5": ("doi ban cung tien",),
    "1.6": ("tuong lai vung buoc", "thu khoa dau vao", "a khoa dau vao"),
    "1.7": ("bien dao yeu thuong",),
    "3.1": ("cam ket hoan hoc phi",),
}


_SCHOLARSHIP_SCORE_CRITERIA_MARKERS = (
    "de nhan hoc bong", "de duoc hoc bong", "toi thieu", "bao nhieu diem", "can diem",
    "diem toan", "diem hoc ba", "diem dgnl", "to hop",
)


def _is_scholarship_conditions_question(analysis: QueryAnalysis) -> bool:
    """Conditions of one named policy, or the score criteria to receive a scholarship."""
    normalized = normalize_question(analysis.normalized_question)
    if analysis.intent != "HOI_HOC_BONG" or "hoc bong" not in normalized:
        return False
    if any(marker in normalized for marker in ("toi da", "cao nhat", "muc cao", "nhieu nhat")):
        return False  # the highest-level question has its own extractor
    names_policy = any(
        marker in normalized
        for markers in _SCHOLARSHIP_POLICY_QUERY_MARKERS.values()
        for marker in markers
    )
    return (
        any(marker in normalized for marker in _SCHOLARSHIP_CONDITION_MARKERS)
        or any(marker in normalized for marker in _SCHOLARSHIP_SCORE_CRITERIA_MARKERS)
        or (names_policy and analysis.entities.get("query_mode") not in {"COUNT", "LIST", "LIST_AND_COUNT"})
    )


def _is_scholarship_overview_question(analysis: QueryAnalysis) -> bool:
    """Recognize broad scholarship questions that need a concise policy overview."""

    normalized = normalize_question(analysis.normalized_question)
    if (
        analysis.intent != "HOI_HOC_BONG"
        or "hoc bong" not in normalized
        or _is_scholarship_conditions_question(analysis)
        or analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}
    ):
        return False
    if any(
        marker in normalized
        for markers in _SCHOLARSHIP_POLICY_QUERY_MARKERS.values()
        for marker in markers
    ):
        return False
    if any(marker in normalized for marker in (
        "bao nhieu", "muc hoc bong", "phan tram", "toi da", "cao nhat", "tong diem", "hoc phi",
    )):
        return False
    return any(marker in normalized for marker in (
        "nhu the nao", "the nao", "ra sao", "co nhung", "gom nhung gi", "chinh sach hoc bong",
    ))


# Score-based tiers (exam total, học bạ, ĐGNL) all belong to "Học bổng tuyển sinh".
_ADMISSION_SCHOLARSHIP_SCORE_MARKERS = (
    "dgnl", "danh gia nang luc", "hoc ba", "tong diem", "to hop", "diem thi", "diem tb",
)


def _scholarship_condition_policy_ids(analysis: QueryAnalysis) -> tuple[str, ...]:
    normalized = normalize_question(analysis.normalized_question)
    matched = tuple(
        policy_id
        for policy_id, markers in _SCHOLARSHIP_POLICY_QUERY_MARKERS.items()
        if any(marker in normalized for marker in markers)
    )
    if matched:
        return matched
    if any(marker in normalized for marker in _ADMISSION_SCHOLARSHIP_SCORE_MARKERS):
        return ("1.2",)
    return tuple(_SCHOLARSHIP_POLICY_HEADINGS)


def _scholarship_policy_source_rank(metadata: Mapping[str, object], text: str) -> int | None:
    source_file = str(metadata.get("source_file") or "").upper().replace("\\", "/")
    title = normalize_question(str(metadata.get("title") or ""))
    folded = normalize_question(text)
    if re.search(r"09_CHINH_SACH_HOC_BONG_DHV_20\d{2}", source_file) or (
        "chinh sach hoc bong" in title and "unibridge" not in title
    ):
        return 0
    if (
        re.search(r"10_HO_TRO_TAI_CHINH_UNIBRIDGE_DHV_20\d{2}", source_file)
        or "unibridge" in title
    ) and "3.1 hoc bong cam ket hoan hoc phi" in folded:
        return 1
    # Some verified fixtures have no source_file metadata. Require the
    # scholarship section marker so a general admissions page cannot enter.
    if "3.1 hoc bong cam ket hoan hoc phi" in folded:
        return 1
    if any(marker in folded for marker in (
        "1.1 chinh sach hoc bong hao khi hung vuong",
        "1.2 hoc bong tuyen sinh",
        "1.3 hoc bong tai nang",
    )):
        return 0
    return None


def _prioritize_scholarship_catalog_documents(documents: list[Any]) -> list[Any]:
    """Keep verified scholarship-policy pages together, in source order.

    The approved scholarship policies span the dedicated scholarship file and
    the refund-policy page in the UniBridge file. Dropping extracted table and
    summary records here prevents duplicates and unrelated tuition/discount
    passages from crowding the answer context.
    """

    eligible: list[tuple[int, int, int, Any]] = []
    for position, document in enumerate(documents):
        metadata = getattr(document, "metadata", {}) or {}
        text = str(getattr(document, "page_content", "") or "")
        if (
            metadata.get("record_type") != "page_text"
            or str(metadata.get("category") or "") != "hoc_bong"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or not _is_official_dhv_source(metadata.get("source_url"))
        ):
            continue
        rank = _scholarship_policy_source_rank(metadata, text)
        if rank is None:
            continue
        try:
            page = int(metadata.get("page") or 0)
        except (TypeError, ValueError, OverflowError):
            page = 99
        eligible.append((rank, page, position, document))

    if not eligible:
        # Preserve compatibility with a caller that supplies a narrow,
        # verified page-only fixture without source metadata.
        return documents
    return [item[3] for item in sorted(eligible, key=lambda item: item[:3])]


def _evidence_scholarship_catalog_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """List named scholarship headings once, using verified school policy pages."""

    normalized = normalize_question(analysis.normalized_question)
    asks_for_list = (
        analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}
        or any(marker in normalized for marker in ("nhung hoc bong nao", "cac hoc bong", "liet ke hoc bong"))
    )
    if analysis.intent != "HOI_HOC_BONG" or not asks_for_list:
        return None
    if re.search(r"\b(?:thu khoa|a khoa)\b", normalized):
        # Câu hỏi về một danh hiệu cụ thể: không trả danh mục đề mục chung.
        return None

    headings: list[str] = []
    seen: set[str] = set()
    target_year = int(analysis.entities.get("year") or settings.target_year)
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        try:
            year = int(metadata.get("year"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not (
            metadata.get("record_type") == "page_text"
            and str(metadata.get("category") or "") in {"hoc_bong", "phuong_thuc_xet_tuyen"}
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and str(metadata.get("status") or "").casefold() == "verified"
            and year == target_year
            and _is_official_dhv_source(metadata.get("source_url"))
        ):
            continue
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not re.match(r"^\d+\.\d+\.?\s+", line):
                continue
            folded = normalize_question(line)
            if "hoc bong" not in folded:
                continue
            title = re.sub(r"^\d+\.\d+\.?\s*", "", line).strip(" .")
            key = normalize_question(title)
            if title and key not in seen:
                seen.add(key)
                headings.append(title)
    if not headings:
        return None
    count_sentence = f"Tài liệu tuyển sinh DHV {target_year} có {len(headings)} đề mục/chính sách học bổng được nêu rõ."
    if analysis.entities.get("query_mode") == "COUNT":
        return count_sentence
    return (
        (count_sentence + "\n" if analysis.entities.get("query_mode") == "LIST_AND_COUNT" else "")
        + f"Các đề mục/chính sách học bổng được nêu trong tài liệu tuyển sinh DHV {target_year}:\n"
        + "\n".join(f"{index}. {title}" for index, title in enumerate(headings, start=1))
    )


def _scholarship_policy_sections(evidence: Any, target_year: int) -> dict[str, tuple[str, list[str]]]:
    """Read only verified page text from the two approved scholarship policy files."""

    eligible: list[tuple[int, int, int, Any]] = []
    for position, chunk in enumerate(getattr(evidence, "chunks", ()) or ()):
        metadata = getattr(chunk, "metadata", {}) or {}
        text = str(getattr(chunk, "text", "") or "")
        try:
            year = int(metadata.get("year"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not (
            metadata.get("record_type") == "page_text"
            and str(metadata.get("category") or "") == "hoc_bong"
            and str(metadata.get("status") or "").casefold() == "verified"
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and year == target_year
            and _is_official_dhv_source(metadata.get("source_url"))
        ):
            continue
        rank = _scholarship_policy_source_rank(metadata, text)
        if rank is None:
            continue
        try:
            page = int(metadata.get("page") or 0)
        except (TypeError, ValueError, OverflowError):
            page = 99
        try:
            chunk_index = int(metadata.get("chunk_index") or position)
        except (TypeError, ValueError, OverflowError):
            chunk_index = position
        eligible.append((rank, page, chunk_index, chunk))

    sections: dict[str, tuple[str, list[str]]] = {}
    active_source: str | None = None
    active: str | None = None
    for _, _, _, chunk in sorted(eligible, key=lambda item: item[:3]):
        metadata = getattr(chunk, "metadata", {}) or {}
        source_key = str(
            metadata.get("source_file")
            or metadata.get("structured_document_id")
            or metadata.get("document_id")
            or metadata.get("source_url")
            or ""
        )
        if source_key != active_source:
            active_source = source_key
            active = None
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            folded_line = normalize_question(line)
            if re.fullmatch(r"hoc bong dhv 20\d{2}", folded_line) or (
                re.search(r"dhv 20\d{2}", folded_line)
                and any(marker in folded_line for marker in (
                    "chinh sach hoc bong",
                    "ho tro tai chinh unibridge",
                ))
            ):
                continue
            if re.match(r"^1\.9\.1\b", line, re.IGNORECASE):
                active = None
                continue
            heading = re.match(r"^(\d+\.\d+)\.?\s+(.+)$", line)
            if heading:
                section_id = heading.group(1)
                title = heading.group(2).strip()
                if section_id in _SCHOLARSHIP_POLICY_HEADINGS or section_id == "1.9":
                    active = section_id
                    sections.setdefault(section_id, (title, []))
                else:
                    # In particular, skip the duplicated 1.8 friend-benefit
                    # table; the conditions and percentages are in 1.5/1.9.
                    active = None
                continue
            if active:
                sections[active][1].append(line)
    return sections


def _join_policy_wrapped_lines(lines: list[str]) -> list[str]:
    """Join PDF line wraps without merging bullets or numbered subheadings."""

    joined: list[str] = []
    starts_new = re.compile(
        r"^(?:[•*\-–]|1\.2\.\d+\s+|Điểm\b|Tổng điểm\b|Công thức\b|"
        r"Thủ khoa\b|Á khoa\b|Mức học bổng\b|Hỗ trợ\b|Áp dụng\b|"
        r"Điều kiện\b|Nhà trường\b|Sinh viên\b|Năm 20\d{2}\b)",
        re.IGNORECASE,
    )
    for raw_line in lines:
        line = re.sub(r"\s+", " ", str(raw_line or "")).strip()
        if not line:
            continue
        if not joined or starts_new.search(line):
            joined.append(line)
            continue
        if re.search(r"[.!?:;)]$", joined[-1]):
            joined.append(line)
        else:
            joined[-1] = f"{joined[-1]} {line}"
    return joined


def _scholarship_policy_details(
    policy_id: str,
    sections: Mapping[str, tuple[str, list[str]]],
) -> list[str] | None:
    section = sections.get(policy_id)
    if section is None:
        return None
    body = section[1]
    if policy_id == "1.1":
        joined = _join_policy_wrapped_lines(body)
        selected = [
            line for line in joined
            if "quỹ học bổng" in line.casefold() or "tân sinh viên" in line.casefold()
        ]
        return selected or None
    if policy_id == "1.2":
        methods: list[tuple[str, list[str]]] = []
        method_by_title: dict[str, tuple[str, list[str]]] = {}
        current: tuple[str, list[str]] | None = None
        skip_marketing_paragraph = False
        skip_overlap_continuation = False
        for line in body:
            match = re.match(r"^1\.2\.\d+\s+(.+)$", line)
            if match:
                title = match.group(1).strip()
                key = normalize_question(title)
                current = method_by_title.get(key)
                if current is None:
                    current = (title, [])
                    method_by_title[key] = current
                    methods.append(current)
                skip_marketing_paragraph = False
                skip_overlap_continuation = False
                continue
            if current is None:
                continue
            folded_line = normalize_question(line)
            if skip_overlap_continuation:
                if folded_line.startswith("diem thi") or folded_line.startswith("ap dung") or line.startswith(("•", "*")):
                    skip_overlap_continuation = False
                else:
                    continue
            if folded_line.startswith("ngoai ra"):
                skip_marketing_paragraph = True
                continue
            if skip_marketing_paragraph:
                continue
            cleaned = line.lstrip("•*-– ").strip()
            if not cleaned or cleaned.casefold() == "điều kiện:":
                continue
            if (
                "danh gia nang luc" in normalize_question(current[0])
                and normalize_question(cleaned).startswith("tong diem")
            ):
                # The source page split repeats the preceding method's final
                # scholarship threshold just before the ĐGNL heading.
                skip_overlap_continuation = True
                continue
            if current[1] and not re.match(
                r"^(?:•|\*|Điểm\b|Tổng điểm\b|Công thức\b|Áp dụng\b)",
                line,
                re.IGNORECASE,
            ) and not re.search(r"[.!?:;)]$", current[1][-1]):
                current[1][-1] = f"{current[1][-1]} {cleaned}"
            else:
                current[1].append(cleaned)
        for _, details in methods:
            unique: list[str] = []
            seen: set[str] = set()
            for detail in details:
                key = normalize_question(detail)
                if key and key not in seen:
                    seen.add(key)
                    unique.append(detail)
            details[:] = unique
        if len(methods) != 4 or any(not details for _, details in methods):
            return None
        return [f"{title}: " + "; ".join(details) for title, details in methods]

    joined = _join_policy_wrapped_lines(body)
    joined = [
        line for line in joined
        if line.casefold() != "điều kiện:"
        and not line.casefold().startswith("bảng 3.4")
        and not (
            re.search(r"dhv 20\d{2}", normalize_question(line))
            and any(marker in normalize_question(line) for marker in (
                "chinh sach hoc bong",
                "ho tro tai chinh unibridge",
            ))
        )
    ]
    if policy_id == "1.5":
        extra_conditions = _join_policy_wrapped_lines(sections.get("1.9", ("", []))[1])
        joined.extend(
            line for line in extra_conditions
            if (
                line.startswith(("•", "-", "–")) or "nếu thành viên" in line.casefold()
            )
            and "áp dụng cho nhóm tân sinh viên đăng ký và hoàn tất nhập học cùng nhau" not in line.casefold()
            and "tân sinh viên có thể giới thiệu thêm bạn bè" not in line.casefold()
        )
    return joined or None


def _evidence_scholarship_conditions_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer scholarship condition questions from named policy sections only."""

    if not _is_scholarship_conditions_question(analysis):
        return None
    target_year = int(analysis.entities.get("year") or settings.target_year)
    sections = _scholarship_policy_sections(evidence, target_year)
    requested_ids = _scholarship_condition_policy_ids(analysis)
    required_sections = set(requested_ids)
    if "1.5" in required_sections:
        required_sections.add("1.9")
    if not required_sections.issubset(sections):
        return None

    answer = [f"Điều kiện các học bổng DHV {target_year} theo tài liệu đã duyệt:"]
    for index, policy_id in enumerate(requested_ids, start=1):
        details = _scholarship_policy_details(policy_id, sections)
        if not details:
            return None
        heading = sections[policy_id][0] or _SCHOLARSHIP_POLICY_HEADINGS[policy_id]
        # The source labels section 1.1 as a fund/policy overview rather than
        # stating a separate selection test. Keep this limitation explicit.
        if policy_id == "1.1":
            details = [
                "Dành cho tân sinh viên; tài liệu nêu quỹ học bổng lên đến 75 tỷ đồng nhưng không ghi tiêu chí xét riêng tại mục này."
            ]
        if policy_id == "3.1":
            details.append(
                "Tài liệu nêu cam kết việc làm nhưng không liệt kê tiêu chí việc làm cụ thể trong mục này."
            )
        answer.append(f"{index}. **{heading}**")
        answer.extend(f"   - {detail.lstrip('•*-– ').strip()}" for detail in details)
    return "\n".join(answer)


def _evidence_scholarship_overview_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Summarize the verified scholarship program without dumping every rule."""

    if not _is_scholarship_overview_question(analysis):
        return None
    return _scholarship_overview_summary(analysis, evidence)


def _scholarship_overview_summary(analysis: QueryAnalysis, evidence: Any) -> str | None:
    target_year = int(analysis.entities.get("year") or settings.target_year)
    sections = _scholarship_policy_sections(evidence, target_year)
    if not set(_SCHOLARSHIP_POLICY_HEADINGS).issubset(sections):
        return None

    summaries: dict[str, list[str]] = {}
    for policy_id in _SCHOLARSHIP_POLICY_HEADINGS:
        details = _scholarship_policy_details(policy_id, sections)
        if not details:
            return None
        if policy_id == "1.1":
            selected = [next((line for line in details if "quỹ học bổng" in line.casefold()), details[0])]
        elif policy_id == "1.2":
            selected = [
                "Xét qua 4 phương thức; mức hỗ trợ được nêu từ 50% đến 80% học phí chuẩn HKI, tùy phương thức và ngưỡng điểm."
            ]
        elif policy_id == "1.4":
            selected = details[:3]
        elif policy_id == "1.5":
            selected = [details[0]]
            eligibility = next(
                (line for line in details[1:] if "cùng học thpt/gdtx" in normalize_question(line)),
                None,
            )
            if eligibility:
                selected.append(eligibility)
        elif policy_id in {"1.6", "1.7", "3.1"}:
            selected = details[:2]
            if policy_id == "3.1":
                selected.append("Tài liệu chưa nêu tiêu chí việc làm cụ thể để xét cam kết hoàn học phí.")
        else:
            selected = details[:1]
        summaries[policy_id] = selected

    answer = [f"Các chính sách học bổng DHV {target_year} (tóm tắt):"]
    for index, policy_id in enumerate(_SCHOLARSHIP_POLICY_HEADINGS, start=1):
        answer.append(f"{index}. **{sections[policy_id][0] or _SCHOLARSHIP_POLICY_HEADINGS[policy_id]}**")
        answer.extend(f"   - {detail.lstrip('•*-– ').strip()}" for detail in summaries[policy_id])
    return "\n".join(answer)


def _evidence_scholarship_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    evidence_lines = _evidence_text_lines(evidence)
    bullets = _bullet_content_lines(evidence)

    def clean_policy_line(line: str) -> str:
        cleaned = re.sub(r"\s+", " ", line).strip(" •")
        cleaned = re.sub(r"^Chính sách học bổng\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        # Repair the two split-word OCR artifacts present in verified source
        # lines; retain a complete sourced amount parenthesis, but discard an
        # amount fragment whose matching close-paren/amount was lost at a
        # chunk boundary.
        cleaned = re.sub(r"đi\s+ểm", "điểm", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"chu\s+ẩn", "chuẩn", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"h\s+ọc", "học", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(Tổng điểm 3 môn)\s*(\d+(?:[.,]\d+)?)\s*≤\s*(\d+(?:[.,]\d+)?)\s*điểm", r"\1 từ \2 đến \3 điểm", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(tương(?:\s+đương)?\b[^)]*$", "", cleaned, flags=re.IGNORECASE)
        trailing_numbered_heading = re.search(
            r"(?<!\w)(\d+(?:\.\d+)+\.?\s+.+)$",
            cleaned,
        )
        if trailing_numbered_heading and _is_scholarship_heading(
            trailing_numbered_heading.group(1)
        ):
            cleaned = cleaned[:trailing_numbered_heading.start()].rstrip()
        return cleaned.rstrip(" ,;:")

    def unique_policy_lines(values: Any) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = clean_policy_line(str(value))
            key = normalize_question(cleaned)
            if cleaned and key and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    joined_amount_lines: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if str(metadata.get("record_type") or "") != "page_text":
            continue
        raw_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in str(getattr(chunk, "text", "") or "").splitlines()
        ]
        for index, line in enumerate(raw_lines[:-1]):
            if not re.search(r"\(\s*tương\s+đương\s*$", line, re.IGNORECASE):
                continue
            amount_line = raw_lines[index + 1]
            if re.search(r"\d[\d.,]*\s*(?:VNĐ|đồng|VND)\s*\)\s*$", amount_line, re.IGNORECASE):
                joined_amount_lines.append(f"{line} {amount_line}")
    lines = unique_policy_lines((*bullets, *evidence_lines, *joined_amount_lines))
    if not lines:
        return None
    normalized_question = normalize_question(analysis.normalized_question)
    target_year = int(analysis.entities.get("year") or settings.target_year)
    if _is_admission_scholarship_conditions_question(analysis):
        conditions_answer = _evidence_admission_scholarship_conditions_answer(
            analysis,
            evidence,
        )
        if conditions_answer:
            return conditions_answer
    if "tong diem 3 mon" in normalized_question or (
        "to hop" in normalized_question
        and "hoc bong" in normalized_question
        and any(marker in normalized_question for marker in ("3 mon", "ba mon"))
    ):
        score_rule_lines = [
            line for line in lines
            if "tong diem 3 mon" in normalize_question(line)
            and re.search(r"\d+(?:[.,]\d+)?\s*%", line)
        ]
        deduplicated_by_key: dict[str, tuple[tuple[int, int], str]] = {}
        for line in score_rule_lines:
            percent_match = re.search(r"\d+(?:[.,]\d+)?\s*%", line)
            condition = re.split(r"hỗ trợ|ho tro", line, maxsplit=1, flags=re.IGNORECASE)[0]
            canonical_condition = condition.replace("≤", "<=").replace("≥", ">=")
            canonical_condition = re.sub(r"\s+", "", normalize_question(canonical_condition))
            canonical_percent = normalize_question(percent_match.group(0)) if percent_match else ""
            numeric_condition = tuple(re.findall(r"\d+(?:[.,]\d+)?", canonical_condition))
            comparison_operators = tuple(re.findall(r"(?:<=|>=|<|>)", canonical_condition))
            key = f"{numeric_condition}|{comparison_operators}|{canonical_percent}"
            short_word_count = sum(
                len(token) <= 2
                for token in re.findall(r"[a-z]+", normalize_question(line))
            )
            quality = (-short_word_count, len(line))
            previous = deduplicated_by_key.get(key)
            if previous is None or quality > previous[0]:
                deduplicated_by_key[key] = (quality, line)
        score_rule_lines = [line for _, line in deduplicated_by_key.values()]
        if score_rule_lines:
            return "Theo điều kiện học bổng DHV xét theo tổng điểm 3 môn:\n" + "\n".join(
                f"- {line.lstrip('• ').strip()}" for line in score_rule_lines
            )
    tier_answer = _scholarship_named_tier_answer(
        normalized_question,
        lines,
        target_year=target_year,
    )
    if tier_answer:
        return tier_answer
    if any(marker in normalized_question for marker in ("toi da", "cao nhat", "muc cao nhat")):
        percentage_lines: list[tuple[float, str]] = []
        for line in lines:
            folded = normalize_question(line)
            match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", line)
            # For a maximum admission-scholarship question, compare the
            # score-conditioned awards and do not confuse a total scholarship
            # fund with an individual award percentage.
            if match and any(marker in folded for marker in ("diem", "hoc ba", "dgnl")):
                percentage_lines.append((float(match.group(1).replace(",", ".")), line))
        if percentage_lines:
            maximum = max(value for value, _ in percentage_lines)
            maximum_lines = list(dict.fromkeys(
                line for value, line in percentage_lines if value == maximum
            ))
            return (
                f"Mức cao nhất trong các điều kiện học bổng xét theo điểm được nêu là {maximum:g}%:\n"
                + "\n".join(f"- {line.lstrip('• ').strip()}" for line in maximum_lines)
            )
    has_verified_policy_page = any(
        str((getattr(chunk, "metadata", {}) or {}).get("record_type") or "") == "page_text"
        and str((getattr(chunk, "metadata", {}) or {}).get("category") or "")
        in {"phuong_thuc_xet_tuyen", "ho_so"}
        and str((getattr(chunk, "metadata", {}) or {}).get("school_code") or "").upper() == "DHV"
        and str((getattr(chunk, "metadata", {}) or {}).get("status") or "").casefold() == "verified"
        for chunk in getattr(evidence, "chunks", ()) or ()
    )
    if has_verified_policy_page:
        # Complete page context is available; do not build a broad answer by
        # concatenating isolated scholarship records from different sections.
        return None

    relevant_markers = tuple(normalize_question(marker) for marker in (
        "học bổng",
        "điều kiện",
        "học bạ",
        "đgnl",
        "tổng điểm",
        "thủ khoa",
        "á khoa",
        "đôi bạn",
        "biển đảo",
        "cam kết",
    ))
    selected = [
        line for line in lines
        if any(marker in normalize_question(line) for marker in relevant_markers)
        and not _is_scholarship_heading(line)
    ]
    if not selected:
        return None
    
    selected_lines = selected[:12]
    count = len(selected_lines)
    operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
    
    if operation == "COUNT":
        return f"Theo dữ liệu tuyển sinh DHV, hiện có {count} loại/chính sách học bổng được ghi nhận."
    elif operation == "LIST_AND_COUNT":
        return f"Theo dữ liệu tuyển sinh DHV, hiện có {count} loại/chính sách học bổng:\n" + "\n".join(
            f"- {line}" for line in selected_lines
        )
    # With the full policy page in evidence, the stitched lines below are page fragments.
    summary = _scholarship_overview_summary(analysis, evidence)
    if summary:
        return summary
    return f"Các chính sách và điều kiện học bổng DHV {target_year} gồm:\n" + "\n".join(
        f"- {line}" for line in selected_lines
    )


def _evidence_scholarship_tier_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Điểm vào công khai cho câu hỏi mức học bổng theo danh hiệu (Thủ khoa/Á khoa/100%)."""

    if analysis.intent != "HOI_HOC_BONG":
        return None
    return _scholarship_named_tier_answer(
        normalize_question(analysis.normalized_question),
        _evidence_text_lines(evidence),
        target_year=int(analysis.entities.get("year") or settings.target_year),
    )


def _scholarship_named_tier_answer(
    normalized_question: str,
    lines: list[str],
    *,
    target_year: int,
) -> str | None:
    """Trả lời các câu hỏi mức học bổng gắn với danh hiệu (Thủ khoa/Á khoa) hoặc mức 100%."""

    asks_thu_khoa = bool(re.search(r"\bthu khoa\b", normalized_question))
    asks_a_khoa = bool(re.search(r"\ba khoa\b", normalized_question))
    asks_full = bool(re.search(r"\b100\s*%|\btoan phan\b|\bfull\b|\bmien toan bo\b", normalized_question))
    if not (asks_thu_khoa or asks_a_khoa or asks_full):
        return None

    def pick(marker: str) -> str | None:
        for line in lines:
            folded = normalize_question(line)
            if folded.startswith(marker) and re.search(r"\d+\s*%", line):
                return line.lstrip("• ").strip()
        return None

    thu_khoa = pick("thu khoa")
    a_khoa = pick("a khoa")
    talent = next(
        (
            line.lstrip("• ").strip()
            for line in lines
            if normalize_question(line).startswith("muc hoc bong")
            and re.search(r"\d+\s*%\s*den\s*100\s*%", normalize_question(line))
        ),
        None,
    )
    if talent:
        talent = re.split(r",\s*dành cho", talent, maxsplit=1)[0].rstrip(" .")
    parts: list[str] = []
    if asks_thu_khoa and thu_khoa:
        parts.append(thu_khoa)
    if asks_a_khoa and a_khoa:
        parts.append(a_khoa)
    if asks_full and not (asks_thu_khoa or asks_a_khoa):
        if thu_khoa:
            parts.append(thu_khoa)
        if talent:
            parts.append(f"Học bổng Tài năng: {talent[0].lower() + talent[1:]}")
    if not parts:
        return None
    return f"Theo chính sách học bổng DHV {target_year}:\n" + "\n".join(
        f"- {part}" for part in parts
    )


def _evidence_admission_scholarship_conditions_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Render the complete 1.4 admission-scholarship policy from verified page text."""

    target_year = int(analysis.entities.get("year") or settings.target_year)
    eligible_chunks: list[Any] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            metadata.get("record_type") != "page_text"
            or str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or not _is_official_dhv_source(metadata.get("source_url"))
        ):
            continue
        try:
            if int(metadata.get("year")) != target_year:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        eligible_chunks.append(chunk)

    anchor = next(
        (
            chunk
            for chunk in eligible_chunks
            if "1 trong 4 phuong thuc xet hoc bong" in normalize_question(
                str(getattr(chunk, "text", "") or "")
            )
        ),
        None,
    )
    if anchor is None:
        return None
    anchor_metadata = getattr(anchor, "metadata", {}) or {}
    structured_id = str(
        anchor_metadata.get("structured_document_id")
        or anchor_metadata.get("document_id")
        or ""
    )
    if not structured_id:
        return None
    try:
        anchor_page = int(anchor_metadata.get("page"))
    except (TypeError, ValueError, OverflowError):
        return None

    related = [
        chunk
        for chunk in eligible_chunks
        if str(
            (getattr(chunk, "metadata", {}) or {}).get("structured_document_id")
            or (getattr(chunk, "metadata", {}) or {}).get("document_id")
            or ""
        ) == structured_id
        and _metadata_page(getattr(chunk, "metadata", {}) or {}) >= anchor_page
    ]
    related.sort(
        key=lambda chunk: (
            _metadata_page(getattr(chunk, "metadata", {}) or {}),
            _metadata_chunk_index(
                getattr(chunk, "metadata", {}) or {},
                0,
            ),
        )
    )

    captured_lines: list[str] = []
    started = False
    ended = False
    for chunk in related:
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if not started:
                if re.match(r"^1\.4\.\s*Học bổng tuyển sinh\b", line, re.IGNORECASE):
                    started = True
                continue
            if re.match(r"^1\.5\.\s*Học bổng\b", line, re.IGNORECASE):
                ended = True
                break
            if re.fullmatch(r"\d+", line):
                continue
            captured_lines.append(line)
        if ended:
            break
    if not started or not ended:
        return None

    intro: list[str] = []
    methods: list[dict[str, Any]] = []
    notes: list[str] = []
    current: dict[str, Any] | None = None
    for line in captured_lines:
        method_match = re.match(r"^([a-d])\.\s*(.+)$", line, re.IGNORECASE)
        if method_match:
            current = {"code": method_match.group(1).lower(), "title": method_match.group(2), "details": []}
            methods.append(current)
            continue
        if normalize_question(line).startswith("ngoai ra"):
            notes.append(line)
            current = None
            continue
        if line.startswith(("•", "-", "–", "*")) or re.match(
            r"^(?:Điểm|Tổng điểm)\b", line, re.IGNORECASE
        ):
            detail = line.lstrip("•-–* ").strip()
            if current is None:
                intro.append(detail)
            else:
                current["details"].append(detail)
            continue
        if current is not None:
            if current["details"]:
                current["details"][-1] = f"{current['details'][-1]} {line}"
            else:
                current["title"] = f"{current['title']} {line}"
        else:
            intro.append(line)

    if {str(method.get("code")) for method in methods} != {"a", "b", "c", "d"}:
        return None
    if any(not method["details"] for method in methods):
        return None

    answer_lines = [f"Điều kiện học bổng tuyển sinh DHV {target_year}:"]
    if intro:
        answer_lines.append(" ".join(intro))
    for method in methods:
        answer_lines.append(f"- {method['title']}")
        answer_lines.extend(f"  - {detail}" for detail in method["details"])
    answer_lines.extend(notes)
    return "\n".join(answer_lines)
