"""Regression tests for the PDF -> structured JSON ingestion layer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.ingestion.loader import load_verified_documents
from src.ingestion.prepare_processed_from_raw import convert_pdf_to_structured_json
from src.ingestion.structured_json import (
    StructuredJSONValidationError,
    build_chunk_documents,
    load_structured_json,
    validate_structured_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"


class StructuredJSONPipelineTests(unittest.TestCase):
    def test_catalog_json_has_pages_records_and_parent_child_programs(self) -> None:
        raw = RAW_ROOT / "nganh_dao_tao" / "danh_muc_nganh_chuong_trinh_va_diem_san_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                raw,
                raw_root=RAW_ROOT,
                output_root=Path(temp_dir),
                markdown_root=None,
            )
            document = load_structured_json(result.output_path)

        self.assertEqual(document["extraction"]["method"], "pypdf_text")
        self.assertEqual(document["extraction"]["page_count"], 2)
        self.assertEqual(len(document["pages"]), 2)
        majors = {
            record["major_name"]: record
            for record in document["records"]
            if record.get("record_type") == "major"
        }
        cntt = majors["Công nghệ thông tin"]
        self.assertEqual(cntt["major_code"], "7480201")
        self.assertEqual(cntt["program_count"], 5)
        self.assertEqual(
            [program["program_name"] for program in cntt["programs"]],
            [
                "Công nghệ phần mềm",
                "Lập trình AI",
                "An ninh mạng và hệ thống",
                "Truyền thông đa phương tiện",
                "Phân tích dữ liệu lớn",
            ],
        )
        self.assertTrue(all(program["parent_major"] == "Công nghệ thông tin" for program in cntt["programs"]))
        self.assertEqual(cntt["thresholds"], {"thpt": 15, "hoc_ba": 18, "dgnl": 600})
        self.assertEqual(validate_structured_document(document), [])

    def test_score_types_are_separate_and_numeric_values_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            for category, name in (("nguong_dau_vao", "diem_san_2026.pdf"), ("diem_trung_tuyen", "diem_trung_tuyen_dot_1_2026.pdf"), ("xet_tuyen_bo_sung", "xet_tuyen_bo_sung_2026.pdf")):
                convert_pdf_to_structured_json(
                    RAW_ROOT / category / name,
                    raw_root=RAW_ROOT,
                    output_root=output_root,
                    markdown_root=None,
                )
            threshold = load_structured_json(output_root / "nguong_dau_vao" / "diem_san_2026.json")
            admission = load_structured_json(output_root / "diem_trung_tuyen" / "diem_trung_tuyen_dot_1_2026.json")
            supplementary = load_structured_json(output_root / "xet_tuyen_bo_sung" / "xet_tuyen_bo_sung_2026.json")

        self.assertTrue(all(record.get("score_type") == "application_threshold" for record in threshold["records"]))
        self.assertTrue(any(record["value"] == 600 for record in threshold["records"]))
        self.assertTrue(any(record["score_type"] == "admission_score" and record["value"] == 20.0 for record in admission["records"]))
        self.assertTrue(any(record.get("score_type") == "supplementary_threshold" and record.get("value") == 20 for record in supplementary["records"]))
        self.assertFalse(any("score" in record and record.get("record_type") in {"application_threshold", "admission_score", "supplementary_threshold"} for record in admission["records"]))

    def test_json_loader_builds_natural_record_chunks_and_flat_metadata(self) -> None:
        raw = RAW_ROOT / "hoc_phi" / "hoc_phi_hoc_ky_1_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = convert_pdf_to_structured_json(raw, raw_root=RAW_ROOT, output_root=output_root, markdown_root=None)
            loaded = load_verified_documents(output_root)

        self.assertEqual(loaded.stats.verified_documents, 1)
        self.assertEqual(len(loaded.documents), 1)
        document = loaded.documents[0]
        self.assertIn("Học phí", document.page_content)
        self.assertNotIn('"record_type"', document.page_content)
        self.assertEqual(document.metadata["record_type"], "tuition")
        self.assertEqual(document.metadata["tuition_amount_vnd"], 12500000)
        self.assertEqual(document.metadata["total_cost_vnd"], 14500000)
        self.assertEqual(document.metadata["page"], 1)
        self.assertTrue(document.metadata["source_file"].endswith("hoc_phi_hoc_ky_1_2026.pdf"))

    def test_validation_rejects_unofficial_sources_and_missing_traceability(self) -> None:
        invalid = {
            "document_id": "invalid",
            "title": "Invalid",
            "category": "hoc_phi",
            "year": 2026,
            "source": {
                "file_name": "invalid.pdf",
                "source_url": "https://example.test/source",
                "source_urls": ["https://example.test/source"],
                "organization": "DHV",
                "verified": True,
                "status": "verified",
                "verification_status": "verified",
            },
            "extraction": {"method": "pypdf_text", "page_count": 1},
            "pages": [{"page": 1, "text": "text"}],
            "sections": [],
            "records": [{"record_type": "tuition", "record_id": "t1"}],
            "warnings": [],
        }
        errors = validate_structured_document(invalid)
        self.assertTrue(any("official DHV" in error["message"] for error in errors))
        self.assertTrue(any("traceability" in error["message"] for error in errors))
        with self.assertRaises(StructuredJSONValidationError):
            build_chunk_documents(invalid)


if __name__ == "__main__":
    unittest.main()
