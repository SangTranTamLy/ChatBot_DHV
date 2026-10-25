"""Regression coverage for the recovered RAW -> JSON -> Chroma data path."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.prepare_processed_from_raw import _extract_pdf_pages, _normalize_extracted_text
from src.ingestion.raw_manifest import load_raw_manifest, validate_manifest_sync
from src.ingestion.structured_json import (
    build_chunk_documents,
    build_structured_document,
    validate_structured_document,
)
from src.ingestion.loader import load_verified_documents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"


def _manifest_entry(document_id: str) -> dict[str, object]:
    manifest = load_raw_manifest(RAW_ROOT / "manifest.json")
    return next(
        entry
        for entry in manifest["documents"]
        if entry.get("document_id") == document_id
    )


def _historical_tuition_entry() -> dict[str, object]:
    """A verified 2024 entry shaped like the reviewed 2026 tuition manifest row.

    The repository no longer ships 2024 sources, but the year-isolation policy
    still applies whenever historical PDFs are added back. The 2026 PDF stands
    in for the raw bytes because only the year metadata matters here.
    """
    entry = dict(_manifest_entry("hoc-phi-va-khoan-thu-nhap-hoc-dhv-2026"))
    entry.update({"document_id": "hoc-phi-dhv-2024", "title": "Học phí DHV 2024", "year": 2024})
    return entry


class _FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class DataPipelineRecoveryTests(unittest.TestCase):
    def test_manifest_data_role_is_preserved_in_processed_and_index_chunks(self) -> None:
        entry = _manifest_entry("thu-tuc-va-quyen-loi-nhap-hoc-dhv-2026")
        document = build_structured_document(
            raw_path=PROJECT_ROOT / str(entry["raw_file"]),
            raw_root=RAW_ROOT,
            pages=[{
                "page": 1,
                "text": (
                    "Quyền lợi và quà tặng sau nhập học.\n"
                    "Sau khi hoàn tất nhập học, tân sinh viên được cấp mã số sinh viên."
                ),
            }],
            manifest_entry=entry,
        )

        self.assertEqual(document["data_role"], entry["data_role"])
        chunks = build_chunk_documents(document)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.metadata["data_role"] == entry["data_role"] for chunk in chunks))

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

    def test_manifest_provenance_preserves_verified_2024_source_url(self) -> None:
        entry = _historical_tuition_entry()
        document = build_structured_document(
            raw_path=PROJECT_ROOT / str(entry["raw_file"]),
            raw_root=RAW_ROOT,
            pages=[{"page": 1, "text": "Học phí 1.100.000 VNĐ một tín chỉ."}],
            manifest_entry=entry,
        )

        self.assertEqual(document["year"], 2024)
        self.assertEqual(document["source"]["source_url"], entry["source_url"])
        self.assertTrue(document["source"]["verified"])
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

    def test_verified_2024_tuition_loads_only_for_2024_target_year(self) -> None:
        entries = {
            2024: _historical_tuition_entry(),
            2026: _manifest_entry("hoc-phi-va-khoan-thu-nhap-hoc-dhv-2026"),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            processed_root = Path(temp_dir)
            for year, entry in entries.items():
                document = build_structured_document(
                    raw_path=PROJECT_ROOT / str(entry["raw_file"]),
                    raw_root=RAW_ROOT,
                    pages=[{"page": 1, "text": f"Học phí năm {year} được tính theo tín chỉ."}],
                    manifest_entry=entry,
                )
                self.assertEqual(validate_structured_document(document), [])
                target = processed_root / "hoc_phi" / f"hoc_phi_{year}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

            historical = load_verified_documents(processed_root, target_year=2024)
            current = load_verified_documents(processed_root, target_year=2026)

        self.assertEqual(historical.stats.verified_documents, 1)
        self.assertTrue(historical.documents)
        self.assertTrue(all(document.metadata["year"] == 2024 for document in historical.documents))
        self.assertEqual(current.stats.verified_documents, 1)
        self.assertTrue(current.documents)
        self.assertTrue(all(document.metadata["year"] == 2026 for document in current.documents))


if __name__ == "__main__":
    unittest.main()
