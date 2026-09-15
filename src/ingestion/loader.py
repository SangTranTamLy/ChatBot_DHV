"""Tải các tài liệu Markdown đã được xác thực kèm theo phần YAML front matter.

Trình tải (loader) sẽ giữ lại metadata nguồn đính kèm vào mỗi Document của LangChain và
báo cáo các file bị lỗi định dạng hoặc chưa được xác thực thay vì âm thầm lập chỉ mục chúng.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document


LOGGER = logging.getLogger(__name__)

FRONT_MATTER_RE = re.compile(
    r"\A(?:\ufeff)?---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)
REQUIRED_METADATA_KEYS = (
    "title",
    "category",
    "year",
    "source_url",
    "source_date",
    "status",
)
INTERNAL_DOCUMENT_TYPES = {"internal", "internal_note", "private"}


class MetadataError(ValueError):
    """Báo lỗi khi một file Markdown có metadata không hợp lệ hoặc không đầy đủ."""


@dataclass
class LoadStats:
    """Các bộ đếm được thu thập trong quá trình quét corpus đã xử lý."""

    files_seen: int = 0
    verified_documents: int = 0
    skipped_unverified: int = 0
    skipped_internal: int = 0
    skipped_other_year: int = 0
    metadata_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class LoadResult:
    """Các tài liệu đã tải, bộ đếm và chi tiết lỗi an toàn để ghi log."""

    documents: list[Document] = field(default_factory=list)
    stats: LoadStats = field(default_factory=LoadStats)
    errors: list[dict[str, str]] = field(default_factory=list)


def _metadata_value(value: Any) -> str | int | float | bool:
    """Chuyển đổi giá trị YAML thành giá trị metadata vô hướng (scalar) tương thích với Chroma."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise MetadataError("missing YAML front matter")

    try:
        raw_metadata = yaml.safe_load(match.group("yaml"))
    except yaml.YAMLError as exc:
        raise MetadataError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw_metadata, dict):
        raise MetadataError("YAML front matter must be a mapping")

    missing = [key for key in REQUIRED_METADATA_KEYS if key not in raw_metadata]
    if missing:
        raise MetadataError("missing required metadata: " + ", ".join(missing))

    metadata = {key: _metadata_value(value) for key, value in raw_metadata.items()}
    try:
        raw_year = metadata["year"]
        if isinstance(raw_year, bool) or int(raw_year) != float(raw_year):
            raise ValueError
        metadata["year"] = int(raw_year)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MetadataError("year must be a numeric value") from exc
    if not str(metadata["title"]).strip():
        raise MetadataError("title must not be empty")
    if not str(metadata["category"]).strip():
        raise MetadataError("category must not be empty")
    if not str(metadata["source_url"]).strip():
        raise MetadataError("source_url must not be empty")

    body = text[match.end() :].strip()
    if not body:
        raise MetadataError("document body is empty")

    metadata["source_file"] = path.as_posix()
    return metadata, body


def load_markdown_file(path: Path) -> Document:
    """Tải một file Markdown vào một đối tượng Document của LangChain."""

    text = path.read_text(encoding="utf-8-sig")
    metadata, body = _parse_front_matter(text, path)
    return Document(page_content=body, metadata=metadata)


def _is_internal(metadata: dict[str, Any]) -> bool:
    document_type = str(metadata.get("document_type", "")).strip().lower()
    source_type = str(metadata.get("source_type", "")).strip().lower()
    return (
        document_type in INTERNAL_DOCUMENT_TYPES
        or source_type in INTERNAL_DOCUMENT_TYPES
        or metadata.get("internal") is True
    )


def load_verified_documents(
    data_dir: str | Path,
    *,
    target_year: int | None = 2026,
) -> LoadResult:
    """Đọc tất cả các file Markdown trong ``data_dir`` và giữ lại các nguồn đã xác thực.

    Các file không vượt qua bước kiểm tra metadata sẽ được báo cáo trong ``errors``. Các file
    có trạng thái (status) khác với ``verified`` sẽ bị bỏ qua và không bao giờ được trả về.
    Mặc định, chỉ các tài liệu thuộc cơ sở tri thức của năm 2026 mới được trả về.
    """

    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"data directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"data path is not a directory: {root}")

    result = LoadResult()
    markdown_files = sorted(path for path in root.rglob("*.md") if path.is_file())

    for path in markdown_files:
        result.stats.files_seen += 1
        relative_path = path.relative_to(root).as_posix()
        try:
            document = load_markdown_file(path)
        except (OSError, UnicodeError, MetadataError) as exc:
            result.stats.metadata_errors += 1
            error = {"file": relative_path, "error": str(exc)}
            result.errors.append(error)
            LOGGER.error("metadata error in %s: %s", relative_path, exc)
            continue

        status = str(document.metadata.get("status", "")).strip().lower()
        if _is_internal(document.metadata):
            result.stats.skipped_internal += 1
            LOGGER.info("skipping internal document: %s", relative_path)
            continue
        if status != "verified":
            result.stats.skipped_unverified += 1
            LOGGER.info("skipping non-verified document: %s", relative_path)
            continue
        if target_year is not None and document.metadata.get("year") != target_year:
            result.stats.skipped_other_year += 1
            LOGGER.info(
                "skipping document outside target year %s: %s",
                target_year,
                relative_path,
            )
            continue

        document.metadata["source_file"] = relative_path
        result.documents.append(document)
        result.stats.verified_documents += 1

    LOGGER.info(
        "loaded files=%d verified_documents=%d skipped_unverified=%d "
        "skipped_internal=%d skipped_other_year=%d metadata_errors=%d",
        result.stats.files_seen,
        result.stats.verified_documents,
        result.stats.skipped_unverified,
        result.stats.skipped_internal,
        result.stats.skipped_other_year,
        result.stats.metadata_errors,
    )
    return result


__all__ = [
    "LoadResult",
    "LoadStats",
    "MetadataError",
    "load_markdown_file",
    "load_verified_documents",
]
