"""Factory tạo embedding cho model Ollama cục bộ đã được cấu hình."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Sequence

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from src.config.settings import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_SENTENCE_TRANSFORMER_MODEL,
    Settings,
    settings,
)


_SENTENCE_TRANSFORMER_CACHE: dict[str, Any] = {}
_MODEL_LOAD_LOCK = threading.RLock()
_EMBEDDINGS_INSTANCE_CACHE: dict[str, Any] = {}


@dataclass(frozen=True)
class EmbeddingConfig:
    backend: str
    model: str
    base_url: str | None = None


def validate_embedding_metadata(
    metadata: object,
    config: EmbeddingConfig,
    *,
    query_dimension: int | None = None,
) -> int:
    """Validate the persisted backend/model/dimension before querying Chroma."""

    if not isinstance(metadata, Mapping):
        raise ValueError("Chroma collection has no embedding metadata; rebuild the index")
    stored_backend = str(metadata.get("embedding_backend") or "")
    stored_model = str(metadata.get("embedding_model") or "")
    try:
        stored_dimension = int(metadata.get("embedding_dimension"))
    except (TypeError, ValueError):
        stored_dimension = 0
    if not stored_backend or not stored_model or stored_dimension <= 0:
        raise ValueError("Chroma collection has incomplete embedding metadata; rebuild the index")
    if stored_backend != config.backend or stored_model != config.model:
        raise ValueError(
            "Chroma embedding configuration mismatch: "
            f"index={stored_backend}/{stored_model}/{stored_dimension}, "
            f"configured={config.backend}/{config.model}; rebuild the index"
        )
    if query_dimension is not None and query_dimension != stored_dimension:
        raise ValueError(
            "Chroma embedding dimension mismatch: "
            f"index={stored_dimension}, configured={query_dimension}; rebuild the index"
        )
    return stored_dimension


def normalize_embedding_backend(backend: str) -> str:
    selected = (backend or "").strip().lower()
    if selected in {"sentence-transformers", "sentence_transformers", "st"}:
        return "sentence-transformers"
    if selected == "ollama":
        return "ollama"
    raise ValueError(
        f"unsupported embedding backend: {selected!r}; choose 'ollama' or 'sentence-transformers'"
    )


def resolve_embedding_config(
    *,
    backend: str | None = None,
    model: str | None = None,
    ollama_model: str | None = None,
    sentence_transformer_model: str | None = None,
    ollama_base_url: str | None = None,
    settings_obj: Settings = settings,
) -> EmbeddingConfig:
    """Resolve backend/model once for build, query, warmup, and diagnostics.

    Precedence: an explicit generic model, an explicit backend-specific legacy
    option, the active Settings model, then the selected backend's legacy
    Settings value. ``SENTENCE_TRANSFORMER_MODEL`` and ``OLLAMA_EMBEDDING_MODEL``
    are loaded into those legacy Settings fields.
    """

    selected_backend = normalize_embedding_backend(backend or settings_obj.embedding_backend)
    active_backend = normalize_embedding_backend(settings_obj.embedding_backend)
    if model and model.strip():
        selected_model = model.strip()
    elif selected_backend == "ollama":
        selected_model = (
            (ollama_model or "").strip()
            or (
                settings_obj.embedding_model
                if selected_backend == active_backend
                else settings_obj.ollama_embedding_model
            )
        )
    else:
        selected_model = (
            (sentence_transformer_model or "").strip()
            or (
                settings_obj.embedding_model
                if selected_backend == active_backend
                else settings_obj.sentence_transformer_model
            )
        )
    if not selected_model:
        selected_model = (
            DEFAULT_OLLAMA_EMBEDDING_MODEL
            if selected_backend == "ollama"
            else DEFAULT_SENTENCE_TRANSFORMER_MODEL
        )
    return EmbeddingConfig(
        backend=selected_backend,
        model=selected_model,
        base_url=(ollama_base_url or settings_obj.ollama_base_url)
        if selected_backend == "ollama"
        else None,
    )


class SentenceTransformerEmbeddings(Embeddings):
    """Adapter embedding của LangChain được hỗ trợ bởi Sentence Transformers."""

    def __init__(self, model_name: str, *, allow_download: bool = False) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Sentence Transformers is not installed. Run "
                "pip install sentence-transformers."
            ) from exc

        self.model_name = model_name
        if model_name not in _SENTENCE_TRANSFORMER_CACHE:
            with _MODEL_LOAD_LOCK:
                if model_name not in _SENTENCE_TRANSFORMER_CACHE:
                    try:
                        _SENTENCE_TRANSFORMER_CACHE[model_name] = SentenceTransformer(
                            model_name,
                            local_files_only=not allow_download,
                        )
                    except Exception as exc:
                        mode = "download was enabled but failed" if allow_download else "is not cached locally"
                        raise RuntimeError(
                            f"Sentence Transformers model {model_name!r} {mode}. "
                            "Run `python -m src.ingestion.prepare_models --download-huggingface` "
                            "to prepare it explicitly, or configure a cached model."
                        ) from exc
        self._model = _SENTENCE_TRANSFORMER_CACHE[model_name]

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

    model_name = model or settings.embedding_model
    server_url = base_url or settings.ollama_base_url
    return OllamaEmbeddings(model=model_name, base_url=server_url)


def create_embeddings(
    *,
    backend: str | None = None,
    model: str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    sentence_transformer_model: str | None = None,
    settings_obj: Settings = settings,
    allow_download: bool = False,
) -> Embeddings:
    """Create the resolved Ollama or Sentence Transformers embedding backend."""

    config = resolve_embedding_config(
        backend=backend,
        model=model,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
        sentence_transformer_model=sentence_transformer_model,
        settings_obj=settings_obj,
    )
    if config.backend == "ollama":
        return create_ollama_embeddings(
            model=config.model,
            base_url=config.base_url,
        )
    if config.backend == "sentence-transformers":
        model_name = config.model
        if model_name not in _EMBEDDINGS_INSTANCE_CACHE:
            with _MODEL_LOAD_LOCK:
                if model_name not in _EMBEDDINGS_INSTANCE_CACHE:
                    if allow_download:
                        _EMBEDDINGS_INSTANCE_CACHE[model_name] = SentenceTransformerEmbeddings(
                            model_name,
                            allow_download=True,
                        )
                    else:
                        _EMBEDDINGS_INSTANCE_CACHE[model_name] = SentenceTransformerEmbeddings(
                            model_name
                        )
        return _EMBEDDINGS_INSTANCE_CACHE[model_name]


__all__ = [
    "DEFAULT_SENTENCE_TRANSFORMER_MODEL",
    "EmbeddingConfig",
    "SentenceTransformerEmbeddings",
    "create_embeddings",
    "create_ollama_embeddings",
    "normalize_embedding_backend",
    "resolve_embedding_config",
    "validate_embedding_metadata",
]
