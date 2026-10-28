"""Regression tests for the PDF -> structured JSON ingestion layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.loader import load_verified_documents
from src.ingestion.pdf_layout import (
    _clean_text,
    _coordinate_table_from_tokens,
    _merge_list_continuations,
    _merge_text,
    _ocr_page_layout,
    _pytesseract_tokens,
    _supplemental_ocr_lines,
    extract_pdf_pages,
)
from src.ingestion.prepare_processed_from_raw import (
    _extract_pdf_pages,
    _inherit_continued_table_headers,
    convert_pdf_to_structured_json,
)
from src.ingestion.structured_json import (
    StructuredJSONValidationError,
    build_chunk_documents,
    build_structured_document,
    load_structured_json,
    parse_admission_methods,
    parse_enrollment_documents,
    parse_major_catalog,
    validate_structured_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
# Official 2026 source PDFs (flat layout; the category comes from manifest.json).
ADMISSION_SCORES_PDF = RAW_ROOT / "01_DIEM_TRUNG_TUYEN_DOT_1_DHV_2026.pdf"
MAJOR_CATALOG_PDF = RAW_ROOT / "02_NGANH_VA_CHUONG_TRINH_DAO_TAO_DHV_2026.pdf"
ADMISSION_METHODS_PDF = RAW_ROOT / "03_DIEU_KIEN_VA_PHUONG_THUC_XET_TUYEN_DHV_2026.pdf"
SUPPLEMENTARY_PDF = RAW_ROOT / "05_XET_TUYEN_BO_SUNG_DHV_2026.pdf"
ENROLLMENT_DOCUMENTS_PDF = RAW_ROOT / "06_HO_SO_CAN_CHUAN_BI_KHI_NHAP_HOC_DHV_2026.pdf"
ENROLLMENT_PROCEDURE_PDF = RAW_ROOT / "07_THU_TUC_VA_QUYEN_LOI_NHAP_HOC_DHV_2026.pdf"
TUITION_PDF = RAW_ROOT / "08_HOC_PHI_VA_KHOAN_THU_NHAP_HOC_DHV_2026.pdf"
SCHOLARSHIP_PDF = RAW_ROOT / "09_CHINH_SACH_HOC_BONG_DHV_2026.pdf"


def _non_empty(values: list[str]) -> list[str]:
    return [value for value in values if str(value).strip()]


class StructuredJSONPipelineTests(unittest.TestCase):
    @staticmethod
    def _synthetic_table_ocr_tokens(
        *,
        confidence: float | None = 0.95,
        conflicting_first_row: bool = False,
    ) -> list[dict[str, object]]:
        rows = [
            (("Mã ngành 7480201", "Điểm chuẩn 18" if conflicting_first_row else "Điểm chuẩn 15"), 170),
            (("7340101", "18"), 195),
            (("7220201", "20"), 220),
        ]
        tokens: list[dict[str, object]] = []
        for (left, right), y in rows:
            for text, x0, x1 in ((left, 50, 150), (right, 200, 290)):
                token: dict[str, object] = {
                    "text": text,
                    "bbox": [x0, y, x1, y + 10],
                    "source": "rapidocr",
                }
                if confidence is not None:
                    token["confidence"] = confidence
                tokens.append(token)
        return tokens

    def test_merged_major_catalog_table_keeps_all_twenty_major_code_pairs(self) -> None:
        expected = (
            ("Quản trị kinh doanh", "7340101"),
            ("Kinh tế quốc tế", "7310106"),
            ("Marketing", "7340115"),
            ("Thương mại điện tử", "7340122"),
            ("Tài chính ngân hàng", "7340201"),
            ("Kế toán", "7340301"),
            ("Công nghệ tài chính", "7340205"),
            ("Kỹ thuật máy tính", "7480106"),
            ("Công nghệ thông tin", "7480201"),
            ("Trí tuệ nhân tạo", "7480107"),
            ("Ngôn ngữ Anh", "7220201"),
            ("Ngôn ngữ Nhật", "7220209"),
            ("Ngôn ngữ Trung Quốc", "7220204"),
            ("Ngôn ngữ Hàn Quốc", "7220210"),
            ("Quản trị Khách sạn", "7810201"),
            ("Quản trị Dịch vụ Du lịch & Lữ hành", "7810103"),
            ("Luật", "7380101"),
            ("Luật Kinh tế", "7380107"),
            ("Quản lý bệnh viện", "7720802"),
            ("Tâm lý học", "7310401"),
        )
        headers = ["", "TÊN NGÀNH", "", "", "CHƯƠNG TRÌNH ĐÀO TẠO", "", "", "MÃ NGÀNH"]
        rows = []
        for index, (major_name, _code) in enumerate(expected):
            values = ["", "", "", "", "", "", "", ""]
            values[0 if index % 2 == 0 else 1] = major_name
            rows.append({"row_index": index + 1, "values": values})
        page = {
            "page": 1,
            "page_number": 1,
            "text": "DHV đào tạo 20 ngành học với hơn 50 chương trình\n"
            + "\n".join(code for _, code in expected),
            "tables": [{"headers": headers, "rows": rows}],
        }

        records = parse_major_catalog([page], include_thresholds=False)
        majors = [record for record in records if record["record_type"] == "major"]
        summary = next(record for record in records if record["record_type"] == "major_catalog_summary")

        self.assertEqual([(record["major_name"], record["major_code"]) for record in majors], list(expected))
        self.assertEqual(summary["major_count"], 20)

    def test_partial_major_table_is_not_summarized_as_complete(self) -> None:
        page = {
            "page": 1,
            "page_number": 1,
            "text": "DHV đào tạo 20 ngành học với hơn 50 chương trình\n7310106\n7480107",
            "tables": [
                {
                    "headers": ["", "TÊN NGÀNH", "", "", "CHƯƠNG TRÌNH ĐÀO TẠO", "", "", "MÃ NGÀNH"],
                    "rows": [
                        {"row_index": 1, "values": ["Kinh tế quốc tế", "", "", "", "", "", "", ""]},
                        {"row_index": 2, "values": ["Trí tuệ nhân tạo", "", "", "", "", "", "", ""]},
                    ],
                }
            ],
        }

        self.assertEqual(parse_major_catalog([page], include_thresholds=False), [])

    def test_url_hyphen_line_wrap_is_repaired_without_changing_prose(self) -> None:
        text = _clean_text("URL: https://example.edu/file/name- value; tuyển sinh - đợt 2")

        self.assertIn("https://example.edu/file/name-value", text)
        self.assertIn("tuyển sinh - đợt 2", text)

    def test_current_enrollment_pdf_records_only_required_documents_and_methods(self) -> None:
        enrollment_pages = _extract_pdf_pages(ENROLLMENT_DOCUMENTS_PDF)
        documents = parse_enrollment_documents(enrollment_pages)
        document_names = [record["document_name"] for record in documents]
        self.assertEqual(
            document_names,
            [
                "Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học.",
                "Học bạ THPT.",
                "Căn cước/Căn cước công dân.",
                "Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026.",
            ],
        )
        # Campus bullets in the procedure PDF are locations, not documents.
        procedure_pages = _extract_pdf_pages(ENROLLMENT_PROCEDURE_PDF)
        self.assertEqual(parse_enrollment_documents(procedure_pages), [])

        method_pages = _extract_pdf_pages(ADMISSION_METHODS_PDF)
        methods = parse_admission_methods(method_pages)
        self.assertEqual([record["method"] for record in methods], ["thpt", "hoc_ba", "dgnl", "h_sca", "trung_cap"])

        numbered_sections = [
            element
            for element in procedure_pages[0]["elements"]
            if element.get("type") == "heading" and "THÍ SINH TRÚNG TUYỂN" in str(element.get("text", ""))
        ]
        self.assertTrue(numbered_sections)
        self.assertFalse(
            any(
                item.get("text") == "THÍ SINH TRÚNG TUYỂN CẦN LÀM GÌ?"
                for list_value in procedure_pages[0]["lists"]
                for item in list_value.get("items", [])
            )
        )

    def test_supplemental_ocr_deduplicates_native_text_and_keeps_new_image_facts(self) -> None:
        native = "Mức hỗ trợ được cộng 1,50 điểm."
        ocr = "Muc ho tro duoc cong 1,50 diem.\n70% học phí học kỳ 1."

        merged, conflict = _merge_text(native, ocr)

        self.assertFalse(conflict)
        self.assertEqual(merged.count("1,50"), 1)
        self.assertIn("70% học phí học kỳ 1", merged)

    def test_conflicting_ocr_numeric_line_is_not_promoted_to_final_text(self) -> None:
        native = "Mức học bổng là 75 tỷ đồng."
        ocr = "Muc hoc bong la 15 ty dong."

        merged, conflict = _merge_text(native, ocr)

        self.assertTrue(conflict)
        self.assertEqual(merged, native)
        self.assertNotIn("15 tỷ", merged)

    def test_low_confidence_image_ocr_is_retained_separately_not_promoted(self) -> None:
        additions, conflict = _supplemental_ocr_lines(
            "Native verified paragraph.",
            [{"text": "garbled 75", "confidence": 0.42}],
        )

        self.assertEqual(additions, [])
        self.assertFalse(conflict)

    def test_low_confidence_ocr_never_becomes_structured_table_cells(self) -> None:
        tokens = self._synthetic_table_ocr_tokens(confidence=0.20)

        tables, _, warnings = _coordinate_table_from_tokens(
            tokens,
            page_number=1,
            source="ocr",
        )

        self.assertEqual(tables, [])
        self.assertTrue(any(warning["type"] == "OCR_TABLE_CONTENT_UNTRUSTED" for warning in warnings))

    def test_missing_confidence_ocr_never_becomes_structured_table_cells(self) -> None:
        tokens = self._synthetic_table_ocr_tokens(confidence=None)

        tables, _, warnings = _coordinate_table_from_tokens(
            tokens,
            page_number=1,
            source="ocr",
        )

        self.assertEqual(tables, [])
        self.assertTrue(any(warning["type"] == "OCR_TABLE_CONTENT_UNTRUSTED" for warning in warnings))

    def test_low_confidence_and_conflicting_ocr_are_gated_during_page_extraction(self) -> None:
        import fitz

        cases = (
            ("low-confidence", self._synthetic_table_ocr_tokens(confidence=0.20), "Bảng điểm tuyển sinh 7480201 15"),
            ("missing-confidence", self._synthetic_table_ocr_tokens(confidence=None), "Bảng điểm tuyển sinh 7480201 15"),
            (
                "numeric-conflict",
                self._synthetic_table_ocr_tokens(conflicting_first_row=True),
                "Bảng điểm tuyển sinh\nMã ngành 7480201 Điểm chuẩn 15",
            ),
        )
        for name, tokens, native_text in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                pdf_path = Path(temp_dir) / "ocr-table.pdf"
                document = fitz.open()
                page = document.new_page(width=612, height=792)
                for line_index, line in enumerate(native_text.splitlines()):
                    page.insert_text((40, 40 + line_index * 18), line, fontsize=10)
                document.save(pdf_path)
                document.close()
                ocr_text = "\n".join(
                    " ".join(str(token["text"]) for token in tokens if int(token["bbox"][1] // 25) == row)
                    for row in range(6, 10)
                )
                with patch(
                    "src.ingestion.pdf_layout._native_elements",
                    return_value=([{"type": "image", "bbox": [0, 100, 300, 250]}], []),
                ), patch(
                    "src.ingestion.pdf_layout._native_tables",
                    return_value=([], [], []),
                ), patch(
                    "src.ingestion.pdf_layout._ocr_page_layout",
                    return_value=(ocr_text, tokens, "rapidocr", []),
                ), patch(
                    "src.ingestion.pdf_layout._has_interleaved_columns",
                    return_value=False,
                ), patch(
                    "src.ingestion.pdf_layout._looks_table_like",
                    return_value=True,
                ):
                    extracted = extract_pdf_pages(pdf_path)

            page_value = extracted[0]
            self.assertEqual(page_value["ocr_boxes"], tokens)
            self.assertEqual(page_value["tables"], [])
            self.assertTrue(
                any(warning["type"] == "OCR_TABLE_CONTENT_UNTRUSTED" for warning in page_value["warnings"])
            )

    def test_list_wrapped_continuation_requires_layout_and_text_signals(self) -> None:
        valid_wrap = [
            {
                "type": "list_item",
                "ordered": False,
                "text": "Toán + 2 môn điểm cao nhất (Văn,",
                "bbox": [140, 100, 300, 115],
                "source": "native",
            },
            {
                "type": "paragraph",
                "text": "Ngoại ngữ, Lý, Hóa)",
                "bbox": [158, 120, 280, 135],
                "source": "native",
            },
        ]
        merged = _merge_list_continuations(valid_wrap)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["type"], "list_item")
        self.assertIn("Ngoại ngữ", merged[0]["text"])

        independent_paragraphs = [
            {
                "type": "list_item",
                "ordered": False,
                "text": "Danh sách hồ sơ cần nộp",
                "bbox": [40, 100, 230, 112],
                "source": "native",
            },
            {
                "type": "paragraph",
                "text": "This is an independent paragraph.",
                "bbox": [40, 120, 330, 132],
                "source": "native",
            },
            {
                "type": "paragraph",
                "text": "Heading-like sentence after the list.",
                "bbox": [58, 140, 300, 152],
                "source": "native",
            },
        ]
        retained = _merge_list_continuations(independent_paragraphs)
        self.assertEqual(len(retained), 3)
        self.assertEqual(retained[1]["type"], "paragraph")
        self.assertEqual(retained[2]["type"], "paragraph")

        non_paragraph_boundaries = (
            [
                independent_paragraphs[0],
                {"type": "heading", "text": "A new section", "bbox": [40, 120, 220, 132], "source": "native"},
            ],
            [
                independent_paragraphs[0],
                {
                    "type": "list_item",
                    "ordered": True,
                    "text": "Second item",
                    "bbox": [58, 120, 220, 132],
                    "source": "native",
                },
            ],
            [
                independent_paragraphs[0],
                {
                    "type": "paragraph",
                    "text": "separate text in another column",
                    "bbox": [400, 120, 550, 132],
                    "source": "native",
                },
            ],
        )
        for elements in non_paragraph_boundaries:
            with self.subTest(boundary=elements[1]["type"], bbox=elements[1]["bbox"]):
                boundary_result = _merge_list_continuations(elements)
                self.assertEqual(len(boundary_result), 2)
                self.assertEqual(boundary_result[0]["type"], "list_item")
                self.assertEqual(boundary_result[0]["text"], "Danh sách hồ sơ cần nộp")

    def test_unrelated_same_width_table_does_not_inherit_previous_headers(self) -> None:
        pages: list[dict[str, object]] = [
            {
                "page_number": 1,
                "page_bbox": [0, 0, 600, 800],
                "native_blocks": [],
                "tables": [
                    {
                        "headers": ["Major", "Code", "Score"],
                        "column_count": 3,
                        "bbox": [60, 600, 540, 760],
                        "rows": [],
                    }
                ],
            },
            {
                "page_number": 2,
                "page_bbox": [0, 0, 600, 800],
                "native_blocks": [
                    {
                        "type": "heading",
                        "text": "Scholarship details",
                        "bbox": [60, 30, 260, 52],
                    }
                ],
                "tables": [
                    {
                        "headers": ["column_1", "column_2", "column_3"],
                        "column_count": 3,
                        "bbox": [60, 70, 540, 400],
                        "rows": [],
                    }
                ],
            },
        ]

        _inherit_continued_table_headers(pages)

        self.assertEqual(pages[1]["tables"][0]["headers"], ["column_1", "column_2", "column_3"])
        self.assertNotIn("header_inherited", pages[1]["tables"][0])

    def test_headerless_table_inherits_headers_when_page_boundary_proves_continuation(self) -> None:
        pages: list[dict[str, object]] = [
            {
                "page_number": 1,
                "page_bbox": [0, 0, 600, 800],
                "native_blocks": [],
                "tables": [
                    {
                        "headers": ["Mã ngành", "Tên ngành", "Điểm chuẩn"],
                        "column_count": 3,
                        "bbox": [60, 600, 540, 790],
                        "rows": [],
                    }
                ],
            },
            {
                "page_number": 2,
                "page_bbox": [0, 0, 600, 800],
                "native_blocks": [],
                "elements": [{"type": "table", "table_id": "page_2_table_1", "text": "column_1 | column_2 | column_3"}],
                "tables": [
                    {
                        "table_id": "page_2_table_1",
                        "headers": ["column_1", "column_2", "column_3"],
                        "column_count": 3,
                        "bbox": [60, 12, 540, 300],
                        "rows": [
                            {
                                "values": ["7480201", "Công nghệ thông tin", "15"],
                                "cells": [
                                    {"column_index": 0, "text": "7480201"},
                                    {"column_index": 1, "text": "Công nghệ thông tin"},
                                    {"column_index": 2, "text": "15"},
                                ],
                                "data": {"column_1": "7480201", "column_2": "Công nghệ thông tin", "column_3": "15"},
                            }
                        ],
                    }
                ],
            },
        ]

        _inherit_continued_table_headers(pages)

        continued = pages[1]["tables"][0]
        self.assertEqual(continued["headers"], ["Mã ngành", "Tên ngành", "Điểm chuẩn"])
        self.assertTrue(continued["header_inherited"])
        self.assertEqual(continued["header_source_page"], 1)
        self.assertEqual(continued["rows"][0]["data"]["Điểm chuẩn"], "15")
        self.assertEqual(continued["rows"][0]["cells"][2]["header"], "Điểm chuẩn")
        self.assertEqual(pages[1]["elements"][0]["text"], "Mã ngành | Tên ngành | Điểm chuẩn")

    def test_literal_backslash_newlines_are_normalized_in_structured_table_headers(self) -> None:
        raw = ADMISSION_SCORES_PDF
        literal_major_header = r"Mã\nngành"
        literal_score_header = r"Điểm\nchuẩn"
        table_id = "page_1_table_1"
        document = build_structured_document(
            raw_path=raw,
            raw_root=RAW_ROOT,
            pages=[
                {
                    "page": 1,
                    "text": "Trang trích xuất được giữ nguyên.",
                    "elements": [
                        {
                            "type": "table",
                            "table_id": table_id,
                            "text": f"{literal_major_header} | {literal_score_header}",
                        }
                    ],
                    "tables": [
                        {
                            "table_id": table_id,
                            "headers": [literal_major_header, literal_score_header],
                            "rows": [
                                {
                                    "values": ["7480201", "15"],
                                    "cells": [
                                        {"column_index": 0, "header": literal_major_header, "text": "7480201"},
                                        {"column_index": 1, "header": literal_score_header, "text": "15"},
                                    ],
                                    "data": {literal_major_header: "7480201", literal_score_header: "15"},
                                }
                            ],
                        }
                    ],
                }
            ],
            manifest_entry={
                "document_id": "synthetic_literal_header_test",
                "title": "Synthetic table header normalization",
                "category": "misc",
                "year": 2026,
                "status": "pending_review",
                "verified": False,
            },
            source_page_count=1,
        )

        page = document["pages"][0]
        self.assertEqual(page["text"], "Trang trích xuất được giữ nguyên.")
        self.assertEqual(page["tables"][0]["headers"], ["Mã ngành", "Điểm chuẩn"])
        self.assertEqual(page["tables"][0]["rows"][0]["data"], {"Mã ngành": "7480201", "Điểm chuẩn": "15"})
        self.assertEqual(page["tables"][0]["rows"][0]["cells"][0]["header"], "Mã ngành")
        self.assertEqual(page["elements"][0]["text"], "Mã ngành | Điểm chuẩn")

    def test_header_inheritance_rejects_caption_and_misaligned_tables(self) -> None:
        scenarios = (
            (
                "caption",
                [{"type": "paragraph", "text": "Scholarship details", "bbox": [60, 30, 260, 52]}],
                [60, 70, 540, 400],
            ),
            (
                "misaligned-footprint",
                [],
                [350, 70, 590, 400],
            ),
        )
        for name, leading_blocks, current_bbox in scenarios:
            with self.subTest(name=name):
                pages: list[dict[str, object]] = [
                    {
                        "page_number": 1,
                        "page_bbox": [0, 0, 600, 800],
                        "native_blocks": [],
                        "tables": [
                            {
                                "headers": ["Major", "Code", "Score"],
                                "column_count": 3,
                                "bbox": [60, 600, 540, 760],
                                "rows": [],
                            }
                        ],
                    },
                    {
                        "page_number": 2,
                        "page_bbox": [0, 0, 600, 800],
                        "native_blocks": leading_blocks,
                        "tables": [
                            {
                                "headers": ["column_1", "column_2", "column_3"],
                                "column_count": 3,
                                "bbox": current_bbox,
                                "rows": [],
                            }
                        ],
                    },
                ]

                _inherit_continued_table_headers(pages)

                self.assertEqual(pages[1]["tables"][0]["headers"], ["column_1", "column_2", "column_3"])
                self.assertNotIn("header_inherited", pages[1]["tables"][0])

    def test_tesseract_uses_available_english_fallback_when_vietnamese_data_missing(self) -> None:
        import pytesseract
        from PIL import Image

        mock_data = {
            "text": ["75%"],
            "conf": ["95"],
            "left": [2],
            "top": [3],
            "width": [10],
            "height": [8],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        with patch.object(pytesseract, "get_languages", return_value=["eng"]), patch.object(
            pytesseract,
            "image_to_data",
            return_value=mock_data,
        ) as image_to_data:
            tokens = _pytesseract_tokens(Image.new("RGB", (20, 20)), 2.0)

        self.assertEqual(image_to_data.call_args.kwargs["lang"], "eng")
        self.assertEqual(tokens[0]["language"], "eng")
        self.assertEqual(tokens[0]["bbox"], [1.0, 1.5, 6.0, 5.5])

    def test_ocr_image_crop_boxes_are_translated_to_page_coordinates(self) -> None:
        token = {"text": "75%", "bbox": [1.0, 2.0, 7.0, 9.0], "confidence": 0.95, "source": "rapidocr"}
        with patch("src.ingestion.pdf_layout._rapidocr_tokens", return_value=[token]):
            text, tokens, engine, failures = _ocr_page_layout(
                SCHOLARSHIP_PDF,
                0,
                image_regions=[[102.1, 313.3, 508.1, 719.3]],
            )

        self.assertEqual(text, "75%")
        self.assertEqual(engine, "rapidocr")
        self.assertEqual(failures, [])
        self.assertGreater(tokens[0]["bbox"][0], 100)
        self.assertGreater(tokens[0]["bbox"][1], 300)
        self.assertLess(tokens[0]["bbox"][2], 120)

    def test_page_model_retains_layout_tables_lists_and_ocr_fields(self) -> None:
        raw = SUPPLEMENTARY_PDF
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(raw, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None)
            document = load_structured_json(result.output_path)

        self.assertEqual(document["extraction"]["page_count"], len(document["pages"]))
        self.assertTrue(all(page["page_number"] == page["page"] for page in document["pages"]))
        required_page_keys = {
            "text",
            "native_text",
            "ocr_text",
            "page_bbox",
            "elements",
            "tables",
            "lists",
            "warnings",
        }
        self.assertTrue(all(required_page_keys <= set(page) for page in document["pages"]))
        self.assertTrue(all(len(page["page_bbox"]) == 4 for page in document["pages"]))
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
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                TUITION_PDF, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None
            )
            document = load_structured_json(result.output_path)

        audit = document["content_audit"]
        self.assertEqual(audit["pages"], len(document["pages"]))
        self.assertEqual(document["extraction"]["source_page_count"], audit["pages"])
        self.assertEqual(len(document["source"]["source_sha256"]), 64)
        self.assertGreater(audit["final_chars"], 0)
        self.assertGreaterEqual(audit["final_chars"], audit["native_chars"])
        self.assertGreater(audit["records"], 0)
        full_text = "\n".join(page["text"] for page in document["pages"]).casefold()
        for token in ("học phí", "nhập học", "tín chỉ"):
            self.assertIn(token, full_text)

        fee_table = document["pages"][0]["tables"][0]
        self.assertEqual(_non_empty(fee_table["headers"]), ["Khoản thu", "Mức phí"])
        self.assertEqual(
            _non_empty(fee_table["rows"][0]["values"]),
            ["Học phí HKI (10 tín chỉ)", "12.500.000 đồng"],
        )
        tuition = next(record for record in document["records"] if record.get("record_type") == "tuition")
        self.assertEqual(tuition["page"], 1)
        self.assertEqual(tuition["tuition_amount_vnd"], 12_500_000)
        self.assertEqual(tuition["tuition_per_credit_vnd"], 1_250_000)
        self.assertEqual(tuition["admission_fee_vnd"], 1_500_000)
        self.assertEqual(tuition["elearning_fee_vnd"], 250_000)
        self.assertEqual(tuition["english_test_fee_vnd"], 250_000)
        self.assertEqual(tuition["total_cost_vnd"], 14_250_000)
        self.assertEqual(tuition["total_cost_breakdown"], "14.250.000 đồng + 250.000 đồng")
        self.assertEqual(validate_structured_document(document), [])

    def test_scholarship_tables_keep_their_own_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                SCHOLARSHIP_PDF, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None
            )
            document = load_structured_json(result.output_path)

        tables = [table for page in document["pages"] for table in page["tables"]]
        self.assertEqual(len(tables), 1)
        self.assertEqual(
            _non_empty(tables[0]["headers"]),
            ["Số lượng tân sinh viên nhập học cùng nhau", "Mức hỗ trợ HKII"],
        )
        self.assertEqual(validate_structured_document(document), [])

    def test_catalog_json_has_pages_records_and_parent_child_programs(self) -> None:
        raw = MAJOR_CATALOG_PDF
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                raw,
                raw_root=RAW_ROOT,
                output_root=Path(temp_dir),
                markdown_root=None,
            )
            document = load_structured_json(result.output_path)

        self.assertEqual(document["extraction"]["method"], "native")
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
        self.assertEqual(len(majors), 20)
        self.assertEqual(sum(len(major["programs"]) for major in majors.values()), 50)
        self.assertEqual(cntt["fact_category"], "nganh_dao_tao")
        self.assertEqual(validate_structured_document(document), [])

    def test_admission_methods_pdf_keeps_methods_and_subject_combinations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = convert_pdf_to_structured_json(
                ADMISSION_METHODS_PDF, raw_root=RAW_ROOT, output_root=Path(temp_dir), markdown_root=None
            )
            document = load_structured_json(result.output_path)

        methods = [record for record in document["records"] if record.get("record_type") == "admission_method"]
        self.assertEqual([method["method"] for method in methods], ["thpt", "hoc_ba", "dgnl", "h_sca", "trung_cap"])
        list_items = [
            item["text"]
            for page in document["pages"]
            for value in page["lists"]
            for item in value["items"]
        ]
        self.assertTrue(any("Tin học, GD kinh tế & PL, Công nghệ" in item for item in list_items))
        self.assertEqual(validate_structured_document(document), [])

    def test_score_types_are_separate_and_numeric_values_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            outputs = {
                raw.name: convert_pdf_to_structured_json(
                    raw, raw_root=RAW_ROOT, output_root=output_root, markdown_root=None
                ).output_path
                for raw in (ADMISSION_METHODS_PDF, ADMISSION_SCORES_PDF, SUPPLEMENTARY_PDF)
            }
            threshold = load_structured_json(outputs[ADMISSION_METHODS_PDF.name])
            admission = load_structured_json(outputs[ADMISSION_SCORES_PDF.name])
            supplementary = load_structured_json(outputs[SUPPLEMENTARY_PDF.name])

        threshold_records = [record for record in threshold["records"] if record.get("record_type") == "application_threshold"]
        self.assertTrue(threshold_records)
        self.assertTrue(all(record.get("score_type") == "application_threshold" for record in threshold_records))
        self.assertTrue(any(record["value"] == 600 for record in threshold_records))
        self.assertTrue(any(record["score_type"] == "admission_score" and record["value"] == 20.0 for record in admission["records"]))
        self.assertTrue(any(record.get("score_type") == "supplementary_threshold" and record.get("value") == 20 for record in supplementary["records"]))
        self.assertFalse(any("score" in record and record.get("record_type") in {"application_threshold", "admission_score", "supplementary_threshold"} for record in admission["records"]))

        # Both score tables visibly repeat their headings on page 2; detected
        # source headers must not be mislabelled as inherited metadata.
        for document in (admission, supplementary):
            score_table = document["pages"][0]["tables"][0]
            continued_score_table = document["pages"][1]["tables"][0]
            self.assertEqual(continued_score_table["headers"], score_table["headers"])
            self.assertTrue(continued_score_table["header_detected"])
            self.assertNotIn("header_inherited", continued_score_table)
            self.assertTrue(
                all(len(row["values"]) == len(score_table["headers"]) for row in continued_score_table["rows"])
            )

    def test_json_loader_builds_natural_record_chunks_and_flat_metadata(self) -> None:
        raw = TUITION_PDF
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
        self.assertTrue(document.metadata["source_file"].endswith(TUITION_PDF.name))

        page_text_documents = [
            item for item in loaded.documents
            if item.metadata.get("record_type") == "page_text"
        ]
        self.assertEqual(len(page_text_documents), page_count)
        self.assertTrue(all(item.metadata.get("page_text_source") is True for item in page_text_documents))

    def test_page_text_supplements_records_for_facts_not_structured_as_records(self) -> None:
        raw = ADMISSION_METHODS_PDF
        with tempfile.TemporaryDirectory() as temp_dir:
            convert_pdf_to_structured_json(
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
