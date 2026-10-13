"""Định dạng chính sách học bổng, điều kiện xét học bổng tuyển sinh và danh mục học bổng DHV."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlparse

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
        folded in {"hoc bong dhv 2026", "hoc bong hoc phi"}
        or re.match(r"^dhv\s+20\d{2}\s*[-–]", text, re.IGNORECASE)
        or (
            text.isupper()
            and "hoc bong" in folded
            and not re.search(r"\d|%|dong|ty", folded)
        )
    )


def _prioritize_scholarship_catalog_documents(documents: list[Any]) -> list[Any]:
    """Put the verified policy pages containing named scholarship headings first."""

    def priority(item: tuple[int, Any]) -> tuple[int, int, int]:
        position, document = item
        metadata = getattr(document, "metadata", {}) or {}
        if (
            str(metadata.get("record_type") or "") == "page_text"
            and str(metadata.get("category") or "") == "phuong_thuc_xet_tuyen"
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and str(metadata.get("status") or "").casefold() == "verified"
        ):
            text = str(getattr(document, "page_content", "") or "")
            if re.search(r"(?m)^\s*\d+\.\d+\.\s+.*học bổng", text, re.IGNORECASE):
                try:
                    page = int(metadata.get("page") or 0)
                except (TypeError, ValueError):
                    page = 99
                try:
                    chunk_index = int(metadata.get("chunk_index") or 0)
                except (TypeError, ValueError):
                    chunk_index = position
                return 0, page, chunk_index
        return 1, 99, position

    return [document for _, document in sorted(enumerate(documents), key=priority)]


def _is_admission_scholarship_conditions_question(analysis: QueryAnalysis) -> bool:
    normalized = normalize_question(analysis.normalized_question)
    return (
        analysis.intent == "HOI_HOC_BONG"
        and "hoc bong" in normalized
        and any(
            marker in normalized
            for marker in ("dieu kien", "nhan hoc bong", "xet hoc bong", "xet the nao")
        )
        and not any(marker in normalized for marker in ("tong diem 3 mon", "cao nhat", "toi da"))
    )


def _prioritize_admission_scholarship_conditions_documents(
    documents: list[Any],
) -> tuple[list[Any], bool]:
    """Keep the complete, verified admission-scholarship section inside evidence limits."""

    eligible: list[tuple[int, Any, Mapping[str, object]]] = []
    for position, document in enumerate(documents):
        metadata = getattr(document, "metadata", {}) or {}
        if (
            metadata.get("record_type") != "page_text"
            or str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or not _is_official_dhv_source(metadata.get("source_url"))
        ):
            continue
        eligible.append((position, document, metadata))

    anchor = next(
        (
            (document, metadata)
            for _, document, metadata in eligible
            if "1 trong 4 phuong thuc xet hoc bong" in normalize_question(
                str(getattr(document, "page_content", "") or "")
            )
        ),
        None,
    )
    if anchor is None:
        return documents, False

    anchor_document, anchor_metadata = anchor
    structured_id = str(
        anchor_metadata.get("structured_document_id")
        or anchor_metadata.get("document_id")
        or ""
    )
    try:
        anchor_page = int(anchor_metadata.get("page"))
    except (TypeError, ValueError):
        return documents, False
    if not structured_id:
        return documents, False

    continuation = [
        (position, document, metadata)
        for position, document, metadata in eligible
        if str(
            metadata.get("structured_document_id") or metadata.get("document_id") or ""
        ) == structured_id
        and _metadata_page(metadata) >= anchor_page
    ]
    continuation.sort(
        key=lambda item: (
            _metadata_page(item[2]),
            _metadata_chunk_index(item[2], item[0]),
            item[0],
        )
    )
    section_documents: list[Any] = []
    section_ended = False
    last_page = anchor_page
    for _, document, metadata in continuation:
        page = _metadata_page(metadata)
        if page > last_page + 1:
            break
        last_page = max(last_page, page)
        section_documents.append(document)
        if re.search(
            r"(?m)^\s*1\.5\.\s*Học bổng\b",
            str(getattr(document, "page_content", "") or ""),
            re.IGNORECASE,
        ):
            section_ended = True
            break

    if not section_ended or anchor_document not in section_documents:
        return documents, False
    section_ids = {id(document) for document in section_documents}
    remaining = [document for document in documents if id(document) not in section_ids]
    return [*section_documents, *remaining], True


def _evidence_scholarship_catalog_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """List named scholarship headings once, using verified school policy pages."""

    normalized = normalize_question(analysis.normalized_question)
    asks_for_list = (
        analysis.entities.get("query_mode") in {"LIST", "LIST_AND_COUNT"}
        or any(marker in normalized for marker in ("nhung hoc bong nao", "cac hoc bong", "liet ke hoc bong"))
    )
    if analysis.intent != "HOI_HOC_BONG" or not asks_for_list:
        return None

    headings: list[str] = []
    seen: set[str] = set()
    target_year = int(analysis.entities.get("year") or settings.target_year)
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        parsed = urlparse(str(metadata.get("source_url") or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            year = int(metadata.get("year"))
        except (TypeError, ValueError):
            continue
        if not (
            metadata.get("record_type") == "page_text"
            and str(metadata.get("category") or "") in {"phuong_thuc_xet_tuyen", "ho_so"}
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and str(metadata.get("status") or "").casefold() == "verified"
            and year == target_year
            and parsed.scheme.lower() == "https"
            and (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
        ):
            continue
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not re.match(r"^\d+\.\d+\.\s+", line):
                continue
            folded = normalize_question(line)
            if "hoc bong" not in folded:
                continue
            title = re.sub(r"^\d+\.\d+\.\s*", "", line).strip(" .")
            key = normalize_question(title)
            if title and key not in seen:
                seen.add(key)
                headings.append(title)
    if not headings:
        return None
    if analysis.entities.get("query_mode") == "COUNT":
        return f"Tài liệu tuyển sinh DHV {target_year} có {len(headings)} đề mục/chính sách học bổng được nêu rõ."
    return (
        f"Các đề mục/chính sách học bổng được nêu trong tài liệu tuyển sinh DHV {target_year}:\n"
        + "\n".join(f"{index}. {title}" for index, title in enumerate(headings, start=1))
    )


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
    return "Mình tóm tắt các chính sách và điều kiện học bổng đang có trong dữ liệu DHV 2026:\n" + "\n".join(
        f"- {line}" for line in selected_lines
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
        except (TypeError, ValueError):
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
    except (TypeError, ValueError):
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

    answer_lines = [f"Điều kiện học bổng tuyển sinh DHV {target_year} theo tài liệu:"]
    if intro:
        answer_lines.append(" ".join(intro))
    for method in methods:
        answer_lines.append(f"- {method['title']}")
        answer_lines.extend(f"  - {detail}" for detail in method["details"])
    answer_lines.extend(notes)
    return "\n".join(answer_lines)
