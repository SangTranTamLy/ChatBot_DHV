"""Small, shared semantic predicates for routing and answer validation."""

from __future__ import annotations

import re
import unicodedata


def normalize_semantic_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", folded).strip()


def enrollment_request(question: str) -> str:
    """Identify the requested enrollment fact, independently of the broad intent."""
    text = normalize_semantic_text(question.partition("intent:")[0])
    if "dang ky xet tuyen" in text and re.search(r"\b(?:han|lich)\b|\bkhi nao\b|\bngay nao\b", text):
        return "deadline"
    if not any(x in text for x in ("ho so", "giay to", "nhap hoc", "tiep nhan tan sinh vien")):
        return ""
    if "xet tuyen" in text and "nhap hoc" not in text:
        return ""
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
