"""Định dạng và tính toán học phí, tín chỉ, hệ thống học kỳ và thanh toán học phí."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.config.settings import settings
from .evidence_utils import _evidence_sentences
from .query_analysis import QueryAnalysis, normalize_question
from .query_semantics import (
    FEE_ROW_SPECS,
    FeeRequest,
    analyze_fee_request,
    is_fee_table_page_text,
    is_tuition_increase_question,
)


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


# --- Verified tuition fee-table reasoning -----------------------------------
# The parser and formatter share FEE_ROW_SPECS. All fee-table reads and all
# arithmetic pass through _fee_table / answer_fee_request.

_AMOUNT_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+)\s*đồng", re.IGNORECASE)
_PRE_SCHOLARSHIP_MARKERS = (
    "tru hoc bong", "da tru", "chua tru", "da giam", "chua giam", "truoc hoc bong",
    "chua ap dung hoc bong", "thay doi muc hoc phi", "lam thay doi", "so chua giam",
)
_PAYABLE_MARKERS = ("dong bao nhieu", "phai dong", "con dong", "can dong", "con lai", "so tien")
_REQUIRED_FEE_ROWS = frozenset({"tuition_hki", "enrollment_fee", "learning_materials"})


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " đồng"


def _fee_rows_text(rows: list[tuple[str, int]]) -> str:
    return "; ".join(f"{label[0].lower()}{label[1:]} {_money(amount)}" for label, amount in rows)


def _parse_vnd(text: str) -> int | None:
    """Parse user-entered ``12,5 triệu`` / ``12.500.000`` amounts."""
    million = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:trieu|tr)\b", text)
    if million:
        try:
            return int(round(float(million.group(1).replace(",", ".")) * 1_000_000))
        except (OverflowError, ValueError):
            return None
    exact = re.search(r"\b(\d{1,3}(?:\.\d{3}){2,})\b", text)
    if exact is None:
        return None
    try:
        return int(exact.group(1).replace(".", ""))
    except ValueError:
        return None


def _trusted_dhv_url(value: object) -> bool:
    source_url = str(value or "").strip()
    try:
        parsed_source = urlparse(source_url)
        source_host = (parsed_source.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return (
        parsed_source.scheme.lower() == "https"
        and bool(source_host)
        and (source_host == "dhv.edu.vn" or source_host.endswith(".dhv.edu.vn"))
    )


def _trusted_fee_table_metadata(metadata: dict[str, object]) -> bool:
    return is_fee_table_page_text(metadata) and _trusted_dhv_url(metadata.get("source_url"))


def _fee_table(analysis: QueryAnalysis, evidence: Any) -> dict[str, object] | None:
    """Read verified DHV fee rows and unit price once for every formatter."""

    expected_year = int(analysis.entities.get("year") or settings.target_year)
    partial_table: dict[str, object] | None = None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        try:
            year = int(metadata.get("year", 0))
        except (OverflowError, TypeError, ValueError):
            continue
        if year != expected_year:
            continue
        if _trusted_fee_table_metadata(metadata):
            raw_text = str(getattr(chunk, "text", "") or "").replace("\\n", "\n")
            lines = [
                re.sub(r"\s+", " ", line).strip()
                for line in raw_text.splitlines()
            ]
            lines = [line for line in lines if line]
            row_values: dict[str, int] = {}
            row_labels: dict[str, str] = {}
            for key, markers, label in FEE_ROW_SPECS:
                for index, line in enumerate(lines):
                    if not any(marker in normalize_question(line) for marker in markers):
                        continue
                    amount = _AMOUNT_RE.search(line) or (
                        _AMOUNT_RE.fullmatch(lines[index + 1]) if index + 1 < len(lines) else None
                    )
                    if amount:
                        row_values[key] = int(amount.group(1).replace(".", ""))
                        row_labels[key] = label
                        break
            per_credit = re.search(
                r"(\d{1,3}(?:\.\d{3})+)\s*(?:đồng|VNĐ|VND)\s*/\s*tín\s*chỉ",
                " ".join(lines),
                re.IGNORECASE,
            )
            folded_text = normalize_question(" ".join(lines))
            fee_total = re.search(
                r"TỔNG\s+CHI\s+PHÍ\s+HỌC\s+KỲ\s+I\s*[:：]?\s*"
                r"(\d{1,3}(?:\.\d{3})+)\s*đồng\s*\+\s*"
                r"(\d{1,3}(?:\.\d{3})+)\s*đồng",
                " ".join(lines),
                re.IGNORECASE,
            )
            table = {
                "rows": tuple(
                    (row_labels[key], row_values[key])
                    for key, _markers, _label in FEE_ROW_SPECS
                    if key in row_values
                ),
                "row_values": row_values,
                "per_credit": int(per_credit.group(1).replace(".", "")) if per_credit else None,
                "pre_scholarship": "chua ap dung hoc bong" in folded_text,
                "published_base_total": int(fee_total.group(1).replace(".", "")) if fee_total else None,
                "published_optional_fee": int(fee_total.group(2).replace(".", "")) if fee_total else None,
                "year": expected_year,
            }
            if _REQUIRED_FEE_ROWS.issubset(row_values):
                return table
            if table["per_credit"] or row_values or table["published_base_total"]:
                partial_table = table

    # Canonical verified tuition records can provide the unit rate when the
    # page table was not retrieved. They never establish fee rows or totals.
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        try:
            year = int(metadata.get("year", 0))
        except (OverflowError, TypeError, ValueError):
            continue
        if (
            str(metadata.get("category") or "") != "hoc_phi"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").strip().upper() != "DHV"
            or year != expected_year
            or not _trusted_dhv_url(metadata.get("source_url"))
        ):
            continue
        amount = re.search(
            r"(\d{1,3}(?:\.\d{3})+)\s*(?:đồng|VNĐ|VND)\s*/\s*tín\s*chỉ",
            str(getattr(chunk, "text", "") or ""),
            re.IGNORECASE,
        )
        if amount:
            rate_only = {
                "rows": (), "row_values": {},
                "per_credit": int(amount.group(1).replace(".", "")),
                "pre_scholarship": False, "year": expected_year,
            }
            if partial_table is not None:
                partial_table["per_credit"] = rate_only["per_credit"]
                return partial_table
            return rate_only
    return partial_table


def _fee_result(
    answer: str | None,
    request: FeeRequest,
    *,
    answered: set[str] | None = None,
    missing: set[str] | None = None,
) -> dict[str, object]:
    answered_topics = answered or set()
    ambiguous_topics = set(request.ambiguous_topics)
    missing_topics = (set(request.topics) - answered_topics - ambiguous_topics) | (missing or set())
    return {
        "answer": answer,
        "requested_topics": list(request.topics),
        "answered_topics": sorted(answered_topics),
        "ambiguous_topics": sorted(ambiguous_topics),
        "missing_topics": sorted(missing_topics),
    }


def answer_fee_request(
    analysis: QueryAnalysis,
    evidence: Any,
    request: FeeRequest | None = None,
) -> dict[str, object] | None:
    """Answer every clear fee-table part from verified rows and code arithmetic."""

    question = normalize_question(analysis.normalized_question)
    fee_request = request or analyze_fee_request(question)
    if not fee_request.is_fee_request:
        return None
    table = _fee_table(analysis, evidence)
    if table is None:
        return _fee_result(None, fee_request)

    per_credit = table.get("per_credit")
    row_values: dict[str, int] = table.get("row_values", {})  # type: ignore[assignment]
    rows: list[tuple[str, int]] = list(table.get("rows", ()))  # type: ignore[arg-type]
    rows_by_key = {key: row_values[key] for key, _markers, _label in FEE_ROW_SPECS if key in row_values}
    label_by_key = {key: label for key, _markers, label in FEE_ROW_SPECS}
    year = int(table["year"])

    relationship_answer = None
    if fee_request.relationship and fee_request.fee_items and all(
        key in rows_by_key for key in fee_request.fee_items
    ):
        selected = [
            (label_by_key[key], rows_by_key[key])
            for key in fee_request.fee_items
        ]
        item_text = "; ".join(
            f"{label} ({_money(amount)})" for label, amount in selected
        )
        if fee_request.relationship == "separate":
            relationship_answer = f"Có. {item_text} là khoản riêng ngoài học phí."
        else:
            relationship_answer = (
                f"Không nằm trong học phí; {item_text} là khoản riêng ngoài học phí."
            )

    if fee_request.semester == "HKII":
        return _fee_result(None, fee_request, missing={"HKII fee table"})

    if fee_request.scope == "annual":
        if per_credit:
            answer = (
                "Mình chưa có số liệu học phí trung bình theo năm. "
                f"Mức được công bố là {_money(int(per_credit))}/tín chỉ; tổng học phí mỗi năm "
                "phụ thuộc vào số tín chỉ thực tế đăng ký."
            )
            return _fee_result(answer, fee_request, answered={"tuition"}, missing={"annual_total"})
        return _fee_result(None, fee_request, missing={"annual_total"})

    tuition = rows_by_key.get("tuition_hki")
    english_fee = rows_by_key.get("english_test_fee")
    if english_fee is None:
        english_fee = table.get("published_optional_fee")
    base_rows = [row for row in rows if row[0] != label_by_key["english_test_fee"]]
    base_total = (
        sum(amount for _label, amount in base_rows)
        if _REQUIRED_FEE_ROWS.issubset(rows_by_key)
        else table.get("published_base_total")
    )
    percent = re.search(r"\b(\d{1,3})\s*%", question)

    if (
        per_credit and fee_request.credits and "bao nhieu tin chi" not in question
        and any(marker in question for marker in ("bao nhieu", "uoc tinh", "tien hoc", "hoc phi", "het bao"))
    ):
        amount = int(per_credit) * fee_request.credits
        answer = (
            f"Mức học phí năm {year} của DHV là {_money(int(per_credit))}/tín chỉ; "
            f"{fee_request.credits} tín chỉ tương ứng {_money(amount)} tiền học, chưa gồm khoản thu khác và chưa trừ học bổng."
        )
        return _fee_result(answer, fee_request, answered={"tuition"})

    asked_amount = _parse_vnd(question)
    if per_credit and asked_amount and any(marker in question for marker in ("bao nhieu tin chi", "may tin chi", "so tin chi")):
        if asked_amount % int(per_credit) == 0:
            answer = (
                f"Với mức {_money(int(per_credit))}/tín chỉ, {_money(asked_amount)} tương ứng "
                f"{asked_amount // int(per_credit)} tín chỉ."
            )
            return _fee_result(answer, fee_request, answered={"tuition"})
        return _fee_result(None, fee_request, missing={"credit_count"})

    if percent and tuition and "hoc phi" in question and any(marker in question for marker in _PAYABLE_MARKERS):
        rate = int(percent.group(1))
        if 0 < rate <= 100:
            support = tuition * rate // 100
            extras = _fee_rows_text([row for row in rows if row[0] != label_by_key["tuition_hki"]])
            answer = (
                f"Học phí chuẩn HK1 năm {year} là {_money(tuition)}. Hỗ trợ {rate}% tương đương "
                f"{_money(support)}, nên phần học phí HK1 còn phải đóng là {_money(tuition - support)}. "
                + (f"Các khoản thu khác được tính riêng: {extras}." if extras else "")
            ).strip()
            return _fee_result(answer, fee_request, answered={"tuition", "other_fees", "total"})

    if "hoc bong" in question and "hoc phi" in question and any(marker in question for marker in _PRE_SCHOLARSHIP_MARKERS):
        if not table.get("pre_scholarship") or tuition is None:
            return _fee_result(None, fee_request)
        rate_text = f", tương ứng {_money(int(per_credit))}/tín chỉ" if per_credit else ""
        lead = "Không." if "thay doi" in question else "Chưa."
        answer = (
            f"{lead} Học phí HKI năm {year} là {_money(tuition)}{rate_text}; đây là mức chưa áp dụng "
            "học bổng và các chính sách hỗ trợ. Đơn giá tín chỉ giữ nguyên; học bổng (nếu được xét) "
            "sẽ giảm vào số tiền bạn phải đóng."
        )
        return _fee_result(answer, fee_request, answered={"tuition", "scholarship"})

    relation_question = any(marker in question for marker in ("co nam trong", "nam trong", "toan bo", "co phai"))
    if relation_question and tuition is not None and base_total is not None:
        extras = _fee_rows_text([row for row in rows if row[0] != label_by_key["tuition_hki"]])
        answer = (
            f"Không. Theo bảng phí học kỳ I năm {year} của DHV, học phí là {_money(tuition)}; "
            f"các khoản khác được tính riêng: {extras}."
        )
        return _fee_result(answer, fee_request, answered={"tuition", "other_fees"})

    if "total" in fee_request.topics:
        if base_total is None:
            return _fee_result(None, fee_request, missing={"total"})
        details = _fee_rows_text(rows)
        if fee_request.optional_english == "include":
            if english_fee is None:
                return _fee_result(None, fee_request, missing={"english_test_fee", "total"})
            total = base_total + english_fee
            if details:
                answer = (
                    f"Theo bảng phí học kỳ I năm {year} của DHV, gồm {details}; "
                    f"tổng cộng {_money(total)}."
                )
            else:
                answer = (
                    f"Theo bảng phí học kỳ I năm {year} của DHV, tổng cơ bản {_money(base_total)} "
                    f"cộng phí kiểm tra năng lực Tiếng Anh {_money(english_fee)} thành {_money(total)}."
                )
        elif fee_request.optional_english == "exclude":
            english_note = (
                f" Khoản kiểm tra năng lực Tiếng Anh {_money(english_fee)} không được cộng vì bạn nêu không kiểm tra."
                if english_fee is not None else ""
            )
            answer = f"Tổng các khoản cơ bản học kỳ I năm {year} là {_money(base_total)}.{english_note}"
        else:
            if english_fee is None:
                answer = f"Tổng các khoản theo bảng phí học kỳ I năm {year} là {_money(base_total)}. Chi tiết: {details}."
            else:
                breakdown = f" ({details})" if details else ""
                answer = (
                    f"Tổng các khoản cơ bản học kỳ I năm {year} là {_money(base_total)}{breakdown}. "
                    f"Nếu thuộc diện kiểm tra năng lực Tiếng Anh, cộng thêm {_money(english_fee)}, "
                    f"thành tối đa {_money(base_total + english_fee)}."
                )
        answered = {"total"}
        if tuition is not None:
            answered.add("tuition")
        if len(rows) > 1:
            answered.add("other_fees")
        if fee_request.fee_items and all(key in rows_by_key for key in fee_request.fee_items):
            answered.add("specific_fee")
        if "scholarship" in fee_request.topics and fee_request.ambiguous_topics:
            answer += " Về học bổng, bạn muốn tìm học bổng đầu vào, học bổng theo học bạ, cam kết hoàn học phí hay xem tất cả?"
        if relationship_answer:
            answer = f"{relationship_answer} {answer}"
        return _fee_result(answer, fee_request, answered=answered)

    if fee_request.fee_items:
        selected = [
            (label_by_key[key], rows_by_key[key])
            for key in fee_request.fee_items if key in rows_by_key
        ]
        missing_items = set(fee_request.fee_items) - set(rows_by_key)
        if not selected:
            return _fee_result(None, fee_request, missing=missing_items)
        if relationship_answer:
            return _fee_result(
                relationship_answer,
                fee_request,
                answered={"specific_fee", "other_fees"},
                missing=missing_items,
            )
        lines = []
        for label, amount in selected:
            if "Tiếng Anh" in label:
                lines.append(f"{label}: {_money(amount)}; khoản này chỉ áp dụng nếu thuộc diện kiểm tra.")
            else:
                lines.append(f"{label}: {_money(amount)}, là khoản riêng ngoài học phí.")
        answer = " ".join(lines)
        if missing_items:
            missing_labels = [label_by_key[key] for key, _markers, label in FEE_ROW_SPECS if key in missing_items]
            answer += " Bảng phí đã kiểm chứng chưa có số tiền cho " + ", ".join(missing_labels) + "."
        return _fee_result(answer, fee_request, answered={"specific_fee", "other_fees"}, missing=missing_items)

    if "other_fees" in fee_request.topics:
        extras = [row for row in rows if row[0] != label_by_key["tuition_hki"]]
        if not extras or tuition is None:
            return _fee_result(None, fee_request, missing={"other_fees"})
        answer = (
            f"Theo bảng phí học kỳ I năm {year} của DHV, học phí là {_money(tuition)}. "
            f"Ngoài ra, các khoản thu khác gồm: {_fee_rows_text(extras)}."
        )
        return _fee_result(answer, fee_request, answered={"tuition", "other_fees"})

    if "tuition" in fee_request.topics:
        if fee_request.scope == "semester" and tuition is not None:
            rate_note = f" Đơn giá là {_money(int(per_credit))}/tín chỉ." if per_credit else ""
            answer = f"Học phí HKI (10 tín chỉ) năm {year} của DHV là {_money(tuition)}.{rate_note}"
        elif fee_request.scope == "per_credit" and per_credit:
            answer = (
                f"Học phí theo tín chỉ năm {year} của DHV là {_money(int(per_credit))}/tín chỉ. "
                "Tổng học phí phụ thuộc vào số tín chỉ thực tế đăng ký."
            )
        else:
            return _fee_result(None, fee_request, missing={"per_credit"})
        if fee_request.ambiguous_topics:
            answer += " Về học bổng, bạn muốn tìm học bổng đầu vào, học bổng theo học bạ, cam kết hoàn học phí hay xem tất cả?"
        return _fee_result(answer, fee_request, answered={"tuition"})

    if "specific_fee" in fee_request.topics or "total" in fee_request.topics:
        return _fee_result(None, fee_request)
    return _fee_result(None, fee_request)


def _fee_request_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    result = answer_fee_request(analysis, evidence)
    return str(result["answer"]) if result and result.get("answer") else None


# Compatibility adapters keep the multi-issue formatter API stable while all
# table parsing, topic selection, and arithmetic live in answer_fee_request.
def _evidence_tuition_answer(evidence: Any, analysis: QueryAnalysis | None = None) -> str | None:
    return _fee_request_answer(analysis, evidence) if analysis is not None else None


def _evidence_fee_item_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    request = analyze_fee_request(analysis.normalized_question)
    return _fee_request_answer(analysis, evidence) if "specific_fee" in request.topics else None


def _evidence_tuition_total_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    request = analyze_fee_request(analysis.normalized_question)
    return _fee_request_answer(analysis, evidence) if "total" in request.topics else None


def _evidence_tuition_per_credit_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    request = analyze_fee_request(analysis.normalized_question)
    return _fee_request_answer(analysis, evidence) if request.scope == "per_credit" else None


def _evidence_optional_english_fee_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    request = analyze_fee_request(analysis.normalized_question)
    if "english_test_fee" not in request.fee_items:
        return None
    return _fee_request_answer(analysis, evidence)


def _evidence_fee_breakdown_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    return _fee_request_answer(analysis, evidence)
