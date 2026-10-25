"""Định dạng các câu trả lời liên quan đến điều kiện tuyển sinh, phương thức, hồ sơ, điểm số và nhập học."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlparse

from src.config.settings import settings
from .query_semantics import enrollment_request
from .catalog_formatters import _method_details_from_evidence
from .evidence_utils import (
    _bullet_content_lines,
    _evidence_sentences,
    _evidence_text_lines,
    _remove_unresolved_url_label,
    _split_source_sentences,
)
from .query_analysis import (
    QueryAnalysis,
    normalize_entity_name,
    normalize_question,
    _is_subject_minimum_request,
)


def _is_result_notification_question(question: str) -> bool:
    normalized = normalize_question(question)
    return "trung tuyen" in normalized and any(
        marker in normalized for marker in ("thong bao", "vao dau", "bao ket qua", "nhan ket qua")
    )


def _prioritize_result_notification_documents(documents: list[Any]) -> list[Any]:
    """Put the requested, verified notification channels inside bounded evidence context."""

    def priority(item: tuple[int, Any]) -> tuple[int, int]:
        position, document = item
        text = normalize_question(str(getattr(document, "page_content", "") or ""))
        has_ministry = "he thong ho tro xet tuyen chung" in text and "bo giao duc" in text
        has_website = "website tuyen sinh" in text and "tuyensinh.dhv.edu.vn" in text
        has_invitation = "thu moi nhap hoc" in text and "tin nhan zalo" in text
        if has_ministry:
            return 0, position
        if has_website:
            return 1, position
        if has_invitation:
            return 2, position
        return 3, position

    return [document for _, document in sorted(enumerate(documents), key=priority)]


def _prioritize_enrollment_document_records(documents: list[Any]) -> list[Any]:
    """Keep checklist records before long enrollment page text in bounded evidence."""

    def priority(item: tuple[int, Any]) -> tuple[int, int]:
        position, document = item
        metadata = getattr(document, "metadata", {}) or {}
        record_type = str(metadata.get("record_type") or "")
        text = normalize_question(str(getattr(document, "page_content", "") or ""))
        if record_type == "enrollment_document":
            return 0, position
        if "2.2 chuan bi ho so nhap hoc" in text:
            return 1, position
        return 2, position

    return [document for _, document in sorted(enumerate(documents), key=priority)]


def _prioritize_admission_date_comparison_documents(
    documents: list[Any],
    question: str,
) -> list[Any]:
    """Keep the two requested milestone facts inside bounded comparison evidence."""

    requested_dates = {
        (int(day), int(month))
        for day, month in re.findall(r"\b(\d{1,2})/(\d{1,2})\b", normalize_question(question))
    }

    def priority(item: tuple[int, Any]) -> tuple[int, int]:
        position, document = item
        text = str(getattr(document, "page_content", "") or "")
        folded = normalize_question(text)
        has_requested_date = any(
            re.search(rf"\b0?{day}/0?{month}(?:/20\d{{2}})?\b", folded)
            or re.search(
                rf"\b{day}\s+thang\s+0?{month}(?:\s+nam\s+20\d{{2}})?\b",
                folded,
            )
            for day, month in requested_dates
        )
        if not has_requested_date:
            return 3, position
        if any(marker in folded for marker in ("uu dai cao nhat", "muc ho tro hoc phi", "muc hoc bong")):
            return 0, position
        if any(marker in folded for marker in (
            "xac nhan nhap hoc", "thoi gian xac nhan", "he thong ho tro xet tuyen chung",
        )):
            return 1, position
        return 2, position

    return [document for _, document in sorted(enumerate(documents), key=priority)]


def _evidence_date_comparison_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Compare two admission milestones only when both meanings appear in evidence."""

    normalized = normalize_question(analysis.normalized_question)
    requested_dates = re.findall(r"\b(\d{1,2})/(\d{1,2})\b", normalized)
    if analysis.intent != "HOI_LICH_TUYEN_SINH" or len(requested_dates) < 2:
        return None
    year = analysis.entities.get("year") or 2026

    def contains_date(sentence: str, day: str, month: str) -> bool:
        folded = normalize_question(sentence)
        return bool(
            re.search(
                rf"\b0?{int(day)}/0?{int(month)}(?:/{int(year)})?\b",
                folded,
            )
            or re.search(
                rf"\b{int(day)}\s+thang\s+{int(month)}\s+nam\s+{int(year)}\b",
                folded,
            )
        )

    evidence_sentences: list[tuple[Mapping[str, object], list[str]]] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        evidence_sentences.append((
            metadata if isinstance(metadata, Mapping) else {},
            _split_source_sentences(str(getattr(chunk, "text", "") or "")),
        ))
    system_contexts = [
        (metadata, sentence)
        for metadata, sentences in evidence_sentences
        for sentence in sentences
        if "he thong ho tro xet tuyen chung" in normalize_question(sentence)
        and "bo giao duc" in normalize_question(sentence)
    ]

    benefit_candidates: list[tuple[int, str, str, str]] = []
    deadline_candidates: list[tuple[str, str, list[str]]] = []
    for day, month in requested_dates[:2]:
        for metadata, chunk_sentences in evidence_sentences:
            dated = [
                sentence for sentence in chunk_sentences
                if contains_date(sentence, day, month)
            ]
            if not dated:
                continue
            for sentence in dated:
                folded = normalize_question(sentence)
                benefit_score = (
                    3 if "uu dai cao nhat" in folded
                    else 2 if any(marker in folded for marker in (
                        "muc ho tro hoc phi", "muc hoc bong", "mien giam hoc phi",
                    ))
                    else 0
                )
                if benefit_score:
                    benefit_candidates.append((benefit_score, day, month, sentence))
            deadline = next(
                (
                    sentence for sentence in dated
                    if any(marker in normalize_question(sentence) for marker in (
                        "xac nhan nhap hoc", "thoi gian xac nhan", "den 17 gio",
                    ))
                ),
                None,
            )
            if deadline:
                source_identity = str(metadata.get("source_file") or metadata.get("source_url") or "")
                system_context = next((
                    sentence for context_metadata, sentence in system_contexts
                    if source_identity
                    and source_identity in {
                        str(context_metadata.get("source_file") or ""),
                        str(context_metadata.get("source_url") or ""),
                    }
                ), None)
                if system_context is None:
                    system_context = next((sentence for _, sentence in system_contexts), None)
                deadline_candidates.append((
                    day,
                    month,
                    [_remove_unresolved_url_label(system_context), deadline]
                    if system_context
                    else [deadline],
                ))

    best_benefit = max(benefit_candidates, default=None, key=lambda item: item[0])
    benefit_milestone = (
        (best_benefit[1], best_benefit[2], [best_benefit[3]])
        if best_benefit
        else None
    )
    deadline_milestone = next(
        (
            item for item in deadline_candidates
            if item[:2] != (benefit_milestone or (None, None))[0:2]
        ),
        None,
    )
    if not benefit_milestone or not deadline_milestone or benefit_milestone[:2] == deadline_milestone[:2]:
        return None
    def label(item: tuple[str, str, list[str]]) -> str:
        return f"{int(item[0])}/{int(item[1]):02d}/{year}"

    return (
        "Không, đây là hai mốc khác nhau:\n"
        f"- {label(benefit_milestone)}: {benefit_milestone[2][0].strip()}\n"
        f"- {label(deadline_milestone)}: "
        + " ".join(sentence.strip() for sentence in deadline_milestone[2])
    )


def _evidence_exam_subject_count_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    normalized = normalize_question(analysis.normalized_question)
    if not any(marker in normalized for marker in ("may mon", "bao nhieu mon", "tong diem may mon")):
        return None
    method = str(analysis.entities.get("admission_method") or "").casefold()
    for line in _evidence_text_lines(evidence):
        folded = normalize_question(line)
        count_match = re.search(r"\b0?(\d+)\s*mon\b", folded)
        if not count_match or "hoc bong" in folded:
            continue

        if method == "thpt":
            # The combined admissions/scholarship document contains several
            # unrelated references to ``3 môn``. Only a sentence explicitly
            # tied to the THPT graduation exam can answer this method-specific
            # question; a scholarship condition is not evidence of a method.
            if not any(marker in folded for marker in ("thi tot nghiep", "thi thpt", "thpt")):
                continue
            subject_count = int(count_match.group(1))
            return (
                "Theo phương thức thi tốt nghiệp THPT, tổ hợp xét tuyển gồm "
                f"{subject_count} môn."
            )

        if any(marker in folded for marker in ("to hop", "xet tuyen")):
            return f"Theo dữ liệu xét tuyển DHV: {line.lstrip('• ').strip()}"
    return None


