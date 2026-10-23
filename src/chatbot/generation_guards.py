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
from .output_validator import validate_model_answer
from .query_analysis import QueryAnalysis, normalize_question
from .scholarship_formatters import _evidence_scholarship_answer
from .school_info_formatters import _evidence_overview_answer
from .tuition_formatters import _evidence_semester_system_answer

_RETRYABLE_VALIDATION_REASONS = frozenset(
    {
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
    }
)


def _retry_prompt(
    prompt: str,
    draft: str,
    facts: Any,
    evidence: Any,
    analysis: QueryAnalysis | None = None,
) -> str:
    checklist = "; ".join(
        f"{fact.get('method')} → {fact.get('raw_value')}"
        for fact in facts
        if fact.get("method") != "deadline"
    )
    labeled_amounts: list[str] = []
    for chunk in getattr(evidence, "chunks", ()):
        for line in chunk.text.splitlines():
            normalized = line.casefold()
            if "học phí" in normalized or "hoc phi" in normalized or "tổng chi phí" in normalized or "tong chi phi" in normalized:
                line = line.strip()
                if line and line not in labeled_amounts:
                    labeled_amounts.append(line)
    amount_instruction = ""
    if labeled_amounts:
        amount_instruction = (
            " Đây là câu hỏi về học phí: bắt buộc chép dòng bắt đầu bằng "
            "nhãn Học phí với đúng giá trị; không dùng dòng Tổng chi phí để "
            "thay thế. Các dòng khoản tiền cần giữ đúng nhãn và giá trị: "
            + " | ".join(labeled_amounts[:4])
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
        parents = [str(relation.get("parent_major")) for relation in relations if relation.get("parent_major")]
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
                relation_instruction += " Mã ngành hợp lệ của ngành cha: " + ", ".join(sorted(set(allowed_codes))) + "."
    return (
        f"{prompt}\n\nBẢN NHÁP CẦN KIỂM TRA:\n{draft[:2000]}\n\n"
        "Hãy tạo lại câu trả lời chỉ từ CONTEXT. Checklist mapping bắt buộc: "
        f"{checklist}. Phải nêu đủ từng mapping trong checklist, giữ nguyên dấu '-' nếu có, "
        "không thêm số và không kết luận đậu/trượt."
        + amount_instruction
        + relation_instruction
        + "\n\nCÂU TRẢ LỜI MỚI:\n"
    )


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


def _combination_is_verified(evidence: Any, combination: object) -> bool:
    """Chỉ coi A00/A01... là có dữ liệu khi evidence có dòng khẳng định tích cực."""

    token = normalize_question(str(combination or "")).upper()
    if not token:
        return True
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
        if token.casefold() not in folded.upper():
            continue
        if any(marker in folded for marker in negative_markers):
            continue
        if "to hop" in folded or token.casefold() in folded:
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
            line for line in _evidence_text_lines(evidence)
            if normalize_question(line).startswith(("hoc phi hki", "hoc phi:", "• hoc phi hki"))
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
    validated = validate_model_answer(
        generated_answer,
        evidence,
        question=question,
        analysis=analysis,
        target_year=target_year,
    )
    reason = validated.get("_validation_reason")
    retry_advisory_fallback = reason == "model_fallback" and analysis.intent == "TU_VAN_CHON_NGANH"
    if validated.get("status") == "no_data" and (
        reason in _RETRYABLE_VALIDATION_REASONS or retry_advisory_fallback
    ):
        try:
            retry_answer = active_llm.generate(
                _retry_prompt(prompt, raw_answer, score_facts, evidence, analysis)
            )
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
        validated = validate_model_answer(
            retry_answer,
            evidence,
            question=question,
            analysis=analysis,
            target_year=target_year,
        )
    return validated
