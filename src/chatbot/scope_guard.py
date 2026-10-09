"""Lớp bảo vệ phạm vi nhỏ gọn dành cho các câu hỏi tuyển sinh DHV."""

from __future__ import annotations

import re
import unicodedata


TARGET_SCHOOL_DHV = "DHV"
TARGET_SCHOOL_OTHER = "OTHER_SCHOOL"
TARGET_SCHOOL_MIXED = "MIXED"
TARGET_SCHOOL_UNSPECIFIED = "UNSPECIFIED"
TARGET_SCHOOL_AMBIGUOUS = "AMBIGUOUS"

SCOPE_REASON_IN_SCOPE_DHV = "in_scope_dhv"
SCOPE_REASON_EXTERNAL_SCHOOL = "external_school"
SCOPE_REASON_MIXED_SCHOOL = "mixed_school"
SCOPE_REASON_AMBIGUOUS_SCHOOL = "ambiguous_school"
SCOPE_REASON_GENERAL_OUT_OF_SCOPE = "general_out_of_scope"
SCOPE_REASON_RELATED_NO_DATA = "related_no_data"


ADMISSIONS_KEYWORDS = frozenset(
    {
        "tuyen sinh",
        "xet tuyen",
        "hoc phi",
        "hoc bong",
        "ho so",
        "giay to",
        "thu tuc",
        "nhap hoc",
        "tan sinh vien",
        "hoc lieu",
        "phi nhap hoc",
        "xac nhan nhap hoc",
        "lich tuyen sinh",
        "lich xet tuyen",
        "han xet tuyen",
        "xet tuyen bo sung",
        "tuyen sinh bo sung",
        "dang ky",
        "nguyen vong",
        "phuong thuc",
        "to hop",
        "hinh thuc xet tuyen",
        "cach xet tuyen",
        "cach thuc xet tuyen",
        "lay may mon",
        "hoc ba",
        "hoc tap thpt",
        "danh gia nang luc",
        "dgnl",
        "thi tot nghiep thpt",
        "thi tot nghiep",
        "thi thpt",
        "cach tinh diem",
        "cong thuc diem",
        "quy doi diem",
        "cong dang ky",
        "cong thong tin xet tuyen",
        "nop nguyen vong",
        "co so",
        "lien he",
        "hotline",
        "dia chi",
        "so dien thoai",
        "dien thoai",
        "email",
        "website",
        "trang web",
        "web",
        " web",
        "nganh hoc",
        "diem nhan ho so",
        "diem nhan ho so bo sung",
        "nhan ho so bo sung",
        "diem san",
        "diem trung tuyen",
        "trung tuyen",
        "diem chuan",
        "diem xet tuyen",
        "nguong dau vao",
        "nganh",
        "chuong trinh",
        "uu tien",
        "cong diem",
        "diem khuyen khich",
        "duoc cong bao nhieu diem",
        "duoc cong may diem",
        "thi sinh khuyet tat",
        "kiem tra nang luc tieng anh",
        "khoan hoc ky",
        "hoc ky i",
        "tong chi phi",
        "so tien hoc ky",
        "hoan tat xac nhan",
        "xac nhan truoc",
        "giay chung nhan ket qua thi",
        "dong tien mat",
        "thong tin truong",
        "thong tin ve truong",
        "thong tin ve dhv",
        "gioi thieu ve truong",
        "gioi thieu truong",
        "gioi thieu ve dhv",
        "dhv la truong",
        "truong dhv la",
        "truong dai hoc hung vuong la",
        "truong thanh lap",
        "thanh lap khi nao",
        "thanh lap nam",
    }
)
SCHOOL_DIRECTORY_KEYWORDS = frozenset(
    {
        "vien dao tao sau dai hoc",
        "vien lien ket giao duc va dao tao tu xa",
        "dao tao tu xa",
        "khoa khoa hoc suc khoe",
        "khoa ky thuat cong nghe",
        "khoa tai chinh ngan hang ke toan",
        "khoa quan tri kinh doanh marketing",
        "khoa ngon ngu",
        "khoa du lich nha hang khach san",
        "khoa luat",
        "cong thong tin dao tao",
    }
)
SCHOOL_KEYWORDS = frozenset(
    {
        "dhv",
        "dai hoc hung vuong",
        "hung vuong",
        "hung vuong tphcm",
        "hung vuong thanh pho ho chi minh",
    }
)

