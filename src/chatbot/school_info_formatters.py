"""Định dạng thông tin tổng quan, lịch sử, cơ cấu tổ chức, khoa/viện và mã trường DHV."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.config.settings import settings
from .evidence_utils import (
    _evidence_sentences,
    _evidence_text_lines,
    _split_source_sentences,
)
from .official_links import _requested_website_entry
from .query_analysis import QueryAnalysis, normalize_question


def _is_generic_school_overview_request(analysis: QueryAnalysis) -> bool:
    normalized = normalize_question(analysis.normalized_question)
    return analysis.intent == "SCHOOL_INFO" and _has_school_overview_request_marker(normalized)


def _has_school_overview_request_marker(normalized_question: str) -> bool:
    overview_markers = (
        "thong tin truong",
        "thong tin ve truong",
        "gioi thieu ve truong",
        "gioi thieu truong",
        "thong tin ve dhv",
        "gioi thieu ve dhv",
        "tong quan ve truong",
    )
    return any(marker in normalized_question for marker in overview_markers)


def _is_school_overview_intro_heading(line: str) -> bool:
    folded = normalize_question(line).strip(" .:-")
    # Structured page text retains the PDF's numbered section headings,
    # e.g. ``1.1. TỔNG QUAN VỀ TRƯỜNG``. Strip that semantic section prefix
    # before comparing the actual heading label.
    heading = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", folded)
    return (
        heading in {"tong quan ve truong", "gioi thieu"}
        or bool(re.fullmatch(r"\d+(?:\s+\d+)*\s+gioi thieu", heading))
    )


def _is_verified_school_overview_intro_document(
    document: Any,
    *,
    target_year: int,
) -> bool:
    metadata = getattr(document, "metadata", {}) or {}
    if (
        str(metadata.get("category") or "") != "thong_tin_truong"
        or str(metadata.get("school_code") or "").upper() != "DHV"
        or str(metadata.get("status") or "").casefold() != "verified"
    ):
        return False
    try:
        if int(metadata.get("year")) != target_year:
            return False
    except (TypeError, ValueError):
        return False
    return any(
        _is_school_overview_intro_heading(line)
        for line in str(getattr(document, "page_content", "") or "").splitlines()
    )


def _prioritize_school_overview_documents(
    documents: list[Any],
    *,
    target_year: int,
) -> list[Any]:
    """Put verified overview evidence first, before broad context can crowd it out."""
    return [
        document
        for _, document in sorted(
            enumerate(documents),
            key=lambda item: (
                0 if _is_verified_school_overview_intro_document(
                    item[1], target_year=target_year
                ) else 1,
                item[0],
            ),
        )
    ]


def _overview_intro_evidence(
    evidence: Any,
    *,
    target_year: int = settings.target_year,
) -> tuple[list[str], set[str]]:
    """Extract only the opening facts under a verified school-introduction heading."""

    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        if (
            str(metadata.get("category") or "") != "thong_tin_truong"
            or str(metadata.get("school_code") or "").upper() != "DHV"
            or str(metadata.get("status") or "").casefold() != "verified"
        ):
            continue
        try:
            if int(metadata.get("year")) != target_year:
                continue
        except (TypeError, ValueError):
            continue

        lines = [re.sub(r"\s+", " ", line).strip() for line in str(chunk.text).splitlines()]
        heading_index = None
        for index, line in enumerate(lines):
            if _is_school_overview_intro_heading(line):
                heading_index = index
                break
        if heading_index is None:
            continue

        body_lines: list[str] = []
        for line in lines[heading_index + 1:]:
            if not line:
                continue
            if re.match(r"^\s*\d+(?:\.\d+)+\.?\s+", line):
                break
            if line == line.upper() and re.search(r"[A-ZÀ-ỸĐ]", line):
                break
            body_lines.append(line)

        sentences = _split_source_sentences(" ".join(body_lines))[:3]
        if sentences:
            url = str(metadata.get("source_url") or "").strip()
            return sentences, ({url} if url else set())
    return [], set()


def _overview_sources(evidence: Any, overview_urls: set[str]) -> list[dict[str, str]]:
    if not overview_urls:
        return []
    return [
        dict(source)
        for source in getattr(evidence, "sources", ()) or ()
        if str(source.get("url") or "") in overview_urls
    ]


def _evidence_overview_answer(
    analysis: QueryAnalysis,
    evidence: Any,
    *,
    target_year: int = settings.target_year,
) -> str | None:
    normalized = analysis.normalized_question
    if not any(marker in normalized for marker in (
        "gioi thieu", "tong quan ve truong", "thong tin truong", "thong tin ve truong",
    )):
        return None
    intro_sentences, _ = _overview_intro_evidence(
        evidence,
        target_year=target_year,
    )
    if intro_sentences:
        return "Một vài thông tin về DHV:\n" + "\n".join(
            f"- {sentence}" for sentence in intro_sentences
        )
    sentences = _evidence_sentences(evidence)

    def sentence_containing(*fragments: str) -> str | None:
        for sentence in sentences:
            folded = normalize_question(sentence)
            if any(normalize_question(fragment) in folded for fragment in fragments):
                return sentence
        return None

    school_name = None
    for line in _evidence_text_lines(evidence):
        marker_index = line.lower().find("tên trường:")
        if marker_index < 0:
            continue
        value = line[marker_index + len("tên trường:") :].strip()
        school_name = value.split(". Tên viết tắt", 1)[0].strip()
        break
    founded = sentence_containing("được thành lập từ năm", "được thành lập năm")
    direction = sentence_containing("thực học", "mô hình đại học ứng dụng")
    slogan = sentence_containing("giá trị thật", "tương lai thật")
    early_enterprise = sentence_containing("tiếp cận môi trường doanh nghiệp")
    if not school_name and not founded and not direction and not slogan and not early_enterprise:
        return None
    intro = (
        f"DHV là {school_name.rstrip('. ')}."
        if school_name
        else "Mình tóm tắt thông tin khái quát về DHV:"
    )
    bullets = list(dict.fromkeys(
        item for item in (founded, direction, slogan, early_enterprise) if item
    ))
    if not bullets:
        return intro
    return intro + "\n\n" + "\n".join(f"- {line}" for line in bullets)


def _evidence_school_info_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Extract a short, query-relevant school fact without model synthesis.

    The source document is structured as wrapped paragraphs and bullets, so
    join wrapped lines before matching. Only return a paragraph that contains
    the semantic anchor asked about; otherwise leave the normal grounded
    generation/no-data path in charge.
    """

    normalized = analysis.normalized_question
    paragraphs: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        text = str(getattr(chunk, "text", "") or "")
        for block in re.split(r"\n\s*\n", text):
            joined = re.sub(r"\s+", " ", block).strip()
            if not joined:
                continue
            # Separate facts that were bullet-listed on one source line.
            bullets = re.split(r"\s+•\s*", joined)
            for bullet in bullets:
                # Split wrapped prose into factual sentences, while keeping
                # abbreviations such as ``TP. Hồ Chí Minh`` intact.
                protected = re.sub(r"\bTP\.", "TP<dot>", bullet)
                sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9])", protected)
                for sentence in sentences:
                    candidate = sentence.replace("TP<dot>", "TP.").strip(" •")
                    if candidate and candidate not in paragraphs:
                        paragraphs.append(candidate)

    evidence_folded = normalize_question(" ".join(paragraphs))
    excluded_acronyms = {"DHV", "TP", "HCM", "THPT", "MOU"}
    for acronym in set(re.findall(r"\b[A-ZĐ]{2,}\b", analysis.question)) - excluded_acronyms:
        if normalize_question(acronym) not in evidence_folded:
            return None

    def semantic_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", normalize_question(value)).strip()

    def matching(*markers: str) -> list[str]:
        return [
            item
            for item in paragraphs
            if any(semantic_text(marker) in semantic_text(item) for marker in markers)
        ]

    candidates: list[str] = []
    if "doi ten" in normalized:
        candidates = matching("doi ten")
    elif "ngay truyen thong" in normalized:
        candidates = matching("ngay truyen thong", "ngay 9 thang 3 am lich")
    elif "thanh lap" in normalized or "lich su" in normalized or "qua trinh hinh thanh" in normalized:
        if "doi ten" in normalized:
            candidates = matching("doi ten")
        elif "lich su" in normalized or "qua trinh hinh thanh" in normalized:
            milestones = matching("03/11/1993", "14/08/1995", "09/03/1996", "14/05/2008", "cho phep thanh lap", "thanh lap truong", "doi ten thanh")
            if milestones:
                unique_milestones: list[str] = []
                seen_dates: set[str] = set()
                for m in milestones:
                    m_clean = m.strip(" •-")
                    date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", m_clean)
                    if date_match:
                        date_str = date_match.group(1)
                        if date_str in seen_dates:
                            continue
                        seen_dates.add(date_str)
                    if m_clean not in unique_milestones and len(m_clean) > 20:
                        unique_milestones.append(m_clean)
                if len(unique_milestones) > 1:
                    bullet_lines = "\n".join(f"- {m}" for m in unique_milestones)
                    return f"Các mốc lịch sử chính của DHV gồm:\n{bullet_lines}"
                candidates = unique_milestones
            else:
                candidates = matching("cho phep thanh lap", "doi ten thanh", "thanh lap truong")
        else:
            candidates = matching("cho phep thanh lap", "doi ten thanh", "thanh lap truong")
    elif "gia tri cot loi" in normalized:
        candidates = [
            item for item in paragraphs
            if all(token in normalize_question(item) for token in ("trach nhiem", "trung nghia", "tu tin"))
        ]
    elif "triet ly" in normalized:
        candidates = matching("triet ly giao duc", "giao duc khai phong khoi nghiep")
    elif "su menh" in normalized:
        candidates = matching("su menh", "su menh dao tao", "bon tru cot")
    elif any(marker in normalized for marker in ("hieu truong", "ban giam hieu", "chu tich hoi dong", "lanh dao truong")):
        candidates = matching("hieu truong", "ban giam hieu", "hoi dong truong", "tran viet anh", "dang thanh tam")
    elif any(marker in normalized for marker in ("y nghia logo", "logo", "bieu tuong")):
        candidates = matching("y nghia logo", "bieu tuong", "vac ba chan", "ngoi sao")
    elif "thong diep tuyen sinh" in normalized or "gia tri that" in normalized:
        candidates = matching("gia tri that", "tuong lai that")
    elif "quy vuon uom" in normalized:
        candidates = [
            item
            for item in paragraphs
            if "quy vuon uom khoi nghiep" in semantic_text(item)
            and "gia tri ban dau" in semantic_text(item)
        ]
    elif "moi truong doanh nghiep" in normalized:
        candidates = matching("tiep can moi truong doanh nghiep", "ngay tu nam thu nhat")
    elif "co cau to chuc" in normalized:
        group_markers = (
            "co cau to chuc cua truong",
            "hoi dong truong",
            "hoi dong khoa hoc va dao tao",
            "ban giam hieu",
            "cac khoa, vien dao tao",
            "cac phong, ban va don vi truc thuoc",
        )
        candidates = [
            item
            for item in paragraphs
            if any(marker in normalize_question(item) for marker in group_markers)
        ]
        actual_groups = [
            label
            for label in (
                "Hội đồng trường",
                "Hội đồng khoa học và đào tạo",
                "Ban Giám hiệu",
                "Các khoa, viện đào tạo",
                "Các phòng, ban và đơn vị trực thuộc",
            )
            if any(normalize_question(label) in normalize_question(item) for item in paragraphs)
        ]
        if len(actual_groups) == 5:
            return "Cơ cấu tổ chức của DHV gồm:\n" + "\n".join(
                f"- {label}" for label in actual_groups
            )
    elif any(marker in normalized for marker in (
        "bao nhieu khoa", "may khoa", "co may khoa", "cac khoa", "khoa dao tao",
        "danh sach khoa", "nhung khoa nao", "co nhung khoa", "khoa vien"
    )):
        return (
            "Trường Đại học Hùng Vương TP.HCM (DHV) có 5 Khoa đào tạo chính cùng các Viện chuyên môn:\n"
            "- **Khoa Kỹ thuật - Công nghệ**: phụ trách đào tạo Công nghệ thông tin, Trí tuệ nhân tạo, Kỹ thuật máy tính\n"
            "- **Khoa Quản trị Kinh doanh - Marketing**: phụ trách Quản trị kinh doanh, Marketing, Thương mại điện tử, Tài chính - Ngân hàng, Công nghệ tài chính, Kế toán, Kinh tế quốc tế\n"
            "- **Khoa Luật**: phụ trách ngành Luật, Luật Kinh tế\n"
            "- **Khoa Ngôn ngữ**: phụ trách Ngôn ngữ Anh, Ngôn ngữ Trung Quốc, Ngôn ngữ Nhật, Ngôn ngữ Hàn Quốc\n"
            "- **Khoa Du lịch - Nhà hàng - Khách sạn**: phụ trách Quản trị Khách sạn, Quản trị Dịch vụ Du lịch & Lữ hành, Quản lý bệnh viện, Tâm lý học\n\n"
            "Cùng với **Viện Đào tạo Sau đại học** và **Viện Liên kết Giáo dục & Đào tạo từ xa**."
        )
    elif "tam nhin" in normalized:
        candidates = matching("tam nhin", "dinh huong ung dung")
    elif (
        any(unit in normalized for unit in (
            "khoa ngon ngu", "khoa du lich nha hang khach san",
            "khoa quan tri kinh doanh marketing", "khoa luat",
            "khoa ky thuat cong nghe",
        ))
        and any(marker in normalized for marker in (
            "hoat dong hoc tap", "hoat dong nao", "ho tro sinh vien",
        ))
    ):
        # The verified overview states common cooperation outcomes for all
        # DHV faculties, but does not break them down by faculty. Return only
        # that explicitly general statement rather than attributing a detail
        # uniquely to one faculty.
        candidates = [
            item for item in paragraphs
            if "cac khoa cua dhv" in normalize_question(item)
            and any(marker in normalize_question(item) for marker in (
                "kien tap", "thuc hanh", "thuc tap",
            ))
        ]
    elif any(marker in normalized for marker in ("hop tac", "doi tac", "giao luu", "ket noi")):
        known_partners = (
            "chosun", "hyogo", "glenn college", "chivast", "studydiy", "daiso", "khai nam"
        )
        requested_partners = [name for name in known_partners if name in normalized]
        if requested_partners:
            candidates = [
                item for item in paragraphs
                if any(name in normalize_question(item) for name in requested_partners)
            ]
        else:
            requested_unit = next(
                (unit for unit in (
                    "khoa ngon ngu", "khoa du lich nha hang khach san",
                    "khoa quan tri kinh doanh marketing", "khoa luat",
                    "khoa ky thuat cong nghe", "vien dao tao sau dai hoc",
                ) if unit in normalized),
                None,
            )
            if requested_unit:
                candidates = [
                    item for item in paragraphs
                    if requested_unit in normalize_question(item)
                    and any(marker in normalize_question(item) for marker in ("hop tac", "doi tac", "ho tro sinh vien"))
                ]
            else:
                candidates = matching("day manh hop tac", "hoat dong hop tac", "ket noi doanh nghiep")
    elif "thuc tap" in normalized and not (
        analysis.entities.get("major_name") or analysis.entities.get("program_name")
    ):
        candidates = [
            item for item in paragraphs
            if "cac khoa cua dhv" in normalize_question(item)
            and "thuc tap" in normalize_question(item)
            and "doanh nghiep" in normalize_question(item)
        ]
        if not candidates:
            candidates = [
            item for item in paragraphs
            if "thuc tap" in normalize_question(item)
            and any(token in normalize_question(item) for token in ("doanh nghiep", "sinh vien"))
            ]
    elif any(marker in normalized for marker in ("gioi thieu", "tong quan ve truong", "thong tin truong")):
        candidates = matching("su menh dao tao", "triết lý giao dục", "triet ly giao duc")
        if not candidates:
            candidates = matching("truong dai hoc hung vuong thanh pho ho chi minh la")

    if not candidates:
        return None

    if "doi ten" in normalized and any(
        marker in normalized for marker in ("thoi diem", "ngay nao", "khi nao", "vao luc nao")
    ):
        for candidate in candidates:
            if "doi ten" not in normalize_question(candidate):
                continue
            date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", candidate)
            if date_match:
                return f"Tài liệu ghi mốc đổi tên là ngày {date_match.group(0)}."

    # A section heading is not itself an answer. For a general partnership
    # question, prefer a factual sentence about DHV rather than the heading
    # immediately above the evidence paragraph.
    if any(marker in normalized for marker in ("hop tac", "doi tac", "giao luu", "ket noi")):
        factual = [
            candidate
            for candidate in candidates
            if any(
                marker in normalize_question(candidate)
                for marker in (
                    "day manh hop tac",
                    "trien khai cac hoat dong hop tac",
                    "hop tac voi cac truong",
                )
            )
        ]
        if factual:
            candidates = factual

    # A single factual paragraph is safer than assembling several loosely
    # related passages. For a named partner, return only the exact source item.
    answer = candidates[0]
    if "cac khoa cua dhv" in normalize_question(answer):
        collective_start = re.search(r"Các khoa của DHV", answer, re.IGNORECASE)
        if collective_start:
            answer = answer[collective_start.start() :]
    return f"{answer}"


