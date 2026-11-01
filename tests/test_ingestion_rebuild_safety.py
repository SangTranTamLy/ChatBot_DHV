from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.config.settings import settings
from src.ingestion.build_vector_db import build_vector_db
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.loader import LoadResult, LoadStats, load_verified_documents
from src.ingestion.path_safety import (
    cleanup_staging_directory,
    publish_staged_directory,
    unique_generated_sibling,
)
from src.ingestion.prepare_processed_from_raw import ProcessedDocument, rebuild_structured_json
from src.ingestion.splitter import SPLITTER_SCHEMA_VERSION
from src.ingestion.splitter import split_documents


class StructuredJsonRebuildSafetyTests(unittest.TestCase):
    def _raw_fixture(self, root: Path, pdf_names: tuple[str, ...] = ("first.pdf",)) -> Path:
        raw = root / "raw"
        raw.mkdir(parents=True)
        for name in pdf_names:
            (raw / name).write_bytes(b"PDF fixture")
        return raw

    def _manifest_patches(self):
        return (
            patch("src.ingestion.raw_manifest.load_raw_manifest", return_value={"documents": []}),
            patch("src.ingestion.raw_manifest.validate_manifest_sync", return_value=[]),
            patch("src.ingestion.raw_manifest.find_manifest_entry", return_value={}),
        )

    def _converted_document(self, pdf_path: Path, output_root: Path) -> ProcessedDocument:
        output = output_root / f"{pdf_path.stem}.json"
        output.write_text(f"new:{pdf_path.stem}", encoding="utf-8")
        return ProcessedDocument(
            raw_path=pdf_path,
            output_path=output,
            title=pdf_path.stem,
            category="fixture",
            source_url="https://dhv.edu.vn/fixture",
            source_date="30/10/2026",
            text=f"new:{pdf_path.stem}",
            records_count=1,
        )

    def test_missing_manifest_keeps_existing_processed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            raw = self._raw_fixture(root)
            output = root / "processed"
            output.mkdir()
            sentinel = output / "current.json"
            sentinel.write_text("CURRENT-PROCESSED", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "manifest is required"):
                rebuild_structured_json(raw_directory=raw, output_directory=output, reset=True)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "CURRENT-PROCESSED")
            self.assertEqual(list(root.glob(".processed.staging-*")), [])

    def test_manifest_mismatch_keeps_existing_processed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            raw = self._raw_fixture(root)
            (raw / "manifest.json").write_text("{}", encoding="utf-8")
            output = root / "processed"
            output.mkdir()
            sentinel = output / "current.json"
            sentinel.write_text("CURRENT-PROCESSED", encoding="utf-8")

            load_manifest, validate_manifest, find_entry = self._manifest_patches()
            with load_manifest, validate_manifest, find_entry, patch(
                "src.ingestion.raw_manifest.validate_manifest_sync",
                return_value=["missing manifest entry"],
            ), self.assertRaisesRegex(RuntimeError, "RAW/manifest sync failed"):
                rebuild_structured_json(raw_directory=raw, output_directory=output, reset=True)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "CURRENT-PROCESSED")

    def test_pdf_or_ocr_failure_does_not_publish_partial_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            raw = self._raw_fixture(root, ("first.pdf", "second.pdf"))
            (raw / "manifest.json").write_text("{}", encoding="utf-8")
            output = root / "processed"
            output.mkdir()
            sentinel = output / "current.json"
            sentinel.write_text("CURRENT-PROCESSED", encoding="utf-8")

            def convert(pdf_path: Path, *, output_root: Path, **_: object) -> ProcessedDocument:
                if pdf_path.name == "second.pdf":
                    raise RuntimeError("OCR engine failed")
                return self._converted_document(pdf_path, output_root)

            load_manifest, validate_manifest, find_entry = self._manifest_patches()
            with load_manifest, validate_manifest, find_entry, patch(
                "src.ingestion.prepare_processed_from_raw.convert_pdf_to_structured_json",
                side_effect=convert,
            ), self.assertRaisesRegex(RuntimeError, "OCR engine failed"):
                rebuild_structured_json(raw_directory=raw, output_directory=output, reset=True)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "CURRENT-PROCESSED")
            self.assertFalse((output / "first.json").exists())
            self.assertEqual(list(root.glob(".processed.staging-*")), [])

    def test_success_publishes_complete_json_and_returns_final_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            raw = self._raw_fixture(root, ("first.pdf", "second.pdf"))
            (raw / "manifest.json").write_text("{}", encoding="utf-8")
            output = root / "processed"
            output.mkdir()
            (output / "old.json").write_text("OLD", encoding="utf-8")

            load_manifest, validate_manifest, find_entry = self._manifest_patches()
            with load_manifest, validate_manifest, find_entry, patch(
                "src.ingestion.prepare_processed_from_raw.convert_pdf_to_structured_json",
                side_effect=lambda path, *, output_root, **_: self._converted_document(path, output_root),
            ):
                documents = rebuild_structured_json(
                    raw_directory=raw, output_directory=output, reset=True
                )

            self.assertEqual({path.name for path in output.glob("*.json")}, {"first.json", "second.json"})
            self.assertEqual(len(documents), 2)
            self.assertTrue(all(document.output_path.is_file() for document in documents))
            self.assertTrue(all(output in document.output_path.parents for document in documents))

    def test_reset_false_preserves_unrelated_existing_processed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            raw = self._raw_fixture(root)
            (raw / "manifest.json").write_text("{}", encoding="utf-8")
            output = root / "processed"
            output.mkdir()
            (output / "manual.json").write_text("KEEP", encoding="utf-8")

            load_manifest, validate_manifest, find_entry = self._manifest_patches()
            with load_manifest, validate_manifest, find_entry, patch(
                "src.ingestion.prepare_processed_from_raw.convert_pdf_to_structured_json",
                side_effect=lambda path, *, output_root, **_: self._converted_document(path, output_root),
            ):
                rebuild_structured_json(raw_directory=raw, output_directory=output, reset=False)

            self.assertEqual((output / "manual.json").read_text(encoding="utf-8"), "KEEP")
            self.assertTrue((output / "first.json").is_file())

    def test_publish_lock_failure_restores_old_directory_and_keeps_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            destination = root / "processed"
            destination.mkdir(parents=True)
            (destination / "current.json").write_text("CURRENT", encoding="utf-8")
            staging = unique_generated_sibling(destination, purpose="staging")
            staging.mkdir()
            (staging / "new.json").write_text("NEW", encoding="utf-8")
            original_replace = __import__("os").replace

            def replace(source: str | Path, target: str | Path) -> None:
                if Path(source) == staging and Path(target) == destination:
                    raise PermissionError("destination is locked")
                original_replace(source, target)

            with patch("src.ingestion.path_safety.os.replace", side_effect=replace):
                with self.assertRaisesRegex(PermissionError, "destination is locked"):
                    publish_staged_directory(
                        staging,
                        destination,
                        protected_paths=(root / "raw",),
                        project_root=root,
                    )

            self.assertEqual((destination / "current.json").read_text(encoding="utf-8"), "CURRENT")
            self.assertFalse((destination / "new.json").exists())
            cleanup_staging_directory(
                staging,
                destination,
                protected_paths=(root / "raw",),
                project_root=root,
            )


class SmallEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class VectorRebuildSafetyTests(unittest.TestCase):
    def _store_with_old_record(self, persist_dir: Path) -> None:
        persist_dir.mkdir(parents=True)
        store = Chroma(
            collection_name="fixture",
            persist_directory=str(persist_dir),
            embedding_function=SmallEmbeddings(),
        )
        try:
            store.add_documents(
                [Document(page_content="old indexed value", metadata={"chunk_id": "old-id"})],
                ids=["old-id"],
            )
        finally:
            close_chroma_store(store)

    def _assert_old_record_queryable(self, persist_dir: Path) -> None:
        store = Chroma(
            collection_name="fixture",
            persist_directory=str(persist_dir),
            embedding_function=SmallEmbeddings(),
        )
        try:
            result = store.similarity_search("old indexed value", k=1)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].page_content, "old indexed value")
        finally:
            close_chroma_store(store)

    def _build_inputs(self, root: Path) -> tuple[Path, Path, LoadResult, list[Document]]:
        data_dir = root / "processed"
        persist_dir = root / "chroma_db"
        load_result = LoadResult(
            documents=[Document(page_content="new indexed value", metadata={"status": "verified"})],
            stats=LoadStats(files_seen=1, verified_documents=1),
        )
        chunks = [
            Document(page_content="new indexed value", metadata={"chunk_id": "new-id"})
        ]
        return data_dir, persist_dir, load_result, chunks

    def test_embedding_failure_keeps_old_index_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            data_dir, persist_dir, load_result, chunks = self._build_inputs(root)
            self._store_with_old_record(persist_dir)

            with patch(
                "src.ingestion.build_vector_db.load_verified_documents",
                return_value=load_result,
            ), patch("src.ingestion.build_vector_db.split_documents", return_value=chunks), patch(
                "src.ingestion.build_vector_db.create_embeddings",
                side_effect=RuntimeError("embedding service unavailable"),
            ), self.assertRaisesRegex(RuntimeError, "embedding service unavailable"):
                build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    embedding_backend="ollama",
                    embedding_model="fixture-model",
                )

            self._assert_old_record_queryable(persist_dir)
            self.assertEqual(list(root.glob(".chroma_db.staging-*")), [])

    def test_successful_build_publishes_the_complete_new_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            data_dir, persist_dir, load_result, chunks = self._build_inputs(root)
            self._store_with_old_record(persist_dir)

            with patch(
                "src.ingestion.build_vector_db.load_verified_documents",
                return_value=load_result,
            ), patch("src.ingestion.build_vector_db.split_documents", return_value=chunks):
                stats = build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    collection_name="fixture",
                    embeddings=SmallEmbeddings(),
                )

            self.assertEqual(stats.collection_count, 1)
            store = Chroma(
                collection_name="fixture",
                persist_directory=str(persist_dir),
                embedding_function=SmallEmbeddings(),
            )
            try:
                records = store.get(include=["documents"])
                self.assertEqual(records["ids"], ["new-id"])
                self.assertEqual(records["documents"], ["new indexed value"])
            finally:
                close_chroma_store(store)
            self.assertEqual(list(root.glob(".chroma_db.staging-*")), [])

    def test_current_processed_corpus_builds_exact_ids_in_an_isolated_index(self) -> None:
        expected_chunks = split_documents(
            load_verified_documents(settings.processed_data_dir, target_year=2026).documents
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_dir = Path(temp_dir) / "isolated-chroma"
            stats = build_vector_db(
                data_directory=settings.processed_data_dir,
                persist_directory=persist_dir,
                collection_name="fixture",
                embeddings=SmallEmbeddings(),
                target_year=2026,
            )

            store = Chroma(
                collection_name="fixture",
                persist_directory=str(persist_dir),
                embedding_function=SmallEmbeddings(),
            )
            try:
                records = store.get(include=["metadatas"])
                expected_ids = {chunk.metadata["chunk_id"] for chunk in expected_chunks}
                self.assertEqual(set(records["ids"]), expected_ids)
                self.assertEqual(len(records["ids"]), len(expected_chunks))
                self.assertEqual(stats.collection_count, len(expected_chunks))
                self.assertEqual(
                    store._collection.metadata["corpus_fingerprint"],
                    stats.corpus_fingerprint,
                )
            finally:
                close_chroma_store(store)

    def test_repeated_build_replaces_edited_removed_and_retyped_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            data_dir, persist_dir, load_result, _ = self._build_inputs(root)
            old_chunks = [
                Document(
                    page_content="old edited content",
                    metadata={"chunk_id": "edited-old", "record_type": "page_text"},
                ),
                Document(
                    page_content="removed source content",
                    metadata={"chunk_id": "removed", "record_type": "page_text"},
                ),
                Document(
                    page_content="same content after retype",
                    metadata={"chunk_id": "retyped", "record_type": "page_text"},
                ),
            ]
            new_chunks = [
                Document(
                    page_content="corrected edited content",
                    metadata={"chunk_id": "edited-new", "record_type": "page_text"},
                ),
                Document(
                    page_content="same content after retype",
                    metadata={"chunk_id": "retyped", "record_type": "document_text"},
                ),
                Document(
                    page_content="new source content",
                    metadata={"chunk_id": "added", "record_type": "document_text"},
                ),
            ]

            with patch(
                "src.ingestion.build_vector_db.load_verified_documents",
                return_value=load_result,
            ), patch(
                "src.ingestion.build_vector_db.split_documents",
                side_effect=[old_chunks, new_chunks],
            ):
                first_stats = build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    collection_name="fixture",
                    embeddings=SmallEmbeddings(),
                )
                second_stats = build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    collection_name="fixture",
                    embeddings=SmallEmbeddings(),
                )

            store = Chroma(
                collection_name="fixture",
                persist_directory=str(persist_dir),
                embedding_function=SmallEmbeddings(),
            )
            try:
                records = store.get(include=["documents", "metadatas"])
                self.assertEqual(set(records["ids"]), {"edited-new", "retyped", "added"})
                self.assertEqual(len(records["ids"]), 3)
                by_id = dict(zip(records["ids"], zip(records["documents"], records["metadatas"])))
                self.assertEqual(by_id["edited-new"][0], "corrected edited content")
                self.assertEqual(by_id["retyped"][1]["record_type"], "document_text")
                self.assertNotIn("removed", records["ids"])
                self.assertEqual(
                    store._collection.metadata["corpus_fingerprint"],
                    second_stats.corpus_fingerprint,
                )
            finally:
                close_chroma_store(store)

            self.assertNotEqual(first_stats.corpus_fingerprint, second_stats.corpus_fingerprint)
            self.assertEqual(second_stats.collection_count, 3)
            self.assertEqual(second_stats.splitter_schema_version, SPLITTER_SCHEMA_VERSION)

    def test_build_persists_the_resolved_backend_model_and_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            data_dir, persist_dir, load_result, chunks = self._build_inputs(root)

            with patch(
                "src.ingestion.build_vector_db.load_verified_documents",
                return_value=load_result,
            ), patch("src.ingestion.build_vector_db.split_documents", return_value=chunks), patch(
                "src.ingestion.build_vector_db.create_embeddings",
                return_value=SmallEmbeddings(),
            ):
                stats = build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    collection_name="fixture",
                    embedding_backend="sentence-transformers",
                    embedding_model="audit/requested-model",
                )

            self.assertEqual(stats.embedding_backend, "sentence-transformers")
            self.assertEqual(stats.embedding_model, "audit/requested-model")
            self.assertEqual(stats.embedding_dimension, 3)
            self.assertEqual(len(stats.corpus_fingerprint), 64)
            store = Chroma(
                collection_name="fixture",
                persist_directory=str(persist_dir),
                embedding_function=SmallEmbeddings(),
            )
            try:
                metadata = store._collection.metadata
                self.assertEqual(metadata["embedding_backend"], "sentence-transformers")
                self.assertEqual(metadata["embedding_model"], "audit/requested-model")
                self.assertEqual(metadata["embedding_dimension"], 3)
                self.assertEqual(metadata["corpus_fingerprint"], stats.corpus_fingerprint)
                self.assertEqual(metadata["splitter_schema_version"], SPLITTER_SCHEMA_VERSION)
                self.assertEqual(metadata["chunk_size"], 512)
                self.assertEqual(metadata["chunk_overlap"], 50)
                self.assertEqual(metadata["tokenizer_model"], "BAAI/bge-m3")
                self.assertEqual(metadata["index_schema_version"], 2)
            finally:
                close_chroma_store(store)

    def test_add_documents_failure_keeps_old_index_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            data_dir, persist_dir, load_result, chunks = self._build_inputs(root)
            self._store_with_old_record(persist_dir)

            class FailedCandidateStore:
                def __init__(self, **_: object) -> None:
                    self._client = self
                    self.closed = False
                    self._collection = self

                def add_documents(self, *_: object, **__: object) -> None:
                    raise RuntimeError("candidate index write failed")

                def count(self) -> int:
                    return 0

                def close(self) -> None:
                    self.closed = True

            with patch(
                "src.ingestion.build_vector_db.load_verified_documents",
                return_value=load_result,
            ), patch("src.ingestion.build_vector_db.split_documents", return_value=chunks), patch(
                "src.ingestion.build_vector_db.Chroma", FailedCandidateStore
            ), self.assertRaisesRegex(RuntimeError, "candidate index write failed"):
                build_vector_db(
                    data_directory=data_dir,
                    persist_directory=persist_dir,
                    embeddings=SmallEmbeddings(),
                )

            self._assert_old_record_queryable(persist_dir)
            self.assertEqual(list(root.glob(".chroma_db.staging-*")), [])


if __name__ == "__main__":
    unittest.main()
