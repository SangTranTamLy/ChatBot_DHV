# FULL PDF CONTENT → STRUCTURED JSON REPORT

## 1. Scope

This implementation upgrades the RAW PDF ingestion boundary so page text remains available for RAG while layout-preserving structured content is serialized alongside it.

- RAW source: `data/raw` (7 PDFs)
- Generated output: `data/processed` (7 Structured JSON files)
- Coverage audit: `reports/PDF_CONTENT_COMPLETENESS_AUDIT.md`
- RAW PDFs changed: no
- Chroma rebuilt: no

## 2. Architecture Before

The production path extracted one plain-text value per page with `pypdf`; scanned pages used string-only Tesseract fallback. Tables, lists, word coordinates, OCR confidence, and layout relationships were not part of the page contract.

## 3. Architecture After

Each page now retains:

- `text`: final page text used by the RAG-facing JSON
- `native_text`, `native_blocks`, `native_words`
- `ocr_text`, `ocr_boxes` with `bbox`, `text`, and `confidence`, plus OCR lines
- `elements`, `lists`, `tables`, and page warnings
- compatibility `semantic_text` for existing deterministic record parsers

Native extraction uses PyMuPDF text/blocks/words and `find_tables()`. OCR uses RapidOCR when installed and coordinate-preserving Tesseract fallback otherwise. When native table detection is unavailable, a conservative coordinate reconstruction is attempted; uncertain content remains in `text` and receives a warning.

## 4. Coverage Summary

| Metric | Result |
|---|---:|
| RAW PDFs discovered | 7 |
| JSON documents generated | 7 |
| PDF/JSON page-count mismatches | 0 |
| Headings | 51 |
| Paragraph elements | 780 |
| Lists | 125 |
| Structured tables | 14 |
| Table rows | 116 |
| Table cells | 475 |
| Native characters | 52,191 |
| OCR characters | 3,065 |
| Final characters | 55,266 |
| Semantic records | 253 |
| Warnings retained for review | 28 |

The per-PDF counts are in `PDF_CONTENT_COMPLETENESS_AUDIT.md`. Warnings include low OCR confidence, native/OCR numeric conflicts, blank OCR pages, and table-like regions that could not be reconstructed safely; their source text was retained.

## 5. Files Changed

| File | Area | Reason |
|---|---|---|
| `src/ingestion/pdf_layout.py` | New layout extraction module | Native blocks/words/tables, OCR boxes, lists, elements, fallback table reconstruction, warnings |
| `src/ingestion/prepare_processed_from_raw.py` | RAW → Structured JSON boundary | Use layout extractor, retain parser compatibility text, add completeness audit generation |
| `src/ingestion/structured_json.py` | Page schema and validator | Serialize page structure/audit counts and validate table/list/page invariants |
| `requirements.txt` | OCR dependencies | Declare optional RapidOCR coordinate-preserving fallback |
| `tests/test_task_pdf_to_structured_json.py` | Ingestion regression tests | Verify page model, tables/cells, lists, OCR fields, audit counts, and enrollment content |

## 6. Numeric and Enrollment Checks

Structured output retains numeric facts such as scores, fees, percentages, credit counts, codes, and dates in page text and semantic records. Decimal score parsing was corrected so `15.0` remains numeric `15.0` rather than becoming `150`.

The enrollment PDF output retains page text and records for hồ sơ, giấy tờ, nhập học, học phí, học liệu, deadlines, and support policies. Validation passed for all generated JSON files.

## 7. Tests

| Suite | Passed | Failed | Skipped | Result |
|---|---:|---:|---:|---|
| PDF/RAW/JSON/OCR targeted suites | 38 | 0 | 3 | PASS |
| Full pytest suite | 183 | 4 | 4 | See regression notes |
| Generated JSON schema validation | 7 documents | 0 | 0 | PASS |
| PDF ↔ JSON page-count audit | 7 PDFs | 0 mismatches | 0 | PASS |

The four full-suite failures are unrelated pre-existing coverage assumptions: three `Task09` cases expect a RAW filename that is not present, and one `TaskC` assertion concerns an existing answer-validator wording path. They do not involve the PDF structured page schema or this ingestion implementation.

## 8. Acceptance Criteria

- [x] All RAW PDF pages represented in JSON.
- [x] Page text, native text, OCR text, elements, lists, tables, and warnings retained.
- [x] Native table headers/rows/cells represented where detected.
- [x] OCR boxes retain bounding boxes and confidence values.
- [x] Native blocks/words are serialized for layout traceability.
- [x] Content that cannot be safely structured is retained in page text and warned.
- [x] Numeric integrity is covered by parser and regression tests.
- [x] Enrollment/import content remains in page text and semantic records.
- [x] Per-PDF completeness audit generated.
- [x] RAW PDF files unchanged.
- [x] Chroma not rebuilt.

## 9. Remaining Risks

Some borderless or visually complex tables still produce `UNPARSED_TABLE` or `PARTIAL_TABLE` warnings because the extractor cannot prove row/column boundaries without inventing relationships. QA should inspect the warning pages in the audit before approving production indexing. Installing the declared RapidOCR dependency will improve scanned-page OCR coverage; the current environment used the available native/Tesseract paths.

## 10. Handoff To QA

QA should rerun:

1. All PDF/JSON ingestion tests and the full pytest suite.
2. Page-count equality for all 7 RAW PDFs.
3. Table header/row/cell assertions for the admissions, enrollment, admission-method, and supplementary PDFs.
4. OCR-box/confidence assertions on a scanned fixture with Vietnamese Tesseract data and, when available, RapidOCR.
5. Manual review of every page listed with `UNPARSED_TABLE`, `PARTIAL_TABLE`, `NATIVE_OCR_CONFLICT`, or `LOW_OCR_CONFIDENCE`.

## Final Verdict

READY_FOR_QA
