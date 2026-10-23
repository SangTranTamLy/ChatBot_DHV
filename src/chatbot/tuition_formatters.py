"""Định dạng và tính toán học phí, tín chỉ, hệ thống học kỳ và thanh toán học phí."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.config.settings import settings
from .evidence_utils import _evidence_text_lines
from .query_analysis import QueryAnalysis, normalize_question
from .query_semantics import (
    excludes_optional_english_test,
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


def _evidence_tuition_total_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Calculate a semester total from the verified page-text fee breakdown."""

    normalized_question = normalize_question(analysis.normalized_question)
    if not is_semester_fee_total_question(normalized_question):
        return None
    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("record_type") or "") != "page_text"
            or str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").strip().upper() != "DHV"
            or str(metadata.get("category") or "") != "ho_so"
        ):
            continue
        try:
            page = int(metadata.get("page", 0))
            year = int(metadata.get("year", 0))
        except (TypeError, ValueError):
            continue
        expected_year = int(analysis.entities.get("year") or settings.target_year)
        if page != 4 or year != expected_year:
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


def _evidence_semester_system_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Trả lời các câu hỏi về số học kỳ, năm học, tín chỉ tối thiểu, thanh toán học phí, cam kết học phí và thời gian đào tạo."""
    normalized = normalize_question(analysis.normalized_question)

    # 1. Hỏi về số học kỳ trong năm (1 năm nhiêu học kì, có mấy học kỳ, mấy học kì...)
    if any(marker in normalized for marker in (
        "may hoc ky", "may hoc ki", "bao nhieu hoc ky", "bao nhieu hoc ki",
        "nhieu hoc ky", "nhieu hoc ki", "1 nam", "mot nam", "so hoc ky", "so hoc ki",
    )) and not any(marker in normalized for marker in ("hoc phi hoc ky 1", "hoc phi hoc ky i", "tong chi phi")):
        return (
            "Theo quy định và cam kết đào tạo của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
            "- Trong một năm học tại DHV có **3 học kỳ**.\n"
            "- Sinh viên sẽ đăng ký tối thiểu **10 tín chỉ/học kỳ**, mang lại sự linh hoạt trong việc quản lý và tối ưu chi phí học tập.\n"
            "- Mức học phí theo tín chỉ (năm 2026) là **1.250.000 đồng/tín chỉ** (Học phí Học kỳ I tương ứng 10 tín chỉ là 12.500.000 đồng) và Nhà trường cam kết học phí ổn định, không tăng trong suốt 4 năm đào tạo."
        )

    # 2. Hỏi về số tín chỉ tối thiểu hoặc đăng ký tín chỉ mỗi học kỳ
    if any(marker in normalized for marker in (
        "toi thieu bao nhieu tin chi", "dang ky bao nhieu tin chi", "may tin chi moi hoc ky", "so tin chi toi thieu",
    )):
        return (
            "Theo quy định đào tạo của Trường Đại học Hùng Vương TP.HCM (DHV):\n"
            "- Một năm học gồm 3 học kỳ, sinh viên đăng ký **tối thiểu 10 tín chỉ/học kỳ**.\n"
            "- Mức học phí là 1.250.000 đồng/tín chỉ (năm 2026), cam kết ổn định trong suốt 4 năm đào tạo."
        )

    # 3. Hỏi về mức học phí theo tín chỉ (1 tín chỉ bao nhiêu, giá mỗi tín chỉ)
    if any(marker in normalized for marker in (
        "1 tin chi", "mot tin chi", "tin chi bao nhieu", "gia tin chi", "phi tin chi", "hoc phi theo tin chi", "moi tin chi bao nhieu",
    )):
        return (
            "Mức học phí theo tín chỉ tại Trường Đại học Hùng Vương TP.HCM (DHV):\n"
            "- Theo thông báo chính thức năm 2026: **1.250.000 đồng/tín chỉ** (Học kỳ I sinh viên đăng ký 10 tín chỉ tương ứng 12.500.000 đồng).\n"
            "- Sinh viên đăng ký tối thiểu 10 tín chỉ/học kỳ.\n"
            "- Nhà trường có chính sách học phí ổn định và cam kết không tăng học phí trong suốt 4 năm học."
        )

    # 4. Hỏi phương thức thanh toán học phí, chuyển khoản, ngân hàng
    if any(marker in normalized for marker in (
        "thanh toan", "dong tien o dau", "chuyen khoan", "ngan hang", "so tai khoan", "vietcombank", "nop hoc phi the nao",
    )):
        return (
            "Trường Đại học Hùng Vương TP.HCM (DHV) cung cấp các phương thức thanh toán học phí thuận tiện:\n"
            "1. **Thanh toán trực tiếp**: Tại Phòng Tài chính – Kế toán, Lầu 1, cơ sở 736 Nguyễn Trãi, Phường 11, Quận 5, TP.HCM.\n"
            "2. **Chuyển khoản ngân hàng**:\n"
            "   - Ngân hàng: **VietcomBank – Chi Nhánh Phú Nhuận**\n"
            "   - Số tài khoản: **21.22.23.68.68**\n"
            "   - Tên tài khoản: Trường Đại học Hùng Vương TP.HCM\n"
            "3. **Tại các cơ sở tiếp nhận nhập học**: Cơ sở 1: 194 Lê Đức Thọ, P. An Nhơn; Cơ sở 2: 37 Kinh Dương Vương, P. Phú Lâm, TP.HCM."
        )

    # 5. Hỏi cam kết học phí, học phí có tăng không
    if is_tuition_increase_question(normalized) or any(marker in normalized for marker in (
        "co tang khong", "tang hoc phi",
    )):
        return (
            "Trường Đại học Hùng Vương TP.HCM (DHV) cam kết **học phí ổn định, không tăng trong suốt 4 năm đào tạo** cho sinh viên, giúp sinh viên và gia đình hoàn toàn an tâm lập kế hoạch tài chính."
        )

    # 6. Hỏi thời gian đào tạo, học mấy năm
    if any(marker in normalized for marker in (
        "thoi gian dao tao", "dao tao may nam", "hoc may nam", "hoc bao nhieu nam",
        "may nam tot nghiep", "may nam ra truong", "may nam hoc", "chuong trinh dao tao may nam",
    )):
        return (
            "Tại Trường Đại học Hùng Vương TP.HCM, thời gian đào tạo chuẩn là **4 năm** áp dụng cho tất cả các ngành đào tạo hệ chính quy của trường."
        )

    return None