def _verified_admission_conditions_section(evidence: Any, *, target_year: int) -> list[str]:
    """Return the complete general-condition section from verified source pages only."""

    grouped: dict[str, list[tuple[int, int, list[str]]]] = {}
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        parsed = urlparse(str(metadata.get("source_url") or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            year = int(metadata.get("year"))
            page = int(metadata.get("page") or 0)
            chunk_index = int(metadata.get("chunk_index") or 0)
        except (TypeError, ValueError):
            continue
        if (
            metadata.get("record_type") != "page_text"
            or str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or str(metadata.get("status") or "").casefold() != "verified"
            or year != target_year
            or parsed.scheme.lower() != "https"
            or not (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
        ):
            continue
        source = str(metadata.get("source_file") or metadata.get("document_id") or "")
        if not source:
            continue
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in str(getattr(chunk, "text", "") or "").splitlines()
            if line.strip()
        ]
        if lines:
            grouped.setdefault(source, []).append((page, chunk_index, lines))

    for source_chunks in grouped.values():
        lines: list[str] = []
        seen: set[tuple[int, str]] = set()
        for page, _, chunk_lines in sorted(source_chunks, key=lambda item: (item[0], item[1])):
            for line in chunk_lines:
                key = (page, normalize_question(line))
                if key not in seen:
                    seen.add(key)
                    lines.append(line)
        start = next(
            (index for index, line in enumerate(lines) if "dieu kien xet tuyen" in normalize_question(line)),
            None,
        )
        if start is None:
            continue
        section_lines: list[str] = []
        for line in lines[start + 1 :]:
            if re.match(r"^\d+\.\d+(?:\.\d+)*\.?\s", normalize_question(line)):
                break
            section_lines.append(line)
        blocks: list[str] = []
        current = ""
        for line in section_lines:
            if re.match(r"^\d+\.\s+", line) or normalize_question(line).startswith("rieng doi voi"):
                if current:
                    blocks.append(current.strip())
                current = line
            elif current:
                current = f"{current} {line}".strip()
            else:
                current = line
        if current:
            blocks.append(current.strip())
        if blocks:
            return blocks
    return []


def _requested_admission_method_number(analysis: QueryAnalysis) -> int | None:
    normalized = normalize_question(analysis.normalized_question)
    method = str(analysis.entities.get("admission_method") or "").casefold()
    if method == "thpt" or any(marker in normalized for marker in ("thi tot nghiep", "thi thpt", "diem thi thpt")):
        return 1
    if method == "hoc_ba" or "hoc ba" in normalized or "hoc tap thpt" in normalized:
        return 2
    if method == "dgnl" or "dgnl" in normalized or "danh gia nang luc" in normalized:
        return 3
    if method == "h_sca" or re.search(r"\bh\s*[- ]?\s*sca\b", normalized) or "nang luc chuyen biet" in normalized:
        return 4
    if method == "trung_cap" or "trung cap" in normalized:
        return 5
    return None


def _asks_for_each_admission_method(normalized: str) -> bool:
    asks_all = any(
        marker in normalized
        for marker in (
            "tung phuong thuc",
            "moi phuong thuc",
            "cac phuong thuc",
            "nhung phuong thuc",
            "tat ca phuong thuc",
            "5 phuong thuc",
        )
    )
    asks_conditions = any(
        marker in normalized
        for marker in ("dieu kien", "yeu cau", "tieu chi", "can dap ung", "chi tiet")
    )
    return asks_all and asks_conditions


def _evidence_eligibility_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    normalized = normalize_question(analysis.normalized_question)
    if not bool(analysis.entities.get("admission_condition_request")) and not any(
        marker in normalized
        for marker in ("dieu kien", "du dieu kien", "duoc tham gia xet tuyen", "co xet duoc khong", "hoc luc", "lop 12", "tot nghiep")
    ):
        return None

    target_year = int(analysis.entities.get("year") or settings.target_year)
    method_details = _method_details_from_evidence(evidence, target_year=target_year)
    labels = {
        1: "Thi tốt nghiệp THPT",
        2: "Học bạ THPT",
        3: "Đánh giá năng lực (ĐGNL)",
        4: "Đánh giá năng lực chuyên biệt (H-SCA)",
        5: "Tốt nghiệp trung cấp",
    }
    if _asks_for_each_admission_method(normalized):
        if all(number in method_details for number in range(1, 6)):
            header = "Điều kiện theo từng phương thức xét tuyển DHV 2026:\n"
            if re.search(r"\b(?:bao nhieu|may|so luong)\b.{0,16}\bphuong thuc\b", normalized):
                header = "DHV 2026 áp dụng 5 phương thức xét tuyển. " + header
            return header + "\n".join(
                f"{number}. {labels[number]}: {method_details[number]}"
                for number in range(1, 6)
            )
        return None

    major = normalize_question(str(analysis.entities.get("major_name") or ""))
    requested_method = _requested_admission_method_number(analysis)
    if requested_method and major not in {"luat", "luat kinh te"}:
        detail = method_details.get(requested_method)
        if detail:
            return (
                f"Theo phương thức {labels[requested_method]} của DHV năm {target_year}: {detail}"
            )
        return None

    blocks = _verified_admission_conditions_section(evidence, target_year=target_year)
    if len(blocks) < 3:
        return None
    general = [
        block for block in blocks
        if not normalize_question(block).startswith("rieng doi voi") and not re.match(r"^\d+\.\s+", block)
    ]
    law_intro = next(
        (block for block in blocks if normalize_question(block).startswith("rieng doi voi")),
        None,
    )
    law_conditions = [block for block in blocks if re.match(r"^\d+\.\s+", block)]
    if not general or not law_intro or len(law_conditions) < 2:
        return None

    answer_lines = ["Điều kiện chung để xét tuyển vào DHV:"]
    answer_lines.extend(f"- {item}" for item in general)
    answer_lines.append("Riêng đối với ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng đồng thời:")
    answer_lines.extend(f"- {item.split('. ', 1)[-1]}" for item in law_conditions[:2])
    student_scores = analysis.entities.get("student_scores")
    if major in {"luat", "luat kinh te"} and student_scores and any(
        marker in normalized for marker in ("hoc luc", "lop 12")
    ):
        answer_lines.append(
            "Điểm thi riêng lẻ không thay thế điều kiện về học lực lớp 12; các yêu cầu trong tài liệu phải được đáp ứng đồng thời."
        )
    return "\n".join(answer_lines)


def _evidence_law_grade_eligibility_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Resolve a stated below-Giỏi grade without asking for an unrelated score method."""

    normalized = normalize_question(analysis.normalized_question)
    major = normalize_question(str(analysis.entities.get("major_name") or ""))
    if major not in {"luat", "luat kinh te"} or not (
        "hoc luc" in normalized and "lop 12" in normalized
    ):
        return None
    stated_grade = next(
        (
            grade for grade in ("trung binh kha", "trung binh", "kha")
            if re.search(rf"\b{re.escape(grade)}\b", normalized)
        ),
        None,
    )
    if stated_grade is None:
        return None
    conditions = _verified_admission_conditions_section(
        evidence,
        target_year=int(analysis.entities.get("year") or settings.target_year),
    )
    law_conditions = [
        re.sub(r"^\d+\.\s*", "", block).strip()
        for block in conditions
        if re.match(r"^\d+\.\s+", block)
    ]
    grade_rule = next(
        (condition for condition in law_conditions if "hoc luc lop 12" in normalize_question(condition)),
        None,
    )
    if not grade_rule or "gioi tro len" not in normalize_question(grade_rule):
        return None
    grade_labels = {
        "trung binh kha": "Trung bình khá",
        "trung binh": "Trung bình",
        "kha": "Khá",
    }
    score_rule = next(
        (condition for condition in law_conditions if "tong diem" in normalize_question(condition)),
        None,
    )
    lines = [
        f"Với học lực lớp 12 loại {grade_labels[stated_grade]}, bạn chưa đáp ứng điều kiện riêng được công bố cho ngành {analysis.entities.get('major_name')}: {grade_rule}.",
        "Điểm số không thay thế điều kiện học lực; các điều kiện của ngành này phải được đáp ứng đồng thời.",
    ]
    if score_rule:
        lines.append(
            f"Điều kiện điểm THPT trong cùng nguồn là: {score_rule}"
        )
    return "\n".join(lines)


def _evidence_method_application_threshold_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Answer a named method's numeric floor only when its verified section states one."""

    if not (
        analysis.intent == "HOI_NGUONG_DAU_VAO"
        and analysis.entities.get("score_type") == "application_threshold"
        and not analysis.entities.get("student_scores")
        and analysis.entities.get("score_query_type") != "personal_score_comparison"
    ):
        return None
    method = normalize_question(str(analysis.entities.get("admission_method") or "").replace("_", " "))
    if method not in {"dgnl", "h sca", "thpt", "hoc ba"}:
        return None
    target_year = int(analysis.entities.get("year") or settings.target_year)
    method_heading = {
        "dgnl": "xet ket qua ky thi danh gia nang luc",
        "h sca": "xet ket qua bai thi danh gia nang luc chuyen biet",
        "thpt": "xet ket qua ky thi tot nghiep thpt",
        "hoc ba": "xet tuyen ket qua hoc tap thpt hoc ba",
    }[method]
    next_heading = {
        "dgnl": "xet ket qua bai thi danh gia nang luc chuyen biet",
        "h sca": "xet tuyen doi voi thi sinh tot nghiep trung cap",
        "thpt": "xet tuyen ket qua hoc tap thpt hoc ba",
        "hoc ba": "xet ket qua ky thi danh gia nang luc",
    }[method]
    if method == "dgnl":
        verified_threshold_source = any(
            str((chunk.metadata or {}).get("category") or "") == "nguong_dau_vao"
            and str((chunk.metadata or {}).get("status") or "").casefold() == "verified"
            and str((chunk.metadata or {}).get("school_code") or "").upper() == "DHV"
            and str((chunk.metadata or {}).get("year") or "") == str(target_year)
            and urlparse(str((chunk.metadata or {}).get("source_url") or "")).scheme.lower() == "https"
            and (
                (urlparse(str((chunk.metadata or {}).get("source_url") or "")).hostname or "").lower().rstrip(".")
                == "dhv.edu.vn"
                or (urlparse(str((chunk.metadata or {}).get("source_url") or "")).hostname or "").lower().rstrip(".").endswith(".dhv.edu.vn")
            )
            for chunk in getattr(evidence, "chunks", ()) or ()
        )
        verified_values = {
            str(fact.get("raw_value") or fact.get("value") or "").strip()
            for fact in getattr(evidence, "score_facts", ()) or ()
            if isinstance(fact, Mapping)
            and str(fact.get("score_type") or "") == "application_threshold"
            and normalize_question(str(fact.get("method") or "")) == "dgnl"
            and str(fact.get("category") or "") == "nguong_dau_vao"
            and str(fact.get("status") or fact.get("source_status") or "").casefold() == "verified"
            and str(fact.get("year") or "") == str(target_year)
        }
        if verified_threshold_source and len(verified_values) == 1 and re.fullmatch(
            r"\d+(?:[.,]\d+)?", next(iter(verified_values))
        ):
            value = next(iter(verified_values)).replace(".", ",")
            return (
                f"Theo phương án tuyển sinh DHV {target_year}, phương thức Đánh giá năng lực (ĐGNL) yêu cầu kết quả từ {value} điểm trở lên."
            )
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
            and str(metadata.get("category") or "") == "phuong_thuc_xet_tuyen"
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and str(metadata.get("status") or "").casefold() == "verified"
            and year == target_year
            and parsed.scheme.lower() == "https"
            and (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
        ):
            continue
        text = str(getattr(chunk, "text", "") or "")
        folded = normalize_question(text)
        start = folded.find(method_heading)
        if start < 0:
            continue
        end = folded.find(next_heading, start + len(method_heading))
        section = folded[start:] if end < 0 else folded[start:end]
        if method == "dgnl":
            match = re.search(r"(?:tu|dat|toi thieu)\s+(\d{3,4})\s+diem(?:\s+tro len)?", section)
            if match:
                return (
                    f"Theo phương án tuyển sinh DHV {target_year}, phương thức Đánh giá năng lực (ĐGNL) yêu cầu kết quả từ {match.group(1)} điểm trở lên."
                )
    return None


def _evidence_subject_minimum_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer subject-level minimums only when the source states their scope."""

    if not _is_subject_minimum_request(analysis.normalized_question):
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if metadata.get("record_type") not in {None, "page_text"}:
            continue
        text = re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or "")).strip()
        folded = normalize_question(text)
        if not all(marker in folded for marker in ("rieng doi voi", "luat", "ngu van hoac toan")):
            continue
        score_match = re.search(
            r"(?:ngu van hoac toan|toan hoac ngu van) tu (\d+(?:[.,]\d+)?) diem tro len",
            folded,
        )
        if not score_match:
            continue
        score = score_match.group(1).replace(",", ".")
        return (
            "Theo điều kiện riêng được công bố cho ngành Luật và Luật Kinh tế, "
            f"môn Toán hoặc Ngữ văn cần đạt từ {score} điểm trở lên (thang điểm 10). "
            "Điều kiện này đi kèm các yêu cầu khác của hai ngành; tài liệu không nêu "
            "mức sàn môn học này như một quy tắc chung cho mọi ngành."
        )
    return None


def _application_documents_missing_evidence(analysis: QueryAnalysis, evidence: Any) -> bool:
    """Do not present enrollment paperwork as an application-document checklist."""

    if analysis.intent != "HOI_HO_SO":
        return False
    normalized = normalize_question(analysis.normalized_question)
    if "xet tuyen" not in normalized or "nhap hoc" in normalized:
        return False
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        record_type = str(metadata.get("record_type") or "").casefold()
        if record_type in {"application_document", "registration_field"}:
            return False
        text = normalize_question(str(getattr(chunk, "text", "") or ""))
        if (
            "ho so xet tuyen" in text
            and any(marker in text for marker in ("giay to", "can nop", "don dang ky", "bao gom"))
        ):
            return False
    return True


def _evidence_required_document_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Resolve a named required document only when the verified checklist lists it."""

    if analysis.intent != "HOI_HO_SO":
        return None
    normalized = normalize_question(analysis.normalized_question)
    if not any(marker in normalized for marker in ("mang theo", "can mang", "can nop", "can chuan bi")):
        return None
    document_aliases = (
        ("giay chung nhan ket qua thi", "giấy chứng nhận kết quả thi"),
        ("hoc ba", "học bạ"),
        ("can cuoc cong dan", "căn cước công dân"),
        ("can cuoc", "căn cước"),
        ("giay khai sinh", "giấy khai sinh"),
        ("giay kham suc khoe", "giấy khám sức khỏe"),
    )
    requested = next(
        ((alias, label) for alias, label in document_aliases if alias in normalized),
        None,
    )
    if not requested:
        return None
    alias, label = requested
    supported = False
    for chunk in getattr(evidence, "chunks", ()) or ():
        chunk_text = str(getattr(chunk, "text", "") or "")
        folded = normalize_question(chunk_text)
        if alias not in folded:
            continue
        if not any(marker in folded for marker in ("mang theo", "ho so nhap hoc", "giay to sau")):
            continue
        if any(marker in folded for marker in ("khong can mang", "khong phai mang", "khong yeu cau")):
            return None
        supported = True
    if not supported:
        return None
    source_line = next(
        (
            re.sub(r"^Hồ sơ nhập học\s*:\s*", "", line.lstrip("• ").strip(), flags=re.IGNORECASE).rstrip(" .")
            for line in _evidence_text_lines(evidence)
            if alias in normalize_question(line)
        ),
        label,
    )
    return f"Có. Hướng dẫn nhập học liệt kê {source_line} trong nhóm giấy tờ cần mang theo."


def _evidence_cash_payment_answer(evidence: Any) -> str | None:
    """Answer in-person payment questions with the documented reception facts.

    The guide does not name a cash counter, so the answer says that plainly
    and gives the verified in-person reception campuses and hours instead.
    """

    lines = _evidence_text_lines(evidence)
    hours = next(
        (
            line.strip() for line in lines
            if "tiep nhan nhap hoc" in normalize_question(line)
            and re.search(r"\b\d{1,2}:\d{2}\b", line)
        ),
        None,
    )
    campuses = list(dict.fromkeys(
        match.group(0).strip(" .")
        for line in lines
        for match in [re.search(r"Cơ sở\s*[12]\s*:[^\n]+", line, re.IGNORECASE)]
        if match
    ))[:2]
    if not hours or not campuses:
        return None
    online = next(
        (
            line.strip() for line in lines
            if "unizone" in normalize_question(line) and "thanh toan" in normalize_question(line)
        ),
        None,
    )
    parts = [
        "Tài liệu nhập học DHV 2026 chưa nêu riêng quầy thu học phí bằng tiền mặt.",
        "Bạn có thể đến nhập học trực tiếp tại:",
        *(f"- {campus}" for campus in campuses),
        f"Thời gian: {hours.replace('DHV tiếp nhận nhập học', '').strip()}"
        + (" (cả Thứ Bảy, Chủ nhật và ngày lễ)." if any(
            "chu nhat" in normalize_question(line) for line in lines
        ) else "."),
    ]
    if online:
        parts.append(f"Nếu nhập học trực tuyến: {online.rstrip('.')}.")
    parts.append("Bạn nên liên hệ bộ phận tuyển sinh để xác nhận hình thức thanh toán tại cơ sở.")
    return "\n".join(parts)


def _evidence_enrollment_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Render enrollment facts from selected evidence without model synthesis.

    Enrollment records are intentionally small and heterogeneous.  A model can
    otherwise mistake a scholarship amount or a gift item for a required
    document.  This formatter only emits lines already present in verified
    evidence and uses metadata record types/pages to keep the semantic groups
    separate.
    """

    normalized = normalize_question(analysis.normalized_question)
    chunks = tuple(getattr(evidence, "chunks", ()) or ())
    request = enrollment_request(normalized)
    if request == "cash_payment":
        return _evidence_cash_payment_answer(evidence)
    if request in {"reception_hours", "reception_dates"}:
        lines = _evidence_text_lines(evidence)
        matches = []
        for index, line in enumerate(lines):
            if "tiep nhan nhap hoc" not in normalize_question(line) or not re.search(r"\b\d{1,2}:\d{2}\b", line):
                continue
            matches.append(line)
            if index + 1 < len(lines) and any(x in normalize_question(lines[index + 1]) for x in ("thu bay", "chu nhat", "ngay le")):
                matches.append(lines[index + 1])
        return "DHV tiếp nhận nhập học vào các khung thời gian sau:\n" + "\n".join(dict.fromkeys(matches)) if matches else None

    def text_for(chunk: Any) -> str:
        return str(getattr(chunk, "text", "") or "").strip()

    def metadata_for(chunk: Any) -> Mapping[str, object]:
        value = getattr(chunk, "metadata", {}) or {}
        return value if isinstance(value, Mapping) else {}

    def unique(lines: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for line in lines:
            cleaned = re.sub(r"\s+", " ", line).strip(" •")
            key = normalize_question(cleaned)
            if cleaned and key and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    if request == "enrollment_benefits":
        requested_year = int(analysis.entities.get("year") or 2026)
        rights_chunks = []
        for chunk in chunks:
            metadata = metadata_for(chunk)
            try:
                chunk_year = int(metadata.get("year"))
            except (TypeError, ValueError):
                continue
            title = normalize_question(str(metadata.get("title") or ""))
            if (
                metadata.get("status") == "verified"
                and str(metadata.get("school_code") or "").upper() == "DHV"
                and chunk_year == requested_year
                and str(metadata.get("category") or "") == "ho_so"
                and "quyen loi nhap hoc" in title
            ):
                rights_chunks.append(chunk)

        source_text = "\n".join(text_for(chunk) for chunk in rights_chunks)
        folded_source = normalize_question(source_text)
        required_facts = (
            "sau khi hoan tat nhap hoc",
            "microsoft office 365 ban quyen 01 nam",
            "word", "excel", "powerpoint", "outlook", "onedrive", "teams", "ai copilot",
            "ma so sinh vien", "balo dhv", "hop dung but", "day deo the sinh vien",
        )
        if not rights_chunks or not all(fact in folded_source for fact in required_facts):
            return None

        return (
            "Sau khi hoàn tất nhập học, tân sinh viên DHV được hưởng các quyền lợi và quà tặng sau:\n"
            "- Microsoft Office 365 bản quyền 01 năm, gồm Word, Excel, PowerPoint, Outlook, OneDrive, Teams và AI Copilot.\n"
            "- Được cấp mã số sinh viên.\n"
            "- Bộ quà tặng gồm balo DHV, hộp đựng bút và dây đeo thẻ sinh viên."
        )

    provided: set[str] = set()
    if any(marker in normalized for marker in ("con thieu", "gi nua", "con lai", "bo sung", "can them")):
        owned = re.search(r"(?<!chua )(?<!khong )(?:da )?co\s+(.+?)(?:\broi\b|\bcan\b|\bcon thieu\b)", normalized)
        if owned:
            owned_text = re.split(r"\b(?:nhung|chua|khong)\b", owned.group(1), maxsplit=1)[0]
            for aliases in (("hoc ba",), ("can cuoc", "cccd"), ("thu moi", "tin nhan zalo"), ("giay chung nhan ket qua thi",)):
                if any(re.search(rf"\b{re.escape(alias)}\b", owned_text) for alias in aliases):
                    provided.add(aliases[0])

    named_document_condition = any(
        alias in normalized
        for alias in (
            "hoc ba", "can cuoc", "cccd", "thu moi", "tin nhan zalo",
            "giay chung nhan ket qua thi", "giay khai sinh", "giay kham suc khoe",
        )
    ) and any(marker in normalized for marker in ("cong chung", "ban goc", "co can", "can mang", "mang theo"))

    # The approved 2026 corpus stores the checklist as one verified
    # ``document_text`` record (not legacy ``enrollment_document`` records).
    # Read only the dedicated checklist source and its explicit bullet list;
    # otherwise a generic question such as "Hồ sơ cần gì?" falls through to
    # the language model, which can echo the whole procedure document.
    if request == "documents":
        checklist_lines: list[str] = []
        checklist_note = ""
        for chunk in chunks:
            metadata = metadata_for(chunk)
            try:
                chunk_year = int(metadata.get("year"))
            except (TypeError, ValueError):
                continue
            title = normalize_question(str(metadata.get("title") or ""))
            if not (
                metadata.get("status") == "verified"
                and str(metadata.get("school_code") or "").upper() == "DHV"
                and chunk_year == int(analysis.entities.get("year") or 2026)
                and str(metadata.get("category") or "") == "ho_so"
                and "ho so can chuan bi khi nhap hoc" in title
            ):
                continue
            in_checklist = False
            for raw_line in text_for(chunk).splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                folded = normalize_question(line)
                if not line:
                    continue
                if "vui long mang theo" in folded and "giay to sau" in folded:
                    in_checklist = True
                    continue
                if folded.startswith("luu y"):
                    if "ban goc" in folded and "khong can cong chung" in folded:
                        checklist_note = "Lưu ý: mang bản gốc để đối chiếu, không cần công chứng."
                    in_checklist = False
                    continue
                if in_checklist and re.match(r"^[•*–-]\s*", line):
                    checklist_lines.append(re.sub(r"^[•*–-]\s*", "", line).rstrip(" ."))
        checklist_lines = unique(checklist_lines)
        if named_document_condition and checklist_lines:
            requested_aliases = (
                ("giay chung nhan ket qua thi",),
                ("hoc ba",),
                ("can cuoc cong dan", "can cuoc", "cccd"),
                ("giay khai sinh",),
                ("giay kham suc khoe",),
            )
            requested_item = next(
                (aliases for aliases in requested_aliases if any(alias in normalized for alias in aliases)),
                (),
            )
            matched_item = next(
                (
                    line for line in checklist_lines
                    if any(alias in normalize_question(line) for alias in requested_item)
                ),
                None,
            ) if requested_item else None
            if matched_item:
                if "cong chung" in normalized and "khong can cong chung" in normalize_question(checklist_note):
                    return f"Với {matched_item.rstrip(' .')}, bạn mang bản gốc để đối chiếu, không cần công chứng."
                return f"Có. {matched_item.rstrip(' .')} nằm trong danh sách giấy tờ cần chuẩn bị khi nhập học."
            if requested_item:
                return None
        if provided:
            checklist_lines = [
                line for line in checklist_lines
                if not any(
                    re.search(rf"\b{re.escape(alias)}\b", normalize_question(line))
                    for item in provided
                    for alias in (item, "cccd" if item == "can cuoc" else item)
                )
            ]
        if checklist_lines and not named_document_condition:
            operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
            if operation == "COUNT":
                answer = f"Hồ sơ nhập học DHV {analysis.entities.get('year') or 2026} cần chuẩn bị {len(checklist_lines)} loại giấy tờ."
            elif operation == "LIST_AND_COUNT":
                answer = (
                    f"Hồ sơ nhập học DHV {analysis.entities.get('year') or 2026} cần chuẩn bị "
                    f"{len(checklist_lines)} loại giấy tờ:\n"
                    + "\n".join(f"- {line}" for line in checklist_lines)
                )
            else:
                heading = "Bạn cần bổ sung các giấy tờ sau:" if provided else "Hồ sơ nhập học DHV 2026 cần chuẩn bị:"
                answer = heading + "\n" + "\n".join(
                    f"- {line}" for line in checklist_lines
                )
            if checklist_note:
                answer += "\n" + checklist_note
            return answer
        if provided:
            answer = "Theo danh sách đã kiểm tra, bạn đã có các giấy tờ được nêu."
            if checklist_note:
                answer += " " + checklist_note
            return answer

    if "uu dai cao nhat" in normalized and any(
        marker in normalized for marker in ("hoan tat xac nhan", "xac nhan truoc moc", "xac nhan truoc ngay")
    ):
        requested_year = int(analysis.entities.get("year") or 2026)
        for chunk in chunks:
            metadata = metadata_for(chunk)
            if (
                str(metadata.get("status") or "") != "verified"
                or str(metadata.get("school_code") or "").upper() != "DHV"
                or int(metadata.get("year") or requested_year) != requested_year
                or str(metadata.get("category") or "") not in {"ho_so", "nhap_hoc"}
            ):
                continue
            for sentence in _split_source_sentences(text_for(chunk)):
                folded = normalize_question(sentence)
                if not (
                    "uu dai cao nhat" in folded
                    and "hoan tat xac nhan" in folded
                    and "truoc ngay" in folded
                ):
                    continue
                date_match = re.search(r"\b\d{1,2}/\d{1,2}(?:/20\d{2})?\b", sentence)
                if date_match:
                    return (
                        f"Theo hướng dẫn nhập học DHV {requested_year}, cần hoàn tất xác nhận "
                        f"trước ngày {date_match.group(0)} để hưởng mức ưu đãi cao nhất."
                    )

    if ("nop ho so" in normalized or request == "enrollment_location") and "dong tien" not in normalized and "xet tuyen" not in normalized and any(
        marker in normalized for marker in ("co so nao", "o dau", "dia chi nao")
    ):
        locations = unique([
            line
            for line in _evidence_text_lines(evidence)
            if re.search(r"\bCơ sở\s*[12]\s*:", line, re.IGNORECASE)
        ])
        if locations:
            return "Bạn có thể nộp hồ sơ nhập học tại một trong hai cơ sở của DHV:\n" + "\n".join(
                f"- {line}" for line in locations[:2]
            )
        return None

    document_answer = None if provided else _evidence_required_document_answer(analysis, evidence)
    if document_answer:
        return document_answer

    if (
        analysis.intent == "HOI_LICH_TUYEN_SINH"
        and "tiep nhan tan sinh vien" in normalized
    ):
        intake_lines = [
            line for line in _evidence_text_lines(evidence)
            if "tiep nhan nhap hoc" in normalize_question(line)
            and re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\b", line)
        ]
        if intake_lines:
            return "Tài liệu nhập học DHV ghi thời gian tiếp nhận tân sinh viên: " + intake_lines[0]

    if "dong tien mat" in normalized:
        source_lines = _evidence_text_lines(evidence)
        locations = unique(
            [line for line in source_lines if re.search(r"\bCơ sở\s*[12]\s*:", line, re.IGNORECASE)]
        )
        schedules = unique(
            [
                line for line in source_lines
                if re.search(r"\b\d{1,2}:\d{2}\b", line)
                and re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", line)
            ]
        )
        if locations or schedules:
            parts = [
                "Mình chưa có thông tin cụ thể về quầy thu tiền mặt."
            ]
            if locations:
                parts.append("Địa điểm tiếp nhận nhập học được công bố:\n" + "\n".join(f"- {line}" for line in locations[:2]))
            if schedules:
                parts.append("Thời gian tiếp nhận:\n" + "\n".join(f"- {line}" for line in schedules[:2]))
            return "\n".join(parts)

    if any(marker in normalized for marker in ("he thong cua bo", "he thong ho tro tuyen sinh chung", "xac nhan tren he thong")):
        confirmation_lines = unique(
            [
                sentence
                for sentence in _evidence_sentences(evidence)
                if "he thong" in normalize_question(sentence)
                and any(marker in normalize_question(sentence) for marker in (
                    "xac nhan", "bo giao duc", "tuyen sinh chung",
                ))
            ]
        )
        confirmation_lines = [_remove_unresolved_url_label(line) for line in confirmation_lines]
        if confirmation_lines:
            return "Về xác nhận trúng tuyển/nhập học trên hệ thống của Bộ, tài liệu DHV ghi:\n" + "\n".join(
                f"- {line}" for line in confirmation_lines[:4]
            )

    if request == "submission_mode" or any(marker in normalized for marker in ("o xa", "nhap hoc truc tuyen", "nhap hoc online", "chua den truong ngay")):
        online_lines = unique([
            sentence
            for sentence in _evidence_sentences(evidence)
            if (
                "truc tuyen" in normalize_question(sentence)
                or "unizone" in normalize_question(sentence)
            )
            and any(
                marker in normalize_question(sentence)
                for marker in ("nhap hoc", "hoan tat thu tuc", "tan sinh vien", "thanh toan hoc phi")
            )
        ])
        if online_lines:
            return "Tài liệu nhập học DHV có nêu hình thức trực tuyến:\n" + "\n".join(
                f"- {line}" for line in online_lines[:4]
            )

    if any(marker in normalized for marker in ("cong bo o dau", "thong tin chi tiet", "huong dan nhap hoc")):
        guide = next(
            (
                str(metadata_for(chunk).get("title") or "").strip()
                for chunk in chunks
                if str(metadata_for(chunk).get("category") or "") == "ho_so"
            ),
            "",
        )
        if guide:
            return f"Hướng dẫn chi tiết có trong tài liệu chính thức DHV: {guide}. Nguồn chính thức được đính kèm cùng câu trả lời."

    if any(marker in normalized for marker in ("khi nao", "thoi gian", "moc nao")):
        timing_lines: list[str] = []
        reception_markers = (
            "tiep nhan nhap hoc", "thoi gian tiep nhan nhap hoc",
            "nhap hoc truc tiep", "ngay tuu truong",
        )
        for chunk in chunks:
            text = text_for(chunk)
            folded = normalize_question(text)
            if not any(marker in folded for marker in ("nhap hoc", "xac nhan nhap hoc", "tuu truong", "tiep nhan nhap hoc")):
                continue
            for line in text.splitlines():
                line = line.strip()
                line_folded = normalize_question(line)
                if not any(marker in line_folded for marker in reception_markers):
                    continue
                has_timing_signal = bool(
                    re.search(r"\b\d{1,2}[/:]\d{1,2}(?:[/:-]\d{2,4})?\b", line)
                    or any(
                        marker in line_folded
                        for marker in (
                            "xuyen suot",
                            "hoan tat xac nhan",
                            "ngay tuu truong",
                            "tiep nhan nhap hoc",
                        )
                    )
                )
                if has_timing_signal and not any(
                    marker in line_folded
                    for marker in ("thoi han ap dung chinh sach", "nguyen vong", "hoc bong")
                ):
                    timing_lines.append(line)
        timing_lines = unique(timing_lines)
        if timing_lines:
            return "Các mốc nhập học có trong dữ liệu DHV 2026:\n" + "\n".join(
                f"- {line}" for line in timing_lines[:8]
            )

    if any(marker in normalized for marker in ("phi nhap hoc", "hoc lieu")):
        fee_lines: list[str] = []
        for chunk in chunks:
            text = text_for(chunk)
            for line in text.splitlines():
                folded = normalize_question(line)
                has_amount = bool(re.search(r"\d[\d.,]*\s*(?:đồng|dong|vnd)\b", line, re.IGNORECASE))
                if has_amount and ("phi nhap hoc" in folded or "tai khoan hoc lieu dien tu" in folded):
                    fee_lines.append(line)
        fee_lines = unique(fee_lines)
        if fee_lines:
            return "Các khoản liên quan đến nhập học:\n" + "\n".join(
                f"- {line}" for line in fee_lines[:6]
            )

    if "nhap hoc" not in normalized and request != "documents":
        return None

    document_lines: list[str] = []
    for chunk in chunks:
        metadata = metadata_for(chunk)
        if str(metadata.get("record_type") or "") != "enrollment_document":
            continue
        try:
            page = int(metadata.get("page", 0))
        except (TypeError, ValueError):
            page = 0
        if page != 3:
            continue
        text = text_for(chunk)
        value = text.split("Hồ sơ nhập học:", 1)[-1].strip()
        if not value or "co so" in normalize_question(value):
            continue
        document_lines.append(value)
    document_lines = unique(document_lines)
    if document_lines:
        if any(marker in normalized for marker in ("cong chung", "ban goc", "ban sao")):
            named = [line for line in document_lines if any(
                re.search(rf"\b{re.escape(alias)}\b", normalized)
                and re.search(rf"\b{re.escape(alias)}\b", normalize_question(line))
                for alias in ("hoc ba", "can cuoc", "thu moi", "giay chung nhan ket qua thi")
            )]
            if len(named) == 1 and any("ban goc" in normalize_question(text_for(chunk)) and
                                       "khong can cong chung" in normalize_question(text_for(chunk)) for chunk in chunks):
                return f"Với {named[0].rstrip(' .')}, bạn mang bản gốc để đối chiếu, không cần công chứng."
        if provided:
            remaining = [line for line in document_lines if not any(
                re.search(rf"\b{re.escape(alias)}\b", normalize_question(line)) for alias in provided
            )]
            if remaining:
                document_lines = remaining
            else:
                return "Bạn đã có các giấy tờ trong danh sách nhập học: " + "; ".join(document_lines) + ". Bạn nhớ mang bản gốc để đối chiếu nhé."
        count = len(document_lines)
        operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
        
        if operation == "COUNT":
            answer = f"Hồ sơ nhập học DHV 2026 cần chuẩn bị {count} loại giấy tờ/khoản mục chính."
        elif operation == "LIST_AND_COUNT":
            answer = f"Hồ sơ nhập học DHV 2026 cần chuẩn bị {count} loại giấy tờ/khoản mục chính:\n" + "\n".join(
                f"- {line}" for line in document_lines
            )
        else:
            heading = "Bạn cần bổ sung các giấy tờ sau:" if provided else "Bạn mang các giấy tờ sau:" if "nhac lai ngan gon" in normalized else "Hồ sơ nhập học DHV 2026 cần chuẩn bị:"
            answer = heading + "\n" + "\n".join(
                f"- {line}" for line in document_lines
            )
        note_lines: list[str] = []
        for chunk in chunks:
            text = text_for(chunk)
            folded = normalize_question(text)
            if "ban goc" in folded and "khong can cong chung" in folded:
                note_lines.append("Lưu ý: mang bản gốc để đối chiếu, không cần công chứng.")
                break
        if note_lines:
            answer += "\n" + "\n".join(note_lines)
        return answer
    return None


def _evidence_admission_bonus_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Return only the evidence line matching the requested admission bonus."""

    normalized = normalize_question(analysis.normalized_question)
    sentences = _evidence_sentences(evidence)
    if any(marker in normalized for marker in ("mos", "icdl", "ic3", "chung chi tin hoc")):
        for line in sentences:
            folded = normalize_question(line)
            if any(name in folded for name in ("mos", "icdl", "ic3")) and "cong 1,50 diem" in folded:
                return f"Theo chính sách tuyển sinh DHV: {line.lstrip('• ').strip()}"
    award_markers = {
        "1,50": ("giai nhat", "giai nhi", "khuyen khich cap quoc gia", "quoc gia tro len"),
        "1,00": ("giai ba", "khuyen khich cap tinh", "cap tinh/thanh pho"),
        "0,50": ("cap truong",),
    }
    asks_award = any(marker in normalized for marker in ("giai", "hoc sinh gioi", "cap quoc gia", "cap tinh", "cap truong"))
    if asks_award:
        award_bullets: list[str] = []
        for chunk in getattr(evidence, "chunks", ()) or ():
            current = ""
            for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue
                if line.startswith(("•", "-", "–")):
                    if current:
                        award_bullets.append(current)
                    current = line.lstrip("•-– ").strip()
                elif current:
                    current_folded = normalize_question(current)
                    if "+" in current and "diem" not in current_folded and normalize_question(line) == "diem":
                        current = f"{current} {line}"
                    else:
                        award_bullets.append(current)
                        current = ""
                        if re.match(r"^\d+(?:\.\d+)*\.", line):
                            break
            if current:
                award_bullets.append(current)
        for line in award_bullets:
            folded = normalize_question(line)
            for amount, markers in award_markers.items():
                if any(marker in normalized for marker in markers) and amount in folded and any(
                    marker in folded for marker in ("giai", "quoc gia", "cap tinh", "cap truong")
                ):
                    return f"Theo chính sách tuyển sinh DHV: {line.lstrip('• ').strip()}"
    return None


def _evidence_formula_answer(evidence: Any) -> str | None:
    lines = _evidence_text_lines(evidence)
    formula_lines = [
        line
        for line in lines
        if line.lower().startswith("• cách ")
        or line.lower().startswith("cách ")
        or line.lower().startswith("• điểm xét tuyển được tính")
        or line.lower().startswith("điểm xét tuyển được tính")
    ]
    if not formula_lines:
        return None
    return "Cách tính điểm xét tuyển được công bố:\n" + "\n".join(
        f"- {line.lstrip('• ').strip()}" for line in formula_lines
    )


def _evidence_admission_combination_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    normalized = normalize_question(analysis.normalized_question)
    if not (
        any(marker in normalized for marker in ("to hop mon", "to hop xet tuyen"))
        or analysis.entities.get("admission_combination_detail")
    ):
        return None
    official_structures: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("record_type") or "") != "page_text"
            or str(metadata.get("page") or "") != "4"
        ):
            continue
        current = ""
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            bullet_text = line.lstrip("•*-– ").strip()
            folded = normalize_question(bullet_text)
            if re.match(r"^(?:toan|ngu van)\s*\+\s*0?2 mon co diem cao nhat", folded):
                if current:
                    official_structures.append(current)
                current = bullet_text
            elif current and line:
                if re.match(
                    r"^(?:cac to hop|viec dang ky|thoi gian dang ky|nguyen tac chung|phuong thuc|1\.\d+\.)",
                    folded,
                ):
                    official_structures.append(current)
                    current = ""
                else:
                    current = f"{current} {line}"
        if current:
            official_structures.append(current)
        if len(official_structures) >= 2:
            break
    if official_structures:
        intro = (
            "Có. DHV xét tuyển theo hai cấu trúc tổ hợp:\n"
            if analysis.entities.get("admission_combination_detail")
            else "DHV xét tuyển theo hai cấu trúc tổ hợp:\n"
        )
        return intro + "\n".join(
            f"- {structure}" for structure in official_structures[:2]
        )
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_bullet = ""

    def flush_section() -> None:
        nonlocal current_bullet
        if current_bullet:
            label = current_heading.strip()
            sections.append((label, re.sub(r"\s+", " ", current_bullet).strip()))
            current_bullet = ""

    for chunk in getattr(evidence, "chunks", ()) or ():
        for line in str(getattr(chunk, "text", "") or "").splitlines():
            cleaned = re.sub(r"\s+", " ", line).strip()
            if not cleaned:
                continue
            folded = normalize_question(cleaned)
            if folded.startswith("khoi "):
                flush_section()
                current_heading = cleaned.rstrip(":")
            elif cleaned.startswith(("•", "-", "–")):
                flush_section()
                if any(marker in folded for marker in ("toan + 2 mon diem cao nhat", "chon 1 trong 2")):
                    current_bullet = cleaned.lstrip("•-– ").strip()
            elif current_bullet and (
                current_bullet.rstrip().endswith((",", ":", "("))
                or current_bullet.count("(") > current_bullet.count(")")
            ):
                # Keep only a genuine PDF line-wrap continuation. Once the
                # sentence is complete, unrelated headings/facts terminate it.
                if re.match(
                    r"^(?:nganh\b|phuong thuc\b|nguong\b|rieng doi voi\b|diem\b|hoc phi\b|hoc bong\b|ho so\b)",
                    folded,
                ):
                    flush_section()
                    current_heading = ""
                else:
                    current_bullet = f"{current_bullet} {cleaned}"
            else:
                flush_section()
                current_heading = ""
    flush_section()
    if not sections:
        return None
    if any(marker in normalized for marker in ("nhung mon nao", "gom nhung mon", "cac mon", "to hop mon")):
        return "Các cấu trúc tổ hợp xét tuyển của DHV gồm:\n" + "\n".join(
            f"- {heading}: {bullet}" if heading else f"- {bullet}"
            for heading, bullet in sections
        )
    heading, bullet = sections[0]
    return "" + (f"{heading}: " if heading else "") + bullet


