"""Multi-issue query resolution: decomposing compound questions, independent retrieval, and section assembly."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from src.config.settings import Settings
from src.models.local_llm import LocalLLM, OllamaError, OllamaUnavailableError, OllamaTimeoutError
from src.retrieval.retriever import RetrieverEmbeddingError, VectorDatabaseError
from src.prompts.rag_prompt import build_rag_prompt

from .admission_answers import _evidence_enrollment_answer, _evidence_general_registration_answer
from .answer_planner import plan_answer
from .catalog_formatters import _candidate_values, _evidence_catalog_answer
from .evidence import (
    build_evidence,
    merge_evidence_bundles,
    select_evidence_documents,
)
from .generation_guards import _validated_generation
from .official_links import _official_links_answer
from .output_validator import FALLBACK_ANSWER, OLLAMA_OFFLINE_ANSWER, OLLAMA_TIMEOUT_ANSWER, VECTOR_DB_ERROR_ANSWER, validate_model_answer
from .query_semantics import analyze_fee_request, enrollment_request
from .year_semantics import current_admission_window_answer
from .pipeline_utils import _attach_answer_plan, _retrieve, _trace
from .query_analysis import (
    ConversationState,
    QueryAnalysis,
    deterministic_score_comparisons,
    deterministic_score_evaluation,
    enrich_analysis_from_evidence,
    normalize_question,
    select_relevant_score_facts,
    update_conversation_state,
)
from .scholarship_formatters import (
    _evidence_scholarship_answer,
    _evidence_scholarship_catalog_answer,
    _evidence_scholarship_conditions_answer,
    _evidence_scholarship_overview_answer,
    _is_scholarship_conditions_question,
    _is_scholarship_overview_question,
    _prioritize_scholarship_catalog_documents,
)
from .school_info_formatters import (
    _evidence_campus_list_answer,
    _evidence_contact_email_answer,
    _evidence_contact_phone_answer,
    _evidence_overview_answer,
    _evidence_school_info_answer,
    _has_school_overview_request_marker,
    _is_generic_school_overview_request,
    _is_verified_school_overview_intro_document,
    _overview_intro_evidence,
    _overview_sources,
    _prioritize_school_overview_documents,
)
from .tuition_formatters import _evidence_semester_system_answer, answer_fee_request


def _issue_failure(exc: Exception) -> dict[str, object]:
    if isinstance(exc, OllamaTimeoutError):
        answer, status = OLLAMA_TIMEOUT_ANSWER, "model_timeout"
    elif isinstance(exc, (OllamaUnavailableError, RetrieverEmbeddingError)):
        answer, status = OLLAMA_OFFLINE_ANSWER, "ollama_offline"
    elif isinstance(exc, VectorDatabaseError):
        answer, status = VECTOR_DB_ERROR_ANSWER, "vector_db_error"
    else:
        answer, status = FALLBACK_ANSWER, "no_data"
    return {"answer": answer, "status": status, "sources": [], "error_type": type(exc).__name__}


def _dedupe_sources(results: list[dict[str, object]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        for source in result.get("sources", ()) or ():
            if not isinstance(source, Mapping):
                continue
            url = str(source.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                {
                    "title": str(source.get("title") or "DHV"),
                    "url": url,
                }
            )
    return sources


_MULTI_ISSUE_LABELS = {
    "SCHOOL_INFO": "Thông tin trường",
    "HOI_HOC_PHI": "Học phí",
    "HOI_HOC_BONG": "Học bổng",
    "DANH_SACH_CHUONG_TRINH": "Chương trình đào tạo",
    "DANH_SACH_NGANH": "Ngành đào tạo",
    "HOI_NGUONG_DAU_VAO": "Ngưỡng đầu vào",
    "HOI_DIEM_TRUNG_TUYEN": "Điểm trúng tuyển",
    "HOI_XET_TUYEN_BO_SUNG": "Xét tuyển bổ sung",
    "HOI_PHUONG_THUC_XET_TUYEN": "Phương thức xét tuyển",
    "HOI_CACH_TINH_DIEM": "Cách tính điểm",
    "HOI_HO_SO": "Hồ sơ",
    "HOI_LICH_TUYEN_SINH": "Lịch tuyển sinh",
    "HOI_NHAP_HOC": "Nhập học",
    "HOI_DANG_KY_XET_TUYEN": "Đăng ký xét tuyển",
    "HOI_CO_SO_LIEN_HE": "Cơ sở và liên hệ",
    "OUT_OF_SCOPE": "Sự kiện và hoạt động trường",
}


def _ask_multi_issue(
    *,
    query: str,
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
    retriever: Any,
    llm: Any | None,
    settings_obj: Settings,
) -> dict[str, object]:
    """Retrieve và trả lời từng issue độc lập rồi ghép lại theo thứ tự câu hỏi."""

    sub_results: list[dict[str, object]] = []
    audits: list[dict[str, object] | None] = []
    selections: list[dict[str, object]] = []
    evidence_bundles = []
    score_evaluations: list[dict[str, object]] = []
    sub_answer_plans: list[dict[str, object]] = []
    school_overview_evidence_prioritized: list[bool] = []
    sub_evidence_boundaries: list[str | None] = []
    retrieved_document_counts: list[int] = []
    selected_evidence_counts: list[int] = []
    retrieval_call_count = 0
    active_llm: Any | None = None
    effective_subplans: list[Any] = []
    for subplan in plan.subplans:
        subquery = subplan.issue_question or subplan.retrieval_query
        normalized_subquery = normalize_question(subquery)
        retrieval_subplan = subplan
        if (
            subplan.intent == "HOI_HOC_BONG"
            and subplan.entity_filters
        ):
            scholarship_filters = {
                key: value
                for key, value in subplan.entity_filters.items()
                if key not in {
                    "major_name",
                    "major_code",
                    "program_name",
                    "parent_major",
                    "candidate_majors",
                    "candidate_programs",
                }
            }
            retrieval_subplan = replace(subplan, entity_filters=scholarship_filters)
        effective_subplans.append(retrieval_subplan)
        sub_analysis = replace(
            analysis,
            question=subquery,
            normalized_question=normalized_subquery,
            intent=subplan.intent,
            entities={
                **(subplan.issue_entities or analysis.entities),
                "issue_intents": [],
                "requested_information": [subplan.intent],
                "request_type": enrollment_request(subquery),
            },
        )
        if subplan.intent == "OUT_OF_SCOPE":
            evidence = build_evidence([], settings_obj=settings_obj)
            sub_answer_plan = plan_answer(
                sub_analysis,
                evidence=evidence,
                status="out_of_scope",
                deterministic=True,
            )
            sub_results.append(
                {
                    "answer": (
                        "Mình chưa có nguồn đã xác minh về sự kiện hoặc hoạt động "
                        "của trường trong dữ liệu tuyển sinh DHV, nên chưa thể trả lời phần này."
                    ),
                    "sources": [],
                    "status": "out_of_scope",
                    "evidence_boundary": "unsupported_event_topic_outside_approved_scope",
                    "answer_plan": sub_answer_plan.to_dict(),
                    "intent": subplan.intent,
                }
            )
            audits.append(None)
            selections.append(
                {
                    "candidate_count": 0,
                    "selected_count": 0,
                    "selected": [],
                    "filtered": [],
                    "filter_reasons": [],
                    "skipped_reason": "unsupported_event_topic_outside_approved_scope",
                }
            )
            evidence_bundles.append(evidence)
            score_evaluations.append(
                {"status": "not_requested", "reason": "unsupported_event_topic"}
            )
            sub_answer_plans.append(sub_answer_plan.to_dict())
            school_overview_evidence_prioritized.append(False)
            sub_evidence_boundaries.append(
                "unsupported_event_topic_outside_approved_scope"
            )
            retrieved_document_counts.append(0)
            selected_evidence_counts.append(0)
            continue

        issue_failure = None
        try:
            documents, audit = _retrieve(retriever, subquery, retrieval_subplan)
        except (RetrieverEmbeddingError, VectorDatabaseError) as exc:
            documents, audit = [], None
            issue_failure = _issue_failure(exc)
        retrieval_call_count += 1
        retrieved_document_counts.append(len(documents))
        audits.append(audit.to_dict() if audit is not None else None)
        overview_analysis = replace(
            sub_analysis,
            question=subquery,
            normalized_question=normalized_subquery,
        )
        overview_issue = (
            subplan.intent == "SCHOOL_INFO"
            and not any(
                marker in normalized_subquery
                for marker in ("khoa", "cac khoa", "bao nhieu khoa", "may khoa")
            )
            and (
                _is_generic_school_overview_request(overview_analysis)
                or _has_school_overview_request_marker(analysis.normalized_question)
            )
        )
        selection = select_evidence_documents(
            documents,
            categories=subplan.categories,
            entities=sub_analysis.entities,
            candidates=_candidate_values(sub_analysis),
            target_year=settings_obj.target_year,
            intent=subplan.intent,
        )
        selections.append(selection.to_dict())
        selected_documents = list(selection.documents)
        if subplan.intent == "HOI_HOC_BONG":
            selected_documents = _prioritize_scholarship_catalog_documents(
                selected_documents
            )
        overview_prioritized = False
        if overview_issue:
            selected_documents = _prioritize_school_overview_documents(
                selected_documents,
                target_year=settings_obj.target_year,
            )
            overview_prioritized = bool(
                selected_documents
                and _is_verified_school_overview_intro_document(
                    selected_documents[0],
                    target_year=settings_obj.target_year,
                )
            )
        school_overview_evidence_prioritized.append(overview_prioritized)
        evidence = build_evidence(selected_documents, settings_obj=settings_obj)
        selected_evidence_counts.append(len(evidence.chunks))
        evidence_bundles.append(evidence)
        sub_analysis = enrich_analysis_from_evidence(sub_analysis, evidence)
        score_comparisons = deterministic_score_comparisons(sub_analysis, evidence)
        score_evaluation = deterministic_score_evaluation(sub_analysis, evidence)
        score_evaluations.append(score_evaluation)
        validated_overview = None
        overview_sources: list[dict[str, str]] = []
        if overview_issue:
            overview_answer = _evidence_overview_answer(
                overview_analysis,
                evidence,
                target_year=settings_obj.target_year,
            )
            _, overview_urls = _overview_intro_evidence(
                evidence,
                target_year=settings_obj.target_year,
            )
            overview_sources = _overview_sources(evidence, overview_urls)
            if overview_answer and overview_sources:
                validated_overview = validate_model_answer(
                    overview_answer,
                    evidence,
                    question=subquery,
                    analysis=overview_analysis,
                    target_year=settings_obj.target_year,
                )
        website_result = None
        if (
            subplan.intent == "HOI_CO_SO_LIEN_HE"
            and sub_analysis.entities.get("website_request")
        ):
            website_result = _official_links_answer(
                sub_analysis,
                evidence,
                verified_documents=selected_documents,
                target_year=settings_obj.target_year,
            )
        direct_result = current_admission_window_answer(sub_analysis.normalized_question, evidence)
        info_answer = None
        fee_coverage: dict[str, object] | None = None
        fee_result: dict[str, object] | None = None
        if subplan.intent == "SCHOOL_INFO" and not overview_issue:
            info_answer = _evidence_school_info_answer(sub_analysis, evidence) or _evidence_semester_system_answer(sub_analysis, evidence)
        elif subplan.intent == "HOI_CO_SO_LIEN_HE":
            info_answer = (
                _evidence_campus_list_answer(sub_analysis, evidence)
                or _evidence_contact_email_answer(sub_analysis, evidence)
                or _evidence_contact_phone_answer(sub_analysis, evidence)
            )
        elif subplan.intent in {"HOI_HO_SO", "HOI_NHAP_HOC"}:
            info_answer = _evidence_enrollment_answer(sub_analysis, evidence)
        elif sub_analysis.entities.get("request_type") in {"reception_hours", "reception_dates"}:
            info_answer = _evidence_enrollment_answer(sub_analysis, evidence)
        elif subplan.intent == "HOI_HOC_PHI":
            info_answer = _evidence_semester_system_answer(sub_analysis, evidence)
            fee_request = analyze_fee_request(sub_analysis.normalized_question)
            if info_answer is None and fee_request.is_fee_request:
                fee_result = answer_fee_request(sub_analysis, evidence, fee_request)
                if fee_result is not None:
                    answer = fee_result.get("answer")
                    info_answer = str(answer) if answer else None
                    fee_coverage = {
                        key: fee_result[key]
                        for key in ("requested_topics", "answered_topics", "ambiguous_topics", "missing_topics")
                    }
        if info_answer and direct_result is None:
            validated_info = validate_model_answer(
                info_answer,
                evidence,
                question=subquery,
                analysis=sub_analysis,
                target_year=settings_obj.target_year,
            )
            if validated_info.get("status") == "ok":
                direct_result = validated_info
                direct_result["sources"] = [dict(s) for s in evidence.sources]
        scholarship_result = None
        strict_scholarship_question = subplan.intent == "HOI_HOC_BONG" and (
            _is_scholarship_conditions_question(sub_analysis)
            or _is_scholarship_overview_question(sub_analysis)
            or sub_analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}
        )
        if subplan.intent == "HOI_HOC_BONG":
            if _is_scholarship_conditions_question(sub_analysis):
                scholarship_answer = _evidence_scholarship_conditions_answer(sub_analysis, evidence)
            elif sub_analysis.entities.get("query_mode") in {"COUNT", "LIST", "LIST_AND_COUNT"}:
                scholarship_answer = _evidence_scholarship_catalog_answer(sub_analysis, evidence)
            elif _is_scholarship_overview_question(sub_analysis):
                scholarship_answer = _evidence_scholarship_overview_answer(sub_analysis, evidence)
            else:
                scholarship_answer = _evidence_scholarship_answer(sub_analysis, evidence)
            if scholarship_answer:
                scholarship_result = validate_model_answer(
                    scholarship_answer,
                    evidence,
                    question=subquery,
                    analysis=sub_analysis,
                    target_year=settings_obj.target_year,
                )
        registration_answer = None
        if website_result is not None:
            sub_status = str(website_result.get("status") or "no_data")
        elif direct_result is not None:
            sub_status = str(direct_result.get("status") or "no_data")
        elif issue_failure is not None:
            sub_status = str(issue_failure.get("status") or "no_data")
        else:
            registration_answer = (
                _evidence_general_registration_answer(sub_analysis, evidence)
                if subplan.intent == "HOI_DANG_KY_XET_TUYEN"
                else None
            )
            sub_status = (
                "ok"
                if (
                validated_overview
                and validated_overview.get("status") == "ok"
                )
                or registration_answer is not None
                or (
                    scholarship_result is not None
                    and scholarship_result.get("status") == "ok"
                )
                or (
                    not overview_issue
                    and not strict_scholarship_question
                    and not (issue_failure is None and fee_result is not None and not fee_result.get("answer"))
                    and evidence.is_usable
                    and score_evaluation.get("status") != "insufficient-data"
                )
                else "no_data"
            )
        sub_answer_plan = plan_answer(
            sub_analysis,
            evidence=evidence,
            status=sub_status,
            deterministic=(
                direct_result is not None
                or overview_issue
                or website_result is not None
                or registration_answer is not None
                or scholarship_result is not None
                or subplan.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
            ),
        )
        sub_answer_plans.append(sub_answer_plan.to_dict())

        if website_result is not None:
            sub_result = dict(website_result)
        elif direct_result is not None:
            sub_result = dict(direct_result)
        elif issue_failure is not None:
            sub_result = dict(issue_failure)
        elif fee_result is not None and not fee_result.get("answer"):
            sub_result = {
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
                "evidence_boundary": "requested_fee_facts_missing_verified_table_rows",
            }
        elif overview_issue:
            if validated_overview and validated_overview.get("status") == "ok":
                sub_result = dict(validated_overview)
                sub_result["sources"] = overview_sources
            else:
                sub_result = {
                    "answer": FALLBACK_ANSWER,
                    "sources": [],
                    "status": "no_data",
                    "evidence_boundary": "school_overview_missing_matching_evidence",
                }
        elif registration_answer:
            sub_result = {
                "answer": registration_answer,
                "sources": [dict(source) for source in evidence.sources],
                "status": "ok",
            }
        elif scholarship_result is not None:
            sub_result = dict(scholarship_result)
            sub_result.pop("_validation_reason", None)
        elif strict_scholarship_question:
            sub_result = {
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
                "evidence_boundary": "complete_scholarship_policy_evidence_missing",
            }
        elif not evidence.is_usable or score_evaluation.get("status") == "insufficient-data":
            sub_result: dict[str, object] = issue_failure or {
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
            }
        else:
            catalog_result = _evidence_catalog_answer(sub_analysis, evidence, state)
            if catalog_result is not None:
                sub_result = catalog_result
            else:
                try:
                    if active_llm is None:
                        active_llm = (
                            llm if llm is not None else LocalLLM(settings_obj=settings_obj)
                        )
                    relevant_score_facts = select_relevant_score_facts(
                        sub_analysis,
                        evidence.score_facts,
                    )
                    prompt = build_rag_prompt(
                        subquery,
                        evidence.context,
                        intent=sub_analysis.intent,
                        entities=sub_analysis.entities,
                        conversation_state=state.to_dict(),
                        answer_plan=sub_answer_plan,
                        score_facts=relevant_score_facts,
                        score_comparisons=score_comparisons,
                        entity_relations=evidence.entity_relations,
                    )
                    sub_result = _validated_generation(
                        active_llm=active_llm,
                        prompt=prompt,
                        evidence=evidence,
                        question=subquery,
                        analysis=sub_analysis,
                        score_facts=relevant_score_facts,
                        answer_plan=sub_answer_plan,
                        score_comparisons=score_comparisons,
                        target_year=settings_obj.target_year,
                    )
                    sub_result.pop("_validation_reason", None)
                except OllamaError as exc:
                    sub_result = _issue_failure(exc)
        sub_result["answer_plan"] = sub_answer_plan.to_dict()
        sub_result["intent"] = subplan.intent
        sub_result["request_type"] = sub_analysis.entities.get("request_type")
        if fee_coverage is not None:
            sub_result["fee_coverage"] = fee_coverage
            sub_result["partial"] = bool(fee_coverage.get("missing_topics"))
        sub_evidence_boundaries.append(
            str(sub_result.get("evidence_boundary"))
            if sub_result.get("evidence_boundary")
            else None
        )
        sub_results.append(sub_result)

    next_state = update_conversation_state(state, analysis, target_year=settings_obj.target_year)
    answer_sections: list[str] = []
    for result in sub_results:
        answer = str(result.get("answer") or "").strip()
        if result.get("status") == "no_data" and not result.get("temporal_checked"):
            topic = {
                "HOI_HOC_PHI": "mức học phí",
                "HOI_HOC_BONG": "học bổng",
                "HOI_HO_SO": "giấy tờ cần chuẩn bị",
                "HOI_NHAP_HOC": "cách nhập học",
                "HOI_CO_SO_LIEN_HE": "địa điểm hoặc thông tin liên hệ",
                "HOI_LICH_TUYEN_SINH": "thời hạn bạn hỏi",
            }.get(str(result.get("intent")), "phần bạn hỏi")
            topic = {
                "reception_hours": "giờ tiếp nhận hồ sơ",
                "reception_dates": "thời gian tiếp nhận hồ sơ",
                "enrollment_location": "địa điểm nhận hồ sơ",
            }.get(result.get("request_type"), topic)
            answer = f"Mình chưa có thông tin chính xác về {topic} để trả lời bạn."
        if not answer:
            continue
        label = _MULTI_ISSUE_LABELS.get(str(result.get("intent") or ""), "Thông tin liên quan")
        label = {"reception_hours": "Giờ tiếp nhận", "reception_dates": "Thời gian tiếp nhận",
                 "enrollment_location": "Nơi nộp hồ sơ"}.get(result.get("request_type"), label)
        answer_sections.append(f"### {label}\n{answer}")
    subplan_statuses = [str(result.get("status") or "error") for result in sub_results]
    statuses = set(subplan_statuses)
    status = "ok" if answer_sections and ("ok" in statuses or "clarification" in statuses) else "no_data"
    partial_response = (
        bool(answer_sections)
        and any(subplan_status != "ok" for subplan_status in subplan_statuses)
    ) or any(bool(result.get("partial")) for result in sub_results)
    complete_response = bool(subplan_statuses) and all(
        subplan_status == "ok" for subplan_status in subplan_statuses
    ) and not partial_response
    merged_evidence = merge_evidence_bundles(
        evidence_bundles,
        settings_obj=settings_obj,
    )
    merged_answer_plan = plan_answer(
        analysis,
        evidence=merged_evidence,
        status=status,
    )
    trace = _trace(analysis, plan, next_state, answer_plan=merged_answer_plan)
    trace["retrieval_calls"] = retrieval_call_count
    trace["retrieved_docs_count"] = sum(retrieved_document_counts)
    trace["retrieved_chunks"] = sum(retrieved_document_counts)
    trace["evidence_count"] = sum(selected_evidence_counts)
    trace["partial_response"] = partial_response
    trace["multi_issue"] = {
        "issues": [
            {
                "issue_id": f"issue_{index}",
                "question": subplan.issue_entities.get("issue_original_question") or subplan.issue_question or subplan.retrieval_query,
                "intent": subplan.intent,
                "status": result.get("status"),
                "can_answer": result.get("status") == "ok",
                "chunk_ids": [str(chunk.metadata.get("chunk_id") or "") for chunk in bundle.chunks],
                "sources": result.get("sources", []),
                "fee_coverage": result.get("fee_coverage"),
                "partial": bool(result.get("partial")),
            }
            for index, (subplan, result, bundle) in enumerate(
                zip(effective_subplans, sub_results, evidence_bundles), start=1
            )
        ],
        "complete": complete_response,
        "partial": partial_response,
        "temporal_checked": any(result.get("temporal_checked") for result in sub_results),
        "subplan_statuses": subplan_statuses,
        "subplans": [subplan.to_dict() for subplan in effective_subplans],
        "subqueries": [subplan.retrieval_query for subplan in plan.subplans],
        "retrieval_audits": audits,
        "evidence_selections": selections,
        "answer_plans": sub_answer_plans,
        "merged_evidence": {
            "chunk_count": len(merged_evidence.chunks),
            "source_count": len(merged_evidence.sources),
            "chunk_ids": [
                str(chunk.metadata.get("chunk_id") or "")
                for chunk in merged_evidence.chunks
            ],
        },
        "statuses": [result.get("status") for result in sub_results],
        "retrieved_docs_counts": retrieved_document_counts,
        "evidence_counts": selected_evidence_counts,
        "school_overview_evidence_prioritized": school_overview_evidence_prioritized,
        "evidence_boundaries": sub_evidence_boundaries,
    }
    trace["score_comparisons"] = []
    trace["score_engine"] = score_evaluations
    return _attach_answer_plan({
        "answer": "\n\n".join(answer_sections) or FALLBACK_ANSWER,
        "sources": _dedupe_sources(sub_results),
        "status": status,
        "partial": partial_response,
        "temporal_checked": trace["multi_issue"]["temporal_checked"],
        "state": next_state.to_dict(),
        "conversation_state": next_state.to_dict(),
        "trace": trace,
    }, merged_answer_plan)
