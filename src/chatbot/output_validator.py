"""Evidence validation for model output before it reaches the UI."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

from .evidence import EvidenceBundle


FALLBACK_ANSWER = (
    "Hiện tại tôi chưa tìm thấy thông tin này trong dữ liệu tuyển sinh DHV đã "
    "được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường "
    "Đại học Hùng Vương TP.HCM."
)
OUT_OF_SCOPE_ANSWER = (
    "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh Trường Đại học "
    "Hùng Vương TP.HCM."
)
CLARIFICATION_ANSWER = (
    "Bạn muốn biết điểm sàn (ngưỡng đầu vào), điểm trúng tuyển hay điểm của đợt "
    "xét tuyển bổ sung?"
)
OLLAMA_OFFLINE_ANSWER = (
    "Hiện tại dịch vụ trả lời cục bộ chưa sẵn sàng. Bạn vui lòng thử lại sau."
)
VECTOR_DB_ERROR_ANSWER = (
    "Hiện tại kho dữ liệu tuyển sinh DHV chưa sẵn sàng. Bạn vui lòng thử lại sau."
)
ERROR_ANSWER = "Xin lỗi, tôi chưa thể xử lý câu hỏi này lúc này. Bạn vui lòng thử lại sau."

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>]+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(\s*(?:https?://|www\.)[^)]+\)", re.IGNORECASE
)
_TOKEN_RE = re.compile(r"\d[\d.,]*|[A-Za-zÀ-ỹĐđ]+", re.UNICODE)
_LABELED_AMOUNT_RE = re.compile(
    r"(?:học phí|hoc phi)[^\n]{0,100}?(?:[:=]|\blà\b|\bla\b)\s*(\d[\d.,]*)",
    re.IGNORECASE,
)
_METHOD_PATTERNS = {
    "thpt": re.compile(r"(?:tốt nghiệp|tot nghiep|thi thpt|thi tn thpt)(?:[^0-9\n]*20\d{2})?[^0-9\n]*(\d[\d.,]*|-)", re.IGNORECASE),
    "hoc_ba": re.compile(r"(?:học bạ|hoc ba|học tập thpt)(?:[^0-9\n]*20\d{2})?[^0-9\n]*(\d[\d.,]*|-)", re.IGNORECASE),
    "dgnl": re.compile(r"(?:đánh giá năng lực|danh gia nang luc|đgnl|dgnl)(?:[^0-9\n]*20\d{2})?[^0-9\n]*(\d[\d.,]*|-)", re.IGNORECASE),
}
_METHOD_LABELS = {
    "thpt": r"(?:tốt nghiệp|tot nghiep|thi thpt|thi tn thpt)",
    "hoc_ba": r"(?:học bạ|hoc ba|học tập thpt)",
    "dgnl": r"(?:đánh giá năng lực|danh gia nang luc|đgnl|dgnl)",
}
_SUPPLEMENTARY_DATE_RE = re.compile(
    r"(?:đến hết ngày|den het ngay|đến ngày|den ngay)\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
_DATE_LITERAL_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b")
_CONTACT_NUMBER_RE = re.compile(
    r"(?<!\d)(?:\+?\d)(?:[\s().-]?\d){7,14}(?!\d)"
)
_EMAIL_LITERAL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
)
_ENTITY_CLAIM_RE = re.compile(
    r"(?:^|[;,]\s*|[—-]\s*)"
    r"(?P<entity>[^,.;:\n]{1,90}?)\s+"
    r"(?:có|là|thuộc|gồm|nhận|được tuyển|từ)\b",
    re.IGNORECASE,
)
_ORGANIZATION_RE = re.compile(
    r"\b(?:trường\s+đại học|đại học)\s+[^,.;:\n]{2,90}",
    re.IGNORECASE,
)
_TRUSTED_SCHOOL_NAMES = frozenset(
    {
        "truong dai hoc hung vuong tphcm",
        "truong dai hoc hung vuong tp hcm",
        "truong dai hoc hung vuong tp",
        "dai hoc hung vuong tphcm",
        "dai hoc hung vuong tp hcm",
        "dai hoc hung vuong tp",
    }
)
_STOPWORDS = frozenset(
    {
        "va", "la", "cua", "cho", "toi", "ban", "mot", "nhung", "duoc",
        "theo", "trong", "nam", "nay", "co", "den", "tu", "voi", "cac",
        "tien", "diem",
    }
)


def validate_model_answer(
    raw_answer: str,
    evidence: EvidenceBundle,
    *,
    question: str = "",
    analysis: Mapping[str, object] | Any | None = None,
) -> dict[str, object]:
    """Accept only a grounded answer with correct structured score mapping.

    This function never constructs a replacement answer from evidence.  A
    failed validation is returned as ``no_data``; the orchestration layer may
    ask the LLM once more with a correction instruction and validate again.
    """

    if not evidence.is_usable:
        return _failed("evidence_empty")
    answer = sanitize_answer(raw_answer)
    if _is_model_fallback(answer) or not answer:
        return _failed("model_fallback")
    if not _is_supported_by_evidence(answer, evidence):
        return _failed("ungrounded")
    relation_failure = _program_relation_failure(answer, evidence, analysis)
    if relation_failure:
        return _failed(relation_failure)
    catalog_failure = _program_catalog_failure(answer, evidence, question, analysis)
    if catalog_failure:
        return _failed(catalog_failure)
    advisory_choice_failure = _advisory_choice_failure(answer, analysis)
    if advisory_choice_failure:
        return _failed(advisory_choice_failure)
    if _has_unsupported_named_entity(answer, evidence, analysis):
        return _failed("ungrounded_entity")
    literal_failure = _unsupported_contact_or_date_literal(answer, evidence, analysis)
    if literal_failure:
        return _failed(literal_failure)
    if _contains_forbidden_admission_claim(answer):
        return _failed("personal_admission_claim")

    if not _has_required_labeled_amount(answer, evidence, question):
        return _failed("tuition_label_or_value")
    score_failure = _score_mapping_failure(answer, evidence, question, analysis)
    if score_failure:
        return _failed(score_failure)
    if not _has_required_supplementary_date(answer, evidence, question):
        return _failed("supplementary_date")

    return {
        "answer": answer,
        "sources": [dict(source) for source in evidence.sources],
        "status": "ok",
    }


def _failed(reason: str) -> dict[str, object]:
    return {
        "answer": FALLBACK_ANSWER,
        "sources": [],
        "status": "no_data",
        "_validation_reason": reason,
    }


def sanitize_answer(answer: str) -> str:
    """Remove links/citation URLs the model may have ignored in the prompt."""

    if not isinstance(answer, str):
        return ""
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", answer)
    cleaned = _URL_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _is_supported_by_evidence(answer: str, evidence: EvidenceBundle) -> bool:
    answer_tokens = _meaningful_tokens(answer)
    evidence_tokens = _meaningful_tokens(" ".join(chunk.text for chunk in evidence.chunks))
    if not answer_tokens or not evidence_tokens:
        return False
    overlap = answer_tokens & evidence_tokens
    return len(overlap) >= 2 or any(token[0].isdigit() for token in overlap)


def _has_unsupported_named_entity(
    answer: str,
    evidence: EvidenceBundle,
    analysis: Mapping[str, object] | Any | None,
) -> bool:
    """Reject named admissions entities that are absent from retrieved text.

    Token overlap alone is too permissive: an answer can mention an unrelated
    major or university while reusing a valid score such as 600. This guard
    checks entity-shaped claims against the actual evidence text and the
    evidence-derived major/program relations. Generic sentence labels are
    ignored, but named candidates and organizations must be present verbatim
    after normalization.
    """

    entities = _analysis_entities(analysis)
    intent = str(analysis.get("intent")) if isinstance(analysis, Mapping) else str(getattr(analysis, "intent", ""))
    if intent != "TU_VAN_CHON_NGANH":
        return False
    evidence_text = _fold_text(" ".join(chunk.text for chunk in evidence.chunks))
    allowed_names = {
        _fold_text(str(relation.get("program_name")))
        for relation in evidence.entity_relations
        if relation.get("program_name")
    }
    allowed_names.update(
        _fold_text(str(relation.get("parent_major")))
        for relation in evidence.entity_relations
        if relation.get("parent_major")
    )
    allowed_names.update(
        _fold_text(str(fact.get("major_name")))
        for fact in evidence.score_facts
        if fact.get("major_name")
    )
    # A candidate is allowed only if it also occurs in retrieved evidence.
    for key in ("candidate_majors", "candidate_programs"):
        values = entities.get(key) if isinstance(entities, Mapping) else None
        if isinstance(values, (list, tuple)):
            for value in values:
                normalized = _fold_text(value)
                if normalized and normalized in evidence_text:
                    allowed_names.add(normalized)

    generic_prefixes = (
        "diem ",
        "nguong ",
        "du lieu ",
        "voi ",
        "theo ",
        "so thich ",
        "chuyen nganh ",
        "cac nganh ",
        "cac lua chon ",
        "nhom nganh ",
        "nganh phu hop ",
        "danh sach ",
    )
    for match in _ENTITY_CLAIM_RE.finditer(answer):
        candidate = _fold_text(match.group("entity"))
        candidate = re.sub(r"^(?:nganh|chuong trinh)\s+", "", candidate).strip()
        residual = candidate
        for allowed in sorted(allowed_names, key=len, reverse=True):
            residual = residual.replace(allowed, " ")
        residual = re.sub(
            r"\b(?:ban|toi|co|the|tham|khao|chuong|trinh|cac|nganh|phu|hop|"
            r"lua|chon|dang|can|nhac|den|voi|so|thich|la|thuoc|nam|trong|"
            r"nganh|cha|duoc|goi|y|nhu|mot|nhom|cac|van)\b",
            " ",
            residual,
        )
        if (
            not candidate
            or candidate.startswith(generic_prefixes)
            or any(term in candidate for term in ("diem ", "nguong ", "ho so", "so voi"))
        ):
            continue
        if residual.strip():
            return True

    for match in _ORGANIZATION_RE.finditer(answer):
        organization = _fold_text(match.group(0))
        if organization in _TRUSTED_SCHOOL_NAMES:
            continue
        if organization not in evidence_text:
            return True
    return False


def _is_model_fallback(answer: str) -> bool:
    normalized = _fold_text(answer)
    return "chua tim thay thong tin" in normalized


def _contains_forbidden_admission_claim(answer: str) -> bool:
    normalized = _fold_text(answer)
    return any(
        phrase in normalized
        for phrase in (
            "chac chan dau",
            "ban se dau",
            "du dieu kien trung tuyen",
            "dam bao trung tuyen",
            "chac chan trung tuyen",
            "du dieu kien xet tuyen",
            "dau chac",
        )
    )


def _program_relation_failure(
    answer: str,
    evidence: EvidenceBundle,
    analysis: Mapping[str, object] | Any | None,
) -> str:
    """Reject a code or relationship that the retrieved corpus does not map."""

    entities = _analysis_entities(analysis)
    programs = list(_candidate_strings(entities.get("candidate_programs")))
    program = str(entities.get("program_name") or "")
    if program and program not in programs:
        programs.insert(0, program)
    if not programs:
        return ""
    answer_folded = _fold_text(answer)
    for program in programs:
        folded_program = _fold_text(program)
        if folded_program not in answer_folded:
            continue
        relations = [
            relation
            for relation in evidence.entity_relations
            if _fold_text(str(relation.get("program_name") or "")) == folded_program
        ]
        if not relations:
            return "program_relation_missing"
        # A program may be discussed as an option, but it must not be relabeled
        # as a standalone major in the model's answer.
        if re.search(rf"{re.escape(folded_program)}\s+la\s+nganh\b", answer_folded) or re.search(
            rf"\bnganh\s+{re.escape(folded_program)}\b", answer_folded
        ):
            return "program_relation_wrong"
        expected_parents = {
            _fold_text(str(relation.get("parent_major") or ""))
            for relation in relations
            if relation.get("parent_major")
        }
        relation_patterns = (
            rf"{re.escape(folded_program)}\s+thuoc\s+nganh\s+([^,.;]+)",
            rf"{re.escape(folded_program)}\s+la\s+chuong trinh\s+thuoc\s+nganh\s+([^,.;]+)",
            rf"{re.escape(folded_program)}\s+nam trong nganh(?:\s+cha)?\s+([^,.;]+)",
        )
        for pattern in relation_patterns:
            for parent_match in re.finditer(pattern, answer_folded):
                mentioned_parent = parent_match.group(1).strip()
                if expected_parents and not any(
                    mentioned_parent == parent
                    or mentioned_parent.startswith(parent + " ")
                    or parent.startswith(mentioned_parent + " ")
                    for parent in expected_parents
                ):
                    return "program_relation_wrong"
        if expected_parents and not any(parent in answer_folded for parent in expected_parents):
            return "program_relation_missing"
        expected_parent_codes = {
            str(fact.get("major_code"))
            for fact in evidence.score_facts
            if _fold_text(str(fact.get("major_name") or "")) in expected_parents
            and fact.get("major_code")
        }
        candidate_major_names = set(_candidate_strings(entities.get("candidate_majors")))
        allowed_codes = set(expected_parent_codes)
        allowed_codes.update(
            str(fact.get("major_code"))
            for fact in evidence.score_facts
            if str(fact.get("major_name") or "") in candidate_major_names
            and fact.get("major_code")
        )
        answer_codes = set(re.findall(r"\b\d{7}\b", answer))
        if answer_codes and not answer_codes.issubset(allowed_codes):
            return "program_relation_wrong"
        for pattern in relation_patterns:
            for parent_match in re.finditer(pattern, answer_folded):
                mentioned_parent = parent_match.group(1).strip()
                mentioned_codes = set(re.findall(r"\b\d{7}\b", mentioned_parent))
                if mentioned_codes and expected_parent_codes and not mentioned_codes.issubset(expected_parent_codes):
                    return "program_relation_wrong"
    return ""


def _candidate_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _program_catalog_failure(
    answer: str,
    evidence: EvidenceBundle,
    question: str,
    analysis: Mapping[str, object] | Any | None,
) -> str:
    """Validate catalog scope, relation coverage and deterministic counts."""

    entities = _analysis_entities(analysis)
    if isinstance(analysis, Mapping):
        intent = str(analysis.get("intent") or "")
    else:
        intent = str(getattr(analysis, "intent", "") or "")
    if intent != "DANH_SACH_CHUONG_TRINH":
        return ""

    normalized_question = _fold_text(question)
    operation = str(entities.get("catalog_operation") or "")
    if not operation:
        count_requested = bool(
            re.search(r"\b(?:bao nhieu|may|so luong)\b.{0,32}\b(?:chuong trinh|chuyen nganh)\b", normalized_question)
            or re.search(r"\b(?:chuong trinh|chuyen nganh)\b.{0,32}\b(?:bao nhieu|may|so luong)\b", normalized_question)
        )
        list_requested = any(
            marker in normalized_question
            for marker in ("danh sach", "liet ke", "liet ra", "co nhung", "nhung", "cac", "gom", "nao")
        )
        operation = (
            "LIST_AND_COUNT" if count_requested and list_requested
            else "COUNT" if count_requested
            else "LIST"
        )

    requested_major = _fold_text(str(entities.get("major_name") or ""))
    rows: list[tuple[str, str]] = []
    all_rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for relation in evidence.entity_relations:
        program = _fold_text(str(relation.get("program_name") or ""))
        parent = _fold_text(str(relation.get("parent_major") or ""))
        if not program or not parent:
            continue
        identity = (parent, program)
        if identity in seen:
            continue
        seen.add(identity)
        all_rows.append(identity)
        if not requested_major or parent == requested_major:
            rows.append(identity)

    if not rows:
        return "program_catalog_missing"

    # Even for a count-only request, a named child from another parent must not
    # leak into the answer as part of a model-generated explanation.
    if requested_major:
        for parent, program in all_rows:
            if parent != requested_major and program in _fold_text(answer):
                return "program_catalog_parent_mismatch"

    if operation in {"COUNT", "LIST_AND_COUNT"}:
        counts = {
            int(match.group(1))
            for match in re.finditer(r"\b(\d+)\s+(?:chuong trinh|chuyen nganh)\b", _fold_text(answer))
        }
        if len(rows) not in counts:
            return "program_catalog_count_mismatch"

    if operation in {"LIST", "LIST_AND_COUNT"}:
        folded_answer = _fold_text(answer)
        for parent, program in rows:
            if program not in folded_answer or parent not in folded_answer:
                return "program_catalog_missing"
    return ""


def _advisory_choice_failure(
    answer: str,
    analysis: Mapping[str, object] | Any | None,
) -> str:
    """Reject a confident single-choice answer for an unresolved comparison."""

    entities = _analysis_entities(analysis)
    intent = str(analysis.get("intent")) if isinstance(analysis, Mapping) else str(getattr(analysis, "intent", ""))
    if intent != "TU_VAN_CHON_NGANH":
        return ""
    candidates: list[str] = []
    for key in ("candidate_majors", "candidate_programs"):
        for value in _candidate_strings(entities.get(key)):
            if value not in candidates:
                candidates.append(value)
    if len(candidates) < 2:
        return ""
    folded_answer = _fold_text(answer)
    mentioned = [candidate for candidate in candidates if _fold_text(candidate) in folded_answer]
    if not mentioned or len(mentioned) == len(candidates):
        return ""
    selector_markers = (
        "tu van cho ban theo nganh",
        "tu van cho ban theo chuong trinh",
        "nen chon",
        "nen hoc",
        "lua chon phu hop nhat",
        "phu hop nhat la",
        "chon nganh",
    )
    if any(marker in folded_answer for marker in selector_markers):
        return "advisory_choices_incomplete"
    return ""


def _has_required_labeled_amount(answer: str, evidence: EvidenceBundle, question: str) -> bool:
    if "hoc phi" not in _fold_text(question):
        return True
    evidence_amounts = {
        match.group(1)
        for chunk in evidence.chunks
        for match in _LABELED_AMOUNT_RE.finditer(chunk.text)
    }
    if not evidence_amounts:
        return True
    answer_has_tuition_label = bool(
        re.search(r"(?:học phí|hoc phi)[^\n]{0,100}(?:[:=]|\blà\b|\bla\b)", answer, re.IGNORECASE)
    )
    return answer_has_tuition_label and any(amount in answer for amount in evidence_amounts)


def _score_mapping_failure(
    answer: str,
    evidence: EvidenceBundle,
    question: str,
    analysis: Mapping[str, object] | Any | None,
) -> str:
    normalized_question = _fold_text(question)
    facts = list(evidence.score_facts)
    if not facts:
        return ""
    entities = _analysis_entities(analysis)
    major = _fold_text(str(entities.get("major_name") or ""))
    code = str(entities.get("major_code") or "")
    score_type = entities.get("score_type")
    if not score_type:
        if "diem san" in normalized_question or "nguong dau vao" in normalized_question or "diem dau vao" in normalized_question:
            score_type = "application_threshold"
        elif "diem trung tuyen" in normalized_question or "diem chuan" in normalized_question:
            score_type = "admission_score"
        elif "xet tuyen bo sung" in normalized_question:
            score_type = "supplementary_threshold"
    if not score_type:
        return ""

    typed_facts = [fact for fact in facts if fact.get("score_type") == score_type]
    if not typed_facts:
        return ""
    if major or code:
        specific = [
            fact
            for fact in typed_facts
            if (major and _fold_text(str(fact.get("major_name") or "")) == major)
            or (code and str(fact.get("major_code") or "") == code)
        ]
        typed_facts = specific or [fact for fact in typed_facts if not fact.get("major_name")]
    else:
        typed_facts = [fact for fact in typed_facts if not fact.get("major_name")] or typed_facts

    expected_by_method: dict[str, set[str]] = {}
    for fact in typed_facts:
        expected_by_method.setdefault(str(fact.get("method")), set()).add(str(fact.get("raw_value")))
    if score_type == "application_threshold":
        for method in ("thpt", "hoc_ba", "dgnl"):
            expected = expected_by_method.get(method, set())
            if not expected:
                continue
            actual_raw = _extract_method_value(answer, method)
            if actual_raw is None:
                return "missing_threshold_mapping"
            actual = _number_token(actual_raw)
            allowed = {_number_token(value) for value in expected if value != "-"}
            if "-" in expected:
                if actual is not None or "-" not in answer:
                    return "wrong_threshold_mapping"
            elif actual is None or actual not in allowed:
                return "wrong_threshold_mapping"
        return ""
    if score_type == "admission_score":
        values = {str(fact.get("raw_value")) for fact in typed_facts}
        if not any(value in answer for value in values):
            return "missing_admission_score"
    if score_type == "supplementary_threshold":
        for method, expected in expected_by_method.items():
            if method == "deadline":
                continue
            actual = _extract_method_value(answer, method)
            if actual is None or not any(_number_token(value) == _number_token(actual) for value in expected):
                return "wrong_supplementary_mapping"
    return ""


def _analysis_entities(analysis: Mapping[str, object] | Any | None) -> Mapping[str, object]:
    if analysis is None:
        return {}
    if isinstance(analysis, Mapping):
        entities = analysis.get("entities")
        return entities if isinstance(entities, Mapping) else analysis
    entities = getattr(analysis, "entities", {})
    return entities if isinstance(entities, Mapping) else {}


def _has_required_supplementary_date(answer: str, evidence: EvidenceBundle, question: str) -> bool:
    normalized_question = _fold_text(question)
    if "xet tuyen bo sung" not in normalized_question and "tuyen sinh bo sung" not in normalized_question:
        return True
    required_dates = {
        str(fact.get("raw_value"))
        for fact in evidence.score_facts
        if fact.get("score_type") == "supplementary_threshold" and fact.get("method") == "deadline"
    }
    if not required_dates:
        required_dates = {
            match.group(1)
            for chunk in evidence.chunks
            for match in _SUPPLEMENTARY_DATE_RE.finditer(_fold_text(chunk.text))
        }
    return not required_dates or any(date in answer for date in required_dates)


_FACT_ONLY_INTENTS = frozenset(
    {
        "HOI_PHUONG_THUC_XET_TUYEN",
        "HOI_CACH_TINH_DIEM",
        "HOI_DANG_KY_XET_TUYEN",
        "HOI_CO_SO_LIEN_HE",
    }
)


def _unsupported_contact_or_date_literal(
    answer: str,
    evidence: EvidenceBundle,
    analysis: Mapping[str, object] | Any | None,
) -> str:
    """Reject invented contact/date literals in the four fact-only topics."""

    if isinstance(analysis, Mapping):
        intent = str(analysis.get("intent") or "")
    else:
        intent = str(getattr(analysis, "intent", "") or "")
    if intent not in _FACT_ONLY_INTENTS:
        return ""

    evidence_text = " ".join(chunk.text for chunk in evidence.chunks)
    if intent == "HOI_CO_SO_LIEN_HE":
        evidence_phones = {
            re.sub(r"\D", "", value)
            for value in _CONTACT_NUMBER_RE.findall(evidence_text)
        }
        for value in _CONTACT_NUMBER_RE.findall(answer):
            if re.sub(r"\D", "", value) not in evidence_phones:
                return "unsupported_contact_value"
        evidence_emails = {
            value.casefold() for value in _EMAIL_LITERAL_RE.findall(evidence_text)
        }
        for value in _EMAIL_LITERAL_RE.findall(answer):
            if value.casefold() not in evidence_emails:
                return "unsupported_contact_value"

    evidence_dates = {
        "".join(character for character in value if character.isdigit())
        for value in _DATE_LITERAL_RE.findall(evidence_text)
    }
    for value in _DATE_LITERAL_RE.findall(answer):
        normalized = "".join(character for character in value if character.isdigit())
        if normalized not in evidence_dates:
            return "unsupported_date"
    return ""


def _number_token(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def _extract_method_value(answer: str, method: str) -> str | None:
    """Read a value from the same mapping segment as a method label.

    Answers may write either ``THPT: 15`` or ``15 điểm theo ... THPT``.
    Segmenting on mapping punctuation prevents the value for the next method
    from being associated with the current label.
    """

    label = _METHOD_LABELS[method]
    for label_match in re.finditer(label, answer, re.IGNORECASE):
        left = max(
            answer.rfind(",", 0, label_match.start()),
            answer.rfind(";", 0, label_match.start()),
            answer.rfind("\n", 0, label_match.start()),
            _last_sentence_boundary(answer, label_match.start()),
        )
        right_candidates = [
            position
            for position in (
                answer.find(",", label_match.end()),
                answer.find(";", label_match.end()),
                answer.find("\n", label_match.end()),
                _next_sentence_boundary(answer, label_match.end()),
            )
            if position >= 0
        ]
        right = min(right_candidates, default=len(answer))
        segment_start = left + 1
        segment = answer[segment_start:right]
        label_start = max(0, label_match.start() - segment_start)
        before = _usable_value_tokens(segment[:label_start])
        after = _usable_value_tokens(segment[label_match.end() - segment_start :])
        numeric_before = [candidate for candidate in before if candidate != "-"]
        if numeric_before:
            return numeric_before[-1]
        if after:
            return after[0]
        if before:
            return before[-1]
    return None


def _usable_value_tokens(text: str) -> list[str]:
    values: list[str] = []
    for candidate in re.findall(r"\d[\d.,]*|-", text):
        compact = candidate.replace(".", "").replace(",", "")
        if compact == "2026" or len(compact) == 7:
            continue
        values.append(candidate)
    return values


def _last_sentence_boundary(text: str, end: int) -> int:
    positions = [
        match.start()
        for match in re.finditer(r"(?<!\d)\.|\.(?!\d)", text[:end])
    ]
    return max(positions, default=-1)


def _next_sentence_boundary(text: str, start: int) -> int:
    match = re.search(r"(?<!\d)\.|\.(?!\d)", text[start:])
    return start + match.start() if match else -1


def _fold_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    folded = folded.lower().replace("đ", "d")
    folded = folded.translate(str.maketrans({char: " " for char in '"“”‘’\'`'}))
    return re.sub(r"\s+", " ", folded).strip()


def _meaningful_tokens(text: str) -> set[str]:
    folded = _fold_text(text)
    return {
        token
        for token in _TOKEN_RE.findall(folded)
        if token not in _STOPWORDS and (len(token) >= 3 or token[0].isdigit())
    }


__all__ = [
    "CLARIFICATION_ANSWER",
    "ERROR_ANSWER",
    "FALLBACK_ANSWER",
    "OLLAMA_OFFLINE_ANSWER",
    "OUT_OF_SCOPE_ANSWER",
    "VECTOR_DB_ERROR_ANSWER",
    "sanitize_answer",
    "validate_model_answer",
]