def _evidence_admission_method_presence_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Confirm an explicitly requested/inherited method only from its verified DHV row."""

    method = normalize_question(
        str(analysis.entities.get("admission_method") or "").replace("_", " ")
    )
    method_markers = {
        "hoc ba": (
            "xet tuyen ket qua hoc tap thpt",
            "xet ket qua hoc tap thpt",
        ),
        "thpt": (
            "xet ket qua ky thi tot nghiep thpt",
            "xet tuyen bang ket qua ky thi tot nghiep thpt",
        ),
        "dgnl": (
            "xet ket qua ky thi danh gia nang luc",
            "danh gia nang luc dgnl",
        ),
        "hsca": (
            "danh gia nang luc chuyen biet",
            "h-sca",
        ),
        "trung cap": (
            "thi sinh tot nghiep trung cap",
            "xet tuyen doi voi thi sinh tot nghiep trung cap",
        ),
    }
    key = next((candidate for candidate in method_markers if candidate in method), None)
    if key is None:
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("status") or "") != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
        ):
            continue
        text = normalize_question(str(getattr(chunk, "text", "") or ""))
        if any(marker in text for marker in method_markers[key]):
            labels = {
                "hoc ba": "kết quả học tập THPT (học bạ)",
                "thpt": "kết quả kỳ thi tốt nghiệp THPT",
                "dgnl": "kỳ thi Đánh giá năng lực",
                "hsca": "bài thi Đánh giá năng lực chuyên biệt (H-SCA)",
                "trung cap": "thí sinh tốt nghiệp trung cấp",
            }
            return f"Có. DHV có phương thức xét tuyển theo {labels[key]} trong phương án tuyển sinh 2026."
    return None


def _evidence_method_calculation_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Return the published method formula for paraphrased calculation questions."""

    normalized = normalize_question(analysis.normalized_question)
    method = str(analysis.entities.get("admission_method") or "")
    if (
        analysis.intent not in {"HOI_PHUONG_THUC_XET_TUYEN", "HOI_CACH_TINH_DIEM"}
        or method not in {"thpt", "hoc_ba"}
        or not any(
            marker in normalized
            for marker in (
                "tinh diem",
                "diem duoc tinh",
                "tinh the nao",
                "diem nhu nao",
                "xet diem nhu nao",
                "diem tinh nhu nao",
                "ca ba nam",
                "ba nam",
                "binh quan",
                "diem trung binh",
            )
        )
    ):
        return None
    detail = _method_details_from_evidence(
        evidence,
        target_year=int(analysis.entities.get("year") or settings.target_year),
    ).get(1 if method == "thpt" else 2)
    if not detail:
        if method == "thpt":
            return None
        # Retrieval for one named method may return the exact page-4 method
        # subsection but omit the section heading on page 3. Extract only the
        # explicitly labelled học-bạ method from verified DHV page text; do
        # not fall back to similarly worded scholarship formulas.
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
                and str(metadata.get("category") or "") == "phuong_thuc_xet_tuyen"
                and str(metadata.get("school_code") or "").upper() == "DHV"
                and str(metadata.get("status") or "").casefold() == "verified"
                and year == int(analysis.entities.get("year") or settings.target_year)
                and parsed.scheme.lower() == "https"
                and (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
            ):
                continue
            source_text = str(getattr(chunk, "text", "") or "")
            source_text = source_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
            lines = [
                re.sub(r"\s+", " ", line).strip()
                for line in source_text.splitlines()
                if line.strip()
            ]
            start = next(
                (
                    index for index, line in enumerate(lines)
                    if "xet tuyen ket qua hoc tap thpt hoc ba"
                    in re.sub(r"[^a-z0-9]+", " ", normalize_question(line)).strip()
                ),
                None,
            )
            if start is None:
                continue
            end = next(
                (
                    index for index in range(start + 1, len(lines))
                    if re.match(
                        r"^(?:c[.)]?\s*|\d+(?:\.\d+)*\.?\s+)xet ket qua ky thi danh gia nang luc\b",
                        normalize_question(lines[index]),
                    )
                ),
                len(lines),
            )
            section = lines[start + 1:end]
            if section:
                detail = "\n".join(section)
                break
    if not detail:
        return None
    detail = detail.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    method_label = (
        "kết quả kỳ thi tốt nghiệp THPT"
        if method == "thpt"
        else "xét tuyển học bạ"
    )
    if method == "hoc_ba":
        detail_lines = [line.strip() for line in detail.splitlines() if line.strip()]
        formula_items = [
            line.lstrip("-• ").strip()
            for line in detail_lines
            if line.lstrip().startswith(("-", "•"))
        ]
        if len(formula_items) == 2:
            context_lines = [
                line for line in detail_lines
                if not line.lstrip().startswith(("-", "•"))
            ]
            detail = "\n".join(
                [*context_lines, f"- Cách 1: {formula_items[0]}", f"- Cách 2: {formula_items[1]}"]
            )
    return (
        f"Theo phương thức {method_label} DHV "
        f"{analysis.entities.get('year') or settings.target_year}: {detail}"
    )


