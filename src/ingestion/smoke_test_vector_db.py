"""Run the required retrieval smoke tests against the persisted ChromaDB."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from langchain_chroma import Chroma

from src.config.settings import settings

from .chroma_lifecycle import close_chroma_store
from .embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL, create_embeddings


LOGGER = logging.getLogger(__name__)
SMOKE_QUERIES: tuple[tuple[str, str], ...] = (
    ("Học phí DHV 2026", "hoc_phi"),
    ("Học bổng DHV 2026", "hoc_bong"),
    ("Nhập học DHV 2026", "nhap_hoc"),
    ("Thông tin trường DHV 2026", "thong_tin_truong"),
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

    embedding_function = create_embeddings(
        backend=backend,
        ollama_model=embedding_model,
        ollama_base_url=ollama_base_url,
        sentence_transformer_model=sentence_transformer_model,
    )
    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=embedding_function,
    )
    try:
        if vector_store._collection.count() == 0:
            raise RuntimeError("ChromaDB collection is empty")

        all_results: list[dict[str, Any]] = []
        for query, expected_category in SMOKE_QUERIES:
            documents = vector_store.similarity_search(query, k=top_k)
            if not documents:
                raise AssertionError(f"no retrieval result for query: {query}")
            summaries = [_result_summary(document) for document in documents]
            print(f"QUERY: {query}")
            for summary in summaries:
                print(json.dumps(summary, ensure_ascii=False))

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
        print("SMOKE_PASS")
        return all_results
    finally:
        close_chroma_store(vector_store)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-backend", default=settings.embedding_backend)
    parser.add_argument("--embedding-model", default=settings.embedding_model)
    parser.add_argument(
        "--sentence-transformer-model",
        default=DEFAULT_SENTENCE_TRANSFORMER_MODEL,
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
