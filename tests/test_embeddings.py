from __future__ import annotations

import os
import sys
import unittest
from dataclasses import replace
from types import ModuleType
from unittest.mock import patch

from src.config.settings import load_settings, settings
from src.ingestion.embeddings import (
    create_embeddings,
    resolve_embedding_config,
    validate_embedding_metadata,
    SentenceTransformerEmbeddings,
)


class EmbeddingResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configured = replace(
            settings,
            embedding_backend="sentence-transformers",
            embedding_model="settings-active-model",
            sentence_transformer_model="legacy-sentence-model",
            ollama_embedding_model="legacy-ollama-model",
        )

    def test_cli_model_overrides_legacy_and_settings_values_for_both_backends(self) -> None:
        sentence_config = resolve_embedding_config(
            backend="st",
            model="audit/requested-model",
            sentence_transformer_model="audit/legacy-cli-model",
            settings_obj=self.configured,
        )
        ollama_config = resolve_embedding_config(
            backend="ollama",
            model="audit/requested-ollama-model",
            ollama_model="audit/legacy-ollama-cli-model",
            settings_obj=self.configured,
        )

        self.assertEqual(sentence_config.backend, "sentence-transformers")
        self.assertEqual(sentence_config.model, "audit/requested-model")
        self.assertEqual(ollama_config.backend, "ollama")
        self.assertEqual(ollama_config.model, "audit/requested-ollama-model")
        self.assertEqual(ollama_config.base_url, self.configured.ollama_base_url)

    def test_backend_specific_cli_then_active_settings_then_legacy_settings(self) -> None:
        explicit_legacy = resolve_embedding_config(
            backend="sentence-transformers",
            sentence_transformer_model="audit/legacy-cli-model",
            settings_obj=self.configured,
        )
        active_settings = resolve_embedding_config(settings_obj=self.configured)
        alternate_backend = resolve_embedding_config(
            backend="ollama", settings_obj=self.configured
        )

        self.assertEqual(explicit_legacy.model, "audit/legacy-cli-model")
        self.assertEqual(active_settings.model, "settings-active-model")
        self.assertEqual(alternate_backend.model, "legacy-ollama-model")

    def test_factory_receives_the_same_model_that_was_resolved(self) -> None:
        with patch(
            "src.ingestion.embeddings.SentenceTransformerEmbeddings"
        ) as sentence_factory:
            create_embeddings(
                backend="sentence_transformers",
                model="audit/requested-model",
                sentence_transformer_model="audit/environment-model",
                settings_obj=self.configured,
            )
        sentence_factory.assert_called_once_with("audit/requested-model")

        with patch("src.ingestion.embeddings.create_ollama_embeddings") as ollama_factory:
            create_embeddings(
                backend="ollama",
                model="audit/requested-ollama-model",
                ollama_model="audit/environment-ollama-model",
                settings_obj=self.configured,
            )
        ollama_factory.assert_called_once_with(
            model="audit/requested-ollama-model",
            base_url=self.configured.ollama_base_url,
        )

    def test_environment_canonical_model_overrides_legacy_values(self) -> None:
        values = {
            "EMBEDDING_BACKEND": "sentence-transformers",
            "EMBEDDING_MODEL": "audit/canonical-model",
            "SENTENCE_TRANSFORMER_MODEL": "audit/legacy-sentence-model",
            "OLLAMA_EMBEDDING_MODEL": "audit/legacy-ollama-model",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen-test",
        }
        with patch("src.config.settings.load_dotenv"), patch.dict(os.environ, values, clear=True):
            configured = load_settings()

        self.assertEqual(configured.embedding_model, "audit/canonical-model")
        self.assertEqual(configured.sentence_transformer_model, "audit/legacy-sentence-model")
        self.assertEqual(configured.ollama_embedding_model, "audit/legacy-ollama-model")

    def test_index_backend_model_and_dimension_mismatches_are_reported(self) -> None:
        config = resolve_embedding_config(settings_obj=self.configured)
        metadata = {
            "embedding_backend": config.backend,
            "embedding_model": config.model,
            "embedding_dimension": 768,
        }

        self.assertEqual(validate_embedding_metadata(metadata, config), 768)
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            validate_embedding_metadata(
                {**metadata, "embedding_model": "another-model"}, config
            )
        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            validate_embedding_metadata(metadata, config, query_dimension=384)

    def test_sentence_transformer_never_falls_back_to_an_implicit_download(self) -> None:
        calls: list[dict[str, object]] = []

        def sentence_transformer(model_name: str, **kwargs: object) -> object:
            calls.append({"model_name": model_name, **kwargs})
            raise OSError("model is not cached")

        fake_module = ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = sentence_transformer  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"sentence_transformers": fake_module}), patch(
            "src.ingestion.embeddings._SENTENCE_TRANSFORMER_CACHE", {}
        ):
            with self.assertRaisesRegex(
                RuntimeError, r"prepare_models --download-huggingface"
            ):
                SentenceTransformerEmbeddings("audit/missing-model")

        self.assertEqual(
            calls,
            [{"model_name": "audit/missing-model", "local_files_only": True}],
        )

    def test_sentence_transformer_download_requires_explicit_opt_in(self) -> None:
        calls: list[dict[str, object]] = []
        fake_model = object()

        def sentence_transformer(model_name: str, **kwargs: object) -> object:
            calls.append({"model_name": model_name, **kwargs})
            return fake_model

        fake_module = ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = sentence_transformer  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"sentence_transformers": fake_module}), patch(
            "src.ingestion.embeddings._SENTENCE_TRANSFORMER_CACHE", {}
        ):
            loaded = SentenceTransformerEmbeddings(
                "audit/download-model", allow_download=True
            )

        self.assertIs(loaded._model, fake_model)
        self.assertEqual(
            calls,
            [{"model_name": "audit/download-model", "local_files_only": False}],
        )


if __name__ == "__main__":
    unittest.main()
