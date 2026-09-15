"""Create verified Markdown documents from the audited RAW PDF corpus."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from src.config.settings import PROJECT_ROOT, settings


LOGGER = logging.getLogger(__name__)
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
YEAR = settings.target_year
TITLE_RE = re.compile(r"^DHV(?:\s+2026)?\s*-\s*(?P<title>.+?)\s*$")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
DATE_LINE_RE = re.compile(
    r"^(?:Ngày cập nhật nguồn|Nguồn cập nhật):\s*(?P<date>.+?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProcessedDocument:
    """One generated Markdown document and its source PDF."""

    raw_path: Path
    output_path: Path
    title: str
    category: str
    source_url: str
    source_date: str
    text: str


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(page for page in pages if page)
    if not text.strip():
        raise ValueError("PDF has no extractable text")

    # Remove line-break artifacts introduced by PDF text extraction while
    # preserving the content and its paragraph/bullet boundaries.
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
    match = URL_RE.search(text)
    if not match:
        raise ValueError("source_url not found in PDF text")
    return match.group(0).rstrip(".,)")


def _source_date_from_text(text: str) -> str:
    for line in text.splitlines():
        match = DATE_LINE_RE.match(line.strip())
        if match:
            value = match.group("date").strip()
            if "|" in value:
                value = value.split("|", 1)[0].strip()
            return value
    raise ValueError("source_date not found in PDF text")


def _front_matter(
    *,
    title: str,
    category: str,
    source_url: str,
    source_date: str,
    raw_file: str,
) -> str:
    values = [
        "---",
        f'title: "{title.replace(chr(34), chr(92) + chr(34))}"',
        f'category: "{category}"',
        f'subcategory: "{category}"',
        f"year: {YEAR}",
        'school: "Trường Đại học Hùng Vương TP.HCM"',
        'school_code: "DHV"',
        'source_type: "official_website"',
        'source_name: "DHV"',
        f'source_url: "{source_url}"',
        f'source_date: "{source_date.replace(chr(34), chr(92) + chr(34))}"',
        'document_type: "pdf_derived_markdown"',
        'status: "verified"',
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
    source_url = _source_url_from_text(text)
    source_date = _source_date_from_text(text)
    raw_file = raw_path.relative_to(PROJECT_ROOT).as_posix()
    output_path = output_root / category / _output_name(raw_path)
    body = f"# {title}\n\n{text}"
    output = _front_matter(
        title=title,
        category=category,
        source_url=source_url,
        source_date=source_date,
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
    )


def rebuild_processed(
    *,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    output_directory: str | Path = DEFAULT_OUTPUT_DIR,
    reset: bool = True,
) -> list[ProcessedDocument]:
    """Recreate processed Markdown exclusively from RAW PDFs."""

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
