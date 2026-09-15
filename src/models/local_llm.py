"""Small, retrieval-agnostic adapter for the local Ollama chat model."""

from __future__ import annotations

from typing import Any

from src.config.settings import Settings, settings


class OllamaError(RuntimeError):
    """Base error for a failed or malformed Ollama response."""


class OllamaUnavailableError(OllamaError):
    """Ollama is offline, unreachable, or the configured model is unavailable."""


class LocalLLM:
    """Generate text with the configured Ollama model.

    Retrieval is intentionally absent from this class. The service passes one
    complete RAG prompt, which keeps the local model adapter independently
    testable and prevents it from inventing a source list.
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
        except ImportError as exc:  # pragma: no cover - dependency is in requirements
            raise OllamaUnavailableError(
                "Ollama Python client is not installed"
            ) from exc
        try:
            self._client = Client(
                host=self.base_url,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - client construction is external
            raise OllamaUnavailableError("Ollama client is unavailable") from exc

    def generate(self, prompt: str) -> str:
        """Return the model's text or a safe, classified Ollama error."""

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
    """Support both the Ollama response object and its dictionary form."""

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
