"""Unit tests for the Task B ingestion and vector-store pipeline."""

from __future__ import annotations

import json
import tempfile
import unittest
import gc
from pathlib import Path
from unittest.mock import call, patch

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

from src.config.settings import settings
from src.ingestion.build_vector_db import _build_parser, build_vector_db, main
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.loader import load_verified_documents
from src.ingestion import splitter
from src.ingestion.splitter import split_documents


class KeywordEmbeddings(Embeddings):
    """Small deterministic embedding used only for offline pipeline tests."""

    terms = (
        "học phí dhv",
        "học phí",
        "học bổng",
        "hồ sơ",
        "lịch",
        "nhập học",
        "2026",
    )

    @classmethod
    def _embed(cls, text: str) -> list[float]:
        lowered = text.lower()
        return [float(term in lowered) for term in cls.terms]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _write_json(
    path: Path,
    *,
    status: str,
    category: str,
    title: str,
    year: int = 2026,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "document_id": path.stem,
        "title": title,
        "category": category,
        "year": year,
        "data_role": "",
        "source": {
            "file_name": f"{path.stem}.pdf",
            "raw_file": f"data/raw/{category}/{path.stem}.pdf",
            "source_url": "https://dhv.edu.vn/test-source",
            "source_urls": ["https://dhv.edu.vn/test-source"],
            "organization": "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh",
            "verified": status == "verified",
            "status": status,
            "verification_status": status,
            "source_sha256": "a" * 64,
        },
        "extraction": {"method": "test_fixture", "page_count": 1},
        "pages": [{"page": 1, "text": f"Thông tin {category} DHV {year}."}],
        "sections": [],
        "records": [
            {
                "record_type": "document_text",
                "record_id": f"{path.stem}_record",
                "text": f"Thông tin {category} DHV {year}.",
                "page": 1,
            }
        ],
        "warnings": [],
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


class IngestionTests(unittest.TestCase):
    def test_tokenizer_loader_falls_back_to_local_slow_variant(self) -> None:
        fallback_tokenizer = object()
        splitter._load_tokenizer.cache_clear()
        try:
            with patch(
                "transformers.AutoTokenizer.from_pretrained",
                side_effect=[MemoryError("fast tokenizer memory limit"), fallback_tokenizer],
            ) as from_pretrained:
                self.assertIs(
                    splitter._load_tokenizer("test-local-tokenizer"),
                    fallback_tokenizer,
                )
            self.assertEqual(
                from_pretrained.call_args_list,
                [
                    call(
                        "test-local-tokenizer",
                        local_files_only=True,
                        use_fast=True,
                    ),
                    call(
                        "test-local-tokenizer",
                        local_files_only=True,
                        use_fast=False,
                    ),
                ],
            )
        finally:
            splitter._load_tokenizer.cache_clear()

    def test_loader_preserves_metadata_and_filters_unverified_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / "hoc_phi" / "verified.json",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2026",
            )
            _write_json(
                root / "hoc_bong" / "draft.json",
                status="draft",
                category="hoc_bong",
                title="Học bổng bản nháp",
            )
            _write_json(
                root / "hoc_phi" / "old.json",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2025",
                year=2025,
            )
            (root / "broken.json").write_text("{broken", encoding="utf-8")

            result = load_verified_documents(root)

            self.assertEqual(result.stats.files_seen, 4)
            self.assertEqual(result.stats.verified_documents, 1)
            self.assertEqual(result.stats.skipped_unverified, 1)
            self.assertEqual(result.stats.skipped_other_year, 1)
            self.assertEqual(result.stats.metadata_errors, 1)
            self.assertEqual(result.documents[0].metadata["category"], "hoc_phi")
            self.assertEqual(result.documents[0].metadata["year"], 2026)
            self.assertEqual(
                result.documents[0].metadata["source_url"],
                "https://dhv.edu.vn/test-source",
            )
            self.assertEqual(result.documents[0].metadata["source_sha256"], "a" * 64)

    def test_loader_all_years_still_excludes_unverified_documents(self) -> None:
        root = Path("fixture-processed")
        files = [
            root / "verified_2024.json",
            root / "verified_2026.json",
            root / "draft_2025.json",
        ]
        envelopes = {
            files[0]: {"year": 2024, "source": {"status": "verified", "verified": True}},
            files[1]: {"year": 2026, "source": {"status": "verified", "verified": True}},
            files[2]: {"year": 2025, "source": {"status": "draft", "verified": False}},
        }

        def read_envelope(path: Path, *args: object, **kwargs: object) -> str:
            return json.dumps(envelopes[path])

        def make_document(path: Path) -> list[Document]:
            return [
                Document(
                    page_content=f"Verified DHV fixture {envelopes[path]['year']}",
                    metadata={"year": envelopes[path]["year"]},
                )
            ]

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("pathlib.Path.rglob", return_value=files),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_text", autospec=True, side_effect=read_envelope),
            patch("src.ingestion.loader.load_structured_json_file", side_effect=make_document),
        ):
            result = load_verified_documents(root, target_year=None)

        self.assertEqual(result.stats.files_seen, 3)
        self.assertEqual(result.stats.verified_documents, 2)
        self.assertEqual(result.stats.skipped_unverified, 1)
        self.assertEqual(
            {document.metadata["year"] for document in result.documents},
            {2024, 2026},
        )

    def test_build_cli_defaults_to_configured_year(self) -> None:
        with patch("src.ingestion.build_vector_db.build_vector_db") as build_mock:
            build_mock.return_value.as_dict.return_value = {"ok": True}
            with patch("sys.argv", ["build_vector_db"]):
                self.assertEqual(main(), 0)

        self.assertEqual(build_mock.call_args.kwargs["target_year"], settings.target_year)

    def test_build_cli_all_years_passes_no_year_filter(self) -> None:
        with patch("src.ingestion.build_vector_db.build_vector_db") as build_mock:
            build_mock.return_value.as_dict.return_value = {"ok": True}
            with patch("sys.argv", ["build_vector_db", "--all-years"]):
                self.assertEqual(main(), 0)

        self.assertIsNone(build_mock.call_args.kwargs["target_year"])

    def test_build_cli_explicit_year_is_preserved(self) -> None:
        with patch("src.ingestion.build_vector_db.build_vector_db") as build_mock:
            build_mock.return_value.as_dict.return_value = {"ok": True}
            with patch("sys.argv", ["build_vector_db", "--year", "2024"]):
                self.assertEqual(main(), 0)

        self.assertEqual(build_mock.call_args.kwargs["target_year"], 2024)

    def test_build_cli_year_and_all_years_are_mutually_exclusive(self) -> None:
        parser = _build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["--year", "2024", "--all-years"])

    def test_build_cli_help_is_windows_console_encodable(self) -> None:
        help_text = _build_parser().format_help()

        self.assertIn("--all-years", help_text)
        help_text.encode("cp1252")

    def test_splitter_keeps_heading_sections_separate_and_ids_unique(self) -> None:
        document = Document(
            page_content=(
                "# Dữ liệu DHV 2026\n\n"
                "## Học phí\n\nHọc phí là 1.250.000 đồng mỗi tín chỉ.\n\n"
                "## Học bổng\n\nHọc bổng hỗ trợ theo kết quả học tập."
            ),
            metadata={
                "title": "Tổng hợp DHV 2026",
                "category": "tong_hop",
                "year": 2026,
                "source_url": "https://example.test/source",
                "source_file": "example.json",
                "status": "verified",
            },
        )

        chunks = split_documents([document], chunk_size=200, chunk_overlap=20)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(len({chunk.metadata["chunk_id"] for chunk in chunks}), len(chunks))
        heading_paths = {chunk.metadata["heading_path"] for chunk in chunks}
        self.assertTrue(any("Học phí" in path for path in heading_paths))
        self.assertTrue(any("Học bổng" in path for path in heading_paths))
        for chunk in chunks:
            self.assertFalse("Học phí là" in chunk.page_content and "Học bổng hỗ trợ" in chunk.page_content)

    def test_build_persists_chroma_and_smoke_query_keeps_source_metadata(self) -> None:
        embeddings = KeywordEmbeddings()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data" / "processed"
            persist_dir = root / "chroma_db"
            _write_json(
                data_dir / "hoc_phi" / "hoc_phi.json",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2026",
            )
            _write_json(
                data_dir / "hoc_bong" / "hoc_bong.json",
                status="verified",
                category="hoc_bong",
                title="Học bổng DHV 2026",
            )

            stats = build_vector_db(
                data_directory=data_dir,
                persist_directory=persist_dir,
                collection_name="test_dhv",
                embeddings=embeddings,
                chunk_size=300,
                chunk_overlap=20,
                reset=True,
            )

            self.assertEqual(stats.files_seen, 2)
            self.assertEqual(stats.verified_documents, 2)
            self.assertGreaterEqual(stats.chunks_indexed, 2)
            self.assertTrue(persist_dir.exists())

            vector_store = Chroma(
                collection_name="test_dhv",
                persist_directory=str(persist_dir),
                embedding_function=embeddings,
            )
            try:
                results = vector_store.similarity_search("Học phí DHV 2026", k=1)

                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].metadata["category"], "hoc_phi")
                self.assertEqual(results[0].metadata["year"], 2026)
                self.assertEqual(
                    results[0].metadata["source_url"],
                    "https://dhv.edu.vn/test-source",
                )
            finally:
                close_chroma_store(vector_store)
                del vector_store
                gc.collect()

    def test_current_processed_corpus_smoke_query(self) -> None:
        """The required smoke query works against the current processed corpus."""

        embeddings = KeywordEmbeddings()
        project_root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (project_root / "data" / "raw" / "manifest.json").read_text(encoding="utf-8")
        )
        expected_verified = sum(
            1
            for entry in manifest["documents"]
            if entry["year"] == manifest["target_year"] and entry["verified"] is True
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_dir = Path(temp_dir) / "chroma_db"
            stats = build_vector_db(
                data_directory=project_root / "data" / "processed",
                persist_directory=persist_dir,
                collection_name="test_dhv_current",
                embeddings=embeddings,
                reset=True,
            )

            self.assertEqual(stats.files_seen, len(manifest["documents"]))
            self.assertEqual(stats.verified_documents, expected_verified)
            self.assertGreater(stats.chunks_indexed, 0)
            vector_store = Chroma(
                collection_name="test_dhv_current",
                persist_directory=str(persist_dir),
                embedding_function=embeddings,
            )
            try:
                results = vector_store.similarity_search(
                    "Học phí DHV 2026",
                    k=stats.chunks_indexed,
                )
                tuition_results = [
                    result
                    for result in results
                    if result.metadata.get("category") == "hoc_phi"
                ]

                self.assertTrue(tuition_results)
                self.assertEqual(tuition_results[0].metadata["year"], 2026)
                self.assertTrue(tuition_results[0].metadata["source_url"])
            finally:
                close_chroma_store(vector_store)
                del vector_store
                gc.collect()


if __name__ == "__main__":
    unittest.main()
