from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from src.config.settings import settings
from src.ingestion.prepare_models import main


class ModelPreflightTests(unittest.TestCase):
    def test_default_preflight_uses_local_cache_without_changing_offline_policy(self) -> None:
        configured = replace(
            settings,
            embedding_backend="sentence-transformers",
            embedding_model="audit/local-model",
        )
        observed: dict[str, object] = {}

        def load_tokenizer(model_name: str, *, allow_download: bool = False) -> object:
            observed["tokenizer_model"] = model_name
            observed["allow_download"] = allow_download
            observed["hub_offline"] = os.environ.get("HF_HUB_OFFLINE")
            return object()

        class Embedding:
            @staticmethod
            def embed_query(_: str) -> list[float]:
                return [1.0]

        original_offline = {
            key: os.environ.get(key)
            for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
        }
        with patch("src.config.settings.settings", configured), patch(
            "src.ingestion.splitter._load_tokenizer", side_effect=load_tokenizer
        ), patch("src.ingestion.embeddings.create_embeddings", return_value=Embedding()), patch.dict(
            os.environ,
            {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            clear=False,
        ):
            result = main([])
            observed["hub_after_main"] = os.environ.get("HF_HUB_OFFLINE")
            observed["transformers_after_main"] = os.environ.get("TRANSFORMERS_OFFLINE")

        self.assertEqual(result, 0)
        self.assertFalse(observed["allow_download"])
        self.assertEqual(observed["hub_offline"], "1")
        self.assertEqual(observed["hub_after_main"], "1")
        self.assertEqual(observed["transformers_after_main"], "1")
        self.assertEqual(
            {key: os.environ.get(key) for key in original_offline}, original_offline
        )

    def test_huggingface_download_requires_explicit_flag_and_is_process_scoped(self) -> None:
        configured = replace(
            settings,
            embedding_backend="sentence-transformers",
            embedding_model="audit/download-model",
        )
        observed: dict[str, object] = {}

        def load_tokenizer(model_name: str, *, allow_download: bool = False) -> object:
            observed["allow_download"] = allow_download
            observed["hub_offline"] = os.environ.get("HF_HUB_OFFLINE")
            return object()

        class Embedding:
            @staticmethod
            def embed_query(_: str) -> list[float]:
                return [1.0]

        original_offline = {
            key: os.environ.get(key)
            for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
        }
        with patch("src.config.settings.settings", configured), patch(
            "src.ingestion.splitter._load_tokenizer", side_effect=load_tokenizer
        ), patch("src.ingestion.embeddings.create_embeddings", return_value=Embedding()), patch.dict(
            os.environ,
            {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            clear=False,
        ):
            result = main(["--download-huggingface"])
            observed["hub_after_main"] = os.environ.get("HF_HUB_OFFLINE")
            observed["transformers_after_main"] = os.environ.get("TRANSFORMERS_OFFLINE")

        self.assertEqual(result, 0)
        self.assertTrue(observed["allow_download"])
        self.assertIsNone(observed["hub_offline"])
        self.assertEqual(observed["hub_after_main"], "1")
        self.assertEqual(observed["transformers_after_main"], "1")
        self.assertEqual(
            {key: os.environ.get(key) for key in original_offline}, original_offline
        )


if __name__ == "__main__":
    unittest.main()
