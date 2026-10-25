"""Định dạng và tính toán học phí, tín chỉ, hệ thống học kỳ và thanh toán học phí."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.config.settings import settings
from .evidence_utils import _evidence_sentences, _evidence_text_lines
from .query_analysis import QueryAnalysis, normalize_question
from .query_semantics import (
    excludes_optional_english_test,
    is_fee_table_page_text,
    is_semester_fee_total_question,
    is_tuition_increase_question,
    mentions_optional_english_test,
    should_include_optional_english_fee,
)


def _evidence_tuition_answer(evidence: Any) -> str | None:
    """Lấy đúng dòng học phí để fallback khi model cục bộ trả lời lỗi.

    Fallback này chỉ giữ dòng có nhãn ``Học phí`` và loại dòng ``Tổng chi phí``;
    vì vậy không thể đổi tên hoặc gộp các khoản thu trong bằng chứng. Chỉ dùng
    record tuition canonical đã xác minh; page text hoặc fixture chung không đủ
    để bỏ qua luồng generation/validation.
    """

    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("record_type") or "") != "tuition"
            or str(metadata.get("status") or "") != "verified"
            or str(metadata.get("school_code") or "").strip().upper() != "DHV"
            or str(metadata.get("category") or "") != "hoc_phi"
        ):
            continue
        try:
            if int(metadata.get("year", 0)) != int(settings.target_year):
                continue
        except (TypeError, ValueError):
            continue
        if not str(metadata.get("source_url") or "").strip():
            continue
        for line in str(getattr(chunk, "text", "") or "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            folded = normalize_question(line)
            if "hoc phi" not in folded or "tong chi phi" in folded:
                continue
            if not re.search(r"\d[\d.,]*\s*(?:đồng|d|vnd|/)", line, re.IGNORECASE):
                continue
            return line.lstrip("• ").strip()
    return None


_FEE_ITEMS = (
    (("phi nhap hoc",), "Phí nhập học"),
    (("hoc lieu",), "Tài khoản học liệu điện tử"),
    (("kiem tra nang luc tieng anh", "kiem tra tieng anh"), "Kiểm tra năng lực Tiếng Anh"),
)


def _evidence_fee_item_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer a question about one named fee row of the verified HKI fee table."""

    normalized = normalize_question(analysis.normalized_question)
    label = next((label for markers, label in _FEE_ITEMS if any(m in normalized for m in markers)), None)
    if label is None:
        return None
    target_year = int(analysis.entities.get("year") or settings.target_year)
    found: re.Match[str] | None = None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        try:
            year = int(metadata.get("year"))
        except (TypeError, ValueError):
            continue
        if (
            str(metadata.get("category") or "") != "hoc_phi"
            or str(metadata.get("status") or "") != "verified"
            or str(metadata.get("school_code") or "").strip().upper() != "DHV"
            or year != target_year
        ):
            continue
        flattened = re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or ""))
        match = re.search(rf"{label}(\s*\(nếu có\))?\s*:?\s*(\d[\d.,]*\s*đồng)", flattened, re.IGNORECASE)
        # Prefer the table row that keeps the "(nếu có)" qualifier.
        if match and (found is None or match.group(1)):
            found = match
    if found is None:
        return None
    qualifier = " (nếu có)" if found.group(1) else ""
    return (
        f"{label}{qualifier} là một khoản riêng trong bảng phí học kỳ I năm {target_year} "
        f"của DHV, ngoài học phí: {found.group(2)}."
    )


