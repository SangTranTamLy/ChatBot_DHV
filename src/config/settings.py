"""Cấu hình ứng dụng được tải từ file ``.env`` cấp dự án.

Task A chịu trách nhiệm quản lý cấu hình này. Các module xử lý dữ liệu (ingestion) cũ
có thể vẫn đọc các tên biến môi trường cũ cho đến khi chuyển sang dùng module này;
các bí danh (aliases) bên dưới giúp giữ tính tương thích ngược trong quá trình chuyển đổi.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_env(name: str, default: str, *aliases: str) -> str:
    """Đọc giá trị biến môi trường không rỗng, kiểm tra các bí danh cũ ở bước cuối."""

    for key in (name, *aliases):
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return default


def _read_int_env(name: str, default: int, *aliases: str) -> int:
    value = _read_env(name, str(default), *aliases)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


def _read_float_env(name: str, default: float, *aliases: str) -> float:
    value = _read_env(name, str(default), *aliases)
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    """Cấu hình không thể thay đổi (immutable) được chia sẻ giữa các tầng ứng dụng."""

    ollama_base_url: str
    ollama_model: str
    embedding_backend: str
    embedding_model: str
    chroma_persist_dir: Path
    chroma_collection: str
    processed_data_dir: Path
    processed_json_dir: Path
    retriever_top_k: int
    target_year: int
    ollama_timeout_seconds: float = 90.0
    rag_max_context_chars: int = 12000

    def __post_init__(self) -> None:
        parsed_url = urlparse(self.ollama_base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("OLLAMA_BASE_URL must be a valid HTTP(S) URL")
        if not self.ollama_model:
            raise ValueError("OLLAMA_MODEL must not be empty")
        if not self.embedding_model:
            raise ValueError("EMBEDDING_MODEL must not be empty")
        if self.embedding_backend not in {
            "ollama",
            "sentence-transformers",
            "sentence_transformers",
            "st",
        }:
            raise ValueError(
                "EMBEDDING_BACKEND must be 'ollama' or 'sentence-transformers'"
            )
        if self.retriever_top_k < 1:
            raise ValueError("RETRIEVER_TOP_K must be at least 1")
        if self.target_year < 2000:
            raise ValueError("TARGET_YEAR must be a four-digit year")
        if self.ollama_timeout_seconds <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero")
        if self.rag_max_context_chars < 100:
            raise ValueError("RAG_MAX_CONTEXT_CHARS must be at least 100")


def load_settings() -> Settings:
    """Tải các thiết lập chuẩn, kèm theo các giá trị mặc định an toàn cho môi trường phát triển cục bộ."""

    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        ollama_base_url=_read_env("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=_read_env(
            "OLLAMA_MODEL", "qwen2.5:3b", "OLLAMA_CHAT_MODEL"
        ),
        embedding_backend=_read_env("EMBEDDING_BACKEND", "ollama"),
        embedding_model=_read_env(
            "EMBEDDING_MODEL", "nomic-embed-text", "OLLAMA_EMBEDDING_MODEL"
        ),
        chroma_persist_dir=_project_path(
            _read_env("CHROMA_PERSIST_DIR", "chroma_db", "CHROMA_PERSIST_DIRECTORY")
        ),
        chroma_collection=_read_env(
            "CHROMA_COLLECTION", "dhv_admissions_2026"
        ),
        processed_data_dir=_project_path(
            _read_env(
                "PROCESSED_DATA_DIR", "data/processed", "DATA_PROCESSED_DIRECTORY"
            )
        ),
        processed_json_dir=_project_path(
            _read_env("PROCESSED_JSON_DIR", "data/processed_json")
        ),
        retriever_top_k=_read_int_env("RETRIEVER_TOP_K", 4, "RAG_TOP_K"),
        target_year=_read_int_env("TARGET_YEAR", 2026, "DHV_KB_YEAR"),
        ollama_timeout_seconds=_read_float_env("OLLAMA_TIMEOUT_SECONDS", 90.0),
        rag_max_context_chars=_read_int_env("RAG_MAX_CONTEXT_CHARS", 12000),
    )


settings = load_settings()

__all__ = ["PROJECT_ROOT", "Settings", "load_settings", "settings"]
