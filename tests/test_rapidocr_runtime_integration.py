"""Real RapidOCR integration coverage for the RAW -> JSON pipeline."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from src.ingestion.pdf_layout import _rapidocr_engine
from src.ingestion.prepare_processed_from_raw import (
    _extract_pdf_pages,
    convert_pdf_to_structured_json,
)
from src.ingestion.structured_json import validate_structured_document


RAPIDOCR_AVAILABLE = importlib.util.find_spec("rapidocr_onnxruntime") is not None


def _write_scanned_fixture(path: Path) -> None:
    """Render a text page and save only its raster image in the fixture PDF."""

    source = fitz.open()
    source_page = source.new_page(width=1100, height=380)
    source_page.insert_text((100, 170), "DHV ADMISSIONS 2026", fontname="helv", fontsize=70)
    pixmap = source_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)

    scanned = fitz.open()
    scanned_page = scanned.new_page(width=1100, height=380)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    scanned.save(path)
    scanned.close()
    source.close()


@unittest.skipUnless(
    RAPIDOCR_AVAILABLE,
    "install rapidocr_onnxruntime to run scanned-PDF OCR integration checks",
)
class RapidOCRRuntimeIntegrationTests(unittest.TestCase):
    def test_rapidocr_runtime_initializes(self) -> None:
        self.assertIsNotNone(_rapidocr_engine())

    def test_scan_reaches_ocr_and_processed_json_uses_ocr_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(temp_dir)
            raw_root = fixture_root / "raw"
            raw_root.mkdir()
            raw_path = raw_root / "ocr_runtime_fixture.pdf"
            output_root = fixture_root / "processed"
            _write_scanned_fixture(raw_path)

            pages = _extract_pdf_pages(raw_path)

            self.assertEqual(pages[0]["extraction_method"], "ocr")
            self.assertNotIn("OCR_FAILED", json.dumps(pages, ensure_ascii=False))
            ocr_text = str(pages[0]["text"])
            self.assertIn("2026", ocr_text)
            self.assertGreater(len(ocr_text), 8)

            document = convert_pdf_to_structured_json(
                raw_path,
                raw_root=raw_root,
                output_root=output_root,
                manifest_entry={
                    "document_id": "ocr-runtime-fixture",
                    "title": "OCR runtime fixture",
                    "category": "fixtures",
                    "raw_file": "ocr_runtime_fixture.pdf",
                    "file_name": "ocr_runtime_fixture.pdf",
                    "year": 2026,
                    "source_url": "https://dhv.edu.vn/ocr-runtime-fixture",
                    "source_date": "2026",
                    "collected_at": "2026-09-23",
                    "status": "verified",
                    "verification_status": "verified",
                    "verified": True,
                },
            )
            structured = json.loads(document.output_path.read_text(encoding="utf-8"))

            self.assertEqual(validate_structured_document(structured), [])
            self.assertEqual(structured["pages"][0]["extraction_method"], "ocr")
            self.assertEqual(structured["pages"][0]["text"], ocr_text)
            self.assertEqual(structured["extraction"]["ocr_pages"], 1)
            self.assertNotIn("OCR_FAILED", json.dumps(structured, ensure_ascii=False))

if __name__ == "__main__":
    unittest.main()
