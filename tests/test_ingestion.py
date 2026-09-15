"""Unit tests for the Task B ingestion and vector-store pipeline."""

from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

from src.ingestion.build_vector_db import build_vector_db
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.loader import load_verified_documents
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


def _write_markdown(
    path: Path,
    *,
    status: str,
    category: str,
    title: str,
    year: int = 2026,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f'title: "{title}"',
                f'category: "{category}"',
                f"year: {year}",
                'source_url: "https://example.test/source"',
                'source_date: "2026-09-14"',
                f'status: "{status}"',
                "---",
                "",
                f"# {title}",
                "",
                f"Thông tin {category} DHV 2026.",
            ]
        ),
        encoding="utf-8",
    )


class IngestionTests(unittest.TestCase):
    def test_loader_preserves_metadata_and_filters_unverified_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_markdown(
                root / "hoc_phi" / "verified.md",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2026",
            )
            _write_markdown(
                root / "hoc_bong" / "draft.md",
                status="draft",
                category="hoc_bong",
                title="Học bổng bản nháp",
            )
            _write_markdown(
                root / "hoc_phi" / "old.md",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2025",
                year=2025,
            )
            (root / "broken.md").write_text("không có front matter", encoding="utf-8")

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
                "https://example.test/source",
            )

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
                "source_file": "example.md",
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
            _write_markdown(
                data_dir / "hoc_phi" / "hoc_phi.md",
                status="verified",
                category="hoc_phi",
                title="Học phí DHV 2026",
            )
            _write_markdown(
                data_dir / "hoc_bong" / "hoc_bong.md",
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
                    "https://example.test/source",
                )
            finally:
                close_chroma_store(vector_store)
                del vector_store
                gc.collect()

    def test_current_processed_corpus_smoke_query(self) -> None:
        """The required smoke query works against the current processed corpus."""

        embeddings = KeywordEmbeddings()
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_dir = Path(temp_dir) / "chroma_db"
            stats = build_vector_db(
                data_directory=project_root / "data" / "processed",
                persist_directory=persist_dir,
                collection_name="test_dhv_current",
                embeddings=embeddings,
                reset=True,
            )

            self.assertEqual(stats.verified_documents, 15)
            self.assertGreaterEqual(stats.chunks_indexed, 18)
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
