"""Check or explicitly prepare the configured embedding and chunk tokenizer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import URLError
from urllib.request import urlopen


def _ollama_has_model(base_url: str, model: str) -> bool:
    """Check the configured Ollama server without starting it or pulling models."""

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Không kết nối được Ollama tại {base_url}. Khởi động Ollama rồi chạy "
            f"`ollama pull {model}`, sau đó chạy lại lệnh kiểm tra."
        ) from exc

    available = {
        str(item.get("name") or item.get("model") or "")
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    if model in available or f"{model}:latest" in available:
        return True
    raise RuntimeError(
        f"Ollama chưa có embedding model {model!r}. Chạy `ollama pull {model}` "
        "rồi kiểm tra lại. Lệnh chuẩn bị không tự tải model Ollama."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check that the configured embedding model and chunk tokenizer are ready. "
            "The default mode reads local caches and never downloads models."
        )
    )
    parser.add_argument(
        "--download-huggingface",
        action="store_true",
        help="explicitly download the configured Hugging Face tokenizer/embedding model",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    previous_offline_values = {
        key: os.environ.get(key)
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    }
    if args.download_huggingface:
        # Enable downloads only in this explicitly requested preparation process.
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)

    try:
        from src.config.settings import settings
        from src.ingestion.embeddings import create_embeddings, resolve_embedding_config
        from src.ingestion.splitter import DEFAULT_TOKENIZER_MODEL, _load_tokenizer

        embedding_config = resolve_embedding_config(settings_obj=settings)
        tokenizer = _load_tokenizer(
            DEFAULT_TOKENIZER_MODEL,
            allow_download=args.download_huggingface,
        )
        del tokenizer

        if embedding_config.backend == "sentence-transformers":
            embedding = create_embeddings(
                backend=embedding_config.backend,
                model=embedding_config.model,
                settings_obj=settings,
                allow_download=args.download_huggingface,
            )
            vector = embedding.embed_query("DHV model preflight")
            if not vector:
                raise RuntimeError(
                    f"Sentence Transformers model {embedding_config.model!r} returned an empty vector"
                )
        else:
            _ollama_has_model(embedding_config.base_url or "", embedding_config.model)

        print(
            "Model preparation succeeded: "
            f"embedding={embedding_config.backend}/{embedding_config.model}; "
            f"tokenizer={DEFAULT_TOKENIZER_MODEL}; "
            f"download={'enabled for this command' if args.download_huggingface else 'disabled'}"
        )
        return 0
    except Exception as exc:
        print(f"Model preparation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for key, value in previous_offline_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
