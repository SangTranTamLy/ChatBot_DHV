"""Small lifecycle helpers for local ChromaDB clients."""

from __future__ import annotations

from typing import Any


def close_chroma_store(vector_store: Any) -> None:
    """Release Chroma resources so persistent files can be removed on Windows.

    Recent ChromaDB releases expose ``Client.close``.  The fallback keeps the
    helper compatible with older releases supported by this project.
    """

    client = getattr(vector_store, "_client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()
        return

    system = getattr(client, "_system", None)
    stop = getattr(system, "stop", None)
    if callable(stop):
        stop()


__all__ = ["close_chroma_store"]
