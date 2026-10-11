"""Small, shared semantic predicates for routing and answer validation."""

from __future__ import annotations

import re
import unicodedata


def normalize_semantic_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", folded).strip()


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
