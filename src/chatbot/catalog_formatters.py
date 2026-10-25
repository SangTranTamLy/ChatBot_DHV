"""Định dạng danh mục ngành đào tạo, chương trình, phương thức tuyển sinh và tư vấn chọn ngành."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.config.settings import settings
from src.ingestion.structured_json import is_official_dhv_url, load_structured_json
from .evidence import select_program_relations
from .evidence_utils import _evidence_sentences
from .query_analysis import ConversationState, QueryAnalysis, normalize_question


def _candidate_values(analysis: QueryAnalysis) -> tuple[str, ...]:
    if analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}:
        # A catalogue request must retain the complete category evidence;
        # candidates from an earlier advisory turn must not narrow the list.
        return ()
    values: list[str] = []
    for key in ("candidate_majors", "candidate_programs"):
        candidates = analysis.entities.get(key)
        if not isinstance(candidates, (list, tuple)):
            continue
        for candidate in candidates:
            text = str(candidate).strip()
            if text and text not in values:
                values.append(text)
    # A single named entity is a normal entity query; its supporting evidence
    # may live in a generic threshold chunk. Candidate narrowing is reserved
    # for genuinely ambiguous/multi-choice advisory turns.
    return tuple(values) if len(values) > 1 else ()


def _advisory_answer_has_guidance(analysis: QueryAnalysis, answer: object) -> bool:
    """Kiểm tra tối thiểu để câu trả lời nhiều lựa chọn thực sự là tư vấn."""

    if analysis.intent != "TU_VAN_CHON_NGANH":
        return True
    candidates = _candidate_values(analysis)
    if not analysis.entities.get("interest"):
        return True
    normalized = normalize_question(str(answer or ""))
    has_guidance = any(
        marker in normalized
        for marker in (
            "nghieng ve",
            "phu hop",
            "goi y",
            "so sanh",
            "neu ban",
            "ban co the can nhac",
            "voi so thich",
        )
    )
    # A recommendation with no explicit candidate list still needs a
    # recommendation-shaped answer. The realization layer can choose only a
    # program/parent relation already present in evidence.
    return has_guidance if candidates or analysis.entities.get("interest") else True


def _advisory_preferred_program(
    candidate_programs: list[str],
    interest: str,
    relations: list[dict[str, str]],
) -> str | None:
    """Không suy ra độ phù hợp từ quan hệ chương trình–ngành.

    Evidence hiện chỉ ghi nhận tên chương trình và ngành cha, không ghi nhận
    quan hệ giữa sở thích/năng lực cá nhân với chương trình. Chỉ bổ sung cơ chế
    chọn khi corpus có loại evidence phù hợp riêng.
    """

    return None


def _has_verified_advisory_fit_evidence(
    analysis: QueryAnalysis,
    evidence: Any,
    state: ConversationState,
    *,
    target_year: int,
) -> bool:
    """Allow generated personal-fit advice only when one verified chunk states it.

    Catalog membership and program-to-major relations are not evidence that a
    program matches a student's interest. Both the interest and a named
    candidate must be tied by explicit fit language in the same official,
    verified, in-year DHV chunk.
    """

    interest = normalize_question(
        str(analysis.entities.get("interest") or state.interest or "").strip()
    )
    if not interest:
        return False

    candidates: list[str] = []
    for key in ("candidate_majors", "candidate_programs"):
        values = analysis.entities.get(key)
        if isinstance(values, (list, tuple)):
            candidates.extend(str(value).strip() for value in values if str(value).strip())
    for value in (analysis.entities.get("major_name"), analysis.entities.get("program_name")):
        if value:
            candidates.append(str(value).strip())
    candidates.extend(state.candidate_majors)
    candidates.extend(state.candidate_programs)
    for relation in getattr(evidence, "entity_relations", ()) or ():
        for key in ("program_name", "parent_major"):
            value = str(relation.get(key) or "").strip()
            if value:
                candidates.append(value)
    for fact in getattr(evidence, "score_facts", ()) or ():
        value = str(fact.get("major_name") or "").strip()
        if value:
            candidates.append(value)

    unique_candidates = tuple(dict.fromkeys(
        normalize_question(candidate) for candidate in candidates if normalize_question(candidate)
    ))
    if not unique_candidates:
        return False

    fit_markers = (
        r"(?<!khong )(?<!khong phai )"
        r"(?:phu hop(?: nhat)?|thich hop|co the phu hop|danh cho)"
    )
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            metadata.get("status") != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
        ):
            continue
        try:
            if int(metadata.get("year")) != int(target_year):
                continue
        except (TypeError, ValueError):
            continue
        source_url = str(metadata.get("source_url") or "")
        host = (urlparse(source_url).hostname or "").lower().rstrip(".")
        if host != "dhv.edu.vn" and not host.endswith(".dhv.edu.vn"):
            continue

        text = normalize_question(str(getattr(chunk, "text", "") or ""))
        if interest not in text:
            continue
        for candidate in unique_candidates:
            if candidate not in text:
                continue
            interest_after_candidate = re.search(
                rf"{re.escape(candidate)}.{{0,180}}{fit_markers}.{{0,100}}{re.escape(interest)}",
                text,
            )
            candidate_after_interest = re.search(
                rf"{re.escape(interest)}.{{0,180}}{fit_markers}.{{0,100}}{re.escape(candidate)}",
                text,
            )
            if interest_after_candidate or candidate_after_interest:
                return True
    return False


def _advisory_evidence_clarification(
    analysis: QueryAnalysis,
    evidence: Any,
    state: ConversationState,
    score_comparisons: Any,
) -> dict[str, object]:
    """Trả về một câu trả lời hữu ích, chỉ dựa trên bằng chứng khi việc sinh văn bản tư vấn thất bại."""

    candidate_majors = list(state.candidate_majors)
    candidate_programs = list(state.candidate_programs)
    relations = list(getattr(evidence, "entity_relations", ()) or ())
    for relation in relations:
        parent = str(relation.get("parent_major") or "").strip()
        program = str(relation.get("program_name") or "").strip()
        if program in candidate_programs and parent and parent not in candidate_majors:
            candidate_majors.append(parent)

    codes_by_major: dict[str, str] = {}
    for fact in getattr(evidence, "score_facts", ()) or ():
        name = str(fact.get("major_name") or "").strip()
        code = str(fact.get("major_code") or "").strip()
        if name and code and normalize_question(name) not in codes_by_major:
            codes_by_major[normalize_question(name)] = code

    interest = str(analysis.entities.get("interest") or state.interest or "").strip()
    interest_display = {
        "chinh sua video": "chỉnh sửa video",
        "edit video": "edit video",
    }.get(normalize_question(interest), interest)
    preferred_program = _advisory_preferred_program(candidate_programs, interest, relations)
    lines: list[str] = []
    if preferred_program:
        parent = next(
            (
                str(relation.get("parent_major") or "").strip()
                for relation in relations
                if str(relation.get("program_name") or "").strip() == preferred_program
                and str(relation.get("parent_major") or "").strip()
            ),
        )
        parent_code = codes_by_major.get(normalize_question(parent))
        code_text = f" (mã ngành {parent_code})" if parent_code else ""
        lines.append(
            f"Với sở thích {interest_display}, mình nghiêng về {preferred_program} hơn. "
            f"Đây là chương trình thuộc ngành {parent}{code_text}."
        )
    if candidate_majors or candidate_programs:
        lines.append("Bạn có thể cân nhắc các lựa chọn sau:")
    for major in candidate_majors:
        major_text = str(major).strip()
        if not major_text:
            continue
        code = codes_by_major.get(normalize_question(major_text))
        children = [
            str(relation.get("program_name"))
            for relation in relations
            if str(relation.get("parent_major") or "").strip() == major_text
            and str(relation.get("program_name") or "").strip()
        ]
        detail = f" (mã ngành {code})" if code else ""
        if children:
            lines.append(f"- {major_text}{detail} gồm: {'; '.join(dict.fromkeys(children))}.")
        else:
            lines.append(f"- {major_text}{detail}.")

    for program in candidate_programs:
        program_text = str(program).strip()
        if program_text == preferred_program:
            continue
        matches = [
            str(relation.get("parent_major"))
            for relation in relations
            if str(relation.get("program_name") or "").strip() == program_text
            and str(relation.get("parent_major") or "").strip()
        ]
        for parent in dict.fromkeys(matches):
            lines.append(f"- {program_text} là chương trình thuộc ngành {parent}.")

    for comparison in score_comparisons or ():
        method = str(comparison.get("method") or "").strip()
        label = {"dgnl": "ĐGNL", "thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ"}.get(method, method)
        lines.append(
            f"- Điểm {label} bạn cung cấp: {comparison.get('student_value')}; "
            f"ngưỡng trong dữ liệu: {comparison.get('threshold_value')}. Đây chỉ là so sánh "
            "với ngưỡng nhận hồ sơ, không phải kết luận trúng tuyển."
        )

    if interest:
        lines.append(
            f"Mình ghi nhận bạn quan tâm đến {interest_display}, nhưng tài liệu DHV đã xác minh "
            "chưa nêu căn cứ để kết luận ngành hoặc chương trình nào phù hợp với sở thích này."
        )
        lines.append(
            "Bạn muốn mình liệt kê các ngành/chương trình có trong tài liệu, hay cho biết thêm "
            "tiêu chí bạn muốn ưu tiên để mình tra cứu thông tin tương ứng?"
        )
    else:
        lines.append(
            "Bạn thích sáng tạo nội dung số hay tìm hiểu AI/IoT và kỹ thuật phần cứng hơn?"
        )
    return {
        "answer": "\n".join(lines),
        "sources": [dict(source) for source in evidence.sources],
        "status": "clarification",
    }


def _deterministic_recommendation_answer(
    analysis: QueryAnalysis,
    evidence: Any,
    score_comparisons: Any,
) -> str | None:
    interest = str(analysis.entities.get("interest") or "").strip()
    if not interest:
        return None
    candidates = list(_candidate_values(analysis))
    relations = list(getattr(evidence, "entity_relations", ()) or ())
    preferred = _advisory_preferred_program(candidates, interest, relations)
    if not preferred:
        return None
    parent = next(
        (
            str(relation.get("parent_major") or "").strip()
            for relation in relations
            if str(relation.get("program_name") or "").strip() == preferred
            and str(relation.get("parent_major") or "").strip()
        ),
        "",
    )
    if not parent:
        return None
    interest_display = {
        "dung video": "dựng video",
        "chinh sua video": "chỉnh sửa video",
        "edit video": "edit video",
    }.get(normalize_question(interest), interest)
    lines = [
        f"Với sở thích {interest_display}, mình nghiêng về {preferred} hơn. "
        f"{preferred} là chương trình thuộc ngành {parent}.",
    ]
    for comparison in score_comparisons or ():
        method = str(comparison.get("method") or "").strip()
        label = {"dgnl": "ĐGNL", "thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ"}.get(method, method)
        relation_word = "cao hơn hoặc bằng" if comparison.get("meets_threshold") else "thấp hơn"
        lines.append(
            f"Điểm {label} bạn nêu là {comparison.get('student_value')}, "
            f"{relation_word} ngưỡng nhận hồ sơ {comparison.get('threshold_value')}."
        )
    lines.append("Đây chỉ là so sánh với ngưỡng nhận hồ sơ, không phải kết luận trúng tuyển.")
    return "\n".join(lines)


def _program_detail_missing_evidence(analysis: QueryAnalysis, evidence: Any) -> bool:
    normalized = normalize_question(analysis.normalized_question)
    detail_cues = (
        "trang bi kien thuc", "kien thuc ve", "hoc gi", "mon hoc", "day ve",
        "noi dung dao tao", "hoc nhu the nao",
    )
    cue = next((marker for marker in detail_cues if marker in normalized), None)
    if not cue or analysis.intent != "HOI_CHUONG_TRINH":
        return False
    suffix = normalized.split(cue, 1)[-1]
    stop_words = {
        "nhu", "the", "nao", "gi", "ve", "cho", "nganh", "chuong", "trinh",
        "marketing", "dhv", "sinh", "vien", "duoc", "nhung", "cua", "thi",
    }
    requested_terms = {
        token for token in re.findall(r"[a-z0-9]+", suffix)
        if len(token) > 2 and token not in stop_words
    }
    if len(requested_terms) < 2:
        return False
    evidence_text = normalize_question(" ".join(
        str(getattr(chunk, "text", "") or "")
        for chunk in getattr(evidence, "chunks", ()) or ()
    ))
    return not requested_terms.issubset(set(re.findall(r"[a-z0-9]+", evidence_text)))


def _major_rows_from_evidence(evidence: Any) -> list[tuple[str, str]]:
    """Trả về các dòng danh mục ngành đã sắp xếp và khử trùng lặp từ danh mục được xác thực."""

    rows: list[tuple[str, str]] = []
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    for fact in getattr(evidence, "score_facts", ()) or ():
        if str(fact.get("category") or "") != "nganh_dao_tao":
            continue
        major = str(fact.get("major_name") or "").strip()
        code = str(fact.get("major_code") or "").strip()
        if not major or not code:
            continue
        normalized = normalize_question(major)
        if code in seen_codes or normalized in seen_names:
            continue
        seen_codes.add(code)
        seen_names.add(normalized)
        rows.append((major, code))
    return rows


def _verified_major_catalog(
    target_year: object,
) -> tuple[list[tuple[str, str]], dict[str, str]] | None:
    """Load the complete, verified major list from its one owning source file."""

    try:
        year = int(target_year)
    except (TypeError, ValueError):
        year = int(settings.target_year)
    category_dir = Path(settings.processed_data_dir) / "nganh_dao_tao"
    for path in sorted(category_dir.glob("*.json")):
        try:
            document = load_structured_json(path)
        except (OSError, ValueError):
            continue
        source = document.get("source") or {}
        if (
            document.get("category") != "nganh_dao_tao"
            or document.get("data_role") != "catalog"
            or document.get("year") != year
            or source.get("status") != "verified"
            or str(source.get("school_code") or "").upper() != "DHV"
            or not is_official_dhv_url(source.get("source_url"))
        ):
            continue

        records = document.get("records") or []
        majors = [
            record
            for record in records
            if isinstance(record, dict) and record.get("record_type") == "major"
        ]
        summary = next(
            (
                record
                for record in records
                if isinstance(record, dict) and record.get("record_type") == "major_catalog_summary"
            ),
            {},
        )
        source_text = normalize_question(
            " ".join(
                str(page.get("text") or "")
                for page in document.get("pages", [])
                if isinstance(page, dict)
            )
        )
        declared_count_match = re.search(
            r"\b(\d{1,3})\s+nganh(?: hoc)?\s+voi\s+hon\s+\d{1,3}\s+chuong trinh\b",
            source_text,
        )
        rows = [
            (str(record.get("major_name") or "").strip(), str(record.get("major_code") or "").strip())
            for record in majors
        ]
        if (
            not rows
            or len(rows) != summary.get("major_count")
            or (
                declared_count_match
                and len(rows) != int(declared_count_match.group(1))
            )
            or any(not name or not re.fullmatch(r"\d{7}", code) for name, code in rows)
            or len({normalize_question(name) for name, _ in rows}) != len(rows)
            or len({code for _, code in rows}) != len(rows)
        ):
            continue

        url = str(source.get("source_url") or "").strip()
        return rows, {"title": str(document.get("title") or "Danh mục ngành DHV"), "url": url}
    return None


_MAJOR_GROUP_LABELS = {
    "economics": "kinh tế",
    "languages": "ngôn ngữ",
    "technology": "công nghệ",
}


def _major_in_group(major_code: str, major_group: str) -> bool:
    """Filter the verified catalog by the code families used by the request."""

    code = str(major_code or "").strip()
    if major_group == "economics":
        # DHV's verified catalog includes International Economics (7310106)
        # alongside the 734 business/economics family.
        return code.startswith("734") or code == "7310106"
    if major_group == "languages":
        return code.startswith("722")
    if major_group == "technology":
        return code.startswith("748")
    return False


def _program_rows_from_evidence(
    evidence: Any,
    major_rows: list[tuple[str, str]],
    *,
    parent_major: str | None = None,
) -> list[tuple[str, str, str | None]]:
    """Trả về ánh xạ chương trình-ngành cha đã sắp xếp mà không biến chương trình thành ngành chính."""

    code_by_major = {
        normalize_question(major): code
        for major, code in major_rows
    }
    rows: list[tuple[str, str, str | None]] = []
    relations = select_program_relations(
        getattr(evidence, "entity_relations", ()) or (),
        parent_major=parent_major,
    )
    for relation in relations:
        program = relation["program_name"]
        parent = relation["parent_major"]
        rows.append((program, parent, code_by_major.get(normalize_question(parent))))
    return rows


def _method_details_from_evidence(
    evidence: Any,
    *,
    target_year: int,
) -> dict[int, str]:
    """Read method explanations from verified page text, not short catalog labels."""

    grouped: dict[str, list[tuple[int, int, list[str]]]] = {}
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("record_type") or "") != "page_text"
            or str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or str(metadata.get("status") or "").casefold() != "verified"
        ):
            continue
        try:
            if int(metadata.get("year")) != target_year:
                continue
            page = int(metadata.get("page") or 0)
            chunk_index = int(metadata.get("chunk_index") or 0)
        except (TypeError, ValueError):
            continue

        source = str(
            metadata.get("source_file")
            or metadata.get("structured_document_id")
            or metadata.get("document_id")
            or ""
        )
        # Some OCR/legacy structured records contain the two literal characters
        # ``\\n`` instead of real line breaks. Split those before parsing method
        # headings and bullets, otherwise the học-bạ section absorbs later
        # methods and its two calculation options are lost.
        raw_text = str(getattr(chunk, "text", "") or "")
        raw_text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
        lines: list[str] = []
        for raw_line in raw_text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            folded = normalize_question(line)
            if (
                not line
                or re.fullmatch(r"\d+", folded)
                or folded.startswith(("dhv 2026 -", "phuong thuc xet tuyen dhv 2026", "tong quan tuyen sinh dhv 2026"))
            ):
                continue
            lines.append(line)
        if source and lines:
            grouped.setdefault(source, []).append((page, chunk_index, lines))

    def format_body(lines: list[str]) -> str:
        parts: list[str] = []
        paragraph = ""
        bullet = ""

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                parts.append(paragraph.strip())
                paragraph = ""

        def flush_bullet() -> None:
            nonlocal bullet
            if bullet:
                parts.append(f"- {bullet.strip()}")
                bullet = ""

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(("•", "- ", "– ")):
                flush_paragraph()
                flush_bullet()
                bullet = line.lstrip("•-– ").strip()
                continue
            if bullet:
                if bullet.endswith((".", "!", "?", ")")):
                    flush_bullet()
                    paragraph = line
                else:
                    bullet = f"{bullet} {line}"
                continue
            if paragraph and paragraph.endswith((".", "!", "?")):
                flush_paragraph()
            paragraph = f"{paragraph} {line}".strip()
        flush_paragraph()
        flush_bullet()
        return "\n".join(dict.fromkeys(item for item in parts if item))[:1800]

    candidates: list[tuple[int, int, dict[int, str]]] = []
    for source, page_chunks in grouped.items():
        lines: list[str] = []
        seen_chunk_texts: set[tuple[int, str]] = set()
        for page, _, chunk_lines in sorted(page_chunks):
            chunk_key = (page, normalize_question("\n".join(chunk_lines)))
            if chunk_key in seen_chunk_texts:
                continue
            seen_chunk_texts.add(chunk_key)
            for line in chunk_lines:
                # Only collapse adjacent duplicate lines caused by overlapping
                # chunks. Identical lines elsewhere can be distinct list items
                # (for example, both subject-combination bullets end in the
                # same word and punctuation).
                if lines and normalize_question(lines[-1]) == normalize_question(line):
                    continue
                lines.append(line)

        anchor = next(
            (
                index
                for index, line in enumerate(lines)
                if "cac phuong thuc xet tuyen nam 2026" in normalize_question(line)
                or "cac phuong thuc xet tuyen gom" in normalize_question(line)
            ),
            None,
        )
        if anchor is None:
            # A method-specific retrieval can legitimately return page 4
            # without page 3's section header. Accept only the exact official
            # transcript-method heading; similarly worded scholarship rules
            # on later pages are deliberately not a fallback anchor.
            method_heading = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if "xet tuyen ket qua hoc tap thpt hoc ba" in normalize_question(line)
                ),
                None,
            )
            if method_heading is not None:
                anchor = method_heading - 1
        if anchor is None:
            continue
        end = len(lines)
        for index in range(anchor + 1, len(lines)):
            # The uploaded 2026 source numbers the method headings as 2.1–2.5.
            # Stop only at a nested section such as 2.6.1, not at the first
            # method heading; older source editions use a.–e. headings below.
            if re.match(r"^\d+(?:\.\d+){2,}\.?\s+", normalize_question(lines[index])):
                end = index
                break
        section_lines = lines[anchor + 1:end]
        headings: list[tuple[int, int]] = []
        for index, line in enumerate(section_lines):
            folded = normalize_question(line)
            letter_heading = re.match(r"^([a-e])(?:\.|\s)+xet\b", folded)
            numbered_heading = re.match(r"^\d+\.([1-5])\.?\s+xet\b", folded)
            if letter_heading:
                headings.append((index, ord(letter_heading.group(1)) - ord("a") + 1))
            elif numbered_heading:
                headings.append((index, int(numbered_heading.group(1))))
        details: dict[int, str] = {}
        for position, (start, method_number) in enumerate(headings):
            stop = headings[position + 1][0] if position + 1 < len(headings) else len(section_lines)
            detail = format_body(section_lines[start + 1:stop])
            if method_number == 1:
                detail = re.split(
                    r"(?:Các tổ hợp xét tuyển được thiết kế linh hoạt|Việc đăng ký nguyện vọng)",
                    detail,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()
            elif method_number == 5:
                # The page continues with a separately labelled set of
                # group/major-specific rules. Keep those out of the vocational
                # method's own eligibility statement instead of misattributing
                # them to every vocational applicant.
                detail = re.split(r"Khối công nghệ\s*:", detail, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if detail:
                details[method_number] = detail
        if details:
            candidates.append((len(details), sum(map(len, details.values())), details))

    if not candidates:
        return {}
    _, _, best = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    # Do not label an incomplete subset as a full, detailed method list.
    return best if len(best) == 5 else {}


def _evidence_catalog_answer(
    analysis: QueryAnalysis,
    evidence: Any,
    state: ConversationState,
) -> dict[str, object] | None:
    """Định dạng các câu trả lời danh mục từ bằng chứng có cấu trúc, không phải từ văn xuôi của model."""

    major_rows = _major_rows_from_evidence(evidence)
    if analysis.intent == "DANH_SACH_NGANH":
        verified_catalog = _verified_major_catalog(
            analysis.entities.get("year") or settings.target_year
        )
        if verified_catalog is not None:
            major_rows, catalog_source = verified_catalog
            catalog_sources = [catalog_source]
        else:
            catalog_sources = [dict(source) for source in evidence.sources]
        major_group = str(analysis.entities.get("major_group") or "")
        if major_group:
            major_rows = [
                (major, code)
                for major, code in major_rows
                if _major_in_group(code, major_group)
            ]
        if not major_rows:
            return None
        group_label = _MAJOR_GROUP_LABELS.get(major_group)
        year_values = [
            str(chunk.metadata.get("year"))
            for chunk in getattr(evidence, "chunks", ())
            if chunk.metadata.get("year")
        ]
        year_text = f" năm {year_values[0]}" if year_values else ""
        count_only = (
            any(
                marker in analysis.normalized_question
                for marker in (
                    "bao nhieu nganh",
                    "nhieu nganh",
                    "bao nhiu nganh",
                    "nhiu nganh",
                    "may nganh",
                    "so luong nganh",
                    "tong so nganh",
                    "co bao nhieu",
                    "co nhieu",
                    "co may",
                )
            )
            and not any(
                marker in analysis.normalized_question
                for marker in (
                    "danh sach",
                    "liet ke",
                    "liet ra",
                    "cac nganh",
                    "nhung nganh",
                    "nganh nao",
                    "nganh gi",
                    "nhung nganh nao",
                )
            )
            and analysis.entities.get("query_mode") not in {"LIST", "LIST_AND_COUNT"}
        )
        if count_only:
            if group_label:
                entries = ", ".join(f"{major} ({code})" for major, code in major_rows)
                return {
                    "answer": (
                        f"Nhóm {group_label} có "
                        f"{len(major_rows)} ngành: {entries}."
                    ),
                    "sources": catalog_sources,
                    "status": "ok",
                }
            for sentence in _evidence_sentences(evidence):
                summary = re.search(
                    r"\b(\d+)\s+nganh\b.{0,100}?\bhon\s+(\d+)\s+chuong\s+trinh\b",
                    normalize_question(sentence),
                )
                if summary and int(summary.group(1)) == len(major_rows):
                    source_year = analysis.entities.get("year") or (year_values[0] if year_values else None)
                    year_text = f" năm {source_year}" if source_year else ""
                    answer_text = (
                        f"Chào bạn! DHV có {len(major_rows)} ngành chính{year_text} và hơn "
                        f"{int(summary.group(2))} chương trình đào tạo.\n\n"
                        f"Nếu bạn cần xem danh sách chi tiết các ngành hoặc tìm hiểu phương thức xét tuyển, bạn cứ nhắn mình nhé!"
                    )
                    return {
                        "answer": answer_text,
                        "sources": catalog_sources,
                        "status": "ok",
                    }
            # PDF line wrapping can split the overview statistic across
            # separate extracted lines, so inspect the flattened selected
            # source text as well. The major count must agree with the
            # structured catalogue before including the program-count fact.
            for chunk in getattr(evidence, "chunks", ()) or ():
                metadata = getattr(chunk, "metadata", {}) or {}
                if (
                    str(metadata.get("category") or "") not in {"phuong_thuc_xet_tuyen", "thong_tin_truong"}
                    or str(metadata.get("record_type") or "") != "page_text"
                    or str(metadata.get("status") or "") != "verified"
                    or str(metadata.get("school_code") or "").upper() != "DHV"
                ):
                    continue
                flattened = normalize_question(
                    " ".join(str(getattr(chunk, "text", "") or "").splitlines())
                )
                summary = re.search(
                    r"\b(\d+)\s+nganh(?: hoc)?\s+voi\s+hon\s+(\d+)\s+chuong\s+trinh\b",
                    flattened,
                )
                if summary and int(summary.group(1)) == len(major_rows):
                    year = metadata.get("year") or (year_values[0] if year_values else None)
                    year_text = f" năm {year}" if year else ""
                    answer_text = (
                        f"Chào bạn! DHV có {len(major_rows)} ngành chính{year_text} và hơn "
                        f"{int(summary.group(2))} chương trình đào tạo.\n\n"
                        f"Nếu bạn cần xem danh sách chi tiết các ngành hoặc tìm hiểu phương thức xét tuyển, bạn cứ nhắn mình nhé!"
                    )
                    return {
                        "answer": answer_text,
                        "sources": catalog_sources,
                        "status": "ok",
                    }
            answer_text = (
                f"Chào bạn! DHV hiện có {len(major_rows)} ngành chính{year_text} theo định hướng ứng dụng thực tiễn.\n\n"
                f"Nếu bạn cần xem danh sách chi tiết các ngành hoặc tìm hiểu phương thức xét tuyển, bạn cứ nhắn mình nhé!"
            )
            return {
                "answer": answer_text,
                "sources": catalog_sources,
                "status": "ok",
            }
        correction = ""
        normalized_question = analysis.normalized_question
        is_list_correction = bool(
            (state.last_list_count and state.last_list_count != len(major_rows))
            or any(
                marker in normalized_question
                for marker in ("sao", "con thieu", "chua du", "danh sach tren", "liet ke lai")
            )
        )
        if group_label:
            correction = (
                f"Nhóm {group_label} có "
                f"{len(major_rows)} ngành theo mã ngành:\n"
            )
        elif is_list_correction:
            correction = (
                "Mình đính chính nhé: danh mục đã được kiểm chứng hiện có "
                f"{len(major_rows)} ngành chính{year_text}. Danh sách trước có thể đã "
                "trộn chương trình đào tạo với ngành chính hoặc bỏ sót một số ngành.\n"
            )
        else:
            correction = (
                f"Chào bạn! Năm 2026, Trường Đại học Hùng Vương TP.HCM (DHV) đào tạo {len(major_rows)} ngành chính{year_text} "
                "với hơn 50 chương trình đào tạo đa dạng. Dưới đây là danh sách các ngành cùng mã ngành để bạn tham khảo nhé:\n"
            )
        lines = [
            f"{index}. {major} — mã ngành {code}"
            for index, (major, code) in enumerate(major_rows, start=1)
        ]
        return {
            "answer": correction + "\n".join(lines),
            "sources": catalog_sources,
            "status": "ok",
        }

    if analysis.intent == "DANH_SACH_CHUONG_TRINH":
        entities = analysis.entities
        requested_major = str(entities.get("major_name") or "").strip() or None
        operation = str(entities.get("catalog_operation") or "LIST")
        program_rows = _program_rows_from_evidence(
            evidence,
            major_rows,
            parent_major=requested_major,
        )
        if not program_rows:
            return None
        scope = requested_major or "toàn bộ danh mục"
        count = len(program_rows)
        lines = []
        if operation in {"LIST", "LIST_AND_COUNT"}:
            lines = [
                f"{index}. {program} — thuộc ngành {parent}"
                + (f" (mã ngành {code})" if code else "")
                for index, (program, parent, code) in enumerate(program_rows, start=1)
            ]
        if operation == "COUNT":
            answer = f"{scope} có {count} chương trình đào tạo."
        elif operation == "LIST_AND_COUNT":
            answer = (
                f"{scope} có {count} chương trình đào tạo:\n"
                + "\n".join(lines)
            )
        else:
            answer = (
                "Mình liệt kê các chương trình đào tạo và ghi rõ ngành cha để bạn "
                "không nhầm với danh sách ngành chính:\n" + "\n".join(lines)
            )
        return {
            "answer": answer,
            "sources": [dict(source) for source in evidence.sources],
            "status": "ok",
            "catalog": {
                "operation": operation,
                "requested_major": requested_major,
                "program_count": count,
                "program_rows": [
                    {"program_name": program, "parent_major": parent, "major_code": code}
                    for program, parent, code in program_rows
                ],
                "deterministic": True,
            },
        }

    if analysis.intent == "HOI_PHUONG_THUC_XET_TUYEN":
        if "to hop mon" in analysis.normalized_question and any(
            marker in analysis.normalized_question for marker in ("nhung mon nao", "gom nhung mon", "cac mon")
        ):
            # A question about the subjects inside combinations is not a
            # request to enumerate the school's admission methods.
            return None
        operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
        if operation not in {"COUNT", "LIST", "LIST_AND_COUNT"}:
            return None
        methods = []
        for fact in getattr(evidence, "score_facts", ()):
            if fact.get("score_type") == "admission_method" and fact.get("method_text"):
                methods.append((fact.get("method_number", 0), fact.get("method_text")))
        if not methods:
            return None
        # Sort by method number and deduplicate
        methods.sort(key=lambda x: (x[0] or 99, x[1]))
        unique_methods = []
        seen = set()
        for number, text in methods:
            key = number if number else text
            if key not in seen:
                seen.add(key)
                unique_methods.append(text)
        count = len(unique_methods)
        cleaned_methods = [
            re.sub(r"^\s*(?:\d+\.)+\d*\.?\s*", "", str(text)).strip()
            for text in unique_methods
        ]
        lines = [f"{index}. {text}" for index, text in enumerate(cleaned_methods, start=1)]

        detail_requested = any(
            marker in normalize_question(analysis.normalized_question)
            for marker in ("chi tiet", "cu the", "dieu kien", "moi phuong thuc", "tung phuong thuc")
        )
        method_details = (
            _method_details_from_evidence(
                evidence,
                target_year=int(analysis.entities.get("year") or settings.target_year),
            )
            if detail_requested
            else {}
        )
        if method_details:
            detailed_lines = [
                f"{index}. {text}\n{method_details[index]}"
                for index, text in enumerate(cleaned_methods, start=1)
            ]
            answer = (
                f"Hiện tại DHV có {count} phương thức xét tuyển chính:\n"
                + "\n".join(detailed_lines)
            )
            return {
                "answer": answer,
                "sources": [dict(source) for source in evidence.sources],
                "status": "ok",
            }
        
        if operation == "COUNT":
            answer = f"Hiện tại Trường Đại học Hùng Vương TP.HCM (DHV) áp dụng {count} phương thức xét tuyển nhé."
        elif operation == "LIST_AND_COUNT":
            answer = f"Hiện tại DHV có {count} phương thức xét tuyển chính, cụ thể như sau:\n" + "\n".join(lines)
        else:
            answer = "Dưới đây là các phương thức xét tuyển của DHV nhé:\n" + "\n".join(lines)
        return {
            "answer": answer,
            "sources": [dict(source) for source in evidence.sources],
            "status": "ok",
        }
    return None


_PROGRAM_RELATION_MARKERS = (
    "co chuyen nganh", "co nganh", "co chuong trinh", "co dao tao", "dao tao chuyen nganh",
    "thuoc nganh", "nam trong nganh", "nam o nganh", "la chuyen nganh", "la chuong trinh",
    "thuoc khoa", "nganh nao",
)


def _evidence_program_relation_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    program = str(analysis.entities.get("program_name") or "").strip()
    if not program:
        return None
    question = normalize_question(analysis.normalized_question)
    if "hoc phan" in question or not any(marker in question for marker in _PROGRAM_RELATION_MARKERS):
        # "Học phần Quản trị Nguồn nhân lực Quốc tế ..." asks about a course
        # activity, not whether the programme exists or which major owns it.
        return None
    program_key = normalize_question(program)
    relation = next(
        (
            item
            for item in getattr(evidence, "entity_relations", ()) or ()
            if normalize_question(str(item.get("program_name") or "")) == program_key
        ),
        None,
    )
    if not relation:
        return None
    parent = str(relation.get("parent_major") or "").strip()
    if not parent:
        return None
    parent_code = next(
        (
            str(fact.get("major_code"))
            for fact in getattr(evidence, "score_facts", ()) or ()
            if normalize_question(str(fact.get("major_name") or "")) == normalize_question(parent)
            and fact.get("major_code")
        ),
        None,
    )
    code_text = f" (mã ngành {parent_code})" if parent_code else ""
    return f"Có. {program} là chương trình thuộc ngành {parent}{code_text}."


def _source_ordered_documents(documents: list[Any]) -> list[Any]:
    """Khôi phục lại thứ tự nguồn sau khi xếp hạng kết hợp (hybrid ranking) cho các câu trả lời danh mục."""

    def key(item: tuple[int, Any]) -> tuple[object, ...]:
        position, document = item
        metadata = getattr(document, "metadata", {}) or {}

        def number(name: str) -> int:
            value = metadata.get(name)
            try:
                return int(value)
            except (TypeError, ValueError):
                return 10**9

        return (
            str(metadata.get("source_file") or ""),
            number("section_index"),
            number("section_chunk_index"),
            number("chunk_index"),
            position,
        )

    return [document for _, document in sorted(enumerate(documents), key=key)]
