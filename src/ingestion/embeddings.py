"""Factory tạo embedding cho model Ollama cục bộ đã được cấu hình."""

from __future__ import annotations

import os
from typing import Sequence

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from src.config.settings import settings


DEFAULT_SENTENCE_TRANSFORMER_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


class SentenceTransformerEmbeddings(Embeddings):
    """Adapter embedding của LangChain được hỗ trợ bởi Sentence Transformers."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Sentence Transformers is not installed. Run "
                "pip install sentence-transformers."
            ) from exc

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


def create_ollama_embeddings(
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> OllamaEmbeddings:
    """Tạo client embedding Ollama từ các tham số hoặc thiết lập của dự án."""

    load_dotenv()
    model_name = model or settings.embedding_model
    server_url = base_url or settings.ollama_base_url
    return OllamaEmbeddings(model=model_name, base_url=server_url)


def create_embeddings(
    *,
    backend: str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    sentence_transformer_model: str | None = None,
) -> Embeddings:
    """Tạo backend Ollama hoặc Sentence Transformers đã được cấu hình."""

    load_dotenv()
    selected_backend = (backend or settings.embedding_backend).strip().lower()
    if selected_backend == "ollama":
        return create_ollama_embeddings(
            model=ollama_model,
            base_url=ollama_base_url,
        )
    if selected_backend in {"sentence-transformers", "sentence_transformers", "st"}:
        model_name = sentence_transformer_model or os.getenv(
            "SENTENCE_TRANSFORMER_MODEL",
            DEFAULT_SENTENCE_TRANSFORMER_MODEL,
        )
        return SentenceTransformerEmbeddings(model_name)
    raise ValueError(
        "unsupported embedding backend: "
        f"{selected_backend!r}; choose 'ollama' or 'sentence-transformers'"
    )


__all__ = [
    "DEFAULT_SENTENCE_TRANSFORMER_MODEL",
    "SentenceTransformerEmbeddings",
    "create_embeddings",
    "create_ollama_embeddings",
]
