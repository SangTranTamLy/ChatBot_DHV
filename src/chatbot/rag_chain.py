"""Điều phối RAG kèm theo phân tích, trạng thái hội thoại giới hạn và kiểm toán (audit)."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Mapping
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

from .evidence import (
    build_evidence,
    EvidenceSelection,
    merge_evidence_bundles,
    select_evidence_documents,
    select_program_relations,
)
from .answer_planner import AnswerPlan, plan_answer
from .output_validator import (
    CLARIFICATION_ANSWER,
    ERROR_ANSWER,
    FALLBACK_ANSWER,
    OLLAMA_OFFLINE_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    VECTOR_DB_ERROR_ANSWER,
    validate_model_answer,
)
from .query_analysis import (
    ConversationState,
    QueryAnalysis,
    analyze_question,
    deterministic_score_comparisons,
    deterministic_score_evaluation,
    enrich_analysis_from_evidence,
    route_question,
    select_relevant_score_facts,
    normalize_question,
    _is_global_catalog_request,
    CONTEXT_INHERIT_EXCLUDED,
    update_conversation_state,
)
from .scope_guard import is_in_scope


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
    }
)


def _analysis_with_state(analysis: QueryAnalysis, state: ConversationState) -> QueryAnalysis:
    entities = dict(analysis.entities)
    if (
        not entities.get("major_name")
        and state.current_major
        and not entities.get("program_name")
        and analysis.intent not in CONTEXT_INHERIT_EXCLUDED
        and not (
            analysis.intent == "DANH_SACH_CHUONG_TRINH"
            and _is_global_catalog_request(analysis.normalized_question)
        )
    ):
        entities["major_name"] = state.current_major
        entities["entity_type"] = "major"
    if not entities.get("candidate_majors") and state.candidate_majors:
        entities["candidate_majors"] = list(state.candidate_majors)
    if not entities.get("candidate_programs") and state.candidate_programs:
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
        # Candidates are alternatives, not a resolved major/program. Parent
        # relationships are resolved only from verified evidence relations.
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
    }
    if evidence_selection is not None:
        trace["evidence_selection"] = evidence_selection.to_dict()
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
        trace["answer_plan"] = payload
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


_ADVISORY_SAFE_FALLBACK_REASONS = frozenset(
    {
        "model_fallback",
        "ungrounded",
        "program_relation_missing",
        "program_relation_wrong",
        "advisory_choices_incomplete",
        "year_mismatch",
    }
)


_DETERMINISTIC_SYSTEM_ANSWERS = {
    "GREETING": (
        "Chào bạn! Mình là trợ lý AI phục vụ đồ án học tập/nghiên cứu, hỗ trợ tra cứu "
        "tuyển sinh DHV. Bạn có thể hỏi về ngành, chương trình, phương thức "
        "xét tuyển, học phí, học bổng, hồ sơ hoặc lịch tuyển sinh năm 2026."
    ),
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


def _clarification_result(
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
) -> dict[str, object]:
    next_state = update_conversation_state(state, analysis)
    answer_plan = plan_answer(analysis, status="clarification")
    return _attach_answer_plan({
        "answer": CLARIFICATION_ANSWER,
        "sources": [],
        "status": "clarification",
        "state": next_state.to_dict(),
        "conversation_state": next_state.to_dict(),
        "trace": _trace(analysis, plan, next_state, answer_plan=answer_plan),
    }, answer_plan)


def _retrieve(
    retriever: Any,
    question: str,
    plan: Any,
) -> tuple[list[Any], Any]:
    method = getattr(retriever, "retrieve_with_audit", None)
    if callable(method):
        entity_filters = dict(getattr(plan, "entity_filters", {}) or {})
        expanded_directory_top_k = None
        if (
            getattr(plan, "intent", "") in {"SCHOOL_INFO", "HOI_CO_SO_LIEN_HE"}
            and "thong_tin_truong" in tuple(getattr(plan, "categories", ()) or ())
        ):
            # The directory is intentionally one school document represented
            # by several verified JSON records. Retrieve the complete small
            # directory so an overview record cannot be hidden behind the
            # first few alphabetically ordered website records.
            expanded_directory_top_k = 64
        try:
            kwargs = {
                "categories": plan.categories,
                "retrieval_query": plan.retrieval_query,
                "entity_filters": entity_filters,
            }
            if expanded_directory_top_k is not None:
                kwargs["top_k"] = expanded_directory_top_k
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


def _filter_documents_for_plan(documents: list[Any], plan: Any) -> list[Any]:
    """Giữ evidence đúng category của từng subplan khi adapter trả về rộng hơn filter."""

    categories = set(getattr(plan, "categories", ()) or ())
    if not categories:
        return list(documents)
    return [
        document
        for document in documents
        if str((getattr(document, "metadata", {}) or {}).get("category") or "") in categories
    ]


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
    active_llm: Any | None = None
    for subplan in plan.subplans:
        subquery = subplan.retrieval_query
        documents, audit = _retrieve(retriever, subquery, subplan)
        audits.append(audit.to_dict() if audit is not None else None)
        sub_analysis = replace(
            analysis,
            intent=subplan.intent,
            entities={
                **analysis.entities,
                "issue_intents": [],
                "requested_information": [subplan.intent],
            },
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
        evidence = build_evidence(selection.documents, settings_obj=settings_obj)
        evidence_bundles.append(evidence)
        sub_analysis = enrich_analysis_from_evidence(sub_analysis, evidence)
        score_comparisons = deterministic_score_comparisons(sub_analysis, evidence)
        score_evaluation = deterministic_score_evaluation(sub_analysis, evidence)
        score_evaluations.append(score_evaluation)
        sub_status = (
            "ok"
            if evidence.is_usable and score_evaluation.get("status") != "insufficient-data"
            else "no_data"
        )
        sub_answer_plan = plan_answer(
            sub_analysis,
            evidence=evidence,
            status=sub_status,
            deterministic=subplan.intent
            in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"},
        )
        sub_answer_plans.append(sub_answer_plan.to_dict())

        if not evidence.is_usable or score_evaluation.get("status") == "insufficient-data":
            sub_result: dict[str, object] = {
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
            }
        else:
            catalog_result = _evidence_catalog_answer(sub_analysis, evidence, state)
            if catalog_result is not None:
                sub_result = catalog_result
            else:
                if active_llm is None:
                    active_llm = llm or LocalLLM(settings_obj=settings_obj)
                prompt = build_rag_prompt(
                    subquery,
                    evidence.context,
                    intent=sub_analysis.intent,
                    entities=sub_analysis.entities,
                    conversation_state=state.to_dict(),
                    answer_plan=sub_answer_plan,
                    score_facts=select_relevant_score_facts(
                        sub_analysis,
                        evidence.score_facts,
                    ),
                    score_comparisons=score_comparisons,
                    entity_relations=evidence.entity_relations,
                )
                sub_result = _validated_generation(
                    active_llm=active_llm,
                    prompt=prompt,
                    evidence=evidence,
                    question=subquery,
                    analysis=sub_analysis,
                    score_facts=select_relevant_score_facts(
                        sub_analysis,
                        evidence.score_facts,
                    ),
                    answer_plan=sub_answer_plan,
                    score_comparisons=score_comparisons,
                )
                sub_result.pop("_validation_reason", None)
        sub_result["answer_plan"] = sub_answer_plan.to_dict()
        sub_result["intent"] = subplan.intent
        sub_results.append(sub_result)

    next_state = update_conversation_state(state, analysis, target_year=settings_obj.target_year)
    answer_sections: list[str] = []
    for result in sub_results:
        answer = str(result.get("answer") or "").strip()
        if not answer:
            continue
        label = _MULTI_ISSUE_LABELS.get(str(result.get("intent") or ""), "Thông tin liên quan")
        answer_sections.append(f"### {label}\n{answer}")
    statuses = {str(result.get("status") or "error") for result in sub_results}
    status = "ok" if answer_sections and ("ok" in statuses or "clarification" in statuses) else "no_data"
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
    trace["multi_issue"] = {
        "subplans": [subplan.to_dict() for subplan in plan.subplans],
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
    }
    trace["score_comparisons"] = []
    trace["score_engine"] = score_evaluations
    return _attach_answer_plan({
        "answer": "\n\n".join(answer_sections) or FALLBACK_ANSWER,
        "sources": _dedupe_sources(sub_results),
        "status": status,
        "state": next_state.to_dict(),
        "conversation_state": next_state.to_dict(),
        "trace": trace,
    }, merged_answer_plan)


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


def _evidence_text_lines(evidence: Any) -> list[str]:
    """Lấy các dòng nội dung đã qua Evidence Selection, không lấy metadata prompt."""

    lines: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        for raw_line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line and line not in lines:
                lines.append(line)
    return lines


def _bullet_content_lines(evidence: Any) -> list[str]:
    """Gộp bullet bị ngắt dòng trong chunk để formatter giữ được nguyên fact."""

    result: list[str] = []
    for line in _evidence_text_lines(evidence):
        if line.startswith("•"):
            result.append(line.lstrip("• ").strip())
        elif (
            result
            and not line.startswith("#")
            and not line.lower().startswith(("dhv ", "nguồn ", "quỹ ", "các chính sách"))
        ):
            result[-1] = f"{result[-1]} {line}"
    unique: list[str] = []
    seen: set[str] = set()
    for line in result:
        key = normalize_question(line)
        if key and key not in seen:
            seen.add(key)
            unique.append(line)
    return unique


def _evidence_overview_answer(evidence: Any) -> str | None:
    lines = _evidence_text_lines(evidence)

    def sentence_containing(fragment: str) -> str | None:
        for index, line in enumerate(lines):
            lower_line = line.lower()
            marker_index = lower_line.find(fragment)
            if marker_index < 0:
                continue
            parts = [line[marker_index:]]
            for continuation in lines[index + 1 :]:
                if continuation.startswith(("#", "•")):
                    break
                parts.append(continuation)
                if "." in continuation:
                    break
            sentence = re.sub(r"\s+", " ", " ".join(parts)).strip()
            return re.split(r"(?<=\.)\s+", sentence, maxsplit=1)[0]
        return None

    school_name = None
    for line in lines:
        marker_index = line.lower().find("tên trường:")
        if marker_index < 0:
            continue
        value = line[marker_index + len("tên trường:") :].strip()
        school_name = value.split(". Tên viết tắt", 1)[0].strip()
        break
    founded = sentence_containing("cổng tuyển sinh 2026 giới thiệu dhv được thành lập từ năm")
    direction = sentence_containing("các trang chính thức mô tả định hướng")
    if not school_name and not founded and not direction:
        return None
    intro = (
        f"DHV là {school_name.rstrip('. ')}."
        if school_name
        else "Mình tóm tắt thông tin khái quát về DHV:"
    )
    bullets = []
    if founded:
        bullets.append(founded)
    if direction:
        bullets.append(direction)
    if not bullets:
        return intro
    return intro + "\n\n" + "\n".join(f"- {line}" for line in bullets)


def _evidence_directory_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Trả lời tồn tại của một đơn vị từ directory, không suy diễn chương trình."""

    entry = _requested_website_entry(analysis.normalized_question)
    if entry is None or analysis.entities.get("website_request"):
        return None
    _, _, title = entry
    title_normalized = normalize_question(title)
    if not any(title_normalized in normalize_question(line) for line in _evidence_text_lines(evidence)):
        return None
    return (
        f"Có. Dữ liệu DHV 2026 ghi nhận {title} trong hệ sinh thái đơn vị chính thức của trường. "
        "Tài liệu này chỉ xác nhận đơn vị và thông tin chung; chưa kết luận về chương trình, "
        "điều kiện hoặc thủ tục cụ thể."
    )


