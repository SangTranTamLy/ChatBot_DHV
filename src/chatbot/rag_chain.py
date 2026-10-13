"""Điều phối RAG kèm theo phân tích, trạng thái hội thoại giới hạn và kiểm toán (audit)."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from src.config.settings import Settings, settings
from src.models.local_llm import LocalLLM, OllamaError, OllamaUnavailableError
from src.prompts.rag_prompt import build_rag_prompt
from src.retrieval.retriever import (
    DHVRetriever,
    RetrievalResult,
    RetrieverEmbeddingError,
    VectorDatabaseError,
    requested_year,
)

from .admission_answers import (
    _application_documents_missing_evidence,
    _asks_for_each_admission_method,
    _evidence_admission_bonus_answer,
    _evidence_admission_combination_answer,
    _evidence_admission_method_presence_answer,
    _evidence_applicant_support_answer,
    _evidence_application_registration_answer,
    _evidence_date_comparison_answer,
    _evidence_eligibility_answer,
    _evidence_enrollment_answer,
    _evidence_exam_subject_count_answer,
    _evidence_formula_answer,
    _evidence_general_registration_answer,
    _evidence_law_grade_eligibility_answer,
    _evidence_major_eligibility_answer,
    _evidence_method_application_threshold_answer,
    _evidence_method_calculation_answer,
    _evidence_required_document_answer,
    _evidence_result_notification_answer,
    _evidence_schedule_answer,
    _evidence_score_comparison_reason_answer,
    _evidence_score_list_answer,
    _evidence_subject_minimum_answer,
    _evidence_supplementary_majors_answer,
    _evidence_vocational_same_group_eligibility_answer,
    _is_result_notification_question,
    _method_label,
    _prioritize_admission_date_comparison_documents,
    _prioritize_enrollment_document_records,
    _prioritize_result_notification_documents,
    _requested_admission_method_number,
    _structured_comparison_answer,
    _structured_score_answer,
    _verified_admission_conditions_section,
)
from .answer_planner import AnswerPlan, plan_answer
from .catalog_formatters import (
    _MAJOR_GROUP_LABELS,
    _advisory_answer_has_guidance,
    _advisory_evidence_clarification,
    _advisory_preferred_program,
    _candidate_values,
    _deterministic_recommendation_answer,
    _evidence_catalog_answer,
    _evidence_program_relation_answer,
    _has_verified_advisory_fit_evidence,
    _major_in_group,
    _major_rows_from_evidence,
    _method_details_from_evidence,
    _program_detail_missing_evidence,
    _program_rows_from_evidence,
    _source_ordered_documents,
)
from .evidence import (
    EvidenceSelection,
    build_evidence,
    merge_evidence_bundles,
    select_evidence_documents,
    select_program_relations,
)
from .evidence_utils import (
    _bullet_content_lines,
    _evidence_sentences,
    _evidence_text_lines,
    _is_official_dhv_source,
    _metadata_chunk_index,
    _metadata_page,
    _remove_unresolved_url_label,
    _split_source_sentences,
)
from .generation_guards import (
    _RETRYABLE_VALIDATION_REASONS,
    _combination_is_verified,
    _is_generation_artifact,
    _realize_generation_artifact,
    _retry_prompt,
    _validated_generation,
)
from .multi_issue import (
    _MULTI_ISSUE_LABELS,
    _ask_multi_issue,
    _dedupe_sources,
    _filter_documents_for_plan,
)
from .official_links import (
    _OFFICIAL_WEBSITE_DIRECTORY,
    _official_links_answer,
    _requested_website_entry,
)
from .output_validator import (
    AMBIGUOUS_SCHOOL_ANSWER,
    CLARIFICATION_ANSWER,
    ERROR_ANSWER,
    EXTERNAL_SCHOOL_ANSWER,
    FALLBACK_ANSWER,
    MIXED_SCHOOL_ANSWER,
    OLLAMA_OFFLINE_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    VECTOR_DB_ERROR_ANSWER,
    validate_model_answer,
)
from .pipeline_utils import (
    _ADVISORY_SAFE_FALLBACK_REASONS,
    _DEFAULT_RETRIEVER,
    _DETERMINISTIC_SYSTEM_ANSWERS,
    _analysis_with_state,
    _attach_answer_plan,
    _clarification_result,
    _get_default_retriever,
    _planned_boundary_result,
    _retrieve,
    _school_scope_boundary_result,
    _trace,
)
from .query_analysis import (
    ConversationState,
    QueryAnalysis,
    QueryPlan,
    _is_admission_date_comparison,
    _is_admissions_context_followup,
    _is_formula_request,
    _is_global_catalog_request,
    _is_subject_minimum_request,
    analyze_question,
    deterministic_score_comparisons,
    deterministic_score_evaluation,
    enrich_analysis_from_evidence,
    normalize_entity_name,
    normalize_question,
    route_question,
    select_relevant_score_facts,
    should_inherit_context,
    update_conversation_state,
)
from .query_decomposer import decompose_question, should_attempt_decomposition
from .query_semantics import (
    excludes_optional_english_test,
    is_semester_fee_total_question,
    mentions_optional_english_test,
    should_include_optional_english_fee,
)
from .scholarship_formatters import (
    _evidence_admission_scholarship_conditions_answer,
    _evidence_scholarship_answer,
    _evidence_scholarship_catalog_answer,
    _is_admission_scholarship_conditions_question,
    _is_scholarship_heading,
    _prioritize_admission_scholarship_conditions_documents,
    _prioritize_scholarship_catalog_documents,
)
from .school_info_formatters import (
    _evidence_directory_answer,
    _evidence_overview_answer,
    _evidence_school_code_answer,
    _evidence_school_info_answer,
    _has_school_overview_request_marker,
    _is_generic_school_overview_request,
    _is_school_overview_intro_heading,
    _is_verified_school_overview_intro_document,
    _named_unit_relation_missing_evidence,
    _overview_intro_evidence,
    _overview_sources,
    _prioritize_school_overview_documents,
    _school_info_detail_missing_evidence,
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
from .tuition_formatters import (
    _evidence_optional_english_fee_answer,
    _evidence_semester_system_answer,
    _evidence_tuition_answer,
    _evidence_tuition_per_credit_answer,
    _evidence_tuition_total_answer,
)


def _try_pre_rag_decomposition(
    *,
    analysis: QueryAnalysis,
    plan: QueryPlan,
    llm: Any | None,
    query_planner: Any | None,
    settings_obj: Settings,
) -> tuple[QueryAnalysis, QueryPlan, Any | None]:
    """Optionally split an in-scope compound query before any retrieval."""

    if not should_attempt_decomposition(analysis, plan):
        return analysis, plan, llm

    planner_llm = query_planner
    if planner_llm is None and llm is not None:
        trace: dict[str, object] = {
            "status": "skipped",
            "reason": "separate_planner_not_configured_for_injected_generator",
            "parts": [],
        }
        return analysis, replace(plan, pre_rag_decomposition=trace), llm
    try:
        if planner_llm is None:
            planner_llm = LocalLLM(settings_obj=settings_obj)
        outcome = decompose_question(analysis.question, planner_llm)
    except Exception:
        outcome = None

    if outcome is None:
        trace: dict[str, object] = {
            "status": "rejected",
            "reason": "planner_unavailable",
            "parts": [],
        }
        return analysis, replace(plan, pre_rag_decomposition=trace), llm

    trace = outcome.to_dict()
    if not outcome.accepted:
        return analysis, replace(plan, pre_rag_decomposition=trace), llm

    shared_entity_keys = (
        "year",
        "target_school",
        "school_mentions",
        "explicit_school",
        "scope_reason",
        "major_name",
        "major_code",
        "program_name",
        "parent_major",
        "entity_type",
        "candidate_majors",
        "candidate_programs",
        "admission_method",
        "candidate_methods",
        "score_type",
        "score_query_type",
        "score_value",
        "student_scores",
        "interest",
        "admission_combination",
    )
    neutral_state = ConversationState(current_year=settings_obj.target_year)
    subplans: list[QueryPlan] = []
    sub_analyses: list[QueryAnalysis] = []
    rejection_reason: str | None = None
    for part in outcome.parts:
        child_analysis = analyze_question(
            part,
            neutral_state,
            default_year=settings_obj.target_year,
        )
        child_target = str(child_analysis.entities.get("target_school") or "UNSPECIFIED")
        if child_target in {"OTHER_SCHOOL", "MIXED", "AMBIGUOUS"}:
            rejection_reason = "part_crosses_school_boundary"
            break
        if child_analysis.intent in {
            "OUT_OF_SCOPE",
            "MULTI_ISSUE",
            "GREETING",
            "THANKS",
            "SYSTEM_IDENTITY",
            "SYSTEM_SCOPE",
        }:
            rejection_reason = "part_not_independently_routable"
            break

        child_entities = dict(child_analysis.entities)
        for key in shared_entity_keys:
            inherited = analysis.entities.get(key)
            current = child_entities.get(key)
            if inherited not in (None, "", [], {}, ()) and current in (None, "", [], {}, ()):
                child_entities[key] = inherited
        child_analysis = replace(child_analysis, entities=child_entities)
        child_plan = route_question(
            child_analysis,
            neutral_state,
            target_year=settings_obj.target_year,
        )
        if child_plan.needs_clarification:
            rejection_reason = "part_requires_clarification"
            break
        if not child_plan.categories or child_plan.subplans:
            rejection_reason = "part_has_no_supported_route"
            break
        if int(child_entities.get("year") or settings_obj.target_year) != int(
            analysis.entities.get("year") or settings_obj.target_year
        ):
            rejection_reason = "part_year_conflicts_with_question"
            break
        subplans.append(child_plan)
        sub_analyses.append(child_analysis)

    intents = [child.intent for child in sub_analyses]
    if rejection_reason is None and (
        len(subplans) < 2 or len(set(intents)) != len(intents)
    ):
        rejection_reason = "parts_do_not_resolve_distinct_issues"
    if rejection_reason is not None:
        trace = {
            **trace,
            "status": "rejected",
            "reason": rejection_reason,
            "routed_intents": intents,
        }
        return analysis, replace(plan, pre_rag_decomposition=trace), llm

    trace = {
        **trace,
        "status": "accepted",
        "reason": "validated_verbatim_spans_and_deterministic_routes",
        "routed_intents": intents,
        "scope_revalidated": True,
    }
    multi_entities = {
        **analysis.entities,
        "issue_intents": intents,
        "requested_information": intents,
    }
    multi_analysis = replace(
        analysis,
        intent="MULTI_ISSUE",
        entities=multi_entities,
        intent_source="llm_pre_rag_decomposition+deterministic_routes",
        intent_confidence=None,
    )
    categories = tuple(
        dict.fromkeys(category for subplan in subplans for category in subplan.categories)
    )
    multi_plan = QueryPlan(
        intent="MULTI_ISSUE",
        categories=categories,
        retrieval_query=plan.retrieval_query,
        metadata_filter=dict(plan.metadata_filter),
        needs_clarification=False,
        subplans=tuple(subplans),
        entity_filters=dict(plan.entity_filters),
        query_mode=plan.query_mode,
        pre_rag_decomposition=trace,
    )
    return multi_analysis, multi_plan, llm


def ask_chatbot(
    question: str,
    *,
    retriever: Any | None = None,
    llm: Any | None = None,
    query_planner: Any | None = None,
    settings_obj: Settings = settings,
    conversation_state: ConversationState | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Trả lời một lượt hỏi thông qua luồng: phân tích → router → truy xuất → sinh văn bản."""

    query = question.strip() if isinstance(question, str) else ""
    state = ConversationState.from_value(conversation_state, default_year=settings_obj.target_year)
    analysis = analyze_question(query, state, default_year=settings_obj.target_year)
    explicit_year = requested_year(query)
    inherit_year = explicit_year is None and should_inherit_context(
        analysis.normalized_question,
        analysis.intent,
        state.previous_intent,
        state,
    )
    query_year = (
        explicit_year
        if explicit_year is not None
        else state.current_year
        if inherit_year
        else settings_obj.target_year
    )
    if int(query_year) != int(settings_obj.target_year):
        settings_obj = replace(settings_obj, target_year=int(query_year))
    state = replace(state, current_year=int(query_year))
    analysis = replace(
        analysis,
        entities={**analysis.entities, "year": int(query_year)},
    )
    analysis = _analysis_with_state(analysis, state)
    plan = route_question(analysis, state, target_year=settings_obj.target_year)

    target_school = str(analysis.entities.get("target_school") or "UNSPECIFIED")
    if target_school in {
        TARGET_SCHOOL_OTHER,
        TARGET_SCHOOL_MIXED,
        TARGET_SCHOOL_AMBIGUOUS,
    }:
        return _school_scope_boundary_result(
            analysis=analysis,
            plan=plan,
            state=state,
            target_school=target_school,
            scope_reason_value=str(
                analysis.entities.get("scope_reason")
                or {
                    TARGET_SCHOOL_OTHER: SCOPE_REASON_EXTERNAL_SCHOOL,
                    TARGET_SCHOOL_MIXED: SCOPE_REASON_MIXED_SCHOOL,
                    TARGET_SCHOOL_AMBIGUOUS: SCOPE_REASON_AMBIGUOUS_SCHOOL,
                }[target_school]
            ),
        )

    if analysis.intent in _DETERMINISTIC_SYSTEM_ANSWERS:
        next_state = update_conversation_state(
            state,
            analysis,
            target_year=settings_obj.target_year,
        )
        answer_plan = plan_answer(analysis)
        return _attach_answer_plan({
            "answer": _DETERMINISTIC_SYSTEM_ANSWERS[analysis.intent],
            "sources": [],
            "status": "ok",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": _trace(analysis, plan, next_state, answer_plan=answer_plan),
        }, answer_plan)

    has_context_entity = bool(
        analysis.entities.get("major_name")
        or analysis.entities.get("major_code")
        or analysis.entities.get("program_name")
        or analysis.entities.get("candidate_majors")
        or analysis.entities.get("candidate_programs")
        or analysis.entities.get("admission_method")
        or analysis.entities.get("student_scores")
    )
    followup = (
        bool(state.current_major or state.current_program)
        and any(
            marker in analysis.normalized_question
            for marker in ("thi sao", "con", "vay", "bao nhieu", "diem")
        )
    ) or _is_admissions_context_followup(
        analysis.normalized_question,
        current_intent=analysis.intent,
        previous_intent=state.previous_intent,
    )
    catalog_followup = (
        analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
        and (
            bool(state.last_listed_majors)
            or state.previous_intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
        )
    )
    admission_date_comparison = (
        analysis.intent == "HOI_LICH_TUYEN_SINH"
        and _is_admission_date_comparison(analysis.normalized_question)
    )
    if analysis.intent == "OUT_OF_SCOPE" or (
        not is_in_scope(
            query,
            has_admissions_entity=has_context_entity,
            has_verified_school_info=bool(analysis.entities.get("verified_school_info_scope")),
        )
        and not has_context_entity
        and not followup
        and not catalog_followup
        and not admission_date_comparison
    ):
        next_state = update_conversation_state(state, analysis)
        answer_plan = plan_answer(analysis, status="out_of_scope")
        trace = _trace(analysis, plan, next_state, answer_plan=answer_plan)
        trace["retrieved_docs_count"] = 0
        trace["evidence_count"] = 0
        trace["retrieval_calls"] = 0
        return _attach_answer_plan({
            "answer": OUT_OF_SCOPE_ANSWER,
            "sources": [],
            "status": "out_of_scope",
            "scope_reason": analysis.entities.get("scope_reason", "general_out_of_scope"),
            "target_school": analysis.entities.get("target_school", "UNSPECIFIED"),
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if plan.needs_clarification:
        return _clarification_result(analysis, plan, state)

    analysis, plan, llm = _try_pre_rag_decomposition(
        analysis=analysis,
        plan=plan,
        llm=llm,
        query_planner=query_planner,
        settings_obj=settings_obj,
    )

    active_retriever = retriever or _get_default_retriever(settings_obj)
    if plan.subplans:
        try:
            return _ask_multi_issue(
                query=query,
                analysis=analysis,
                plan=plan,
                state=state,
                retriever=active_retriever,
                llm=llm,
                settings_obj=settings_obj,
            )
        except RetrieverEmbeddingError:
            return _planned_boundary_result(
                answer=OLLAMA_OFFLINE_ANSWER,
                status="ollama_offline",
                analysis=analysis,
                plan=plan,
                state=state,
            )
        except VectorDatabaseError:
            return _planned_boundary_result(
                answer=VECTOR_DB_ERROR_ANSWER,
                status="vector_db_error",
                analysis=analysis,
                plan=plan,
                state=state,
            )
        except OllamaUnavailableError:
            return _planned_boundary_result(
                answer=OLLAMA_OFFLINE_ANSWER,
                status="ollama_offline",
                analysis=analysis,
                plan=plan,
                state=state,
            )
        except OllamaError:
            return _planned_boundary_result(
                answer=FALLBACK_ANSWER,
                status="no_data",
                analysis=analysis,
                plan=plan,
                state=state,
            )
        except Exception:
            return _planned_boundary_result(
                answer=ERROR_ANSWER,
                status="error",
                analysis=analysis,
                plan=plan,
                state=state,
            )
    retrieval_audit = None
    try:
        documents, retrieval_audit = _retrieve(active_retriever, query, plan)
    except RetrieverEmbeddingError:
        return _planned_boundary_result(
            answer=OLLAMA_OFFLINE_ANSWER,
            status="ollama_offline",
            analysis=analysis,
            plan=plan,
            state=state,
        )
    except VectorDatabaseError:
        return _planned_boundary_result(
            answer=VECTOR_DB_ERROR_ANSWER,
            status="vector_db_error",
            analysis=analysis,
            plan=plan,
            state=state,
            retrieval_audit=retrieval_audit,
        )
    except Exception:
        return _planned_boundary_result(
            answer=ERROR_ANSWER,
            status="error",
            analysis=analysis,
            plan=plan,
            state=state,
        )

    candidate_values = _candidate_values(analysis)
    evidence_selection = select_evidence_documents(
        documents,
        categories=plan.categories,
        entities=analysis.entities,
        candidates=candidate_values,
        target_year=settings_obj.target_year,
        intent=analysis.intent,
    )
    evidence_documents = list(evidence_selection.documents)
    scholarship_conditions_evidence_prioritized = False
    if _is_admission_scholarship_conditions_question(analysis):
        evidence_documents, scholarship_conditions_evidence_prioritized = (
            _prioritize_admission_scholarship_conditions_documents(evidence_documents)
        )
    elif (
        analysis.intent == "HOI_HOC_BONG"
        and analysis.entities.get("query_mode") in {"LIST", "LIST_AND_COUNT"}
    ):
        evidence_documents = _prioritize_scholarship_catalog_documents(evidence_documents)
    if analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}:
        evidence_documents = _source_ordered_documents(evidence_documents)
    normalized_enrollment_query = normalize_question(analysis.normalized_question)
    enrollment_checklist_question = (
        analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"}
        and (
            analysis.entities.get("query_mode") in {"LIST", "LIST_AND_COUNT"}
            or any(marker in normalized_enrollment_query for marker in (
                "mang theo", "can mang", "giay to", "ho so nhap hoc", "can chuan bi",
            ))
        )
    )
    if enrollment_checklist_question:
        evidence_documents = _prioritize_enrollment_document_records(evidence_documents)
    date_comparison_evidence_reordered = (
        analysis.intent == "HOI_LICH_TUYEN_SINH"
        and _is_admission_date_comparison(analysis.normalized_question)
    )
    if date_comparison_evidence_reordered:
        evidence_documents = _prioritize_admission_date_comparison_documents(
            evidence_documents,
            analysis.normalized_question,
        )
    notification_evidence_reordered = _is_result_notification_question(
        analysis.normalized_question
    )
    if notification_evidence_reordered:
        evidence_documents = _prioritize_result_notification_documents(evidence_documents)
    school_overview_evidence_prioritized = False
    if _is_generic_school_overview_request(analysis):
        evidence_documents = _prioritize_school_overview_documents(
            evidence_documents,
            target_year=settings_obj.target_year,
        )
        school_overview_evidence_prioritized = bool(
            evidence_documents
            and _is_verified_school_overview_intro_document(
                evidence_documents[0],
                target_year=settings_obj.target_year,
            )
        )
    evidence = build_evidence(evidence_documents, settings_obj=settings_obj)
    analysis = enrich_analysis_from_evidence(analysis, evidence)
    score_comparisons = deterministic_score_comparisons(analysis, evidence)
    score_evaluation = deterministic_score_evaluation(analysis, evidence)
    listed_majors = None
    listed_programs = None
    listed_program_parents = None
    if analysis.intent == "DANH_SACH_NGANH":
        listed_majors = [major for major, _ in _major_rows_from_evidence(evidence)]
    elif analysis.intent == "DANH_SACH_CHUONG_TRINH":
        major_rows = _major_rows_from_evidence(evidence)
        program_rows = _program_rows_from_evidence(
            evidence,
            major_rows,
            parent_major=str(analysis.entities.get("major_name") or "").strip() or None,
        )
        listed_programs = [program for program, _, _ in program_rows]
        listed_program_parents = [parent for _, parent, _ in program_rows]
    next_state = update_conversation_state(
        state,
        analysis,
        target_year=settings_obj.target_year,
        last_listed_majors=listed_majors,
        last_list_count=len(listed_majors) if listed_majors is not None else None,
        last_listed_programs=listed_programs,
        last_listed_program_parents=listed_program_parents,
    )
    trace = _trace(
        analysis,
        plan,
        next_state,
        retrieval_audit,
        evidence_selection,
    )
    trace["retrieved_docs_count"] = len(documents)
    trace["retrieved_chunks"] = len(documents)
    trace["evidence_count"] = len(evidence_documents)
    trace["result_notification_evidence_prioritized"] = notification_evidence_reordered
    trace["enrollment_checklist_evidence_prioritized"] = enrollment_checklist_question
    trace["admission_date_evidence_prioritized"] = date_comparison_evidence_reordered
    trace["school_overview_evidence_prioritized"] = school_overview_evidence_prioritized
    trace["scholarship_conditions_evidence_prioritized"] = scholarship_conditions_evidence_prioritized
    trace["retrieval_calls"] = 1
    trace["score_comparisons"] = [dict(comparison) for comparison in score_comparisons]
    trace["score_engine"] = score_evaluation
    trace["score_facts"] = [dict(fact) for fact in evidence.score_facts]
    trace["selected_score_facts"] = [
        dict(fact)
        for fact in select_relevant_score_facts(analysis, evidence.score_facts)
    ]
    trace["matching_facts"] = list(trace["selected_score_facts"])
    score_query_type = analysis.entities.get("score_query_type")
    lookup_facts = select_relevant_score_facts(analysis, evidence.score_facts)
    structured_lookup_answer = (
        _evidence_score_list_answer(analysis, evidence)
        if analysis.entities.get("entity_type") == "major_list"
        else (
            _evidence_method_application_threshold_answer(analysis, evidence)
            or _evidence_score_comparison_reason_answer(analysis, evidence)
            or _structured_score_answer(analysis, lookup_facts)
        )
    )
    admission_rule_answer = None
    if analysis.intent in {"HOI_DANG_KY_XET_TUYEN", "HOI_NGUONG_DAU_VAO"}:
        admission_rule_answer = (
            _evidence_law_grade_eligibility_answer(analysis, evidence)
            or _evidence_method_application_threshold_answer(analysis, evidence)
            or _evidence_subject_minimum_answer(analysis, evidence)
            or _evidence_eligibility_answer(analysis, evidence)
            or _evidence_major_eligibility_answer(analysis, evidence)
        )
    deadline_only_lookup = bool(
        score_query_type == "supplementary_threshold_lookup"
        and any(fact.get("method") == "deadline" for fact in lookup_facts)
    )
    normalized_query = normalize_question(analysis.normalized_question)
    supplementary_route_question = (
        analysis.intent in {"HOI_XET_TUYEN_BO_SUNG", "HOI_DANG_KY_XET_TUYEN"}
        and any(marker in normalized_query for marker in (
            "xet bo sung", "xet tuyen bo sung", "tuyen sinh bo sung", "dot bo sung",
        ))
        and any(marker in normalized_query for marker in (
            "online", "truc tuyen", "den truong nop", "nop tai", "nop ho so",
            "nhan ho so", "thoi gian nhan ho so", "thoi han", "han nhan ho so", "khi nao nhan ho so",
            "hinh thuc nop", "dang ky truc tiep",
        ))
    )
    if (
        score_evaluation.get("status") == "insufficient-data"
        and not structured_lookup_answer
        and not deadline_only_lookup
        and not admission_rule_answer
        and not supplementary_route_question
    ):
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)
    if (
        analysis.entities.get("entity_type") == "major_list"
        and score_query_type in {
            "admission_score_lookup",
            "application_threshold_lookup",
            "supplementary_threshold_lookup",
        }
        and not structured_lookup_answer
    ):
        trace["evidence_boundary"] = "referenced_major_list_not_fully_supported"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)
    if not evidence.is_usable:
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if analysis.intent == "TU_VAN_CHON_NGANH" and not _has_verified_advisory_fit_evidence(
        analysis,
        evidence,
        state,
        target_year=settings_obj.target_year,
    ):
        trace["advisory_boundary"] = "personal_fit_not_in_verified_evidence"
        trace["validator"] = {
            "status": "clarification",
            "reason": "personal_fit_not_in_verified_evidence",
        }
        result = _advisory_evidence_clarification(
            analysis,
            evidence,
            next_state,
            score_comparisons,
        )
        answer_plan = plan_answer(analysis, evidence=evidence, status="clarification")
        trace["answer_plan"] = answer_plan.to_dict()
        trace["planner_mode"] = answer_plan.mode
        trace["final_status"] = "clarification"
        result["state"] = next_state.to_dict()
        result["conversation_state"] = next_state.to_dict()
        result["trace"] = trace
        return _attach_answer_plan(result, answer_plan)

    if (
        score_query_type in {
            "admission_score_lookup",
            "application_threshold_lookup",
            "supplementary_threshold_lookup",
        }
        and not analysis.entities.get("student_scores")
        and structured_lookup_answer
        and not supplementary_route_question
    ):
        selected_score_facts = lookup_facts
        direct_answer = structured_lookup_answer
        trace["deterministic_branch"] = str(score_query_type)
        trace["deterministic_selected_score_facts"] = [
            dict(fact) for fact in selected_score_facts
        ]
        if direct_answer:
            validated = validate_model_answer(
                direct_answer,
                evidence,
                question=query,
                analysis=analysis,
                target_year=settings_obj.target_year,
            )
            trace["deterministic_validation"] = {
                "status": validated.get("status"),
                "reason": validated.get("_validation_reason"),
            }
            trace["validator"] = dict(trace["deterministic_validation"])
            if validated.get("status") == "ok":
                answer_plan = plan_answer(
                    analysis,
                    evidence=evidence,
                    deterministic=True,
                )
                trace["answer_plan"] = answer_plan.to_dict()
                trace["planner_mode"] = answer_plan.mode
                validated["state"] = next_state.to_dict()
                validated["conversation_state"] = next_state.to_dict()
                validated["trace"] = trace
                trace["final_status"] = "ok"
                return _attach_answer_plan(validated, answer_plan)
        if "deterministic_validation" not in trace:
            trace["deterministic_validation"] = {
                "status": "no_data",
                "reason": "structured_score_answer_unavailable",
            }
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    requested_combination = analysis.entities.get("admission_combination")
    if requested_combination and not _combination_is_verified(evidence, requested_combination):
        trace["boundary"] = "admission_combination_not_verified"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    website_answer = _official_links_answer(
        analysis,
        evidence,
        verified_documents=evidence_documents,
        target_year=settings_obj.target_year,
    )
    if website_answer is not None:
        evidence_boundary = website_answer.pop("evidence_boundary", None)
        if evidence_boundary:
            trace["evidence_boundary"] = evidence_boundary
        else:
            trace["deterministic_branch"] = "verified_website_directory"
        website_answer["state"] = next_state.to_dict()
        website_answer["conversation_state"] = next_state.to_dict()
        website_status = str(website_answer.get("status") or "no_data")
        answer_plan = plan_answer(
            analysis,
            evidence=evidence,
            status=website_status,
            deterministic=website_status == "ok",
        )
        trace["answer_plan"] = answer_plan.to_dict()
        trace["final_status"] = website_status
        website_answer["trace"] = trace
        return _attach_answer_plan(website_answer, answer_plan)

    catalog_answer = _evidence_catalog_answer(analysis, evidence, state)
    if catalog_answer is not None:
        if catalog_answer.get("catalog") is not None:
            trace["catalog"] = catalog_answer["catalog"]
        answer_plan = plan_answer(
            analysis,
            evidence=evidence,
            deterministic=True,
        )
        trace["answer_plan"] = answer_plan.to_dict()
        catalog_answer["state"] = next_state.to_dict()
        catalog_answer["conversation_state"] = next_state.to_dict()
        catalog_answer["trace"] = trace
        return _attach_answer_plan(catalog_answer, answer_plan)

    if _school_info_detail_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "requested_school_info_detail_missing"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if _named_unit_relation_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "named_school_unit_relation_missing"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if analysis.intent == "SCHOOL_INFO":
        normalized_q = normalize_question(analysis.normalized_question)
        asks_faculty = any(m in normalized_q for m in ("khoa", "cac khoa", "bao nhieu khoa", "may khoa"))
        if _is_generic_school_overview_request(analysis) and not asks_faculty:
            overview_answer = _evidence_overview_answer(
                analysis,
                evidence,
                target_year=settings_obj.target_year,
            )
            _, overview_urls = _overview_intro_evidence(
                evidence,
                target_year=settings_obj.target_year,
            )
            overview_sources = _overview_sources(evidence, overview_urls)
            validated_overview = (
                validate_model_answer(
                    overview_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                    target_year=settings_obj.target_year,
                )
                if overview_answer and overview_sources
                else None
            )
            trace["validator"] = {
                "status": validated_overview.get("status") if validated_overview else "no_data",
                "reason": (
                    validated_overview.get("_validation_reason")
                    if validated_overview
                    else "overview_intro_evidence_unavailable"
                ),
            }
            if validated_overview and validated_overview.get("status") == "ok":
                answer_plan = plan_answer(
                    analysis,
                    evidence=evidence,
                    deterministic=True,
                )
                trace["deterministic_branch"] = "verified_school_overview"
                trace["answer_plan"] = answer_plan.to_dict()
                validated_overview["sources"] = overview_sources
                validated_overview["state"] = next_state.to_dict()
                validated_overview["conversation_state"] = next_state.to_dict()
                validated_overview["trace"] = trace
                return _attach_answer_plan(validated_overview, answer_plan)

            trace["evidence_boundary"] = "school_overview_missing_matching_evidence"
            answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
            trace["answer_plan"] = answer_plan.to_dict()
            return _attach_answer_plan({
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
                "state": next_state.to_dict(),
                "conversation_state": next_state.to_dict(),
                "trace": trace,
            }, answer_plan)

        school_info_answer = _evidence_school_info_answer(analysis, evidence) or _evidence_semester_system_answer(analysis, evidence)
        if school_info_answer:
            validated_school_info = validate_model_answer(
                school_info_answer,
                evidence,
                question=query,
                analysis=analysis,
                target_year=settings_obj.target_year,
            )
            trace["validator"] = {
                "status": validated_school_info.get("status"),
                "reason": validated_school_info.get("_validation_reason"),
            }
            if validated_school_info.get("status") == "ok":
                answer_plan = plan_answer(analysis, evidence=evidence, deterministic=True)
                trace["answer_plan"] = answer_plan.to_dict()
                validated_school_info["state"] = next_state.to_dict()
                validated_school_info["conversation_state"] = next_state.to_dict()
                validated_school_info["trace"] = trace
                return _attach_answer_plan(validated_school_info, answer_plan)

        overview_answer = _evidence_overview_answer(
            analysis,
            evidence,
            target_year=settings_obj.target_year,
        ) or _evidence_directory_answer(analysis, evidence)
        if overview_answer:
            answer_plan = plan_answer(
                analysis,
                evidence=evidence,
                deterministic=True,
            )
            trace["answer_plan"] = answer_plan.to_dict()
            return _attach_answer_plan({
                "answer": overview_answer,
                "sources": [dict(source) for source in evidence.sources],
                "status": "ok",
                "state": next_state.to_dict(),
                "conversation_state": next_state.to_dict(),
                "trace": trace,
            }, answer_plan)

    direct_evidence_answer = None
    applicant_support_question = (
        analysis.intent == "HOI_DANG_KY_XET_TUYEN"
        and "khuyet tat" in normalized_query
        and any(marker in normalized_query for marker in (
            "chinh sach", "ho tro", "quyen loi", "tao dieu kien",
        ))
    )
    result_notification_question = _is_result_notification_question(
        analysis.normalized_question
    )
    if analysis.intent == "HOI_LICH_TUYEN_SINH" and admission_date_comparison:
        direct_evidence_answer = _evidence_date_comparison_answer(analysis, evidence)
    elif result_notification_question:
        direct_evidence_answer = _evidence_result_notification_answer(analysis, evidence)
    elif supplementary_route_question:
        direct_evidence_answer = _evidence_application_registration_answer(analysis, evidence)
    elif applicant_support_question:
        direct_evidence_answer = _evidence_applicant_support_answer(analysis, evidence)
    elif analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"} or (
        analysis.intent == "HOI_LICH_TUYEN_SINH"
        and "tiep nhan tan sinh vien" in analysis.normalized_question
    ):
        direct_evidence_answer = _evidence_enrollment_answer(analysis, evidence)
    elif analysis.intent == "HOI_HOC_PHI" or any(k in normalized_query for k in ("hoc ky", "hoc ki", "1 nam", "mot nam", "thoi gian dao tao", "dao tao may nam")):
        direct_evidence_answer = (
            _evidence_semester_system_answer(analysis, evidence)
            or _evidence_optional_english_fee_answer(analysis, evidence)
            or _evidence_tuition_per_credit_answer(analysis, evidence)
            or _evidence_tuition_total_answer(analysis, evidence)
            or _evidence_tuition_answer(evidence)
        )
    elif analysis.intent == "HOI_HOC_BONG":
        direct_evidence_answer = (
            _evidence_scholarship_catalog_answer(analysis, evidence)
            or _evidence_scholarship_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_XET_TUYEN_BO_SUNG":
        direct_evidence_answer = (
            _evidence_application_registration_answer(analysis, evidence)
            or _evidence_supplementary_majors_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_CACH_TINH_DIEM":
        direct_evidence_answer = (
            (
                _evidence_method_calculation_answer(analysis, evidence)
                if analysis.entities.get("admission_method") == "thpt"
                else None
            )
            or _evidence_admission_bonus_answer(analysis, evidence)
            or _evidence_exam_subject_count_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_CO_SO_LIEN_HE":
        direct_evidence_answer = _evidence_school_code_answer(analysis, evidence)
    elif analysis.intent == "HOI_DANG_KY_XET_TUYEN":
        direct_evidence_answer = (
            _evidence_vocational_same_group_eligibility_answer(analysis, evidence)
            or _evidence_general_registration_answer(analysis, evidence)
            or admission_rule_answer
        )
    elif analysis.intent == "HOI_NGUONG_DAU_VAO":
        direct_evidence_answer = (
            _evidence_law_grade_eligibility_answer(analysis, evidence)
            or _evidence_method_application_threshold_answer(analysis, evidence)
            or _evidence_eligibility_answer(analysis, evidence)
            or _evidence_vocational_same_group_eligibility_answer(analysis, evidence)
            or _evidence_subject_minimum_answer(analysis, evidence)
            or _evidence_major_eligibility_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_PHUONG_THUC_XET_TUYEN":
        direct_evidence_answer = (
            _evidence_vocational_same_group_eligibility_answer(analysis, evidence)
            or _evidence_method_calculation_answer(analysis, evidence)
            or _evidence_admission_combination_answer(analysis, evidence)
            or _evidence_admission_method_presence_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_CHUONG_TRINH":
        direct_evidence_answer = _evidence_program_relation_answer(analysis, evidence)

    if direct_evidence_answer:
        validated_direct_answer = validate_model_answer(
            direct_evidence_answer,
            evidence,
            question=query,
            analysis=analysis,
            target_year=settings_obj.target_year,
        )
        trace["evidence_direct_answer"] = {
            "attempted": True,
            "status": validated_direct_answer.get("status"),
            "reason": validated_direct_answer.get("_validation_reason"),
        }
        if validated_direct_answer.get("status") == "ok":
            answer_plan = plan_answer(analysis, evidence=evidence, deterministic=True)
            trace["answer_plan"] = answer_plan.to_dict()
            validated_direct_answer["state"] = next_state.to_dict()
            validated_direct_answer["conversation_state"] = next_state.to_dict()
            validated_direct_answer["trace"] = trace
            trace["final_status"] = "ok"
            return _attach_answer_plan(validated_direct_answer, answer_plan)

    method_formula_request = (
        analysis.intent == "HOI_CACH_TINH_DIEM"
        and analysis.entities.get("admission_method") == "thpt"
        and _is_formula_request(analysis.normalized_question)
    )
    method_formula_answer = (
        _evidence_method_calculation_answer(analysis, evidence)
        if method_formula_request
        else None
    )
    protected_evidence_request = (
        applicant_support_question
        or result_notification_question
        or supplementary_route_question
        or (method_formula_request and method_formula_answer is None)
        or (
            bool(analysis.entities.get("admission_condition_request"))
            and admission_rule_answer is None
        )
        or (
            _is_subject_minimum_request(analysis.normalized_question)
            and _evidence_subject_minimum_answer(analysis, evidence) is None
        )
        or (analysis.intent == "HOI_LICH_TUYEN_SINH" and admission_date_comparison)
    )
    if protected_evidence_request:
        trace["evidence_boundary"] = (
            "requested_method_formula_missing_matching_evidence"
            if method_formula_request and method_formula_answer is None
            else "requested_admission_detail_not_fully_supported"
        )
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if (
        analysis.intent == "HOI_PHUONG_THUC_XET_TUYEN"
        and (
            any(marker in analysis.normalized_question for marker in ("to hop mon", "to hop xet tuyen"))
            or analysis.entities.get("admission_combination_detail")
        )
        and _evidence_admission_combination_answer(analysis, evidence) is None
    ):
        trace["evidence_boundary"] = "requested_admission_combination_detail_missing"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if _application_documents_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "application_document_checklist_missing"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if _program_detail_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "requested_program_detail_missing"
        answer_plan = plan_answer(analysis, evidence=evidence, status="no_data")
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    if score_comparisons and analysis.intent != "TU_VAN_CHON_NGANH":
        comparison_lines: list[str] = []
        for comparison in score_comparisons:
            label = _method_label(comparison.get("method"))
            relation_word = "cao hơn hoặc bằng" if comparison.get("meets_threshold") else "thấp hơn"
            comparison_lines.append(
                f"Điểm {label} bạn nêu là {comparison.get('student_value')}, "
                f"{relation_word} ngưỡng nhận hồ sơ {comparison.get('threshold_value')}."
            )
        comparison_lines.append(
            "Đây chỉ là phép so sánh với ngưỡng nhận hồ sơ, không phải kết luận trúng tuyển."
        )
        answer_plan = plan_answer(analysis, evidence=evidence, deterministic=True)
        trace["answer_plan"] = answer_plan.to_dict()
        return _attach_answer_plan({
            "answer": "\n".join(comparison_lines),
            "sources": [dict(source) for source in evidence.sources],
            "status": "ok",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": trace,
        }, answer_plan)

    answer_plan = plan_answer(analysis, evidence=evidence)
    prompt = build_rag_prompt(
        query,
        evidence.context,
        intent=analysis.intent,
        entities=analysis.entities,
        conversation_state=next_state.to_dict(),
        answer_plan=answer_plan,
        score_facts=select_relevant_score_facts(analysis, evidence.score_facts),
        score_comparisons=score_comparisons,
        entity_relations=evidence.entity_relations,
    )
    try:
        enrollment_answer = None
        if analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"}:
            enrollment_answer = _evidence_enrollment_answer(analysis, evidence)
        if enrollment_answer:
            result = validate_model_answer(
                enrollment_answer,
                evidence,
                question=query,
                analysis=analysis,
                target_year=settings_obj.target_year,
            )
        else:
            active_llm = llm or LocalLLM(settings_obj=settings_obj)
            result = _validated_generation(
                active_llm=active_llm,
                prompt=prompt,
                evidence=evidence,
                question=query,
                analysis=analysis,
                score_facts=select_relevant_score_facts(analysis, evidence.score_facts),
                answer_plan=answer_plan,
                score_comparisons=score_comparisons,
                target_year=settings_obj.target_year,
            )
        validation_reason = result.pop("_validation_reason", None)
        if result.get("status") == "ok":
            structured_answer = None
            if analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"}:
                structured_answer = _evidence_enrollment_answer(analysis, evidence)
            elif answer_plan.mode == "OVERVIEW":
                structured_answer = _evidence_overview_answer(
                    analysis,
                    evidence,
                    target_year=settings_obj.target_year,
                )
            elif answer_plan.mode == "COMPARISON":
                structured_answer = _structured_comparison_answer(analysis, evidence)
            elif (
                analysis.intent == "HOI_HOC_BONG"
                and not analysis.entities.get("student_scores")
            ):
                structured_answer = _evidence_scholarship_answer(analysis, evidence)
            if structured_answer:
                structured_result = validate_model_answer(
                    structured_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                    target_year=settings_obj.target_year,
                )
                if structured_result.get("status") == "ok":
                    result = structured_result
                    validation_reason = None
        if (
            result.get("status") == "no_data"
            and analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"}
        ):
            enrollment_answer = _evidence_enrollment_answer(analysis, evidence)
            if enrollment_answer:
                fallback_result = validate_model_answer(
                    enrollment_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                    target_year=settings_obj.target_year,
                )
                if fallback_result.get("status") == "ok":
                    result = fallback_result
                    validation_reason = None
        if (
            result.get("status") == "no_data"
            and analysis.intent == "TU_VAN_CHON_NGANH"
            and evidence.is_usable
            and validation_reason in _ADVISORY_SAFE_FALLBACK_REASONS
        ):
            result = _advisory_evidence_clarification(
                analysis,
                evidence,
                next_state,
                score_comparisons,
            )
        elif (
            result.get("status") == "no_data"
            and analysis.intent == "HOI_HOC_PHI"
            and isinstance(active_llm, LocalLLM)
        ):
            tuition_answer = _evidence_tuition_answer(evidence)
            if tuition_answer:
                fallback_result = validate_model_answer(
                    tuition_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                    target_year=settings_obj.target_year,
                )
                if fallback_result.get("status") == "ok":
                    result = fallback_result
                    validation_reason = None
        elif (
            result.get("status") == "no_data"
            and analysis.intent == "HOI_HOC_BONG"
            and not analysis.entities.get("student_scores")
            and isinstance(active_llm, LocalLLM)
        ):
            scholarship_answer = _evidence_scholarship_answer(analysis, evidence)
            if scholarship_answer:
                fallback_result = validate_model_answer(
                    scholarship_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                    target_year=settings_obj.target_year,
                )
                if fallback_result.get("status") == "ok":
                    result = fallback_result
                    validation_reason = None
        elif (
            result.get("status") == "ok"
            and not _advisory_answer_has_guidance(analysis, result.get("answer"))
        ):
            result = _advisory_evidence_clarification(
                analysis,
                evidence,
                next_state,
                score_comparisons,
            )
    except OllamaUnavailableError:
        return _planned_boundary_result(
            answer=OLLAMA_OFFLINE_ANSWER,
            status="ollama_offline",
            analysis=analysis,
            plan=plan,
            state=next_state,
            retrieval_audit=retrieval_audit,
            trace=trace,
        )
    except OllamaError:
        return _planned_boundary_result(
            answer=FALLBACK_ANSWER,
            status="no_data",
            analysis=analysis,
            plan=plan,
            state=next_state,
            retrieval_audit=retrieval_audit,
            trace=trace,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _planned_boundary_result(
            answer=ERROR_ANSWER,
            status="error",
            analysis=analysis,
            plan=plan,
            state=next_state,
            retrieval_audit=retrieval_audit,
            trace=trace,
        )

    final_status = str(result.get("status") or "no_data")
    trace["validator"] = {
        "status": final_status,
        "reason": validation_reason,
    }
    final_answer_plan = plan_answer(
        analysis,
        evidence=evidence,
        status=final_status,
    )
    trace["answer_plan"] = final_answer_plan.to_dict()
    trace["planner_mode"] = final_answer_plan.mode
    result["state"] = next_state.to_dict()
    result["conversation_state"] = next_state.to_dict()
    result["trace"] = trace
    return _attach_answer_plan(result, final_answer_plan)


__all__ = [
    "ask_chatbot",
    "_get_default_retriever",
    "_analysis_with_state",
    "_trace",
    "_attach_answer_plan",
    "_planned_boundary_result",
    "_clarification_result",
    "_school_scope_boundary_result",
    "_retrieve",
    "_try_pre_rag_decomposition",
    "_ask_multi_issue",
    "_filter_documents_for_plan",
    "_dedupe_sources",
    "_MULTI_ISSUE_LABELS",
    "_evidence_text_lines",
    "_split_source_sentences",
    "_evidence_sentences",
    "_remove_unresolved_url_label",
    "_bullet_content_lines",
    "_metadata_page",
    "_metadata_chunk_index",
    "_is_official_dhv_source",
    "_OFFICIAL_WEBSITE_DIRECTORY",
    "_requested_website_entry",
    "_official_links_answer",
    "_evidence_tuition_answer",
    "_evidence_tuition_total_answer",
    "_evidence_tuition_per_credit_answer",
    "_evidence_optional_english_fee_answer",
    "_evidence_semester_system_answer",
    "_is_generic_school_overview_request",
    "_has_school_overview_request_marker",
    "_is_school_overview_intro_heading",
    "_is_verified_school_overview_intro_document",
    "_prioritize_school_overview_documents",
    "_overview_intro_evidence",
    "_overview_sources",
    "_evidence_overview_answer",
    "_evidence_school_info_answer",
    "_evidence_directory_answer",
    "_evidence_school_code_answer",
    "_named_unit_relation_missing_evidence",
    "_school_info_detail_missing_evidence",
    "_candidate_values",
    "_advisory_answer_has_guidance",
    "_advisory_preferred_program",
    "_has_verified_advisory_fit_evidence",
    "_advisory_evidence_clarification",
    "_deterministic_recommendation_answer",
    "_program_detail_missing_evidence",
    "_major_rows_from_evidence",
    "_MAJOR_GROUP_LABELS",
    "_major_in_group",
    "_program_rows_from_evidence",
    "_method_details_from_evidence",
    "_evidence_catalog_answer",
    "_evidence_program_relation_answer",
    "_source_ordered_documents",
    "_is_scholarship_heading",
    "_prioritize_scholarship_catalog_documents",
    "_is_admission_scholarship_conditions_question",
    "_prioritize_admission_scholarship_conditions_documents",
    "_evidence_scholarship_catalog_answer",
    "_evidence_scholarship_answer",
    "_evidence_admission_scholarship_conditions_answer",
    "_is_result_notification_question",
    "_prioritize_result_notification_documents",
    "_prioritize_enrollment_document_records",
    "_prioritize_admission_date_comparison_documents",
    "_evidence_date_comparison_answer",
    "_evidence_exam_subject_count_answer",
    "_verified_admission_conditions_section",
    "_requested_admission_method_number",
    "_asks_for_each_admission_method",
    "_evidence_eligibility_answer",
    "_evidence_law_grade_eligibility_answer",
    "_evidence_method_application_threshold_answer",
    "_evidence_subject_minimum_answer",
    "_application_documents_missing_evidence",
    "_evidence_required_document_answer",
    "_evidence_enrollment_answer",
    "_evidence_admission_bonus_answer",
    "_evidence_formula_answer",
    "_evidence_admission_combination_answer",
    "_evidence_admission_method_presence_answer",
    "_evidence_method_calculation_answer",
    "_evidence_vocational_same_group_eligibility_answer",
    "_evidence_major_eligibility_answer",
    "_method_label",
    "_evidence_schedule_answer",
    "_evidence_supplementary_majors_answer",
    "_evidence_score_list_answer",
    "_structured_score_answer",
    "_evidence_score_comparison_reason_answer",
    "_structured_comparison_answer",
    "_evidence_applicant_support_answer",
    "_evidence_application_registration_answer",
    "_evidence_general_registration_answer",
    "_evidence_result_notification_answer",
    "_RETRYABLE_VALIDATION_REASONS",
    "_retry_prompt",
    "_is_generation_artifact",
    "_combination_is_verified",
    "_realize_generation_artifact",
    "_validated_generation",
]
