"""Pipeline coordination utilities: retrieval, trace assembly, and boundary answers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from src.config.settings import Settings, settings
from src.retrieval.retriever import DHVRetriever, RetrievalResult
from .answer_planner import AnswerPlan, plan_answer
from .evidence import EvidenceSelection
from .output_validator import (
    AMBIGUOUS_SCHOOL_ANSWER,
    CLARIFICATION_ANSWER,
    EXTERNAL_SCHOOL_ANSWER,
    MIXED_SCHOOL_ANSWER,
)
from .query_analysis import (
    ConversationState,
    QueryAnalysis,
    _is_admission_date_comparison,
    _is_formula_request,
    _is_global_catalog_request,
    _is_website_request,
    normalize_question,
    should_inherit_context,
    update_conversation_state,
)
from .scope_guard import (
    SCOPE_REASON_AMBIGUOUS_SCHOOL,
    SCOPE_REASON_EXTERNAL_SCHOOL,
    SCOPE_REASON_MIXED_SCHOOL,
    TARGET_SCHOOL_AMBIGUOUS,
    TARGET_SCHOOL_MIXED,
    TARGET_SCHOOL_OTHER,
    is_in_scope,
    scope_reason,
)

_ADVISORY_SAFE_FALLBACK_REASONS = frozenset(
    {
        "model_fallback",
        "ungrounded",
        "missing_threshold_mapping",
        "ungrounded_entity",
        "wrong_threshold_mapping",
        "wrong_supplementary_mapping",
        "missing_admission_score",
        "score_type_mismatch",
        "method_mismatch",
        "program_relation_missing",
        "program_relation_wrong",
        "advisory_choices_incomplete",
        "unsupported_advisory_fit",
        "year_mismatch",
    }
)

_DETERMINISTIC_SYSTEM_ANSWERS = {
    "GREETING": (
        "Chào bạn! Mình là trợ lý AI phục vụ đồ án học tập/nghiên cứu, hỗ trợ tra cứu "
        "tuyển sinh DHV. Bạn có thể hỏi về ngành, chương trình, phương thức "
        "xét tuyển, học phí, học bổng, hồ sơ hoặc lịch tuyển sinh năm 2026."
    ),
    "THANKS": "Không có gì! Nếu cần, bạn cứ hỏi thêm về tuyển sinh DHV nhé.",
    "SYSTEM_IDENTITY": (
        "Mình là trợ lý AI phục vụ đồ án học tập/nghiên cứu, hỗ trợ tra cứu tuyển sinh "
        "DHV. Mình không phải chatbot hay kênh thông tin chính thức "
        "của DHV; với thông tin quan trọng, bạn nên kiểm tra lại trên kênh chính thức "
        "của nhà trường."
    ),
    "SYSTEM_SCOPE": (
        "Mình hỗ trợ tra cứu thông tin tuyển sinh DHV năm 2026 và thông tin về trường "
        "liên quan trực tiếp đã được kiểm chứng. Đây không phải toàn bộ thông tin của "
        "DHV; mình không tự suy đoán những nội dung chưa có trong dữ liệu. Bạn có thể "
        "hỏi về ngành, chương trình, phương thức xét tuyển, điểm, học phí, học bổng, "
        "hồ sơ, lịch tuyển sinh hoặc nhập học."
    ),
}

_DEFAULT_RETRIEVER: Any | None = None


def _get_default_retriever(settings_obj: Settings = settings) -> Any:
    global _DEFAULT_RETRIEVER
    if _DEFAULT_RETRIEVER is None or getattr(_DEFAULT_RETRIEVER, "settings", None) != settings_obj:
        _DEFAULT_RETRIEVER = DHVRetriever(settings_obj=settings_obj)
    return _DEFAULT_RETRIEVER


def _analysis_with_state(analysis: QueryAnalysis, state: ConversationState) -> QueryAnalysis:
    entities = dict(analysis.entities)
    school_target = str(entities.get("target_school") or "UNSPECIFIED")
    can_inherit_dhv_entities = school_target in {"DHV", "UNSPECIFIED"}
    inherit_context = can_inherit_dhv_entities and should_inherit_context(
        analysis.normalized_question,
        analysis.intent,
        state.previous_intent,
        state,
    )
    if (
        inherit_context
        and not entities.get("major_name")
        and state.current_major
        and not entities.get("program_name")
        and analysis.intent != "HOI_HOC_PHI"
        and not (
            analysis.intent == "DANH_SACH_CHUONG_TRINH"
            and _is_global_catalog_request(analysis.normalized_question)
        )
    ):
        entities["major_name"] = state.current_major
        entities["entity_type"] = "major"
    if (
        inherit_context
        and not entities.get("candidate_majors")
        and state.candidate_majors
    ):
        entities["candidate_majors"] = list(state.candidate_majors)
    if (
        inherit_context
        and not entities.get("candidate_programs")
        and state.candidate_programs
    ):
        entities["candidate_programs"] = list(state.candidate_programs)
    candidate_names: set[str] = set()
    for key in ("candidate_majors", "candidate_programs"):
        values = entities.get(key)
        if isinstance(values, (list, tuple)):
            candidate_names.update(str(value).strip() for value in values if str(value).strip())
    candidate_count = len(candidate_names)
    explicit_choice = bool(
        "toi chon" in analysis.normalized_question
        or "minh chon" in analysis.normalized_question
        or "da chon" in analysis.normalized_question
    )
    if analysis.intent == "TU_VAN_CHON_NGANH" and candidate_count > 1 and not explicit_choice:
        entities["major_name"] = None
        entities["major_code"] = None
        entities["program_name"] = None
        entities["parent_major"] = None
        entities["entity_type"] = "ambiguous"
    if not entities.get("year"):
        entities["year"] = state.current_year
    return replace(analysis, entities=entities)


def _trace(
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
    retrieval_audit: Any = None,
    evidence_selection: EvidenceSelection | None = None,
    answer_plan: AnswerPlan | None = None,
) -> dict[str, object]:
    has_admissions_entity = any(
        analysis.entities.get(key)
        for key in (
            "major_name",
            "major_code",
            "program_name",
            "candidate_majors",
            "candidate_programs",
            "admission_method",
            "student_scores",
        )
    )
    trace = {
        "intent": analysis.intent,
        "intent_classifier": {
            "source": analysis.intent_source,
            "confidence": analysis.intent_confidence,
        },
        "entities": dict(analysis.entities),
        "router": plan.to_dict(),
        "conversation_state": state.to_dict(),
        "retrieval": retrieval_audit.to_dict() if retrieval_audit is not None else None,
        "retrieval_calls": 0,
        "retrieved_docs_count": 0,
        "retrieved_chunks": 0,
        "evidence_count": 0,
        "scope": {
            "in_scope": is_in_scope(
                str(analysis.entities.get("contextual_question") or analysis.question),
                has_admissions_entity=has_admissions_entity,
                target_school=analysis.entities.get("target_school"),
                has_verified_school_info=bool(analysis.entities.get("verified_school_info_scope")),
            ),
            "target_school": analysis.entities.get("target_school", "UNSPECIFIED"),
            "school_mentions": list(analysis.entities.get("school_mentions") or ()),
            "scope_reason": analysis.entities.get("scope_reason")
            or scope_reason(
                analysis.question,
                target_school=analysis.entities.get("target_school"),
                has_admissions_entity=has_admissions_entity,
                has_verified_school_info=bool(analysis.entities.get("verified_school_info_scope")),
            ),
            "has_admissions_entity": has_admissions_entity,
        },
    }
    if evidence_selection is not None:
        trace["evidence_selection"] = evidence_selection.to_dict()
    if getattr(plan, "pre_rag_decomposition", None) is not None:
        trace["pre_rag_decomposition"] = dict(plan.pre_rag_decomposition)
    if answer_plan is not None:
        trace["answer_plan"] = answer_plan.to_dict()
    return trace


def _attach_answer_plan(
    result: dict[str, object],
    answer_plan: AnswerPlan,
) -> dict[str, object]:
    """Đưa contract planner ra API và giữ gợi ý tách khỏi nội dung model."""

    payload = answer_plan.to_dict()
    result["answer_plan"] = payload
    if answer_plan.related_questions:
        result["related_questions"] = list(answer_plan.related_questions)
    trace = result.get("trace")
    if isinstance(trace, dict):
        scope_trace = trace.get("scope")
        if isinstance(scope_trace, dict):
            target_school = str(scope_trace.get("target_school") or "UNSPECIFIED")
            if result.get("status") == "no_data" and target_school in {"DHV", "UNSPECIFIED"}:
                scope_trace["scope_reason"] = "related_no_data"
            result.setdefault("target_school", target_school)
            result.setdefault("scope_reason", scope_trace.get("scope_reason"))
        trace["answer_plan"] = payload
        trace["final_status"] = result.get("status")
    return result


def _planned_boundary_result(
    *,
    answer: str,
    status: str,
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
    retrieval_audit: Any = None,
    trace: dict[str, object] | None = None,
) -> dict[str, object]:
    """Chuẩn hóa các kết thúc an toàn để trace luôn nói rõ mode đã chọn."""

    answer_plan = plan_answer(analysis, status=status)
    active_trace = trace or _trace(
        analysis,
        plan,
        state,
        retrieval_audit,
        answer_plan=answer_plan,
    )
    active_trace["answer_plan"] = answer_plan.to_dict()
    return _attach_answer_plan(
        {
            "answer": answer,
            "sources": [],
            "status": status,
            "state": state.to_dict(),
            "conversation_state": state.to_dict(),
            "trace": active_trace,
        },
        answer_plan,
    )


def _clarification_result(
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
) -> dict[str, object]:
    next_state = update_conversation_state(state, analysis)
    answer_plan = plan_answer(analysis, status="clarification")
    answer = CLARIFICATION_ANSWER
    if plan.clarification_reason == "admission_method_for_personal_score":
        answer = "Bạn cho mình biết điểm này theo phương thức nào: thi tốt nghiệp THPT, học bạ hay ĐGNL?"
    return _attach_answer_plan({
        "answer": answer,
        "sources": [],
        "status": "clarification",
        "state": next_state.to_dict(),
        "conversation_state": next_state.to_dict(),
        "trace": _trace(analysis, plan, next_state, answer_plan=answer_plan),
    }, answer_plan)


def _school_scope_boundary_result(
    *,
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
    target_school: str,
    scope_reason_value: str,
) -> dict[str, object]:
    """Kết thúc trước retrieval cho external/mixed/ambiguous school."""

    next_state = update_conversation_state(state, analysis)
    if target_school == TARGET_SCHOOL_AMBIGUOUS:
        answer = AMBIGUOUS_SCHOOL_ANSWER
        status = "clarification"
    elif target_school == TARGET_SCHOOL_MIXED:
        answer = MIXED_SCHOOL_ANSWER
        status = "out_of_scope"
    else:
        answer = EXTERNAL_SCHOOL_ANSWER
        status = "out_of_scope"
    answer_plan = plan_answer(analysis, status=status)
    trace = _trace(analysis, plan, next_state, answer_plan=answer_plan)
    trace["retrieved_docs_count"] = 0
    trace["evidence_count"] = 0
    trace["retrieval_calls"] = 0
    trace["scope"]["scope_reason"] = scope_reason_value
    return _attach_answer_plan(
        {
            "answer": answer,
            "sources": [],
            "status": status,
            "scope_reason": scope_reason_value,
            "target_school": target_school,
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        },
        answer_plan,
    )


def _retrieve(
    retriever: Any,
    question: str,
    plan: Any,
) -> tuple[list[Any], Any]:
    method = getattr(retriever, "retrieve_with_audit", None)
    if callable(method):
        entity_filters = dict(getattr(plan, "entity_filters", {}) or {})
        normalized_query = normalize_question(question)
        expanded_directory_top_k = None
        expanded_school_code_top_k = None
        expanded_combination_top_k = None
        expanded_score_top_k = None
        if (
            (getattr(plan, "intent", "") == "SCHOOL_INFO" or _is_website_request(normalized_query))
            and "thong_tin_truong" in tuple(getattr(plan, "categories", ()) or ())
        ):
            expanded_directory_top_k = 64
        if (
            getattr(plan, "intent", "") == "HOI_CO_SO_LIEN_HE"
            and "ma truong" in normalized_query
        ):
            expanded_school_code_top_k = 8
        if (
            (
                getattr(plan, "intent", "") == "HOI_PHUONG_THUC_XET_TUYEN"
                and (
                    entity_filters.get("admission_combination_detail")
                    or entity_filters.get("admission_method")
                )
            )
            or (
                getattr(plan, "intent", "") == "HOI_CACH_TINH_DIEM"
                and entity_filters.get("admission_method") == "thpt"
                and _is_formula_request(normalized_query)
            )
        ):
            expanded_combination_top_k = 16
        if (
            getattr(plan, "intent", "") == "TU_VAN_CHON_NGANH"
            and "application_threshold" in str(getattr(plan, "retrieval_query", ""))
        ):
            expanded_score_top_k = 32
        if (
            getattr(plan, "intent", "") in {"HOI_NGUONG_DAU_VAO", "HOI_DIEM_TRUNG_TUYEN"}
            and len(entity_filters.get("candidate_majors", ())) > 1
        ):
            expanded_score_top_k = max(expanded_score_top_k or 0, 64)
        if (
            getattr(plan, "intent", "") == "HOI_NGUONG_DAU_VAO"
            and "phuong_thuc_xet_tuyen" in tuple(getattr(plan, "categories", ()) or ())
            and entity_filters.get("admission_method") in {"dgnl", "h_sca", "thpt", "hoc_ba"}
        ):
            expanded_score_top_k = max(expanded_score_top_k or 0, 32)
        expanded_scholarship_top_k = None
        if getattr(plan, "intent", "") == "HOI_HOC_BONG":
            expanded_scholarship_top_k = 96
        expanded_enrollment_top_k = None
        if (
            (
                getattr(plan, "intent", "") in {"HOI_NHAP_HOC", "HOI_HO_SO"}
                or getattr(plan, "intent", "") == "HOI_LICH_TUYEN_SINH"
                and "tiep nhan tan sinh vien" in normalized_query
            )
            and any(
                category in {"ho_so", "nhap_hoc"}
                for category in tuple(getattr(plan, "categories", ()) or ())
            )
        ):
            expanded_enrollment_top_k = 64
        expanded_supplementary_detail_top_k = None
        if (
            getattr(plan, "intent", "") == "HOI_XET_TUYEN_BO_SUNG"
            and any(marker in normalized_query for marker in (
                "nhan ho so", "thoi gian nhan ho so", "han nhan ho so",
                "nop ho so", "truc tuyen", "co so",
            ))
        ):
            expanded_supplementary_detail_top_k = 32
        expanded_admission_detail_top_k = None
        is_result_notification = (
            getattr(plan, "intent", "") == "HOI_DANG_KY_XET_TUYEN"
            and "trung tuyen" in normalized_query
            and any(marker in normalized_query for marker in (
                "thong bao", "vao dau", "bao ket qua", "nhan ket qua",
            ))
        )
        is_intake_start_date = (
            getattr(plan, "intent", "") == "HOI_LICH_TUYEN_SINH"
            and "tiep nhan tan sinh vien" in normalized_query
        )
        is_eligibility = (
            getattr(plan, "intent", "") in {"HOI_DANG_KY_XET_TUYEN", "HOI_NGUONG_DAU_VAO"}
            and any(marker in normalized_query for marker in (
                "dieu kien", "tot nghiep", "duoc dang ky", "hoc luc", "lop 12",
            ))
        )
        if is_result_notification:
            expanded_admission_detail_top_k = 128
        elif (
            is_intake_start_date
            or is_eligibility
            or (
            getattr(plan, "intent", "") == "HOI_LICH_TUYEN_SINH"
            and _is_admission_date_comparison(normalized_query)
            )
        ):
            expanded_admission_detail_top_k = 64
        expanded_enumeration_top_k = None
        if (
            getattr(plan, "query_mode", "") in {"COUNT", "LIST", "LIST_AND_COUNT"}
            and (
                getattr(plan, "intent", "")
                not in {"HOI_NGUONG_DAU_VAO", "HOI_DIEM_TRUNG_TUYEN", "HOI_XET_TUYEN_BO_SUNG"}
                or getattr(plan, "intent", "") == "HOI_XET_TUYEN_BO_SUNG"
                and getattr(plan, "query_mode", "") in {"LIST", "LIST_AND_COUNT"}
            )
        ):
            expanded_enumeration_top_k = 64
        if (
            getattr(plan, "intent", "") in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
            and not entity_filters.get("major_name")
        ):
            expanded_enumeration_top_k = max(expanded_enumeration_top_k or 0, 96)
        try:
            kwargs = {
                "categories": plan.categories,
                "retrieval_query": plan.retrieval_query,
                "entity_filters": entity_filters,
            }
            data_roles = tuple(getattr(plan, "data_roles", ()) or ())
            if data_roles:
                kwargs["data_roles"] = data_roles
            if (
                expanded_directory_top_k is not None
                or expanded_school_code_top_k is not None
                or expanded_combination_top_k is not None
                or expanded_score_top_k is not None
                or expanded_scholarship_top_k is not None
                or expanded_enrollment_top_k is not None
                or expanded_supplementary_detail_top_k is not None
                or expanded_admission_detail_top_k is not None
                or expanded_enumeration_top_k is not None
            ):
                kwargs["top_k"] = max(
                    value
                    for value in (
                        expanded_directory_top_k,
                        expanded_school_code_top_k,
                        expanded_combination_top_k,
                        expanded_score_top_k,
                        expanded_scholarship_top_k,
                        expanded_enrollment_top_k,
                        expanded_supplementary_detail_top_k,
                        expanded_admission_detail_top_k,
                        expanded_enumeration_top_k,
                    )
                    if value is not None
                )
            result = method(question, **kwargs)
        except TypeError:
            try:
                result = method(
                    question,
                    categories=plan.categories,
                    retrieval_query=plan.retrieval_query,
                )
            except TypeError:
                result = method(question)
        if isinstance(result, RetrievalResult):
            return list(result.documents), result.audit
        if isinstance(result, Mapping):
            documents = list(result.get("documents") or [])
            return documents, result.get("audit")
        documents = list(getattr(result, "documents", ()) or ())
        return documents, getattr(result, "audit", None)
    return list(retriever.retrieve(plan.retrieval_query)), None