def _evidence_tuition_answer(evidence: Any) -> str | None:
    """Lấy đúng dòng học phí để fallback khi model cục bộ trả lời lỗi.

    Fallback này chỉ giữ dòng có nhãn ``Học phí`` và loại dòng ``Tổng chi phí``;
    vì vậy không thể đổi tên hoặc gộp các khoản thu trong bằng chứng.
    """

    for line in _evidence_text_lines(evidence):
        folded = normalize_question(line)
        if "hoc phi" not in folded or "tong chi phi" in folded:
            continue
        if not re.search(r"\d[\d.,]*\s*(?:đồng|d|vnd|/)", line, re.IGNORECASE):
            continue
        return line.lstrip("• ").strip()
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


def _evidence_scholarship_answer(evidence: Any) -> str | None:
    bullets = _bullet_content_lines(evidence)
    if not bullets:
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
        line for line in bullets
        if any(marker in normalize_question(line) for marker in relevant_markers)
    ]
    if not selected:
        return None
    return "Mình tóm tắt các chính sách và điều kiện học bổng đang có trong dữ liệu DHV 2026:\n" + "\n".join(
        f"- {line}" for line in selected[:12]
    )


def _method_label(method: object) -> str:
    return {
        "thpt": "thi tốt nghiệp THPT",
        "hoc_ba": "học bạ",
        "dgnl": "ĐGNL",
        "deadline": "hạn xét tuyển bổ sung",
    }.get(str(method or ""), str(method or "phương thức"))


