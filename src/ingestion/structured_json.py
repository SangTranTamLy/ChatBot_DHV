"""Structured JSON data layer for the DHV PDF ingestion pipeline.

This module owns the representation between extracted PDF text and the vector
store.  It deliberately contains deterministic, category-specific parsers:
the source PDF remains authoritative and an unrecognised value is kept as raw
text (or ``None``) instead of being guessed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from langchain_core.documents import Document


OFFICIAL_DHV_HOST = "dhv.edu.vn"
SCHOOL_NAME = "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh"
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_MAJOR_CODE_RE = re.compile(r"^\d{7}$")
_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_VND_RE = re.compile(r"(?P<number>\d{1,3}(?:\.\d{3})+|\d+)\s*đồng", re.IGNORECASE)
_DATE_LINE_RE = re.compile(
    r"^(?:Ngày cập nhật nguồn|Nguồn cập nhật|Ngày thu thập/kiểm tra):\s*(?P<date>.+?)\s*$",
    re.IGNORECASE,
)
_COLLECTED_AT_RE = re.compile(
    r"(?:Ngày kiểm tra|Ngày thu thập/kiểm tra|Kiểm tra):\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


class StructuredJSONValidationError(ValueError):
    """Raised when a generated structured document violates its contract."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        message = "; ".join(str(error.get("message", error)) for error in errors)
        super().__init__(message or "invalid structured JSON document")


def is_official_dhv_url(value: object) -> bool:
    """Return whether *value* is an HTTPS URL on DHV or an official subdomain."""

    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    return bool(
        parsed.scheme.lower() == "https"
        and host
        and not parsed.username
        and not parsed.password
        and (host == OFFICIAL_DHV_HOST or host.endswith(f".{OFFICIAL_DHV_HOST}"))
    )


def _clean_text(value: str) -> str:
    """Normalise extraction artefacts without changing factual tokens."""

    value = value.replace("\u00a0", " ").replace("\u00ad", "")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "-", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _to_int(value: str) -> int | None:
    value = value.strip().replace(".", "").replace(",", "")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_amount(value: str) -> int | None:
    match = _VND_RE.search(value)
    if not match:
        return None
    return _to_int(match.group("number"))


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _value_or_raw(value: str) -> int | float | str:
    if value.strip() == "-":
        return "-"
    if "," in value:
        # Scores in the source use a decimal comma (for example ``20,0``).
        try:
            return float(value.replace(".", "").replace(",", "."))
        except ValueError:
            pass
    number = _to_int(value)
    return number if number is not None else value.strip()


def _source_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_RE.finditer(text):
        value = match.group(0).rstrip(".,);]")
        if value not in urls:
            urls.append(value)
    return urls


def _date_metadata(text: str) -> tuple[str, str]:
    source_date = ""
    for line in _nonempty_lines(text):
        match = _DATE_LINE_RE.match(line)
        if match:
            source_date = match.group("date").split("|", 1)[0].strip()
            break
    collected_at = ""
    match = _COLLECTED_AT_RE.search(text)
    if match:
        day, month, year = match.group("date").split("/")
        collected_at = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return source_date, collected_at


def _title_from_text(text: str) -> str:
    first = next(iter(_nonempty_lines(text)), "")
    match = re.match(r"^DHV(?:\s+2026)?\s*-\s*(?P<title>.+?)\s*$", first)
    return match.group("title").strip() if match else first


def _page_for_line(lines: list[tuple[int, str]], index: int) -> int:
    return lines[index][0] if 0 <= index < len(lines) else 1


