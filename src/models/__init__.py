"""Local model adapters used by the chatbot service."""

from .local_llm import LocalLLM, OllamaError, OllamaUnavailableError

__all__ = ["LocalLLM", "OllamaError", "OllamaUnavailableError"]