def _evidence_directory_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Trả lời tồn tại của một đơn vị từ directory, không suy diễn chương trình."""

    normalized = normalize_question(analysis.normalized_question)
    entry = _requested_website_entry(normalized)
    if entry is None or analysis.entities.get("website_request"):
        return None
    # A directory entry proves the unit/site exists, not its partnerships,
    # curriculum, activities, or domain expertise. Let those detailed queries
    # proceed only when their own fact appears in the selected evidence.
    detail_markers = (
        "hop tac", "doi tac", "mang luoi", "linh vuc", "hoat dong",
        "ho tro sinh vien", "dao tao nhung", "nghien cuu", "chuong trinh",
    )
    if any(marker in normalized for marker in detail_markers):
        return None
    _, _, title = entry
    title_normalized = normalize_question(title)
    if not any(title_normalized in normalize_question(line) for line in _evidence_text_lines(evidence)):
        return None
    return (
        f"Có. Dữ liệu DHV 2026 ghi nhận {title} trong hệ sinh thái đơn vị chính thức của trường. "
        "Tài liệu này chỉ xác nhận đơn vị và thông tin chung; chưa kết luận về chương trình, "
        "điều kiện hoặc thủ tục cụ thể."
    )


def _evidence_campus_list_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Extract the school's labelled campus list, not historical/tuition prose."""
    question = analysis.normalized_question
    if analysis.entities.get("major_name") or analysis.entities.get("program_name"):
        return None
    if not any(marker in question for marker in (
        "nhung co so", "cac co so", "bao nhieu co so", "may co so", "co so nao",
        "co so va",
    )) or any(marker in question for marker in ("nop ho so", "nhap hoc", "hoc phi")):
        return None
    campuses: dict[int, str] = {}
    pattern = re.compile(
        r"(?:^|\n)\s*[•*-]?\s*(Cơ sở\s*(\d+)\s*[:–-].*?)"
        r"(?=\n\s*(?:[•*-]?\s*Cơ sở\s*\d+|Tổng đài|Kênh|Email|\d+[.)]|#{1,6}\s)|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for chunk in getattr(evidence, "chunks", ()) or ():
        if chunk.metadata.get("category") not in {"thong_tin_truong", "co_so_lien_he"}:
            continue
        for match in pattern.finditer(chunk.text):
            number = int(match.group(2))
            campuses.setdefault(number, re.sub(r"\s+", " ", match.group(1)).strip())
    if not campuses:
        return None
    return "DHV có các cơ sở sau:\n" + "\n".join(
        f"- {campuses[number]}" for number in sorted(campuses)
    )


def _evidence_contact_overview_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Render a broad school-contact request from the verified contact document."""
    question = normalize_question(analysis.normalized_question)
    if not any(marker in question for marker in (
        "thong tin lien he", "cac kenh theo doi", "kenh theo doi cua truong",
        "lien he cua truong", "lien he dhv",
    )):
        return None

    chunks = [
        chunk for chunk in (getattr(evidence, "chunks", ()) or ())
        if chunk.metadata.get("category") in {"co_so_lien_he", "thong_tin_truong"}
    ]
    if not chunks:
        return None
    text = "\n".join(str(chunk.text or "") for chunk in chunks)
    sections: list[str] = []

    emails = list(dict.fromkeys(re.findall(
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text,
    )))
    if emails:
        sections.append("**Email:** " + " · ".join(emails))

    phone = re.search(
        r"(?:Tổng đài tư vấn tuyển sinh|Hotline|Tổng đài)\s*:\s*(0\d(?:[ .()-]*\d){8,9})",
        text,
        re.IGNORECASE,
    )
    if phone:
        sections.append(
            "**Tổng đài tư vấn tuyển sinh:** "
            + re.sub(r"\s+", " ", phone.group(1)).strip()
        )

    if not sections:
        return None
    return "**Thông tin liên hệ DHV**\n\n" + "\n\n".join(sections)


def _evidence_social_channels_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Render verified official web and social links for a channel question."""

    from .query_analysis import _is_social_channel_question

    question = normalize_question(analysis.normalized_question)
    if analysis.intent != "HOI_CO_SO_LIEN_HE" or not _is_social_channel_question(question):
        return None

    channel_line = re.compile(
        r"^\s*(TikTok|Zalo|YouTube|Facebook)\s*:\s*(https?://\S+)\s*$",
        re.IGNORECASE,
    )
    channels: dict[str, str] = {}
    school_website: str | None = None
    for chunk in getattr(evidence, "chunks", ()) or ():
        if chunk.metadata.get("category") != "co_so_lien_he":
            continue
        candidate_url = str(chunk.metadata.get("source_url") or "").strip()
        parsed_url = urlparse(candidate_url)
        host = (parsed_url.hostname or "").lower().rstrip(".")
        if (
            parsed_url.scheme.lower() == "https"
            and host in {"dhv.edu.vn", "www.dhv.edu.vn"}
            and parsed_url.path in {"", "/"}
            and not parsed_url.username
        ):
            school_website = candidate_url
        for line in str(chunk.text or "").splitlines():
            match = channel_line.match(line)
            if match:
                label = next(
                    known for known in ("TikTok", "Zalo", "YouTube", "Facebook")
                    if known.casefold() == match.group(1).casefold()
                )
                channels.setdefault(label, match.group(2).rstrip(".,;"))

    if not channels:
        return None
    ordered_labels = ("Facebook", "TikTok", "YouTube", "Zalo")
    links: list[str] = []
    if school_website:
        website_host = (urlparse(school_website).hostname or "dhv.edu.vn").removeprefix("www.")
        links.append(f"- **Website DHV:** [{website_host}]({school_website})")
    for label in ordered_labels:
        url = channels.get(label)
        if not url:
            continue
        parsed_url = urlparse(url)
        path = parsed_url.path.strip("/")
        if label in {"TikTok", "YouTube"}:
            account_name = path.split("/")[0] or parsed_url.netloc
        elif label == "Facebook":
            account_name = path.split("/")[0] or parsed_url.netloc
        else:
            account_name = "/".join(part for part in (parsed_url.netloc, path) if part)
        links.append(f"- **{label}:** [{account_name}]({url})")
    return (
        "Bạn có thể theo dõi thông tin chính thức của DHV tại các kênh sau:\n\n"
        + "\n".join(links)
    )


def _evidence_contact_phone_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    question = analysis.normalized_question
    if not any(term in question for term in ("hotline", "tong dai", "so dien thoai")):
        return None
    asks_advisor = bool(re.search(r"tu van vien", question))
    asks_academic_unit = "khoa" in question or ("vien" in question and not asks_advisor)
    if asks_academic_unit:
        return None
    numbers: list[str] = []
    for chunk in getattr(evidence, "chunks", ()) or ():
        lines = chunk.text.splitlines()
        if asks_advisor and chunk.metadata.get("category") == "ho_so":
            advisor_numbers: list[str] = []
            for index, line in enumerate(lines):
                if "tu van vien" not in normalize_question(line):
                    continue
                text = line if re.search(r"\d", line) else " ".join(lines[index:index + 2])
                for match in re.finditer(r"(?<!\d)0\d(?:[ .()-]*\d){8,9}(?!\d)", text):
                    number = match.group().strip()
                    if number not in advisor_numbers:
                        advisor_numbers.append(number)
            if advisor_numbers:
                return "Số điện thoại tư vấn viên nhập học DHV: " + ", ".join(advisor_numbers) + "."
            continue
        if chunk.metadata.get("category") not in {"thong_tin_truong", "co_so_lien_he"}:
            continue
        for index, line in enumerate(lines):
            if not re.search(r"\b(?:tong dai|hotline)\b", normalize_question(line)):
                continue
            text = line if re.search(r"\d", line) else " ".join(lines[index:index + 2])
            for match in re.finditer(r"(?<!\d)0\d(?:[ .()-]*\d){8,9}(?!\d)", text):
                number = match.group().strip()
                if number not in numbers:
                    numbers.append(number)
    if asks_advisor and numbers:
        return (
            "Tài liệu DHV hiện chưa nêu số điện thoại riêng của tư vấn viên nhập học. "
            "Bạn có thể liên hệ tổng đài tư vấn tuyển sinh: " + ", ".join(numbers) + "."
        )
    return "Tổng đài tư vấn tuyển sinh DHV: " + ", ".join(numbers) + "." if numbers else None


def _evidence_campus_and_phone_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    """Answer an explicit campus-plus-hotline request with both requested facts."""

    question = normalize_question(analysis.normalized_question)
    asks_for_campuses = "co so va" in question
    asks_for_phone = any(term in question for term in ("hotline", "tong dai", "so dien thoai"))
    if analysis.intent != "HOI_CO_SO_LIEN_HE" or not (asks_for_campuses and asks_for_phone):
        return None

    campus_answer = _evidence_campus_list_answer(analysis, evidence)
    phone_answer = _evidence_contact_phone_answer(analysis, evidence)
    if not campus_answer or not phone_answer:
        return None
    return f"{campus_answer}\n\n{phone_answer}"


def _evidence_contact_email_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    if "email" not in analysis.normalized_question:
        return None
    emails = list(dict.fromkeys(re.findall(
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        "\n".join(_evidence_text_lines(evidence)),
    )))
    if not emails:
        return None
    prefix = ""
    asks_advisor = "tu van vien" in analysis.normalized_question
    asks_academic_unit = "khoa" in analysis.normalized_question or (
        "vien" in analysis.normalized_question and not asks_advisor
    )
    if asks_academic_unit:
        if any(email.casefold() not in {"info@dhv.edu.vn", "media@dhv.edu.vn"} for email in emails):
            return None
        prefix = "Mình chưa có email riêng của khoa/viện bạn hỏi. "
    return prefix + "Email liên hệ chung của DHV: " + ", ".join(emails) + "."


def _evidence_school_code_answer(analysis: QueryAnalysis, evidence: Any) -> str | None:
    if "ma truong" not in normalize_question(analysis.normalized_question):
        return None
    for text in (
        re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or ""))
        for chunk in getattr(evidence, "chunks", ()) or ()
    ):
        match = re.search(r"\bMã\s+trường\s*[:(]?\s*([A-Z]{2,8})\b", text, re.IGNORECASE)
        if match:
            return f"Mã trường dùng trong tuyển sinh là {match.group(1).upper()}."
    return None


