"""Các hàm hỗ trợ vòng đời nhỏ gọn dành cho client ChromaDB cục bộ."""

from __future__ import annotations

from typing import Any


def close_chroma_store(vector_store: Any) -> None:
    """Giải phóng tài nguyên Chroma để các file lưu trữ có thể được xóa trên Windows.

    Các phiên bản ChromaDB gần đây hỗ trợ ``Client.close``. Cách dự phòng (fallback) giúp
    hàm này vẫn tương thích với các phiên bản cũ hơn được dự án hỗ trợ.
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
