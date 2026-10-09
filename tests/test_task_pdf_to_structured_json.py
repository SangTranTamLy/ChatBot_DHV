"""Regression tests for the PDF -> structured JSON ingestion layer."""

from __future__ import annotations

import json
import re
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
    def test_page_model_retains_layout_tables_lists_and_ocr_fields(self) -> None:
        raw = RAW_ROOT / "phuong_thuc_xet_tuyen" / "PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(raw, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None)
            document = load_structured_json(result.output_path)

        self.assertEqual(document["extraction"]["page_count"], len(document["pages"]))
        self.assertTrue(all(page["page_number"] == page["page"] for page in document["pages"]))
        required_page_keys = {"text", "native_text", "ocr_text", "elements", "tables", "lists", "warnings"}
        self.assertTrue(all(required_page_keys <= set(page) for page in document["pages"]))
        tables = [table for page in document["pages"] for table in page["tables"]]
        self.assertTrue(tables)
        table = tables[0]
        self.assertTrue(table["headers"])
        self.assertTrue(table["rows"])
        self.assertTrue(all(row["cells"] for row in table["rows"]))
        self.assertTrue(any(page["lists"] for page in document["pages"]))
        self.assertTrue(all("bbox" in word and "text" in word for page in document["pages"] for word in page["native_words"]))
        self.assertEqual(validate_structured_document(document), [])

    def test_content_audit_counts_page_structures_and_keeps_import_data(self) -> None:
        raw = RAW_ROOT / "ho_so" / "HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(raw, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None)
            document = load_structured_json(result.output_path)

        audit = document["content_audit"]
        self.assertEqual(audit["pages"], len(document["pages"]))
        self.assertGreater(audit["final_chars"], 0)
        self.assertGreaterEqual(audit["final_chars"], audit["native_chars"])
        self.assertGreater(audit["records"], 0)
        full_text = "\n".join(page["text"] for page in document["pages"])
        for token in ("Hồ sơ", "nhập học", "học phí"):
            self.assertIn(token.casefold(), full_text.casefold())
        self.assertRegex(full_text.casefold(), r"giấy\s+tờ")
        self.assertEqual(validate_structured_document(document), [])

    def test_catalog_json_has_pages_records_and_parent_child_programs(self) -> None:
        raw = RAW_ROOT / "phuong_thuc_xet_tuyen" / "PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                raw,
                raw_root=RAW_ROOT,
                output_root=Path(temp_dir),
                markdown_root=None,
            )
            document = load_structured_json(result.output_path)

        self.assertEqual(document["extraction"]["method"], "native")
        self.assertEqual(document["extraction"]["page_count"], 10)
        self.assertEqual(len(document["pages"]), 10)
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
        self.assertEqual(len(majors), 20)
        self.assertEqual(cntt["fact_category"], "nganh_dao_tao")
        self.assertEqual(validate_structured_document(document), [])

    def test_score_types_are_separate_and_numeric_values_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            for category, name in (
                ("phuong_thuc_xet_tuyen", "PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf"),
                ("diem_trung_tuyen", "DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf"),
                ("xet_tuyen_bo_sung", "Ho_Xet_Tuyen_Bo_Sung_Dai_Hoc_Chinh_Quy_2026.pdf"),
            ):
                convert_pdf_to_structured_json(RAW_ROOT / category / name, raw_root=RAW_ROOT, output_root=output_root, markdown_root=None)
            threshold = load_structured_json(output_root / "phuong_thuc_xet_tuyen" / "PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.json")
            admission = load_structured_json(output_root / "diem_trung_tuyen" / "DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.json")
            supplementary = load_structured_json(output_root / "xet_tuyen_bo_sung" / "Ho_Xet_Tuyen_Bo_Sung_Dai_Hoc_Chinh_Quy_2026.json")

        threshold_records = [record for record in threshold["records"] if record.get("record_type") == "application_threshold"]
        self.assertTrue(threshold_records)
        self.assertTrue(all(record.get("score_type") == "application_threshold" for record in threshold_records))
        self.assertTrue(any(record["value"] == 600 for record in threshold_records))
        self.assertTrue(any(record["score_type"] == "admission_score" and record["value"] == 20.0 for record in admission["records"]))
        self.assertTrue(any(record.get("score_type") == "supplementary_threshold" and record.get("value") == 20 for record in supplementary["records"]))
        self.assertFalse(any("score" in record and record.get("record_type") in {"application_threshold", "admission_score", "supplementary_threshold"} for record in admission["records"]))

    def test_json_loader_builds_natural_record_chunks_and_flat_metadata(self) -> None:
        raw = RAW_ROOT / "ho_so" / "HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = convert_pdf_to_structured_json(raw, raw_root=RAW_ROOT, output_root=output_root, markdown_root=None)
            loaded = load_verified_documents(output_root)
            page_count = len(load_structured_json(result.output_path)["pages"])

        self.assertEqual(loaded.stats.verified_documents, 1)
        tuition_documents = [document for document in loaded.documents if document.metadata.get("record_type") == "tuition"]
        self.assertEqual(len(tuition_documents), 1)
        document = tuition_documents[0]
        self.assertIn("Học phí", document.page_content)
        self.assertNotIn('"record_type"', document.page_content)
        self.assertEqual(document.metadata["record_type"], "tuition")
        self.assertEqual(document.metadata["tuition_amount_vnd"], 12500000)
        self.assertEqual(document.metadata["tuition_per_credit_vnd"], 1250000)
        self.assertEqual(document.metadata["total_cost_vnd"], 14250000)
        self.assertEqual(document.metadata["page"], 1)
        self.assertTrue(document.metadata["source_file"].endswith("HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf"))

        page_text_documents = [
            item for item in loaded.documents
            if item.metadata.get("record_type") == "page_text"
        ]
        self.assertEqual(len(page_text_documents), page_count)
        self.assertTrue(all(item.metadata.get("page_text_source") is True for item in page_text_documents))

    def test_page_text_supplements_records_for_facts_not_structured_as_records(self) -> None:
        raw = RAW_ROOT / "phuong_thuc_xet_tuyen" / "PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                raw,
                raw_root=RAW_ROOT,
                output_root=Path(temp_dir),
                markdown_root=None,
            )
            loaded = load_verified_documents(Path(temp_dir))

        mos_chunks = [
            item for item in loaded.documents
            if item.metadata.get("record_type") == "page_text" and "MOS" in item.page_content
        ]
        self.assertTrue(mos_chunks)
        self.assertTrue(any("được cộng 1,50 điểm" in item.page_content for item in mos_chunks))

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
            "extraction": {"method": "native", "page_count": 1},
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