# Các tên dưới đây là những tổ chức giáo dục thường xuất hiện trong câu hỏi
# ``điểm chuẩn/học phí trường khác``.  Không đưa mọi chuỗi ``đại học`` vào đây:
# các câu hỏi chung như ``Trường có xét học bạ không?`` vẫn phải được hiểu là
# đang hỏi DHV theo ngữ cảnh của chatbot.
FOREIGN_INSTITUTION_KEYWORDS = frozenset(
    {
        "dai hoc quoc gia ha noi",
        "dhqghn",
        "dhqg hn",
        "dai hoc quoc gia thanh pho ho chi minh",
        "dai hoc bach khoa ha noi",
        "bach khoa ha noi",
        "dai hoc bach khoa tphcm",
        "dai hoc bach khoa tp hcm",
        "bach khoa tphcm",
        "bach khoa tp hcm",
        "dai hoc kinh te quoc dan",
        "kinh te quoc dan",
        "dai hoc ngoai thuong",
        "ngoai thuong",
        "ftu",
        "dai hoc fpt",
        "fpt university",
        "dai hoc rmit",
        "rmit",
        "dai hoc ton duc thang",
        "ton duc thang",
        "dai hoc kinh te tp hcm",
        "dai hoc kinh te tphcm",
        "ueh",
        "dai hoc sai gon",
        "dai hoc thuong mai",
        "dai hoc van lang",
        "dai hoc van hien",
        "van hien",
        "dai hoc hoa sen",
        "hoa sen",
        "dai hoc nguyen tat thanh",
        "nguyen tat thanh",
        "dai hoc mo tphcm",
        "dai hoc mo tp hcm",
        "dai hoc y duoc",
    }
)
_OTHER_SCHOOL_MARKERS = (
    "truong khac",
    "truong dai hoc khac",
    "truong dh khac",
    "truong cao dang khac",
    "dai hoc khac",
    "cao dang khac",
    "hoc vien khac",
    "truong ben kia",
    "truong nay khac",
)
_DGNL_EXTERNAL_SOURCE_RE = re.compile(
    r"\b(?:dgnl|danh gia nang luc)\b.{0,32}\b(?:dhqg|dai hoc quoc gia)\b",
)
_GENERIC_INSTITUTION_FOLLOWERS = frozenset(
    {
        "bao",
        "ban",
        "bat",
        "bo",
        "cao",
        "cach",
        "can",
        "co",
        "cua",
        "cu",
        "con",
        "cong",
        "da",
        "dao",
        "danh",
        "de",
        "di",
        "do",
        "doanh",
        "dam",
        "doi",
        "duoc",
        "giai",
        "giao",
        "gi",
        "gì",
        "gom",
        "hop",
        "hoc",
        "hoat",
        "hinh",
        "huong",
        "kinh",
        "ky",
        "khong",
        "kia",
        "la",
        "lay",
        "lam",
        "lien",
        "linh",
        "minh",
        "nam",
        "nao",
        "nganh",
        "nghe",
        "nghiep",
        "ngay",
        "nop",
        "nhan",
        "nhieu",
        "nay",
        "ngoai",
        "noi",
        "nhu",
        "mo",
        "o",
        "phu",
        "quoc",
        "ra",
        "se",
        "tai",
        "sinh",
        "thanh",
        "thuc",
        "theo",
        "thi",
        "tiep",
        "thong",
        "tin",
        "to",
        "chuc",
        "chuyen",
        "giup",
        "phong",
        "nhom",
        "trien",
        "trong",
        "tu",
        "truong",
        "tuyen",
        "va",
        "ve",
        "voi",
        "vay",
        "xet",
        "ay",
        "te",
        "mieng",
    }
)
_INSTITUTION_REFERENCE_RE = re.compile(
    r"\b(?P<kind>truong|dai hoc|dh|hoc vien|cao dang|university)\s+(?P<first>[a-z0-9]+)\b",
)


def _contains_scope_marker(normalized: str, marker: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized))


def _has_unknown_named_institution(normalized: str) -> bool:
    """Bắt tên trường chưa có trong danh sách nhưng được nêu rõ trong câu hỏi.

    Không coi các mẫu ``trường có...``, ``đại học nào...`` là tên trường. Nếu
    từ ngay sau ``trường/đại học/học viện/cao đẳng`` là một từ mô tả khác,
    đó thường là tên riêng (ví dụ ``trường Văn Hiến``).
    """

    for match in _INSTITUTION_REFERENCE_RE.finditer(normalized):
        first_word = match.group("first")
        if first_word in _GENERIC_INSTITUTION_FOLLOWERS:
            continue
        # ``Trường thành lập khi nào?`` is a school-information question;
        # ``Trường Thành Đô`` is a named institution and must be rejected.
        if first_word == "thanh" and re.match(r"\s+lap\b", normalized[match.end() :]):
            continue
        # ``trường đại học ...`` is inspected again by the ``đại học`` match.
        if match.group("kind") == "truong" and first_word == "dai":
            continue
        return True
    return False


