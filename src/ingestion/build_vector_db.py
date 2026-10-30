"""Build or rebuild the DHV ChromaDB collection from structured JSON.

Chạy từ thư mục gốc của dự án:

    python -m src.ingestion.build_vector_db --reset

Lệnh này sử dụng Ollama embeddings được cấu hình trong ``.env`` hoặc qua tham số dòng lệnh.
The input is validated JSON in ``data/processed``.  Generated Markdown is no
longer an accepted corpus representation.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

from src.config.settings import settings

from .embeddings import create_embeddings, resolve_sentence_transformer_model
from .chroma_lifecycle import close_chroma_store
from .loader import LoadResult, load_verified_documents
from .splitter import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_TOKENIZER_MODEL,
    split_documents,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_COLLECTION = settings.chroma_collection
DEFAULT_KB_YEAR = settings.target_year


@dataclass
class BuildStats:
    """Bản tóm tắt được in ra sau khi xây dựng thành công."""

    files_seen: int
    verified_documents: int
    skipped_unverified: int
    skipped_internal: int
    skipped_other_year: int
    metadata_errors: int
    chunks_indexed: int
    collection_name: str
    persist_directory: str
    embedding_backend: str
    embedding_model: str
    collection_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Chừa chỗ cho token đặc biệt [CLS]/[SEP] mà model embedding tự thêm vào.
_SPECIAL_TOKEN_MARGIN = 2


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def embedding_token_limit(embedding_function: Any) -> int | None:
    """Trả về số token tối đa model embedding đọc được (``None`` nếu không rõ)."""

    value = getattr(embedding_function, "max_seq_length", None)
    return int(value) if isinstance(value, int) and value > 0 else None


def resolve_chunk_window(
    chunk_size: int,
    chunk_overlap: int,
    token_limit: int | None,
    *,
    align: bool,
) -> tuple[int, int]:
    """Kiểm tra chunk có vừa cửa sổ của model embedding hay không.

    Khi chunk dài hơn cửa sổ, phần đuôi chunk bị cắt lúc embed nên vector chỉ
    đại diện cho phần đầu. ``align=True`` thu nhỏ chunk cho vừa; ``align=False``
    giữ nguyên (để không đổi index đang dùng) nhưng ghi cảnh báo rõ ràng.
    """

    if token_limit is None:
        return chunk_size, chunk_overlap
    usable = max(16, token_limit - _SPECIAL_TOKEN_MARGIN)
    if chunk_size <= usable:
        return chunk_size, chunk_overlap
    if not align:
        LOGGER.warning(
            "chunk_size=%d token vượt giới hạn %d token của model embedding: phần "
            "cuối mỗi chunk dài sẽ KHÔNG được embed. Chạy lại với "
            "--align-chunks-to-embedding (hoặc CHUNK_ALIGN_TO_EMBEDDING=1) để sửa.",
            chunk_size,
            token_limit,
        )
        return chunk_size, chunk_overlap
    aligned_overlap = min(chunk_overlap, usable // 5)
    LOGGER.info(
        "aligning chunk_size %d -> %d tokens (overlap %d -> %d) to the embedding window",
        chunk_size, usable, chunk_overlap, aligned_overlap,
    )
    return usable, aligned_overlap


def _reset_persist_directory(persist_directory: Path) -> None:
    """Chỉ xóa thư mục vector-store đã được cấu hình rõ ràng."""

    resolved = persist_directory.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.cwd().resolve():
        raise ValueError("refusing to reset a filesystem root or the project root")
    if resolved.exists():
        LOGGER.info("resetting vector store at %s", resolved)
        shutil.rmtree(resolved)


def build_vector_db(
    *,
    data_directory: str | Path = settings.processed_data_dir,
    persist_directory: str | Path = settings.chroma_persist_dir,
    collection_name: str = DEFAULT_COLLECTION,
    embeddings: Any | None = None,
    embedding_backend: str | None = None,
    embedding_model: str | None = None,
    ollama_base_url: str | None = None,
    sentence_transformer_model: str | None = None,
    target_year: int | None = DEFAULT_KB_YEAR,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    tokenizer_model: str = DEFAULT_TOKENIZER_MODEL,
    reset: bool = False,
    align_chunks_to_embedding: bool | None = None,
) -> BuildStats:
    """Tải, chia đoạn, nhúng (embed) và lưu trữ corpus DHV đã xác thực.

    ``align_chunks_to_embedding`` (mặc định đọc ``CHUNK_ALIGN_TO_EMBEDDING``)
    thu nhỏ chunk cho vừa cửa sổ token của model embedding.
    """

    load_result = load_verified_documents(data_directory, target_year=target_year)
    if not load_result.documents:
        stats = load_result.stats.as_dict()
        raise RuntimeError(
            "no verified structured documents found in "
            f"{data_directory}; load stats: {stats}"
        )

    if embeddings is not None:
        embedding_function = embeddings
        resolved_backend = "custom"
        resolved_model = type(embeddings).__name__
    else:
        resolved_backend = (embedding_backend or settings.embedding_backend).strip().lower()
        if resolved_backend in {"sentence_transformers", "st"}:
            resolved_backend = "sentence-transformers"
        if resolved_backend == "ollama":
            resolved_model = embedding_model or settings.embedding_model
        else:
            resolved_model = resolve_sentence_transformer_model(
                sentence_transformer_model
            )
        embedding_function = create_embeddings(
            backend=resolved_backend,
            ollama_model=embedding_model,
            ollama_base_url=ollama_base_url,
            sentence_transformer_model=sentence_transformer_model,
        )

    align = (
        _env_flag("CHUNK_ALIGN_TO_EMBEDDING")
        if align_chunks_to_embedding is None
        else align_chunks_to_embedding
    )
    chunk_size, chunk_overlap = resolve_chunk_window(
        chunk_size,
        chunk_overlap,
        embedding_token_limit(embedding_function),
        align=align,
    )

    chunks = split_documents(
        load_result.documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        tokenizer_model=tokenizer_model,
    )
    if not chunks:
        raise RuntimeError("verified documents produced zero chunks")

    persist_path = Path(persist_directory)
    if reset:
        _reset_persist_directory(persist_path)
    persist_path.mkdir(parents=True, exist_ok=True)

    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=str(persist_path),
        embedding_function=embedding_function,
    )
    collection_count = 0
    try:
        vector_store.add_documents(
            chunks,
            ids=[chunk.metadata["chunk_id"] for chunk in chunks],
        )
        collection_count = int(vector_store._collection.count())
        if collection_count <= 0:
            raise RuntimeError(
                f"Chroma collection {collection_name!r} is empty after indexing"
            )
    finally:
        close_chroma_store(vector_store)

    result = BuildStats(
        **load_result.stats.as_dict(),
        chunks_indexed=len(chunks),
        collection_name=collection_name,
        persist_directory=str(persist_path),
        embedding_backend=resolved_backend,
        embedding_model=resolved_model,
        collection_count=collection_count,
    )
    LOGGER.info("vector database build complete: %s", result.as_dict())
    for error in load_result.errors:
        LOGGER.warning("skipped file=%s error=%s", error["file"], error["error"])
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the DHV ChromaDB collection from verified processed JSON."
    )
    parser.add_argument(
        "--data-dir",
        default=str(settings.processed_data_dir),
        help="validated processed JSON directory",
    )
    parser.add_argument(
        "--persist-dir",
        default=str(settings.chroma_persist_dir),
        help="ChromaDB persistence directory",
    )
    parser.add_argument(
        "--collection",
        default=settings.chroma_collection,
        help="ChromaDB collection name",
    )
    year_group = parser.add_mutually_exclusive_group()
    year_group.add_argument(
        "--year",
        type=int,
        default=None,
        help=f"knowledge-base year to index (default: {settings.target_year})",
    )
    year_group.add_argument(
        "--all-years",
        action="store_true",
        help=(
            "index verified documents from every year; source, DHV, and verification "
            "gates still apply (mutually exclusive with --year)"
        ),
    )
    parser.add_argument(
        "--embedding-backend",
        choices=("ollama", "sentence-transformers"),
        default=settings.embedding_backend,
        help="embedding backend",
    )
    parser.add_argument(
        "--embedding-model",
        default=settings.embedding_model,
        help="Ollama embedding model",
    )
    parser.add_argument(
        "--sentence-transformer-model",
        default=None,
        help=(
            "Sentence Transformers model name or local path "
            "(default: SENTENCE_TRANSFORMER_MODEL, then EMBEDDING_MODEL)"
        ),
    )
    parser.add_argument(
        "--ollama-base-url",
        default=settings.ollama_base_url,
        help="Ollama server URL",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--tokenizer-model", default=DEFAULT_TOKENIZER_MODEL)
    parser.add_argument(
        "--align-chunks-to-embedding",
        action="store_true",
        default=None,
        help="shrink chunks so they fit the embedding model's token window",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the configured ChromaDB directory before indexing",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.all_years:
        target_year = None
    elif args.year is not None:
        target_year = args.year
    else:
        target_year = settings.target_year
    try:
        stats = build_vector_db(
            data_directory=args.data_dir,
            persist_directory=args.persist_dir,
            collection_name=args.collection,
            embedding_backend=args.embedding_backend,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_base_url,
            sentence_transformer_model=args.sentence_transformer_model,
            target_year=target_year,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            tokenizer_model=args.tokenizer_model,
            reset=args.reset,
            align_chunks_to_embedding=args.align_chunks_to_embedding,
        )
    except Exception as exc:  # external embedding/vector-store services
        LOGGER.error("vector database build failed: %s", exc)
        return 1

    print(stats.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BuildStats",
    "build_vector_db",
    "embedding_token_limit",
    "main",
    "resolve_chunk_window",
]