def _all_lines(pages: list[dict[str, Any]]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for page in pages:
        page_number = int(page["page"])
        result.extend((page_number, line.strip()) for line in str(page.get("text", "")).splitlines() if line.strip())
    return result


def parse_major_catalog(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse major rows while keeping programs as children of their major."""

    lines = _all_lines(pages)
    records: list[dict[str, Any]] = []
    for index, (_, line) in enumerate(lines):
        if not _MAJOR_CODE_RE.fullmatch(line):
            continue
        major_name = ""
        for previous_index in range(index - 1, -1, -1):
            candidate = lines[previous_index][1]
            if candidate and not _MAJOR_CODE_RE.fullmatch(candidate):
                major_name = candidate
                break
        if not major_name:
            continue

        payload: list[str] = []
        values: list[str] | None = None
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor][1]
            if (
                cursor + 2 < len(lines)
                and all(_NUMBER_RE.fullmatch(lines[pos][1]) or lines[pos][1] == "-" for pos in range(cursor, cursor + 3))
            ):
                values = [lines[pos][1] for pos in range(cursor, cursor + 3)]
                break
            # A new code before thresholds means this row is malformed.  Keep
            # the row out of structured records rather than borrowing values.
            if _MAJOR_CODE_RE.fullmatch(candidate):
                values = None
                break
            payload.append(candidate)
            cursor += 1
        if values is None:
            continue

        program_text = " ".join(payload).strip()
        programs: list[dict[str, Any]] = []
        if program_text and program_text not in {"-", "—"}:
            for program_name in (item.strip() for item in program_text.split(";")):
                if program_name:
                    programs.append(
                        {
                            "program_name": program_name,
                            "parent_major": major_name,
                            "parent_major_code": line,
                            "page": _page_for_line(lines, index),
                        }
                    )
        records.append(
            {
                "record_type": "major",
                "record_id": f"major_{len(records) + 1:03d}",
                "major_name": major_name,
                "major_code": line,
                "programs": programs,
                "program_count": len(programs),
                "threshold_type": "application_threshold",
                "thresholds": {
                    "thpt": _value_or_raw(values[0]),
                    "hoc_ba": _value_or_raw(values[1]),
                    "dgnl": _value_or_raw(values[2]),
                },
                "thresholds_raw": {
                    "thpt": values[0],
                    "hoc_ba": values[1],
                    "dgnl": values[2],
                },
                "page": _page_for_line(lines, index),
            }
        )
    if records:
        records.append(
            {
                "record_type": "major_catalog_summary",
                "record_id": "major_catalog_summary",
                "major_count": len(records),
                "majors": [
                    {"major_name": record["major_name"], "major_code": record["major_code"]}
                    for record in records
                ],
                "major_rows": [
                    {
                        "major_name": record["major_name"],
                        "major_code": record["major_code"],
                        "thresholds_raw": record["thresholds_raw"],
                    }
                    for record in records
                ],
                # Keep the summary tied to the page carrying the parsed rows;
                # do not invent a page number for synthetic test documents.
                "page": records[-1]["page"],
            }
        )
    return records


def parse_application_thresholds(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    patterns = (
        ("thpt", "Xét kết quả kỳ thi tốt nghiệp THPT", r"từ\s+(\d+(?:[.,]\d+)?)\s*điểm"),
        ("hoc_ba", "Xét kết quả học tập THPT (học bạ)", r"từ\s+(\d+(?:[.,]\d+)?)\s*điểm"),
        ("dgnl", "Xét kết quả kỳ thi Đánh giá năng lực", r"từ\s+(\d+(?:[.,]\d+)?)\s*điểm"),
    )
    records: list[dict[str, Any]] = []
    for method, label, pattern in patterns:
        match = re.search(re.escape(label) + r"[^\n]*?" + pattern, text, re.IGNORECASE)
        if match:
            raw_value = match.group(1)
            records.append(
                {
                    "record_type": "application_threshold",
                    "record_id": f"application_threshold_{method}",
                    "score_type": "application_threshold",
                    "method": method,
                    "label": label,
                    "value": _value_or_raw(raw_value),
                    "raw_value": raw_value,
                    "page": next((int(page["page"]) for page in pages if label.casefold() in str(page.get("text", "")).casefold()), 1),
                }
            )
    return records


def parse_admission_scores(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            match = re.match(r"^•\s*(?P<major>[^:]+):\s*(?P<value>\d+(?:[.,]\d+)?)\s*điểm", line, re.IGNORECASE)
            if match:
                raw_value = match.group("value")
                major_name = match.group("major").strip()
                record_type = "admission_score_rule" if major_name.casefold().startswith("các ngành") else "admission_score"
                records.append(
                    {
                        "record_type": record_type,
                        "record_id": f"admission_score_{len(records) + 1:03d}",
                        "score_type": "admission_score",
                        "method": "thpt",
                        "major_name": major_name,
                        "value": _value_or_raw(raw_value),
                        "raw_value": raw_value,
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_tuition(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    record: dict[str, Any] = {
        "record_type": "tuition",
        "record_id": "tuition_semester_1",
        "semester": "Học kỳ I",
        "credits": None,
        "tuition_amount_vnd": None,
        "admission_fee_vnd": None,
        "elearning_fee_vnd": None,
        "english_test_fee_vnd": None,
        "total_cost_vnd": None,
        "page": 1,
    }
    credits_match = re.search(r"Học phí HKI\s*\((\d+)\s*tín chỉ\)", text, re.IGNORECASE)
    if credits_match:
        record["credits"] = int(credits_match.group(1))
    field_patterns = {
        "tuition_amount_vnd": r"Học phí HKI[^\n]*?:\s*([^\n]+)",
        "admission_fee_vnd": r"Phí nhập học:\s*([^\n]+)",
        "elearning_fee_vnd": r"Tài khoản học liệu điện tử:\s*([^\n]+)",
        "english_test_fee_vnd": r"Kiểm tra năng lực Tiếng Anh[^:]*:\s*([^\n]+)",
        "total_cost_vnd": r"Tổng chi phí học kỳ I:\s*([^\n]+)",
    }
    for field, pattern in field_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            record[field] = _to_amount(match.group(1))
    return [record] if any(value is not None for key, value in record.items() if key.endswith("_vnd")) else []


def parse_scholarship(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    fund_match = re.search(r"tổng giá trị lên đến\s+(\d+)\s*tỷ đồng", text, re.IGNORECASE)
    if fund_match:
        records.append(
            {
                "record_type": "scholarship_fund",
                "record_id": "scholarship_fund_2026",
                "fund_amount_vnd": int(fund_match.group(1)) * 1_000_000_000,
                "raw_value": f"{fund_match.group(1)} tỷ đồng",
                "page": 1,
            }
        )
    condition_patterns = (
        (
            "academic_average",
            "Học bạ",
            r"Điểm TB lớp 11 hoặc HK1 lớp 12\s*>\s*8,5\s*:\s*hỗ trợ\s*(\d+)%[^\n]*\(([^)]+)\)",
            {"threshold_operator": ">", "threshold_value": 8.5},
        ),
        (
            "academic_average",
            "Học bạ",
            r"từ\s*7\s*đến\s*8,5\s*:\s*hỗ trợ\s*(\d+)%\s*\(([^)]+)\)",
            {"threshold_operator": "between", "threshold_min": 7, "threshold_max": 8.5},
        ),
        (
            "three_subject_total",
            "Theo tổng điểm 3 môn",
            r">\s*25,5\s*hỗ trợ\s*(\d+)%",
            {"threshold_operator": ">", "threshold_value": 25.5},
        ),
        (
            "three_subject_total",
            "Theo tổng điểm 3 môn",
            r"từ\s*21\s*đến\s*25,5\s*hỗ trợ\s*(\d+)%",
            {"threshold_operator": "between", "threshold_min": 21, "threshold_max": 25.5},
        ),
        (
            "dgnl",
            "ĐGNL ĐHQG-HCM",
            r">\s*700\s*hỗ trợ\s*(\d+)%[^\n]*\(([^)]+)\)",
            {"method": "dgnl", "threshold_operator": ">", "threshold_value": 700},
        ),
        (
            "dgnl",
            "ĐGNL ĐHQG-HCM",
            r"từ\s*650\s*đến\s*700\s*hỗ trợ\s*(\d+)%\s*\(([^)]+)\)",
            {"method": "dgnl", "threshold_operator": "between", "threshold_min": 650, "threshold_max": 700},
        ),
    )
    for condition_index, (condition_type, label, pattern, condition_fields) in enumerate(condition_patterns, start=1):
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        record: dict[str, Any] = {
            "record_type": "scholarship",
            "record_id": f"scholarship_{condition_type}_{condition_index}",
            "scholarship_name": "Học bổng tuyển sinh",
            "condition_type": condition_type,
            "basis_label": label,
            "support_percent": int(match.group(1)),
            "page": 1,
            **condition_fields,
        }
        if match.lastindex and match.lastindex >= 2:
            amount = _to_amount(match.group(2))
            if amount is not None:
                record["support_amount_vnd"] = amount
        records.append(record)
    # Preserve the remaining policies as exact text records.  No score or
    # eligibility value is inferred from prose that is not a deterministic row.
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line.startswith("• ") and any(
                marker in line for marker in ("Học bổng Tài năng", "Học bổng Ngành Tiên phong", "Đôi bạn cùng tiến", "Tương lai vững bước", "Biển đảo")
            ):
                records.append(
                    {
                        "record_type": "scholarship_policy",
                        "record_id": f"scholarship_policy_{len(records) + 1:03d}",
                        "policy_text": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    summary_lines: list[str] = []
    for record in records:
        record_type = record.get("record_type")
        if record_type == "scholarship_fund":
            summary_lines.append(f"Quỹ học bổng: {record.get('raw_value', '')}.")
        elif record_type == "scholarship":
            basis = str(record.get("basis_label") or "Điều kiện")
            operator = str(record.get("threshold_operator") or "")
            if operator == "between":
                threshold = f"từ {record.get('threshold_min')} đến {record.get('threshold_max')}"
            else:
                threshold = f"{operator} {record.get('threshold_value')}".strip()
            summary_lines.append(
                f"{basis}: {threshold}; hỗ trợ {record.get('support_percent')}%."
            )
        elif record_type == "scholarship_policy":
            summary_lines.append(str(record.get("policy_text") or ""))
    if summary_lines:
        records.insert(
            0,
            {
                "record_type": "scholarship_summary",
                "record_id": "scholarship_summary_2026",
                "summary_lines": summary_lines,
                "page": 1,
            },
        )
    return records


_WEBSITE_DIRECTORY: dict[str, tuple[str, str]] = {
    "https://dhv.edu.vn/": ("Website chính Trường Đại học Hùng Vương TP.HCM", "school"),
    "https://tuyensinh.dhv.edu.vn/": ("Cổng tuyển sinh DHV", "admissions_portal"),
    "https://ipic.dhv.edu.vn/": ("Viện Đào tạo Sau đại học", "institute"),
    "https://epdl.dhv.edu.vn/": ("Viện Liên kết Giáo dục và Đào tạo từ xa", "institute"),
    "https://heal.dhv.edu.vn/": ("Khoa Khoa học Sức khỏe", "faculty"),
    "https://tec.dhv.edu.vn/": ("Khoa Kỹ thuật Công nghệ", "faculty"),
    "https://fba.dhv.edu.vn/": ("Khoa Tài chính - Ngân hàng - Kế toán", "faculty"),
    "https://bam.dhv.edu.vn/": ("Khoa Quản trị Kinh doanh - Marketing", "faculty"),
    "https://lan.dhv.edu.vn/": ("Khoa Ngôn ngữ", "faculty"),
    "https://host.dhv.edu.vn/": ("Khoa Du lịch - Nhà hàng - Khách sạn", "faculty"),
    "https://online.dhv.edu.vn/": ("Cổng thông tin đào tạo dành cho sinh viên/giảng viên", "training_portal"),
}

_CATEGORY_LABELS = {
    "cach_tinh_diem": "Cách tính điểm xét tuyển DHV 2026",
    "co_so_lien_he": "Cơ sở và liên hệ tuyển sinh DHV 2026",
    "dang_ky_xet_tuyen": "Cổng đăng ký xét tuyển DHV 2026",
    "diem_trung_tuyen": "Điểm trúng tuyển DHV 2026",
    "ho_so": "Hồ sơ nhập học DHV 2026",
    "hoc_bong": "Học bổng DHV 2026",
    "hoc_phi": "Học phí DHV 2026",
    "lich_tuyen_sinh": "Lịch tuyển sinh DHV 2026",
    "nganh_dao_tao": "Ngành đào tạo DHV 2026",
    "nguong_dau_vao": "Điểm sàn DHV 2026",
    "nhap_hoc": "Nhập học DHV 2026",
    "phuong_thuc_xet_tuyen": "Phương thức xét tuyển DHV 2026",
    "thong_tin_truong": "Thông tin trường DHV 2026",
    "xet_tuyen_bo_sung": "Xét tuyển bổ sung DHV 2026",
}


def parse_official_websites(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    for url in _source_urls(text):
        normalized = url.rstrip("/") + "/" if url.count("/") == 2 else url
        unit_name, unit_type = _WEBSITE_DIRECTORY.get(
            normalized,
            ("Đơn vị DHV từ nguồn chính thức", "official_unit"),
        )
        page = next((int(item["page"]) for item in pages if url in str(item.get("text", ""))), 1)
        records.append(
            {
                "record_type": "official_website",
                "record_id": f"official_website_{len(records) + 1:03d}",
                "unit_name": unit_name,
                "unit_type": unit_type,
                "url": url,
                "page": page,
            }
        )
    overview_lines = _nonempty_lines(text)
    overview = [
        line
        for line in overview_lines
        if any(marker in line for marker in ("Tên trường:", "được thành lập từ năm", "thành lập từ năm"))
    ]
    if overview:
        records.insert(
            0,
            {
                "record_type": "school_information",
                "record_id": "school_information_overview",
                "information_text": " ".join(overview),
                "page": 1,
            },
        )
    return records


def parse_score_formulas(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    method = ""
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line.casefold() in {"học bạ", "thi tốt nghiệp thpt"}:
                method = "hoc_ba" if line.casefold() == "học bạ" else "thpt"
            if line.startswith("• ") and ("Điểm xét tuyển" in line or "Xét theo tổ hợp" in line):
                records.append(
                    {
                        "record_type": "score_formula",
                        "record_id": f"score_formula_{len(records) + 1:03d}",
                        "score_type": "score_formula",
                        "method": method or None,
                        "formula_text": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_admission_methods(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            match = re.match(r"^•\s*Phương thức\s*(\d+)\s*:\s*(.*)$", line, re.IGNORECASE)
            if match:
                records.append(
                    {
                        "record_type": "admission_method",
                        "record_id": f"admission_method_{match.group(1)}",
                        "method_number": int(match.group(1)),
                        "method_text": match.group(2).strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_registration_fields(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if not line.startswith("• ") or any(token in line for token in ("CCCD", "Căn cước", "Mã định danh")):
                continue
            records.append(
                {
                    "record_type": "registration_field",
                    "record_id": f"registration_field_{len(records) + 1:03d}",
                    "field_text": line[2:].strip(),
                    "page": int(page["page"]),
                }
            )
    return records


def parse_contacts(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if not line.startswith("• "):
                continue
            value = line[2:].strip()
            if ":" not in value:
                continue
            label, content = value.split(":", 1)
            contact_type = "hotline" if "đài" in label.casefold() or "hotline" in label.casefold() else "address"
            records.append(
                {
                    "record_type": "contact",
                    "record_id": f"contact_{len(records) + 1:03d}",
                    "contact_type": contact_type,
                    "label": label.strip(),
                    "value": content.strip(),
                    "page": int(page["page"]),
                }
            )
    return records


def parse_enrollment_documents(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line.startswith("• "):
                records.append(
                    {
                        "record_type": "enrollment_document",
                        "record_id": f"enrollment_document_{len(records) + 1:03d}",
                        "document_name": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_enrollment_modes(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    mode = ""
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line in {"Nhập học trực tiếp", "Nhập học trực tuyến"}:
                mode = "direct" if "trực tiếp" in line else "online"
            elif line.startswith("• "):
                records.append(
                    {
                        "record_type": "enrollment_mode",
                        "record_id": f"enrollment_mode_{len(records) + 1:03d}",
                        "mode": mode or "unspecified",
                        "instruction": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_deadlines(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if not line.startswith("• ") or not re.search(r"\d{1,2}/\d{1,2}/\d{4}", line):
                continue
            dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", line)
            records.append(
                {
                    "record_type": "deadline",
                    "record_id": f"deadline_{len(records) + 1:03d}",
                    "deadline_date": dates[-1],
                    "dates": dates,
                    "description": line[2:].strip(),
                    "page": int(page["page"]),
                }
            )
    return records


def parse_supplementary(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    quota = re.search(r"(\d+)\s*chỉ tiêu tại\s*(\d+)\s*chương trình", text, re.IGNORECASE)
    if quota:
        records.append(
            {
                "record_type": "supplementary_quota",
                "record_id": "supplementary_quota_2026",
                "quota": int(quota.group(1)),
                "program_count": int(quota.group(2)),
                "page": 1,
            }
        )
    threshold_line = next((line for line in _nonempty_lines(text) if "phần lớn chương trình nhận hồ sơ" in line), "")
    if threshold_line:
        records.append(
            {
                "record_type": "supplementary_threshold",
                "record_id": "supplementary_threshold_thpt_general",
                "score_type": "supplementary_threshold",
                "method": "thpt",
                "scope": "most_programs",
                "value": 15,
                "raw_value": "15",
                "page": 1,
            }
        )
        for major_name in ("Luật", "Luật kinh tế"):
            records.append(
                {
                    "record_type": "supplementary_threshold",
                    "record_id": f"supplementary_threshold_{major_name.casefold().replace(' ', '_')}",
                    "score_type": "supplementary_threshold",
                    "method": "thpt",
                    "major_name": major_name,
                    "value": 20,
                    "raw_value": "20",
                    "page": 1,
                }
            )
    if "Học bạ THPT" in text and "từ 18 điểm" in text:
        records.append(
            {
                "record_type": "supplementary_threshold",
                "record_id": "supplementary_threshold_hoc_ba_general",
                "score_type": "supplementary_threshold",
                "method": "hoc_ba",
                "scope": "most_programs",
                "value": 18,
                "raw_value": "18",
                "page": 1,
            }
        )
    records.extend(parse_deadlines(pages))
    return records


def parse_deadlines_and_policies(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line.startswith("• "):
                records.append(
                    {
                        "record_type": "policy_note",
                        "record_id": f"policy_note_{len(records) + 1:03d}",
                        "text": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


PARSERS = {
    "cach_tinh_diem": parse_score_formulas,
    "co_so_lien_he": parse_contacts,
    "dang_ky_xet_tuyen": parse_registration_fields,
    "nganh_dao_tao": parse_major_catalog,
    "nguong_dau_vao": parse_application_thresholds,
    "diem_trung_tuyen": parse_admission_scores,
    "hoc_phi": parse_tuition,
    "hoc_bong": parse_scholarship,
    "ho_so": parse_enrollment_documents,
    "lich_tuyen_sinh": parse_deadlines,
    "nhap_hoc": parse_enrollment_modes,
    "phuong_thuc_xet_tuyen": parse_admission_methods,
    "thong_tin_truong": parse_official_websites,
    "xet_tuyen_bo_sung": parse_supplementary,
}


def _parse_category_records(category: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parser = PARSERS.get(category)
    if parser is not None:
        parsed = parser(pages)
        if parsed:
            return parsed
        # A category-specific parser may legitimately find no deterministic
        # row (for example a descriptive career document under the same
        # ``nganh_dao_tao`` category).  Keep a traceable raw-text record rather
        # than making that source disappear from the processed layer.
        return [
            {
                "record_type": "document_text",
                "record_id": "document_text_001",
                "text": "\n\n".join(str(page.get("text", "")) for page in pages).strip(),
                "page": int(pages[0]["page"]) if pages else 1,
            }
        ]
    records = parse_deadlines_and_policies(pages)
    if records:
        return records
    return [
        {
            "record_type": "document_text",
            "record_id": "document_text_001",
            "text": "\n\n".join(str(page.get("text", "")) for page in pages).strip(),
            "page": int(pages[0]["page"]) if pages else 1,
        }
    ]


def _page_sections(title: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page["page"])
        sections.append(
            {
                "section_id": f"sec_{len(sections) + 1:03d}",
                "heading": title if page_number == 1 else f"{title} - trang {page_number}",
                "page_start": page_number,
                "page_end": page_number,
                "text": str(page.get("text", "")),
            }
        )
    return sections


def build_structured_document(
    *,
    raw_path: str | Path,
    raw_root: str | Path,
    pages: Iterable[Mapping[str, Any]],
    extraction_method: str = "pypdf_text",
    warnings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one JSON-serialisable structured document from extracted pages."""

    raw_file_path = Path(raw_path).resolve()
    raw_root_path = Path(raw_root).resolve()
    page_values = [
        {"page": int(page["page"]), "text": _clean_text(str(page.get("text", "")))}
        for page in pages
    ]
    if not page_values:
        raise ValueError("PDF has no pages")
    combined_text = "\n\n".join(page["text"] for page in page_values if page["text"])
    title = _title_from_text(combined_text)
    category = raw_file_path.parent.relative_to(raw_root_path).as_posix()
    if not category or "/" in category:
        raise ValueError("RAW PDF must be directly below one category directory")
    urls = _source_urls(combined_text)
    if not urls:
        raise ValueError("source URL not found in PDF text")
    if not all(is_official_dhv_url(url) for url in urls):
        raise ValueError("structured source URL is outside official DHV domain")
    source_date, collected_at = _date_metadata(combined_text)
    if not source_date:
        raise ValueError("source_date not found in PDF text")

    document_id = raw_file_path.stem
    data_role = "description" if category == "nganh_dao_tao" and any(marker in document_id.casefold() for marker in ("mo_ta", "nghe_nghiep", "trien_vong", "gioi_thieu")) else ("catalog" if category == "nganh_dao_tao" else "")
    warning_values: list[dict[str, Any]] = [dict(value) for value in warnings]
    for page in page_values:
        if not page["text"]:
            warning_values.append(
                {
                    "type": "EMPTY_EXTRACTED_PAGE",
                    "page": page["page"],
                    "message": "Page has no extracted text; review the RAW PDF before indexing.",
                }
            )
    structured = {
        "document_id": document_id,
        "title": title,
        "category": category,
        "year": 2026,
        "data_role": data_role,
        "source": {
            "file_name": raw_file_path.name,
            "raw_file": raw_file_path.relative_to(Path.cwd()).as_posix() if raw_file_path.is_relative_to(Path.cwd()) else raw_file_path.as_posix(),
            "source_url": urls[0],
            "source_urls": urls,
            "organization": SCHOOL_NAME,
            "verified": True,
            "status": "verified",
            "verification_status": "verified",
            "source_date": source_date,
            "collected_at": collected_at,
            "school_code": "DHV",
        },
        "extraction": {
            "method": extraction_method,
            "text_source": "pypdf",
            "page_count": len(page_values),
        },
        "pages": page_values,
        "sections": _page_sections(title, page_values),
        "records": _parse_category_records(category, page_values),
        "warnings": warning_values,
    }
    errors = validate_structured_document(structured)
    if errors:
        raise StructuredJSONValidationError(errors)
    return structured


def validate_structured_document(
    document: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> list[dict[str, Any]]:
    """Validate schema, provenance and domain invariants.

    The default return value is a list so callers can include all failures in a
    report.  ``raise_on_error=True`` is provided for ingestion boundaries.
    """

    errors: list[dict[str, Any]] = []

    def error(path: str, message: str) -> None:
        errors.append({"path": path, "message": message})

    for key in ("document_id", "title", "category", "source", "pages", "sections", "records", "warnings"):
        if key not in document:
            error(key, f"missing required field: {key}")
    if not str(document.get("document_id", "")).strip():
        error("document_id", "document_id must not be empty")
    if not str(document.get("title", "")).strip():
        error("title", "title must not be empty")
    if not str(document.get("category", "")).strip():
        error("category", "category must not be empty")
    year = document.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        error("year", "year must be an integer between 2000 and 2100")

    source = document.get("source")
    if not isinstance(source, Mapping):
        error("source", "source must be an object")
        source = {}
    for key in ("file_name", "source_url", "organization", "verified"):
        if key not in source:
            error(f"source.{key}", f"missing source field: {key}")
    urls = list(source.get("source_urls") or [])
    if source.get("source_url") and source.get("source_url") not in urls:
        urls.insert(0, source["source_url"])
    for index, url in enumerate(urls):
        if not is_official_dhv_url(url):
            error(f"source.source_urls[{index}]", "source URL must be an official DHV HTTPS URL on dhv.edu.vn or a subdomain")
    if source.get("status") != "verified" or source.get("verification_status") != "verified" or source.get("verified") is not True:
        error("source", "source must be explicitly verified")

    pages = document.get("pages")
    if not isinstance(pages, list) or not pages:
        error("pages", "pages must be a non-empty list")
        pages = []
    page_numbers: list[int] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            error(f"pages[{index}]", "page must be an object")
            continue
        number = page.get("page")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            error(f"pages[{index}].page", "page must be a positive integer")
        else:
            page_numbers.append(number)
        if not isinstance(page.get("text"), str):
            error(f"pages[{index}].text", "page text must be a string")
    if page_numbers and page_numbers != list(range(1, len(page_numbers) + 1)):
        error("pages", "page indexes must be sequential starting at 1")
    extraction = document.get("extraction")
    if isinstance(extraction, Mapping) and extraction.get("page_count") != len(pages):
        error("extraction.page_count", "page_count must equal len(pages)")

    records = document.get("records")
    if not isinstance(records, list):
        error("records", "records must be a list")
        records = []
    allowed_pages = set(page_numbers)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            error(f"records[{index}]", "record must be an object")
            continue
        if not str(record.get("record_type", "")).strip():
            error(f"records[{index}].record_type", "record_type must not be empty")
        page_value = record.get("page")
        source_pages = record.get("source_pages")
        if page_value is None and not source_pages:
            error(f"records[{index}]", "record must retain page or source_pages traceability")
        if page_value is not None and page_value not in allowed_pages:
            error(f"records[{index}].page", "record page does not exist in pages")
        if record.get("record_type") == "major":
            if not _MAJOR_CODE_RE.fullmatch(str(record.get("major_code", ""))):
                error(f"records[{index}].major_code", "major_code must be a seven-digit string")
            programs = record.get("programs") or []
            if not isinstance(programs, list):
                error(f"records[{index}].programs", "programs must be a list")
            else:
                for program_index, program in enumerate(programs):
                    if not isinstance(program, Mapping):
                        error(f"records[{index}].programs[{program_index}]", "program must be an object")
                        continue
                    if program.get("parent_major") != record.get("major_name"):
                        error(f"records[{index}].programs[{program_index}].parent_major", "program parent_major must match the containing major")
                    if program.get("page") not in allowed_pages:
                        error(f"records[{index}].programs[{program_index}].page", "program page does not exist in pages")
        if record.get("record_type") in {"application_threshold", "admission_score", "admission_score_rule", "supplementary_threshold"} and "score" in record:
            error(f"records[{index}]", "score is ambiguous; use the explicit semantic record type and value")
        record_type = str(record.get("record_type", ""))
        numeric_keys = {"threshold_value", "threshold_min", "threshold_max", "support_percent", "credits", "quota", "program_count"}
        if record_type in {"application_threshold", "admission_score", "admission_score_rule", "supplementary_threshold"}:
            numeric_keys.add("value")
        for key, value in record.items():
            if key.endswith("_vnd") or key in numeric_keys:
                if value is not None and value != "-" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                    error(f"records[{index}].{key}", "numeric field must be numeric, null, or the explicit '-' marker")
                if isinstance(value, (int, float)) and value < 0:
                    error(f"records[{index}].{key}", "numeric field must not be negative")
            if key == "url" and not is_official_dhv_url(value):
                error(f"records[{index}].url", "record URL must be an official DHV URL")

    if raise_on_error and errors:
        raise StructuredJSONValidationError(errors)
    return errors


def _record_text(record: Mapping[str, Any]) -> str:
    record_type = str(record.get("record_type", ""))
    if record_type == "major":
        lines = [
            f"Ngành: {record.get('major_name', '')} {record.get('major_code', '')}",
            f"Mã ngành: {record.get('major_code', '')}",
        ]
        programs = record.get("programs") or []
        if programs:
            lines.append("Các chương trình:")
            lines.extend(f"- {program.get('program_name', '')}" for program in programs if isinstance(program, Mapping))
        thresholds = record.get("thresholds") or {}
        if thresholds:
            lines.append("Ngưỡng hồ sơ (application_threshold):")
            labels = {"thpt": "Thi tốt nghiệp THPT", "hoc_ba": "Học bạ THPT", "dgnl": "ĐGNL ĐHQG-HCM"}
            lines.extend(f"- {labels.get(key, key)}: {value}" for key, value in thresholds.items())
            if all(value == "-" for value in thresholds.values()):
                lines.append("Giá trị gốc trong bảng: - - -")
        return "\n".join(lines)
    if record_type == "major_catalog_summary":
        lines = [f"Danh mục ngành đào tạo DHV 2026 có {record.get('major_count')} ngành:"]
        for major in record.get("major_rows", record.get("majors", [])):
            if not isinstance(major, Mapping):
                continue
            raw_thresholds = major.get("thresholds_raw") or {}
            marker = "- - -" if raw_thresholds and all(value == "-" for value in raw_thresholds.values()) else " / ".join(str(raw_thresholds.get(key, "")) for key in ("thpt", "hoc_ba", "dgnl"))
            lines.append(f"- {major.get('major_name')} {major.get('major_code')} {marker}")
        return "\n".join(lines)
    if record_type == "tuition":
        labels = (
            ("tuition_amount_vnd", "Học phí"),
            ("admission_fee_vnd", "Phí nhập học"),
            ("elearning_fee_vnd", "Tài khoản học liệu điện tử"),
            ("english_test_fee_vnd", "Kiểm tra năng lực Tiếng Anh"),
            ("total_cost_vnd", "Tổng chi phí học kỳ I"),
        )
        amount = record.get("tuition_amount_vnd")
        credits = record.get("credits", "")
        lines = [f"{label}: {_format_vnd(record[key])} đồng" for key, label in labels if isinstance(record.get(key), int)]
        summary = (
            f"Học phí HKI ({credits} tín chỉ): {_format_vnd(amount)} đồng"
            if isinstance(amount, int)
            else f"Học phí {record.get('semester', '')} ({credits} tín chỉ):"
        )
        return summary + "\n" + "\n".join(lines)
    if record_type == "official_website":
        return f"Đơn vị: {record.get('unit_name', '')}\nWebsite: {record.get('url', '')}"
    if record_type == "school_information":
        return str(record.get("information_text") or "").strip()
    if record_type == "application_threshold":
        return f"Ngưỡng đảm bảo chất lượng đầu vào (điểm sàn, {record.get('method', '')}): {record.get('raw_value', record.get('value'))} điểm."
    if record_type in {"admission_score", "admission_score_rule"}:
        return f"Điểm trúng tuyển ({record.get('method', '')}) ngành {record.get('major_name', '')}: {record.get('raw_value', record.get('value'))} điểm."
    if record_type == "supplementary_threshold":
        scope = record.get("major_name") or record.get("scope") or ""
        return f"Ngưỡng xét tuyển bổ sung ({record.get('method', '')}) {scope}: {record.get('raw_value', record.get('value'))} điểm."
    if record_type == "scholarship_fund":
        return f"• Quỹ học bổng 2026: {_format_vnd(int(record.get('fund_amount_vnd')))} đồng."
    if record_type == "scholarship":
        details = [
            str(record.get("basis_label") or "Điều kiện"),
            f"ngưỡng {record.get('threshold_operator', '')} {record.get('threshold_value', '')}".strip(),
        ]
        if record.get("threshold_min") is not None or record.get("threshold_max") is not None:
            details.append(
                f"khoảng {record.get('threshold_min', '')}–{record.get('threshold_max', '')}"
            )
        details.append(f"mức hỗ trợ {record.get('support_percent')}%")
        if isinstance(record.get("support_amount_vnd"), int):
            details.append(f"tương đương {_format_vnd(record['support_amount_vnd'])} đồng")
        return "• Học bổng tuyển sinh: " + "; ".join(detail for detail in details if detail)
    if record_type == "scholarship_policy":
        return f"• Chính sách học bổng: {record.get('policy_text', '')}"
    if record_type == "scholarship_summary":
        lines = ["• Điều kiện nhận học bổng tuyển sinh DHV 2026:"]
        lines.extend(f"• {line}" for line in record.get("summary_lines", []) if line)
        return "\n".join(lines)
    if record_type == "score_formula":
        return str(record.get("formula_text") or "").strip()
    if record_type == "admission_method":
        return f"Phương thức xét tuyển {record.get('method_number')}: {record.get('method_text', '')}"
    if record_type == "registration_field":
        return f"Thông tin trên cổng đăng ký xét tuyển: {record.get('field_text', '')}"
    if record_type == "contact":
        return f"{record.get('label', 'Liên hệ')}: {record.get('value', '')}"
    if record_type == "enrollment_document":
        return f"Hồ sơ nhập học: {record.get('document_name', '')}"
    if record_type == "enrollment_mode":
        return f"Nhập học ({record.get('mode', '')}): {record.get('instruction', '')}"
    if record_type == "deadline":
        return f"Hạn/mốc tuyển sinh {record.get('deadline_date', '')}: {record.get('description', '')}"
    if record_type == "supplementary_quota":
        return f"Xét tuyển bổ sung: {record.get('quota')} chỉ tiêu tại {record.get('program_count')} chương trình."
    return str(record.get("text") or record.get("policy_text") or record.get("raw_value") or "").strip()


def _scalar_metadata(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def build_chunk_documents(structured_document: Mapping[str, Any]) -> list[Document]:
    """Create natural-language LangChain documents from individual records."""

    validate_structured_document(structured_document, raise_on_error=True)
    source = structured_document["source"]
    base_metadata: dict[str, Any] = {
        "document_id": structured_document["document_id"],
        "title": structured_document["title"],
        "category": structured_document["category"],
        "year": structured_document["year"],
        "source_file": source.get("raw_file") or source.get("file_name"),
        "source_url": source.get("source_url"),
        "source_urls": json.dumps(source.get("source_urls") or [], ensure_ascii=False),
        "school_code": source.get("school_code", "DHV"),
        "status": source.get("status", "verified"),
        "verification_status": source.get("verification_status", "verified"),
        "source_date": source.get("source_date", ""),
        "collected_at": source.get("collected_at", ""),
    }
    document_id = str(structured_document["document_id"])
    chunks: list[Document] = []
    for index, record in enumerate(structured_document.get("records", []), start=1):
        if not isinstance(record, Mapping):
            continue
        text = _record_text(record)
        if not text:
            continue
        # Record text stays human-readable, but carries the document identity
        # that users commonly include in queries (for example "Học phí DHV
        # 2026").  This improves dense retrieval without embedding the whole
        # JSON object or relying on runtime parsing.
        category_label = _CATEGORY_LABELS.get(str(structured_document["category"]), str(structured_document["category"]))
        if record.get("record_type") != "major_catalog_summary":
            text = f"{category_label}\nDHV {structured_document['year']} - {structured_document['title']}\n{text}"
        metadata = dict(base_metadata)
        metadata.update(
            {
                "structured_record_id": record.get("record_id", f"record_{index:03d}"),
                "record_type": record.get("record_type", ""),
                "page": record.get("page", 1),
                "data_role": structured_document.get("data_role", ""),
            }
        )
        for key in (
            "major_name", "major_code", "parent_major", "parent_major_code", "method", "score_type",
            "threshold_type", "condition_type", "unit_name", "unit_type", "url", "program_count",
            "method_number", "scope", "basis_label", "scholarship_name", "contact_type", "label",
            "mode", "deadline_date", "quota", "major_count",
        ):
            scalar = _scalar_metadata(record.get(key))
            if scalar is not None:
                metadata[key] = scalar
        if record.get("record_type") == "major":
            program_names = [
                program.get("program_name")
                for program in record.get("programs", [])
                if isinstance(program, Mapping) and program.get("program_name")
            ]
            metadata["program_names"] = json.dumps(program_names, ensure_ascii=False)
        thresholds = record.get("thresholds")
        if isinstance(thresholds, Mapping):
            for key, value in thresholds.items():
                scalar = _scalar_metadata(value)
                if scalar is not None:
                    metadata[f"application_threshold_{key}"] = scalar
        for key in ("value", "raw_value", "threshold_value", "support_percent", "support_amount_vnd", "fund_amount_vnd", "credits"):
            scalar = _scalar_metadata(record.get(key))
            if scalar is not None:
                metadata[key] = scalar
        # Keep additional category-specific scalar fields available for
        # deterministic metadata filtering without ever placing nested lists
        # or objects into Chroma metadata.
        for key, value in record.items():
            if key in {"record_type", "record_id", "programs", "thresholds", "thresholds_raw", "dates"}:
                continue
            scalar = _scalar_metadata(value)
            if scalar is not None:
                metadata[key] = scalar
        chunks.append(Document(page_content=text, metadata=metadata))
    if not chunks:
        for section in structured_document.get("sections", []):
            if not isinstance(section, Mapping) or not str(section.get("text", "")).strip():
                continue
            metadata = dict(base_metadata)
            metadata.update(
                {
                    "structured_record_id": section.get("section_id", "section_001"),
                    "record_type": "section",
                    "page": section.get("page_start", 1),
                    "heading_path": section.get("heading", ""),
                    "data_role": structured_document.get("data_role", ""),
                }
            )
            chunks.append(
                Document(
                    page_content=(
                        f"{_CATEGORY_LABELS.get(str(structured_document['category']), str(structured_document['category']))}\n"
                        f"DHV {structured_document['year']} - {structured_document['title']}\n{section['text']}"
                    ),
                    metadata=metadata,
                )
            )
    # A stable parent document id is useful for deterministic chunk ids added
    # later by splitter.py; record-level text is intentionally never a JSON dump.
    for chunk in chunks:
        chunk.metadata["structured_document_id"] = document_id
    return chunks


def write_structured_json(document: Mapping[str, Any], output_path: str | Path) -> Path:
    validate_structured_document(document, raise_on_error=True)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_structured_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    document = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise StructuredJSONValidationError([{"path": "$", "message": "JSON root must be an object"}])
    validate_structured_document(document, raise_on_error=True)
    return document


__all__ = [
    "PARSERS",
    "SCHOOL_NAME",
    "StructuredJSONValidationError",
    "build_chunk_documents",
    "build_structured_document",
    "is_official_dhv_url",
    "load_structured_json",
    "parse_admission_scores",
    "parse_application_thresholds",
    "parse_major_catalog",
    "parse_official_websites",
    "parse_scholarship",
    "parse_tuition",
    "validate_structured_document",
    "write_structured_json",
]