def _structured_score_answer(
    analysis: QueryAnalysis,
    facts: Any,
) -> str | None:
    rows = [
        fact for fact in (facts or ())
        if isinstance(fact, Mapping) and fact.get("raw_value") not in (None, "")
    ]
    if not rows:
        return None
    grouped: list[str] = []
    for fact in rows:
        label = _method_label(fact.get("method"))
        raw_value = str(fact.get("raw_value"))
        if raw_value == "-":
            value = "chưa công bố"
        else:
            value = f"{raw_value} điểm"
        major = str(fact.get("major_name") or "").strip()
        prefix = f"{major}: " if major and len(rows) == 1 else ""
        grouped.append(f"{prefix}{label}: {value}")
    score_type = str(analysis.entities.get("score_type") or "")
    if score_type == "admission_score":
        intro = "Điểm trúng tuyển được công bố: "
    elif score_type == "supplementary_threshold":
        intro = "Ngưỡng xét tuyển bổ sung được công bố: "
    else:
        intro = "Ngưỡng nhận hồ sơ được công bố: "
    return intro + "; ".join(grouped) + "."


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
        label = _method_label(comparison.get("method"))
        relation_word = "cao hơn hoặc bằng" if comparison.get("meets_threshold") else "thấp hơn"
        lines.append(
            f"Điểm {label} bạn nêu là {comparison.get('student_value')}, "
            f"{relation_word} ngưỡng nhận hồ sơ {comparison.get('threshold_value')}."
        )
    lines.append("Đây chỉ là so sánh với ngưỡng nhận hồ sơ, không phải kết luận trúng tuyển.")
    return "\n".join(lines)


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
) -> str:
    """Dọn output echo/context theo plan; không thay đổi dữ kiện evidence."""

    if answer_plan.mode == "OVERVIEW":
        overview = _evidence_overview_answer(evidence)
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
    if analysis.intent == "HOI_HOC_PHI":
        lines = [
            line for line in _evidence_text_lines(evidence)
            if normalize_question(line).startswith(("hoc phi hki", "hoc phi:", "• hoc phi hki"))
        ]
        if lines:
            return lines[0].lstrip("• ").strip()
    if analysis.intent == "HOI_HOC_BONG":
        scholarship = _evidence_scholarship_answer(evidence)
        if scholarship:
            return scholarship
    if analysis.intent == "HOI_CACH_TINH_DIEM":
        formula = _evidence_formula_answer(evidence)
        if formula:
            return formula
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
        )
        if _is_generation_artifact(raw_answer)
        else raw_answer
    )
    validated = validate_model_answer(
        generated_answer,
        evidence,
        question=question,
        analysis=analysis,
    )
    reason = validated.get("_validation_reason")
    retry_advisory_fallback = reason == "model_fallback" and analysis.intent == "TU_VAN_CHON_NGANH"
    if validated.get("status") == "no_data" and (
        reason in _RETRYABLE_VALIDATION_REASONS or retry_advisory_fallback
    ):
        retry_answer = active_llm.generate(
            _retry_prompt(prompt, raw_answer, score_facts, evidence, analysis)
        )
        retry_answer = (
            _realize_generation_artifact(
                retry_answer,
                analysis=analysis,
                answer_plan=answer_plan,
                evidence=evidence,
                score_facts=score_facts,
                score_comparisons=score_comparisons,
            )
            if _is_generation_artifact(retry_answer)
            else retry_answer
        )
        validated = validate_model_answer(
            retry_answer,
            evidence,
            question=question,
            analysis=analysis,
        )
    return validated


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
    lines.append("Mình tóm tắt các hướng bạn đang cân nhắc theo dữ liệu DHV đã được kiểm chứng:")
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
        if not preferred_program:
            lines.append(f"Mình ghi nhận bạn đang quan tâm đến {interest_display}.")
        lines.append(
            "Bạn muốn mình so sánh sâu hơn về nội dung học và hướng công việc của "
            "các lựa chọn này không?"
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


def _advisory_preferred_program(
    candidate_programs: list[str],
    interest: str,
    relations: list[dict[str, str]],
) -> str | None:
    """Chọn một mục tiêu tư vấn có điều kiện từ sở thích của người dùng và các tên trong bằng chứng."""

    if not interest:
        return None
    interest_text = normalize_question(interest)
    creative_signals = (
        "edit",
        "video",
        "noi dung",
        "truyen thong",
        "media",
        "thiet ke",
    )
    if not any(signal in interest_text for signal in creative_signals):
        return None
    programs = list(candidate_programs)
    if not programs:
        programs = list(
            dict.fromkeys(
                str(relation.get("program_name") or "").strip()
                for relation in relations
                if str(relation.get("program_name") or "").strip()
            )
        )
    if any(signal in interest_text for signal in ("video", "edit", "dung video")):
        for program in programs:
            if "truyen thong da phuong tien" in normalize_question(program):
                if any(
                    str(relation.get("program_name") or "").strip() == program
                    and str(relation.get("parent_major") or "").strip()
                    for relation in relations
                ):
                    return program
    for program in programs:
        program_text = str(program).strip()
        program_normalized = normalize_question(program_text)
        if not any(
            signal in program_normalized
            for signal in ("truyen thong", "da phuong tien", "digital marketing")
        ):
            continue
        if any(
            str(relation.get("program_name") or "").strip() == program_text
            and str(relation.get("parent_major") or "").strip()
            for relation in relations
        ):
            return program_text
    return None


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


def _evidence_catalog_answer(
    analysis: QueryAnalysis,
    evidence: Any,
    state: ConversationState,
) -> dict[str, object] | None:
    """Định dạng các câu trả lời danh mục từ bằng chứng có cấu trúc, không phải từ văn xuôi của model."""

    major_rows = _major_rows_from_evidence(evidence)
    if analysis.intent == "DANH_SACH_NGANH":
        if not major_rows:
            return None
        year_values = [
            str(chunk.metadata.get("year"))
            for chunk in getattr(evidence, "chunks", ())
            if chunk.metadata.get("year")
        ]
        year_text = f" năm {year_values[0]}" if year_values else ""
        count_only = (
            any(
                marker in analysis.normalized_question
                for marker in ("bao nhieu nganh", "may nganh", "so luong nganh")
            )
            and not any(
                marker in analysis.normalized_question
                for marker in ("danh sach", "liet ke", "liet ra")
            )
        )
        if count_only:
            return {
                "answer": f"DHV hiện có {len(major_rows)} ngành chính{year_text}.",
                "sources": [dict(source) for source in evidence.sources],
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
        if is_list_correction:
            correction = (
                "Mình đính chính nhé: danh mục đã được kiểm chứng hiện có "
                f"{len(major_rows)} ngành chính{year_text}. Danh sách trước có thể đã "
                "trộn chương trình đào tạo với ngành chính hoặc bỏ sót một số ngành.\n"
            )
        else:
            correction = (
                f"Danh mục đã được kiểm chứng hiện có {len(major_rows)} ngành chính{year_text}, "
                "mình liệt kê theo đúng bảng ngành và mã ngành:\n"
            )
        lines = [
            f"{index}. {major} — mã ngành {code}"
            for index, (major, code) in enumerate(major_rows, start=1)
        ]
        return {
            "answer": correction + "\n".join(lines),
            "sources": [dict(source) for source in evidence.sources],
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
            answer = f"{scope} có {count} chương trình đào tạo được xác nhận trong dữ liệu DHV."
        elif operation == "LIST_AND_COUNT":
            answer = (
                f"{scope} có {count} chương trình đào tạo được xác nhận trong dữ liệu DHV:\n"
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
    return None


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


_OFFICIAL_WEBSITE_DIRECTORY = (
    ("admissions_portal", ("tuyen sinh", "cong tuyen sinh"), "tuyensinh.dhv.edu.vn", "Cổng tuyển sinh DHV"),
    ("school_website", ("website chinh", "website cua truong", "website truong", "web truong"), "dhv.edu.vn", "Website chính Trường Đại học Hùng Vương TP.HCM"),
    ("ipic", ("vien dao tao sau dai hoc", "sau dai hoc"), "ipic.dhv.edu.vn", "Viện Đào tạo Sau đại học"),
    ("epdl", ("vien lien ket giao duc", "dao tao tu xa"), "epdl.dhv.edu.vn", "Viện Liên kết Giáo dục và Đào tạo từ xa"),
    ("online", ("cong thong tin dao tao",), "online.dhv.edu.vn", "Cổng thông tin đào tạo dành cho sinh viên/giảng viên"),
    ("heal", ("khoa khoa hoc suc khoe", "khoa suc khoe"), "heal.dhv.edu.vn", "Khoa Khoa học Sức khỏe"),
    ("tec", ("khoa ky thuat cong nghe", "ky thuat cong nghe"), "tec.dhv.edu.vn", "Khoa Kỹ thuật Công nghệ"),
    ("fba", ("khoa tai chinh ngan hang ke toan", "tai chinh ngan hang ke toan"), "fba.dhv.edu.vn", "Khoa Tài chính - Ngân hàng - Kế toán"),
    ("bam", ("khoa quan tri kinh doanh marketing", "quan tri kinh doanh marketing"), "bam.dhv.edu.vn", "Khoa Quản trị Kinh doanh - Marketing"),
    ("lan", ("khoa ngon ngu",), "lan.dhv.edu.vn", "Khoa Ngôn ngữ"),
    ("host", ("khoa du lich nha hang khach san", "du lich nha hang khach san"), "host.dhv.edu.vn", "Khoa Du lịch - Nhà hàng - Khách sạn"),
    ("law", ("khoa luat",), "law.dhv.edu.vn", "Khoa Luật"),
    ("iatai", ("vien cong nghe tien tien", "tri tue nhan tao dhv"), "iatai.dhv.edu.vn", "Viện Công nghệ tiên tiến và Trí tuệ nhân tạo DHV"),
    ("core", ("vien van hoa doanh nghiep",), "core.dhv.edu.vn", "Viện Văn hóa Doanh nghiệp"),
    ("tek", ("trung tam cong nghe",), "tek.dhv.edu.vn", "Trung tâm Công nghệ"),
    ("library", ("trung tam hoc lieu", "thu vien dhv"), "thuvien.dhv.edu.vn", "Trung tâm Học liệu"),
    ("journal", ("tap chi khoa hoc",), "tapchikhoahoc.dhv.edu.vn", "Tạp chí Khoa học DHV"),
)


def _requested_website_entry(normalized_question: str) -> tuple[str, str, str] | None:
    normalized = normalize_question(normalized_question)
    for target, aliases, host, title in _OFFICIAL_WEBSITE_DIRECTORY:
        if any(alias in normalized for alias in aliases):
            return target, host, title
    return None


def _official_links_answer(analysis: QueryAnalysis, evidence: Any) -> dict[str, object] | None:
    """Trả provenance chính thức từ backend; UI quyết định không hiển thị URL."""

    if not analysis.entities.get("website_request"):
        return None

    all_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def add_source(url: object, title: str) -> None:
        value = str(url or "").strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme.lower() != "https"
            or not host
            or not (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
            or value in seen_urls
        ):
            return
        seen_urls.add(value)
        all_sources.append({"title": title, "url": value})

    def metadata_urls(metadata: Mapping[str, object]) -> list[str]:
        values: list[object] = [metadata.get("source_url")]
        raw_values = metadata.get("source_urls")
        if isinstance(raw_values, str):
            try:
                decoded = json.loads(raw_values)
            except (TypeError, ValueError):
                decoded = ()
            raw_values = decoded
        if isinstance(raw_values, (list, tuple, set)):
            values.extend(raw_values)
        return [str(value).strip() for value in values if str(value or "").strip()]

    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        for url in metadata_urls(metadata):
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            title = str(metadata.get("title") or "Nguồn chính thức DHV")
            if host in {"dhv.edu.vn", "www.dhv.edu.vn"} and urlparse(url).path in {"", "/"}:
                title = "Website trường"
            elif host == "tuyensinh.dhv.edu.vn":
                title = "Cổng tuyển sinh 2026"
            add_source(url, title)

    # Keep compatibility with test/adaptor documents that expose only the
    # already-normalized evidence source contract.
    for source in getattr(evidence, "sources", ()) or ():
        add_source(
            source.get("url"),
            str(source.get("title") or "Nguồn chính thức DHV"),
        )

    requested_entry = _requested_website_entry(analysis.normalized_question)
    website_kind = str(analysis.entities.get("website_kind") or "")
    if requested_entry is not None:
        _, requested_host, requested_title = requested_entry
        requested_sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".") == requested_host
        ]
        root_sources = [
            source for source in requested_sources if urlparse(source["url"]).path in {"", "/"}
        ]
        sources = root_sources or requested_sources
        for source in sources:
            source["title"] = requested_title
    elif website_kind == "school_website":
        school_sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            in {"dhv.edu.vn", "www.dhv.edu.vn"}
        ]
        root_sources = [
            source
            for source in school_sources
            if urlparse(source["url"]).path in {"", "/"}
        ]
        sources = root_sources or school_sources
    elif website_kind == "admissions_portal":
        sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            == "tuyensinh.dhv.edu.vn"
        ]
    else:
        sources = list(all_sources)
    if not sources:
        sources = list(all_sources)

    if not sources:
        return None

    lines = [
        "Chào bạn! Bạn có thể xem thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM tại các nguồn chính thức sau:",
    ]
    for source in sources:
        title = source["title"]
        url = source["url"]
        lines.append(f"- **{title}:** [{url}]({url})")
    lines.append(
        "\nNếu bạn cần, mình có thể tiếp tục tra cứu ngành học, phương thức xét tuyển, học phí hoặc hồ sơ từ các tài liệu DHV đã kiểm chứng."
    )
    return {
        "answer": "\n".join(lines),
        "sources": sources,
        "status": "ok",
    }


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