def _evidence_vocational_same_group_eligibility_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Answer the vocational same-group admission condition from Method 5 only."""

    normalized = normalize_question(analysis.normalized_question)
    if not (
        "trung cap" in normalized
        and "cung nhom nganh" in normalized
        and any(marker in normalized for marker in ("co the vao", "du dieu kien", "xet tuyen", "dang ky"))
    ):
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "phuong_thuc_xet_tuyen"
            or str(metadata.get("record_type") or "") != "page_text"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").strip().upper() != "DHV"
        ):
            continue
        try:
            if int(metadata.get("year", 0)) != settings.target_year:
                continue
        except (TypeError, ValueError):
            continue
        source_url = str(metadata.get("source_url") or "").strip()
        parsed_source = urlparse(source_url)
        source_host = (parsed_source.hostname or "").lower().rstrip(".")
        if (
            parsed_source.scheme.lower() != "https"
            or not source_host
            or not (source_host == "dhv.edu.vn" or source_host.endswith(".dhv.edu.vn"))
        ):
            continue
        source_text = normalize_question(str(getattr(chunk, "text", "") or ""))
        required_conditions = (
            "trung cap nghe cung nhom nganh du tuyen dai hoc",
            "hoan thanh chuong trinh van hoa thpt theo quy dinh",
        )
        if all(condition in source_text for condition in required_conditions):
            return (
                "Phương thức 5 của DHV áp dụng đối với thí sinh đã tốt nghiệp trung cấp nghề "
                "cùng nhóm ngành dự tuyển đại học và đã hoàn thành chương trình văn hóa THPT "
                "theo quy định."
            )
    return None


def _evidence_major_eligibility_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer a specific Law-grade eligibility question from the published rule."""

    normalized = normalize_question(analysis.normalized_question)
    major = normalize_question(str(analysis.entities.get("major_name") or ""))
    if major in {"luat", "luat kinh te"}:
        complete_answer = _evidence_eligibility_answer(analysis, evidence)
        if complete_answer:
            return complete_answer
    if major not in {"luat", "luat kinh te"} or not any(
        marker in normalized for marker in ("hoc luc", "lop 12")
    ):
        return None
    required_markers = (
        "luat", "hoc luc lop 12", "tong diem 03 mon", "ngu van hoac toan"
    )
    conditions: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if metadata.get("record_type") not in {None, "page_text"}:
            continue
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in str(getattr(chunk, "text", "") or "").splitlines()
        ]
        folded_chunk = normalize_question(" ".join(lines))
        if not all(marker in folded_chunk for marker in required_markers):
            continue
        active = False
        current = ""
        for line in lines:
            folded = normalize_question(line)
            if "rieng doi voi" in folded and "nganh luat" in folded and "dieu kien" in folded:
                active = True
                continue
            if not active:
                continue
            if re.match(r"^\d+(?:\.\d+)+\.", line):
                if current:
                    conditions.append(current)
                break
            if line.startswith(("•", "-", "–")):
                if current:
                    conditions.append(current)
                current = line.lstrip("•-– ").strip()
            elif current:
                current = f"{current} {line}"
        if current:
            conditions.append(current)
        if len(conditions) >= 2:
            break
    # A PDF line can run into the next numbered heading ("... 6 điểm trở lên
    # 2 Các phương thức xét tuyển ..."); keep only the condition itself.
    conditions = [
        re.split(r"\s+\d+\s+(?=[A-ZĐ][a-zà-ỹ]*\s)", condition, maxsplit=1)[0].strip()
        for condition in conditions
        if condition
    ]
    if len(conditions) < 2:
        return None
    return (
        "Với ngành Luật, tài liệu tuyển sinh yêu cầu đồng thời:\n"
        + "\n".join(f"- {condition.strip(' •')}" for condition in dict.fromkeys(conditions[:2]))
        + "\nĐiểm thi riêng lẻ không thay thế điều kiện học lực lớp 12; các yêu cầu trong tài liệu phải được đáp ứng đồng thời."
    )


