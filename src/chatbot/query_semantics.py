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
    words = (question or "").split(" ")
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