def _evidence_tuition_total_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Calculate a semester total from the verified page-text fee breakdown."""

    normalized_question = normalize_question(analysis.normalized_question)
    if not is_semester_fee_total_question(normalized_question):
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if not is_fee_table_page_text(dict(metadata)):
            continue
        try:
            year = int(metadata.get("year", 0))
        except (TypeError, ValueError):
            continue
        expected_year = int(analysis.entities.get("year") or settings.target_year)
        if year != expected_year:
            continue
        source_url = str(metadata.get("source_url") or "").strip()
        parsed_source = urlparse(source_url)
        source_host = (parsed_source.hostname or "").lower().rstrip(".")
        if (
            parsed_source.scheme.lower() != "https"
            or not source_host
            or not (source_host == "dhv.edu.vn" or source_host.endswith(".dhv.edu.vn"))
        ):
            continue
        text = re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or ""))
        match = re.search(
            r"TỔNG\s+CHI\s+PHÍ\s+HỌC\s+KỲ\s+I\s*"
            r"(\d{1,3}(?:\.\d{3})+)\s+đồng\s*\+\s*"
            r"(\d{1,3}(?:\.\d{3})+)\s+đồng",
            text,
            re.IGNORECASE,
        )
        if not match:
            continue
        amounts = [int(value.replace(".", "")) for value in match.groups()]
        if any(amount <= 0 for amount in amounts):
            continue
        base = f"{amounts[0]:,}".replace(",", ".")
        extra = f"{amounts[1]:,}".replace(",", ".")
        folded_text = normalize_question(text)
        if mentions_optional_english_test(normalized_question) and not mentions_optional_english_test(folded_text):
            continue
        if excludes_optional_english_test(normalized_question) and not any(
            marker in folded_text for marker in ("neu co", "neu ap dung", "tuy truong hop", "chi ap dung")
        ):
            continue
        if should_include_optional_english_fee(normalized_question):
            total = amounts[0] + amounts[1]
            formatted = f"{total:,}".replace(",", ".")
            return (
                "Theo bảng chi phí nhập học, tổng chi phí học kỳ I gồm "
                f"{base} đồng và khoản kiểm tra tiếng Anh {extra} đồng, "
                f"tổng cộng {formatted} đồng."
            )
        if excludes_optional_english_test(normalized_question):
            return (
                "Theo bảng chi phí nhập học, tổng các khoản học kỳ I trước khoản kiểm tra "
                f"tiếng Anh là {base} đồng. Khoản kiểm tra tiếng Anh {extra} đồng chỉ áp dụng "
                f"nếu thuộc diện kiểm tra; trường hợp bạn nêu không cộng khoản này, nên tổng là {base} đồng."
            )
        total = amounts[0] + amounts[1]
        formatted = f"{total:,}".replace(",", ".")
        return (
            f"Theo bảng chi phí nhập học, tổng các khoản cơ bản học kỳ I là {base} đồng. "
            f"Khoản kiểm tra tiếng Anh {extra} đồng chỉ cộng thêm nếu thuộc diện kiểm tra "
            f"(tổng cộng {formatted} đồng nếu có kiểm tra tiếng Anh)."
        )
    return None


def _evidence_tuition_per_credit_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    normalized_question = normalize_question(analysis.normalized_question)
    if "tin chi" not in normalized_question:
        return None
    if any(marker in normalized_question for marker in ("bao nhieu tin chi", "so tin chi")) and not any(
        marker in normalized_question for marker in ("hoc phi", "gia", "tien", "dong")
    ):
        return None
    for line in _evidence_text_lines(evidence):
        folded = normalize_question(line)
        if "hoc phi" in folded and "tin chi" in folded and re.search(
            r"\d[\d.,]*\s*(?:đồng|dong|vnd)\s*/\s*tín\s*chỉ",
            line,
            re.IGNORECASE,
        ):
            return line.lstrip("• ").strip()
    return None


def _evidence_optional_english_fee_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    normalized_question = normalize_question(analysis.normalized_question)
    if "kiem tra nang luc tieng anh" not in normalized_question:
        return None
    if not any(marker in normalized_question for marker in ("ai cung", "tat ca", "bat buoc", "co phai", "can dong")):
        return None
    optional_row_found = False
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        # The page-text table preserves the source row/cell adjacency. A
        # separate normalized tuition record may contain conflicting fee
        # metadata, so it cannot establish this conditional row's amount.
        if str(metadata.get("record_type") or "") != "page_text":
            continue
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in str(getattr(chunk, "text", "") or "").splitlines()
        ]
        for index, line in enumerate(lines):
            if "kiem tra nang luc tieng anh" not in normalize_question(line):
                continue
            if "neu co" not in normalize_question(line):
                continue
            optional_row_found = True
            amount = re.search(r"(\d[\d.,]*)\s*(?:đồng|dong|vnd)\b", line, re.IGNORECASE)
            if amount is None and index + 1 < len(lines):
                amount = re.search(
                    r"^\s*(\d[\d.,]*)\s*(?:đồng|dong|vnd)\s*$",
                    lines[index + 1],
                    re.IGNORECASE,
                )
            if amount is not None:
                return (
                    "Không thể kết luận rằng tất cả thí sinh đều phải đóng khoản này. "
                    "Bảng phí ghi khoản kiểm tra năng lực tiếng Anh là "
                    f"{amount.group(1)} đồng (nếu có); mình chưa có thông tin cụ thể hơn về điều kiện áp dụng."
                )
    if optional_row_found:
        return (
            "Không thể kết luận rằng tất cả thí sinh đều phải đóng khoản này. "
            "Bảng phí ghi khoản kiểm tra năng lực tiếng Anh là khoản phí phát sinh nếu có; "
            "mình chưa có thông tin cụ thể hơn về điều kiện áp dụng."
        )
    return None


_PAYMENT_QUESTION_MARKERS = (
    "thanh toan", "dong tien o dau", "chuyen khoan", "ngan hang", "so tai khoan",
    "nop hoc phi the nao", "hinh thuc dong", "dong hoc phi", "nop hoc phi", "dong tien mat",
)
_BANK_ACCOUNT_MARKERS = ("chuyen khoan", "ngan hang", "so tai khoan", "tai khoan ngan hang")


def _first_evidence_line(evidence: Any, *required: str) -> str | None:
    """First full source sentence (not a wrapped PDF line) containing every marker."""
    for sentence in _evidence_sentences(evidence):
        folded = normalize_question(sentence)
        if all(marker in folded for marker in required):
            return re.sub(r"\s+", " ", sentence).lstrip("• ").strip()
    return None


def _evidence_semester_system_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer payment-channel and tuition-stability questions from verified lines only.

    The verified 2026 corpus states the UniZone payment channel and the
    "không tăng trong suốt khóa học" commitment. It does not state a bank
    account, the number of semesters per year, a minimum credit load or the
    programme length, so those questions are left to the normal no-data flow
    instead of being answered from hard-coded text.
    """

    normalized = normalize_question(analysis.normalized_question)

    if any(marker in normalized for marker in _PAYMENT_QUESTION_MARKERS):
        channel = _first_evidence_line(evidence, "unizone") or _first_evidence_line(
            evidence, "thanh toan hoc phi"
        )
        if channel is None:
            return None
        # Drop a merged heading such as "Hình thức 2: Nhập học trực tuyến".
        subject = re.search(r"\bTân sinh viên\b", channel)
        if subject:
            channel = channel[subject.start():]
        answer = f"Theo hướng dẫn nhập học của DHV: {channel.rstrip('.')}."
        if any(marker in normalized for marker in _BANK_ACCOUNT_MARKERS):
            answer += (
                " Tài liệu tuyển sinh đã kiểm chứng chưa nêu số tài khoản ngân hàng; bạn nên "
                "thanh toán theo kênh trên hoặc hỏi tư vấn viên tuyển sinh trước khi chuyển tiền."
            )
        return answer

    if is_tuition_increase_question(normalized) or any(
        marker in normalized for marker in ("co tang khong", "tang hoc phi")
    ):
        # Table rows have no full stops, so a "sentence" may swallow the fee
        # table; keep only the clause that states the commitment itself.
        flattened = " ".join(
            re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or ""))
            for chunk in getattr(evidence, "chunks", ()) or ()
        )
        # A sentence ends at "." followed by a space or the end; "1.250.000" is not an end.
        commitment = re.search(r"(Học phí được tính.{0,160}?không tăng.{0,120}?\.)(?=\s|$)", flattened)
        if commitment is None:
            commitment = re.search(r"((?:Học phí|Nhà trường).{0,160}?không tăng.{0,120}?\.)(?=\s|$)", flattened)
        return commitment.group(1).strip() if commitment else None

    return None


