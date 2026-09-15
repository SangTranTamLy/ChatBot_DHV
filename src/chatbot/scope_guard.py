"""Lớp bảo vệ phạm vi nhỏ gọn dành cho các câu hỏi tuyển sinh DHV."""

from __future__ import annotations

import re
import unicodedata


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
        "diem san",
        "diem trung tuyen",
        "diem chuan",
        "diem xet tuyen",
        "nguong dau vao",
        "nganh",
        "chuong trinh",
        "uu tien",
        "thong tin truong",
        "thong tin ve truong",
        "thong tin ve dhv",
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
        "hung vuong tphcm",
        "hung vuong thanh pho ho chi minh",
    }
)

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
    return text.lower().replace("đ", "d")


def is_personal_life_advice(question: str) -> bool:
    """Nhận diện yêu cầu lời khuyên cá nhân, không phải tra cứu tuyển sinh."""

    normalized = normalize_scope_text(question).strip()
    return (
        any(marker in normalized for marker in _PERSONAL_ADVICE_PASSION_MARKERS)
        and any(marker in normalized for marker in _PERSONAL_ADVICE_CONFLICT_MARKERS)
        and any(marker in normalized for marker in _PERSONAL_ADVICE_DECISION_MARKERS)
    )


def is_in_scope(question: str, *, has_admissions_entity: bool = False) -> bool:
    """Trả về xem một câu hỏi có vẻ liên quan đến tuyển sinh DHV hay không."""

    normalized = normalize_scope_text(question).strip()
    if not normalized:
        return False
    if is_personal_life_advice(normalized) and not has_admissions_entity:
        return False
    if any(keyword in normalized for keyword in ADMISSIONS_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in SCHOOL_DIRECTORY_KEYWORDS):
        return True
    return bool(
        any(keyword in normalized for keyword in SCHOOL_KEYWORDS)
        and re.search(r"\b20\d{2}\b", normalized)
    )


__all__ = ["is_in_scope", "is_personal_life_advice", "normalize_scope_text"]
