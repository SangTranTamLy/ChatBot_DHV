"""Structured JSON data layer for the DHV PDF ingestion pipeline.

This module owns the representation between extracted PDF text and the vector
store.  It deliberately contains deterministic, category-specific parsers:
the source PDF remains authoritative and an unrecognised value is kept as raw
text (or ``None``) instead of being guessed.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
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

    value = unicodedata.normalize("NFC", value)
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _value_or_raw(value: str) -> int | float | str:
    if value.strip() == "-":
        return "-"
    if re.fullmatch(r"\d+\.\d+", value.strip()):
        try:
            return float(value.strip())
        except ValueError:
            pass
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
    match = re.match(r"^DHV(?:\s+\d{4})?\s*-\s*(?P<title>.+?)\s*$", first)
    return match.group("title").strip() if match else first


def _page_for_line(lines: list[tuple[int, str]], index: int) -> int:
    return lines[index][0] if 0 <= index < len(lines) else 1


def _all_lines(pages: list[dict[str, Any]]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for page in pages:
        page_number = int(page["page"])
        result.extend((page_number, line.strip()) for line in str(page.get("text", "")).splitlines() if line.strip())
    return result


def _fold_label(value: object) -> str:
    """Fold a table label for semantic matching without altering its raw text."""

    text = str(value or "").casefold().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _table_values(row: Mapping[str, Any]) -> list[str]:
    """Return cells in source order; never build this from a duplicate-key dict."""

    values = row.get("values")
    if isinstance(values, list):
        return [_clean_text(str(value or "")).strip() for value in values]
    cells = row.get("cells")
    if isinstance(cells, list):
        ordered = sorted(
            (cell for cell in cells if isinstance(cell, Mapping)),
            key=lambda cell: (int(cell.get("column_index", 0)), int(cell.get("row_index", 0))),
        )
        return [_clean_text(str(cell.get("text") or "")).strip() for cell in ordered]
    return []


def _single_line(value: object) -> str:
    return re.sub(r"\s+", " ", _clean_text(str(value or ""))).strip()


def _table_header_text(value: object) -> str:
    """Normalize real or escaped line breaks in a structured table header."""

    text = str(value or "")
    # Some upstream JSON-compatible fixtures encode a visual line break as
    # two literal characters (backslash + n) instead of an actual newline.
    # Normalize only header presentation; page text and cell contents remain
    # untouched for source fidelity.
    text = text.replace("\\r\\n", " ").replace("\\n", " ").replace("\\r", " ")
    return _single_line(text)


def _row_data_from_values(headers: list[str], values: list[str]) -> dict[str, str]:
    """Build a header-keyed row mapping without losing duplicate columns."""

    result: dict[str, str] = {}
    occurrences: dict[str, int] = {}
    for index, value in enumerate(values):
        base = headers[index].strip() if index < len(headers) else f"column_{index + 1}"
        base = base or f"column_{index + 1}"
        occurrences[base] = occurrences.get(base, 0) + 1
        key = base if occurrences[base] == 1 else f"{base} [{occurrences[base]}]"
        result[key] = value
    return result


def _normalize_page_tables(page: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Copy page table structures while canonicalizing only their headers."""

    normalized_tables: list[dict[str, Any]] = []
    headers_by_table_id: dict[str, list[str]] = {}
    for source_table in page.get("tables", []) or []:
        if not isinstance(source_table, Mapping):
            continue
        table = dict(source_table)
        old_headers = table.get("headers")
        if isinstance(old_headers, list):
            headers = [_table_header_text(header) for header in old_headers]
            table["headers"] = headers
            table_id = str(table.get("table_id") or "")
            if table_id:
                headers_by_table_id[table_id] = headers

            normalized_rows: list[dict[str, Any]] = []
            for source_row in table.get("rows", []) or []:
                if not isinstance(source_row, Mapping):
                    normalized_rows.append(source_row)
                    continue
                row = dict(source_row)
                values = _table_values(source_row)
                cells: list[dict[str, Any]] = []
                for cell_index, source_cell in enumerate(source_row.get("cells", []) or []):
                    if not isinstance(source_cell, Mapping):
                        cells.append(source_cell)
                        continue
                    cell = dict(source_cell)
                    try:
                        column_index = int(cell.get("column_index", cell_index))
                    except (TypeError, ValueError):
                        column_index = cell_index
                    if 0 <= column_index < len(headers):
                        cell["header"] = headers[column_index]
                    cells.append(cell)
                if isinstance(source_row.get("cells"), list):
                    row["cells"] = cells
                if isinstance(source_row.get("data"), Mapping):
                    row["data"] = _row_data_from_values(headers, values)
                normalized_rows.append(row)
            if isinstance(table.get("rows"), list):
                table["rows"] = normalized_rows
        normalized_tables.append(table)

    normalized_elements: list[dict[str, Any]] = []
    for source_element in page.get("elements", []) or []:
        if not isinstance(source_element, Mapping):
            continue
        element = dict(source_element)
        table_id = str(element.get("table_id") or "")
        if element.get("type") == "table" and table_id in headers_by_table_id:
            element["text"] = " | ".join(headers_by_table_id[table_id])
        normalized_elements.append(element)
    return normalized_tables, normalized_elements


def _iter_table_rows(
    pages: list[dict[str, Any]],
) -> Iterable[tuple[int, Mapping[str, Any], list[str], list[str]]]:
    """Yield page, table, headers, and ordered cell values for every table row."""

    for page in pages:
        page_number = int(page.get("page", page.get("page_number", 1)) or 1)
        tables = page.get("tables")
        if not isinstance(tables, list):
            continue
        for table in tables:
            if not isinstance(table, Mapping):
                continue
            raw_headers = table.get("headers")
            if not isinstance(raw_headers, list):
                continue
            headers = [_table_header_text(value) for value in raw_headers]
            rows = table.get("rows")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, Mapping):
                    yield page_number, table, headers, _table_values(row)


def _table_column(headers: list[str], *needles: str) -> int | None:
    folded_needles = tuple(_fold_label(needle) for needle in needles)
    for index, header in enumerate(headers):
        folded = _fold_label(header)
        if any(needle and needle in folded for needle in folded_needles):
            return index
    return None


def _program_names_from_cell(value: object) -> list[str]:
    """Rejoin visual line wraps while preserving separate program entries.

    In the source tables, program labels are unbulleted lines. A lowercase
    continuation or a preceding conjunction indicates a wrapped label; a new
    capitalized line otherwise starts a separate program. The untouched cell
    text remains in ``pages[].tables`` regardless of this semantic parse.
    """

    lines = [
        re.sub(r"^(?:[-•●▪◦]|\d+[.)])\s*", "", line).strip()
        for line in _clean_text(str(value or "")).splitlines()
        if line.strip()
    ]
    programs: list[str] = []
    continuation_endings = ("và", "&", "của", "với", "theo", "-", "–")
    for line in lines:
        if not programs:
            programs.append(line)
            continue
        previous = programs[-1].rstrip()
        joins_previous = (
            line[:1].islower()
            or previous.casefold().endswith(continuation_endings)
        )
        if joins_previous:
            programs[-1] = f"{previous} {line}".strip()
        else:
            programs.append(line)
    return programs


def _append_major_catalog_summary(records: list[dict[str, Any]]) -> None:
    majors = [record for record in records if record.get("record_type") == "major"]
    if not majors:
        return
    records.append(
        {
            "record_type": "major_catalog_summary",
            "record_id": "major_catalog_summary",
            "fact_category": "nganh_dao_tao",
            "major_count": len(majors),
            "majors": [
                {"major_name": record["major_name"], "major_code": record["major_code"]}
                for record in majors
            ],
            "major_rows": [
                {
                    "major_name": record["major_name"],
                    "major_code": record["major_code"],
                    "thresholds_raw": record.get("thresholds_raw", {}),
                }
                for record in majors
            ],
            "page": majors[-1]["page"],
        }
    )


def _catalog_code_positions(lines: list[tuple[int, str]]) -> list[int]:
    """Return code lines used by catalog-style PDFs.

    DHV publishes the same catalog in several layouts: one uses a standalone
    seven-digit code after the program list, another keeps ``Major  code`` on
    one line.  Admission tables use a leading row number and are deliberately
    excluded here so their values cannot be mislabeled as application
    thresholds.
    """

    positions: list[int] = []
    for index, (_, line) in enumerate(lines):
        if _MAJOR_CODE_RE.fullmatch(line) or re.fullmatch(r".+\s+\d{7}", line):
            positions.append(index)
    return positions


def _catalog_major_name(lines: list[tuple[int, str]], index: int) -> str:
    line = lines[index][1]
    inline = re.fullmatch(r"(?P<name>.+?)\s+(?P<code>\d{7})", line)
    if inline:
        return inline.group("name").strip(" •-.")

    candidates: list[str] = []
    cursor = index - 1
    while cursor >= 0 and len(candidates) < 3:
        candidate = lines[cursor][1].strip()
        if _MAJOR_CODE_RE.fullmatch(candidate):
            break
        if candidate.startswith(("-", "•")):
            cursor -= 1
            continue
        # Native extraction can put a wrapped program continuation on its own
        # line (for example ``hợp`` after ``- Quản trị Kinh doanh tổng``).
        # It is not the major label and must not be promoted to one.
        if (
            cursor > 0
            and lines[cursor - 1][1].strip().startswith(("-", "•"))
            and not (
                cursor > 1
                and _MAJOR_CODE_RE.fullmatch(lines[cursor - 2][1].strip())
            )
            and (
                candidate[:1].islower()
                or (
                    cursor > 1
                    and lines[cursor - 2][1].strip().startswith(("-", "•"))
                )
                or (
                    cursor > 2
                    and not lines[cursor - 2][1].strip().startswith(("-", "•"))
                    and lines[cursor - 3][1].strip().startswith(("-", "•"))
                )
            )
        ):
            cursor -= 1
            continue
        if re.match(r"^(?:STT|Mã|Tên mã|Bảng|1\.\d|\d+\.)", candidate, re.IGNORECASE):
            break
        candidates.append(candidate)
        cursor -= 1
        # A lower-case line is normally a wrapped continuation such as
        # ``lịch & Lữ hành``.  The next line is the start of the major name.
        if not candidate[:1].islower():
            break
    if not candidates:
        return ""
    return " ".join(reversed(candidates)).strip(" •-.")


def _catalog_programs(
    lines: list[tuple[int, str]],
    *,
    index: int,
    lower_bound: int,
    parent_major: str,
    parent_major_code: str,
    page: int,
) -> list[dict[str, Any]]:
    """Read bullet programs, including line-wrapped bullet continuations."""

    programs: list[dict[str, Any]] = []
    pending_continuation: list[str] = []
    cursor = index - 1
    while cursor > lower_bound:
        candidate = lines[cursor][1].strip()
        if candidate == parent_major:
            break
        if candidate.startswith(("-", "•")):
            program_name = candidate[1:].strip(" •-.")
            if pending_continuation:
                program_name = f"{program_name} {' '.join(reversed(pending_continuation))}".strip()
                pending_continuation.clear()
            if program_name:
                programs.append(
                    {
                        "program_name": program_name,
                        "parent_major": parent_major,
                        "parent_major_code": parent_major_code,
                        "page": page,
                    }
                )
            cursor -= 1
            continue
        if cursor > lower_bound and lines[cursor - 1][1].strip().startswith(("-", "•")):
            pending_continuation.append(candidate)
            cursor -= 1
            continue
        break
    programs.reverse()
    return programs


