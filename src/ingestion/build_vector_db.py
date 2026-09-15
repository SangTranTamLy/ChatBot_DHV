"""Xây dựng hoặc xây dựng lại collection ChromaDB của DHV.

Chạy từ thư mục gốc của dự án:

    python -m src.ingestion.build_vector_db --reset

Lệnh này sử dụng Ollama embeddings được cấu hình trong ``.env`` hoặc qua tham số dòng lệnh.
Nó chỉ lập chỉ mục các file Markdown đã được xác thực từ thư mục ``data/processed``.
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

from .embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL, create_embeddings
from .chroma_lifecycle import close_chroma_store
from .loader import LoadResult, load_verified_documents
from .splitter import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, split_documents


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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reset_persist_directory(persist_directory: Path) -> None:
    """Chỉ xóa thư mục vector-store đã được cấu hình rõ ràng."""

    resolved = persist_directory.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.cwd().resolve():
        raise ValueError("refusing to reset a filesystem root or the project root")
    if resolved.exists():
        LOGGER.info("resetting vector store at %s", resolved)
        shutil.rmtree(resolved)


def _load_stats(load_result: LoadResult) -> dict[str, int]:
    return load_result.stats.as_dict()


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
    reset: bool = False,
) -> BuildStats:
    """Tải, chia đoạn, nhúng (embed) và lưu trữ corpus DHV đã xác thực."""

    load_result = load_verified_documents(data_directory, target_year=target_year)
    if not load_result.documents:
        stats = _load_stats(load_result)
        raise RuntimeError(
            "no verified Markdown documents found in "
            f"{data_directory}; load stats: {stats}"
        )

    chunks = split_documents(
        load_result.documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not chunks:
        raise RuntimeError("verified documents produced zero chunks")

    persist_path = Path(persist_directory)
    if reset:
        _reset_persist_directory(persist_path)
    persist_path.mkdir(parents=True, exist_ok=True)

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
            resolved_model = sentence_transformer_model or os.getenv(
                "SENTENCE_TRANSFORMER_MODEL",
                DEFAULT_SENTENCE_TRANSFORMER_MODEL,
            )
        embedding_function = create_embeddings(
            backend=resolved_backend,
            ollama_model=embedding_model,
            ollama_base_url=ollama_base_url,
            sentence_transformer_model=sentence_transformer_model,
        )
    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=str(persist_path),
        embedding_function=embedding_function,
    )
    try:
        vector_store.add_documents(
            chunks,
            ids=[chunk.metadata["chunk_id"] for chunk in chunks],
        )
    finally:
        close_chroma_store(vector_store)

    result = BuildStats(
        **_load_stats(load_result),
        chunks_indexed=len(chunks),
        collection_name=collection_name,
        persist_directory=str(persist_path),
        embedding_backend=resolved_backend,
        embedding_model=resolved_model,
    )
    LOGGER.info("vector database build complete: %s", result.as_dict())
    for error in load_result.errors:
        LOGGER.warning("skipped file=%s error=%s", error["file"], error["error"])
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default=str(settings.processed_data_dir),
        help="processed Markdown directory",
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
    parser.add_argument(
        "--year",
        type=int,
        default=settings.target_year,
        help="knowledge-base year to index (default: 2026)",
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
        default=os.getenv(
            "SENTENCE_TRANSFORMER_MODEL",
            DEFAULT_SENTENCE_TRANSFORMER_MODEL,
        ),
        help="Sentence Transformers model name or local path",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=settings.ollama_base_url,
        help="Ollama server URL",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
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
    try:
        stats = build_vector_db(
            data_directory=args.data_dir,
            persist_directory=args.persist_dir,
            collection_name=args.collection,
            embedding_backend=args.embedding_backend,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_base_url,
            sentence_transformer_model=args.sentence_transformer_model,
            target_year=args.year,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            reset=args.reset,
        )
    except (FileNotFoundError, NotADirectoryError, RuntimeError, ValueError, OSError) as exc:
        LOGGER.error("vector database build failed: %s", exc)
        return 1
    except Exception as exc:  # external embedding/vector-store services
        LOGGER.error("vector database build failed: %s", exc)
        return 1

    print(stats.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BuildStats", "build_vector_db", "main"]