_EXTERNAL_ALIAS_DISPLAY = {
    # ``Bách Khoa`` is a well-known bare alias, but it does not identify DHV
    # and may refer to more than one institution.  Register the semantic
    # institution alias instead of allowing it to fall through to DHV's
    # unspecified-school default.
    "bach khoa": "Bách Khoa",
    "van hien": "Văn Hiến",
    "van lang": "Văn Lang",
    "hoa sen": "Hoa Sen",
    "nguyen tat thanh": "Nguyễn Tất Thành",
    "dai hoc quoc gia ha noi": "Đại học Quốc gia Hà Nội",
    "dai hoc quoc gia thanh pho ho chi minh": "Đại học Quốc gia TP.HCM",
    "dai hoc bach khoa ha noi": "Đại học Bách khoa Hà Nội",
    "dai hoc bach khoa tphcm": "Đại học Bách khoa TP.HCM",
    "dai hoc kinh te quoc dan": "Đại học Kinh tế Quốc dân",
    "dai hoc ngoai thuong": "Đại học Ngoại thương",
    "dai hoc fpt": "Đại học FPT",
    "dai hoc rmit": "RMIT",
    "dai hoc sai gon": "Đại học Sài Gòn",
}


def _school_mentions(normalized: str) -> tuple[list[str], bool, bool]:
    """Trích xuất tên trường theo một registry nhỏ và mẫu tên rõ ràng."""

    mentions: list[str] = []
    explicit_dhv = any(
        _contains_scope_marker(normalized, marker)
        for marker in (
            "dhv",
            "dai hoc hung vuong tp ho chi minh",
            "dai hoc hung vuong tphcm",
            "dai hoc hung vuong tp hcm",
            "dai hoc hung vuong thanh pho ho chi minh",
            "hung vuong tp ho chi minh",
            "hung vuong tphcm",
            "hung vuong tp hcm",
            "hung vuong thanh pho ho chi minh",
        )
    )
    bare_hung_vuong = _contains_scope_marker(normalized, "hung vuong")
    ambiguous_hung_vuong = bare_hung_vuong and not explicit_dhv
    if explicit_dhv:
        mentions.append("Trường Đại học Hùng Vương TP.HCM")
    elif ambiguous_hung_vuong:
        mentions.append("Hùng Vương")

    for alias, display in _EXTERNAL_ALIAS_DISPLAY.items():
        if _contains_scope_marker(normalized, alias):
            if display not in mentions:
                mentions.append(display)

    for keyword in FOREIGN_INSTITUTION_KEYWORDS:
        if _contains_scope_marker(normalized, keyword):
            display = _EXTERNAL_ALIAS_DISPLAY.get(keyword, keyword)
            if display not in mentions:
                mentions.append(display)

    external_score_source = any(
        _contains_scope_marker(normalized, marker)
        for marker in (
            "dhqg hcm",
            "dhqg tphcm",
            "dhqg tp hcm",
            "dai hoc quoc gia tp hcm",
            "dai hoc quoc gia tphcm",
            "dai hoc quoc gia hcm",
        )
    )
    if external_score_source and not _DGNL_EXTERNAL_SOURCE_RE.search(normalized):
        if "ĐHQG-HCM" not in mentions:
            mentions.append("ĐHQG-HCM")

    # A generic phrase such as ``trường đại học khác`` does not identify a
    # named institution, but it explicitly moves the question outside DHV.
    # Keep this separate from the broad word ``trường`` so generic DHV
    # questions (``Trường có những ngành nào?``) remain unspecified/default.
    if any(_contains_scope_marker(normalized, marker) for marker in _OTHER_SCHOOL_MARKERS):
        if "trường khác" not in mentions:
            mentions.append("trường khác")

    if _has_unknown_named_institution(normalized) and not mentions and not explicit_dhv:
        mentions.append("trường khác")

    return mentions, explicit_dhv, ambiguous_hung_vuong


