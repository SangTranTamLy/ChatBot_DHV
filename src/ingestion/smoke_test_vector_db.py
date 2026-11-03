"""Run the required retrieval smoke tests against the persisted ChromaDB."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from langchain_chroma import Chroma

from src.config.settings import settings

from .chroma_lifecycle import close_chroma_store
from .embeddings import (
    create_embeddings,
    resolve_embedding_config,
    validate_embedding_metadata,
)


LOGGER = logging.getLogger(__name__)
SMOKE_QUERIES: tuple[tuple[str, str], ...] = (
    (f"Học phí DHV {settings.target_year}", "hoc_phi"),
    (f"Học bổng DHV {settings.target_year}", "hoc_bong"),
    (f"Nhập học DHV {settings.target_year}", "ho_so"),
    (f"Thông tin trường DHV {settings.target_year}", "thong_tin_truong"),
)


def _result_summary(document: Any) -> dict[str, Any]:
    metadata = document.metadata
    return {
        "category": metadata.get("category"),
        "year": metadata.get("year"),
        "source_url": metadata.get("source_url"),
        "source_file": metadata.get("source_file"),
        "heading_path": metadata.get("heading_path"),
        "content_preview": document.page_content[:220].replace("\n", " | "),
    }


def _print_console_safe(value: object) -> None:
    """Print Unicode diagnostics safely in legacy Windows CMD code pages."""

    text = str(value)
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="backslashreplace").decode("ascii"))


def run_smoke_tests(
    *,
    backend: str,
    embedding_model: str | None,
    sentence_transformer_model: str | None,
    ollama_base_url: str,
    persist_directory: str,
    collection_name: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Query Chroma with the same embedding backend/model used for indexing."""

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    embedding_config = resolve_embedding_config(
        backend=backend,
        model=embedding_model,
        ollama_base_url=ollama_base_url,
        sentence_transformer_model=sentence_transformer_model,
    )
    embedding_function = create_embeddings(
        backend=embedding_config.backend,
        model=embedding_config.model,
        ollama_base_url=embedding_config.base_url,
    )
    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=embedding_function,
    )
    try:
        if vector_store._collection.count() == 0:
            raise RuntimeError("ChromaDB collection is empty")
        validate_embedding_metadata(vector_store._collection.metadata, embedding_config)

        all_results: list[dict[str, Any]] = []
        for query, expected_category in SMOKE_QUERIES:
            query_vector = embedding_function.embed_query(query)
            validate_embedding_metadata(
                vector_store._collection.metadata,
                embedding_config,
                query_dimension=len(query_vector),
            )
            documents = vector_store.similarity_search_by_vector(query_vector, k=top_k)
            if not documents:
                raise AssertionError(f"no retrieval result for query: {query}")
            summaries = [_result_summary(document) for document in documents]
            _print_console_safe(f"QUERY: {query}")
            for summary in summaries:
                _print_console_safe(json.dumps(summary, ensure_ascii=False))

            matching = [
                document
                for document in documents
                if document.metadata.get("category") == expected_category
                and document.metadata.get("year") == settings.target_year
            ]
            if not matching:
                raise AssertionError(
                    f"expected category={expected_category!r}, "
                    f"year={settings.target_year} for query: {query}"
                )

            if expected_category == "hoc_phi":
                if not any(
                    document.metadata.get("source_url")
                    and "học phí" in document.page_content.lower()
                    for document in matching
                ):
                    raise AssertionError(
                        "tuition result must include source_url and tuition content"
                    )
            if expected_category == "thong_tin_truong":
                if not any(
                    document.metadata.get("source_url")
                    and "thành lập" in document.page_content.lower()
                    and document.metadata.get("verification_status") == "verified"
                    for document in matching
                ):
                    raise AssertionError(
                        "school-info result must include verified source_url and school content"
                    )

            all_results.append(
                {
                    "query": query,
                    "expected_category": expected_category,
                    "results": summaries,
                }
            )
        _print_console_safe("SMOKE_PASS")
        return all_results
    finally:
        close_chroma_store(vector_store)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-backend", default=settings.embedding_backend)
    parser.add_argument("--embedding-model", default=None)
    parser.add_argument(
        "--sentence-transformer-model",
        default=None,
    )
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--persist-dir", default=str(settings.chroma_persist_dir))
    parser.add_argument("--collection", default=settings.chroma_collection)
    parser.add_argument("--top-k", type=int, default=settings.retriever_top_k)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        run_smoke_tests(
            backend=args.embedding_backend,
            embedding_model=args.embedding_model,
            sentence_transformer_model=args.sentence_transformer_model,
            ollama_base_url=args.ollama_base_url,
            persist_directory=args.persist_dir,
            collection_name=args.collection,
            top_k=args.top_k,
        )
    except Exception as exc:  # external embedding/vector-store services
        LOGGER.error("retrieval smoke test failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SMOKE_QUERIES", "main", "run_smoke_tests"]