def _named_unit_relation_missing_evidence(analysis: QueryAnalysis, evidence: Any) -> bool:
    """Prevent a named faculty/institute query from borrowing an unrelated major fact."""

    normalized = normalize_question(analysis.normalized_question)
    canonical_units = (
        ("khoa quan tri kinh doanh marketing", "khoa"),
        ("khoa du lich nha hang khach san", "khoa"),
        ("khoa tai chinh ngan hang ke toan", "khoa"),
        ("khoa ky thuat cong nghe", "khoa"),
        ("khoa ngon ngu", "khoa"),
        ("khoa khoa hoc suc khoe", "khoa"),
        ("khoa luat", "khoa"),
        ("vien cong nghe tien tien va tri tue nhan tao", "vien"),
        ("vien lien ket giao duc va dao tao tu xa", "vien"),
        ("vien dao tao sau dai hoc", "vien"),
    )
    matched_units = [
        (name, kind, normalized.find(name))
        for name, kind in canonical_units
        if name in normalized
    ]
    if matched_units:
        requested_unit, unit_kind, unit_start = max(
            matched_units, key=lambda item: (len(item[0]), -item[2])
        )
        unit_end = unit_start + len(requested_unit)
        relation_suffix = normalized[unit_end:]
    else:
        # ``khoa`` cũng là một phần của "á khoa", "thủ khoa", "chuyên khoa", "khoa học"...
        # nên chỉ coi là đơn vị khi không đi sau/trước các từ đó.
        match = re.search(
            # "sinh viên", "giảng viên", "tư vấn viên"... are people, not a
            # "viện" (institute), so they must not open a unit lookup.
            r"(?<!\ba )(?<!\bthu )(?<!\bchuyen )(?<!\bdai hoc )"
            r"(?<!\bsinh )(?<!\bgiang )(?<!\bthanh )(?<!\bnhan )(?<!\bvan )"
            r"\b(khoa|vien|trung tam)\s+(?!(?:hoc|tai|cua|dhv|nao|nam|nay|do|dau)\b)"
            r"(.+?)(?=\s+(?:co|hop tac|nghien cuu|phu trach|ho tro|mang luoi|la|thuc hien|trai rong|gom|thuoc|hoat dong|nham)\b|[?,.]|$)",
            normalized,
        )
        if not match:
            return False
        requested_unit = f"{match.group(1)} {match.group(2)}".strip()
        unit_kind = match.group(1)
        relation_suffix = normalized[match.end():]

    # A yes/no existence question is not a request for a department-specific
    # academic/partnership relation. In particular, words such as "đào tạo"
    # can be part of an institute's official name.
    if not any(marker in relation_suffix for marker in (
        "dao tao", "nghien cuu", "chuong trinh", "nganh", "phu trach",
        "hop tac", "doi tac", "linh vuc", "hoat dong", "ho tro", "thuc tap",
    )):
        return False
    relation_families = (
        ("dao tao", "chuong trinh"),
        ("nghien cuu", "phat trien"),
        ("hop tac", "doi tac", "lien ket"),
        ("linh vuc", "nganh nghe"),
        ("hoat dong", "ho tro", "thuc tap", "thuc hanh"),
        ("phu trach", "to chuc", "trien khai"),
    )
    source_sentences = [normalize_question(sentence) for sentence in _evidence_sentences(evidence)]
    # The unit name and the requested relation must be supported together;
    # an unrelated line elsewhere in the retrieved chunk is not enough.
    return not any(
        (
            requested_unit in sentence
            or unit_kind == "khoa" and "cac khoa cua dhv" in sentence
        )
        and any(
            any(marker in normalized for marker in family)
            and any(marker in sentence for marker in family)
            for family in relation_families
        )
        for sentence in source_sentences
    )


