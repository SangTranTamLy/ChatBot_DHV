"""Bảo vệ chất lượng văn bản sinh từ mô hình cục bộ, xử lý echo/artifact và cơ chế retry khi không đạt chuẩn kiểm định."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.config.settings import settings
from .admission_answers import (
    _evidence_formula_answer,
    _evidence_schedule_answer,
    _structured_comparison_answer,
    _structured_score_answer,
)
from .answer_planner import AnswerPlan
from .catalog_formatters import _deterministic_recommendation_answer
from .evidence_utils import _evidence_text_lines
from .output_validator import FALLBACK_ANSWER, validate_model_answer
from .query_analysis import QueryAnalysis, normalize_question
from .scholarship_formatters import _evidence_scholarship_answer
from .school_info_formatters import _evidence_overview_answer
from .tuition_formatters import _evidence_semester_system_answer

_RETRYABLE_VALIDATION_REASONS = frozenset(
    {
        "prompt_leak",
        "missing_threshold_mapping",
        "wrong_threshold_mapping",
        "missing_admission_score",
        "wrong_supplementary_mapping",
        "tuition_label_or_value",
        "program_relation_missing",
        "program_relation_wrong",
        "personal_admission_claim",
        "ungrounded",
        "ungrounded_entity",
        "advisory_choices_incomplete",
        "unsupported_contact_value",
        "unsupported_contact_channel",
        "unsupported_date",
        "program_catalog_missing",
        "program_catalog_parent_mismatch",
        "program_catalog_count_mismatch",
        "entity_mismatch",
        "year_mismatch",
        "score_type_mismatch",
        "method_mismatch",
        "institution_mismatch",
        "official_status_claim",
        "requested_information_mismatch",
        "answer_too_long",
        "context_echo",
        "missing_score_comparison",
        "wrong_score_comparison",
        "major_catalog_missing",
        "major_catalog_count_mismatch",
        "major_catalog_code_mismatch",
        "required_content_missing",
    }
)

_MAX_GENERATED_ANSWER_CHARS = 6000


def _retry_prompt(
    prompt: str,
    draft: str,
    facts: Any,
    evidence: Any,
    analysis: QueryAnalysis | None = None,
    score_comparisons: Any = (),
) -> str:
    checklist = "; ".join(
        f"{fact.get('method')} → {fact.get('raw_value')}"
        for fact in facts or ()
        if fact.get("method") != "deadline"
    )
    labeled_amounts: list[str] = []
    seen_amounts: set[str] = set()
    analysis_question = str(
        getattr(analysis, "normalized_question", "")
        or getattr(analysis, "question", "")
        or ""
    )
    is_tuition_question = (
        analysis is not None and getattr(analysis, "intent", None) == "HOI_HOC_PHI"
    ) or any(marker in normalize_question(analysis_question) for marker in ("hoc phi", "tien hoc"))
    if is_tuition_question:
        for line in _evidence_text_lines(evidence):
            normalized = normalize_question(line)
            if not any(label in normalized for label in ("hoc phi", "tong chi phi")):
                continue
            if line not in seen_amounts:
                seen_amounts.add(line)
                labeled_amounts.append(line)
                if len(labeled_amounts) == 4:
                    break
    amount_instruction = ""
    if labeled_amounts:
        amount_instruction = (
            " Đây là câu hỏi về học phí: bắt buộc chép dòng bắt đầu bằng "
            "nhãn Học phí với đúng giá trị; không dùng dòng Tổng chi phí để "
            "thay thế. Các dòng khoản tiền cần giữ đúng nhãn và giá trị: "
            + " | ".join(labeled_amounts)
            + "."
        )
    relation_instruction = ""
    entities = getattr(analysis, "entities", {}) if analysis is not None else {}
    program = str(entities.get("program_name") or "") if isinstance(entities, Mapping) else ""
    if program:
        relations = [
            relation
            for relation in getattr(evidence, "entity_relations", ())
            if str(relation.get("program_name") or "") == program
        ]
        parents = [
            str(relation.get("parent_major"))
            for relation in relations
            if relation.get("parent_major")
        ]
        allowed_codes = [
            str(fact.get("major_code"))
            for fact in getattr(evidence, "score_facts", ())
            if str(fact.get("major_name") or "") in parents and fact.get("major_code")
        ]
        if parents:
            relation_instruction = (
                f" Quan hệ bắt buộc: chương trình {program} thuộc ngành "
                f"{parents[0]}; không gọi chương trình là ngành độc lập."
            )
            if allowed_codes:
                relation_instruction += (
                    " Mã ngành hợp lệ của ngành cha: "
                    + ", ".join(sorted(set(allowed_codes)))
                    + "."
                )
    comparison_instruction = ""
    if score_comparisons and getattr(analysis, "intent", None) != "TU_VAN_CHON_NGANH":
        required_comparisons = []
        for comparison in score_comparisons:
            method = str(comparison.get("method") or "")
            label = {
                "thpt": "thi tốt nghiệp THPT",
                "hoc_ba": "học bạ THPT",
                "dgnl": "ĐGNL",
            }.get(method, "phương thức xét tuyển")
            relation = "cao hơn hoặc bằng" if comparison.get("meets_threshold") else "thấp hơn"
            required_comparisons.append(
                f"{label}: điểm thí sinh {comparison.get('student_value')}; "
                f"ngưỡng {comparison.get('threshold_value')}; kết luận đúng là {relation}."
            )
        if required_comparisons:
            comparison_instruction = (
                " Bắt buộc giữ nguyên từng phép so sánh điểm cá nhân sau đây, không bỏ "
                "điểm thí sinh hoặc đổi quan hệ: " + " | ".join(required_comparisons)
            )
    major_catalog_instruction = ""
    if analysis is not None and getattr(analysis, "intent", None) == "DANH_SACH_NGANH":
        major_rows: list[str] = []
        seen_major_rows: set[tuple[str, str]] = set()
        for fact in getattr(evidence, "score_facts", ()) or ():
            if (
                str(fact.get("category") or "") != "nganh_dao_tao"
                or not fact.get("major_name")
                or not fact.get("major_code")
                or str(fact.get("status") or fact.get("source_status") or "").casefold() != "verified"
            ):
                continue
            identity = (str(fact["major_name"]), str(fact["major_code"]))
            if identity in seen_major_rows:
                continue
            seen_major_rows.add(identity)
            major_rows.append(f"{identity[0]} — mã ngành {identity[1]}")
        if major_rows:
            major_catalog_instruction = (
                " Danh sách ngành đã xác minh phải giữ đủ từng cặp tên–mã dưới đây, "
                "mỗi ngành đúng một lần; không thêm ngành hoặc mã khác: "
                + " | ".join(major_rows)
                + "."
            )
    return (
        f"{prompt}\n\nBẢN NHÁP CẦN KIỂM TRA:\n{draft[:2000]}\n\n"
        "Hãy tạo lại câu trả lời chỉ từ CONTEXT và không nhắc tới từ CONTEXT hay "
        "'ngữ cảnh' trong câu trả lời. Checklist mapping bắt buộc: "
        f"{checklist}. Phải nêu đủ từng mapping trong checklist, giữ nguyên dấu '-' nếu có, "
        "không thêm số và không kết luận đậu/trượt."
        + amount_instruction
        + relation_instruction
        + comparison_instruction
        + major_catalog_instruction
        + "\n\nCÂU TRẢ LỜI MỚI:\n"
    )


def _score_comparison_failure(
    answer: str,
    score_comparisons: Any,
    analysis: QueryAnalysis,
) -> str:
    """Keep user-provided scores and deterministic comparison outcomes intact."""

    if not score_comparisons or analysis.intent == "TU_VAN_CHON_NGANH":
        return ""
    folded = normalize_question(answer)
    numeric_tokens = re.findall(r"(?<!\d)\d+(?:[.,]\d+)?(?!\d)", folded)
    normalized_numbers = {
        number.replace(",", ".").rstrip("0").rstrip(".")
        if "." in number or "," in number
        else number
        for number in numeric_tokens
    }

    def number_is_present(value: object) -> bool:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return str(value) in numeric_tokens
        expected = str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"
        return expected in normalized_numbers

    for comparison in score_comparisons:
        if not number_is_present(comparison.get("student_value")) or not number_is_present(
            comparison.get("threshold_value")
        ):
            return "missing_score_comparison"
        if comparison.get("meets_threshold"):
            if not any(
                marker in folded
                for marker in (
                    "cao hon hoac bang",
                    "bang hoac cao hon",
                    "cao hon nguong",
                    "dat nguong",
                    "dat muc toi thieu",
                )
            ):
                return "wrong_score_comparison"
        elif not any(
            marker in folded
            for marker in ("thap hon", "chua dat nguong", "duoi nguong")
        ):
            return "wrong_score_comparison"
    return ""


def _is_generation_artifact(answer: object) -> bool:
    value = str(answer or "").lstrip()
    normalized = normalize_question(value)
    return value.startswith("[") or normalized.startswith(
        (
            "du lieu tuyen sinh:",
            "theo du lieu tuyen sinh",
            "day la cac thong tin duoc cong bo",
        )
    )


def _is_context_echo(answer: object, evidence: Any) -> bool:
    """Reject long verbatim source dumps even when every copied number is valid."""

    value = normalize_question(str(answer or ""))
    answer_tokens = value.split()
    if len(value) < 800 or len(answer_tokens) < 100:
        return False
    candidates = [str(getattr(evidence, "context", "") or "")]
    candidates.extend(
        str(getattr(chunk, "text", "") or "")
        for chunk in (getattr(evidence, "chunks", ()) or ())
    )
    for candidate in candidates:
        normalized_candidate = normalize_question(candidate)
        candidate_tokens = set(normalized_candidate.split())
        overlap = sum(token in candidate_tokens for token in answer_tokens)
        if len(normalized_candidate) >= 400 and (
            value in normalized_candidate
            or normalized_candidate in value
            or overlap / len(answer_tokens) >= 0.86
        ):
            return True
    return False


def _combination_is_verified(evidence: Any, combination: object) -> bool:
    """Chỉ coi A00/A01... là có dữ liệu khi evidence có dòng khẳng định tích cực."""

    token = normalize_question(str(combination or ""))
    if not token:
        return True
    token_pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    )
    negative_markers = (
        "khong dua",
        "chua co",
        "chua duoc",
        "chua xac nhan",
        "neu chua",
        "khong import",
    )
    for line in _evidence_text_lines(evidence):
        folded = normalize_question(line)
        if not token_pattern.search(folded):
            continue
        if any(marker in folded for marker in negative_markers):
            continue
        return True
    return False


def _realize_generation_artifact(
    raw_answer: str,
    *,
    analysis: QueryAnalysis,
    answer_plan: AnswerPlan,
    evidence: Any,
    score_facts: Any,
    score_comparisons: Any,
    target_year: int = settings.target_year,
) -> str:
    """Dọn output echo/context theo plan; không thay đổi dữ kiện evidence."""

    if answer_plan.mode == "OVERVIEW":
        overview = _evidence_overview_answer(
            analysis,
            evidence,
            target_year=target_year,
        )
        if overview:
            return overview
    if answer_plan.mode == "COMPARISON":
        comparison = _structured_comparison_answer(analysis, evidence)
        if comparison:
            return comparison
    if answer_plan.mode == "RECOMMENDATION":
        recommendation = _deterministic_recommendation_answer(
            analysis, evidence, score_comparisons
        )
        if recommendation:
            return recommendation
    if analysis.intent in {"HOI_HOC_PHI", "SCHOOL_INFO"}:
        semester_ans = _evidence_semester_system_answer(analysis, evidence)
        if semester_ans:
            return semester_ans
        lines = [
            line
            for line in _evidence_text_lines(evidence)
            if normalize_question(line).startswith(
                ("hoc phi hki", "hoc phi:", "• hoc phi hki")
            )
        ]
        if lines:
            return lines[0].lstrip("• ").strip()
    if analysis.intent == "HOI_HOC_BONG":
        scholarship = _evidence_scholarship_answer(analysis, evidence)
        if scholarship:
            return scholarship
    if analysis.intent == "HOI_CACH_TINH_DIEM":
        formula = _evidence_formula_answer(evidence)
        if formula:
            return formula
    if analysis.intent == "HOI_LICH_TUYEN_SINH":
        operation = str(analysis.entities.get("query_mode") or "SINGLE_FACT")
        if operation in {"COUNT", "LIST", "LIST_AND_COUNT"}:
            schedule = _evidence_schedule_answer(analysis, evidence)
            if schedule:
                return schedule
    if score_facts and analysis.intent in {
        "HOI_NGUONG_DAU_VAO",
        "HOI_DIEM_TRUNG_TUYEN",
        "HOI_XET_TUYEN_BO_SUNG",
    }:
        score_answer = _structured_score_answer(analysis, score_facts)
        if score_answer:
            return score_answer

    # Last resort for an echoed context: retain content lines but remove the
    # prompt's internal evidence labels and metadata.
    cleaned: list[str] = []
    for line in str(raw_answer or "").splitlines():
        stripped = line.strip()
        lowered = normalize_question(stripped)
        if (
            not stripped
            or re.match(r"^\[evidence\s+\d+\]$", lowered)
            or lowered.startswith(("tieu de:", "nhom:", "nam:", "muc:", "noi dung:", "nguon chinh thuc dhv:"))
        ):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned).strip() or str(raw_answer or "").strip()


def _advisory_score_echo(answer: str, analysis: QueryAnalysis) -> str:
    """Keep the student's supplied score and combination visible in score advice."""

    if analysis.intent != "TU_VAN_CHON_NGANH":
        return answer
    entities = analysis.entities
    scores = entities.get("student_scores")
    if not isinstance(scores, Mapping) or not scores:
        return answer

    method = str(entities.get("admission_method") or "")
    score = next(
        (
            scores.get(key)
            for key in (method, "thpt", "unspecified")
            if key and isinstance(scores.get(key), (int, float))
        ),
        None,
    )
    combination = str(entities.get("admission_combination") or "").upper()
    combination_label = (
        "D01 (Toán, Ngữ văn, Tiếng Anh)" if combination == "D01" else combination
    )
    folded_answer = normalize_question(answer)
    score_text = ""
    if score is not None:
        score_text = str(int(score) if isinstance(score, float) and score.is_integer() else score)
        score_pattern = re.escape(score_text).replace(r"\.", r"[.,]")
        score_is_present = bool(re.search(rf"(?<!\d){score_pattern}(?!\d)", folded_answer))
    else:
        score_is_present = True

    combination_is_present = not combination_label or (
        bool(re.search(r"\bd01\b", folded_answer))
        if combination == "D01"
        else normalize_question(combination_label) in folded_answer
    )
    if score_is_present and combination_is_present:
        return answer

    method_label = {
        "thpt": " theo phương thức thi tốt nghiệp THPT",
        "dgnl": " theo phương thức ĐGNL",
        "hoc_ba": " theo phương thức xét học bạ THPT",
    }.get(method, "")
    localized_score = score_text.replace(".", ",")
    if not score_is_present and not combination_is_present:
        prefix = (
            f"Bạn cho biết đạt **{localized_score} điểm**{method_label} "
            f"với tổ hợp **{combination_label}**."
        )
    elif not score_is_present:
        prefix = f"Bạn cho biết đạt **{localized_score} điểm**{method_label}."
    else:
        prefix = f"Tổ hợp bạn nêu là **{combination_label}**."
    return f"{prefix}\n\n{answer}".strip() if answer.strip() else prefix