def _method_label(method: object) -> str:
    return {
        "thpt": "thi tốt nghiệp THPT",
        "hoc_ba": "học bạ",
        "dgnl": "ĐGNL",
        "deadline": "hạn xét tuyển bổ sung",
    }.get(str(method or ""), str(method or "phương thức"))


def _evidence_schedule_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    lines = _evidence_text_lines(evidence)
    timing_lines = []
    seen = set()
    for line in lines:
        folded = normalize_question(line)
        if any(marker in folded for marker in ("thoi gian", "ngay", "han", "tu ngay", "den ngay")):
            if re.search(r"\d{1,2}[/:]\d{1,2}", line) and line not in seen:
                seen.add(line)
                timing_lines.append(line)
                
    if not timing_lines:
        return None
        
    count = len(timing_lines)
    operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
    
    if operation == "COUNT":
        return f"Có {count} mốc thời gian chính."
    elif operation == "LIST_AND_COUNT":
        return f"Có {count} mốc thời gian chính:\n" + "\n".join(
            f"- {line}" for line in timing_lines
        )
    return "Các mốc tuyển sinh DHV gồm:\n" + "\n".join(
        f"- {line}" for line in timing_lines
    )


def _evidence_supplementary_majors_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    if analysis.intent != "HOI_XET_TUYEN_BO_SUNG":
        return None
    normalized = normalize_question(analysis.normalized_question)
    if not any(marker in normalized for marker in ("nganh nao", "nhung nganh", "chuong trinh nao", "nhung chuong trinh")):
        return None
    names: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        raw_text = str(getattr(chunk, "text", "") or "")
        flattened = re.sub(r"\s+", " ", raw_text)
        match = re.search(
            r"\bgồm\s*:\s*(?P<names>.+?)(?:\.\s*(?=(?:Với|Đối với|Phương thức|Bảng|$)))",
            flattened,
            re.IGNORECASE,
        )
        if not match:
            continue
        names_text = match.group("names")
        leading_items, conjunction, final_item = names_text.rpartition(" và ")
        if conjunction:
            raw_names = leading_items.split(",") + [final_item]
        else:
            raw_names = names_text.split(",")
        parsed = [
            re.sub(r"\s+", " ", value).strip(" .;–-\t")
            for value in raw_names
        ]
        parsed = [value for value in parsed if value and not re.fullmatch(r"\d+(?:[.,]\d+)?", value)]
        if len(parsed) >= 2:
            names = list(dict.fromkeys(parsed))
            break
    for fact in getattr(evidence, "score_facts", ()) or ():
        if names:
            break
        if not isinstance(fact, Mapping):
            continue
        if not (
            fact.get("status") == "verified"
            or fact.get("source_status") == "verified"
            or fact.get("verified") is True
        ):
            continue
        if fact.get("score_type") != "supplementary_threshold":
            continue
        name = str(fact.get("major_name") or "").strip()
        if name and normalize_question(name) not in {normalize_question(value) for value in names}:
            names.append(name)
    if not names:
        return None
    operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
    if operation == "COUNT":
        return f"Theo dữ liệu xét tuyển bổ sung DHV 2026, có {len(names)} ngành được ghi nhận."
    if any(
        "chuong trinh" in normalize_question(str(getattr(chunk, "text", "") or ""))
        and len(names) >= 2
        for chunk in getattr(evidence, "chunks", ()) or ()
    ):
        return (
            f"Các chương trình có trong đợt xét tuyển bổ sung DHV 2026 ({len(names)} chương trình):\n"
            + "\n".join(f"{index}. {name}" for index, name in enumerate(names, start=1))
        )
    return (
        f"Các ngành có dữ liệu xét tuyển bổ sung DHV 2026 ({len(names)} ngành):\n"
        + "\n".join(f"{index}. {name}" for index, name in enumerate(names, start=1))
    )