# --- HKI fee-table reasoning -------------------------------------------------
# Every amount below is read from the verified page text of the fee table (the
# same trust boundary as the semester-total answer); nothing is invented.

_AMOUNT_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+)\s*đồng", re.IGNORECASE)
_FEE_ROW_LABELS = (
    ("hoc phi hki", "Học phí HKI (10 tín chỉ)"),
    ("phi nhap hoc", "Phí nhập học"),
    ("tai khoan hoc lieu dien tu", "Tài khoản học liệu điện tử"),
    ("kiem tra nang luc tieng anh", "Kiểm tra năng lực Tiếng Anh (nếu có)"),
)
_FEE_COMPOSITION_MARKERS = (
    "ngoai hoc phi", "ngoai tien hoc", "ngoai tien hoc phi", "khoan nao", "nhung khoan",
    "cac khoan", "khoan gi", "co nam trong", "nam trong", "toan bo", "chi tinh tien hoc",
    "dong them", "con phai dong",
)
_PRE_SCHOLARSHIP_MARKERS = (
    "tru hoc bong", "da tru", "chua tru", "da giam", "chua giam", "truoc hoc bong",
    "chua ap dung hoc bong", "thay doi muc hoc phi", "lam thay doi", "so chua giam",
)
_PAYABLE_MARKERS = ("dong bao nhieu", "phai dong", "con dong", "can dong", "con lai", "so tien")


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " đồng"