def detect_target_school(question: str) -> dict[str, object]:
    """Xác định trường đích độc lập với intent nghiệp vụ.

    Intent trả lời câu hỏi hỏi gì; hàm này trả lời câu hỏi đang hỏi trường
    nào. Hai thông tin không được trộn để tránh lấy fact DHV cho trường khác.
    """

    normalized = normalize_scope_text(question).strip()
    mentions, explicit_dhv, ambiguous_hung_vuong = _school_mentions(normalized)
    has_external = any(
        mention != "Trường Đại học Hùng Vương TP.HCM" and mention != "Hùng Vương"
        for mention in mentions
    )
    comparison_markers = (
        "so sanh",
        "so voi",
        "khac nhau",
        "khac biet",
        "nen chon truong nao",
    )
    explicit_comparison = (
        explicit_dhv
        and has_external
        and any(_contains_scope_marker(normalized, marker) for marker in comparison_markers)
    )
    if explicit_comparison:
        target = TARGET_SCHOOL_MIXED
        reason = SCOPE_REASON_MIXED_SCHOOL
    elif explicit_dhv:
        target = TARGET_SCHOOL_DHV
        reason = SCOPE_REASON_IN_SCOPE_DHV
    elif ambiguous_hung_vuong:
        target = TARGET_SCHOOL_AMBIGUOUS
        reason = SCOPE_REASON_AMBIGUOUS_SCHOOL
    elif has_external:
        target = TARGET_SCHOOL_OTHER
        reason = SCOPE_REASON_EXTERNAL_SCHOOL
    else:
        target = TARGET_SCHOOL_UNSPECIFIED
        reason = ""
    return {
        "target_school": target,
        "school_mentions": mentions,
        "scope_reason": reason,
        "explicit_school": bool(mentions),
    }

_PERSONAL_ADVICE_PASSION_MARKERS = (
    "dam me",
    "yeu thich",
    "so thich ca nhan",
    "dieu minh thich",
    "cong viec minh thich",
)
_PERSONAL_ADVICE_CONFLICT_MARKERS = (
    "theo dam me",
    "dam me hay",
    "dam me hoac",
    "khong dam me",
    "khong yeu thich",
    "nganh de xin viec",
    "cong viec on dinh",
)
_PERSONAL_ADVICE_DECISION_MARKERS = (
    "phan van",
    "nen ",
    "khong biet",
    "tu van",
    "lua chon",
)


def normalize_scope_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.lower().replace("đ", "d")
    # ``TP.HCM``, ``TP-HCM`` và ``ĐHQG-HCM`` phải được xử lý giống nhau.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_personal_life_advice(question: str) -> bool:
    """Nhận diện yêu cầu lời khuyên cá nhân, không phải tra cứu tuyển sinh."""

    normalized = normalize_scope_text(question).strip()
    return (
        any(marker in normalized for marker in _PERSONAL_ADVICE_PASSION_MARKERS)
        and any(marker in normalized for marker in _PERSONAL_ADVICE_CONFLICT_MARKERS)
        and any(marker in normalized for marker in _PERSONAL_ADVICE_DECISION_MARKERS)
    )


def _is_tuition_unit_question(normalized: str) -> bool:
    """Nhận diện câu hỏi học phí theo đơn vị tín chỉ.

    ``tín chỉ`` tự nó không mở phạm vi; chỉ mở khi câu hỏi cũng có tín hiệu
    hỏi giá/phí. Nhờ vậy một câu hỏi chung về tín chỉ không bị coi là câu hỏi
    tuyển sinh một cách quá rộng.
    """

    has_unit = "tin chi" in normalized
    asks_price = any(
        marker in normalized
        for marker in ("bao nhieu tien", "gia bao nhieu", "bao nhieu", "hoc phi", "phi moi")
    )
    return has_unit and asks_price


def is_foreign_institution_question(question: str) -> bool:
    """Nhận diện yêu cầu nhắm tới trường khác DHV.

    ĐHQG-HCM là nguồn của kỳ thi ĐGNL mà DHV có thể dùng để xét tuyển, nên
    cụm này chỉ bị chặn khi nó được hỏi như một trường hoặc không nằm trong
    ngữ cảnh kỳ thi ĐGNL.
    """

    target = detect_target_school(question)["target_school"]
    return target in {TARGET_SCHOOL_OTHER, TARGET_SCHOOL_MIXED}