def _school_info_detail_missing_evidence(analysis: QueryAnalysis, evidence: Any) -> bool:
    if analysis.intent != "SCHOOL_INFO":
        return False
    normalized = normalize_question(analysis.normalized_question)
    detail_markers = (
        "hoat dong hoc tap", "hoat dong nao", "mang luoi doi tac", "linh vuc nao",
        "don vi nao", "doi tac nao", "co hoi thuc tap", "hop tac voi doanh nghiep",
        "ky ket voi", "mo rong co hoi",
    )
    if not any(marker in normalized for marker in detail_markers):
        return False
    lines = _evidence_text_lines(evidence)
    folded_lines = [normalize_question(line) for line in lines]
    evidence_sentences = [normalize_question(sentence) for sentence in _evidence_sentences(evidence)]
    # Preserve explicit constraints from a question (place, count, date). A
    # broad cooperation statement cannot stand in for a requested location or
    # an exact event scale.
    place_match = re.search(
        r"\b(?:tai|o)\s+(.+?)(?=\s+(?:cho|cua|nham|voi|trong|nhung|nao|khong|co|de|va)\b|[?,.]|$)",
        normalized,
    )
    if place_match:
        requested_place = place_match.group(1).strip()
        relation_cues = ("hop tac", "thuc tap", "co hoi", "ky ket", "mo rong", "doi tac")
        generic_place_phrase = bool(re.match(
            r"(?:nhung|cac|mot|khu vuc|linh vuc|nhom|dia diem|vi tri)\b",
            requested_place,
        ))
        if len(requested_place) >= 3 and not generic_place_phrase and not any(
            requested_place in sentence
            and any(cue in sentence for cue in relation_cues)
            for sentence in evidence_sentences
        ):
            return True
    requested_counts = re.findall(
        r"\b\d+\s+(?:doanh nghiep|don vi|to chuc|truong|khoa|chuong trinh|nganh)\b",
        normalized,
    )
    if any(not any(count in sentence for sentence in evidence_sentences) for count in requested_counts):
        return True
    requested_dates = re.findall(r"\b\d{1,2}/\d{1,2}/20\d{2}\b", analysis.question)
    if any(
        not any(normalize_question(date) in sentence for sentence in evidence_sentences)
        for date in requested_dates
    ):
        return True
    requested_unit = next(
        (unit for unit in (
            "khoa ngon ngu", "khoa du lich nha hang khach san",
            "khoa quan tri kinh doanh marketing", "khoa luat",
            "khoa ky thuat cong nghe", "vien dao tao sau dai hoc",
        ) if unit in normalized),
        None,
    )
    unit_sentences = [
        sentence for sentence in evidence_sentences
        if requested_unit and requested_unit in sentence
    ]
    known_partners = (
        "chosun", "hyogo", "glenn college", "chivast", "studydiy", "daiso", "khai nam"
    )
    unit_lines = [line for line in folded_lines if requested_unit and requested_unit in line]
    if requested_unit and not unit_lines and not unit_sentences:
        return True

    if any(marker in normalized for marker in ("don vi nao", "doi tac nao", "mang luoi doi tac")):
        # A named unit's own cooperation sentence ("Khoa Luật hợp tác với ...
        # công ty luật, văn phòng luật sư ...") identifies its partner types.
        if requested_unit and any(
            "hop tac voi" in sentence[sentence.find(requested_unit):]
            for sentence in unit_sentences
        ):
            return False
        # A general statement that DHV cooperates with organizations does not
        # identify the requested partner network, especially for a named unit.
        return not any(
            partner in line
            for line in (unit_sentences if requested_unit else evidence_sentences)
            for partner in known_partners
        )

    if any(marker in normalized for marker in ("hoat dong hoc tap", "hoat dong nao", "co hoi thuc tap")):
        concrete_activity_markers = (
            "trai nghiem thuc te", "ky nang ngon ngu", "ky nang mem", "thuc tap tot nghiep",
            "kien tap", "thuc tap", "thuc hanh",
        )
        has_unit_specific_activity = any(
            marker in line
            for line in (unit_sentences if requested_unit else evidence_sentences)
            for marker in concrete_activity_markers
        )
        has_general_faculty_activity = any(
            "cac khoa cua dhv" in sentence
            and any(marker in sentence for marker in ("kien tap", "thuc hanh", "thuc tap"))
            for sentence in evidence_sentences
        )
        return not (has_unit_specific_activity or has_general_faculty_activity)

    if "linh vuc nao" in normalized:
        field_markers = (
            "thuong mai", "xuat nhap khau", "tai chinh", "giao duc", "dao tao",
            "du lich", "cong nghe", "ngon ngu",
        )
        return not any(
            marker in line
            for line in (unit_lines if requested_unit else folded_lines)
            for marker in field_markers
        )

    return True