def _evidence_score_list_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    entities = analysis.entities
    if entities.get("entity_type") != "major_list":
        return None
    candidates = [str(value).strip() for value in entities.get("candidate_majors", ()) if str(value).strip()]
    score_type = str(entities.get("score_type") or "")
    requested_method = str(entities.get("admission_method") or "")
    candidate_methods = entities.get("candidate_methods") or ()
    filter_method = bool(requested_method and len(candidate_methods) <= 1)
    normalized_question = normalize_question(analysis.normalized_question)
    explicit_all_major_request = any(
        marker in normalized_question
        for marker in ("tat ca cac nganh", "toan bo cac nganh")
    )
    if not candidates and explicit_all_major_request:
        for fact in getattr(evidence, "score_facts", ()) or ():
            if not isinstance(fact, Mapping) or fact.get("score_type") != score_type:
                continue
            if not (
                fact.get("status") == "verified"
                or fact.get("source_status") == "verified"
                or fact.get("verified") is True
            ):
                continue
            name = str(fact.get("major_name") or "").strip()
            if name and normalize_entity_name(name) not in {
                normalize_entity_name(value) for value in candidates
            }:
                candidates.append(name)
    if len(candidates) < 2 or not score_type:
        return None
    candidate_by_fold = {normalize_entity_name(name): name for name in candidates}
    grouped: dict[str, list[tuple[str, str]]] = {name: [] for name in candidates}
    major_codes: dict[str, str] = {}
    for fact in getattr(evidence, "score_facts", ()) or ():
        if not isinstance(fact, Mapping):
            continue
        if not (
            fact.get("status") == "verified"
            or fact.get("source_status") == "verified"
            or fact.get("verified") is True
        ) or fact.get("score_type") != score_type:
            continue
        method = str(fact.get("method") or "")
        if not method or method == "deadline":
            continue
        if filter_method and method != requested_method:
            continue
        candidate = candidate_by_fold.get(
            normalize_entity_name(str(fact.get("major_name") or ""))
        )
        if not candidate:
            continue
        code = str(fact.get("major_code") or "").strip()
        if code:
            major_codes.setdefault(candidate, code)
        raw_value = str(fact.get("raw_value") or "").strip()
        if not raw_value:
            continue
        row = (_method_label(method), "chưa công bố" if raw_value == "-" else f"{raw_value} điểm")
        if row not in grouped[candidate]:
            grouped[candidate].append(row)
    if any(not grouped[name] for name in candidates):
        return None
    method_order = ("thi tốt nghiệp THPT", "học bạ", "ĐGNL")
    available_methods = {
        method for values in grouped.values() for method, _ in values
    }
    methods = [method for method in method_order if method in available_methods]
    methods.extend(sorted(available_methods - set(method_order)))
    name_column = "Ngành" if entities.get("candidate_majors") else "Tên mã xét tuyển"
    rows = [
        f"| {name_column} | Mã xét tuyển | " + " | ".join(methods) + " |",
        "|---|---|" + "---|" * len(methods),
    ]
    for candidate in candidates:
        by_method = dict(grouped[candidate])
        values = [by_method.get(method, "-") for method in methods]
        rows.append(
            "| " + candidate + " | " + major_codes.get(candidate, "-") + " | "
            + " | ".join(values) + " |"
        )
    if score_type == "admission_score":
        scope = (
            "các ngành bạn vừa xem"
            if entities.get("candidate_majors")
            else "theo mã xét tuyển"
        )
        return (
            f"Điểm trúng tuyển đợt 1 năm 2026 {scope}:\n"
            + "\n".join(rows)
            + "\n\nLưu ý: đây là điểm trúng tuyển theo từng phương thức, không phải ngưỡng chung để nộp hồ sơ."
        )
    return "Ngưỡng nhận hồ sơ của các ngành bạn vừa hỏi:\n" + "\n".join(rows)


