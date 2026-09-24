"""Regression coverage for the recovered RAW -> JSON -> Chroma data path."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.prepare_processed_from_raw import _extract_pdf_pages, _normalize_extracted_text
from src.ingestion.raw_manifest import load_raw_manifest, validate_manifest_sync
from src.ingestion.structured_json import build_structured_document, validate_structured_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"


class _FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class DataPipelineRecoveryTests(unittest.TestCase):
    def test_manifest_covers_current_raw_files_exactly_once(self) -> None:
        manifest = load_raw_manifest(RAW_ROOT / "manifest.json")
        self.assertEqual(validate_manifest_sync(manifest, raw_root=RAW_ROOT), [])
        self.assertEqual(len(manifest["documents"]), len(list(RAW_ROOT.rglob("*.pdf"))))

    def test_ocr_fallback_is_called_and_marks_page(self) -> None:
        with patch(
            "src.ingestion.prepare_processed_from_raw.PdfReader",
            return_value=_FakeReader([_FakePage("")]),
        ), patch(
            "src.ingestion.prepare_processed_from_raw._ocr_page",
            return_value="OCR text có đủ nội dung để lập chỉ mục.",
        ) as ocr:
            pages = _extract_pdf_pages(Path("fixture.pdf"))

        ocr.assert_called_once_with(Path("fixture.pdf"), 0)
        self.assertEqual(pages[0]["extraction_method"], "ocr")
        self.assertEqual(pages[0]["text"], "OCR text có đủ nội dung để lập chỉ mục.")

    def test_manifest_provenance_survives_pdf_without_url(self) -> None:
        document = build_structured_document(
            raw_path=RAW_ROOT / "hoc_phi" / "Hoc_Phi_DHV_2024.pdf",
            raw_root=RAW_ROOT,
            pages=[{"page": 1, "text": "Học phí 1.100.000 VNĐ một tín chỉ."}],
            manifest_entry={
                "document_id": "hoc-phi-2024-fixture",
                "title": "Học phí DHV 2024",
                "category": "hoc_phi",
                "raw_file": "data/raw/hoc_phi/Hoc_Phi_DHV_2024.pdf",
                "year": 2024,
                "status": "missing_source_url",
                "verification_status": "missing_source_url",
                "verified": False,
            },
        )

        self.assertEqual(document["year"], 2024)
        self.assertIsNone(document["source"]["source_url"])
        self.assertEqual(validate_structured_document(document), [])

    def test_normalization_preserves_numbers_dates_money_urls_and_vietnamese(self) -> None:
        value = _normalize_extracted_text(
            "7480201\u00ad\n 7220201 2026 21/08/2026 12.500.000 1.250.000 "
            "0287 1000 888 https://dhv.edu.vn/ Trường"
        )
        for token in (
            "7480201",
            "7220201",
            "2026",
            "21/08/2026",
            "12.500.000",
            "1.250.000",
            "0287 1000 888",
            "https://dhv.edu.vn/",
            "Trường",
        ):
            self.assertIn(token, value)

    def test_processed_corpus_keeps_2024_and_loader_source_is_not_verified(self) -> None:
        processed = json.loads(
            (PROJECT_ROOT / "data" / "processed" / "hoc_phi" / "Hoc_Phi_DHV_2024.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(processed["year"], 2024)
        self.assertEqual(processed["source"]["status"], "missing_source_url")
        self.assertFalse(processed["source"]["verified"])


if __name__ == "__main__":
    unittest.main()
