"""Xử lý tra cứu website, cổng thông tin và danh bạ liên kết chính thức của DHV."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from src.config.settings import settings
from .output_validator import FALLBACK_ANSWER
from .query_analysis import QueryAnalysis, normalize_question

_OFFICIAL_WEBSITE_DIRECTORY = (
    ("admissions_portal", ("tuyen sinh", "cong tuyen sinh"), "tuyensinh.dhv.edu.vn", "Cổng tuyển sinh DHV"),
    ("school_website", ("website chinh", "website cua truong", "website truong", "web truong"), "dhv.edu.vn", "Website chính Trường Đại học Hùng Vương TP.HCM"),
    ("ipic", ("vien dao tao sau dai hoc", "sau dai hoc"), "ipic.dhv.edu.vn", "Viện Đào tạo Sau đại học"),
    ("epdl", ("vien lien ket giao duc", "dao tao tu xa"), "epdl.dhv.edu.vn", "Viện Liên kết Giáo dục và Đào tạo từ xa"),
    ("online", ("cong thong tin dao tao",), "online.dhv.edu.vn", "Cổng thông tin đào tạo dành cho sinh viên/giảng viên"),
    ("heal", ("khoa khoa hoc suc khoe", "khoa suc khoe"), "heal.dhv.edu.vn", "Khoa Khoa học Sức khỏe"),
    ("tec", ("khoa ky thuat cong nghe", "ky thuat cong nghe"), "tec.dhv.edu.vn", "Khoa Kỹ thuật Công nghệ"),
    ("fba", ("khoa tai chinh ngan hang ke toan", "tai chinh ngan hang ke toan"), "fba.dhv.edu.vn", "Khoa Tài chính - Ngân hàng - Kế toán"),
    ("bam", ("khoa quan tri kinh doanh marketing", "quan tri kinh doanh marketing"), "bam.dhv.edu.vn", "Khoa Quản trị Kinh doanh - Marketing"),
    ("lan", ("khoa ngon ngu",), "lan.dhv.edu.vn", "Khoa Ngôn ngữ"),
    ("host", ("khoa du lich nha hang khach san", "du lich nha hang khach san"), "host.dhv.edu.vn", "Khoa Du lịch - Nhà hàng - Khách sạn"),
    ("law", ("khoa luat",), "law.dhv.edu.vn", "Khoa Luật"),
    ("iatai", ("vien cong nghe tien tien", "tri tue nhan tao dhv"), "iatai.dhv.edu.vn", "Viện Công nghệ tiên tiến và Trí tuệ nhân tạo DHV"),
    ("core", ("vien van hoa doanh nghiep",), "core.dhv.edu.vn", "Viện Văn hóa Doanh nghiệp"),
    ("tek", ("trung tam cong nghe",), "tek.dhv.edu.vn", "Trung tâm Công nghệ"),
    ("library", ("trung tam hoc lieu", "thu vien dhv"), "thuvien.dhv.edu.vn", "Trung tâm Học liệu"),
    ("journal", ("tap chi khoa hoc",), "tapchikhoahoc.dhv.edu.vn", "Tạp chí Khoa học DHV"),
)


def _requested_website_entry(normalized_question: str) -> tuple[str, str, str] | None:
    normalized = normalize_question(normalized_question)
    for target, aliases, host, title in _OFFICIAL_WEBSITE_DIRECTORY:
        if any(alias in normalized for alias in aliases):
            return target, host, title
    return None


def _official_links_answer(
    analysis: QueryAnalysis,
    evidence: Any,
    *,
    verified_documents: Iterable[Any] = (),
    target_year: int = settings.target_year,
) -> dict[str, object] | None:
    """Trả provenance chính thức từ backend; UI quyết định không hiển thị URL."""

    if not analysis.entities.get("website_request"):
        return None

    all_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def add_source(url: object, title: str) -> None:
        value = str(url or "").strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme.lower() != "https"
            or not host
            or not (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
            or value in seen_urls
        ):
            return
        seen_urls.add(value)
        all_sources.append({"title": title, "url": value})

    def metadata_urls(metadata: Mapping[str, object]) -> list[str]:
        values: list[object] = [metadata.get("source_url")]
        raw_values = metadata.get("source_urls")
        if isinstance(raw_values, str):
            try:
                decoded = json.loads(raw_values)
            except (TypeError, ValueError):
                decoded = ()
            raw_values = decoded
        if isinstance(raw_values, (list, tuple, set)):
            values.extend(raw_values)
        return [str(value).strip() for value in values if str(value or "").strip()]

    for chunk in getattr(evidence, "chunks", ()) or ():
        metadata = getattr(chunk, "metadata", {}) or {}
        for url in metadata_urls(metadata):
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            title = str(metadata.get("title") or "Nguồn chính thức DHV")
            if host in {"dhv.edu.vn", "www.dhv.edu.vn"} and urlparse(url).path in {"", "/"}:
                title = "Website trường"
            elif host == "tuyensinh.dhv.edu.vn":
                title = f"Cổng tuyển sinh {target_year}"
            add_source(url, title)

    # Evidence context is size-limited, but a count query must consider every
    # selected verified record, including records clipped out of that context.
    for document in verified_documents:
        metadata = getattr(document, "metadata", {}) or {}
        if (
            str(metadata.get("status") or "").casefold() != "verified"
            or str(metadata.get("school_code") or "").upper() != "DHV"
        ):
            continue
        try:
            if int(metadata.get("year")) != target_year:
                continue
        except (TypeError, ValueError):
            continue
        title = str(metadata.get("title") or "Nguồn chính thức DHV")
        for url in metadata_urls(metadata):
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            if host in {"dhv.edu.vn", "www.dhv.edu.vn"} and urlparse(url).path in {"", "/"}:
                title = "Website trường"
            elif host == "tuyensinh.dhv.edu.vn":
                title = f"Cổng tuyển sinh {target_year}"
            add_source(url, title)

    # Keep compatibility with test/adaptor documents that expose only the
    # already-normalized evidence source contract.
    for source in getattr(evidence, "sources", ()) or ():
        add_source(
            source.get("url"),
            str(source.get("title") or "Nguồn chính thức DHV"),
        )

    requested_entry = _requested_website_entry(analysis.normalized_question)
    website_kind = str(analysis.entities.get("website_kind") or "")
    if analysis.entities.get("website_count_request"):
        sites_by_host: dict[str, dict[str, str]] = {}
        for source in all_sources:
            parsed = urlparse(source["url"])
            host = (parsed.hostname or "").lower().rstrip(".")
            canonical_host = host[4:] if host.startswith("www.") else host
            if not canonical_host:
                continue
            current = sites_by_host.get(canonical_host)
            is_root = parsed.path in {"", "/"}
            current_is_root = bool(
                current and urlparse(current["url"]).path in {"", "/"}
            )
            if current is None or (is_root and not current_is_root):
                sites_by_host[canonical_host] = dict(source)
        sources = list(sites_by_host.values())
        sources.sort(
            key=lambda source: (
                0 if (urlparse(source["url"]).hostname or "").lower() == "dhv.edu.vn" else
                1 if (urlparse(source["url"]).hostname or "").lower() == "tuyensinh.dhv.edu.vn" else
                2,
                (urlparse(source["url"]).hostname or "").lower(),
            )
        )
    elif requested_entry is not None:
        _, requested_host, requested_title = requested_entry
        requested_sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".") == requested_host
        ]
        if requested_host == "tuyensinh.dhv.edu.vn" and not requested_sources:
            # Some verified DHV material links to the admissions landing page
            # on the main host rather than the dedicated subdomain. Accept
            # only that semantically matching path, never an arbitrary other
            # DHV website as a substitute for the requested portal.
            requested_sources = [
                source
                for source in all_sources
                if (urlparse(source["url"]).hostname or "").lower().rstrip(".")
                in {"dhv.edu.vn", "www.dhv.edu.vn"}
                and urlparse(source["url"]).path.rstrip("/").casefold()
                in {"/tuyen-sinh", "/tuyen_sinh", "/admissions"}
            ]
        root_sources = [
            source for source in requested_sources if urlparse(source["url"]).path in {"", "/"}
        ]
        sources = root_sources or requested_sources
        for source in sources:
            source_host = (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            if source_host == requested_host:
                source["title"] = requested_title
    elif website_kind == "school_website":
        school_sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            in {"dhv.edu.vn", "www.dhv.edu.vn"}
        ]
        root_sources = [
            source
            for source in school_sources
            if urlparse(source["url"]).path in {"", "/"}
        ]
        sources = root_sources or school_sources
    elif website_kind == "admissions_portal":
        sources = [
            source
            for source in all_sources
            if (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            == "tuyensinh.dhv.edu.vn"
        ]
    else:
        sources = list(all_sources)

    if not sources:
        if (
            analysis.entities.get("website_count_request")
            or requested_entry is not None
            or website_kind in {"school_website", "admissions_portal"}
        ):
            return {
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "status": "no_data",
                "evidence_boundary": "requested_website_not_in_verified_evidence",
            }
        return None

    if analysis.entities.get("website_count_request"):
        answer_lines = [
            "Trong các nguồn DHV đã xác minh, tìm thấy "
            f"{len(sources)} website/cổng thông tin khác nhau:"
        ]
        answer_lines.extend(
            f"- **{source['title']}:** [{source['url']}]({source['url']})"
            for source in sources
        )
        return {
            "answer": "\n".join(answer_lines),
            "sources": sources,
            "status": "ok",
        }

    lines = [
        "Chào bạn! Bạn có thể xem thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM tại các nguồn chính thức sau:",
    ]
    for source in sources:
        title = source["title"]
        url = source["url"]
        lines.append(f"- **{title}:** [{url}]({url})")
    lines.append(
        "\nNếu bạn có thắc mắc gì thêm về ngành học, học phí, hay hồ sơ xét tuyển thì cứ hỏi mình nhé!"
    )
    return {
        "answer": "\n".join(lines),
        "sources": sources,
        "status": "ok",
    }