def _remove_duplicate_major_code_bullets(answer: str, analysis: QueryAnalysis) -> str:
    """Drop a code-only bullet if the same major code already appeared in its heading."""

    if analysis.intent != "TU_VAN_CHON_NGANH":
        return answer
    seen_codes: set[str] = set()
    kept: list[str] = []
    code_only = re.compile(
        r"^\s*(?:[-*•]\s*)?(?:mã\s+ngành|ma\s+nganh)\s*[:：]?\s*(\d{7})\s*[.)]?\s*$",
        re.IGNORECASE,
    )
    for line in str(answer or "").splitlines():
        match = code_only.match(line)
        if match and match.group(1) in seen_codes:
            continue
        if match:
            seen_codes.add(match.group(1))
        else:
            seen_codes.update(re.findall(r"\b\d{7}\b", line))
        kept.append(line)
    return "\n".join(kept).strip()


def _ensure_score_advisory_open_question(answer: str, analysis: QueryAnalysis) -> str:
    """End score-guided major advice with one open question about the student's priorities."""

    scores = analysis.entities.get("student_scores")
    if (
        analysis.intent != "TU_VAN_CHON_NGANH"
        or not isinstance(scores, Mapping)
        or not scores
    ):
        return answer

    # The prompt asks for one closing question, but models sometimes omit it or
    # insert several. Keep declarative content and supply the same grounded,
    # open-ended follow-up at the end of every score-advice answer.
    declarative_lines: list[str] = []
    for line in str(answer or "").splitlines():
        if "?" not in line:
            declarative_lines.append(line)
            continue
        declarative_lines.extend(
            fragment.strip()
            for fragment in re.split(r"(?<=[.!])\s+", line)
            if fragment.strip() and "?" not in fragment
        )
    body = "\n".join(declarative_lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    follow_up = (
        "Bạn đang quan tâm nhất đến lĩnh vực nào—kinh tế, truyền thông, "
        "quản trị hay công nghệ—để mình tư vấn sát hơn?"
    )
    return f"{body}\n\n{follow_up}" if body else follow_up


def _validated_generation(
    *,
    active_llm: Any,
    prompt: str,
    evidence: Any,
    question: str,
    analysis: QueryAnalysis,
    score_facts: Any,
    answer_plan: AnswerPlan,
    score_comparisons: Any = (),
    required_phrases: Any = (),
    target_year: int = settings.target_year,
) -> dict[str, object]:
    raw_answer = active_llm.generate(prompt)
    generated_answer = (
        _realize_generation_artifact(
            raw_answer,
            analysis=analysis,
            answer_plan=answer_plan,
            evidence=evidence,
            score_facts=score_facts,
            score_comparisons=score_comparisons,
            target_year=target_year,
        )
        if _is_generation_artifact(raw_answer)
        else raw_answer
    )
    generated_answer = _advisory_score_echo(generated_answer, analysis)
    generated_answer = _remove_duplicate_major_code_bullets(generated_answer, analysis)
    generated_answer = _ensure_score_advisory_open_question(generated_answer, analysis)
    validated = _validate_generated_answer(
        generated_answer,
        evidence=evidence,
        question=question,
        analysis=analysis,
        score_comparisons=score_comparisons,
        target_year=target_year,
    )
    validated = _check_required_phrases(validated, generated_answer, required_phrases)
    reason = validated.get("_validation_reason")
    retry_advisory_fallback = (
        reason == "model_fallback" and analysis.intent == "TU_VAN_CHON_NGANH"
    )
    if validated.get("status") == "no_data" and (
        reason in _RETRYABLE_VALIDATION_REASONS or retry_advisory_fallback
    ):
        try:
            retry_prompt = _retry_prompt(
                    prompt,
                    raw_answer,
                    score_facts,
                    evidence,
                    analysis,
                    score_comparisons,
                )
            required = [str(phrase).strip() for phrase in required_phrases or () if str(phrase).strip()]
            if required:
                retry_prompt += (
                    "\n\nBẢN ĐÁP ÁN TRƯỚC ĐÃ BỎ SÓT NỘI DUNG BẮT BUỘC. "
                    "Ở lần trả lời này, hãy bao gồm đầy đủ các cụm/tiêu đề sau, "
                    "không bỏ bất kỳ mục nào: "
                    + "; ".join(required)
                )
            retry_answer = active_llm.generate(retry_prompt)
        except Exception:
            # A retryable draft must not turn into a generic runtime error when
            # a local model/adapter cannot produce the second draft. Return the
            # validated failure so the grounded fallback can use state/evidence.
            return validated
        retry_answer = (
            _realize_generation_artifact(
                retry_answer,
                analysis=analysis,
                answer_plan=answer_plan,
                evidence=evidence,
                score_facts=score_facts,
                score_comparisons=score_comparisons,
                target_year=target_year,
            )
            if _is_generation_artifact(retry_answer)
            else retry_answer
        )
        retry_answer = _advisory_score_echo(retry_answer, analysis)
        retry_answer = _remove_duplicate_major_code_bullets(retry_answer, analysis)
        retry_answer = _ensure_score_advisory_open_question(retry_answer, analysis)
        validated = _validate_generated_answer(
            retry_answer,
            evidence=evidence,
            question=question,
            analysis=analysis,
            score_comparisons=score_comparisons,
            target_year=target_year,
        )
        validated = _check_required_phrases(validated, retry_answer, required_phrases)
    return validated


def _check_required_phrases(
    validated: dict[str, object], answer: str, required_phrases: Any
) -> dict[str, object]:
    """Reject an otherwise grounded answer when it silently omits a required section."""

    if validated.get("status") != "ok":
        return validated
    folded_answer = normalize_question(answer)
    missing = [
        str(phrase).strip()
        for phrase in required_phrases or ()
        if str(phrase).strip()
        and normalize_question(str(phrase)) not in folded_answer
    ]
    if not missing:
        return validated
    return {
        "answer": FALLBACK_ANSWER,
        "sources": [],
        "status": "no_data",
        "_validation_reason": "required_content_missing",
    }


def _validate_generated_answer(
    answer: str,
    *,
    evidence: Any,
    question: str,
    analysis: QueryAnalysis,
    score_comparisons: Any,
    target_year: int,
) -> dict[str, object]:
    if len(answer) > _MAX_GENERATED_ANSWER_CHARS:
        reason = "answer_too_long"
    elif _is_context_echo(answer, evidence):
        reason = "context_echo"
    else:
        reason = _score_comparison_failure(answer, score_comparisons, analysis)
    if reason:
        return {
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "_validation_reason": reason,
        }
    return validate_model_answer(
        answer,
        evidence,
        question=question,
        analysis=analysis,
        target_year=target_year,
    )