def ask_chatbot(
    question: str,
    *,
    retriever: Any | None = None,
    llm: Any | None = None,
    settings_obj: Settings = settings,
    conversation_state: ConversationState | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Trả lời một lượt hỏi thông qua luồng: phân tích → router → truy xuất → sinh văn bản."""

    query = question.strip() if isinstance(question, str) else ""
    state = ConversationState.from_value(conversation_state, default_year=settings_obj.target_year)
    analysis = analyze_question(query, state, default_year=settings_obj.target_year)
    analysis = _analysis_with_state(analysis, state)
    plan = route_question(analysis, state, target_year=settings_obj.target_year)

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
    )
    followup = bool(state.current_major or state.current_program) and any(
        marker in analysis.normalized_question
        for marker in ("thi sao", "con", "vay", "bao nhieu", "diem")
    )
    catalog_followup = (
        analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
        and (
            bool(state.last_listed_majors)
            or state.previous_intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
        )
    )
    # The classified OUT_OF_SCOPE intent is authoritative.  Do not let a
    # broad token such as ``ngành`` or ``tuyển sinh`` reopen retrieval for an
    # unrelated question, even if the legacy scope keyword guard says it is
    # plausibly in scope.
    if analysis.intent == "OUT_OF_SCOPE" or (
        not is_in_scope(query, has_admissions_entity=has_context_entity)
        and not has_context_entity
        and not followup
        and not catalog_followup
    ):
        next_state = update_conversation_state(state, analysis)
        answer_plan = plan_answer(analysis, status="out_of_scope")
        return _attach_answer_plan({
            "answer": OUT_OF_SCOPE_ANSWER,
            "sources": [],
            "status": "out_of_scope",
            "state": next_state.to_dict(),
            "conversation_state": next_state.to_dict(),
            "trace": _trace(analysis, plan, next_state, answer_plan=answer_plan),
        }, answer_plan)

    explicit_year = requested_year(query)
    if explicit_year is not None and explicit_year != settings_obj.target_year:
        answer_plan = plan_answer(analysis, status="no_data")
        return _attach_answer_plan({
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": state.to_dict(),
            "trace": _trace(analysis, plan, state, answer_plan=answer_plan),
        }, answer_plan)

    if plan.needs_clarification:
        return _clarification_result(analysis, plan, state)

    active_retriever = retriever or DHVRetriever(settings_obj=settings_obj)
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
    if analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}:
        evidence_documents = _source_ordered_documents(evidence_documents)
    evidence = build_evidence(evidence_documents, settings_obj=settings_obj)
    analysis = enrich_analysis_from_evidence(analysis, evidence)
    score_comparisons = deterministic_score_comparisons(analysis, evidence)
    score_evaluation = deterministic_score_evaluation(analysis, evidence)
    listed_majors = None
    if analysis.intent == "DANH_SACH_NGANH":
        listed_majors = [major for major, _ in _major_rows_from_evidence(evidence)]
    next_state = update_conversation_state(
        state,
        analysis,
        target_year=settings_obj.target_year,
        last_listed_majors=listed_majors,
        last_list_count=len(listed_majors) if listed_majors is not None else None,
    )
    trace = _trace(
        analysis,
        plan,
        next_state,
        retrieval_audit,
        evidence_selection,
    )
    trace["score_comparisons"] = [dict(comparison) for comparison in score_comparisons]
    trace["score_engine"] = score_evaluation
    if score_evaluation.get("status") == "insufficient-data":
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

    requested_combination = analysis.entities.get("admission_combination")
    if requested_combination and not _combination_is_verified(evidence, requested_combination):
        # A 2026 source can mention an older/unverified combination precisely
        # to say it must not be imported. Treat that as no-data rather than
        # allowing a generic threshold or formula answer to look like support
        # for the requested combination.
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

    website_answer = _official_links_answer(analysis, evidence)
    if website_answer is not None:
        website_answer["state"] = next_state.to_dict()
        website_answer["conversation_state"] = next_state.to_dict()
        answer_plan = plan_answer(analysis, evidence=evidence, deterministic=True)
        trace["answer_plan"] = answer_plan.to_dict()
        website_answer["trace"] = trace
        return _attach_answer_plan(website_answer, answer_plan)

    catalog_answer = _evidence_catalog_answer(analysis, evidence, state)
    if catalog_answer is not None:
        # Major/program catalogues are structured evidence. Formatting them
        # deterministically prevents an LLM from turning child programmes
        # into majors or dropping rows from the verified source table.
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

    if analysis.intent == "SCHOOL_INFO":
        overview_answer = _evidence_directory_answer(analysis, evidence) or _evidence_overview_answer(evidence)
        if overview_answer:
            # School overview is a bounded summary owned by selected evidence;
            # it should not become a model-dependent dump of addresses,
            # contacts, or historical caveats.
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

    # A personal score comparison is a closed, numeric operation. Keep it out
    # of free-form generation so the model cannot turn a threshold comparison
    # into an admission verdict.
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
        )
        validation_reason = result.pop("_validation_reason", None)
        if result.get("status") == "ok":
            structured_answer = None
            if answer_plan.mode == "OVERVIEW":
                # A school overview should be a compact summary, not a dump
                # of every retrieved contact/address line.
                structured_answer = _evidence_overview_answer(evidence)
            elif answer_plan.mode == "COMPARISON":
                # The model may satisfy the grounding check while still
                # collapsing a side-by-side request into prose. Keep
                # generation for natural language, then enforce the planner's
                # comparison shape from the same verified facts.
                structured_answer = _structured_comparison_answer(analysis, evidence)
            elif (
                analysis.intent == "HOI_HOC_BONG"
                and not analysis.entities.get("student_scores")
            ):
                # Scholarship policy is a set of independent conditions. A
                # compact evidence-owned list is safer and easier to scan than
                # letting generation merge conditions into one paragraph.
                structured_answer = _evidence_scholarship_answer(evidence)
            if structured_answer:
                structured_result = validate_model_answer(
                    structured_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
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
            # Local generation can fail nondeterministically even when the
            # selected tuition line is sufficient.  Keep the user-facing
            # answer useful without weakening the validator or changing any
            # injected test double's behavior.
            tuition_answer = _evidence_tuition_answer(evidence)
            if tuition_answer:
                fallback_result = validate_model_answer(
                    tuition_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
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
            scholarship_answer = _evidence_scholarship_answer(evidence)
            if scholarship_answer:
                fallback_result = validate_model_answer(
                    scholarship_answer,
                    evidence,
                    question=query,
                    analysis=analysis,
                )
                if fallback_result.get("status") == "ok":
                    result = fallback_result
                    validation_reason = None
        elif (
            result.get("status") == "ok"
            and not _advisory_answer_has_guidance(analysis, result.get("answer"))
        ):
            # A model can produce a fact dump that passes entity validation
            # while still failing the user's counselling request. Replace
            # that shape with an evidence-only comparison and a next question.
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
        # An empty or malformed local-model response is not an answer. Keep
        # the user-facing contract explicit: say we do not know instead of
        # allowing a generic error message to look like an answer.
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
    final_answer_plan = plan_answer(
        analysis,
        evidence=evidence,
        status=final_status,
    )
    trace["answer_plan"] = final_answer_plan.to_dict()
    result["state"] = next_state.to_dict()
    # Keep an explicit service-facing alias so callers do not drop state after
    # a clarification response by looking for conversation_state.
    result["conversation_state"] = next_state.to_dict()
    result["trace"] = trace
    return _attach_answer_plan(result, final_answer_plan)


__all__ = ["ask_chatbot"]
