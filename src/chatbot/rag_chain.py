"""RAG orchestration with analysis, bounded conversation state and audit."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

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
    select_candidate_documents,
    select_program_relations,
)
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
    enrich_analysis_from_evidence,
    route_question,
    select_relevant_score_facts,
    normalize_question,
    _is_global_catalog_request,
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
    }
)


def _analysis_with_state(analysis: QueryAnalysis, state: ConversationState) -> QueryAnalysis:
    entities = dict(analysis.entities)
    if (
        not entities.get("major_name")
        and state.current_major
        and not entities.get("program_name")
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
) -> dict[str, object]:
    return {
        "intent": analysis.intent,
        "entities": dict(analysis.entities),
        "router": plan.to_dict(),
        "conversation_state": state.to_dict(),
        "retrieval": retrieval_audit.to_dict() if retrieval_audit is not None else None,
    }


_ADVISORY_SAFE_FALLBACK_REASONS = frozenset(
    {
        "model_fallback",
        "ungrounded",
        "program_relation_missing",
        "program_relation_wrong",
        "advisory_choices_incomplete",
    }
)


def _clarification_result(
    analysis: QueryAnalysis,
    plan: Any,
    state: ConversationState,
) -> dict[str, object]:
    next_state = update_conversation_state(state, analysis)
    return {
        "answer": CLARIFICATION_ANSWER,
        "sources": [],
        "status": "clarification",
        "state": next_state.to_dict(),
        "conversation_state": next_state.to_dict(),
        "trace": _trace(analysis, plan, next_state),
    }


def _retrieve(
    retriever: Any,
    question: str,
    plan: Any,
) -> tuple[list[Any], Any]:
    method = getattr(retriever, "retrieve_with_audit", None)
    if callable(method):
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


def _validated_generation(
    *,
    active_llm: Any,
    prompt: str,
    evidence: Any,
    question: str,
    analysis: QueryAnalysis,
    score_facts: Any,
) -> dict[str, object]:
    raw_answer = active_llm.generate(prompt)
    validated = validate_model_answer(
        raw_answer,
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
    """Return a useful, evidence-only answer when advisory generation fails."""

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
            f"Với sở thích {interest}, mình nghiêng về {preferred_program} hơn. "
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
            lines.append(f"Mình ghi nhận bạn đang quan tâm đến {interest}.")
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
    """Choose a conditional advisory target from user interest and evidence names."""

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
    for program in candidate_programs:
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
    """Return ordered, deduplicated major rows from the verified catalogue."""

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
    """Return ordered program-parent mappings without promoting programs to majors."""

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
    """Format catalogue answers from structured evidence, not model prose."""

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
    """Restore source order after hybrid ranking for catalogue responses."""

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
    """Answer one turn through analysis → router → retrieval → generation."""

    query = question.strip() if isinstance(question, str) else ""
    state = ConversationState.from_value(conversation_state, default_year=settings_obj.target_year)
    analysis = analyze_question(query, state, default_year=settings_obj.target_year)
    analysis = _analysis_with_state(analysis, state)
    plan = route_question(analysis, state, target_year=settings_obj.target_year)

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
    if not is_in_scope(query) and not has_context_entity and not followup and not catalog_followup:
        return {
            "answer": OUT_OF_SCOPE_ANSWER,
            "sources": [],
            "status": "out_of_scope",
            "state": update_conversation_state(state, analysis).to_dict(),
            "trace": _trace(analysis, plan, state),
        }

    explicit_year = requested_year(query)
    if explicit_year is not None and explicit_year != settings_obj.target_year:
        return {
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": state.to_dict(),
            "trace": _trace(analysis, plan, state),
        }

    if plan.needs_clarification:
        return _clarification_result(analysis, plan, state)

    active_retriever = retriever or DHVRetriever(settings_obj=settings_obj)
    retrieval_audit = None
    try:
        documents, retrieval_audit = _retrieve(active_retriever, query, plan)
    except RetrieverEmbeddingError:
        return {
            "answer": OLLAMA_OFFLINE_ANSWER,
            "sources": [],
            "status": "ollama_offline",
            "state": state.to_dict(),
            "trace": _trace(analysis, plan, state),
        }
    except VectorDatabaseError:
        return {
            "answer": VECTOR_DB_ERROR_ANSWER,
            "sources": [],
            "status": "vector_db_error",
            "state": state.to_dict(),
            "trace": _trace(analysis, plan, state, retrieval_audit),
        }
    except Exception:
        return {
            "answer": ERROR_ANSWER,
            "sources": [],
            "status": "error",
            "state": state.to_dict(),
            "trace": _trace(analysis, plan, state),
        }

    candidate_values = _candidate_values(analysis)
    evidence_documents = select_candidate_documents(documents, candidate_values)
    if candidate_values and not evidence_documents:
        # A candidate name can be split across retrieval chunks or absent from
        # a broad row returned by a test/store adapter. Keep verified source
        # documents available rather than turning a recoverable advisory into
        # evidence_empty.
        evidence_documents = select_candidate_documents(documents)
    if analysis.intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}:
        evidence_documents = _source_ordered_documents(evidence_documents)
    evidence = build_evidence(evidence_documents, settings_obj=settings_obj)
    analysis = enrich_analysis_from_evidence(analysis, evidence)
    score_comparisons = deterministic_score_comparisons(analysis, evidence)
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
    trace = _trace(analysis, plan, next_state, retrieval_audit)
    trace["score_comparisons"] = [dict(comparison) for comparison in score_comparisons]
    if not evidence.is_usable:
        return {
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "status": "no_data",
            "state": next_state.to_dict(),
            "trace": trace,
        }

    catalog_answer = _evidence_catalog_answer(analysis, evidence, state)
    if catalog_answer is not None:
        # Major/program catalogues are structured evidence. Formatting them
        # deterministically prevents an LLM from turning child programmes
        # into majors or dropping rows from the verified source table.
        if catalog_answer.get("catalog") is not None:
            trace["catalog"] = catalog_answer["catalog"]
        catalog_answer["state"] = next_state.to_dict()
        catalog_answer["conversation_state"] = next_state.to_dict()
        catalog_answer["trace"] = trace
        return catalog_answer

    prompt = build_rag_prompt(
        query,
        evidence.context,
        intent=analysis.intent,
        entities=analysis.entities,
        conversation_state=next_state.to_dict(),
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
        )
        validation_reason = result.pop("_validation_reason", None)
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
    except OllamaUnavailableError:
        return {
            "answer": OLLAMA_OFFLINE_ANSWER,
            "sources": [],
            "status": "ollama_offline",
            "state": next_state.to_dict(),
            "trace": trace,
        }
    except OllamaError:
        return {
            "answer": ERROR_ANSWER,
            "sources": [],
            "status": "error",
            "state": next_state.to_dict(),
            "trace": trace,
        }
    except Exception:
        return {
            "answer": ERROR_ANSWER,
            "sources": [],
            "status": "error",
            "state": next_state.to_dict(),
            "trace": trace,
        }

    result["state"] = next_state.to_dict()
    # Keep an explicit service-facing alias so callers do not drop state after
    # a clarification response by looking for conversation_state.
    result["conversation_state"] = next_state.to_dict()
    result["trace"] = trace
    return result


__all__ = ["ask_chatbot"]
