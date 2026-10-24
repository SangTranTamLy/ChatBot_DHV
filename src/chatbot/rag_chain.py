"""Điều phối RAG kèm theo phân tích, trạng thái hội thoại giới hạn và kiểm toán (audit)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from src.config.settings import Settings, settings
from src.models.local_llm import LocalLLM, OllamaError, OllamaUnavailableError, OllamaTimeoutError
from src.prompts.rag_prompt import build_rag_prompt
from src.retrieval.retriever import RetrieverEmbeddingError, VectorDatabaseError, requested_year
from .year_semantics import current_admission_window_answer

from .admission_answers import (
    _application_documents_missing_evidence,
    _evidence_admission_bonus_answer,
    _evidence_admission_combination_answer,
    _evidence_admission_method_presence_answer,
    _evidence_applicant_support_answer,
    _evidence_application_registration_answer,
    _evidence_date_comparison_answer,
    _evidence_eligibility_answer,
    _evidence_enrollment_answer,
    _evidence_exam_subject_count_answer,
    _evidence_general_registration_answer,
    _evidence_law_grade_eligibility_answer,
    _evidence_major_eligibility_answer,
    _evidence_method_application_threshold_answer,
    _evidence_method_calculation_answer,
    _evidence_result_notification_answer,
    _evidence_score_comparison_reason_answer,
    _evidence_score_list_answer,
    _evidence_subject_minimum_answer,
    _evidence_supplementary_detail_answer,
    _evidence_supplementary_majors_answer,
    _evidence_vocational_same_group_eligibility_answer,
    _is_result_notification_question,
    _method_label,
    _prioritize_admission_date_comparison_documents,
    _prioritize_enrollment_document_records,
    _prioritize_result_notification_documents,
    _structured_comparison_answer,
    _structured_score_answer,
)
from .answer_planner import plan_answer
from .catalog_formatters import (
    _advisory_answer_has_guidance,
    _advisory_evidence_clarification,
    _candidate_values,
    _evidence_catalog_answer,
    _evidence_program_relation_answer,
    _has_verified_advisory_fit_evidence,
    _major_rows_from_evidence,
    _method_details_from_evidence,
    _program_detail_missing_evidence,
    _program_rows_from_evidence,
    _source_ordered_documents,
)
from .evidence import build_evidence, select_evidence_documents
from .evidence_utils import _remove_unresolved_url_label
from .generation_guards import _combination_is_verified, _validated_generation
from .multi_issue import _ask_multi_issue
from .official_links import _official_links_answer
from .output_validator import (
    ERROR_ANSWER,
    FALLBACK_ANSWER,
    OLLAMA_OFFLINE_ANSWER,
    OLLAMA_TIMEOUT_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    VECTOR_DB_ERROR_ANSWER,
    validate_model_answer,
)
from .pipeline_utils import (
    _ADVISORY_SAFE_FALLBACK_REASONS,
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
    _is_admission_date_comparison,
    _is_admissions_context_followup,
    _is_formula_request,
    _is_subject_minimum_request,
    analyze_question,
    deterministic_score_comparisons,
    deterministic_score_evaluation,
    enrich_analysis_from_evidence,
    normalize_question,
    route_question,
    select_relevant_score_facts,
    should_inherit_context,
    update_conversation_state,
)
from .query_decomposer import _try_pre_rag_decomposition
from .query_semantics import correct_domain_typos
from .scholarship_formatters import (
    _evidence_scholarship_answer,
    _evidence_scholarship_catalog_answer,
    _evidence_scholarship_tier_answer,
    _evidence_scholarship_conditions_answer,
    _evidence_scholarship_overview_answer,
    _is_scholarship_conditions_question,
    _is_scholarship_overview_question,
    _prioritize_scholarship_catalog_documents,
)
from .school_info_formatters import (
    _evidence_campus_list_answer,
    _evidence_campus_and_phone_answer,
    _evidence_contact_overview_answer,
    _evidence_contact_email_answer,
    _evidence_contact_phone_answer,
    _evidence_social_channels_answer,
    _evidence_directory_answer,
    _evidence_overview_answer,
    _evidence_school_code_answer,
    _evidence_school_info_answer,
    _is_generic_school_overview_request,
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
)
from .tuition_formatters import (
    _evidence_fee_item_answer,
    _evidence_optional_english_fee_answer,
    _evidence_semester_system_answer,
    _evidence_tuition_answer,
    _evidence_tuition_per_credit_answer,
    _evidence_tuition_total_answer,
)


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

    query = correct_domain_typos(question.strip()) if isinstance(question, str) else ""
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
        if inherit_year or analysis.entities.get("contextual_question")
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
            str(analysis.entities.get("contextual_question") or query),
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
        except OllamaTimeoutError:
            return _planned_boundary_result(
                answer=OLLAMA_TIMEOUT_ANSWER,
                status="model_timeout",
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
    if analysis.intent == "HOI_HOC_BONG":
        evidence_documents = _prioritize_scholarship_catalog_documents(evidence_documents)
        scholarship_conditions_evidence_prioritized = _is_scholarship_conditions_question(analysis)
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
    date_comparison_evidence_reordered = admission_date_comparison
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
    listed_methods = None
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
    elif (
        analysis.intent == "HOI_PHUONG_THUC_XET_TUYEN"
        and analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}
    ):
        method_codes = {
            1: "thpt",
            2: "hoc_ba",
            3: "dgnl",
            4: "h_sca",
            5: "trung_cap",
        }
        method_facts = sorted(
            (
                fact
                for fact in evidence.score_facts
                if fact.get("score_type") == "admission_method" and fact.get("method_number")
            ),
            key=lambda fact: int(fact.get("method_number") or 99),
        )
        listed_methods = list(
            dict.fromkeys(
                str(fact.get("method") or method_codes.get(int(fact["method_number"])))
                for fact in method_facts
                if fact.get("method") or int(fact["method_number"]) in method_codes
            )
        )
    next_state = update_conversation_state(
        state,
        analysis,
        target_year=settings_obj.target_year,
        last_listed_majors=listed_majors,
        last_list_count=len(listed_majors) if listed_majors is not None else None,
        last_listed_programs=listed_programs,
        last_listed_program_parents=listed_program_parents,
        last_listed_methods=listed_methods,
    )
    trace = _trace(
        analysis,
        plan,
        next_state,
        retrieval_audit,
        evidence_selection,
    )
    def finish(result: dict[str, object], answer_plan: Any) -> dict[str, object]:
        result.update(state=next_state.to_dict(), conversation_state=next_state.to_dict(), trace=trace)
        return _attach_answer_plan(result, answer_plan)

    def no_data() -> dict[str, object]:
        return finish(
            {"answer": FALLBACK_ANSWER, "sources": [], "status": "no_data"},
            plan_answer(analysis, evidence=evidence, status="no_data"),
        )

    temporal_result = current_admission_window_answer(analysis.question, evidence)
    if temporal_result is not None:
        trace["temporal_checked"] = True
        return finish(temporal_result, plan_answer(
            analysis, evidence=evidence, status=str(temporal_result["status"]), deterministic=True,
        ))

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
    lookup_facts = select_relevant_score_facts(analysis, evidence.score_facts)
    trace["selected_score_facts"] = [dict(fact) for fact in lookup_facts]
    trace["matching_facts"] = list(trace["selected_score_facts"])
    score_query_type = analysis.entities.get("score_query_type")
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
    supplementary_detail_question = str(analysis.entities.get("request_type") or "").startswith("supplementary_")
    supplementary_route_question = (
        not supplementary_detail_question
        and analysis.intent in {"HOI_XET_TUYEN_BO_SUNG", "HOI_DANG_KY_XET_TUYEN"}
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
        # Câu hỏi quy tắc phương thức (vd. học bạ lấy điểm lớp nào) không cần dữ liệu điểm số.
        and analysis.intent != "HOI_PHUONG_THUC_XET_TUYEN"
        and not structured_lookup_answer
        and not deadline_only_lookup
        and not admission_rule_answer
        and not supplementary_route_question
    ):
        return no_data()
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
        return no_data()
    if not evidence.is_usable:
        return no_data()

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
        return finish(result, answer_plan)

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
                trace["final_status"] = "ok"
                return finish(validated, answer_plan)
        if "deterministic_validation" not in trace:
            trace["deterministic_validation"] = {
                "status": "no_data",
                "reason": "structured_score_answer_unavailable",
            }
        return no_data()

    requested_combination = analysis.entities.get("admission_combination")
    if requested_combination and not _combination_is_verified(evidence, requested_combination):
        trace["boundary"] = "admission_combination_not_verified"
        return no_data()

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
        return finish(website_answer, answer_plan)

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
        return finish(catalog_answer, answer_plan)

    if _school_info_detail_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "requested_school_info_detail_missing"
        return no_data()

    if _named_unit_relation_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "named_school_unit_relation_missing"
        return no_data()

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
                return finish(validated_overview, answer_plan)

            trace["evidence_boundary"] = "school_overview_missing_matching_evidence"
            return no_data()

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
                return finish(validated_school_info, answer_plan)

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
            return finish({
                "answer": overview_answer,
                "sources": [dict(source) for source in evidence.sources],
                "status": "ok",
            }, answer_plan)

    direct_evidence_answer = None
    enrollment_answer = None
    enrollment_answer_checked = False
    validated_enrollment_answer = None
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
    elif supplementary_detail_question:
        direct_evidence_answer = _evidence_supplementary_detail_answer(analysis, evidence)
    elif supplementary_route_question:
        direct_evidence_answer = _evidence_application_registration_answer(analysis, evidence)
    elif applicant_support_question:
        direct_evidence_answer = _evidence_applicant_support_answer(analysis, evidence)
    elif analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"} or (
        analysis.intent == "HOI_LICH_TUYEN_SINH"
        and ("tiep nhan tan sinh vien" in analysis.normalized_question
             or analysis.entities.get("request_type") in {"reception_hours", "reception_dates"})
    ):
        direct_evidence_answer = _evidence_enrollment_answer(analysis, evidence)
        enrollment_answer = direct_evidence_answer
        enrollment_answer_checked = True
    elif analysis.intent == "HOI_HOC_PHI" or any(k in normalized_query for k in ("hoc ky", "hoc ki", "1 nam", "mot nam", "thoi gian dao tao", "dao tao may nam")):
        direct_evidence_answer = (
            _evidence_semester_system_answer(analysis, evidence)
            or _evidence_optional_english_fee_answer(analysis, evidence)
            or _evidence_fee_item_answer(analysis, evidence)
            or _evidence_tuition_per_credit_answer(analysis, evidence)
            or _evidence_tuition_total_answer(analysis, evidence)
            or _evidence_tuition_answer(evidence)
        )
    elif analysis.intent == "HOI_HOC_BONG":
        tier_answer = _evidence_scholarship_tier_answer(analysis, evidence)
        if tier_answer:
            direct_evidence_answer = tier_answer
        elif _is_scholarship_conditions_question(analysis):
            direct_evidence_answer = _evidence_scholarship_conditions_answer(analysis, evidence)
        elif analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}:
            direct_evidence_answer = _evidence_scholarship_catalog_answer(analysis, evidence)
        elif _is_scholarship_overview_question(analysis):
            direct_evidence_answer = _evidence_scholarship_overview_answer(analysis, evidence)
        else:
            direct_evidence_answer = _evidence_scholarship_answer(analysis, evidence)
    elif analysis.intent == "HOI_XET_TUYEN_BO_SUNG":
        direct_evidence_answer = (
            _evidence_application_registration_answer(analysis, evidence)
            or _evidence_supplementary_majors_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_CACH_TINH_DIEM":
        direct_evidence_answer = (
            (
                _evidence_method_calculation_answer(analysis, evidence)
                if analysis.entities.get("admission_method") in {"thpt", "hoc_ba"}
                else None
            )
            or _evidence_admission_bonus_answer(analysis, evidence)
            or _evidence_exam_subject_count_answer(analysis, evidence)
        )
    elif analysis.intent == "HOI_CO_SO_LIEN_HE":
        direct_evidence_answer = (
            _evidence_social_channels_answer(analysis, evidence)
            or _evidence_campus_and_phone_answer(analysis, evidence)
            or _evidence_contact_phone_answer(analysis, evidence)
            or _evidence_contact_overview_answer(analysis, evidence)
            or
            _evidence_school_code_answer(analysis, evidence)
            or _evidence_campus_list_answer(analysis, evidence)
            or _evidence_contact_email_answer(analysis, evidence)
        )
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
        if enrollment_answer and analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"}:
            validated_enrollment_answer = validated_direct_answer
        if validated_direct_answer.get("status") == "ok":
            answer_plan = plan_answer(analysis, evidence=evidence, deterministic=True)
            trace["answer_plan"] = answer_plan.to_dict()
            trace["final_status"] = "ok"
            return finish(validated_direct_answer, answer_plan)

    strict_scholarship_request = analysis.intent == "HOI_HOC_BONG" and (
        _is_scholarship_conditions_question(analysis)
        or _is_scholarship_overview_question(analysis)
        or analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}
    )
    if strict_scholarship_request:
        # Never let generation replace a missing or incomplete scholarship
        # policy answer with a list of headings or stitched page fragments.
        trace["evidence_boundary"] = "complete_scholarship_policy_evidence_missing"
        return no_data()

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
        or supplementary_detail_question
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
        return no_data()

    if (
        analysis.intent == "HOI_PHUONG_THUC_XET_TUYEN"
        and (
            any(marker in analysis.normalized_question for marker in ("to hop mon", "to hop xet tuyen"))
            or analysis.entities.get("admission_combination_detail")
        )
        and _evidence_admission_combination_answer(analysis, evidence) is None
    ):
        trace["evidence_boundary"] = "requested_admission_combination_detail_missing"
        return no_data()

    if _application_documents_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "application_document_checklist_missing"
        return no_data()

    if _program_detail_missing_evidence(analysis, evidence):
        trace["evidence_boundary"] = "requested_program_detail_missing"
        return no_data()

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
        return finish({
            "answer": "\n".join(comparison_lines),
            "sources": [dict(source) for source in evidence.sources],
            "status": "ok",
        }, answer_plan)

    answer_plan = plan_answer(analysis, evidence=evidence)
    prompt = build_rag_prompt(
        query,
        evidence.context,
        intent=analysis.intent,
        entities=analysis.entities,
        conversation_state=next_state.to_dict(),
        answer_plan=answer_plan,
        score_facts=lookup_facts,
        score_comparisons=score_comparisons,
        entity_relations=evidence.entity_relations,
    )
    try:
        if analysis.intent in {"HOI_NHAP_HOC", "HOI_HO_SO"} and not enrollment_answer_checked:
            enrollment_answer = _evidence_enrollment_answer(analysis, evidence)
            if enrollment_answer:
                validated_enrollment_answer = validate_model_answer(
                    enrollment_answer, evidence, question=query, analysis=analysis,
                    target_year=settings_obj.target_year,
                )
        active_llm = None
        if validated_enrollment_answer is not None:
            result = dict(validated_enrollment_answer)
        else:
            active_llm = llm or LocalLLM(settings_obj=settings_obj)
            result = _validated_generation(
                active_llm=active_llm,
                prompt=prompt,
                evidence=evidence,
                question=query,
                analysis=analysis,
                score_facts=lookup_facts,
                answer_plan=answer_plan,
                score_comparisons=score_comparisons,
                target_year=settings_obj.target_year,
            )
        validation_reason = result.pop("_validation_reason", None)
        if result.get("status") == "ok" and analysis.intent not in {"HOI_NHAP_HOC", "HOI_HO_SO"}:
            structured_answer = None
            if answer_plan.mode == "OVERVIEW":
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
    except OllamaTimeoutError:
        return _planned_boundary_result(
            answer=OLLAMA_TIMEOUT_ANSWER,
            status="model_timeout",
            analysis=analysis,
            plan=plan,
            state=next_state,
            retrieval_audit=retrieval_audit,
            trace=trace,
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
    except Exception:
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
    return finish(result, final_answer_plan)


__all__ = ["ask_chatbot"]