def _fee_rows_text(rows: list[tuple[str, int]]) -> str:
    """``phí nhập học 1.500.000 đồng; kiểm tra năng lực Tiếng Anh (nếu có) 250.000 đồng``."""
    return "; ".join(f"{label[0].lower()}{label[1:]} {_money(amount)}" for label, amount in rows)


def _parse_vnd(text: str) -> int | None:
    """Parse ``12,5 triệu`` / ``12.500.000`` style amounts from a question."""
    million = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:trieu|tr)\b", text)
    if million:
        return int(round(float(million.group(1).replace(",", ".")) * 1_000_000))
    exact = re.search(r"\b(\d{1,3}(?:\.\d{3}){2,})\b", text)
    return int(exact.group(1).replace(".", "")) if exact else None


def _fee_table(analysis: QueryAnalysis, evidence: Any) -> dict[str, object] | None:
    """Read rows, per-credit price and the pre-scholarship note from page text."""

    expected_year = int(analysis.entities.get("year") or settings.target_year)
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if not is_fee_table_page_text(dict(metadata)):
            continue
        try:
            if int(metadata.get("year", 0)) != expected_year:
                continue
        except (TypeError, ValueError):
            continue
        lines = [re.sub(r"\s+", " ", line).strip() for line in str(getattr(chunk, "text", "") or "").splitlines()]
        lines = [line for line in lines if line]
        rows: list[tuple[str, int]] = []
        for marker, label in _FEE_ROW_LABELS:
            for index, line in enumerate(lines):
                if marker not in normalize_question(line):
                    continue
                amount = _AMOUNT_RE.search(line) or (
                    _AMOUNT_RE.fullmatch(lines[index + 1]) if index + 1 < len(lines) else None
                )
                if amount:
                    rows.append((label, int(amount.group(1).replace(".", ""))))
                    break
        if len(rows) < 2 or rows[0][0] != _FEE_ROW_LABELS[0][1]:
            continue
        per_credit = re.search(r"(\d{1,3}(?:\.\d{3})+)\s*đồng\s*/\s*tín\s*chỉ", " ".join(lines), re.IGNORECASE)
        folded_text = normalize_question(" ".join(lines))
        return {
            "rows": rows,
            "per_credit": int(per_credit.group(1).replace(".", "")) if per_credit else None,
            "pre_scholarship": "chua ap dung hoc bong" in folded_text,
            "year": expected_year,
        }
    return None


