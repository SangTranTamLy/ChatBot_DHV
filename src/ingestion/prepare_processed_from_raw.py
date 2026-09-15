"""Tạo các tài liệu Markdown đã xác thực từ corpus RAW PDF đã được kiểm duyệt."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from pypdf import PdfReader

from src.config.settings import PROJECT_ROOT, settings


LOGGER = logging.getLogger(__name__)
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
YEAR = settings.target_year
TITLE_RE = re.compile(r"^DHV(?:\s+2026)?\s*-\s*(?P<title>.+?)\s*$")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
DATE_LINE_RE = re.compile(
    r"^(?:Ngày cập nhật nguồn|Nguồn cập nhật|Ngày thu thập/kiểm tra):\s*(?P<date>.+?)\s*$",
    re.IGNORECASE,
)
COLLECTED_AT_LINE_RE = re.compile(
    r"(?:Ngày kiểm tra|Ngày thu thập/kiểm tra|Kiểm tra):\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)
ALLOWED_SOURCE_HOST = "dhv.edu.vn"


@dataclass(frozen=True)
class ProcessedDocument:
    """Một tài liệu Markdown được tạo ra và file PDF nguồn của nó."""

    raw_path: Path
    output_path: Path
    title: str
    category: str
    source_url: str
    source_date: str
    text: str
    source_urls: tuple[str, ...] = ()
    collected_at: str = ""
    data_role: str = ""


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(page for page in pages if page)
    if not text.strip():
        raise ValueError("PDF has no extractable text")

    # Loại bỏ các lỗi xuống dòng do quá trình trích xuất văn bản PDF gây ra,
    # đồng thời giữ nguyên nội dung và ranh giới đoạn văn/dấu đầu dòng.
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "-", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title_from_text(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    match = TITLE_RE.match(first_line)
    return match.group("title").strip() if match else first_line


def _source_url_from_text(text: str) -> str:
    urls = _source_urls_from_text(text)
    if not urls:
        raise ValueError("source_url not found in PDF text")
    return urls[0]


def _source_urls_from_text(text: str) -> tuple[str, ...]:
    """Lấy và kiểm tra toàn bộ URL provenance được ghi trong RAW PDF.

    RAW chỉ được phép chứa link HTTPS đến ``dhv.edu.vn`` hoặc subdomain của
    domain này. Việc kiểm tra ở bước prepare giúp manifest và processed data có
    cùng một policy, thay vì chỉ tin URL đầu tiên.
    """

    urls: list[str] = []
    for match in URL_RE.finditer(text):
        value = match.group(0).rstrip(".,);]")
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host:
            raise ValueError(f"source URL must be HTTPS: {value}")
        if host != ALLOWED_SOURCE_HOST and not host.endswith(f".{ALLOWED_SOURCE_HOST}"):
            raise ValueError(f"source URL is outside official DHV domain: {value}")
        if parsed.username or parsed.password:
            raise ValueError(f"source URL must not contain credentials: {value}")
        if value not in urls:
            urls.append(value)
    return tuple(urls)


def _source_date_from_text(text: str) -> str:
    for line in text.splitlines():
        match = DATE_LINE_RE.match(line.strip())
        if match:
            value = match.group("date").strip()
            if "|" in value:
                value = value.split("|", 1)[0].strip()
            return value
    raise ValueError("source_date not found in PDF text")


def _collected_at_from_text(text: str) -> str:
    for line in text.splitlines():
        match = COLLECTED_AT_LINE_RE.search(line.strip())
        if match:
            day, month, year = match.group("date").split("/")
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    raise ValueError("collected_at not found in PDF text")


def _data_role_from_path(raw_path: Path, category: str) -> str:
    """Phân biệt tài liệu catalog với tài liệu mô tả trong cùng category.

    Category vẫn phản ánh domain ``nganh_dao_tao`` để router tương thích. Vai
    trò hẹp hơn được dùng bởi Evidence Selection để không parse văn xuôi mô tả
    như bảng điểm/quan hệ ngành. Các marker là quy ước tên file tổng quát, không
    mã hóa riêng một ngành.
    """

    if category != "nganh_dao_tao":
        return ""
    stem = raw_path.stem.casefold()
    description_markers = ("mo_ta", "nghe_nghiep", "trien_vong", "gioi_thieu")
    if any(marker in stem for marker in description_markers):
        return "description"
    return "catalog"


def _quote_yaml(value: str) -> str:
    return value.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))


def _front_matter(
    *,
    title: str,
    category: str,
    source_url: str,
    source_urls: tuple[str, ...],
    source_date: str,
    collected_at: str,
    data_role: str,
    raw_file: str,
) -> str:
    values = [
        "---",
        f'title: "{_quote_yaml(title)}"',
        f'category: "{category}"',
        f'subcategory: "{category}"',
        f"year: {YEAR}",
        'school: "Trường Đại học Hùng Vương TP.HCM"',
        'school_code: "DHV"',
        'source_type: "official_website"',
        'source_name: "DHV"',
        f'source_url: "{source_url}"',
        "source_urls:",
        *[f'  - "{_quote_yaml(url)}"' for url in source_urls],
        f'source_date: "{_quote_yaml(source_date)}"',
        f'date: "{_quote_yaml(source_date)}"',
        f'collected_at: "{collected_at}"',
        f'data_role: "{data_role}"',
        'document_type: "pdf_derived_markdown"',
        'status: "verified"',
        'verification_status: "verified"',
        'language: "vi"',
        f'raw_file: "{raw_file}"',
        "---",
        "",
    ]
    return "\n".join(values)


def _output_name(raw_path: Path) -> str:
    return f"{raw_path.stem}.md"


def convert_pdf(raw_path: Path, *, raw_root: Path, output_root: Path) -> ProcessedDocument:
    text = _extract_pdf_text(raw_path)
    category = raw_path.parent.relative_to(raw_root).as_posix()
    if "/" in category:
        raise ValueError("RAW PDF must be directly below one category directory")
    title = _title_from_text(text)
    source_urls = _source_urls_from_text(text)
    source_url = source_urls[0]
    source_date = _source_date_from_text(text)
    collected_at = _collected_at_from_text(text)
    data_role = _data_role_from_path(raw_path, category)
    raw_file = raw_path.relative_to(PROJECT_ROOT).as_posix()
    output_path = output_root / category / _output_name(raw_path)
    body = f"# {title}\n\n{text}"
    output = _front_matter(
        title=title,
        category=category,
        source_url=source_url,
        source_urls=source_urls,
        source_date=source_date,
        collected_at=collected_at,
        data_role=data_role,
        raw_file=raw_file,
    ) + body + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return ProcessedDocument(
        raw_path=raw_path,
        output_path=output_path,
        title=title,
        category=category,
        source_url=source_url,
        source_date=source_date,
        text=text,
        source_urls=source_urls,
        collected_at=collected_at,
        data_role=data_role,
    )


def rebuild_processed(
    *,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    output_directory: str | Path = DEFAULT_OUTPUT_DIR,
    reset: bool = True,
) -> list[ProcessedDocument]:
    """Tạo lại Markdown đã xử lý hoàn toàn từ các file RAW PDF."""

    raw_root = Path(raw_directory).resolve()
    output_root = Path(output_directory).resolve()
    if not raw_root.exists() or not raw_root.is_dir():
        raise FileNotFoundError(f"RAW directory does not exist: {raw_root}")
    if output_root == raw_root or output_root == Path(output_root.anchor):
        raise ValueError("refusing to use RAW directory or a filesystem root as output")
    if reset and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(raw_root.rglob("*.pdf"))
    if not raw_files:
        raise RuntimeError(f"no RAW PDF files found in {raw_root}")

    documents = [
        convert_pdf(path, raw_root=raw_root, output_root=output_root)
        for path in raw_files
    ]
    LOGGER.info(
        "processed rebuild complete: raw_pdfs=%d processed_documents=%d output=%s",
        len(raw_files),
        len(documents),
        output_root,
    )
    return documents


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--output-dir", default=str(settings.processed_data_dir))
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        documents = rebuild_processed(
            raw_directory=args.raw_dir,
            output_directory=args.output_dir,
            reset=not args.no_reset,
        )
    except Exception as exc:
        LOGGER.error("processed rebuild failed: %s", exc)
        return 1
    print({"raw_pdfs": len({document.raw_path for document in documents}), "processed_documents": len(documents)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ProcessedDocument", "convert_pdf", "main", "rebuild_processed"]