def _major_catalog_from_layout_tables(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover a full major catalogue from split/merged PDF table columns.

    Some DHV tables have merged cells. The PDF layout reader can place a major
    name in either the unnamed first column or the labelled major column, and
    may put the associated code on a later visual row. In that layout, pairing
    cells from a single extracted row silently drops most majors. Read the
    ordered major-name column and ordered seven-digit codes independently,
    then pair them only when the source's declared catalogue count confirms
    the complete mapping.
    """

    table_pages: set[int] = set()
    names: list[str] = []
    programs_by_name: dict[str, list[dict[str, Any]]] = {}
    active_major = ""

    for page in pages:
        page_number = int(page.get("page", page.get("page_number", 1)) or 1)
        for table in page.get("tables", []) or []:
            if not isinstance(table, Mapping):
                continue
            raw_headers = table.get("headers")
            if not isinstance(raw_headers, list):
                continue
            headers = [_table_header_text(value) for value in raw_headers]
            major_index = _table_column(headers, "ten nganh")
            program_index = _table_column(headers, "chuong trinh")
            if major_index is None or program_index is None:
                continue
            table_pages.add(page_number)

            for row in table.get("rows", []) or []:
                if not isinstance(row, Mapping):
                    continue
                values = _table_values(row)
                label = ""
                for column_index in dict.fromkeys((0, major_index)):
                    if column_index >= len(values):
                        continue
                    candidate = " ".join(values[column_index].split()).strip(" •*-")
                    if (
                        candidate
                        and not _MAJOR_CODE_RE.fullmatch(candidate)
                        and len(candidate.split()) <= 12
                    ):
                        label = candidate
                        break
                if label:
                    active_major = label
                    if label not in programs_by_name:
                        names.append(label)
                        programs_by_name[label] = []

                if not active_major:
                    continue
                # The extracted table may shift a merged program column one
                # cell left on some rows. Collect only those two adjacent
                # columns, and deduplicate while preserving document order.
                for column_index in dict.fromkeys((program_index - 1, program_index)):
                    if not 0 <= column_index < len(values):
                        continue
                    for program_name in _program_names_from_cell(values[column_index]):
                        program_name = program_name.strip(" •*-")
                        if not program_name or program_name in {
                            item["program_name"] for item in programs_by_name[active_major]
                        }:
                            continue
                        programs_by_name[active_major].append(
                            {
                                "program_name": program_name,
                                "parent_major": active_major,
                                "page": page_number,
                            }
                        )

    if not names or not table_pages:
        return []

    lines = _all_lines(pages)
    code_positions = [
        index
        for index, (page_number, line) in enumerate(lines)
        if page_number in table_pages and _MAJOR_CODE_RE.fullmatch(line)
    ]
    codes = [lines[index][1] for index in code_positions]
    all_text = " ".join(str(page.get("text", "")) for page in pages)
    declared_count_match = re.search(
        r"\b(\d{1,3})\s+nganh(?: hoc)?\s+voi\s+hon\s+\d{1,3}\s+chuong trinh\b",
        _fold_label(all_text),
    )
    declared_count = int(declared_count_match.group(1)) if declared_count_match else None
    if (
        len(names) != len(codes)
        or len(set(names)) != len(names)
        or len(set(codes)) != len(codes)
        or (declared_count is not None and len(names) != declared_count)
    ):
        return []

    records: list[dict[str, Any]] = []
    for index, (major_name, major_code) in enumerate(zip(names, codes), start=1):
        code_position = code_positions[index - 1]
        page_number = _page_for_line(lines, code_position)
        record: dict[str, Any] = {
            "record_type": "major",
            "record_id": f"major_{index:03d}",
            "fact_category": "nganh_dao_tao",
            "major_name": major_name,
            "major_code": major_code,
            "programs": [
                {**program, "parent_major_code": major_code}
                for program in programs_by_name.get(major_name, [])
            ],
            "program_count": len(programs_by_name.get(major_name, [])),
            "page": page_number,
        }
        records.append(record)

    _append_major_catalog_summary(records)
    return records


def parse_major_catalog(
    pages: list[dict[str, Any]],
    *,
    include_thresholds: bool = True,
) -> list[dict[str, Any]]:
    """Parse major rows while keeping programs as children of their major.

    ``include_thresholds`` is only enabled for a source whose table explicitly
    places three threshold columns after each major row.  Multi-topic official
    PDFs often contain the catalog without those columns; in that case the
    catalog and threshold facts are emitted as separate semantic records.
    """

    table_records: list[dict[str, Any]] = []
    for page_number, _table, headers, values in _iter_table_rows(pages):
        major_index = _table_column(headers, "ten nganh")
        code_index = _table_column(headers, "ma nganh")
        if major_index is None or code_index is None or max(major_index, code_index) >= len(values):
            continue
        major_name = _single_line(values[major_index]).strip(" •-.")
        major_code = re.sub(r"\s+", "", values[code_index])
        if not major_name or not re.fullmatch(r"\d{7}", major_code):
            continue

        program_index = _table_column(headers, "chuong trinh")
        programs: list[dict[str, Any]] = []
        if program_index is not None and program_index < len(values):
            for program_name in _program_names_from_cell(values[program_index]):
                program_name = program_name.strip(" •-.")
                if program_name:
                    programs.append(
                        {
                            "program_name": program_name,
                            "parent_major": major_name,
                            "parent_major_code": major_code,
                            "page": page_number,
                        }
                    )

        record: dict[str, Any] = {
            "record_type": "major",
            "record_id": f"major_{len(table_records) + 1:03d}",
            "fact_category": "nganh_dao_tao",
            "major_name": major_name,
            "major_code": major_code,
            "programs": programs,
            "program_count": len(programs),
            "page": page_number,
        }
        if include_thresholds:
            threshold_columns = {
                "thpt": _table_column(headers, "thi tn thpt", "thpt"),
                "hoc_ba": _table_column(headers, "hoc ba", "hoc tap thpt"),
                "dgnl": _table_column(headers, "dgnl"),
            }
            raw_thresholds = {
                method: values[index]
                for method, index in threshold_columns.items()
                if index is not None and index < len(values) and values[index]
            }
            if len(raw_thresholds) == 3:
                record["threshold_type"] = "application_threshold"
                record["thresholds_raw"] = raw_thresholds
                record["thresholds"] = {
                    method: _value_or_raw(value)
                    for method, value in raw_thresholds.items()
                }
        table_records.append(record)

    all_text = " ".join(str(page.get("text", "")) for page in pages)
    declared_count_match = re.search(
        r"\b(\d{1,3})\s+nganh(?: hoc)?\s+voi\s+hon\s+\d{1,3}\s+chuong trinh\b",
        _fold_label(all_text),
    )
    declared_count = int(declared_count_match.group(1)) if declared_count_match else None
    layout_records = _major_catalog_from_layout_tables(pages)
    if table_records and (
        (declared_count is not None and len(table_records) == declared_count)
        or (
            declared_count is None
            and (not layout_records or len(table_records) >= len(layout_records))
        )
    ):
        # Keep the row-level threshold fields when the direct table parse is
        # already complete; the layout fallback exists for split-cell tables.
        _append_major_catalog_summary(table_records)
        return table_records
    if layout_records:
        return layout_records

    has_catalog_layout = any(
        _table_column(headers, "ten nganh") is not None
        and _table_column(headers, "chuong trinh") is not None
        for _page_number, _table, headers, _values in _iter_table_rows(pages)
    )
    if declared_count_match and has_catalog_layout:
        # If the layout-based reconstruction cannot verify the advertised
        # number of rows, keep the partial parse out of the index entirely.
        return []

    if table_records:
        if declared_count is not None and len(table_records) != declared_count:
            # Do not manufacture a "complete" summary from a partial table
            # parse. A later rebuild can safely omit these records until the
            # layout reader can verify every name/code pair.
            return []
        _append_major_catalog_summary(table_records)
        return table_records

    # Do not reinterpret score tables (or program/major-code tables whose
    # name column is not explicitly a major-name column) as a catalog by
    # reading nearby row numbers as major names. Those facts have dedicated
    # parsers and remain available in the preserved table/page content.
    for _page_number, _table, headers, _values in _iter_table_rows(pages):
        has_major_code = _table_column(headers, "ma nganh", "ma xet tuyen") is not None
        has_major_name = _table_column(headers, "ten nganh") is not None
        has_score_columns = any(
            _table_column(headers, marker) is not None
            for marker in ("thi tn thpt", "hoc tap thpt", "hoc ba", "dgnl")
        )
        if has_major_code and (has_score_columns or not has_major_name):
            return []

    lines = _all_lines(pages)
    code_positions = _catalog_code_positions(lines)
    records: list[dict[str, Any]] = []
    for position_index, index in enumerate(code_positions):
        page, line = lines[index]
        inline = re.fullmatch(r"(?P<name>.+?)\s+(?P<code>\d{7})", line)
        major_code = inline.group("code") if inline else line
        major_name = _catalog_major_name(lines, index)
        if not major_name:
            continue

        lower_bound = code_positions[position_index - 1] if position_index else -1
        programs = _catalog_programs(
            lines,
            index=index,
            lower_bound=lower_bound,
            parent_major=major_name,
            parent_major_code=major_code,
            page=page,
        )
        next_code = (
            code_positions[position_index + 1]
            if position_index + 1 < len(code_positions)
            else len(lines)
        )
        # A page break can place the final bullet of a major after its code
        # and before the next major label.  Keep that source bullet attached
        # to the preceding major instead of silently dropping it.
        next_major_name = (
            _catalog_major_name(lines, next_code)
            if next_code < len(lines)
            else ""
        )
        if next_major_name:
            for forward_index in range(index + 1, next_code):
                candidate = lines[forward_index][1].strip()
                if candidate == next_major_name:
                    break
                if (
                    programs
                    and not candidate.startswith(("-", "•"))
                    and lines[forward_index - 1][1].strip().startswith(("-", "•"))
                ):
                    programs[-1]["program_name"] = (
                        f"{programs[-1]['program_name']} {candidate}"
                    ).strip()
                    continue
                if not candidate.startswith(("-", "•")):
                    candidate_key = re.sub(r"\s+", " ", candidate).casefold()
                    next_major_key = re.sub(r"\s+", " ", next_major_name).casefold()
                    if candidate_key and next_major_key.startswith(candidate_key):
                        break
                if candidate.startswith(("-", "•")):
                    program_name = candidate[1:].strip(" •-.")
                    if program_name and not any(
                        program.get("program_name") == program_name
                        for program in programs
                    ):
                        programs.append(
                            {
                                "program_name": program_name,
                                "parent_major": major_name,
                                "parent_major_code": major_code,
                                "page": lines[forward_index][0],
                            }
                        )

        record: dict[str, Any] = {
            "record_type": "major",
            "record_id": f"major_{len(records) + 1:03d}",
            "fact_category": "nganh_dao_tao",
            "major_name": major_name,
            "major_code": major_code,
            "programs": programs,
            "program_count": len(programs),
            "page": page,
        }

        if include_thresholds and not inline:
            values: list[str] = []
            for value_index in range(index + 1, next_code):
                value = lines[value_index][1]
                if _NUMBER_RE.fullmatch(value) or value == "-":
                    values.append(value)
                if len(values) == 3:
                    break
            if len(values) == 3:
                record.update(
                    {
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
                    }
                )
        records.append(record)

    _append_major_catalog_summary(records)
    return records


def parse_application_thresholds(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    def add(method: str, raw_value: str, label: str, *, major_name: str | None = None) -> None:
        record: dict[str, Any] = {
            "record_type": "application_threshold",
            "record_id": f"application_threshold_{method}_{len(records) + 1:03d}",
            "fact_category": "nguong_dau_vao",
            "score_type": "application_threshold",
            "method": method,
            "label": label,
            "value": _value_or_raw(raw_value),
            "raw_value": raw_value,
            "page": next((int(page["page"]) for page in pages if label.casefold() in str(page.get("text", "")).casefold()), 1),
        }
        if major_name:
            record["major_name"] = major_name
        records.append(record)

    thpt = re.search(r"tối\s*thiểu\s*(\d+(?:[.,]\d+)?)\s*điểm", text, re.IGNORECASE)
    if not thpt:
        # One source PDF places an illustration marker between ``tối`` and
        # ``thiểu`` at a page boundary.  The bounded fallback preserves the
        # same sentence instead of borrowing a value from another section.
        thpt = re.search(r"tối[\s\S]{0,300}?thiểu\s*(\d+(?:[.,]\d+)?)\s*điểm", text, re.IGNORECASE)
    if thpt:
        add("thpt", thpt.group(1), "Điều kiện chung xét tuyển THPT")

    law = re.search(
        r"ngành\s+Luật\s+và\s+Luật\s+Kinh\s+tế[\s\S]{0,500}?đạt\s+từ\s+(\d+(?:[.,]\d+)?)\s*điểm",
        text,
        re.IGNORECASE,
    )
    if law:
        for major_name in ("Luật", "Luật kinh tế"):
            add("thpt", law.group(1), "Điều kiện riêng ngành Luật/Luật kinh tế", major_name=major_name)

    dgnl = re.search(
        r"Đánh\s+giá\s+năng\s+lực[\s\S]{0,500}?điểm\s+từ\s+(\d+(?:[.,]\d+)?)\s*điểm",
        text,
        re.IGNORECASE,
    )
    if dgnl:
        add("dgnl", dgnl.group(1), "Xét kết quả kỳ thi Đánh giá năng lực")
    return records


def parse_admission_scores(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    table_records: list[dict[str, Any]] = []
    for page_number, _table, headers, values in _iter_table_rows(pages):
        code_index = _table_column(headers, "ma xet tuyen", "ma nganh")
        major_index = _table_column(headers, "ten ma xet tuyen", "ten nganh")
        method_columns = {
            "thpt": _table_column(headers, "thi tn thpt", "thi tot nghiep thpt"),
            "hoc_ba": _table_column(headers, "hoc tap thpt", "hoc ba"),
            "dgnl": _table_column(headers, "dgnl"),
        }
        if (
            code_index is None
            or major_index is None
            or any(index is None for index in method_columns.values())
            or max([code_index, major_index, *(int(index) for index in method_columns.values())]) >= len(values)
        ):
            continue
        major_code = re.sub(r"\s+", "", values[code_index])
        major_name = _single_line(values[major_index]).strip(" •*-")
        if not re.fullmatch(r"\d{7,9}", major_code) or not major_name:
            continue
        for method, column_index in method_columns.items():
            raw_value = _single_line(values[int(column_index)])
            if not raw_value:
                continue
            marker = "(*)" if re.search(r"\(\s*\*\s*\)\s*$", raw_value) else ""
            numeric_value = re.sub(r"\s*\(\s*\*\s*\)\s*$", "", raw_value).strip()
            table_records.append(
                {
                    "record_type": "admission_score",
                    "record_id": f"admission_score_{len(table_records) + 1:03d}",
                    "fact_category": "diem_trung_tuyen",
                    "score_type": "admission_score",
                    "method": method,
                    "major_name": major_name,
                    "major_code": major_code,
                    "value": _value_or_raw(numeric_value),
                    "raw_value": raw_value,
                    "page": page_number,
                    **({"footnote_marker": marker} if marker else {}),
                }
            )
    records.extend(table_records)

    for page in pages:
        lines = _nonempty_lines(str(page.get("text", "")))
        if not table_records:
            rows: list[str] = []
            current: list[str] = []
            for line in lines:
                if re.match(r"^\d+\s+\d{7,9}\s+", line):
                    if current:
                        rows.append(" ".join(current))
                    current = [line]
                elif current:
                    current.append(line)
            if current:
                rows.append(" ".join(current))
            row_pattern = re.compile(
                r"^\d+\s+(?P<code>\d{7,9})\s+(?P<major>.+?)\s+"
                r"(?P<thpt>\d+(?:[.,]\d+)?)\s+"
                r"(?P<hoc_ba>\d+(?:[.,]\d+)?(?:\(\*\))?)\s+"
                r"(?P<dgnl>\d+(?:[.,]\d+)?)$",
                re.IGNORECASE,
            )
            for row in rows:
                match = row_pattern.match(row)
                if not match:
                    continue
                for method in ("thpt", "hoc_ba", "dgnl"):
                    raw_value = match.group(method)
                    marker = "(*)" if "(*)" in raw_value else ""
                    numeric_value = raw_value.replace("(*)", "").strip()
                    records.append(
                        {
                            "record_type": "admission_score",
                            "record_id": f"admission_score_{len(records) + 1:03d}",
                            "fact_category": "diem_trung_tuyen",
                            "score_type": "admission_score",
                            "method": method,
                            "major_name": match.group("major").strip(" •*-"),
                            "major_code": match.group("code"),
                            "value": _value_or_raw(numeric_value),
                            "raw_value": raw_value,
                            "page": int(page["page"]),
                            **({"footnote_marker": marker} if marker else {}),
                        }
                    )

        for line in lines:
            match = re.match(r"^•\s*(?P<major>[^:]+):\s*(?P<value>\d+(?:[.,]\d+)?)\s*điểm", line, re.IGNORECASE)
            if match:
                raw_value = match.group("value")
                major_name = match.group("major").strip()
                record_type = "admission_score_rule" if major_name.casefold().startswith("các ngành") else "admission_score"
                records.append(
                    {
                        "record_type": record_type,
                        "record_id": f"admission_score_{len(records) + 1:03d}",
                        "fact_category": "diem_trung_tuyen",
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
        "total_cost_breakdown": None,
        "tuition_per_credit_vnd": None,
        "unit_type": "per_semester",
        "unit_name": "Học kỳ I",
        "page": 1,
    }
    table_fee_page: int | None = None
    for page_number, _table, headers, values in _iter_table_rows(pages):
        label_index = _table_column(headers, "khoan thu", "hang muc", "noi dung thu")
        amount_index = _table_column(headers, "muc phi", "so tien", "thanh tien")
        if label_index is None or amount_index is None or max(label_index, amount_index) >= len(values):
            continue
        label = _fold_label(values[label_index])
        amount_text = _single_line(values[amount_index])
        amount = _to_amount(amount_text)
        if amount is None:
            amount_match = re.search(r"\d[\d.]*", amount_text)
            amount = _to_int(amount_match.group(0)) if amount_match else None
        if amount is None:
            continue
        if "hoc phi hki" in label or "hoc phi hoc ky i" in label:
            record["tuition_amount_vnd"] = amount
            credits_match = re.search(
                r"\((\d+)\s*tín\s*chỉ\)",
                _single_line(values[label_index]),
                re.IGNORECASE,
            )
            if credits_match:
                record["credits"] = int(credits_match.group(1))
            table_fee_page = page_number
        elif "phi nhap hoc" in label:
            record["admission_fee_vnd"] = amount
            table_fee_page = table_fee_page or page_number
        elif "tai khoan hoc lieu" in label or "hoc lieu dien tu" in label:
            record["elearning_fee_vnd"] = amount
            table_fee_page = table_fee_page or page_number
        elif "kiem tra nang luc tieng anh" in label:
            record["english_test_fee_vnd"] = amount
            table_fee_page = table_fee_page or page_number
        elif "tong chi phi hoc ky i" in label:
            record["total_cost_vnd"] = amount
            record["total_cost_breakdown"] = amount_text
            table_fee_page = table_fee_page or page_number
    if table_fee_page is not None:
        record["page"] = table_fee_page

    credits_match = re.search(r"Học phí HKI\s*\((\d+)\s*tín chỉ\)", text, re.IGNORECASE)
    if credits_match and record["credits"] is None:
        record["credits"] = int(credits_match.group(1))
    field_patterns = {
        "tuition_amount_vnd": r"Học phí HKI[^\n]*?\)\s*([^\n]+)",
        "admission_fee_vnd": r"Phí nhập học\s*:?\s*([^\n]+)",
        "elearning_fee_vnd": r"Tài khoản học liệu điện tử\s*:?\s*([^\n]+)",
        "english_test_fee_vnd": r"Kiểm tra năng lực Tiếng Anh[^:]*:?\s*([^\n]+)",
        "total_cost_vnd": r"Tổng chi phí học kỳ I\s*:?\s*([^\n]+)",
    }
    for field, pattern in field_patterns.items():
        if record.get(field) is not None:
            continue
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            record[field] = _to_amount(match.group(1))
    total_match = re.search(r"Tổng chi phí học kỳ I\s*:?\s*([^\n]+)", text, re.IGNORECASE)
    if total_match and record["total_cost_breakdown"] is None:
        record["total_cost_breakdown"] = total_match.group(1).strip()
    per_credit = re.search(
        r"học phí\s+được\s+tính\s+([\d.]+)\s*đồng\s*/\s*tín\s*chỉ",
        text,
        re.IGNORECASE,
    )
    if per_credit:
        record["tuition_per_credit_vnd"] = _to_int(per_credit.group(1))
        record["unit_type"] = "per_credit"
        record["unit_name"] = "tín chỉ"
        record["per_credit_page"] = next(
            (int(page["page"]) for page in pages if "được tính" in str(page.get("text", "")).casefold()),
            1,
        )
        if table_fee_page is None:
            record["page"] = record["per_credit_page"]
    record["fact_category"] = "hoc_phi"
    return [record] if any(value is not None for key, value in record.items() if key.endswith("_vnd")) else []


def parse_scholarship(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    fund_match = re.search(r"tổng giá trị lên đến\s+(\d+)\s*tỷ đồng", text, re.IGNORECASE)
    if fund_match:
        records.append(
            {
                "record_type": "scholarship_fund",
                "record_id": "scholarship_fund",
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
    policy_markers = (
        "học bổng",
        "hỗ trợ học phí",
        "hỗ trợ "
    )
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            folded_line = line.casefold()
            if any(marker in folded_line for marker in policy_markers) and (
                "%" in line or "triệu" in folded_line or "tỷ" in folded_line or "học phí" in folded_line
            ):
                records.append(
                    {
                        "record_type": "scholarship_policy",
                        "record_id": f"scholarship_policy_{len(records) + 1:03d}",
                        "policy_text": line[2:].strip() if line.startswith("• ") else line.strip(),
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
                "record_id": "scholarship_summary",
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
    "cach_tinh_diem": "Cách tính điểm xét tuyển DHV",
    "co_so_lien_he": "Cơ sở và liên hệ tuyển sinh DHV",
    "dang_ky_xet_tuyen": "Cổng đăng ký xét tuyển DHV",
    "diem_trung_tuyen": "Điểm trúng tuyển DHV",
    "ho_so": "Hồ sơ nhập học DHV",
    "hoc_bong": "Học bổng DHV",
    "hoc_phi": "Học phí DHV",
    "lich_tuyen_sinh": "Lịch tuyển sinh DHV",
    "nganh_dao_tao": "Ngành đào tạo DHV",
    "nguong_dau_vao": "Điểm sàn DHV",
    "nhap_hoc": "Nhập học DHV",
    "phuong_thuc_xet_tuyen": "Phương thức xét tuyển DHV",
    "thong_tin_truong": "Thông tin trường DHV",
    "xet_tuyen_bo_sung": "Xét tuyển bổ sung DHV",
}


def _category_label(category: str, year: int) -> str:
    return f"{_CATEGORY_LABELS.get(category, category)} {year}"


def parse_official_websites(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    records: list[dict[str, Any]] = []
    for url in _source_urls(text):
        # Social/video links may be present in a school-information PDF, but
        # only DHV-owned HTTPS URLs are promoted to provenance records.
        # ``extracted_links`` still preserves every link found in the text.
        if not is_official_dhv_url(url):
            continue
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


def parse_school_information(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse structured school background, leadership, campuses and partnerships.

    Emits fine-grained semantic records for the school-information corpus
    without losing provenance or official website records.
    """
    records: list[dict[str, Any]] = parse_official_websites(pages)
    combined_text = "\n".join(str(page.get("text", "")) for page in pages)

    p1_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 1), "")
    p2_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 2), "")
    p3_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 3), "")
    p4_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 4), "")
    p5_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 5), "")
    p6_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 6), "")
    p7_text = next((str(p.get("text", "")) for p in pages if int(p.get("page", 0)) == 7), "")

    # 1.1 Tổng quan về trường
    if "TỔNG QUAN VỀ TRƯỜNG" in p1_text or "TỔNG QUAN VỀ TRƯỜNG" in combined_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_overview",
                "topic": "tong_quan",
                "page": 1,
                "information_text": (
                    "Tổng quan về Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh là một trong những trường đại học lâu năm "
                    "tại Thành phố lớn nhất nước. Với sứ mệnh đào tạo và phát triển nguồn nhân lực cho xã hội, "
                    "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh tự hào là nơi đào tạo các thế hệ sinh viên "
                    "trở thành người có Trách nhiệm, Trung Nghĩa và Tự tin trong cuộc sống.\n"
                    "Chương trình đào tạo là sự kết hợp một số nguyên tắc và giá trị cốt lõi của giáo dục Việt Nam "
                    "cũng như những nền giáo dục tiên tiến trên thế giới như Mỹ: tập trung phát triển nhân cách và đạo đức "
                    "của sinh viên cũng như nhấn mạnh việc phát triển kỹ năng, tư duy sáng tạo, khả năng tự học và khả năng "
                    "giải quyết vấn đề của sinh viên nhằm tạo ra một thế hệ công dân có trách nhiệm với xã hội."
                ),
            }
        )

    # 1.2 - 1.5 Triết lý giáo dục
    if "Triết lý giáo dục" in p1_text or "GIÁO DỤC - KHAI PHÓNG - KHỞI NGHIỆP" in p1_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "educational_philosophy",
                "topic": "triet_ly_giao_duc",
                "page": 1,
                "information_text": (
                    "Triết lý giáo dục của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "Nền tảng của triết lý giáo dục này là 6 chữ \"GIÁO DỤC - KHAI PHÓNG - KHỞI NGHIỆP\", "
                    "mục tiêu của triết lý này là \"vươn mình - phát triển - thành công\".\n"
                    "• Giáo dục để vươn mình: DHV coi sứ mệnh của giáo dục là thay đổi vận mệnh của đất nước, "
                    "vận mệnh của dân tộc, vận mệnh của mỗi người. Để có thể thay đổi vận mệnh, nền giáo dục phải "
                    "mang tính toàn diện và là một quá trình học tập suốt đời.\n"
                    "• Khai phóng để phát triển: Để thực hiện được sứ mệnh vươn mình, giáo dục DHV không giới hạn "
                    "ở việc truyền thụ kiến thức, mà phải giúp khai mở tư duy, rèn luyện năng lực phản biện để có thể "
                    "sáng tạo không ngừng.\n"
                    "• Khởi nghiệp để thành công: Không dừng lại ở chữ nghĩa lý thuyết, giáo dục DHV dẫn người học đến hành động. "
                    "Chỉ có hành động sáng tạo không ngừng mới có thể đưa người học đến thành công, đưa đất nước đến phát triển, "
                    "đưa dân tộc đến vươn mình."
                ),
            }
        )

    # Tầm nhìn & Kiểm định
    if "Đại học khởi nghiệp hàng đầu châu Á" in p1_text or "Tầm nhìn" in p1_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_vision",
                "topic": "tam_nhin",
                "page": 1,
                "information_text": (
                    "Tầm nhìn của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "Đại học khởi nghiệp hàng đầu châu Á. DHV trở thành trường đại học định hướng ứng dụng theo mô hình "
                    "đại học khởi nghiệp hàng đầu Việt Nam và khu vực Châu Á.\n"
                    "Chương trình đạt kiểm định quốc tế: Một số ngành hoặc chuyên ngành được kiểm định và xếp hạng "
                    "bởi các tổ chức kiểm định và đánh giá chất lượng giáo dục uy tín trên thế giới."
                ),
            }
        )

    # 1.7 Sứ mệnh
    if "1.7. Sứ mệnh" in p2_text or "Sứ mệnh" in p2_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_mission",
                "topic": "su_menh",
                "page": 2,
                "information_text": (
                    "Sứ mệnh của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "• Cộng đồng học thuật đa ngành: Xây dựng một cộng đồng học thuật đa văn hóa, đa ngành, phát huy tối đa "
                    "sự giao tiếp và hợp tác đa chiều giữa sinh viên, giảng viên, doanh nghiệp và xã hội.\n"
                    "• Phát triển tư duy và kỹ năng: Khuyến khích khả năng sáng tạo, tư duy độc lập, tư duy phản biện "
                    "cùng các kỹ năng của giảng viên và sinh viên.\n"
                    "• Nghiên cứu và đổi mới sáng tạo: Nghiên cứu và phát triển các công nghệ, phương pháp và ứng dụng mới "
                    "trong các lĩnh vực như học thuật, công nghệ, kinh doanh…\n"
                    "• Góp phần phát triển xã hội: Góp phần vào sự phát triển và cải thiện xã hội thông qua các giải pháp như "
                    "cung cấp nguồn nhân lực chất lượng cao, các phương pháp và ứng dụng mới trong các lĩnh vực của nền kinh tế."
                ),
            }
        )

    # 1.8 Giá trị cốt lõi
    if "1.8. Giá trị cốt lõi" in p2_text or "Giá trị cốt lõi" in p2_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "core_values",
                "topic": "gia_tri_cot_loi",
                "page": 2,
                "information_text": (
                    "Giá trị cốt lõi của Trường Đại học Hùng Vương TP.HCM (DHV) gồm 3 giá trị:\n"
                    "a. Trách nhiệm (Faithful): Mọi thành viên DHV đều xác định đảm nhận trách nhiệm và chịu trách nhiệm "
                    "với hành động hoặc nhiệm vụ mình được giao, với xã hội.\n"
                    "b. Trung nghĩa (Confident): Thể hiện sự trung thành, tin cậy và kiên định dựa trên tính công bằng, "
                    "khách quan và sự tôn trọng đối với tất cả quan điểm.\n"
                    "c. Tự tin (Responsible): Thể hiện sự tự tin vào khả năng của bản thân, sẵn sàng đối mặt với thách thức, "
                    "dám đưa ra các ý kiến phản biện mang tính chất xây dựng và bảo vệ quan điểm của mình dù có thể "
                    "đi ngược với quan điểm số đông."
                ),
            }
        )

    # 1.9 Lịch sử hình thành
    if "LỊCH SỬ HÌNH THÀNH" in p2_text or "2395/QĐ-TCCB" in combined_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_history",
                "topic": "lich_su_hinh_thanh",
                "page": 2,
                "source_pages": [2, 3],
                "information_text": (
                    "Lịch sử hình thành và phát triển của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "• Ngày 03/11/1993: Bộ Giáo dục và Đào tạo ra quyết định số 2395/QĐ-TCCB chính thức công nhận "
                    "Hội đồng Sáng lập Trường Đại học Dân lập Hùng Vương Thành phố Hồ Chí Minh gồm 9 thành viên, trong đó "
                    "cố Giáo sư, Thạc sĩ Y khoa Ngô Gia Hy giữ vai trò Chủ tịch. Đây là cột mốc đầu tiên, đánh dấu "
                    "sự ra đời của ngôi trường mang tên Quốc tổ Vua Hùng.\n"
                    "• Ngày 14/08/1995: Thủ tướng Chính phủ ký quyết định số 470-TTg cho phép thành lập Trường Đại học Dân lập "
                    "Hùng Vương Thành phố Hồ Chí Minh. Trong giai đoạn này, Trường xây dựng tôn chỉ: 'Khoa học – Phát triển – Đạo đức' "
                    "với phương châm: Chất lượng hàng đầu, không chạy theo số lượng, không vụ lợi cá nhân, trong sáng về tài chính.\n"
                    "• Ngày 09/03/1996 (âm lịch): Logo đầu tiên của Trường chính thức ra mắt vào Ngày truyền thống lần thứ nhất "
                    "ngày 9/3/1996 (âm lịch).\n"
                    "• Ngày 14/05/2008: Bộ trưởng Bộ Giáo dục và Đào tạo ban hành văn bản số 4167/BGDĐT-PC cho phép "
                    "Trường Đại học Dân lập Hùng Vương đổi tên thành Trường Đại học Hùng Vương Thành phố Hồ Chí Minh."
                ),
            }
        )

    # Logo, Tên trường & Ngày truyền thống
    if "Logo đầu tiên" in p3_text or "Ý nghĩa tên trường" in p3_text or "Ngày truyền thống của Trường" in p4_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_logo_and_tradition",
                "topic": "ngay_truyen_thong_va_logo",
                "page": 3,
                "source_pages": [3, 4],
                "information_text": (
                    "Ý nghĩa Tên trường, Biểu tượng Logo và Ngày truyền thống DHV:\n"
                    "• Ngày truyền thống của Trường: Hằng năm lấy ngày 9 tháng 3 âm lịch (ngày tiên thường Giỗ Quốc tổ Hùng Vương) "
                    "làm Ngày truyền thống của Trường. Tượng Vua Hùng được xây dựng tại cơ sở chính 736 Nguyễn Trãi, Quận 5, TP. Hồ Chí Minh.\n"
                    "• Ý nghĩa tên trường Đại học Hùng Vương TP.HCM: Với tên gọi Hùng Vương, tất cả thành viên của Trường đều "
                    "luôn nhắc nhở bản thân gìn giữ và phát huy các truyền thống quý báu từ thời đại Hùng Vương, từ nền văn hóa Văn Lang:\n"
                    "  - Truyền thống đoàn kết và yêu thương giữa các dân tộc (liên minh hòa bình 15 bộ lạc dựng xây nước Văn Lang);\n"
                    "  - Truyền thống xem tất cả người dân Việt Nam như anh em ruột thịt (truyền thuyết Âu Cơ cùng một mẹ);\n"
                    "  - Truyền thống đoàn kết đối phó với thiên tai và bảo vệ cuộc sống (chuyện Sơn Tinh - Thủy Tinh);\n"
                    "  - Truyền thống kiên cường vượt qua khó khăn để bảo vệ Tổ quốc (hình tượng Thánh Gióng vươn lên đánh bại giặc).\n"
                    "• Ý nghĩa biểu tượng Logo: Chiếc vạc ba chân ở trung tâm tượng trưng cho tam tài: thiên, địa, nhân. "
                    "Sự kết hợp giữa hình vuông và hình tròn gợi nhắc bánh chưng và bánh dày (đất và trời, cha và mẹ, âm và dương, "
                    "triết lý 'vuông tròn'). 18 đường gạch ở giữa biểu trưng cho 18 đời Vua Hùng; 5 cột khói tượng trưng cho ngũ hành "
                    "quyện thành hình Rồng, Tiên và bản đồ Việt Nam. Hai ngôi sao 15 cánh đại diện cho 15 bộ lạc của nước Văn Lang xưa. "
                    "Màu xanh biểu trưng cho tuổi trẻ và tương lai, màu trắng là sự tổng hòa của mọi sức mạnh và tinh hoa kết nối thế giới. "
                    "Link xem logo: https://drive.google.com/file/d/1sjemgqjD_cAm7i-gMIOG2w_o-YD81lgx/view?usp=drive_link"
                ),
            }
        )

    # 1.10 Cơ cấu tổ chức & Lãnh đạo
    if "CƠ CẤU TỔ CHỨC" in p4_text or "Đặng Thành Tâm" in p4_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_leadership",
                "topic": "lanh_dao_va_to_chuc",
                "page": 4,
                "source_pages": [4, 5],
                "information_text": (
                    "Cơ cấu tổ chức và Lãnh đạo Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "Cơ cấu tổ chức gồm: Hội đồng trường, Hội đồng khoa học và đào tạo, Ban Giám hiệu, Các khoa/viện đào tạo, "
                    "Các phòng/ban và đơn vị trực thuộc.\n"
                    "1. Hội đồng trường:\n"
                    "• Kỹ sư Đặng Thành Tâm – Chủ tịch Hội đồng Trường.\n"
                    "• TS. Trần Việt Anh – Phó Chủ tịch Thường trực Hội đồng Trường, Phó Hiệu trưởng Phụ trách, Chủ tịch Hội đồng Khoa học và Đào tạo.\n"
                    "• Kỹ sư Trương Hạ Long – Phó Chủ tịch Hội đồng Trường.\n"
                    "2. Hội đồng khoa học & đào tạo: TS. Trần Việt Anh – Chủ tịch Hội đồng Khoa học và Đào tạo.\n"
                    "3. Ban Giám hiệu:\n"
                    "• TS. Trần Việt Anh – Phó Chủ tịch Thường trực Hội đồng Trường, Phó Hiệu trưởng Phụ trách, Chủ tịch Hội đồng Khoa học và Đào tạo.\n"
                    "• PGS.TS. Trần Văn Hưng – Phó Hiệu trưởng, Ủy viên Hội đồng Khoa học và Đào tạo.\n"
                    "• TS. Lương Thị Hòa – Phó Hiệu trưởng, Trưởng khoa Luật (Tiến sĩ Luật Hành chính – Hiến pháp, hơn 10 năm cống hiến cho ngành giáo dục).\n"
                    "4. Lãnh đạo Khoa/Viện tiêu biểu:\n"
                    "• TS. Nguyễn Quang Hiếu – Trưởng khoa Ngôn ngữ (hơn 25 năm kinh nghiệm giảng dạy và quản lý các trung tâm/học viện/trường đào tạo Ngôn ngữ Anh).\n"
                    "• TS. Nguyễn Văn Dũng – Trưởng khoa Kỹ thuật – Công nghệ, Ủy viên Hội đồng Khoa học và Đào tạo.\n"
                    "• TS. Lương Thị Hoà – Phó Hiệu trưởng, Trưởng khoa Luật."
                ),
            }
        )

    # 1.11.1 Hợp tác quốc tế
    if "HỢP TÁC – ĐỐI TÁC" in p5_text or "Đại học Khai Nam" in p5_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "international_partnerships",
                "topic": "doi_tac_quoc_te",
                "page": 5,
                "source_pages": [5, 6],
                "information_text": (
                    "Hợp tác quốc tế của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "DHV triển khai các hoạt động hợp tác quốc tế trong đào tạo, trao đổi sinh viên, trao đổi giảng viên, "
                    "học thuật và chương trình liên kết. Các đối tác và hoạt động tiêu biểu gồm:\n"
                    "• Trường Đại học Khai Nam – Đài Loan: hợp tác trao đổi sinh viên, chuyển đổi tín chỉ, trao đổi giảng viên "
                    "và phát triển học bổng. Năm 2026, hai trường ký thỏa thuận thành lập Trung tâm Hợp tác và Quan hệ quốc tế.\n"
                    "• Trường Đại học Chosun – Hàn Quốc: ký Biên bản Ghi nhớ hợp tác (MOU) với DHV vào tháng 01/2026.\n"
                    "• Trường Đại học Hyogo – Nhật Bản: DHV tiếp đón và trao đổi các cơ hội hợp tác quốc tế vào cuối năm 2025.\n"
                    "• Glenn College – Canada: hợp tác nhằm mở rộng cơ hội tiếp cận giáo dục quốc tế và nâng cao chất lượng đào tạo cho sinh viên.\n"
                    "• Chivast Education – Trung Quốc: hợp tác trong lĩnh vực giáo dục quốc tế.\n"
                    "• StudyDIY: hợp tác xây dựng các chương trình thực hành, học tập trải nghiệm và làm việc tại Đài Loan hoặc Việt Nam.\n"
                    "• DAISO INDUSTRIES Co., Ltd. – Nhật Bản: trao đổi về chương trình thực tập sinh tại Nhật Bản kéo dài 6 tháng hoặc 1 năm dành cho sinh viên DHV."
                ),
            }
        )

    # 1.11.2 - 1.11.3 Hợp tác doanh nghiệp và mục tiêu
    if "Hợp tác doanh nghiệp" in p6_text or "Fleur De Lys" in p6_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "business_partnerships",
                "topic": "doi_tac_doanh_nghiep",
                "page": 6,
                "information_text": (
                    "Hợp tác doanh nghiệp và kết nối nghề nghiệp tại DHV:\n"
                    "Các khoa của DHV hợp tác chặt chẽ với doanh nghiệp và tổ chức chuyên môn nhằm tạo điều kiện cho sinh viên kiến tập, thực hành, thực tập và tìm việc làm:\n"
                    "• Khoa Du lịch – Nhà hàng – Khách sạn hợp tác với các doanh nghiệp: Chuỗi khách sạn Fleur De Lys, Kỳ Hòa Tourist, Khách sạn InterContinental, "
                    "Khách sạn Đệ Nhất, Vietravel, Chợ Lớn Tourist, Khách sạn Mai House Sài Gòn, Trung tâm Hội nghị & Tiệc cưới Metropole "
                    "cùng nhiều doanh nghiệp trong lĩnh vực du lịch, khách sạn và sự kiện.\n"
                    "• Khoa Ngôn ngữ có các đối tác thuộc lĩnh vực giáo dục, thương mại, tài chính và đào tạo: Glenn College, Woori Bank, Ngân hàng Quân đội (MB), "
                    "Tập đoàn Giáo dục Đại Trường Phát, AECC Global Việt Nam, Cengage Learning Asia, IMAP Việt Nam và nhiều đơn vị khác.\n"
                    "• Khoa Quản trị Kinh doanh – Marketing tăng cường kết nối với doanh nghiệp để sinh viên được kiến tập, thực hành, trải nghiệm thực tế, tiếp cận việc làm và hỗ trợ khởi nghiệp.\n"
                    "• Khoa Luật hợp tác với trung tâm trợ giúp pháp lý, công ty luật, văn phòng luật sư, văn phòng công chứng, trọng tài thương mại, tòa án và viện kiểm sát "
                    "nhằm hỗ trợ sinh viên kiến tập, thực hành nghề nghiệp và thực tập tốt nghiệp.\n"
                    "• Mục tiêu hợp tác: Tạo cơ hội thực tập và trải nghiệm thực tế cho sinh viên; tăng cường kết nối với doanh nghiệp; hỗ trợ việc làm sau tốt nghiệp; "
                    "phát triển chương trình đào tạo gắn với thực tiễn; mở rộng chương trình trao đổi sinh viên và giảng viên; tạo cơ hội học tập và trải nghiệm quốc tế; "
                    "nâng cao năng lực ngoại ngữ, kỹ năng mềm và kỹ năng nghề nghiệp cho sinh viên."
                ),
            }
        )

    # 1.11.4 Cơ sở đào tạo & Kênh liên hệ
    if "Các cơ sở của trường" in p7_text or "194 Lê Đức Thọ" in p7_text:
        records.append(
            {
                "record_type": "school_information",
                "record_id": "campus_locations",
                "fact_category": "co_so_lien_he",
                "topic": "co_so_dao_tao",
                "page": 7,
                "information_text": (
                    "Các cơ sở đào tạo của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
                    "• Cơ sở 1: 194 Lê Đức Thọ, Phường An Nhơn, Thành phố Hồ Chí Minh\n"
                    "• Cơ sở 2 (Cơ sở chính có tượng Vua Hùng): 736 Nguyễn Trãi, Phường Chợ Lớn, Thành phố Hồ Chí Minh (Quận 5)\n"
                    "• Cơ sở 3: 37 Kinh Dương Vương, Phường Phú Lâm, Thành phố Hồ Chí Minh\n"
                    "• Cơ sở 4 (Cơ sở thực hành, nghiên cứu): Công viên Phần mềm Quang Trung, Phường Trung Mỹ Tây, Thành phố Hồ Chí Minh"
                ),
            }
        )
        records.append(
            {
                "record_type": "school_information",
                "record_id": "school_contacts",
                "fact_category": "co_so_lien_he",
                "topic": "thong_tin_lien_he",
                "page": 7,
                "information_text": (
                    "Thông tin liên hệ và các kênh thông tin chính thức của DHV:\n"
                    "• Tổng đài tư vấn tuyển sinh: 0287 1000 888\n"
                    "• Email chính thức: info@dhv.edu.vn, media@dhv.edu.vn\n"
                    "• Cổng thông tin tuyển sinh chính thức: https://tuyensinh.dhv.edu.vn/\n"
                    "• Website chính thức: https://dhv.edu.vn/\n"
                    "• Kênh TikTok chính thức: https://www.tiktok.com/@dhv.official\n"
                    "• Kênh Zalo chính thức: https://zalo.me/1822829687649866202\n"
                    "• Kênh YouTube chính thức: https://www.youtube.com/@hungvuonguni\n"
                    "• Trang Facebook chính thức: https://www.facebook.com/hungvuonguni"
                ),
            }
        )
        # Đồng thời tạo các bản ghi liên hệ cụ thể có fact_category=co_so_lien_he
        campus_items = (
            ("Cơ sở 1", "194 Lê Đức Thọ, Phường An Nhơn, Thành phố Hồ Chí Minh"),
            ("Cơ sở 2 (Cơ sở chính)", "736 Nguyễn Trãi, Phường Chợ Lớn, Thành phố Hồ Chí Minh"),
            ("Cơ sở 3", "37 Kinh Dương Vương, Phường Phú Lâm, Thành phố Hồ Chí Minh"),
            ("Cơ sở 4 (Cơ sở thực hành, nghiên cứu)", "Công viên Phần mềm Quang Trung, Phường Trung Mỹ Tây, Thành phố Hồ Chí Minh"),
        )
        for idx, (label, val) in enumerate(campus_items, start=1):
            records.append(
                {
                    "record_type": "contact",
                    "record_id": f"contact_campus_{idx:02d}",
                    "fact_category": "co_so_lien_he",
                    "contact_type": "address",
                    "label": label,
                    "value": val,
                    "page": 7,
                }
            )
        records.append(
            {
                "record_type": "contact",
                "record_id": "contact_hotline_01",
                "fact_category": "co_so_lien_he",
                "contact_type": "hotline",
                "label": "Tổng đài tư vấn tuyển sinh",
                "value": "0287 1000 888",
                "page": 7,
            }
        )
        records.append(
            {
                "record_type": "contact",
                "record_id": "contact_email_01",
                "fact_category": "co_so_lien_he",
                "contact_type": "email",
                "label": "Email tuyển sinh và truyền thông",
                "value": "info@dhv.edu.vn, media@dhv.edu.vn",
                "page": 7,
            }
        )

    return records


