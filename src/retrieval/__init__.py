"""Retrieval adapters for the DHV knowledge base."""

from .retriever import (
    DHVRetriever,
    RetrievalAudit,
    RetrievalResult,
    RetrieverEmbeddingError,
    RetrieverError,
    VectorDatabaseError,
    requested_year,
    topic_category,
)

__all__ = [
    "DHVRetriever", #lớp truy xuất dữ liệu
    "RetrievalAudit", #cấu trúc dữ liệu kiểm toán truy xuất
    "RetrievalResult",
    "RetrieverEmbeddingError",
    "RetrieverError",
    "VectorDatabaseError",
    "requested_year",
    "topic_category",
]
