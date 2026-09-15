"""Lightweight scope guard for DHV admissions questions."""

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


def normalize_scope_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    return text.lower().replace("đ", "d")


def is_in_scope(question: str) -> bool:
    """Return whether a question plausibly concerns DHV admissions."""

    normalized = normalize_scope_text(question).strip()
    if not normalized:
        return False
    if any(keyword in normalized for keyword in ADMISSIONS_KEYWORDS):
        return True
    return bool(
        any(keyword in normalized for keyword in SCHOOL_KEYWORDS)
        and re.search(r"\b20\d{2}\b", normalized)
    )


__all__ = ["is_in_scope", "normalize_scope_text"]
