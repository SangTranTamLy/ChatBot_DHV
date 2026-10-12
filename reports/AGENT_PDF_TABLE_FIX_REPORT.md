# PDF Structured JSON Table Fix Report

## 1. Scope

This bounded change addresses table-header normalization and continued-table header provenance only. No RAW PDF, `data/processed`, Chroma collection, chatbot runtime, or evaluation dataset was changed. No deployment was performed.

## 2. Root Cause Verification

### Literal backslash-newline in headers

`structured_json.py` previously normalized actual newline characters while parsing table headers, but did not normalize the two-character escaped forms `\\n`, `\\r`, or `\\r\\n`. The page table could therefore retain an escaped line break in `headers`, and its row mapping/cell labels could disagree with a normalized header.

### Continued-table header inheritance

`_inherit_continued_table_headers()` treated an explicitly empty `native_blocks` list as if preceding page content were unknown. That blocked inheritance even when adjacent-page geometry, table width, and column count showed a continued table.

The source PDFs involved in the previous report were also checked directly. The score table on page 2 of `V1_DIEM_TRUNG_TUYEN_DHV_2026.pdf` visibly repeats its column headings. The program table on pages 2–3 of `V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` also visibly repeats its headings. These tables have detected source headers; setting `header_inherited=true` for them would misstate provenance. The test now checks detected headers for those sources, while a separate headerless continuation fixture verifies genuine inheritance.

## 3. Implementation

- Added canonical table-header normalization for actual and escaped line breaks in structured page tables and parser-facing headers.
- Kept page text and cell values unchanged; synchronized normalized labels across table headers, cell headers, row-data keys, and table element text.
- Preserved malformed/non-mapping row or cell entries instead of silently dropping them during normalization.
- Changed the continuation guard so an explicitly empty native-block list counts as no independent content before the table. Missing/unavailable block metadata remains fail-closed. Existing adjacency, page-boundary geometry, table footprint, one-table-per-page, and column-count checks remain in force.
- Corrected the source-backed assertions for the score and program PDFs: retain header equality and row mapping checks, assert that visible source headers were detected, and do not label them inherited.
- Added a synthetic positive case for a truly headerless continued table, plus a structured-document regression for literal escaped newlines.

## 4. Files Changed

| File | Area | Reason |
|---|---|---|
| `src/ingestion/structured_json.py` | Header normalization and copied table structures | Normalize escaped line breaks consistently and keep headers, cells, row mappings, and table elements aligned. |
| `src/ingestion/prepare_processed_from_raw.py` | Continued-table boundary guard | Permit inheritance when an inspected page has no independent blocks before an otherwise strongly matched continuation. |
| `tests/test_task_pdf_to_structured_json.py` | Regression/source assertions | Cover escaped header normalization and justified inheritance; assert accurate provenance for PDFs that visibly repeat headers. |

## 5. Verification

### Focused regression tests

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_headerless_table_inherits_headers_when_page_boundary_proves_continuation `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_literal_backslash_newlines_are_normalized_in_structured_table_headers `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_unrelated_same_width_table_does_not_inherit_previous_headers `
  tests/test_task_pdf_to_structured_json.py::StructuredJSONPipelineTests::test_header_inheritance_rejects_caption_and_misaligned_tables
```

Result: **4 passed, 2 subtests passed**.

### Complete focused PDF test file

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_task_pdf_to_structured_json.py -q -p no:cacheprovider
```

The normal sandbox run hit Windows `WinError 5` while tests attempted nested temporary-directory writes. The suite was rerun with approved elevated execution and completed: **21 passed, 1 failed, 8 subtests passed**.

The remaining failure is `test_content_audit_counts_page_structures_and_keeps_import_data`: it expects two scholarship tables in `document["pages"][4]`, but the current source extraction has one table on PDF page 5 and the second table on PDF page 6. This is outside the two requested fixes and was not altered to make the suite green.

### Static checks

- `python -m py_compile src/ingestion/structured_json.py src/ingestion/prepare_processed_from_raw.py tests/test_task_pdf_to_structured_json.py` — **passed**.
- `git diff --check` — **passed** (Git emitted only existing line-ending conversion warnings).
- Visual source review — confirmed repeated headers on score PDF page 2 and program PDF pages 2–3.

## 6. Remaining Risks

- The complete focused PDF test file is not fully green because of the unrelated page-index/table-count assertion described above. It should be reviewed separately against the current PDF before changing its expectation.
- The normal restricted Windows test run can still encounter temporary-directory ACL errors; the elevated rerun completed the suite and exposed the one assertion failure.
- No full-project suite, live Ollama test, QA/security review, processed-data regeneration, or Chroma audit was part of this bounded task.

## 7. Handoff to QA

QA should review the diff and rerun the two new regressions, existing positive/negative inheritance tests, and the full focused PDF test file. Confirm that the score/program source headers are correctly marked as detected rather than inherited. Track the page-5/page-6 scholarship table assertion as a separate source-backed issue; do not count the current focused suite as fully passing.
