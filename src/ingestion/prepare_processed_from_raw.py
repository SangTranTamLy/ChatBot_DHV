"""Generate structured JSON (and an optional legacy Markdown view) from RAW PDFs."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader

from src.config.settings import PROJECT_ROOT, settings

from .structured_json import (
    StructuredJSONValidationError,
    build_structured_document,
    write_structured_json,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
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
    """A generated Structured JSON representation and its RAW PDF source."""

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
    records_count: int = 0
    warnings_count: int = 0
    pages_count: int = 0


def _normalize_extracted_text(text: str) -> str:
    """Clean extraction artefacts while preserving factual tokens and Unicode."""

    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "-", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_pages(path: Path) -> list[dict[str, object]]:
    """Extract text by page and retain page boundaries for the JSON layer.

    OCR is intentionally not introduced here: the separately scoped mandatory
    OCR task has not been implemented in this repository yet.  This function
    is the current pypdf text-layer extractor and is kept as one explicit
    boundary so a later OCR implementation can replace it without changing
    the JSON parser or vector builder.
    """

    reader = PdfReader(str(path))
    pages = [
        {"page": index, "text": _normalize_extracted_text(page.extract_text() or "")}
        for index, page in enumerate(reader.pages, start=1)
    ]
    if not any(str(page["text"]).strip() for page in pages):
        raise ValueError("PDF has no extractable text")
    return pages


def _extract_pdf_text(path: Path) -> str:
    """Return the compatibility flat text view of page-level extraction."""

    pages = _extract_pdf_pages(path)
    text = "\n\n".join(str(page["text"]) for page in pages if str(page["text"]).strip())
    if not text.strip():
        raise ValueError("PDF has no extractable text")
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


def convert_pdf_to_structured_json(
    raw_path: Path,
    *,
    raw_root: Path,
    output_root: Path,
    markdown_root: Path | None = None,
) -> ProcessedDocument:
    """Generate one Structured JSON document directly from one RAW PDF.

    ``markdown_root`` remains an explicit compatibility argument for callers
    from the previous task, but Markdown generation is intentionally removed.
    Passing a non-null path fails loudly instead of silently recreating the
    retired generated Markdown layer.
    """

    if markdown_root is not None:
        raise ValueError("generated Markdown output was removed; use Structured JSON")

    pages = _extract_pdf_pages(raw_path)
    structured = build_structured_document(
        raw_path=raw_path,
        raw_root=raw_root,
        pages=pages,
        extraction_method="pypdf_text",
    )
    category = str(structured["category"])
    json_path = output_root / category / f"{raw_path.stem}.json"
    write_structured_json(structured, json_path)

    return ProcessedDocument(
        raw_path=raw_path,
        output_path=json_path,
        title=str(structured["title"]),
        category=category,
        source_url=str(structured["source"]["source_url"]),
        source_date=str(structured["source"].get("source_date", "")),
        text="\n\n".join(str(page["text"]) for page in structured["pages"] if str(page["text"]).strip()),
        source_urls=tuple(str(url) for url in structured["source"].get("source_urls", [])),
        collected_at=str(structured["source"].get("collected_at", "")),
        data_role=str(structured.get("data_role", "")),
        records_count=len(structured.get("records", [])),
        warnings_count=len(structured.get("warnings", [])),
        pages_count=len(structured.get("pages", [])),
    )


def _safe_reset_generated_directory(path: Path, *, raw_root: Path) -> None:
    resolved = path.resolve()
    raw_resolved = raw_root.resolve()
    if (
        resolved == raw_resolved
        or raw_resolved in resolved.parents
        or resolved == Path(resolved.anchor)
        or resolved == PROJECT_ROOT.resolve()
    ):
        raise ValueError(f"refusing to reset protected directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def rebuild_structured_json(
    *,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    output_directory: str | Path = DEFAULT_OUTPUT_DIR,
    reset: bool = True,
) -> list[ProcessedDocument]:
    """Scan all RAW PDFs and generate validated JSON under ``data/processed``.

    A failed source is not represented as a successful output.  The scan
    continues so the final exception reports every failed PDF in one run.
    """

    raw_root = Path(raw_directory).resolve()
    output_root = Path(output_directory).resolve()
    if not raw_root.exists() or not raw_root.is_dir():
        raise FileNotFoundError(f"RAW directory does not exist: {raw_root}")
    if output_root == raw_root or output_root == Path(output_root.anchor):
        raise ValueError("refusing to use RAW directory or a filesystem root as JSON output")
    if reset:
        _safe_reset_generated_directory(output_root, raw_root=raw_root)
    output_root.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(raw_root.rglob("*.pdf"))
    if not raw_files:
        raise RuntimeError(f"no RAW PDF files found in {raw_root}")
    documents: list[ProcessedDocument] = []
    failures: list[str] = []
    for index, path in enumerate(raw_files, start=1):
        LOGGER.info("[%d/%d] %s", index, len(raw_files), path.name)
        try:
            document = convert_pdf_to_structured_json(
                path,
                raw_root=raw_root,
                output_root=output_root,
            )
        except (OSError, ValueError, StructuredJSONValidationError) as exc:
            failures.append(f"{path.relative_to(raw_root).as_posix()}: {exc}")
            LOGGER.error("failed: %s", failures[-1])
            continue
        documents.append(document)
        LOGGER.info(
            "  extraction=%s pages=%d records=%d warnings=%d output=%s",
            "OK",
            document.pages_count,
            document.records_count,
            document.warnings_count,
            document.output_path,
        )
    LOGGER.info(
        "structured JSON rebuild summary: raw_pdfs=%d success=%d failed=%d records=%d warnings=%d",
        len(raw_files),
        len(documents),
        len(failures),
        sum(document.records_count for document in documents),
        sum(document.warnings_count for document in documents),
    )
    if failures:
        raise RuntimeError("structured JSON rebuild failed:\n" + "\n".join(failures))
    return documents


def rebuild_processed(
    *,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    output_directory: str | Path = DEFAULT_OUTPUT_DIR,
    reset: bool = True,
) -> list[ProcessedDocument]:
    """Backward-compatible name for the canonical JSON rebuild."""

    return rebuild_structured_json(
        raw_directory=raw_directory,
        output_directory=output_directory,
        reset=reset,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument(
        "--output-dir",
        default=str(settings.processed_data_dir),
        help="generated Structured JSON directory",
    )
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
        documents = rebuild_structured_json(
            raw_directory=args.raw_dir,
            output_directory=args.output_dir,
            reset=not args.no_reset,
        )
    except Exception as exc:
        LOGGER.error("processed rebuild failed: %s", exc)
        return 1
    print(
        {
            "raw_pdfs": len({document.raw_path for document in documents}),
            "json_documents": len(documents),
            "records": sum(document.records_count for document in documents),
            "warnings": sum(document.warnings_count for document in documents),
            "processed_output": str(Path(args.output_dir).resolve()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ProcessedDocument",
    "_extract_pdf_pages",
    "convert_pdf_to_structured_json",
    "main",
    "rebuild_processed",
    "rebuild_structured_json",
]
