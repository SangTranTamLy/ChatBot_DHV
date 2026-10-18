# -*- coding: utf-8 -*-
"""
DHV Admissions Chatbot - Background Warmup Service
Pre-warms the SentenceTransformer embedding model and ChromaDB retriever in a
background daemon thread upon application startup.
Matches the architectural pattern of VietLabor AI (app/warmup.py).
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Ensure HuggingFace runs in offline mode immediately
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_warmup_lock = threading.Lock()
_warmup_started = False
_warmup_done = False
_warmup_thread: threading.Thread | None = None


def is_warmed_up() -> bool:
    """Returns True if the background warmup has completed."""
    return _warmup_done


def wait_for_warmup(timeout: float = 5.0) -> bool:
    """Blocks until background warmup completes or timeout expires."""
    if _warmup_done:
        return True
    if _warmup_thread is not None and _warmup_thread.is_alive():
        _warmup_thread.join(timeout=timeout)
    return _warmup_done


def _warmup_worker() -> None:
    global _warmup_done
    t0 = time.perf_counter()
    logger.info("[Warmup] Starting background warmup of DHV RAG engine...")

    try:
        # Step 1: Pre-load SentenceTransformer embeddings
        from src.ingestion.embeddings import create_embeddings
        emb = create_embeddings()
        if hasattr(emb, "embed_query"):
            emb.embed_query("DHV tuyển sinh 2026")
        logger.info("[Warmup] Embeddings initialized in %.2fs", time.perf_counter() - t0)

        # Step 2: Pre-load Chroma retriever
        from src.chatbot.rag_chain import _get_default_retriever
        retriever = _get_default_retriever()
        if retriever is not None and hasattr(retriever, "retrieve"):
            retriever.retrieve("ngành đào tạo")
        logger.info("[Warmup] Chroma retriever initialized in %.2fs", time.perf_counter() - t0)

    except Exception as exc:
        logger.warning("[Warmup] Non-critical background warmup error: %s", exc)
    finally:
        _warmup_done = True
        elapsed = time.perf_counter() - t0
        logger.info("[Warmup] Completed in %.2fs. Chatbot is hot-ready.", elapsed)


def start_background_warmup() -> None:
    """Launches the warmup thread once in the background.

    Idempotent and safe to call multiple times from Streamlit or API.
    """
    global _warmup_started, _warmup_thread
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True
        _warmup_thread = threading.Thread(
            target=_warmup_worker,
            name="dhv-warmup-worker",
            daemon=True,
        )
        _warmup_thread.start()


__all__ = ["is_warmed_up", "start_background_warmup"]