def parse_score_formulas(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    method = ""
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            if line.casefold() in {"học bạ", "thi tốt nghiệp thpt"}:
                method = "hoc_ba" if line.casefold() == "học bạ" else "thpt"
            if line.startswith("• ") and (
                "Điểm xét tuyển" in line
                or "Xét theo tổ hợp" in line
                or "Xét theo" in line
            ):
                records.append(
                    {
                        "record_type": "score_formula",
                        "record_id": f"score_formula_{len(records) + 1:03d}",
                        "fact_category": "cach_tinh_diem",
                        "score_type": "score_formula",
                        "method": method or None,
                        "formula_text": line[2:].strip(),
                        "page": int(page["page"]),
                    }
                )
    return records


def parse_admission_methods(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    fallback_patterns = (
        ("thpt", re.compile(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*Xét kết quả kỳ thi tốt nghiệp THPT", re.IGNORECASE)),
        ("hoc_ba", re.compile(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*Xét (?:tuyển )?(?:kết quả )?học tập THPT", re.IGNORECASE)),
        ("h_sca", re.compile(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*Xét kết quả (?:bài thi|kỳ thi) Đánh giá năng lực chuyên biệt", re.IGNORECASE)),
        ("dgnl", re.compile(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*Xét kết quả kỳ thi Đánh giá năng lực", re.IGNORECASE)),
        ("trung_cap", re.compile(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*Xét tuyển đối với thí sinh tốt nghiệp trung cấp", re.IGNORECASE)),
    )
    for page in pages:
        for line in _nonempty_lines(str(page.get("text", ""))):
            match = re.match(r"^•?\s*Phương thức\s*(\d+)\s*:\s*(.*)$", line, re.IGNORECASE)
            if match:
                records.append(
                    {
                        "record_type": "admission_method",
                        "record_id": f"admission_method_{match.group(1)}",
                        "fact_category": "phuong_thuc_xet_tuyen",
                        "method_number": int(match.group(1)),
                        "method_text": match.group(2).strip(),
                        "page": int(page["page"]),
                    }
                )
                continue
            for method, pattern in fallback_patterns:
                if pattern.search(line):
                    method_text = re.sub(r"^(?:(?:[a-z]\.)|(?:\d+(?:\.\d+)*\.?))\s*", "", line, flags=re.IGNORECASE)
                    records.append(
                        {
                            "record_type": "admission_method",
                            "record_id": f"admission_method_{len(records) + 1:03d}",
                            "fact_category": "phuong_thuc_xet_tuyen",
                            "method_number": len(records) + 1,
                            "method": method,
                            "method_text": method_text.strip(),
                            "page": int(page["page"]),
                        }
                    )
                    break
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
        elements = page.get("elements")
        if isinstance(elements, list):
            in_document_section = False
            for element in elements:
                if not isinstance(element, Mapping):
                    continue
                line = _single_line(element.get("text", ""))
                if not line:
                    continue
                numbered_heading = bool(re.match(r"^\d+(?:\.\d+)+\s+", line))
                folded = _fold_label(line)
                if numbered_heading and "ho so" in folded and "nhap hoc" in folded:
                    in_document_section = True
                    continue
                if in_document_section and numbered_heading:
                    in_document_section = False
                if in_document_section and element.get("type") == "list_item":
                    records.append(
                        {
                            "record_type": "enrollment_document",
                            "record_id": f"enrollment_document_{len(records) + 1:03d}",
                            "document_name": line,
                            "page": int(page["page"]),
                        }
                    )
            continue

        # Compatibility fallback for older page models without layout elements:
        # only treat bullets in the numbered enrollment-document section as
        # required documents.
        in_document_section = False
        for line in _nonempty_lines(str(page.get("text", ""))):
            numbered_heading = bool(re.match(r"^\d+(?:\.\d+)+\s+", line))
            folded = _fold_label(line)
            if numbered_heading and "ho so" in folded and "nhap hoc" in folded:
                in_document_section = True
                continue
            if in_document_section and numbered_heading:
                in_document_section = False
            if in_document_section and line.startswith("• "):
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
            if not re.search(r"\d{1,2}/\d{1,2}/\d{4}", line):
                continue
            if not line.startswith("• ") and not re.search(r"(?:hạn|thời gian|đến hết|đăng ký)", line, re.IGNORECASE):
                continue
            dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", line)
            records.append(
                {
                    "record_type": "deadline",
                    "record_id": f"deadline_{len(records) + 1:03d}",
                    "fact_category": "lich_tuyen_sinh",
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
                "record_id": "supplementary_quota",
                "fact_category": "xet_tuyen_bo_sung",
                "quota": int(quota.group(1)),
                "program_count": int(quota.group(2)),
                "page": 1,
            }
        )
    compact_text = re.sub(r"\s+", " ", text).strip()
    threshold_line = "phần lớn chương trình nhận hồ sơ"
    if threshold_line in compact_text.casefold():
        records.append(
            {
                "record_type": "supplementary_threshold",
                "record_id": "supplementary_threshold_thpt_general",
                "fact_category": "xet_tuyen_bo_sung",
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
                    "fact_category": "xet_tuyen_bo_sung",
                    "score_type": "supplementary_threshold",
                    "method": "thpt",
                    "major_name": major_name,
                    "value": 20,
                    "raw_value": "20",
                    "page": 1,
                }
            )
    if "học tập trung học phổ thông" in compact_text.casefold() and re.search(r"phần lớn chương trình từ 18", compact_text, re.IGNORECASE):
        records.append(
            {
                "record_type": "supplementary_threshold",
                "record_id": "supplementary_threshold_hoc_ba_general",
                "fact_category": "xet_tuyen_bo_sung",
                "score_type": "supplementary_threshold",
                "method": "hoc_ba",
                "scope": "most_programs",
                "value": 18,
                "raw_value": "18",
                "page": 1,
            }
        )
    for page in pages:
        lines = _nonempty_lines(str(page.get("text", "")))
        rows: list[str] = []
        current: list[str] = []
        for line in lines:
            if re.match(r"^\d+\s+\d{7,9}\s+", line):
                if current:
                    rows.append(" ".join(current))
                current = [line]
            elif current:
                current.append(line)
        if current:
            rows.append(" ".join(current))
        row_pattern = re.compile(
            r"^\d+\s+(?P<code>\d{7,9})\s+(?P<major>.+?)\s+"
            r"(?P<quota>\d+)\s+(?P<thpt>\d+(?:[.,]\d+)?)\s+"
            r"(?P<hoc_ba>\d+(?:[.,]\d+)?)(?:\(\*\))?$",
            re.IGNORECASE,
        )
        for row in rows:
            match = row_pattern.match(row)
            if not match:
                continue
            for method in ("thpt", "hoc_ba"):
                raw_value = match.group(method)
                records.append(
                    {
                        "record_type": "supplementary_threshold",
                        "record_id": f"supplementary_threshold_{len(records) + 1:03d}",
                        "fact_category": "xet_tuyen_bo_sung",
                        "score_type": "supplementary_threshold",
                        "method": method,
                        "major_name": match.group("major").strip(" •*-"),
                        "major_code": match.group("code"),
                        "quota": int(match.group("quota")),
                        "value": _value_or_raw(raw_value),
                        "raw_value": raw_value,
                        "page": int(page["page"]),
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
    "thong_tin_truong": parse_school_information,
    "xet_tuyen_bo_sung": parse_supplementary,
}


def _parse_category_records(category: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Use the final layout-preserving page text for prose parsers and the
    # ordered table cells for structured facts. ``semantic_text`` remains in
    # the JSON for audit, but must not override table/page reading order.
    parser = PARSERS.get(category)
    parser_pages = pages
    semantic_pages = [
        {**page, "text": str(page.get("semantic_text") or page.get("text", ""))}
        for page in pages
    ]
    records = list(parser(parser_pages)) if parser is not None else parse_deadlines_and_policies(parser_pages)
    if category == "xet_tuyen_bo_sung" and parser is not None:
        # The compact pypdf view may recover a prose threshold whose line
        # wrapping differs from PyMuPDF. Merge only those threshold facts and
        # deduplicate by semantic identity; table records stay page-layout-led.
        compact_records = [
            record
            for record in parser(semantic_pages)
            if record.get("record_type") == "supplementary_threshold"
        ]
        existing_keys = {
            (
                record.get("record_type"),
                record.get("method"),
                record.get("major_name"),
                record.get("value"),
            )
            for record in records
            if record.get("record_type") == "supplementary_threshold"
        }
        for record in compact_records:
            key = (record.get("record_type"), record.get("method"), record.get("major_name"), record.get("value"))
            if key not in existing_keys:
                records.append(record)
                existing_keys.add(key)

    if category == "xet_tuyen_bo_sung":
        # The supplementary source owns its submission deadline.  Keep that
        # deadline queryable with the supplementary topic while retaining the
        # cross-domain provenance for the calendar facet.
        for record in records:
            if record.get("record_type") == "deadline":
                record.setdefault("source_fact_category", "lich_tuyen_sinh")
                record["fact_category"] = "xet_tuyen_bo_sung"

    def extend_as(fact_category: str, parsed: Iterable[Mapping[str, Any]]) -> None:
        for value in parsed:
            record = dict(value)
            record.setdefault("fact_category", fact_category)
            records.append(record)

    # Official DHV PDFs are often multi-topic documents.  Their manifest
    # category remains the document's primary purpose, while deterministic
    # facts are emitted under their domain category for retrieval.  This keeps
    # ``phuong_thuc_xet_tuyen`` and ``ho_so`` provenance intact without hiding
    # catalog, threshold, or tuition facts that are explicitly present in the
    # same verified source.
    if category != "nganh_dao_tao":
        records.extend(parse_major_catalog(parser_pages, include_thresholds=False))
    if category != "nguong_dau_vao":
        records.extend(parse_application_thresholds(parser_pages))
    if category != "hoc_phi":
        records.extend(parse_tuition(parser_pages))
    if category not in {"diem_trung_tuyen", "xet_tuyen_bo_sung"}:
        records.extend(parse_admission_scores(parser_pages))
    if category != "hoc_bong":
        extend_as("hoc_bong", parse_scholarship(parser_pages))
    if category != "cach_tinh_diem":
        extend_as("cach_tinh_diem", parse_score_formulas(parser_pages))
    if category not in {"lich_tuyen_sinh", "xet_tuyen_bo_sung"}:
        extend_as("lich_tuyen_sinh", parse_deadlines(parser_pages))
    if category != "phuong_thuc_xet_tuyen":
        extend_as("phuong_thuc_xet_tuyen", parse_admission_methods(parser_pages))

    # The official source states a general THPT minimum and a general ĐGNL
    # minimum, then names Law/Law Economics as exceptions.  Materialize the
    # general rule against the catalog rows so entity-filtered retrieval can
    # answer a named-major query without changing the score semantic type.
    catalog_rows = [
        record
        for record in records
        if record.get("record_type") == "major"
        and record.get("fact_category") == "nganh_dao_tao"
    ]
    generic_thresholds = [
        record
        for record in records
        if record.get("record_type") == "application_threshold"
        and record.get("fact_category") == "nguong_dau_vao"
        and not record.get("major_name")
        and record.get("method") in {"thpt", "dgnl"}
    ]
    for threshold in generic_thresholds:
        for major in catalog_rows:
            major_name = str(major.get("major_name") or "")
            if major_name.casefold() in {"luật", "luật kinh tế"}:
                continue
            expanded = dict(threshold)
            expanded.update(
                {
                    "record_id": f"{threshold.get('record_id')}_{major.get('major_code')}",
                    "major_name": major_name,
                    "major_code": major.get("major_code"),
                    "scope": "general_rule_from_source",
                }
            )
            records.append(expanded)

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
    extraction_method: str = "native_pdf",
    warnings: Iterable[Mapping[str, Any]] = (),
    manifest_entry: Mapping[str, Any] | None = None,
    source_page_count: int | None = None,
) -> dict[str, Any]:
    """Build one JSON-serialisable structured document from extracted pages."""

    raw_file_path = Path(raw_path).resolve()
    raw_root_path = Path(raw_root).resolve()
    page_values: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page_number", page["page"]))
        page_warnings = [dict(item) for item in page.get("warnings", []) if isinstance(item, Mapping)]
        normalized_tables, normalized_elements = _normalize_page_tables(page)
        page_values.append(
            {
                # ``page`` remains for compatibility with existing records;
                # ``page_number`` is the explicit page-content contract.
                "page": page_number,
                "page_number": page_number,
                "page_bbox": [float(value) for value in (page.get("page_bbox") or [])],
                "text": _clean_text(str(page.get("text", ""))),
                "semantic_text": _clean_text(str(page.get("semantic_text", ""))),
                "native_text": _clean_text(str(page.get("native_text", ""))),
                "ocr_text": _clean_text(str(page.get("ocr_text", ""))),
                "native_blocks": [dict(item) for item in page.get("native_blocks", []) if isinstance(item, Mapping)],
                "native_words": [dict(item) for item in page.get("native_words", []) if isinstance(item, Mapping)],
                "ocr_boxes": [dict(item) for item in page.get("ocr_boxes", []) if isinstance(item, Mapping)],
                "ocr_lines": [dict(item) for item in page.get("ocr_lines", []) if isinstance(item, Mapping)],
                "elements": normalized_elements,
                "tables": normalized_tables,
                "lists": [dict(item) for item in page.get("lists", []) if isinstance(item, Mapping)],
                "warnings": page_warnings,
                "extraction_method": str(page.get("extraction_method") or extraction_method),
                "ocr_engine": str(page.get("ocr_engine") or ""),
            }
        )
    if not page_values:
        raise ValueError("PDF has no pages")
    combined_text = "\n\n".join(page["text"] for page in page_values if page["text"])
    metadata = dict(manifest_entry or {})
    title = str(metadata.get("title") or _title_from_text(combined_text)).strip()
    category = str(metadata.get("category") or raw_file_path.parent.relative_to(raw_root_path).as_posix())
    if not category or "/" in category:
        raise ValueError("RAW PDF must be directly below one category directory")
    year = metadata.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise ValueError(f"manifest year is required and must be an integer for {raw_file_path.name}")
    extracted_links = _source_urls(combined_text)
    source_urls = [str(url) for url in metadata.get("source_urls") or [] if str(url).strip()]
    source_url = str(metadata.get("source_url") or "").strip() or None
    if source_url and source_url not in source_urls:
        source_urls.insert(0, source_url)
    source_date = str(metadata.get("source_date") or metadata.get("date") or "").strip()
    collected_at = str(metadata.get("collected_at") or "").strip()
    document_id = str(metadata.get("document_id") or raw_file_path.stem)
    data_role = "description" if category == "nganh_dao_tao" and any(marker in document_id.casefold() for marker in ("mo_ta", "nghe_nghiep", "trien_vong", "gioi_thieu")) else ("catalog" if category == "nganh_dao_tao" else "")
    warning_values: list[dict[str, Any]] = [dict(value) for value in warnings]
    for page in page_values:
        warning_values.extend(dict(value) for value in page.get("warnings", []))
        if not page["text"]:
            warning_values.append(
                {
                    "type": "EMPTY_EXTRACTED_PAGE",
                    "page": page["page"],
                    "message": "Page has no extracted text; review the RAW PDF before indexing.",
                }
            )
    native_pages = sum(
        bool(str(page.get("native_text", "")).strip())
        or str(page.get("extraction_method")) in {"native", "native_pdf", "mixed"}
        for page in page_values
    )
    ocr_pages = sum(
        bool(str(page.get("ocr_text", "")).strip())
        or str(page.get("extraction_method")) in {"ocr", "mixed"}
        for page in page_values
    )
    mixed_pages = sum(str(page.get("extraction_method")) == "mixed" for page in page_values)
    methods = {str(page.get("extraction_method", extraction_method)) for page in page_values}
    has_ocr_only_page = "ocr" in methods
    has_native_only_page = bool(methods & {"native", "native_pdf"})
    # Supplemental OCR inside image regions does not turn an otherwise
    # native-text document into an OCR document.  ``mixed`` is reserved for a
    # document containing both native-only and OCR-only pages.
    extraction_name = "ocr" if methods and methods <= {"ocr"} else (
        "mixed" if has_ocr_only_page and has_native_only_page else "native"
    )
    raw_file = str(metadata.get("raw_file") or metadata.get("file") or "")
    if not raw_file:
        raw_file = raw_file_path.relative_to(Path.cwd()).as_posix() if raw_file_path.is_relative_to(Path.cwd()) else raw_file_path.as_posix()
    status = str(metadata.get("status") or metadata.get("verification_status") or "pending_review").strip().lower()
    verified = metadata.get("verified") is True and status == "verified"
    source_sha256 = _file_sha256(raw_file_path)
    records = _parse_category_records(category, page_values)
    content_audit = {
        "pages": len(page_values),
        "headings": sum(1 for page in page_values for element in page["elements"] if element.get("type") == "heading"),
        "paragraphs": sum(1 for page in page_values for element in page["elements"] if element.get("type") == "paragraph"),
        "elements": sum(len(page["elements"]) for page in page_values),
        "lists": sum(len(page["lists"]) for page in page_values),
        "list_items": sum(len(item.get("items", [])) for page in page_values for item in page["lists"]),
        "tables": sum(len(page["tables"]) for page in page_values),
        "rows": sum(len(table.get("rows", [])) for page in page_values for table in page["tables"]),
        "cells": sum(
            len(row.get("cells", []))
            for page in page_values
            for table in page["tables"]
            for row in table.get("rows", [])
        ),
        "native_chars": sum(len(page["native_text"]) for page in page_values),
        "ocr_chars": sum(len(page["ocr_text"]) for page in page_values),
        "final_chars": sum(len(page["text"]) for page in page_values),
        "native_blocks": sum(len(page["native_blocks"]) for page in page_values),
        "native_words": sum(len(page["native_words"]) for page in page_values),
        "ocr_boxes": sum(len(page["ocr_boxes"]) for page in page_values),
        "records": len(records),
        "warnings": len(warning_values),
    }
    structured = {
        "document_id": document_id,
        "title": title,
        "category": category,
        "year": year,
        "data_role": data_role,
        "source": {
            "file_name": raw_file_path.name,
            "raw_file": raw_file,
            "source_sha256": source_sha256,
            "source_url": source_url,
            "source_urls": source_urls,
            "organization": str(metadata.get("organization") or SCHOOL_NAME),
            "verified": verified,
            "status": status,
            "verification_status": status,
            "source_type": metadata.get("source_type", "unknown"),
            "source_date": source_date,
            "collected_at": collected_at,
            "school_code": "DHV",
        },
        "extraction": {
            "method": extraction_name,
            "text_source": "pypdf" if ocr_pages == 0 else ("ocr" if native_pages == 0 else "mixed"),
            "page_count": len(page_values),
            **({"source_page_count": source_page_count} if source_page_count is not None else {}),
            "native_pages": native_pages,
            "ocr_pages": ocr_pages,
            "mixed_pages": mixed_pages,
            "element_count": content_audit["elements"],
            "table_count": content_audit["tables"],
            "list_count": content_audit["lists"],
            "native_char_count": content_audit["native_chars"],
            "ocr_char_count": content_audit["ocr_chars"],
            "final_char_count": content_audit["final_chars"],
        },
        "content_audit": content_audit,
        "extracted_links": extracted_links,
        "pages": page_values,
        "sections": _page_sections(title, page_values),
        "records": records,
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

    for key in ("document_id", "title", "category", "year", "source", "pages", "sections", "records", "warnings"):
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
    for key in ("file_name", "organization", "verified", "status", "verification_status"):
        if key not in source:
            error(f"source.{key}", f"missing source field: {key}")
    if not str(source.get("raw_file", "")).strip():
        error("source.raw_file", "source raw_file is required for traceability")
    urls = list(source.get("source_urls") or [])
    if source.get("source_url") and source.get("source_url") not in urls:
        urls.insert(0, source["source_url"])
    if source.get("source_url") and not is_official_dhv_url(source.get("source_url")):
        error("source.source_url", "source URL must be an official DHV HTTPS URL on dhv.edu.vn or a subdomain")
    for index, url in enumerate(urls):
        if not is_official_dhv_url(url):
            error(f"source.source_urls[{index}]", "source URL must be an official DHV HTTPS URL on dhv.edu.vn or a subdomain")
    if source.get("status") == "verified":
        if source.get("verification_status") != "verified" or source.get("verified") is not True:
            error("source", "verified source must be explicitly verified")
        if not source.get("source_url"):
            error("source.source_url", "verified source requires source_url")
    elif source.get("verified") is True:
        error("source", "unverified source cannot set verified=true")

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
        page_number = page.get("page_number")
        if page_number is not None:
            if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
                error(f"pages[{index}].page_number", "page_number must be a positive integer")
            elif page_number != number:
                error(f"pages[{index}].page_number", "page_number must match page")
        if not isinstance(page.get("text"), str):
            error(f"pages[{index}].text", "page text must be a string")
        for text_key in ("native_text", "ocr_text"):
            if text_key in page and not isinstance(page.get(text_key), str):
                error(f"pages[{index}].{text_key}", f"{text_key} must be a string")
        for collection_key in ("elements", "tables", "lists", "native_blocks", "native_words", "ocr_boxes", "ocr_lines", "warnings"):
            if collection_key in page and not isinstance(page.get(collection_key), list):
                error(f"pages[{index}].{collection_key}", f"{collection_key} must be a list")
        if isinstance(page.get("elements"), list):
            for element_index, element in enumerate(page["elements"]):
                if not isinstance(element, Mapping) or not str(element.get("type", "")).strip():
                    error(f"pages[{index}].elements[{element_index}]", "element must have a type")
        if isinstance(page.get("tables"), list):
            for table_index, table in enumerate(page["tables"]):
                table_path = f"pages[{index}].tables[{table_index}]"
                if not isinstance(table, Mapping):
                    error(table_path, "table must be an object")
                    continue
                if not str(table.get("table_id", "")).strip():
                    error(f"{table_path}.table_id", "table_id must not be empty")
                if not isinstance(table.get("headers"), list):
                    error(f"{table_path}.headers", "headers must be a list")
                if not isinstance(table.get("rows"), list):
                    error(f"{table_path}.rows", "rows must be a list")
                else:
                    for row_index, row in enumerate(table["rows"]):
                        if not isinstance(row, Mapping) or not isinstance(row.get("cells"), list):
                            error(f"{table_path}.rows[{row_index}]", "table row must retain a cells list")
                            continue
                        for cell_index, cell in enumerate(row["cells"]):
                            if not isinstance(cell, Mapping) or not isinstance(cell.get("text"), str):
                                error(f"{table_path}.rows[{row_index}].cells[{cell_index}]", "table cell must retain text")
        if isinstance(page.get("lists"), list):
            for list_index, list_value in enumerate(page["lists"]):
                list_path = f"pages[{index}].lists[{list_index}]"
                if not isinstance(list_value, Mapping):
                    error(list_path, "list must be an object")
                    continue
                if not isinstance(list_value.get("ordered"), bool):
                    error(f"{list_path}.ordered", "ordered must be boolean")
                if not isinstance(list_value.get("items"), list):
                    error(f"{list_path}.items", "items must be a list")
        method = page.get("extraction_method")
        if method not in {None, "native", "ocr", "mixed", "native_pdf"}:
            error(f"pages[{index}].extraction_method", "extraction_method must be native, ocr, or mixed")
    if page_numbers and page_numbers != list(range(1, len(page_numbers) + 1)):
        error("pages", "page indexes must be sequential starting at 1")
    if pages and not any(str(page.get("text", "")).strip() for page in pages if isinstance(page, Mapping)):
        error("pages", "at least one page must contain non-empty text")
    extraction = document.get("extraction")
    if isinstance(extraction, Mapping) and extraction.get("page_count") != len(pages):
        error("extraction.page_count", "page_count must equal len(pages)")
    if isinstance(extraction, Mapping):
        source_page_count = extraction.get("source_page_count")
        if source_page_count is not None:
            if isinstance(source_page_count, bool) or not isinstance(source_page_count, int) or source_page_count < 1:
                error("extraction.source_page_count", "source_page_count must be a positive integer")
            elif source_page_count != len(pages):
                error("extraction.source_page_count", "source PDF page count must equal len(pages)")
    content_audit = document.get("content_audit")
    if isinstance(content_audit, Mapping):
        if content_audit.get("pages") != len(pages):
            error("content_audit.pages", "content_audit pages must equal len(pages)")
        for key in ("headings", "paragraphs", "lists", "tables", "rows", "cells", "native_chars", "ocr_chars", "final_chars", "records", "warnings"):
            value = content_audit.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                error(f"content_audit.{key}", "audit count must be a non-negative integer")

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


def _record_text(record: Mapping[str, Any], *, year: int | None = None) -> str:
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
        lines = [f"Danh mục ngành đào tạo DHV {year or ''} có {record.get('major_count')} ngành:"]
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
        per_credit = record.get("tuition_per_credit_vnd")
        if isinstance(per_credit, int):
            lines.insert(0, f"Học phí theo tín chỉ: {_format_vnd(per_credit)} đồng/tín chỉ")
        breakdown = str(record.get("total_cost_breakdown") or "").strip()
        if breakdown:
            lines.append(f"Tổng chi phí theo nguồn: {breakdown}")
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
        major = str(record.get("major_name") or "").strip()
        scope = f" ngành {major}" if major else ""
        return f"Ngưỡng đảm bảo chất lượng đầu vào{scope} (điểm sàn, {record.get('method', '')}): {record.get('raw_value', record.get('value'))} điểm."
    if record_type in {"admission_score", "admission_score_rule"}:
        return f"Điểm trúng tuyển ({record.get('method', '')}) ngành {record.get('major_name', '')}: {record.get('raw_value', record.get('value'))} điểm."
    if record_type == "supplementary_threshold":
        scope = record.get("major_name") or record.get("scope") or ""
        return f"Ngưỡng xét tuyển bổ sung ({record.get('method', '')}) {scope}: {record.get('raw_value', record.get('value'))} điểm."
    if record_type == "scholarship_fund":
        return f"• Quỹ học bổng {year or ''}: {_format_vnd(int(record.get('fund_amount_vnd')))} đồng."
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
        lines = [f"• Điều kiện nhận học bổng tuyển sinh DHV {year or ''}:"]
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
        "source_category": structured_document["category"],
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
    # Preserve the verified source fingerprint in every indexed record/chunk
    # so freshness audits can compare Chroma directly with processed JSON and
    # the current RAW PDF without relying only on a filename.
    source_sha256 = _scalar_metadata(source.get("source_sha256"))
    if source_sha256 is not None:
        base_metadata["source_sha256"] = source_sha256
    document_id = str(structured_document["document_id"])
    chunks: list[Document] = []
    for index, record in enumerate(structured_document.get("records", []), start=1):
        if not isinstance(record, Mapping):
            continue
        text = _record_text(record, year=int(structured_document["year"]))
        if not text:
            continue
        # Record text stays human-readable, but carries the document identity
        # that users commonly include in queries (for example "Học phí DHV
        # the document year").  This improves dense retrieval without embedding the whole
        # JSON object or relying on runtime parsing.
        record_category = str(record.get("fact_category") or structured_document["category"])
        category_label = _category_label(record_category, int(structured_document["year"]))
        if record.get("record_type") != "major_catalog_summary":
            text = f"{category_label}\nDHV {structured_document['year']} - {structured_document['title']}\n{text}"
        metadata = dict(base_metadata)
        metadata.update(
            {
                "category": record_category,
                "fact_category": record_category,
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
    # Semantic records remain the primary index, but they do not necessarily
    # cover every meaningful paragraph, heading, procedure, or table note on
    # a PDF page. Preserve page text as supplemental RAG material for every
    # verified document. This is additive: it does not replace structured
    # records or change the processed JSON. The original category/provenance
    # and page number stay attached so downstream filters remain authoritative.
    record_page_contents = {chunk.page_content for chunk in chunks}
    for page in structured_document.get("pages", []):
        if not isinstance(page, Mapping):
            continue
        page_number = page.get("page_number", page.get("page", 1))
        page_text = str(page.get("text") or "").strip()
        if not page_text:
            continue
        page_content = (
            f"{_category_label(str(structured_document['category']), int(structured_document['year']))}\n"
            f"DHV {structured_document['year']} - {structured_document['title']}\n{page_text}"
        )
        # A page that only repeats one semantic record adds no retrieval value,
        # and deterministic chunk IDs would otherwise collide in Chroma. Keep
        # the record version because it has the more precise semantic metadata.
        if page_content in record_page_contents:
            continue
        metadata = dict(base_metadata)
        metadata.update(
            {
                "structured_record_id": f"page_{page_number}",
                "record_type": "page_text",
                "page": page_number,
                "data_role": structured_document.get("data_role", ""),
                "page_text_source": True,
            }
        )
        chunks.append(
            Document(
                page_content=page_content,
                metadata=metadata,
            )
        )

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
                        f"{_category_label(str(structured_document['category']), int(structured_document['year']))}\n"
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
    "parse_school_information",
    "parse_tuition",
    "validate_structured_document",
    "write_structured_json",
]
