"""Question normalization, intent/entity extraction and conversation slots.

The module deliberately contains no admissions facts or answer text.  It only
turns natural-language input into a small, bounded representation that the
router and RAG prompt can consume.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence


INTENTS = (
    "HOI_NGANH",
    "HOI_CHUONG_TRINH",
    "HOI_NGUONG_DAU_VAO",
    "HOI_DIEM_TRUNG_TUYEN",
    "HOI_XET_TUYEN_BO_SUNG",
    "HOI_HOC_PHI",
    "HOI_HOC_BONG",
    "HOI_HO_SO",
    "HOI_LICH_TUYEN_SINH",
    "HOI_NHAP_HOC",
    "HOI_PHUONG_THUC_XET_TUYEN",
    "HOI_CACH_TINH_DIEM",
    "HOI_DANG_KY_XET_TUYEN",
    "HOI_CO_SO_LIEN_HE",
    "TU_VAN_CHON_NGANH",
    "DANH_SACH_NGANH",
    "DANH_SACH_CHUONG_TRINH",
    "OUT_OF_SCOPE",
)

APPLICATION_THRESHOLD = "application_threshold"
ADMISSION_SCORE = "admission_score"
SUPPLEMENTARY_THRESHOLD = "supplementary_threshold"

CATALOG_LIST = "LIST"
CATALOG_COUNT = "COUNT"
CATALOG_LIST_AND_COUNT = "LIST_AND_COUNT"

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_CODE_RE = re.compile(r"\b(\d{7})\b")
_DECIMAL_RE = r"\d+(?:[.,]\d+)?"
_SCORE_RE = re.compile(rf"(?<!\w)({_DECIMAL_RE})\s*(?:điểm|diem)\b", re.IGNORECASE)
_SUBJECT_SCORE_RE = re.compile(
    rf"\b(toán|toan|văn|van|ngữ văn|ngu van|anh|tiếng anh|tieng anh)\s*[:=]?\s*({_DECIMAL_RE})",
    re.IGNORECASE,
)
_DGNL_SCORE_RE = re.compile(
    rf"(?:đgnl|dgnl|đánh giá năng lực|danh gia nang luc)[^\d]{{0,12}}({_DECIMAL_RE})",
    re.IGNORECASE,
)

_MAJOR_ALIASES = (
    ("quan tri kinh doanh", "Quản trị kinh doanh"),
    ("qtkd", "Quản trị kinh doanh"),
    ("kinh te quoc te", "Kinh tế quốc tế"),
    ("marketing", "Marketing"),
    ("thuong mai dien tu", "Thương mại điện tử"),
    ("tmdt", "Thương mại điện tử"),
    ("tai chinh ngan hang", "Tài chính ngân hàng"),
    ("tai chinh - ngan hang", "Tài chính ngân hàng"),
    ("tcnh", "Tài chính ngân hàng"),
    ("ke toan", "Kế toán"),
    ("cong nghe tai chinh", "Công nghệ tài chính"),
    ("luat kinh te", "Luật Kinh tế"),
    ("cong nghe thong tin", "Công nghệ thông tin"),
    ("cntt", "Công nghệ thông tin"),
    ("ky thuat may tinh", "Kỹ thuật máy tính"),
    ("ktmt", "Kỹ thuật máy tính"),
    ("tri tue nhan tao", "Trí tuệ nhân tạo"),
    ("ngon ngu anh", "Ngôn ngữ Anh"),
    ("ngon ngu nhat", "Ngôn ngữ Nhật"),
    ("ngon ngu trung quoc", "Ngôn ngữ Trung Quốc"),
    ("ngon ngu trung", "Ngôn ngữ Trung Quốc"),
    ("ngon ngu han quoc", "Ngôn ngữ Hàn Quốc"),
    ("ngon ngu han", "Ngôn ngữ Hàn Quốc"),
    ("quan tri khach san", "Quản trị Khách sạn"),
    ("quan tri dich vu du lich & lu hanh", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("quan tri dich vu du lich va lu hanh", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("quan tri du lich lu hanh", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("qlbv", "Quản lý bệnh viện"),
    ("quan ly benh vien", "Quản lý bệnh viện"),
    ("tam ly hoc", "Tâm lý học"),
    ("luat", "Luật"),
)
_PROGRAM_ALIASES = (
    ("cong nghe tai chinh", "Công nghệ tài chính"),
    ("quan tri khach san", "Quản trị khách sạn"),
    ("quan tri kinh doanh tong hop", "Quản trị Kinh doanh tổng hợp"),
    ("quan tri nguon nhan luc", "Quản trị Nguồn nhân lực"),
    ("quan tri logistics", "Quản trị Logistics"),
    ("khoi nghiep va phat trien ben vung", "Khởi nghiệp và Phát triển bền vững"),
    ("quan tri cong nghe va doi moi sang tao", "Quản trị công nghệ và Đổi mới sáng tạo"),
    ("quan tri marketing", "Quản trị Marketing"),
    ("digital marketing", "Digital Marketing"),
    ("truyen thong va quan he cong chung", "Truyền thông và quan hệ công chúng"),
    ("truyen thong so", "Truyền thông số"),
    ("quan tri thuong mai dien tu", "Quản trị thương mại điện tử"),
    ("kinh doanh so", "Kinh doanh số"),
    ("phan tich du lieu kinh doanh", "Phân tích dữ liệu kinh doanh"),
    ("ngan hang so", "Ngân hàng số"),
    ("tai chinh doanh nghiep", "Tài chính doanh nghiệp"),
    ("ke toan doanh nghiep", "Kế toán doanh nghiệp"),
    ("ke toan so", "Kế toán số"),
    ("khai pha du lieu tai chinh", "Khai phá dữ liệu tài chính"),
    ("he thong nhung thong minh", "Hệ thống nhúng thông minh"),
    ("ai va iot ung dung", "AI và IoT ứng dụng"),
    ("truyen thong da phuong tien", "Truyền thông đa phương tiện"),
    ("cong nghe phan mem", "Công nghệ phần mềm"),
    ("lap trinh ai", "Lập trình AI"),
    ("an ninh mang va he thong", "An ninh mạng và hệ thống"),
    ("phan tich du lieu lon", "Phân tích dữ liệu lớn"),
    ("giang day tieng anh", "Giảng dạy Tiếng Anh"),
    ("tieng anh thuong mai", "Tiếng Anh Thương mại"),
    ("tieng nhat thuong mai", "Tiếng Nhật thương mại"),
    ("ngon ngu - van hoa nhat ban", "Ngôn ngữ - Văn hóa Nhật Bản"),
    ("ngon ngu van hoa nhat ban", "Ngôn ngữ - Văn hóa Nhật Bản"),
    ("tieng trung thuong mai", "Tiếng Trung thương mại"),
    ("tieng trung hanh chinh van phong", "Tiếng Trung hành chính văn phòng"),
    ("giang day tieng trung", "Giảng dạy Tiếng Trung"),
    ("tieng trung van hoa - du lich", "Tiếng Trung Văn hóa - Du lịch"),
    ("tieng trung van hoa du lich", "Tiếng Trung Văn hóa - Du lịch"),
    ("giang day tieng han", "Giảng dạy Tiếng Hàn"),
    ("tieng han thuong mai", "Tiếng Hàn thương mại"),
    ("quan tri nha hang va dich vu am thuc", "Quản trị nhà hàng và dịch vụ ẩm thực"),
    ("quan tri lu hanh", "Quản trị lữ hành"),
    ("quan ly giai tri", "Quản lý giải trí"),
    ("quan tri su kien", "Quản trị sự kiện"),
    ("quan ly chat luong benh vien", "Quản lý chất lượng bệnh viện"),
    ("quan ly tai chinh benh vien", "Quản lý tài chính bệnh viện"),
    ("quan ly trang thiet bi y te", "Quản lý trang thiết bị y tế"),
    ("tam ly hoc duong", "Tâm lý học đường"),
    ("tam ly lam sang", "Tâm lý lâm sàng"),
    ("tam ly to chuc - nhan su", "Tâm lý tổ chức - Nhân sự"),
    ("tam ly to chuc nhan su", "Tâm lý tổ chức - Nhân sự"),
    ("ung dung ai trong tam ly", "Ứng dụng AI trong tâm lý"),
)
_MAX_CANDIDATES = 8
_MAX_LISTED_MAJORS = 24
_PROGRAM_CATALOG_TERMS = ("chuong trinh", "chuyen nganh")


def normalize_question(value: str) -> str:
    """Normalize spacing and accents for matching while keeping no history."""

    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    folded = folded.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", folded).strip()


def _number(value: str) -> int | float:
    parsed = float(value.replace(",", "."))
    return int(parsed) if parsed.is_integer() else parsed


@dataclass(frozen=True)
class ConversationState:
    """Bounded per-session slots; no unbounded message history is stored here."""

    current_year: int = 2026
    current_major: str | None = None
    current_program: str | None = None
    current_method: str | None = None
    current_score_type: str | None = None
    student_scores: dict[str, object] = field(default_factory=dict)
    interest: str | None = None
    candidate_majors: tuple[str, ...] = ()
    candidate_programs: tuple[str, ...] = ()
    last_listed_majors: tuple[str, ...] = ()
    last_list_count: int = 0
    previous_intent: str | None = None
    turn_count: int = 0

    @classmethod
    def from_value(cls, value: object, *, default_year: int = 2026) -> "ConversationState":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            return cls(current_year=default_year)
        scores = value.get("student_scores")
        return cls(
            current_year=_safe_int(value.get("current_year"), default_year),
            current_major=_safe_str(value.get("current_major")),
            current_program=_safe_str(value.get("current_program")),
            current_method=_safe_str(value.get("current_method")),
            current_score_type=_safe_str(value.get("current_score_type")),
            student_scores=dict(scores) if isinstance(scores, Mapping) else {},
            interest=_safe_str(value.get("interest")),
            candidate_majors=_safe_str_tuple(value.get("candidate_majors")),
            candidate_programs=_safe_str_tuple(value.get("candidate_programs")),
            last_listed_majors=_safe_str_tuple(
                value.get("last_listed_majors"), limit=_MAX_LISTED_MAJORS
            ),
            last_list_count=max(0, _safe_int(value.get("last_list_count"), 0)),
            previous_intent=_safe_str(value.get("previous_intent")),
            turn_count=max(0, _safe_int(value.get("turn_count"), 0)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "current_year": self.current_year,
            "current_major": self.current_major,
            "current_program": self.current_program,
            "current_method": self.current_method,
            "current_score_type": self.current_score_type,
            "student_scores": dict(self.student_scores),
            "interest": self.interest,
            "candidate_majors": list(self.candidate_majors),
            "candidate_programs": list(self.candidate_programs),
            "last_listed_majors": list(self.last_listed_majors),
            "last_list_count": self.last_list_count,
            "previous_intent": self.previous_intent,
            "turn_count": self.turn_count,
        }


@dataclass(frozen=True)
class QueryAnalysis:
    """Structured interpretation of one normalized user turn."""

    question: str
    normalized_question: str
    intent: str
    entities: dict[str, object]
    needs_clarification: bool = False
    clarification_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "normalized_question": self.normalized_question,
            "intent": self.intent,
            "entities": dict(self.entities),
            "needs_clarification": self.needs_clarification,
            "clarification_reason": self.clarification_reason,
        }


@dataclass(frozen=True)
class QueryPlan:
    """Router output used by retrieval and generation."""

    intent: str
    categories: tuple[str, ...]
    retrieval_query: str
    metadata_filter: dict[str, object]
    needs_clarification: bool = False
    clarification_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "categories": list(self.categories),
            "retrieval_query": self.retrieval_query,
            "metadata_filter": self.metadata_filter,
            "needs_clarification": self.needs_clarification,
            "clarification_reason": self.clarification_reason,
        }


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _safe_str_tuple(value: object, *, limit: int = _MAX_CANDIDATES) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    result: list[str] = []
    for item in value:
        text = _safe_str(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return tuple(result)


def _has_multiple_candidates(entities: Mapping[str, object]) -> bool:
    values: list[str] = []
    for key in ("candidate_majors", "candidate_programs"):
        candidates = entities.get(key)
        if not isinstance(candidates, Sequence) or isinstance(candidates, str):
            continue
        for candidate in candidates:
            text = str(candidate).strip()
            if text and text not in values:
                values.append(text)
    return len(values) > 1


def _has_explicit_choice(normalized: str) -> bool:
    """Return whether an advisory turn explicitly commits to one option."""

    return bool(
        re.search(
            r"\b(?:toi|minh)\s+(?:da\s+)?(?:chon|quyet dinh chon)\b"
            r"|\bchon\s+(?:nganh|chuong trinh)\s+[^,.;]+$",
            normalized,
        )
    )


def _clear_ambiguous_advisory_entities(
    entities: dict[str, object],
    normalized: str,
    intent: str,
) -> None:
    """Keep mentions as candidates without promoting one to a resolved slot."""

    if intent != "TU_VAN_CHON_NGANH" or _has_explicit_choice(normalized):
        return
    if not _has_multiple_candidates(entities):
        return
    entities["major_name"] = None
    entities["major_code"] = None
    entities["program_name"] = None
    entities["parent_major"] = None
    entities["entity_type"] = "ambiguous"


def _extract_interest(normalized: str) -> str | None:
    match = re.search(
        r"\b(?:so thich|thich|quan tam|yeu thich)\s*(?::|la)?\s*"
        r"(.+?)(?=\s*(?:,|\.|nhung|chua|va chua|nen chon|chon nganh|$))",
        normalized,
    )
    if not match:
        return None
    value = match.group(1).strip(" ,")
    return value or None


def _extract_scores(normalized: str) -> tuple[dict[str, object], dict[str, object] | None]:
    scores: dict[str, object] = {}
    subjects: dict[str, object] = {}
    for match in _SUBJECT_SCORE_RE.finditer(normalized):
        label = match.group(1).replace(" ", "_")
        label = {"toan": "toan", "van": "van", "ngu_van": "van", "anh": "anh", "tieng_anh": "anh"}.get(label, label)
        subjects[label] = _number(match.group(2))
    if subjects:
        scores["thpt_subjects"] = subjects

    dgnl = _DGNL_SCORE_RE.search(normalized)
    if dgnl:
        scores["dgnl"] = _number(dgnl.group(1))

    standalone = [
        _number(match.group(1))
        for match in _SCORE_RE.finditer(normalized)
        if not (match.start() > 0 and normalized[match.start() - 1].isalnum())
    ]
    if standalone and not subjects and "dgnl" not in scores:
        scores["unspecified"] = standalone[0]

    return scores, (dict(scores) if scores else None)


def _catalog_operation(normalized: str) -> str | None:
    """Recognize program-catalog language, including the common alias ``chuyên ngành``.

    The classifier deliberately requires a catalog/request marker so a question
    such as ``chương trình thuộc ngành nào`` remains an entity question rather
    than becoming a catalog listing.
    """

    if not any(term in normalized for term in _PROGRAM_CATALOG_TERMS):
        return None

    count_requested = bool(
        re.search(
            r"\b(?:bao nhieu|may|so luong)\b.{0,32}\b(?:chuong trinh|chuyen nganh)\b",
            normalized,
        )
        or re.search(
            r"\b(?:chuong trinh|chuyen nganh)\b.{0,32}\b(?:bao nhieu|may|so luong)\b",
            normalized,
        )
    )
    list_requested = any(
        marker in normalized
        for marker in (
            "danh sach",
            "liet ke",
            "liet ra",
            "co nhung",
            "nhung",
            "cac",
            "gom",
            "nao",
            "chuong trinh cua",
            "chuyen nganh cua",
        )
    )
    if count_requested and list_requested:
        return CATALOG_LIST_AND_COUNT
    if count_requested:
        return CATALOG_COUNT
    if list_requested:
        return CATALOG_LIST
    return None


def _is_global_catalog_request(normalized: str) -> bool:
    """Whether a catalog request explicitly asks for the whole catalog."""

    return bool(
        re.search(r"\b(?:tat ca|toan bo)\b", normalized)
        or "toan truong" in normalized
    )


def _extract_entities(normalized: str, state: ConversationState) -> dict[str, object]:
    year_match = _YEAR_RE.search(normalized)
    year = int(year_match.group(1)) if year_match else state.current_year
    code_match = _CODE_RE.search(normalized)
    major_code = code_match.group(1) if code_match else None

    program_alias_matches = [
        (alias, canonical)
        for alias, canonical in _PROGRAM_ALIASES
        if re.search(rf"\b{re.escape(alias)}\b", normalized)
    ]
    major_names = _safe_str_tuple(
        [
            canonical
            for alias, canonical in _MAJOR_ALIASES
            if re.search(rf"\b{re.escape(alias)}\b", normalized)
        ]
    )
    # A verified program may share its display name with its parent major. In
    # ordinary major/catalog questions the major interpretation wins; only an
    # explicit relation question keeps the same-name row as a program entity.
    explicit_program_relation = bool(re.search(r"\bthuoc\s+nganh\b", normalized))
    if not explicit_program_relation:
        major_names_normalized = {normalize_question(name) for name in major_names}
        program_alias_matches = [
            (alias, canonical)
            for alias, canonical in program_alias_matches
            if normalize_question(canonical) not in major_names_normalized
        ]
    program_names = _safe_str_tuple([canonical for _, canonical in program_alias_matches])
    program_name = program_names[0] if program_names else None
    major_name = major_names[0] if major_names else None
    # A major next to a program can be an alternative choice, not the
    # program's parent. Resolve that relationship from evidence later.
    parent_major = None
    admission_method = None
    if "dgnl" in normalized or "danh gia nang luc" in normalized:
        admission_method = "dgnl"
    elif "hoc ba" in normalized or "hoc tap thpt" in normalized:
        admission_method = "hoc_ba"
    elif "tot nghiep thpt" in normalized or "thi thpt" in normalized or re.search(r"\bthpt\b", normalized):
        admission_method = "thpt"
    elif re.search(r"phuong thuc\s*1\b", normalized):
        admission_method = "thpt"
    elif re.search(r"phuong thuc\s*2\b", normalized):
        admission_method = "hoc_ba"

    score_type = None
    if "xet tuyen bo sung" in normalized or "tuyen sinh bo sung" in normalized:
        score_type = SUPPLEMENTARY_THRESHOLD
    elif any(term in normalized for term in ("diem trung tuyen", "diem chuan")) or re.search(r"\bdiem dau(?!\s+vao)\b", normalized):
        score_type = ADMISSION_SCORE
    elif any(term in normalized for term in ("diem san", "nguong dau vao", "diem dau vao", "diem nhan ho so", "duoc dang ky")):
        score_type = APPLICATION_THRESHOLD

    score_facts, score_value = _extract_scores(normalized)
    catalog_operation = _catalog_operation(normalized)
    entity_type = "program" if program_name else ("major" if major_name or major_code else None)
    return {
        "year": year,
        "major_name": major_name,
        "candidate_majors": list(major_names),
        "major_code": major_code,
        "program_name": program_name,
        "candidate_programs": list(program_names),
        "parent_major": parent_major,
        "entity_type": entity_type,
        "admission_method": admission_method,
        "score_type": score_type,
        "score_value": score_value,
        "student_scores": score_facts,
        "interest": _extract_interest(normalized),
        "catalog_operation": catalog_operation,
        "requested_information": [],
    }


def _classify_intent(normalized: str, entities: dict[str, object], state: ConversationState) -> str:
    advisory = any(term in normalized for term in ("chon nganh", "chua biet chon", "phan van", "nen hoc nganh", "nen chon"))
    if advisory or (entities.get("interest") and entities.get("student_scores")):
        return "TU_VAN_CHON_NGANH"
    # Keep enrollment confirmation distinct from applying for admission.
    if (
        "xac nhan nhap hoc" in normalized
        or (
            "nhap hoc" in normalized
            and not any(term in normalized for term in ("ho so", "giay to", "thu tuc"))
        )
    ):
        return "HOI_NHAP_HOC"
    if (
        "phuong thuc" in normalized
        or "hinh thuc xet tuyen" in normalized
        or "to hop xet tuyen" in normalized
        or "to hop mon" in normalized
        or "to hop" in normalized
    ):
        return "HOI_PHUONG_THUC_XET_TUYEN"
    if (
        "cach tinh diem" in normalized
        or "cong thuc diem" in normalized
        or "quy doi diem" in normalized
        or "diem xet tuyen" in normalized
    ):
        return "HOI_CACH_TINH_DIEM"
    if (
        "dang ky xet tuyen" in normalized
        or "cong dang ky" in normalized
        or "cong thong tin xet tuyen" in normalized
        or "nop nguyen vong" in normalized
        or "nguyen vong" in normalized
        or "dang ky" in normalized
    ) and "nhap hoc" not in normalized and "lich " not in normalized and "han xet tuyen" not in normalized:
        return "HOI_DANG_KY_XET_TUYEN"
    if (
        "co so" in normalized
        or "lien he" in normalized
        or "hotline" in normalized
        or "dia chi" in normalized
        or "so dien thoai" in normalized
        or "dien thoai" in normalized
        or "email" in normalized
    ):
        return "HOI_CO_SO_LIEN_HE"
    if entities.get("catalog_operation"):
        return "DANH_SACH_CHUONG_TRINH"
    list_markers = ("danh sach", "liet ke", "liet ra", "nhung nganh")
    program_list_requested = (
        "chuong trinh" in normalized
        and any(marker in normalized for marker in list_markers)
    ) or any(
        marker in normalized
        for marker in ("cac chuong trinh dao tao", "co nhung chuong trinh", "nhung chuong trinh nao")
    )
    if program_list_requested:
        return "DANH_SACH_CHUONG_TRINH"
    major_list_requested = (
        ("danh sach" in normalized and "nganh" in normalized)
        or ("liet ke" in normalized and "nganh" in normalized)
        or ("con thieu" in normalized and "nganh" in normalized)
        or any(
            marker in normalized
            for marker in ("co nhung nganh", "nhung nganh nao", "bao nhieu nganh")
        )
        or ("danh sach tren" in normalized and any(
            marker in normalized for marker in ("chua du", "thieu", "sai", "10 nganh", "12 nganh")
        ))
        or (
            state.previous_intent in {"DANH_SACH_NGANH", "DANH_SACH_CHUONG_TRINH"}
            and any(marker in normalized for marker in ("chua du", "con thieu", "thieu nganh", "liet ke lai"))
        )
    )
    if major_list_requested:
        return "DANH_SACH_NGANH"
    if entities.get("program_name") or "chuong trinh" in normalized:
        return "HOI_CHUONG_TRINH"
    if entities.get("major_code") or any(term in normalized for term in ("ma nganh", "nganh gi", "nganh nao", "nganh hoc")):
        return "HOI_NGANH"
    if (entities.get("major_name") or entities.get("major_code") or entities.get("program_name")) and any(
        term in normalized for term in ("bao nhieu diem", "lay bao nhieu diem", "diem nao")
    ):
        return "HOI_NGUONG_DAU_VAO"
    if "hoc phi" in normalized:
        return "HOI_HOC_PHI"
    if "hoc bong" in normalized:
        return "HOI_HOC_BONG"
    if "xet tuyen bo sung" in normalized or "tuyen sinh bo sung" in normalized:
        return "HOI_XET_TUYEN_BO_SUNG"
    if "ho so" in normalized or "giay to" in normalized or "thu tuc" in normalized:
        return "HOI_HO_SO"
    if "lich tuyen sinh" in normalized or "lich xet tuyen" in normalized or "han xet tuyen" in normalized:
        return "HOI_LICH_TUYEN_SINH"
    if "nhap hoc" in normalized or "xac nhan nhap hoc" in normalized:
        return "HOI_NHAP_HOC"
    if entities.get("score_type") == APPLICATION_THRESHOLD:
        return "HOI_NGUONG_DAU_VAO"
    if entities.get("score_type") == ADMISSION_SCORE:
        return "HOI_DIEM_TRUNG_TUYEN"
    if entities.get("score_type") == SUPPLEMENTARY_THRESHOLD:
        return "HOI_XET_TUYEN_BO_SUNG"
    if entities.get("major_name") or entities.get("major_code"):
        # A named major is an in-scope entity even when the first turn is only
        # an interest statement; the bounded state can then support a follow-up.
        return "HOI_NGANH"
    if state.current_major and any(term in normalized for term in ("thi sao", "con", "vay", "bao nhieu diem", "diem")):
        return "HOI_NGUONG_DAU_VAO" if "diem" in normalized else "HOI_CHUONG_TRINH"
    return "OUT_OF_SCOPE"


def analyze_question(question: str, state: ConversationState | Mapping[str, object] | None = None, *, default_year: int = 2026) -> QueryAnalysis:
    """Normalize one turn and extract only bounded structured entities."""

    active_state = ConversationState.from_value(state, default_year=default_year)
    original = question if isinstance(question, str) else ""
    normalized = normalize_question(original)
    entities = _extract_entities(normalized, active_state)
    intent = _classify_intent(normalized, entities, active_state)
    _clear_ambiguous_advisory_entities(entities, normalized, intent)
    if (
        intent == "DANH_SACH_CHUONG_TRINH"
        and not entities.get("major_name")
        and active_state.current_major
        and not _is_global_catalog_request(normalized)
    ):
        # A short follow-up such as ``gồm những chuyên ngành nào`` inherits
        # only the bounded current_major slot, never raw conversation history.
        entities["major_name"] = active_state.current_major
        entities["entity_type"] = "major"
    requested = {
        "HOI_NGANH": ["major"],
        "HOI_CHUONG_TRINH": ["program"],
        "HOI_NGUONG_DAU_VAO": [APPLICATION_THRESHOLD],
        "HOI_DIEM_TRUNG_TUYEN": [ADMISSION_SCORE],
        "HOI_XET_TUYEN_BO_SUNG": [SUPPLEMENTARY_THRESHOLD],
        "HOI_HOC_PHI": ["tuition"],
        "HOI_HOC_BONG": ["scholarship"],
        "HOI_HO_SO": ["documents"],
        "HOI_LICH_TUYEN_SINH": ["schedule"],
        "HOI_NHAP_HOC": ["enrollment"],
        "HOI_PHUONG_THUC_XET_TUYEN": ["admission_methods"],
        "HOI_CACH_TINH_DIEM": ["score_calculation"],
        "HOI_DANG_KY_XET_TUYEN": ["application_registration"],
        "HOI_CO_SO_LIEN_HE": ["campus_contact"],
        "TU_VAN_CHON_NGANH": ["recommendation"],
        "DANH_SACH_NGANH": ["major_list"],
        "DANH_SACH_CHUONG_TRINH": ["program_list"],
    }.get(intent, [])
    entities["requested_information"] = requested
    return QueryAnalysis(
        question=original,
        normalized_question=normalized,
        intent=intent,
        entities=entities,
    )


def _clarification_needed(analysis: QueryAnalysis, state: ConversationState) -> tuple[bool, str]:
    normalized = analysis.normalized_question
    score_type = analysis.entities.get("score_type") or state.current_score_type
    has_score_request = bool(re.search(r"bao nhieu diem|lay bao nhieu diem|diem nao", normalized))
    if analysis.intent == "DANH_SACH_NGANH" and "diem" in normalized and not score_type:
        return True, "score_kind_for_major_list"
    if has_score_request and not score_type and analysis.intent in {"HOI_NGANH", "HOI_CHUONG_TRINH", "HOI_NGUONG_DAU_VAO", "OUT_OF_SCOPE"}:
        return True, "score_kind_for_entity"
    return False, ""


def route_question(analysis: QueryAnalysis, state: ConversationState | Mapping[str, object] | None = None, *, target_year: int = 2026) -> QueryPlan:
    """Route an interpreted question to safe category filters."""

    active_state = ConversationState.from_value(state, default_year=target_year)
    entities = dict(analysis.entities)
    resolved = replace(analysis, entities=entities)
    if (
        not entities.get("major_name")
        and active_state.current_major
        and not entities.get("program_name")
        and not (
            resolved.intent == "DANH_SACH_CHUONG_TRINH"
            and _is_global_catalog_request(analysis.normalized_question)
        )
    ):
        entities["major_name"] = active_state.current_major
        entities["entity_type"] = "major"
    if not entities.get("candidate_majors") and active_state.candidate_majors:
        entities["candidate_majors"] = list(active_state.candidate_majors)
    if not entities.get("candidate_programs") and active_state.candidate_programs:
        entities["candidate_programs"] = list(active_state.candidate_programs)
    score_type = entities.get("score_type") or active_state.current_score_type
    if score_type:
        entities["score_type"] = score_type

    resolved = replace(analysis, entities=entities)
    needs_clarification, reason = _clarification_needed(resolved, active_state)
    categories: tuple[str, ...]
    if resolved.intent == "HOI_NGUONG_DAU_VAO":
        # The Law rows intentionally contain '-' and must not be mixed with
        # the generic threshold document.
        major = str(entities.get("major_name") or "").lower()
        categories = ("nganh_dao_tao",) if major in {"luật", "luật kinh tế"} else ("nganh_dao_tao", "nguong_dau_vao")
    elif resolved.intent == "HOI_DIEM_TRUNG_TUYEN":
        categories = ("diem_trung_tuyen",)
    elif resolved.intent == "HOI_XET_TUYEN_BO_SUNG":
        categories = ("xet_tuyen_bo_sung",)
    elif resolved.intent == "HOI_PHUONG_THUC_XET_TUYEN":
        categories = ("phuong_thuc_xet_tuyen",)
    elif resolved.intent == "HOI_CACH_TINH_DIEM":
        categories = ("cach_tinh_diem",)
    elif resolved.intent == "HOI_DANG_KY_XET_TUYEN":
        categories = ("dang_ky_xet_tuyen",)
    elif resolved.intent == "HOI_CO_SO_LIEN_HE":
        categories = ("co_so_lien_he",)
    elif resolved.intent in {
        "HOI_NGANH",
        "HOI_CHUONG_TRINH",
        "DANH_SACH_NGANH",
        "DANH_SACH_CHUONG_TRINH",
        "TU_VAN_CHON_NGANH",
    }:
        categories = ("nganh_dao_tao", "nguong_dau_vao") if resolved.intent == "TU_VAN_CHON_NGANH" else ("nganh_dao_tao",)
    elif resolved.intent == "HOI_HOC_PHI":
        categories = ("hoc_phi",)
    elif resolved.intent == "HOI_HOC_BONG":
        categories = ("hoc_bong",)
    elif resolved.intent == "HOI_HO_SO":
        categories = ("ho_so",)
    elif resolved.intent == "HOI_LICH_TUYEN_SINH":
        categories = ("lich_tuyen_sinh",)
    elif resolved.intent == "HOI_NHAP_HOC":
        categories = ("nhap_hoc",)
    else:
        categories = ()

    parts = [analysis.question.strip(), f"intent:{resolved.intent}", f"year:{entities.get('year') or target_year}"]
    for key in ("major_name", "major_code", "program_name", "parent_major", "score_type", "admission_method"):
        value = entities.get(key)
        if value:
            parts.append(f"{key}:{value}")
    for key in ("candidate_majors", "candidate_programs"):
        values = entities.get(key)
        if isinstance(values, Sequence) and not isinstance(values, str):
            parts.extend(f"{key}:{value}" for value in values if value)
    metadata_filter: dict[str, object] = {"year": target_year}
    if categories:
        metadata_filter["categories"] = list(categories)
    return QueryPlan(
        intent=resolved.intent,
        categories=categories,
        retrieval_query=" ".join(parts),
        metadata_filter=metadata_filter,
        needs_clarification=needs_clarification,
        clarification_reason=reason,
    )


def enrich_analysis_from_evidence(analysis: QueryAnalysis, evidence: Any) -> QueryAnalysis:
    """Resolve major/program relationships from retrieved corpus evidence."""

    entities = dict(analysis.entities)
    facts = getattr(evidence, "score_facts", ())
    code = entities.get("major_code")
    if code and not entities.get("major_name"):
        for fact in facts:
            if fact.get("major_code") == code and fact.get("major_name"):
                entities["major_name"] = fact["major_name"]
                entities["entity_type"] = "major"
                break
    major = normalize_question(str(entities.get("major_name") or ""))
    if major and not entities.get("major_code"):
        for fact in facts:
            if normalize_question(str(fact.get("major_name") or "")) == major and fact.get("major_code"):
                entities["major_code"] = fact["major_code"]
                break
    program = entities.get("program_name")
    candidate_programs = set(_safe_str_tuple(entities.get("candidate_programs")))
    relations = getattr(evidence, "entity_relations", ())
    if program:
        for relation in relations:
            if normalize_question(str(relation.get("program_name") or "")) == normalize_question(str(program)):
                entities["parent_major"] = relation.get("parent_major")
                break
    candidate_majors = list(_safe_str_tuple(entities.get("candidate_majors")))
    # In an ambiguous advisory turn, program_name is intentionally empty.
    # Still retain the evidence-derived parent as a candidate, without
    # promoting it to the resolved parent_major slot.
    for relation in relations:
        relation_program = _safe_str(relation.get("program_name"))
        relation_parent = _safe_str(relation.get("parent_major"))
        if relation_program in candidate_programs and relation_parent and relation_parent not in candidate_majors:
            candidate_majors.append(relation_parent)
    parent_major = _safe_str(entities.get("parent_major"))
    if parent_major and parent_major not in candidate_majors and program:
        candidate_majors.append(parent_major)
    if candidate_majors:
        entities["candidate_majors"] = candidate_majors[:_MAX_CANDIDATES]
    return replace(analysis, entities=entities)


def deterministic_score_comparisons(
    analysis: QueryAnalysis,
    evidence: Any,
) -> tuple[dict[str, object], ...]:
    """Compare explicitly supplied scores with retrieved thresholds only."""

    student_scores = analysis.entities.get("student_scores")
    if not isinstance(student_scores, Mapping):
        return ()
    facts = getattr(evidence, "score_facts", ())
    comparisons: list[dict[str, object]] = []
    for method, score in student_scores.items():
        if method == "thpt_subjects" or not isinstance(score, (int, float)):
            continue
        candidates = [
            fact
            for fact in facts
            if fact.get("score_type") == APPLICATION_THRESHOLD
            and fact.get("method") == method
            and isinstance(fact.get("value"), (int, float))
        ]
        if not candidates:
            continue
        threshold = candidates[0]["value"]
        comparisons.append(
            {
                "method": method,
                "student_value": score,
                "threshold_value": threshold,
                "operator": ">=",
                "meets_threshold": score >= threshold,
            }
        )
    return tuple(comparisons)


def select_relevant_score_facts(
    analysis: QueryAnalysis,
    facts: Any,
) -> tuple[dict[str, object], ...]:
    """Limit prompt facts to the requested entity/type without losing mapping."""

    fact_list = list(facts or ())
    entities = analysis.entities
    major = normalize_question(str(entities.get("major_name") or ""))
    code = str(entities.get("major_code") or "")
    score_type = entities.get("score_type")
    if score_type:
        fact_list = [fact for fact in fact_list if fact.get("score_type") == score_type]
    if major or code:
        specific = [
            fact
            for fact in fact_list
            if (major and normalize_question(str(fact.get("major_name") or "")) == major)
            or (code and str(fact.get("major_code") or "") == code)
        ]
        generic = [fact for fact in fact_list if not fact.get("major_name")]
        return tuple(specific + generic)
    generic = [fact for fact in fact_list if not fact.get("major_name")]
    return tuple(generic or fact_list[:12])


def update_conversation_state(
    state: ConversationState | Mapping[str, object] | None,
    analysis: QueryAnalysis,
    *,
    target_year: int = 2026,
    last_listed_majors: Sequence[str] | None = None,
    last_list_count: int | None = None,
) -> ConversationState:
    """Update slots from one turn without retaining raw messages."""

    current = ConversationState.from_value(state, default_year=target_year)
    entities = analysis.entities
    scores = dict(current.student_scores)
    new_scores = entities.get("student_scores")
    if isinstance(new_scores, Mapping):
        scores.update(new_scores)
    major = entities.get("major_name") or entities.get("parent_major") or current.current_major
    program = entities.get("program_name") or current.current_program
    method = entities.get("admission_method") or current.current_method
    score_type = entities.get("score_type") or current.current_score_type
    interest = entities.get("interest") or current.interest
    year = entities.get("year") or current.current_year or target_year
    candidate_majors = list(current.candidate_majors)
    candidate_programs = list(current.candidate_programs)
    for key, target in (("candidate_majors", candidate_majors), ("candidate_programs", candidate_programs)):
        values = entities.get(key)
        for value in _safe_str_tuple(values):
            if value not in target:
                target.append(value)
    explicit_conflict = bool(
        entities.get("program_name")
        and entities.get("major_name")
        and analysis.intent == "TU_VAN_CHON_NGANH"
    )
    ambiguous_choices = analysis.intent == "TU_VAN_CHON_NGANH" and (
        explicit_conflict or (current.current_major is None and len(candidate_majors) > 1)
    )
    if ambiguous_choices:
        major = current.current_major
        program = current.current_program
    listed_majors = current.last_listed_majors
    listed_count = current.last_list_count
    if last_listed_majors is not None:
        listed_majors = _safe_str_tuple(last_listed_majors, limit=_MAX_LISTED_MAJORS)
        listed_count = max(
            0,
            last_list_count if last_list_count is not None else len(listed_majors),
        )
    return ConversationState(
        current_year=int(year),
        current_major=str(major) if major else None,
        current_program=str(program) if program else None,
        current_method=str(method) if method else None,
        current_score_type=str(score_type) if score_type else None,
        student_scores=scores,
        interest=str(interest) if interest else None,
        candidate_majors=tuple(candidate_majors[:_MAX_CANDIDATES]),
        candidate_programs=tuple(candidate_programs[:_MAX_CANDIDATES]),
        last_listed_majors=listed_majors,
        last_list_count=listed_count,
        previous_intent=analysis.intent,
        turn_count=current.turn_count + 1,
    )


__all__ = [
    "ADMISSION_SCORE",
    "APPLICATION_THRESHOLD",
    "CATALOG_COUNT",
    "CATALOG_LIST",
    "CATALOG_LIST_AND_COUNT",
    "ConversationState",
    "INTENTS",
    "QueryAnalysis",
    "QueryPlan",
    "SUPPLEMENTARY_THRESHOLD",
    "analyze_question",
    "deterministic_score_comparisons",
    "enrich_analysis_from_evidence",
    "normalize_question",
    "route_question",
    "select_relevant_score_facts",
    "update_conversation_state",
]