def scope_reason(
    question: str,
    *,
    target_school: str | None = None,
    has_admissions_entity: bool = False,
    has_verified_school_info: bool = False,
) -> str:
    """Trả về lý do phạm vi để trace phân biệt external với câu hỏi chung."""

    normalized = normalize_scope_text(question).strip()
    target = target_school or str(detect_target_school(normalized)["target_school"])
    if target == TARGET_SCHOOL_OTHER:
        return SCOPE_REASON_EXTERNAL_SCHOOL
    if target == TARGET_SCHOOL_MIXED:
        return SCOPE_REASON_MIXED_SCHOOL
    if target == TARGET_SCHOOL_AMBIGUOUS:
        return SCOPE_REASON_AMBIGUOUS_SCHOOL
    if is_personal_life_advice(normalized) and not has_admissions_entity:
        return SCOPE_REASON_GENERAL_OUT_OF_SCOPE
    if has_verified_school_info:
        return SCOPE_REASON_IN_SCOPE_DHV
    if _is_tuition_unit_question(normalized):
        return SCOPE_REASON_IN_SCOPE_DHV
    if has_admissions_entity and any(
        marker in normalized
        for marker in ("hoc luc", "lop 12", "du dieu kien", "xet", "nguong", "diem san")
    ):
        return SCOPE_REASON_IN_SCOPE_DHV
    raw_date_count = len(re.findall(r"\b\d{1,2}\s*[./-]\s*\d{1,2}\b", question or ""))
    if raw_date_count >= 2 and "moc" in normalized and "huong dan" in normalized:
        return SCOPE_REASON_IN_SCOPE_DHV
    if (
        "huong dan" in normalized
        and len(re.findall(r"\b\d{1,2}/\d{1,2}\b", normalized)) >= 2
        and "moc" in normalized
    ):
        return SCOPE_REASON_IN_SCOPE_DHV
    if any(keyword in normalized for keyword in ADMISSIONS_KEYWORDS):
        return SCOPE_REASON_IN_SCOPE_DHV
    if any(keyword in normalized for keyword in SCHOOL_DIRECTORY_KEYWORDS):
        return SCOPE_REASON_IN_SCOPE_DHV
    if any(keyword in normalized for keyword in ("thoi tiet", "gia vang", "nau pho", "cau chuyen", "xin viec", "viec lam")):
        return SCOPE_REASON_GENERAL_OUT_OF_SCOPE
    if target == TARGET_SCHOOL_DHV:
        return SCOPE_REASON_IN_SCOPE_DHV
    return SCOPE_REASON_GENERAL_OUT_OF_SCOPE


def is_in_scope(
    question: str,
    *,
    has_admissions_entity: bool = False,
    target_school: str | None = None,
    has_verified_school_info: bool = False,
) -> bool:
    """Trả về xem một câu hỏi có vẻ liên quan đến tuyển sinh DHV hay không."""

    normalized = normalize_scope_text(question).strip()
    if not normalized:
        return False
    # Tên trường đích là ranh giới cứng. Kiểm tra trước các từ khóa rộng như
    # ``điểm chuẩn`` để không truy xuất nhầm dữ liệu DHV cho trường khác.
    reason = scope_reason(
        normalized,
        target_school=target_school,
        has_admissions_entity=has_admissions_entity,
        has_verified_school_info=has_verified_school_info,
    )
    if reason in {
        SCOPE_REASON_EXTERNAL_SCHOOL,
        SCOPE_REASON_MIXED_SCHOOL,
        SCOPE_REASON_AMBIGUOUS_SCHOOL,
        SCOPE_REASON_GENERAL_OUT_OF_SCOPE,
    }:
        return False
    return reason == SCOPE_REASON_IN_SCOPE_DHV


__all__ = [
    "FOREIGN_INSTITUTION_KEYWORDS",
    "SCOPE_REASON_AMBIGUOUS_SCHOOL",
    "SCOPE_REASON_EXTERNAL_SCHOOL",
    "SCOPE_REASON_GENERAL_OUT_OF_SCOPE",
    "SCOPE_REASON_IN_SCOPE_DHV",
    "SCOPE_REASON_MIXED_SCHOOL",
    "SCOPE_REASON_RELATED_NO_DATA",
    "TARGET_SCHOOL_AMBIGUOUS",
    "TARGET_SCHOOL_DHV",
    "TARGET_SCHOOL_MIXED",
    "TARGET_SCHOOL_OTHER",
    "TARGET_SCHOOL_UNSPECIFIED",
    "detect_target_school",
    "is_foreign_institution_question",
    "is_in_scope",
    "is_personal_life_advice",
    "normalize_scope_text",
    "scope_reason",
]
