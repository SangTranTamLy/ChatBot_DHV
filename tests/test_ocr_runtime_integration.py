"""Real Tesseract OCR integration coverage for the RAW -> JSON pipeline."""

from __future__ import annotations

import io
import json
import os
import unittest
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from src.ingestion.prepare_processed_from_raw import (
    _extract_pdf_pages,
    convert_pdf_to_structured_json,
)
from src.ingestion.structured_json import validate_structured_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PDF = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "diem_trung_tuyen"
    / "DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf"
)


def _tesseract_is_ready() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return "vie" in pytesseract.get_languages(config="")
    except Exception:
        return False


def _font_path() -> Path:
    windows_root = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for candidate in (
        windows_root / "Fonts" / "arial.ttf",
        windows_root / "Fonts" / "tahoma.ttf",
        windows_root / "Fonts" / "segoeui.ttf",
    ):
        if candidate.exists():
            return candidate
    raise unittest.SkipTest("a Unicode system font is required for the OCR fixture")


def _write_scanned_fixture(path: Path) -> None:
    image = Image.new("RGB", (2200, 760), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(_font_path()), 86)
    draw.multiline_text(
        (100, 100),
        "Trường Đại học Hùng Vương TP. Hồ Chí Minh\nTuyển sinh năm 2026",
        font=font,
        fill="black",
        spacing=35,
    )
    png = io.BytesIO()
    image.save(png, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page(width=1100, height=380)
    page.insert_image(page.rect, stream=png.getvalue())
    pdf.save(path)
    pdf.close()


@unittest.skipUnless(
    _tesseract_is_ready(),
    "real Tesseract executable with Vietnamese traineddata is required",
)
class OCRRuntimeIntegrationTests(unittest.TestCase):
    def test_tesseract_runtime_and_vietnamese_language_are_real(self) -> None:
        version = str(pytesseract.get_tesseract_version())
        languages = pytesseract.get_languages(config="")

        self.assertTrue(version.strip())
        self.assertIn("vie", languages)

    def test_scan_reaches_ocr_and_processed_json_uses_ocr_text(self) -> None:
        raw_root = PROJECT_ROOT / "tests" / "fixtures"
        raw_path = raw_root / ".ocr_runtime_fixture.pdf"
        output_root = PROJECT_ROOT / "tests"
        output_path = output_root / "fixtures" / ".ocr_runtime_fixture.json"
        try:
            _write_scanned_fixture(raw_path)

            pages = _extract_pdf_pages(raw_path)

            self.assertEqual(pages[0]["extraction_method"], "ocr")
            self.assertNotIn("OCR_FAILED", json.dumps(pages, ensure_ascii=False))
            ocr_text = str(pages[0]["text"])
            self.assertIn("2026", ocr_text)
            self.assertIn("trường", ocr_text.casefold())
            self.assertGreater(len(ocr_text), 20)

            document = convert_pdf_to_structured_json(
                raw_path,
                raw_root=raw_root,
                output_root=output_root,
                manifest_entry={
                    "document_id": "ocr-runtime-fixture",
                    "title": "OCR runtime fixture",
                    "category": "fixtures",
                    "raw_file": "tests/fixtures/ocr_runtime_fixture.pdf",
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
        finally:
            raw_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def test_previous_production_page_is_blank_not_an_ocr_runtime_failure(self) -> None:
        self.assertTrue(PRODUCTION_PDF.exists())

        page = _extract_pdf_pages(PRODUCTION_PDF)[7]

        self.assertEqual(page["page"], 8)
        self.assertEqual(page["text"], "")
        self.assertNotEqual(page.get("warnings", [{}])[0].get("type"), "OCR_FAILED")
        self.assertEqual(page["warnings"][0]["type"], "OCR_EMPTY_OR_LOW_QUALITY")


if __name__ == "__main__":
    unittest.main()