def _is_verified_fact(fact: Mapping[str, object]) -> bool:
    return (
        fact.get("status") == "verified"
        or fact.get("source_status") == "verified"
        or fact.get("verified") is True
    )


def _admission_score_overview_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Summarise round-1 admission scores per method: range, usual value, exceptions.

    Used when no major is named. Taking the first row per method would present
    one major's score as the school's score; this groups every verified row.
    """

    entities = analysis.entities
    if (
        entities.get("score_type") != "admission_score"
        or entities.get("major_name")
        or entities.get("major_code")
        or entities.get("candidate_majors")
        or entities.get("student_scores")
    ):
        return None
    requested_method = str(entities.get("admission_method") or "")
    by_method: dict[str, list[tuple[str, str, float]]] = {}
    for fact in getattr(evidence, "score_facts", ()) or ():
        if not isinstance(fact, Mapping) or not _is_verified_fact(fact):
            continue
        if fact.get("score_type") != "admission_score":
            continue
        method = str(fact.get("method") or "")
        raw_value = str(fact.get("raw_value") or "").strip()
        major = str(fact.get("major_name") or "").strip()
        if not method or not major or not raw_value or raw_value == "-":
            continue
        if requested_method and method != requested_method:
            continue
        try:
            value = float(fact.get("value"))
        except (TypeError, ValueError):
            continue
        rows = by_method.setdefault(method, [])
        existing = next((index for index, row in enumerate(rows) if row[0] == major), None)
        if existing is None:
            rows.append((major, raw_value, value))
        elif "(*)" in raw_value and "(*)" not in rows[existing][1]:
            # The same row may be indexed twice; keep the variant that carries
            # the published "(*)" condition marker.
            rows[existing] = (major, raw_value, value)
    # Require a real table (several majors), not a single matched row.
    by_method = {method: rows for method, rows in by_method.items() if len(rows) >= 3}
    if not by_method:
        return None

    lines = []
    for method in sorted(by_method, key=lambda m: ("thpt", "hoc_ba", "dgnl").index(m) if m in ("thpt", "hoc_ba", "dgnl") else 9):
        rows = by_method[method]
        counts: dict[str, int] = {}
        for _, raw_value, _ in rows:
            counts[raw_value] = counts.get(raw_value, 0) + 1
        usual = max(counts, key=lambda raw: (counts[raw], -len(raw)))
        values = [value for _, _, value in rows]
        low, high = min(values), max(values)
        fmt = lambda number: f"{number:g}".replace(".", ",")
        span = fmt(low) if low == high else f"{fmt(low)}–{fmt(high)}"
        exceptions = []
        for raw_value in sorted({raw for _, raw, _ in rows if raw != usual}, key=lambda raw: next(v for _, r, v in rows if r == raw)):
            majors = ", ".join(major for major, raw, _ in rows if raw == raw_value)
            exceptions.append(f"{raw_value.replace('.', ',')} điểm: {majors}")
        detail = f"phần lớn mã xét tuyển {usual.replace('.', ',')} điểm"
        if exceptions:
            detail += "; " + "; ".join(exceptions)
        label = _method_label(method)
        lines.append(f"- {label[:1].upper()}{label[1:]}: {span} điểm ({detail}).")
    note = (
        "\nGhi chú (*) là điều kiện riêng của ngành theo bảng công bố."
        if any("(*)" in raw for rows in by_method.values() for _, raw, _ in rows)
        else ""
    )
    return "Điểm trúng tuyển đợt 1 năm 2026 của DHV theo từng phương thức:\n" + "\n".join(lines) + note


def _structured_score_answer(
    analysis: QueryAnalysis,
    facts: Any,
) -> str | None:
    rows = []
    seen_methods: set[tuple[str, str]] = set()
    for fact in facts or ():
        if not isinstance(fact, Mapping) or fact.get("raw_value") in (None, ""):
            continue
        # A supplementary source can also expose a deadline fact. It belongs
        # in the evidence bundle, but is not a score row.
        method = str(fact.get("method") or "")
        key = (normalize_question(str(fact.get("major_name") or "")), method)
        if method == "deadline" or key in seen_methods:
            continue
        seen_methods.add(key)
        rows.append(fact)
    if not rows:
        return None
    several_majors = len({key[0] for key in seen_methods if key[0]}) > 1
    grouped: list[str] = []
    for fact in rows:
        label = _method_label(fact.get("method"))
        raw_value = str(fact.get("raw_value"))
        if raw_value == "-":
            value = "chưa công bố"
        else:
            value = f"{raw_value} điểm"
        major = str(fact.get("major_name") or "").strip()
        prefix = f"{major}: " if major and (len(rows) == 1 or several_majors) else ""
        grouped.append(f"{prefix}{label}: {value}")
    score_type = str(analysis.entities.get("score_type") or "")
    normalized_question = normalize_question(analysis.normalized_question)
    if score_type == "admission_score":
        intro = "Điểm trúng tuyển được công bố: "
    elif score_type == "supplementary_threshold":
        intro = "Ngưỡng xét tuyển bổ sung được công bố: "
    elif (
        score_type == "application_threshold"
        and not analysis.entities.get("major_name")
        and not analysis.entities.get("candidate_majors")
        and any(marker in normalized_question for marker in ("phan lon", "da so", "cac nganh con lai"))
    ):
        intro = "Ngưỡng nhận hồ sơ cho phần lớn chương trình theo dữ liệu DHV: "
    else:
        intro = "Ngưỡng nhận hồ sơ được công bố: "
    answer = intro + "; ".join(grouped) + "."
    if (
        score_type == "application_threshold"
        and any(marker in normalized_question for marker in ("phan lon", "da so", "cac nganh con lai"))
    ):
        answer += " Đây là ngưỡng nhận hồ sơ, không phải điểm trúng tuyển."
    return answer


def _evidence_score_comparison_reason_answer(
    analysis: QueryAnalysis,
    evidence: Any,
) -> str | None:
    """Answer a score-difference question only when the source states the comparison."""

    normalized_question = normalize_question(analysis.normalized_question)
    if not (
        analysis.intent == "HOI_DIEM_TRUNG_TUYEN"
        and analysis.entities.get("major_name")
        and any(marker in normalized_question for marker in ("vi sao", "tai sao"))
        and "cao hon" in normalized_question
        and "cac nganh khac" in normalized_question
    ):
        return None
    requested_major = normalize_question(str(analysis.entities.get("major_name") or ""))
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "diem_trung_tuyen"
            or str(metadata.get("record_type") or "") != "page_text"
            or str(metadata.get("status") or "") != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
        ):
            continue
        text = str(getattr(chunk, "text", "") or "")
        folded = normalize_question(" ".join(text.splitlines()))
        leading_group = re.search(
            r"cac nganh\s+(.+?)\s+dan dau voi muc diem chuan la\s*"
            r"(\d+(?:[.,]\d+)?)\s*diem",
            folded,
        )
        leading_score = re.search(
            r"dan dau voi muc diem chuan la\s*(\d+(?:[.,]\d+)?)\s*diem",
            folded,
        )
        remaining_score = re.search(
            r"cac nganh\s*(?:/\s*chuong trinh)?\s*dao tao con lai\s*"
            r"giu muc diem trung tuyen la\s*(\d+(?:[.,]\d+)?)\s*diem",
            folded,
        )
        if (
            requested_major not in folded
            or not leading_group
            or not leading_score
            or not remaining_score
        ):
            continue
        source_group = re.search(
            r"các\s+ngành\s+(.+?)\s+dẫn\s+đầu\s+với\s+mức\s+điểm\s+chuẩn\s+là\s*"
            r"\d+(?:[.,]\d+)?\s*điểm",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        leading_majors = (
            re.sub(r"\s+", " ", source_group.group(1)).strip(" ,.;:")
            if source_group
            else leading_group.group(1).strip(" ,.;:")
        )
        leading_value = leading_score.group(1).replace(".", ",")
        remaining_value = remaining_score.group(1).replace(".", ",")
        return (
            "Theo tài liệu tuyển sinh DHV 2026, điểm trúng tuyển THPT của các ngành "
            f"{leading_majors} là {leading_value} điểm; "
            f"các ngành/chương trình còn lại là {remaining_value} điểm. "
            "Tài liệu không nêu nguyên nhân cụ thể của mức chênh lệch."
        )
    return None


def _structured_comparison_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    entities = analysis.entities
    candidates: list[str] = []
    for key in ("candidate_majors", "candidate_programs"):
        values = entities.get(key)
        if isinstance(values, (list, tuple)):
            for value in values:
                text = str(value).strip()
                if text and text not in candidates:
                    candidates.append(text)
    if len(candidates) < 2:
        return None
    facts = [
        fact for fact in getattr(evidence, "score_facts", ()) or ()
        if isinstance(fact, Mapping) and fact.get("major_name")
    ]
    by_major: dict[str, dict[str, str]] = {}
    codes: dict[str, str] = {}
    for fact in facts:
        major = str(fact.get("major_name") or "").strip()
        if major not in candidates:
            continue
        by_major.setdefault(major, {})[_method_label(fact.get("method"))] = str(fact.get("raw_value") or "-")
        if fact.get("major_code"):
            codes[major] = str(fact.get("major_code"))
    if not by_major:
        return None
    headers = candidates[:2]
    rows = ["| Tiêu chí | " + " | ".join(headers) + " |", "|---|" + "---|" * len(headers)]
    if any(major in codes for major in headers):
        rows.append("| Mã ngành | " + " | ".join(codes.get(major, "-") for major in headers) + " |")
    for label in ("thi tốt nghiệp THPT", "học bạ", "ĐGNL"):
        if any(label in by_major.get(major, {}) for major in headers):
            rows.append(
                f"| Ngưỡng {label} | "
                + " | ".join(by_major.get(major, {}).get(label, "-") for major in headers)
                + " |"
            )
    relations = getattr(evidence, "entity_relations", ()) or ()
    programs = {
        major: [
            str(relation.get("program_name"))
            for relation in relations
            if str(relation.get("parent_major") or "").strip() == major
            and str(relation.get("program_name") or "").strip()
        ]
        for major in headers
    }
    if any(programs.values()):
        rows.append(
            "| Chương trình đã ghi nhận | "
            + " | ".join(
                "; ".join(dict.fromkeys(programs.get(major, ())) or "-")
                for major in headers
            )
            + " |"
        )
    rows.append("")
    rows.append("Các ngưỡng trong bảng là ngưỡng nhận hồ sơ, không phải kết luận trúng tuyển.")
    return "\n".join(rows)


def _evidence_applicant_support_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer a named applicant-group policy only when the source names that group."""

    normalized = normalize_question(analysis.normalized_question)
    if "khuyet tat" not in normalized or not any(
        marker in normalized for marker in ("chinh sach", "ho tro", "quyen loi", "tao dieu kien")
    ):
        return None
    for sentence in _evidence_sentences(evidence):
        folded = normalize_question(sentence)
        has_tuition_waiver = bool(re.search(r"mien\W*giam\s+hoc phi", folded))
        if "khuyet tat" in folded and (
            has_tuition_waiver
            or "ho tro hoc phi" in folded
            or "chinh sach" in folded
        ):
            return f"{sentence.strip()}"
    return None


