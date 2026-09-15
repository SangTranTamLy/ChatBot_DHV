"""Adapter nhỏ gọn, không phụ thuộc vào retrieval, dành cho model chat Ollama cục bộ."""

from __future__ import annotations

from typing import Any

from src.config.settings import Settings, settings


class OllamaError(RuntimeError):
    """Lỗi cơ sở khi phản hồi từ Ollama bị thất bại hoặc sai định dạng."""


class OllamaUnavailableError(OllamaError):
    """Ollama đang offline, không thể kết nối, hoặc model được cấu hình không tồn tại."""


class LocalLLM:
    """Sinh văn bản bằng model Ollama đã cấu hình.

    Chức năng truy xuất (Retrieval) cố tình không được đưa vào class này. Service sẽ truyền
    một prompt RAG hoàn chỉnh, giúp adapter của model nội bộ có thể được kiểm thử
    độc lập và ngăn nó tự bịa ra danh sách nguồn.
    """

    def __init__(
        self,
        *,
        settings_obj: Settings = settings,
        client: Any | None = None,
    ) -> None:
        self.model = settings_obj.ollama_model
        self.base_url = settings_obj.ollama_base_url
        self.timeout_seconds = settings_obj.ollama_timeout_seconds
        if client is not None:
            self._client = client
            return
        try:
            from ollama import Client
        except ImportError as exc:  # pragma: no cover - thư viện phụ thuộc đã có trong requirements
            raise OllamaUnavailableError(
                "Ollama Python client is not installed"
            ) from exc
        try:
            self._client = Client(
                host=self.base_url,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - việc khởi tạo client nằm ở bên ngoài
            raise OllamaUnavailableError("Ollama client is unavailable") from exc

    def generate(self, prompt: str) -> str:
        """Trả về văn bản của model hoặc một lỗi Ollama an toàn, đã được phân loại."""

        if not isinstance(prompt, str) or not prompt.strip():
            raise OllamaError("prompt must not be empty")
        try:
            response = self._client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
        except Exception as exc:
            raise OllamaUnavailableError("Ollama request failed") from exc

        content = _extract_content(response)
        if not content:
            raise OllamaError("Ollama returned an empty response")
        return content


def _extract_content(response: Any) -> str:
    """Hỗ trợ cả đối tượng phản hồi từ Ollama và dạng dictionary của nó."""

    message = getattr(response, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content is not None:
            return str(content).strip()
    if isinstance(response, dict):
        message = response.get("message") or {}
        if isinstance(message, dict) and message.get("content") is not None:
            return str(message["content"]).strip()
    return ""


__all__ = ["LocalLLM", "OllamaError", "OllamaUnavailableError"]
