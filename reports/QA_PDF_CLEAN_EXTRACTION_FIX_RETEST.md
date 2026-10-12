# QA PDF Clean Extraction Fix Retest

## 1. Scope and verdict

Retest scope was limited to the updated PDF ingestion patch and findings F-01/F-02/F-03. No source code, RAW PDF, `data/processed`, Chroma, or earlier QA report was edited. No deployment or full-suite run was performed.

**Verdict: BLOCKED for PDF completeness and data promotion.** The three code findings are closed by focused tests and read-only code review, but real Vietnamese OCR is unavailable, so image-contained PDF content is still unverified. The current Chroma file hash also differs from the prior QA snapshot; this retest did not modify or open the database and cannot attribute that difference.

## 2. Findings

| Finding | Result | Evidence |
|---|---|---|
| F-01 — low/missing confidence or native-conflicting OCR entering table cells | **CLOSED (code-level)** | `_filter_ocr_table_tokens()` rejects a line if any token has missing/low confidence and rejects numeric-conflicting lines before table reconstruction. Focused page-extraction tests passed for low-confidence and conflicting OCR; both produced no OCR table. Additional read-only assertions passed for missing confidence, raw OCR retention, and warning retention when the native-coordinate fallback returns a table. |
| F-02 — unrelated same-width table inheriting prior headers | **CLOSED (code-level)** | Positive real-PDF score/catalog continuation assertions passed. The existing heading negative test passed. Additional synthetic assertions passed for an independent caption before the table and a mismatched horizontal footprint; neither inherited headers. The implementation requires consecutive pages, matching column count, prior table near page end, next table near page top, at least 80% horizontal overlap, and no leading independent content. |
| F-03 — independent content merged into a list item | **CLOSED (code-level)** | The genuine wrapped-list continuation test passed. Independent paragraphs remained separate. Additional synthetic assertions passed for a heading, a new list item, and a paragraph in another column; none merged into the preceding item. Merge requires same source, tight vertical gap, hanging indent, horizontal overlap, unfinished prior text, and continuation-like text. |

“Closed” here means the reported deterministic code paths passed retest; it does not certify OCR accuracy or completeness on source PDF images.

## 3. Focused tests

Command run (with temporary test files directed to the workspace-local `.test_tmp`):

```powershell
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
& .\.venv\Scripts\python.exe -m pytest -q -rs `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_low_confidence_ocr_never_becomes_structured_table_cells `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_low_confidence_and_conflicting_ocr_are_gated_during_page_extraction `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_unrelated_same_width_table_does_not_inherit_previous_headers `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_list_wrapped_continuation_requires_layout_and_text_signals `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_score_types_are_separate_and_numeric_values_are_preserved `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_content_audit_counts_page_structures_and_keeps_import_data `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_catalog_json_has_pages_records_and_parent_child_programs `
  tests/test_ocr_runtime_integration.py
```

Result: **7 passed, 3 skipped, 2 subtests passed, 0 failed** in 6.76s. All three OCR integration tests skipped because a real Tesseract executable with Vietnamese trained data is required.

Additional non-persistent assertions run against temporary/synthetic inputs: missing OCR confidence is rejected; raw OCR text/boxes and an OCR rejection warning survive native-table fallback; independent caption/geometry cases do not inherit headers; heading/new-item/other-column cases do not merge into a list. All passed. The first scratch attempt hit the Windows temporary-directory ACL; it was rerun successfully with `.test_tmp` as the temporary root.

The Lead’s targeted/full-suite results in `PDF_CLEAN_EXTRACTION_FIX_REPORT.md` were not rerun as part of this focused retest.

## 4. OCR runtime blocker

Read-only runtime check:

- `rapidocr_onnxruntime`: not installed.
- `tesseract` on PATH: not found.
- `pytesseract.get_languages()`: raises `TesseractNotFoundError` because the executable is unavailable in this runtime.
- Consequently, image-only Vietnamese text and OCR bounding boxes on actual production PDFs could not be checked.

Do not promote freshly extracted JSON or claim full PDF completeness until OCR is operational and the image-bearing pages have been staged and compared against their source PDFs.

## 5. Data boundary snapshot

- RAW inventory: **7 PDFs**.
- Processed inventory: **7 JSON files**.
- `git status` showed no changes under `data/raw`, `data/processed`, or `chroma_db` during this retest.
- No RAW/processed content was opened for writing, and no Chroma client/rebuild was run.
- Current `chroma_db/chroma.sqlite3`: **4,313,088 bytes**, SHA-256 `D2308F45371F13DFC865565896C8FDD9E18CA37F1D1C48250A45326AE6139C0E`.
- Earlier QA snapshot reported SHA-256 `53acefe99e04618e19518182714c6f72308f517ca8f4d0d543fb4bbd25ebe5d1`. These hashes differ. The database timestamp is October 11, 2026; this retest did not write the file, so the difference predates or is external to these retest actions. Reconcile the active DB snapshot before relying on it; this retest does not assert its current logical record count or contents.

## 6. Handoff

QA can accept F-01/F-02/F-03 as closed at the deterministic-code level. The extraction/data task remains **BLOCKED** until a working OCR runtime is available, image-bearing pages are re-extracted to a separate candidate, and PDF-to-JSON coverage is validated. Reconcile the Chroma hash change before any database promotion or runtime validation. No deployment was performed.
