"""Build or rebuild the DHV ChromaDB collection from structured JSON.

Chạy từ thư mục gốc của dự án:

    python -m src.ingestion.build_vector_db --reset

Lệnh này sử dụng Ollama embeddings được cấu hình trong ``.env`` hoặc qua tham số dòng lệnh.
The input is validated JSON in ``data/processed``. Generated Markdown is no
longer an accepted corpus representation. Stop chatbot processes that have
the configured Chroma directory open before publishing a new index; a locked
directory fails safely and leaves the prior index in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

from src.config.settings import PROJECT_ROOT, settings

from .embeddings import (
    create_embeddings,
    resolve_embedding_config,
)
from .chroma_lifecycle import close_chroma_store
from .loader import LoadResult, load_verified_documents
from .path_safety import (
    DEFAULT_RAW_DIR,
    cleanup_staging_directory,
    publish_staged_directory,
    unique_generated_sibling,
    validate_generated_directory,
)
from .splitter import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_TOKENIZER_MODEL,
    SPLITTER_SCHEMA_VERSION,
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
    embedding_dimension: int
    corpus_fingerprint: str
    splitter_schema_version: int
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


def _corpus_fingerprint(records: list[dict[str, Any]]) -> str:
    """Hash the complete, ordered chunk content and metadata for this build."""

    canonical_records = sorted(records, key=lambda record: str(record["id"]))
    payload = json.dumps(
        canonical_records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expected_chunk_records(chunks: list[Any]) -> list[dict[str, Any]]:
    records = [
        {
            "id": str(chunk.metadata.get("chunk_id") or ""),
            "document": str(chunk.page_content),
            "metadata": dict(chunk.metadata),
        }
        for chunk in chunks
    ]
    ids = [record["id"] for record in records]
    if any(not chunk_id for chunk_id in ids):
        raise RuntimeError("every generated chunk must have a non-empty chunk_id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("generated chunks contain duplicate chunk_id values")
    return records


def _validate_staged_collection(vector_store: Any, expected_records: list[dict[str, Any]]) -> int:
    """Require the staged collection to match the complete expected chunk set."""

    collection_count = int(vector_store._collection.count())
    expected_ids = {record["id"] for record in expected_records}
    indexed = vector_store.get(include=["documents", "metadatas"])
    indexed_ids = [str(chunk_id) for chunk_id in indexed.get("ids", [])]
    indexed_id_set = set(indexed_ids)
    if collection_count != len(expected_records) or indexed_id_set != expected_ids:
        missing = sorted(expected_ids - indexed_id_set)
        unexpected = sorted(indexed_id_set - expected_ids)
        raise RuntimeError(
            "staged Chroma chunk IDs do not match the expected corpus: "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}, "
            f"count={collection_count}, expected={len(expected_records)}"
        )

    actual_records = [
        {
            "id": chunk_id,
            "document": str(document),
            "metadata": dict(metadata or {}),
        }
        for chunk_id, document, metadata in zip(
            indexed_ids,
            indexed.get("documents", []),
            indexed.get("metadatas", []),
            strict=True,
        )
    ]
    expected_fingerprint = _corpus_fingerprint(expected_records)
    indexed_fingerprint = _corpus_fingerprint(actual_records)
    if indexed_fingerprint != expected_fingerprint:
        raise RuntimeError(
            "staged Chroma content or metadata differs from the expected corpus"
        )
    return collection_count


def _reset_persist_directory(
    persist_directory: Path,
    *,
    data_directory: str | Path = settings.processed_data_dir,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    project_root: str | Path = PROJECT_ROOT,
) -> None:
    """Chỉ xóa thư mục vector-store đã được cấu hình rõ ràng."""

    resolved = validate_generated_directory(
        persist_directory,
        protected_paths=(data_directory, raw_directory, settings.processed_data_dir),
        project_root=project_root,
        forbid_current_directory=True,
    )
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
    """Build a complete staged index, then publish it over the prior store."""

    persist_path = validate_generated_directory(
        persist_directory,
        protected_paths=(data_directory, DEFAULT_RAW_DIR, settings.processed_data_dir),
        project_root=PROJECT_ROOT,
        forbid_current_directory=True,
    )
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
        embedding_config = resolve_embedding_config(
            backend=embedding_backend,
            model=embedding_model,
            sentence_transformer_model=sentence_transformer_model,
            ollama_base_url=ollama_base_url,
            settings_obj=settings,
        )
        resolved_backend = embedding_config.backend
        resolved_model = embedding_config.model
        embedding_function = create_embeddings(
            backend=resolved_backend,
            model=resolved_model,
            ollama_base_url=embedding_config.base_url,
            settings_obj=settings,
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
    expected_records = _expected_chunk_records(chunks)
    corpus_fingerprint = _corpus_fingerprint(expected_records)

    query_vector = embedding_function.embed_query(chunks[0].page_content)
    embedding_dimension = len(query_vector)
    if embedding_dimension <= 0:
        raise RuntimeError("embedding backend returned an empty vector")

    staging = unique_generated_sibling(persist_path, purpose="staging")
    staging = validate_generated_directory(
        staging,
        protected_paths=(data_directory, DEFAULT_RAW_DIR, settings.processed_data_dir, persist_path),
        project_root=PROJECT_ROOT,
        forbid_current_directory=True,
    )
    persist_path.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        vector_store = Chroma(
            collection_name=collection_name,
            persist_directory=str(staging),
            embedding_function=embedding_function,
            collection_metadata={
                "embedding_backend": resolved_backend,
                "embedding_model": resolved_model,
                "embedding_dimension": embedding_dimension,
                "corpus_fingerprint": corpus_fingerprint,
                "splitter_schema_version": SPLITTER_SCHEMA_VERSION,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "tokenizer_model": tokenizer_model,
                "index_schema_version": 2,
            },
        )
        collection_count = 0
        try:
            vector_store.add_documents(
                chunks,
                ids=[chunk.metadata["chunk_id"] for chunk in chunks],
            )
            collection_count = _validate_staged_collection(vector_store, expected_records)
            smoke_results = vector_store.similarity_search(chunks[0].page_content, k=1)
            if not smoke_results:
                raise RuntimeError(
                    f"Chroma collection {collection_name!r} returned no result for its smoke query"
                )
        finally:
            close_chroma_store(vector_store)

        publish_staged_directory(
            staging,
            persist_path,
            protected_paths=(data_directory, DEFAULT_RAW_DIR, settings.processed_data_dir),
            project_root=PROJECT_ROOT,
            forbid_current_directory=True,
        )
    finally:
        try:
            cleanup_staging_directory(
                staging,
                persist_path,
                protected_paths=(data_directory, DEFAULT_RAW_DIR, settings.processed_data_dir),
                project_root=PROJECT_ROOT,
                forbid_current_directory=True,
            )
        except OSError as exc:
            LOGGER.warning("could not remove verified staging directory %s: %s", staging, exc)

    result = BuildStats(
        **load_result.stats.as_dict(),
        chunks_indexed=len(chunks),
        collection_name=collection_name,
        persist_directory=str(persist_path),
        embedding_backend=resolved_backend,
        embedding_model=resolved_model,
        embedding_dimension=embedding_dimension,
        corpus_fingerprint=corpus_fingerprint,
        splitter_schema_version=SPLITTER_SCHEMA_VERSION,
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
        default=None,
        help="model for the selected backend; overrides backend-specific settings",
    )
    parser.add_argument(
        "--sentence-transformer-model",
        default=None,
        help="legacy Sentence Transformers override; used when --embedding-model is omitted",
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
        help="accepted for compatibility; every build publishes a complete staged index",
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


__all__ = ["BuildStats", "build_vector_db", "main"]
