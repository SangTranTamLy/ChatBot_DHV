"""Regression coverage for the generated processed-layer migration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.config.settings import PROJECT_ROOT, settings
from src.ingestion.loader import load_verified_documents
from src.ingestion.structured_json import validate_structured_document


RAW_ROOT = PROJECT_ROOT / "data" / "raw"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"


class ProcessedJSONMigrationTests(unittest.TestCase):
    def test_canonical_processed_directory_contains_json_for_every_raw_pdf(self) -> None:
        raw_pdfs = sorted(RAW_ROOT.rglob("*.pdf"))
        json_files = sorted(PROCESSED_ROOT.rglob("*.json"))
        markdown_files = sorted(PROCESSED_ROOT.rglob("*.md"))

        self.assertEqual(settings.processed_data_dir, PROCESSED_ROOT)
        self.assertEqual(len(json_files), len(raw_pdfs))
        self.assertEqual(markdown_files, [])

    def test_all_canonical_json_documents_are_valid_utf8_and_verified(self) -> None:
        json_files = sorted(PROCESSED_ROOT.rglob("*.json"))
        self.assertTrue(json_files)
        for path in json_files:
            with self.subTest(path=path):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(validate_structured_document(document), [])
                self.assertEqual(document["year"], 2026)
                self.assertIs(document["source"]["verified"], True)

    def test_loader_reads_canonical_json_only(self) -> None:
        result = load_verified_documents(PROCESSED_ROOT)

        self.assertEqual(result.stats.files_seen, 15)
        self.assertEqual(result.stats.verified_documents, 15)
        self.assertEqual(result.stats.metadata_errors, 0)
        self.assertTrue(result.documents)
        self.assertTrue(all(document.metadata["source_file"].endswith(".pdf") for document in result.documents))


if __name__ == "__main__":
    unittest.main()
