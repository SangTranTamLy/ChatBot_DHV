"""Lập kế hoạch trình bày câu trả lời trước khi gọi model ngôn ngữ.

Planner này chỉ quyết định *cách* diễn đạt một câu trả lời. Nó không truy xuất,
không tạo facts và không thay thế Evidence Selection hay các engine tất định.
Nhờ vậy cùng một bộ evidence có thể được trình bày ngắn gọn, giải thích, so
sánh hoặc tư vấn tùy loại câu hỏi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .query_analysis import normalize_question


ANSWER_MODES = (
    "DIRECT_SHORT",
    "EXPLANATION",
    "OVERVIEW",
    "COMPARISON",
    "TABLE",
    "STEP_BY_STEP",
    "RECOMMENDATION",
    "CLARIFICATION",
    "NO_DATA",
    "OUT_OF_SCOPE",
)

(
    DIRECT_SHORT,
    EXPLANATION,
    OVERVIEW,
    COMPARISON,
    TABLE,
    STEP_BY_STEP,
    RECOMMENDATION,
    CLARIFICATION,
    NO_DATA,
    OUT_OF_SCOPE,
) = ANSWER_MODES

# ``TABLE`` is the historical public value for catalogue output.  Keep that
# value for existing integrations while exposing the task terminology as a
# semantic alias; catalogue rows are still rendered by the deterministic
# catalogue formatter in ``rag_chain``.
CATALOG_LIST = TABLE

# These aliases make the contract discoverable for callers that use the name
# ``PLANNER_MODES`` or ``ANSWER_PLANNER_MODES``.
PLANNER_MODES = ANSWER_MODES
ANSWER_PLANNER_MODES = ANSWER_MODES

_SYSTEM_INTENTS = frozenset({"GREETING", "SYSTEM_IDENTITY", "SYSTEM_SCOPE"})
_NO_EVIDENCE_STATUSES = frozenset(
    {"no_data", "ollama_offline", "vector_db_error", "error"}
)
_STEP_INTENTS = frozenset(
    {
        "HOI_HO_SO",
        "HOI_DANG_KY_XET_TUYEN",
        "HOI_NHAP_HOC",
        "HOI_LICH_TUYEN_SINH",
    }
)
_SIMPLE_INTENTS = frozenset(
    {
        "HOI_HOC_PHI",
        "HOI_CO_SO_LIEN_HE",
        "HOI_NGUONG_DAU_VAO",
        "HOI_DIEM_TRUNG_TUYEN",
        "HOI_XET_TUYEN_BO_SUNG",
    }
)
_OVERVIEW_MARKERS = (
    "tong quan",
    "khai quat",
    "gioi thieu",
    "toan dien",
    "co nhung gi",
)
_COMPARISON_MARKERS = (
    "so sanh",
    "khac nhau",
    "khac biet",
    "giua",
    "hay hon",
    "nen chon",
)
_TABLE_MARKERS = (
    "bang",
    "bang so sanh",
    "liet ke",
    "danh sach",
    "gom nhung",
    "co nhung",
)


@dataclass(frozen=True)
class AnswerPlan:
    """Contract nhỏ gọn cho bước realization của câu trả lời."""

    mode: str
    intent: str
    response_format: str
    lead_with: str
    sections: tuple[str, ...] = ()
    required_content: tuple[str, ...] = ()
    related_questions: tuple[str, ...] = ()
    evidence_required: bool = True
    deterministic: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.mode not in ANSWER_MODES:
            raise ValueError(f"Unsupported answer mode: {self.mode}")

    @property
    def answer_mode(self) -> str:
        """Alias dễ đọc cho code tích hợp."""

        return self.mode

    @property
    def format(self) -> str:
        """Tương thích với caller dùng ``format`` thay vì ``response_format``."""

        return self.response_format

    @property
    def use_table(self) -> bool:
        return self.mode == "TABLE"

    @property
    def is_catalog_list(self) -> bool:
        """Whether this plan uses the catalogue-list contract."""

        return self.mode == CATALOG_LIST and self.intent in {
            "DANH_SACH_NGANH",
            "DANH_SACH_CHUONG_TRINH",
        }

    @property
    def is_deterministic(self) -> bool:
        return self.deterministic

    def __getitem__(self, key: str) -> object:
        """Cho phép adapter cũ đọc plan như một payload mapping."""

        return self.to_dict()[key]

    def get(self, key: str, default: object = None) -> object:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "answer_mode": self.mode,
            "intent": self.intent,
            "response_format": self.response_format,
            "format": self.response_format,
            "lead_with": self.lead_with,
            "sections": list(self.sections),
            "required_content": list(self.required_content),
            "related_questions": list(self.related_questions),
            "evidence_required": self.evidence_required,
            "deterministic": self.deterministic,
            "reason": self.reason,
        }


def _field(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _entities(analysis: object) -> Mapping[str, object]:
    value = _field(analysis, "entities", {})
    return value if isinstance(value, Mapping) else {}


def _intent(analysis: object) -> str:
    return str(_field(analysis, "intent", "OUT_OF_SCOPE") or "OUT_OF_SCOPE")


def _normalized(analysis: object) -> str:
    value = _field(analysis, "normalized_question", None)
    if value is not None:
        return normalize_question(str(value))
    return normalize_question(str(_field(analysis, "question", "") or ""))


def _as_names(value: object) -> list[str]:
    items = value if isinstance(value, Sequence) and not isinstance(value, str) else (value,)
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _candidate_names(analysis: object) -> tuple[str, ...]:
    entities = _entities(analysis)
    names: list[str] = []
    seen: set[str] = set()
    for key in ("candidate_majors", "candidate_programs"):
        for value in _as_names(entities.get(key)):
            normalized = normalize_question(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                names.append(value)
    return tuple(names)


def _major_or_program(analysis: object) -> str | None:
    entities = _entities(analysis)
    for key in ("major_name", "program_name", "parent_major"):
        value = str(entities.get(key) or "").strip()
        if value:
            return value
    candidates = _candidate_names(analysis)
    return candidates[0] if len(candidates) == 1 else None


def _evidence_available(evidence: object | None) -> bool:
    if evidence is None:
        return True
    usable = _field(evidence, "is_usable", None)
    if usable is not None:
        return bool(usable)
    chunks = _field(evidence, "chunks", ())
    context = str(_field(evidence, "context", "") or "").strip()
    sources = _field(evidence, "sources", ())
    return bool(chunks and context and sources)


def _has_multiple_choices(analysis: object) -> bool:
    candidates = _candidate_names(analysis)
    if len(candidates) > 1:
        return True
    entities = _entities(analysis)
    # The extractor keeps the first canonical name in major_name and all names
    # in candidate_majors. This fallback also supports hand-built analyses in
    # tests and adapters.
    major_names = _as_names(entities.get("major_names"))
    distinct = {
        normalized
        for name in (*candidates, *major_names)
        if (normalized := normalize_question(name))
    }
    return len(distinct) > 1


def _catalog_operation(analysis: object) -> str:
    return str(_entities(analysis).get("catalog_operation") or "").upper()


def choose_answer_mode(
    analysis: object,
    *,
    status: str = "ok",
    evidence: object | None = None,
    deterministic: bool = False,
) -> str:
    """Chọn mode theo intent, ngôn ngữ câu hỏi và trạng thái evidence."""

    intent = _intent(analysis)
    normalized = _normalized(analysis)
    needs_clarification = bool(_field(analysis, "needs_clarification", False))

    if intent == "OUT_OF_SCOPE" or status == "out_of_scope":
        return "OUT_OF_SCOPE"
    if intent in _SYSTEM_INTENTS:
        return "DIRECT_SHORT" if intent != "SYSTEM_SCOPE" else "EXPLANATION"
    score_question = any(marker in normalized for marker in ("bao nhieu diem", "lay bao nhieu diem", "diem nao"))
    score_type = _entities(analysis).get("score_type")
    if needs_clarification or status == "clarification" or (
        score_question
        and not score_type
        and intent in {"HOI_NGANH", "HOI_CHUONG_TRINH", "HOI_NGUONG_DAU_VAO"}
    ):
        return "CLARIFICATION"
    if status in _NO_EVIDENCE_STATUSES or (evidence is not None and not _evidence_available(evidence)):
        return "NO_DATA"
    if intent == "TU_VAN_CHON_NGANH":
        return "RECOMMENDATION"
    if intent == "MULTI_ISSUE":
        return "EXPLANATION"
    if intent == "SCHOOL_INFO":
        return "OVERVIEW"
    if intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}:
        count_only_major = (
            intent == "DANH_SACH_NGANH"
            and any(
                marker in normalized
                for marker in (
                    "bao nhieu nganh",
                    "nhieu nganh",
                    "bao nhiu nganh",
                    "nhiu nganh",
                    "may nganh",
                    "so luong nganh",
                    "tong so nganh",
                    "co bao nhieu",
                    "co nhieu",
                    "co may",
                )
            )
            and not any(
                marker in normalized
                for marker in (
                    "danh sach",
                    "liet ke",
                    "liet ra",
                    "cac nganh",
                    "nhung nganh",
                    "nganh nao",
                    "nganh gi",
                )
            )
        )
        return "DIRECT_SHORT" if _catalog_operation(analysis) == "COUNT" or count_only_major else "TABLE"
    if _has_multiple_choices(analysis) and any(marker in normalized for marker in _COMPARISON_MARKERS):
        return "COMPARISON"
    if intent in _STEP_INTENTS:
        return "STEP_BY_STEP"
    if intent == "HOI_CACH_TINH_DIEM":
        return "EXPLANATION"
    if intent == "HOI_HOC_BONG":
        return "EXPLANATION"
    if any(marker in normalized for marker in _OVERVIEW_MARKERS):
        return "OVERVIEW"
    if intent in _SIMPLE_INTENTS:
        return "DIRECT_SHORT"
    if any(marker in normalized for marker in _TABLE_MARKERS) and _has_multiple_choices(analysis):
        return "TABLE"
    if deterministic:
        return "DIRECT_SHORT"
    return "EXPLANATION"


def _response_format(mode: str) -> str:
    return {
        "DIRECT_SHORT": "short_paragraph",
        "EXPLANATION": "short_paragraphs",
        "OVERVIEW": "overview_with_bullets",
        "COMPARISON": "comparison_table_or_bullets",
        "TABLE": "markdown_table_or_numbered_list",
        "STEP_BY_STEP": "numbered_steps",
        "RECOMMENDATION": "conditional_advice_with_comparison",
        "CLARIFICATION": "one_clarifying_question",
        "NO_DATA": "fixed_no_data_message",
        "OUT_OF_SCOPE": "fixed_scope_message",
    }[mode]


def _sections(mode: str) -> tuple[str, ...]:
    if mode == "OVERVIEW":
        return ("answer", "key_points", "next_question")
    if mode == "COMPARISON":
        return ("comparison_basis", "option_a", "option_b", "next_question")
    if mode == "TABLE":
        return ("intro", "structured_rows", "next_question")
    if mode == "STEP_BY_STEP":
        return ("brief_answer", "ordered_steps", "caveat_or_next_step")
    if mode == "RECOMMENDATION":
        return ("conditional_recommendation", "evidence_comparison", "next_question")
    if mode == "EXPLANATION":
        return ("direct_answer", "explanation", "next_question")
    if mode in {"CLARIFICATION", "NO_DATA", "OUT_OF_SCOPE"}:
        return ("answer",)
    return ("answer", "next_question")


def _required_content(mode: str, intent: str) -> tuple[str, ...]:
    if mode == "COMPARISON":
        return ("mention_each_requested_option", "use_only_selected_evidence")
    if mode == "RECOMMENDATION":
        return ("state_advice_conditionally", "do_not_decide_admission", "mention_each_candidate")
    if mode == "TABLE":
        return ("preserve_structured_rows", "do_not_invent_columns_or_values")
    if mode == "STEP_BY_STEP":
        return ("preserve_step_order", "keep_deadlines_and_documents_separate")
    if intent in {"HOI_NGUONG_DAU_VAO", "HOI_DIEM_TRUNG_TUYEN", "HOI_XET_TUYEN_BO_SUNG"}:
        return ("preserve_score_type_and_method", "do_not_claim_pass_or_fail")
    if intent == "HOI_HOC_PHI":
        return ("preserve_tuition_label", "separate_total_cost")
    if intent == "HOI_HOC_BONG":
        return ("preserve_scholarship_conditions", "keep_each_policy_separate")
    return ()


def related_questions_for(
    analysis: object, *, limit: int = 6, status: str = "ok"
) -> tuple[str, ...]:
    """Tạo nhóm follow-up theo câu hỏi, entity và trạng thái dữ liệu."""

    if limit <= 0:
        return ()
    intent = _intent(analysis)
    year = str(_entities(analysis).get("year") or 2026)
    normalized = _normalized(analysis)
    topic = _major_or_program(analysis)
    candidates = _candidate_names(analysis)
    combination = str(_entities(analysis).get("admission_combination") or "").strip().upper()
    has_student_score = bool(_entities(analysis).get("student_scores"))
    suggestions: list[str] = []

    def add(question: str) -> None:
        question = question.strip()
        if question and question not in suggestions and "http://" not in question and "https://" not in question:
            suggestions.append(question)

    if status == "clarification":
        if "diem" in normalized or intent in {
            "HOI_NGUONG_DAU_VAO",
            "HOI_DIEM_TRUNG_TUYEN",
            "HOI_XET_TUYEN_BO_SUNG",
        }:
            add(f"Điểm sàn DHV năm {year} là bao nhiêu?")
            add(f"Điểm trúng tuyển DHV năm {year} là bao nhiêu?")
            add(f"DHV có thông tin xét tuyển bổ sung năm {year} không?")
        elif intent in {"HOI_NGANH", "HOI_CHUONG_TRINH", "TU_VAN_CHON_NGANH"}:
            add("Bạn đang quan tâm đến ngành hoặc chương trình nào của DHV?")
            add("Bạn thích lĩnh vực kinh tế, truyền thông, quản trị hay công nghệ?")
            add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        else:
            add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
            add(f"Các phương thức xét tuyển DHV năm {year} gồm những gì?")
            add(f"Học phí DHV năm {year} được tính như thế nào?")
        return tuple(suggestions[:limit])

    if intent in {"OUT_OF_SCOPE", "NO_DATA"}:
        # Even when the request is outside the corpus or too vague to classify,
        # offer safe DHV topics the assistant can actually handle.
        add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        add(f"Các phương thức xét tuyển DHV năm {year} gồm những gì?")
        add(f"Học phí và học bổng DHV năm {year} có thông tin gì?")
        add(f"Hồ sơ xét tuyển DHV năm {year} cần chuẩn bị gì?")
        return tuple(suggestions[:limit])
    if intent == "GREETING":
        add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        add(f"Các phương thức xét tuyển DHV {year} gồm những gì?")
        add(f"Học phí và học bổng DHV {year} có thông tin gì?")
        add(f"Hồ sơ xét tuyển DHV {year} cần chuẩn bị gì?")
    elif intent == "SYSTEM_IDENTITY":
        add("Bạn hỗ trợ những nội dung tuyển sinh nào của DHV?")
        add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        add(f"Học phí và học bổng DHV {year} có thông tin gì?")
    elif intent == "SYSTEM_SCOPE":
        add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        add(f"Học phí DHV {year} được công bố như thế nào?")
        add(f"Các phương thức xét tuyển DHV {year} gồm những gì?")
        add(f"Học bổng tuyển sinh DHV {year} có những điều kiện nào?")
    elif intent == "MULTI_ISSUE":
        add(f"DHV hiện có những ngành đào tạo nào năm {year}?")
        add(f"Các phương thức xét tuyển DHV {year} gồm những gì?")
        add("Hồ sơ xét tuyển DHV gồm những gì?")
        add(f"Học phí các ngành DHV {year} được tính như thế nào?")
        add(f"Học bổng tuyển sinh DHV {year} có những điều kiện nào?")
    elif intent in {"HOI_NGANH", "HOI_CHUONG_TRINH"} and _has_multiple_choices(analysis) and any(
        marker in normalized for marker in _COMPARISON_MARKERS
    ):
        add(f"Mình có thể so sánh {' và '.join(candidates[:2])} theo cùng tiêu chí không?")
        add("Các chương trình đào tạo thuộc từng lựa chọn là gì?")
        add(f"Các phương thức xét tuyển DHV {year} gồm những gì?")
    elif intent == "DANH_SACH_NGANH":
        asks_count = _catalog_operation(analysis) == "COUNT" or any(
            marker in normalized
            for marker in ("bao nhieu nganh", "bao nhiu nganh", "may nganh", "so luong nganh", "tong so nganh")
        )
        if asks_count:
            add("Bạn muốn xem danh sách đầy đủ các ngành DHV không?")
            add(f"Các ngành DHV xét tuyển theo tổ hợp nào năm {year}?")
            add("Bạn đang quan tâm nhóm ngành nào để mình tư vấn sát hơn?")
            add(f"DHV có những chương trình đào tạo nào năm {year}?")
            add(f"Điều kiện xét tuyển vào các ngành DHV năm {year} là gì?")
            add("Mình có thể gợi ý ngành theo sở thích và tổ hợp môn của bạn không?")
        else:
            add("Bạn muốn tìm hiểu sâu về ngành nào trong danh sách?")
            add(f"Các ngành DHV xét tuyển theo tổ hợp nào năm {year}?")
            add(f"DHV có những chương trình đào tạo nào năm {year}?")
            add("Bạn đang quan tâm nhóm ngành nào để mình tư vấn sát hơn?")
            add(f"Điều kiện xét tuyển vào các ngành DHV năm {year} là gì?")
            add("Mình có thể gợi ý ngành theo sở thích và tổ hợp môn của bạn không?")
    elif intent == "DANH_SACH_CHUONG_TRINH":
        add("Bạn muốn tìm hiểu chương trình thuộc ngành nào?")
        if topic:
            add(f"Ngành {topic} có những chương trình đào tạo nào?")
            add(f"Các chương trình của ngành {topic} học những nội dung gì?")
        add(f"Các ngành DHV xét tuyển theo tổ hợp nào năm {year}?")
        add("Bạn đang quan tâm lĩnh vực nào để mình gợi ý chương trình phù hợp?")
    elif intent == "TU_VAN_CHON_NGANH":
        if combination:
            add(f"DHV có những ngành nào xét tổ hợp {combination} năm {year}?")
        if has_student_score:
            add(f"Có thể dùng điểm học bạ để xét tuyển DHV năm {year} không?")
        if candidates:
            add(f"Mình có thể so sánh nội dung học của {' và '.join(candidates[:2])} không?")
        add("Các phương thức xét tuyển của lựa chọn này là gì?")
        add(f"Học phí và học bổng DHV {year} có những gì cần biết?")
        add("Điểm sàn và điểm chuẩn khác nhau như thế nào?")
    elif intent in {"HOI_NGANH", "HOI_CHUONG_TRINH"} and topic:
        add(f"{topic} có những chương trình đào tạo nào?")
        add(f"{topic} xét tuyển theo phương thức nào năm {year}?")
        add(f"Học phí và học bổng DHV {year} có những thông tin nào?")
        add(f"{topic} có những tổ hợp xét tuyển nào năm {year}?")
        add(f"Điều kiện xét tuyển ngành {topic} năm {year} là gì?")
    elif intent == "HOI_HOC_PHI":
        add(f"DHV có những học bổng nào cho tân sinh viên {year}?")
        add(f"Học phí học kỳ I DHV {year} gồm những khoản nào?")
        add("Cách đóng học phí tại DHV như thế nào?")
        add(f"Học phí DHV {year} có thể thay đổi theo năm học không?")
        if topic:
            add(f"Học bổng nào có thể hỗ trợ học phí ngành {topic}?")
    elif intent == "HOI_HOC_BONG":
        add(f"Học phí học kỳ I DHV {year} là bao nhiêu?")
        add(f"Điều kiện của các học bổng DHV {year} gồm những gì?")
        add(f"Hồ sơ xét học bổng DHV {year} cần chuẩn bị gì?")
        add(f"Học bổng tuyển sinh DHV {year} được xét theo phương thức nào?")
        add("Có thể nhận tư vấn về học bổng ở đâu?")
    elif intent in _STEP_INTENTS:
        add(f"Các mốc tuyển sinh DHV {year} là gì?")
        add(f"Học phí và học bổng DHV {year} có những thông tin nào?")
        add(f"Các phương thức xét tuyển DHV {year} gồm những gì?")
        add("Nộp hồ sơ trực tuyến tại cổng nào của DHV?")
        add("Nếu thiếu giấy tờ thì cần xử lý thế nào?")
    elif intent in {"HOI_NGUONG_DAU_VAO", "HOI_DIEM_TRUNG_TUYEN", "HOI_XET_TUYEN_BO_SUNG"}:
        add(f"DHV có những phương thức xét tuyển nào năm {year}?")
        add("Cách tính điểm xét tuyển được công bố ra sao?")
        if combination:
            add(f"Những ngành nào tại DHV xét tổ hợp {combination} năm {year}?")
        if has_student_score:
            add(f"Có thể xét học bạ song song với điểm thi năm {year} không?")
        add("Điểm sàn và điểm chuẩn khác nhau như thế nào?")
    elif "so sanh" in normalized and candidates:
        add(f"Các chương trình thuộc {' và '.join(candidates[:2])} là gì?")
        add(f"Học phí và học bổng DHV {year} có những thông tin nào?")

    return tuple(suggestions[:limit])


def plan_answer(
    analysis: object,
    evidence: object | None = None,
    *,
    status: str = "ok",
    deterministic: bool = False,
    related_limit: int = 6,
) -> AnswerPlan:
    """Tạo AnswerPlan để trace, prompt và UI dùng chung một contract."""

    intent = _intent(analysis)
    mode = choose_answer_mode(
        analysis,
        status=status,
        evidence=evidence,
        deterministic=deterministic,
    )
    followup_status = status
    if mode == "CLARIFICATION":
        followup_status = "clarification"
    elif mode == "OUT_OF_SCOPE":
        followup_status = "out_of_scope"
    elif mode == "NO_DATA" and status == "ok":
        followup_status = "no_data"
    related = related_questions_for(
        analysis,
        limit=related_limit,
        status=followup_status,
    )
    reason = {
        "DIRECT_SHORT": "single_fact_or_deterministic_short_answer",
        "EXPLANATION": "explain_multiple_or_process_related_facts",
        "OVERVIEW": "explicit_broad_overview_request",
        "COMPARISON": "multiple_requested_options_need_side_by_side_view",
        "TABLE": "structured_list_or_comparable_rows",
        "STEP_BY_STEP": "procedural_admissions_question",
        "RECOMMENDATION": "bounded_interest_or_choice_counselling",
        "CLARIFICATION": "question_needs_user_choice_before_retrieval",
        "NO_DATA": "evidence_or_verified_rule_is_unavailable",
        "OUT_OF_SCOPE": "question_is_outside_admissions_scope",
    }[mode]
    return AnswerPlan(
        mode=mode,
        intent=intent,
        response_format=_response_format(mode),
        lead_with={
            "DIRECT_SHORT": "direct_answer",
            "EXPLANATION": "direct_answer_then_context",
            "OVERVIEW": "one_sentence_overview",
            "COMPARISON": "comparison_basis",
            "TABLE": "short_intro_then_rows",
            "STEP_BY_STEP": "first_action",
            "RECOMMENDATION": "conditional_recommendation",
            "CLARIFICATION": "clarifying_question",
            "NO_DATA": "no_data_boundary",
            "OUT_OF_SCOPE": "scope_boundary",
        }[mode],
        sections=_sections(mode),
        required_content=_required_content(mode, intent),
        related_questions=related,
        evidence_required=(
            intent not in _SYSTEM_INTENTS
            and mode not in {"CLARIFICATION", "NO_DATA", "OUT_OF_SCOPE"}
        ),
        deterministic=deterministic,
        reason=reason,
    )


# Explicit aliases keep the module convenient without introducing another
# planner owner.
build_answer_plan = plan_answer
select_answer_mode = choose_answer_mode
suggest_related_questions = related_questions_for


class AnswerPlanner:
    """Facade mỏng cho các caller thích dùng planner dạng object."""

    def plan(
        self,
        analysis: object,
        evidence: object | None = None,
        *,
        status: str = "ok",
        deterministic: bool = False,
        related_limit: int = 6,
    ) -> AnswerPlan:
        return plan_answer(
            analysis,
            evidence,
            status=status,
            deterministic=deterministic,
            related_limit=related_limit,
        )

    def choose_mode(
        self,
        analysis: object,
        *,
        status: str = "ok",
        evidence: object | None = None,
        deterministic: bool = False,
    ) -> str:
        return choose_answer_mode(
            analysis,
            status=status,
            evidence=evidence,
            deterministic=deterministic,
        )

    def related_questions(self, analysis: object, *, limit: int = 6) -> tuple[str, ...]:
        return related_questions_for(analysis, limit=limit)


__all__ = [
    "ANSWER_MODES",
    "ANSWER_PLANNER_MODES",
    "CATALOG_LIST",
    "CLARIFICATION",
    "COMPARISON",
    "DIRECT_SHORT",
    "EXPLANATION",
    "NO_DATA",
    "OUT_OF_SCOPE",
    "OVERVIEW",
    "RECOMMENDATION",
    "STEP_BY_STEP",
    "TABLE",
    "AnswerPlanner",
    "AnswerPlan",
    "PLANNER_MODES",
    "build_answer_plan",
    "choose_answer_mode",
    "plan_answer",
    "related_questions_for",
    "select_answer_mode",
    "suggest_related_questions",
]