def _evidence_fee_breakdown_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer composition, credit arithmetic and scholarship-adjusted fee questions."""

    question = normalize_question(analysis.normalized_question)
    table = _fee_table(analysis, evidence)
    if table is None:
        return None
    rows: list[tuple[str, int]] = table["rows"]  # type: ignore[assignment]
    tuition_label, tuition = rows[0]
    per_credit = table["per_credit"]
    year = table["year"]
    credits_match = re.search(r"\b(\d{1,2})\s*tin chi\b", question)

    # 1) "N tín chỉ thì tiền học bao nhiêu?"
    if per_credit and credits_match and "bao nhieu tin chi" not in question and any(
        marker in question for marker in ("bao nhieu", "uoc tinh", "tien hoc", "hoc phi", "het bao")
    ):
        credits = int(credits_match.group(1))
        if credits == 1:
            return f"Học phí năm {year} của DHV là {_money(per_credit)}/tín chỉ (chưa trừ học bổng)."
        return (
            f"Học phí năm {year} của DHV là {_money(per_credit)}/tín chỉ, nên {credits} tín chỉ "
            f"tương ứng khoảng {_money(credits * per_credit)} (chưa gồm các khoản thu khác và chưa trừ học bổng)."
        )

    # 2) "12,5 triệu tương ứng bao nhiêu tín chỉ?"
    asked_amount = _parse_vnd(question)
    if per_credit and asked_amount and any(m in question for m in ("bao nhieu tin chi", "may tin chi", "so tin chi")):
        if asked_amount % per_credit == 0:
            return (
                f"Với mức {_money(per_credit)}/tín chỉ, {_money(asked_amount)} tương ứng "
                f"{asked_amount // per_credit} tín chỉ."
            )
        return None

    # 3) "Học bổng 70% học phí chuẩn HK1 thì phải đóng bao nhiêu?"
    percent = re.search(r"\b(\d{1,3})\s*%", question)
    if percent and "hoc phi" in question and any(marker in question for marker in _PAYABLE_MARKERS):
        rate = int(percent.group(1))
        if 0 < rate <= 100:
            support = tuition * rate // 100
            others = _fee_rows_text(rows[1:])
            return (
                f"Học phí chuẩn HK1 năm {year} là {_money(tuition)}. Hỗ trợ {rate}% tương đương "
                f"{_money(support)}, nên phần học phí HK1 còn phải đóng là {_money(tuition - support)}. "
                + (f"Các khoản thu khác được tính riêng: {others}." if others else "")
            ).strip()

    # 4) "Học phí đã trừ học bổng chưa?" / "Học bổng có làm thay đổi đơn giá?"
    if "hoc bong" in question and "hoc phi" in question and any(m in question for m in _PRE_SCHOLARSHIP_MARKERS):
        if not table["pre_scholarship"]:
            return None
        unit = f", tương ứng {_money(per_credit)}/tín chỉ" if per_credit else ""
        lead = "Không." if "thay doi" in question else "Chưa."
        return (
            f"{lead} {tuition_label} năm {year} là {_money(tuition)}{unit}; đây là mức chưa áp dụng "
            "học bổng và các chính sách hỗ trợ. Đơn giá tín chỉ giữ nguyên, học bổng (nếu được xét) "
            "sẽ giảm vào số tiền bạn phải đóng."
        )

    # 5) "Ngoài học phí còn những khoản nào?" / "Phí nhập học có nằm trong học phí không?"
    if any(marker in question for marker in _FEE_COMPOSITION_MARKERS) and len(rows) >= 2:
        extras = _fee_rows_text(rows[1:])
        yes_no = any(m in question for m in ("co nam trong", "nam trong", "toan bo", "co phai"))
        lead = "Không. " if yes_no else ""
        note = " (mức chưa áp dụng học bổng)" if table["pre_scholarship"] else ""
        return (
            f"{lead}Theo bảng phí học kỳ I năm {year} của DHV{note}, {tuition_label[0].lower()}{tuition_label[1:]} là {_money(tuition)}; "
            f"các khoản thu khác được tính riêng: {extras}."
        )
    return None