_SUPPLEMENTARY_DETAIL_PATTERNS = {
    "supplementary_quota": r"(\d+)\s+chỉ tiêu tại\s+(\d+)\s+chương trình",
    "supplementary_program_count": r"(\d+)\s+chỉ tiêu tại\s+(\d+)\s+chương trình",
    "supplementary_deadline": r"nhận hồ sơ đến hết ngày\s+(\d{1,2}/\d{1,2}/\d{4})",
    "supplementary_fee": r"((?:miễn phí|lệ phí) xét tuyển[^.;]*)",
    "supplementary_programs": r"tuyển sinh tại\s+(\d+)\s+chương trình[^:]{0,160}gồm:\s*(.+?)\.(?=\s|$)",
    "supplementary_audience": r"(Đây là cơ hội dành cho .+?\.)(?=\s|$)",
}
_SUPPLEMENTARY_REQUESTS = frozenset({
    "supplementary_quota", "supplementary_program_count", "supplementary_deadline",
    "supplementary_fee", "supplementary_deadline_fee", "supplementary_programs",
    "supplementary_methods", "supplementary_benefits",
})


def _supplementary_notice(analysis: QueryAnalysis, evidence: Any) -> tuple[int, str] | None:
    """Flattened text of the verified supplementary notice for the requested year."""
    target_year = int(analysis.entities.get("year") or settings.target_year)
    parts: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        try:
            year = int(metadata.get("year"))
        except (TypeError, ValueError):
            continue
        if (
            str(metadata.get("category") or "") == "xet_tuyen_bo_sung"
            and str(metadata.get("status") or "") == "verified"
            and str(metadata.get("school_code") or "").upper() == "DHV"
            and year == target_year
        ):
            parts.append(re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or "")))
    return (target_year, " ".join(parts)) if parts else None


def _evidence_supplementary_detail_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer one named detail of the supplementary round from the verified notice only."""

    request = str(analysis.entities.get("request_type") or "")
    if request not in _SUPPLEMENTARY_REQUESTS:
        return None
    notice = _supplementary_notice(analysis, evidence)
    if notice is None:
        return None
    year, text = notice

    def find(key: str) -> re.Match[str] | None:
        return re.search(_SUPPLEMENTARY_DETAIL_PATTERNS[key], text, re.IGNORECASE)

    # Phrase it as the notice's milestone: the round may already be closed.
    prefix = f"Theo thông báo xét tuyển bổ sung năm {year}, DHV"
    quota, deadline, fee = find("supplementary_quota"), find("supplementary_deadline"), find("supplementary_fee")

    if request == "supplementary_quota" and quota:
        return f"{prefix} tuyển {quota.group(1)} chỉ tiêu tại {quota.group(2)} chương trình đào tạo."
    if request == "supplementary_program_count" and quota:
        return f"{prefix} mở xét tuyển bổ sung cho {quota.group(2)} chương trình đào tạo."
    if request == "supplementary_deadline" and deadline:
        return f"{prefix} nhận hồ sơ đến hết ngày {deadline.group(1)}."
    if request == "supplementary_fee" and fee:
        return f"{prefix} {fee.group(1).strip()}."
    if request == "supplementary_deadline_fee" and deadline and fee:
        return f"{prefix} nhận hồ sơ đến hết ngày {deadline.group(1)} và {fee.group(1).strip()}."
    if request == "supplementary_programs":
        programs = find("supplementary_programs")
        if programs:
            return f"{prefix} xét tuyển bổ sung tại {programs.group(1)} chương trình: {programs.group(2).strip()}."
        return None
    if request == "supplementary_methods":
        folded = normalize_question(text)
        methods = [
            label for marker, label in (
                ("phuong thuc xet ket qua thi tot nghiep", f"kết quả thi tốt nghiệp THPT năm {year}"),
                ("phuong thuc xet ket qua hoc tap", "kết quả học tập THPT (học bạ)"),
                ("danh gia nang luc", "kết quả thi Đánh giá năng lực"),
            ) if marker in folded
        ]
        if not methods:
            return None
        answer = f"{prefix} xét tuyển bổ sung theo {len(methods)} phương thức: {'; '.join(methods)}."
        asked = normalize_question(analysis.normalized_question)
        if any(m in asked for m in ("dgnl", "danh gia nang luc")) and "danh gia nang luc" not in folded:
            answer += " Thông báo không nêu phương thức Đánh giá năng lực (ĐGNL) cho đợt này."
        return answer
    if request == "supplementary_benefits":
        reasons = []
        audience = find("supplementary_audience")
        if audience:
            reasons.append(audience.group(1).strip())
        if quota:
            reasons.append(f"Đợt này có {quota.group(1)} chỉ tiêu tại {quota.group(2)} chương trình đào tạo.")
        if fee:
            reasons.append(f"DHV {fee.group(1).strip()}.")
        if deadline:
            reasons.append(f"Hạn nhận hồ sơ: hết ngày {deadline.group(1)}.")
        return f"Theo thông báo xét tuyển bổ sung năm {year}: " + " ".join(reasons) if reasons else None
    return None


def _evidence_application_registration_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Render verified online/in-person routes for a supplementary application."""

    normalized = normalize_question(analysis.normalized_question)
    if not any(marker in normalized for marker in (
        "xet bo sung", "xet tuyen bo sung", "tuyen sinh bo sung", "dot bo sung",
    )):
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "xet_tuyen_bo_sung"
            or str(metadata.get("record_type") or "") != "page_text"
        ):
            continue
        raw_text = str(getattr(chunk, "text", "") or "")
        flattened = re.sub(r"\s+", " ", raw_text).strip()
        route = re.search(
            r"Thí sinh có thể đăng ký trực tuyến .*? nộp hồ sơ trực tiếp tại một trong hai cơ sở của Nhà trường\.",
            flattened,
            re.IGNORECASE,
        )
        if not route:
            continue
        sites = [
            re.sub(r"\s+", " ", line).strip()
            for line in raw_text.splitlines()
            if re.match(r"\s*(?:\d+\.\s*)?•?\s*Cơ sở [12]\s*:", line, re.IGNORECASE)
        ]
        if len(sites) < 2:
            continue
        answer = (
            "Bạn có thể đăng ký xét tuyển bổ sung theo hai cách: "
            + route.group(0)
            + "\n"
            + "\n".join(f"- {site.lstrip('• ')}" for site in sites[:2])
        )
        deadline = re.search(
            r"Thời gian nhận hồ sơ đến hết ngày\s+(\d{1,2}/\d{1,2}/\d{4})",
            flattened,
            re.IGNORECASE,
        )
        if deadline and any(marker in normalized for marker in (
            "khi nao", "thoi gian", "thoi han", "den khi nao", "den ngay nao", "den ngay", "han nhan",
        )):
            answer += f"\nThời gian nhận hồ sơ đến hết ngày {deadline.group(1)}."
        return answer
    return None


def _evidence_general_registration_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Extract the general application rule/deadline only for a how-to query."""

    normalized = normalize_question(analysis.normalized_question)
    if not any(marker in normalized for marker in (
        "cach dang ky", "dang ky tuyen sinh", "dang ky xet tuyen",
    )):
        return None
    if any(marker in normalized for marker in (
        "o dau", "cong dang ky", "cong tuyen sinh", "website", "trang web",
        "xet bo sung", "xet tuyen bo sung", "tuyen sinh bo sung", "dot bo sung",
        "du dieu kien", "dieu kien", "hoc luc", "cong diem", "khuyet tat",
    )):
        return None

    text = re.sub(
        r"\s+",
        " ",
        " ".join(
            str(getattr(chunk, "text", "") or "")
            for chunk in getattr(evidence, "chunks", ()) or ()
        ),
    ).strip()
    principle = re.search(
        r"Nguyên tắc chung:\s*(.+?)"
        r"(?=\s+(?:Thời gian đăng ký xét tuyển:|Các phương thức xét tuyển gồm:|1\.\d+\.|$))",
        text,
        re.IGNORECASE,
    )
    deadline = re.search(
        r"Thời gian đăng ký xét tuyển:\s*(?:Đến hết ngày\s*)?(\d{1,2}/\d{1,2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    answer_parts: list[str] = []
    if principle:
        answer_parts.append(principle.group(1).strip().rstrip(" .;"))
    if deadline:
        answer_parts.append(
            f"Thời gian đăng ký xét tuyển được nêu đến hết ngày {deadline.group(1)}."
        )
    if not answer_parts:
        return None
    return "Năm 2026, " + ". ".join(answer_parts).rstrip(".") + "."


def _evidence_result_notification_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Use only documented admission-result and enrollment-confirmation channels."""

    if not _is_result_notification_question(analysis.normalized_question):
        return None
    sentences = _evidence_sentences(evidence)
    lines = _evidence_text_lines(evidence)
    invitation = next(
        (
            line for line in lines
            if "thu moi nhap hoc" in normalize_question(line)
            and "tin nhan zalo" in normalize_question(line)
            and len(line) < 450
        ),
        next(
            (
                sentence for sentence in sentences
                if "thu moi nhap hoc" in normalize_question(sentence)
                and "tin nhan zalo" in normalize_question(sentence)
                and len(sentence) < 450
            ),
            None,
        ),
    )
    confirmation = next(
        (
            sentence for sentence in sentences
            if "he thong ho tro xet tuyen chung" in normalize_question(sentence)
            and "bo giao duc" in normalize_question(sentence)
        ),
        None,
    )
    website_instruction = None
    for line in lines:
        folded = normalize_question(line)
        if "website tuyen sinh" not in folded:
            continue
        website_at = line.casefold().find("website tuyển sinh")
        if website_at < 0:
            website_at = line.casefold().find("website tuyen sinh")
        url_match = re.search(r"tuyensinh\.dhv\.edu\.vn", line, re.IGNORECASE)
        if website_at >= 0:
            previous_sentence = max(line.rfind(". ", 0, website_at), line.rfind("! ", 0, website_at), line.rfind("? ", 0, website_at))
            start = previous_sentence + 2 if previous_sentence >= 0 and website_at - previous_sentence < 180 else website_at
            if url_match:
                end = url_match.end()
            else:
                next_sentence = line.find(". ", website_at)
                end = next_sentence if next_sentence >= 0 else min(len(line), website_at + 200)
            website_instruction = line[start:end].strip(" .;,")
            break
    if not website_instruction:
        website_instruction = next(
            (
                sentence for sentence in sentences
                if "website tuyen sinh" in normalize_question(sentence)
            ),
            None,
        )
    details: list[str] = []
    if confirmation:
        details.append(f"Tài liệu điểm trúng tuyển yêu cầu: {_remove_unresolved_url_label(confirmation)}")
    if website_instruction:
        if "tuyensinh.dhv.edu.vn" in normalize_question(website_instruction):
            details.append(
                f"Hướng dẫn nhập học cũng chỉ tới website tuyển sinh của DHV: {website_instruction.strip()}"
            )
        else:
            details.append("Hướng dẫn nhập học cũng chỉ tới website tuyển sinh của DHV để xem thông tin chi tiết.")
    if invitation:
        details.append(f"Tài liệu nhập học nhắc đến: {_remove_unresolved_url_label(invitation)}")
    if not details:
        return None
    return "Bạn lưu ý các bước sau:\n" + "\n".join(
        f"- {detail}" for detail in details
    )
