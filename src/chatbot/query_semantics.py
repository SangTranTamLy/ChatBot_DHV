"""Small, shared semantic predicates for routing and answer validation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_semantic_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", folded).strip()


def is_cash_payment_request(question: str) -> bool:
    """"Đóng tiền mặt ở đâu?" asks where/when to pay in person."""
    text = normalize_semantic_text(question)
    return "tien mat" in text and any(word in text for word in ("dong", "nop", "thanh toan", "tra"))


def enrollment_request(question: str) -> str:
    """Identify the requested enrollment fact, independently of the broad intent."""
    text = normalize_semantic_text(question.partition("intent:")[0])
    if is_cash_payment_request(text):
        return "cash_payment"
    if "nhap hoc" not in text and any(
        marker in text
        for marker in ("xet tuyen bo sung", "tuyen sinh bo sung", "dot bo sung")
    ):
        # Supplementary deadlines belong to the supplementary-round parser,
        # not the general admission/enrollment deadline request.
        return ""
    if "dang ky xet tuyen" in text and re.search(r"\b(?:han|lich)\b|\bkhi nao\b|\bngay nao\b", text):
        return "deadline"
    enrollment_context = any(
        marker in text
        for marker in (
            "ho so", "giay to", "nhap hoc", "vao hoc", "tan sinh vien",
            "sinh vien moi", "trung tuyen", "hoan tat thu tuc",
        )
    )
    benefit_markers = (
        "qua tang", "nhan qua", "duoc tang", "tang gi", "nhan gi",
        "nhan duoc gi", "duoc nhung gi", "nhan duoc nhung gi",
        "quyen loi", "office 365", "microsoft 365", "balo", "hop dung but",
        "day deo the", "ma so sinh vien", "sinh vien duoc cap",
    )
    if enrollment_context and any(marker in text for marker in benefit_markers):
        return "enrollment_benefits"
    if not enrollment_context:
        return ""
    if "xet tuyen" in text and "nhap hoc" not in text:
        return ""
    if "nhap hoc chinh thuc" in text:
        return "official_enrollment"
    if "xac nhan" in text:
        return ""
    if any(x in text for x in ("khung gio", "may gio", "gio nao", "luc nao trong ngay", "gio lam viec", "gio tiep nhan", "gio nhan", "thu bay", "chu nhat", "ngay le")):
        return "reception_hours"
    if any(x in text for x in ("han nop", "han nhan", "den ngay", "den khi", "khi nao", "ngay nao", "bao gio", "thoi gian")):
        return "reception_dates" if "nhap hoc" in text or "tan sinh vien" in text else "deadline"
    if any(x in text for x in ("o dau", "dia chi", "co so nao", "dia diem", "noi nao")):
        return "enrollment_location"
    if any(x in text for x in ("online", "truc tuyen", "hinh thuc", "cach nop")):
        return "submission_mode"
    if any(x in text for x in ("hoc phi", "hoc bong", "le phi", "phi nhap hoc", "hoc lieu", "dong tien", "uu dai", "diem")):
        return ""
    if "ho so" in text or "giay to" in text or ("thu tuc" in text and any(x in text for x in ("can chuan bi", "can gi", "gom"))):
        return "documents"
    return ""


def mentions_optional_english_test(question: str) -> bool:
    folded = normalize_semantic_text(question)
    return any(
        marker in folded
        for marker in (
            "kiem tra nang luc tieng anh",
            "kiem tra tieng anh",
            "thi tieng anh",
            "english test",
        )
    )


def excludes_optional_english_test(question: str) -> bool:
    folded = normalize_semantic_text(question)
    if not mentions_optional_english_test(folded):
        return False
    return any(
        marker in folded
        for marker in (
            "khong thuoc dien",
            "khong phai",
            "khong can",
            "khong thi",
            "khong kiem tra",
            "khong dong",
            "khong gom",
            "khong bao gom",
            "khong phat sinh",
        )
    )


def is_semester_fee_total_question(question: str) -> bool:
    folded = normalize_semantic_text(question)
    asks_total = any(
        marker in folded
        for marker in (
            "tong cac khoan",
            "tong chi phi",
            "tong tien",
            "tinh tong",
            "tong cong",
            "so tien",
        )
    )
    semester = any(marker in folded for marker in ("hoc ky", "hki", "hk1"))
    return asks_total and (semester or mentions_optional_english_test(folded))


# One vocabulary for recognizing and reading the verified DHV fee-table rows.
# ``key`` is the stable identifier used by the fee request parser; the marker
# is matched against normalized source lines, and the label is display text.
FEE_ROW_SPECS = (
    ("tuition_hki", ("hoc phi hki",), "Học phí HKI (10 tín chỉ)"),
    ("enrollment_fee", ("phi nhap hoc",), "Phí nhập học"),
    ("learning_materials", ("tai khoan hoc lieu dien tu", "hoc lieu"), "Tài khoản học liệu điện tử"),
    (
        "english_test_fee",
        ("kiem tra nang luc tieng anh", "kiem tra tieng anh"),
        "Kiểm tra năng lực Tiếng Anh (nếu có)",
    ),
)


@dataclass(frozen=True)
class FeeRequest:
    """Normalized details requested about tuition and its verified fee table."""

    is_fee_request: bool = False
    scope: str = "unknown"
    topics: tuple[str, ...] = ()
    semester: str | None = None
    credits: int | None = None
    optional_english: str = "unknown"
    relationship: str | None = None
    follow_up: bool = False
    fee_items: tuple[str, ...] = ()
    ambiguous_topics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "is_fee_request": self.is_fee_request,
            "scope": self.scope,
            "topics": list(self.topics),
            "semester": self.semester,
            "credits": self.credits,
            "optional_english": self.optional_english,
            "relationship": self.relationship,
            "follow_up": self.follow_up,
            "fee_items": list(self.fee_items),
            "ambiguous_topics": list(self.ambiguous_topics),
        }


def analyze_fee_request(question: str) -> FeeRequest:
    """Parse fee scope and requested topics without deriving any amounts.

    Amounts remain the responsibility of the verified fee-table formatter.
    This parser only supplies a compact, shared interpretation for routing and
    coverage checks.
    """

    text = normalize_semantic_text(question)
    has_money_request = any(
        marker in text
        for marker in (
            "hoc phi", "tien hoc", "phi nhap hoc", "hoc lieu",
            "kiem tra nang luc tieng anh", "kiem tra tieng anh",
            "khoan thu", "khoan khac", "cac khoan", "dong bao nhieu",
            "phai dong", "can dong", "con dong", "tong tien", "tong cac khoan",
            "tong chi phi", "tong cong", "tong la bao nhieu", "so tien", "cong het",
            "cong lai", "het bao nhieu", "gia tin chi", "don gia",
        )
    ) or (
        "tin chi" in text
        and any(marker in text for marker in ("bao nhieu", "gia", "phi", "tien", "dong"))
    )
    if not has_money_request:
        return FeeRequest()

    items = tuple(
        key
        for key, markers, _label in FEE_ROW_SPECS[1:]
        if any(marker in text for marker in markers)
    )
    asks_total = any(
        marker in text
        for marker in (
            "tong", "so tien", "cong het", "cong lai", "het bao nhieu", "bao nhieu tat ca",
        )
    )
    asks_other_fees = any(
        marker in text
        for marker in (
            "ngoai hoc phi", "ngoai tien hoc", "khoan thu khac", "khoan khac",
            "cac khoan khac", "nhung khoan", "cac khoan", "dong them",
            "them cac khoan", "phat sinh", "khi nhap hoc",
        )
    )
    asks_tuition = any(marker in text for marker in ("hoc phi", "tien hoc", "gia tin chi", "don gia")) and not any(
        marker in text
        for marker in (
            "ngoai hoc phi", "ngoai tien hoc", "co nam trong hoc phi",
            "nam trong hoc phi", "da bao gom hoc phi", "bao gom hoc phi",
        )
    )
    if not asks_tuition and not items and not asks_other_fees and any(
        marker in text for marker in ("hoc ky", "hki", "hk1", "dong bao nhieu", "phai dong", "can dong")
    ):
        asks_tuition = True

    topics: list[str] = []
    if asks_tuition:
        topics.append("tuition")
    if asks_other_fees or items:
        topics.append("other_fees")
    if asks_total:
        topics.append("total")
    if items:
        topics.append("specific_fee")
    scholarship = "hoc bong" in text
    if scholarship:
        topics.append("scholarship")

    annual = any(marker in text for marker in ("theo nam", "moi nam", "hang nam", "trung binh nam"))
    semester = None
    if re.search(r"\b(?:hki|hk1|hoc ky i|hoc ki i|hoc ky 1|hoc ki 1)\b", text):
        semester = "HKI"
    elif re.search(r"\b(?:hkii|hk2|hoc ky ii|hoc ki ii|hoc ky 2|hoc ki 2)\b", text):
        semester = "HKII"
    credit_match = re.search(r"\b(\d{1,2})\s*tin chi\b", text)
    credits = int(credit_match.group(1)) if credit_match else None
    if annual:
        scope = "annual"
    elif semester or items or asks_other_fees or asks_total:
        scope = "semester"
    elif asks_tuition or credits is not None:
        scope = "per_credit"
    else:
        scope = "unknown"

    if excludes_optional_english_test(text):
        optional_english = "exclude"
    elif mentions_optional_english_test(text) and any(
        marker in text for marker in ("neu co", "co kiem tra", "neu kiem tra", "tinh ca", "bao gom")
    ):
        optional_english = "include"
    else:
        optional_english = "unknown"

    relationship = None
    if any(marker in text for marker in ("thu rieng", "phi rieng", "tinh rieng")):
        relationship = "separate"
    elif any(marker in text for marker in (
        "co nam trong", "nam trong hoc phi", "da gom", "da bao gom", "bao gom hoc phi",
        "bao gom phi", "duoc tinh trong hoc phi",
    )):
        relationship = "included"

    follow_up = bool(re.search(r"\b(?:vay|the|con|neu|cach|cong)\b", text))
    ambiguous_topics = ("scholarship",) if scholarship and not any(
        marker in text for marker in ("dau vao", "hoc ba", "hoan hoc phi", "dgnl", "cam ket")
    ) else ()
    return FeeRequest(
        is_fee_request=True,
        scope=scope,
        topics=tuple(topics),
        semester=semester,
        credits=credits,
        optional_english=optional_english,
        relationship=relationship,
        follow_up=follow_up,
        fee_items=items,
        ambiguous_topics=ambiguous_topics,
    )


# The verified HKI fee table lives in the tuition document; the previous
# combined enrollment PDF ("ho_so") is still accepted for older corpora.
FEE_TABLE_CATEGORIES = frozenset({"hoc_phi", "ho_so"})


def is_fee_table_page_text(metadata: object) -> bool:
    """True for verified DHV page text that may carry the HKI fee table."""
    if not isinstance(metadata, dict):
        return False
    return (
        str(metadata.get("record_type") or "") == "page_text"
        and str(metadata.get("category") or "") in FEE_TABLE_CATEGORIES
        and str(metadata.get("status") or "").casefold() == "verified"
        and str(metadata.get("school_code") or "").strip().upper() == "DHV"
    )


def should_include_optional_english_fee(question: str) -> bool:
    return mentions_optional_english_test(question) and not excludes_optional_english_test(question)


def is_tuition_increase_question(question: str) -> bool:
    """Hỏi học phí có tăng/ổn định không, với mọi cách diễn đạt (``có tăng hay k``...)."""
    folded = normalize_semantic_text(question)
    if "hoc phi" not in folded:
        return False
    # ``tầng`` cũng bị bỏ dấu thành ``tang``; câu hỏi tầng/lầu là hỏi địa điểm.
    if re.search(r"\btang (?:may|\d)|\blau\b", folded):
        return False
    return bool(re.search(r"\b(?:tang|on dinh|giu nguyen|cam ket)\b", folded))


# Cụm từ tuyển sinh hay bị gõ sai, kèm số ký tự sai tối đa được sửa. Chỉ
# ``phương thức`` chịu sai 2 ký tự (``Phước thực``); cụm khác chỉ 1 để không đổi
# nhầm cụm có nghĩa khác (``chuẩn ngành`` ≠ ``chuyên ngành``).
_DOMAIN_PHRASES = {
    "phuong thuc": ("phương thức", 2),
    "dieu kien": ("điều kiện", 1),
    "xet tuyen": ("xét tuyển", 1),
    "tuyen sinh": ("tuyển sinh", 1),
    "chuyen nganh": ("chuyên ngành", 1),
    "trung tuyen": ("trúng tuyển", 1),
    "hoc phi": ("học phí", 1),
}
_VOWELS = "aeiouy"


def _strip_telex_residue(token: str) -> str:
    """Bỏ phím Telex sót lại khi bộ gõ không nhận (``dieefu`` → ``dieu``)."""
    token = re.sub(r"([aeod])\1", r"\1", token)
    token = re.sub(rf"(?<=[{_VOWELS}])[sfrxj](?=[{_VOWELS}])", "", token)
    return re.sub(rf"(?<=[{_VOWELS}])[sfrxj]$", "", token)


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, start=1):
        current = [i]
        for j, char_right in enumerate(right, start=1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (char_left != char_right),
            ))
        previous = current
    return previous[-1]


def _match_domain_phrase(first: str, second: str) -> str | None:
    key = f"{_strip_telex_residue(normalize_semantic_text(first))} {_strip_telex_residue(normalize_semantic_text(second))}"
    # ``phòng thuộc`` occurs naturally in programme names followed by a
    # relation question (for example, ``Tiếng Trung hành chính văn phòng
    # thuộc ngành nào?``). Its edit distance is close enough to ``phương
    # thức`` that fuzzy correction otherwise destroys the programme name.
    if key == "phong thuoc":
        return None
    for folded, (canonical, allowed) in _DOMAIN_PHRASES.items():
        if key == folded:
            return canonical
        head, tail = folded.split()
        if not key.startswith(head[0]) or key.split()[-1][:1] != tail[0]:
            continue
        if _edit_distance(key, folded) <= allowed:
            return canonical
    return None


def correct_domain_typos(question: str) -> str:
    """Sửa lỗi gõ ở các cụm tuyển sinh để bộ tách ý nhận ra đủ các vế câu hỏi."""
    # ``hp`` là viết tắt phổ biến của ``học phí`` (``hp bn?``).
    words = re.sub(r"(?<!\w)hp(?!\w)", "học phí", question or "", flags=re.IGNORECASE).split(" ")
    corrected: list[str] = []
    index = 0
    while index < len(words):
        if index + 1 < len(words):
            first, second = words[index], words[index + 1]
            core_second = second.rstrip(",.;:?!")
            canonical = _match_domain_phrase(first, core_second) if first and core_second else None
            if canonical and normalize_semantic_text(f"{first} {core_second}") != normalize_semantic_text(canonical):
                if first[:1].isupper():
                    canonical = canonical[0].upper() + canonical[1:]
                corrected.append(canonical + second[len(core_second):])
                index += 2
                continue
        corrected.append(words[index])
        index += 1
    return " ".join(corrected)
