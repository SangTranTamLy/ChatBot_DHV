"""Load verified Structured JSON documents into LangChain Documents."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from .structured_json import build_chunk_documents, load_structured_json


LOGGER = logging.getLogger(__name__)

INTERNAL_DOCUMENT_TYPES = {"internal", "internal_note", "private"}


class MetadataError(ValueError):
    """Báo lỗi khi một structured JSON document không hợp lệ."""


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


def load_structured_json_file(path: Path) -> list[Document]:
    """Load one validated JSON document as natural-language record documents.

    The JSON object itself is never used as ``page_content``.  Each record is
    rendered by the structured chunk builder and carries flattened provenance
    suitable for Chroma metadata.
    """

    return build_chunk_documents(load_structured_json(path))


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
    """Read verified JSON files in ``data_dir``.

    Các file không vượt qua validation được báo cáo trong ``errors``. Chỉ
    document đúng năm và đã verified mới được đưa vào chunk builder.
    """

    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"data directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"data path is not a directory: {root}")

    result = LoadResult()
    json_files = sorted(
        path
        for path in root.rglob("*.json")
        if path.is_file() and path.name.lower() != "manifest.json"
    )
    if json_files:
        for path in json_files:
            result.stats.files_seen += 1
            relative_path = path.relative_to(root).as_posix()
            try:
                # Read the envelope first so an explicitly draft/unverified
                # document is classified as skipped data, not as a malformed
                # verified document. Full schema/domain validation happens
                # only for candidates that can enter the KB.
                structured = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(structured, dict):
                    raise MetadataError("structured JSON root must be an object")
                source = structured.get("source", {})
                status = str(source.get("status", "")).strip().lower()
                if _is_internal(dict(source)):
                    result.stats.skipped_internal += 1
                    continue
                if status != "verified" or source.get("verified") is not True:
                    result.stats.skipped_unverified += 1
                    continue
                if target_year is not None and structured.get("year") != target_year:
                    result.stats.skipped_other_year += 1
                    continue
                documents = load_structured_json_file(path)
                if not documents:
                    raise MetadataError("structured JSON produced zero record documents")
                result.documents.extend(documents)
                result.stats.verified_documents += 1
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                result.stats.metadata_errors += 1
                error = {"file": relative_path, "error": str(exc)}
                result.errors.append(error)
                LOGGER.error("structured JSON error in %s: %s", relative_path, exc)
        LOGGER.info(
            "loaded structured JSON files=%d verified_documents=%d skipped_unverified=%d "
            "skipped_internal=%d skipped_other_year=%d metadata_errors=%d",
            result.stats.files_seen,
            result.stats.verified_documents,
            result.stats.skipped_unverified,
            result.stats.skipped_internal,
            result.stats.skipped_other_year,
            result.stats.metadata_errors,
        )
        return result
    return result


__all__ = [
    "LoadResult",
    "LoadStats",
    "MetadataError",
    "load_structured_json_file",
    "load_verified_documents",
]
