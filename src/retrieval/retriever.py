"""Chroma retriever for the verified DHV admissions knowledge base."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config.settings import Settings, settings
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.embeddings import create_embeddings


class RetrieverError(RuntimeError):
    """Base error for a vector-store retrieval failure."""


class VectorDatabaseError(RetrieverError):
    """The configured Chroma database or collection cannot be read."""


class RetrieverEmbeddingError(RetrieverError):
    """The configured embedding service failed while encoding a query."""


_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_TOKEN_RE = re.compile(r"\d{7}|[a-zA-ZÀ-ỹĐđ]+", re.UNICODE)
_RETRIEVAL_STOPWORDS = frozenset(
    {"va", "la", "cua", "cho", "toi", "ban", "dhv", "nam", "co", "ve", "diem"}
)


@dataclass(frozen=True)
class RetrievalAudit:
    """Serializable audit information for retrieval-only evaluation."""

    query: str
    normalized_query: str
    metadata_filter: dict[str, object]
    top_k: int
    hits: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "metadata_filter": self.metadata_filter,
            "top_k": self.top_k,
            "hits": [dict(hit) for hit in self.hits],
        }


@dataclass(frozen=True)
class RetrievalResult:
    """Documents plus an audit trace; generation is intentionally absent."""

    documents: tuple[Document, ...]
    audit: RetrievalAudit


def _normalise_tokens(value: str) -> set[str]:
    folded = _normalize(value)
    return {
        token
        for token in _TOKEN_RE.findall(folded)
        if token not in _RETRIEVAL_STOPWORDS and (len(token) >= 3 or token.isdigit())
    }


def _document_identity(document: Document) -> str:
    metadata = document.metadata or {}
    return str(metadata.get("chunk_id") or metadata.get("source_file") or id(document))


def _keyword_score(query: str, document: Document) -> float:
    query_tokens = _normalise_tokens(query)
    content = _normalize(document.page_content)
    content_tokens = _normalise_tokens(document.page_content)
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & content_tokens)
    score = float(overlap)
    if _normalize(query).strip() and _normalize(query).strip() in content:
        score += 5.0
    for token in query_tokens:
        if len(token) >= 7 and token in content:
            score += 1.5
    return score


def requested_year(question: str) -> int | None:
    """Return an explicitly mentioned four-digit year, if present."""

    match = _YEAR_RE.search(question or "")
    return int(match.group(1)) if match else None


def topic_category(question: str) -> str | None:
    """Infer a broad corpus category from topic words, without using facts."""

    normalized = _normalize(question)
    if "xac nhan nhap hoc" in normalized:
        return "lich_tuyen_sinh"
    if "hoc phi" in normalized:
        return "hoc_phi"
    if "hoc bong" in normalized:
        return "hoc_bong"
    if "xet tuyen bo sung" in normalized or "tuyen sinh bo sung" in normalized:
        return "xet_tuyen_bo_sung"
    if "ho so" in normalized or "giay to" in normalized:
        return "ho_so"
    if "thu tuc nhap hoc" in normalized:
        return "ho_so"
    if "nhap hoc" in normalized:
        return "nhap_hoc"
    if "lich tuyen sinh" in normalized or "lich xet tuyen" in normalized or "han xet tuyen" in normalized:
        return "lich_tuyen_sinh"
    if "diem trung tuyen" in normalized or "diem chuan" in normalized:
        return "diem_trung_tuyen"
    if (
        "diem san" in normalized
        or "nguong dau vao" in normalized
        or "nguong dam bao chat luong" in normalized
    ):
        return "nguong_dau_vao"
    # Specific topic markers must win over a broad mention of "ngành" or
    # "chương trình", otherwise e.g. "phương thức xét tuyển của ngành CNTT"
    # would be sent to the programme catalogue.
    if (
        "phuong thuc" in normalized
        or "hinh thuc xet tuyen" in normalized
        or "to hop xet tuyen" in normalized
        or "to hop mon" in normalized
        or "to hop" in normalized
    ):
        return "phuong_thuc_xet_tuyen"
    if (
        "cach tinh diem" in normalized
        or "cong thuc diem" in normalized
        or "quy doi diem" in normalized
        or "diem xet tuyen" in normalized
    ):
        return "cach_tinh_diem"
    if (
        ("dang ky" in normalized or "cong dang ky" in normalized or "cong thong tin xet tuyen" in normalized or "nop nguyen vong" in normalized or "nguyen vong" in normalized)
        and "nhap hoc" not in normalized
        and "lich " not in normalized
        and "han xet tuyen" not in normalized
    ):
        return "dang_ky_xet_tuyen"
    if (
        "co so" in normalized
        or "hotline" in normalized
        or "lien he" in normalized
        or "dia chi" in normalized
        or "so dien thoai" in normalized
        or "dien thoai" in normalized
        or "email" in normalized
    ):
        return "co_so_lien_he"
    if "nganh" in normalized or "chuong trinh" in normalized:
        return "nganh_dao_tao"
    return None


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return folded.lower().replace("đ", "d")


def _categories_from_question(question: str) -> tuple[str, ...]:
    category = topic_category(question)
    return (category,) if category else ()


def _metadata_filter(target_year: int, categories: tuple[str, ...]) -> dict[str, object]:
    if not categories:
        return {"year": target_year}
    if len(categories) == 1:
        return {"$and": [{"year": target_year}, {"category": categories[0]}]}
    return {
        "$and": [
            {"year": target_year},
            {"$or": [{"category": category} for category in categories]},
        ]
    }


def _rank_hybrid_candidates(
    query: str,
    candidates: Iterable[Document],
    vector_documents: list[Document],
    vector_scores: dict[str, float],
    target_year: int,
    top_k: int,
) -> list[Document]:
    vector_rank = {
        _document_identity(document): rank
        for rank, document in enumerate(vector_documents, start=1)
    }
    unique: dict[str, Document] = {}
    for document in candidates:
        if _is_verified_dhv_document(document, target_year):
            unique.setdefault(_document_identity(document), document)
    ranked = []
    for identity, document in unique.items():
        keyword_score = _keyword_score(query, document)
        ranked.append(
            (
                -keyword_score,
                vector_rank.get(identity, 10**6),
                vector_scores.get(identity, 10**6),
                identity,
                document,
            )
        )
    ranked.sort(key=lambda item: item[:4])
    return [item[4] for item in ranked[:top_k]]


def _audit_hit(
    document: Document,
    rank: int,
    query: str,
    vector_documents: list[Document],
) -> dict[str, object]:
    metadata = document.metadata or {}
    vector_rank = next(
        (
            position
            for position, candidate in enumerate(vector_documents, start=1)
            if _document_identity(candidate) == _document_identity(document)
        ),
        None,
    )
    return {
        "rank": rank,
        "score": _keyword_score(query, document),
        "keyword_score": _keyword_score(query, document),
        "vector_rank": vector_rank,
        "category": metadata.get("category"),
        "year": metadata.get("year"),
        "status": metadata.get("status"),
        "title": metadata.get("title"),
        "source_file": metadata.get("source_file"),
        "chunk_id": metadata.get("chunk_id"),
        "content_preview": document.page_content[:220].replace("\n", " | "),
    }


class DHVRetriever:
    """Lazy hybrid Chroma retriever using the Task B embedding contract.

    Chroma remains the source of truth.  A small runtime keyword pass over the
    same collection is used only to improve exact entity/code matching; it does
    not write to the collection or change its embeddings.
    """

    def __init__(
        self,
        *,
        settings_obj: Settings = settings,
        store_factory: Callable[..., Any] = Chroma,
        embedding_factory: Callable[..., Any] = create_embeddings,
    ) -> None:
        self.settings = settings_obj
        self._store_factory = store_factory
        self._embedding_factory = embedding_factory

    def retrieve(self, question: str) -> list[Document]:
        """Retrieve verified documents for the configured knowledge-base year.

        An explicit request for a different year is treated as no data. This
        is important because dense retrieval would otherwise return nearby
        2026 chunks for a question asking about 2027.
        """

        return list(self.retrieve_with_audit(question).documents)

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: Iterable[str] | None = None,
        retrieval_query: str | None = None,
    ) -> RetrievalResult:
        """Retrieve top-k verified chunks and return a generation-free audit."""

        query = (retrieval_query or question or "").strip()
        original_query = (question or "").strip()
        empty_audit = RetrievalAudit(
            query=original_query,
            normalized_query=_normalize(query),
            metadata_filter={"year": self.settings.target_year},
            top_k=self.settings.retriever_top_k,
            hits=(),
        )
        if not query:
            return RetrievalResult((), empty_audit)
        year = requested_year(original_query) or requested_year(query)
        if year is not None and year != self.settings.target_year:
            return RetrievalResult((), empty_audit)

        persist_directory = Path(self.settings.chroma_persist_dir)
        if not persist_directory.exists() or not persist_directory.is_dir():
            raise VectorDatabaseError(
                f"Chroma persist directory is missing: {persist_directory}"
            )

        try:
            embedding_function = self._embedding_factory(
                backend=self.settings.embedding_backend,
                ollama_model=self.settings.embedding_model,
                ollama_base_url=self.settings.ollama_base_url,
            )
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("query embedding backend could not be created") from exc

        try:
            vector_store = self._store_factory(
                collection_name=self.settings.chroma_collection,
                persist_directory=str(persist_directory),
                embedding_function=embedding_function,
            )
        except Exception as exc:
            raise VectorDatabaseError("ChromaDB could not be opened") from exc

        metadata_filter = _metadata_filter(
            self.settings.target_year,
            tuple(categories) if categories is not None else _categories_from_question(original_query),
        )
        try:
            count = vector_store._collection.count()
            if count <= 0:
                raise VectorDatabaseError("Chroma collection is empty")

            vector_documents, vector_scores = self._vector_search(
                vector_store,
                query,
                metadata_filter,
            )
            candidates = self._collection_candidates(vector_store, metadata_filter)
            if not candidates:
                candidates = list(vector_documents)
            documents = _rank_hybrid_candidates(
                query,
                candidates,
                vector_documents,
                vector_scores,
                self.settings.target_year,
                self.settings.retriever_top_k,
            )
        except RetrieverEmbeddingError:
            raise
        except VectorDatabaseError:
            raise
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("Chroma similarity search failed") from exc
        finally:
            close_chroma_store(vector_store)

        hits = tuple(
            _audit_hit(document, rank, query, vector_documents)
            for rank, document in enumerate(documents, start=1)
        )
        audit = RetrievalAudit(
            query=original_query,
            normalized_query=_normalize(query),
            metadata_filter=metadata_filter,
            top_k=self.settings.retriever_top_k,
            hits=hits,
        )
        return RetrievalResult(tuple(documents), audit)

    def _vector_search(
        self,
        vector_store: Any,
        query: str,
        metadata_filter: dict[str, object],
    ) -> tuple[list[Document], dict[str, float]]:
        try:
            if hasattr(vector_store, "similarity_search_with_score"):
                pairs = vector_store.similarity_search_with_score(
                    query,
                    k=self.settings.retriever_top_k,
                    filter=metadata_filter,
                )
                documents = [pair[0] for pair in pairs]
                scores = {
                    _document_identity(document): float(pair[1])
                    for document, pair in zip(documents, pairs)
                }
                return documents, scores
            documents = vector_store.similarity_search(
                query,
                k=self.settings.retriever_top_k,
                filter=metadata_filter,
            )
            return list(documents), {}
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("Chroma similarity search failed") from exc

    @staticmethod
    def _collection_candidates(
        vector_store: Any,
        metadata_filter: dict[str, object],
    ) -> list[Document]:
        """Read the existing collection for keyword reranking, never mutate it."""

        getter = getattr(vector_store, "get", None)
        if not callable(getter):
            return []
        try:
            payload = getter(
                where=metadata_filter,
                include=["documents", "metadatas"],
            )
        except Exception:
            return []
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        return [
            Document(page_content=str(content or ""), metadata=dict(metadata or {}))
            for content, metadata in zip(documents, metadatas)
            if content
        ]


def _is_verified_dhv_document(document: Document, target_year: int) -> bool:
    metadata = document.metadata or {}
    return (
        metadata.get("status") == "verified"
        and metadata.get("year") == target_year
        and metadata.get("school_code") == "DHV"
        and bool(str(metadata.get("source_url", "")).strip())
        and bool(document.page_content.strip())
    )


def retrieve_documents(question: str) -> list[Document]:
    """Convenience function for callers that use the default settings."""

    return DHVRetriever().retrieve(question)


__all__ = [
    "DHVRetriever",
    "RetrievalAudit",
    "RetrieverEmbeddingError",
    "RetrieverError",
    "RetrievalResult",
    "VectorDatabaseError",
    "requested_year",
    "topic_category",
    "retrieve_documents",
]
