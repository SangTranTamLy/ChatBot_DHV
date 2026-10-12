# PDF Extraction Code Audit

## Verdict

**NOT YET PROVEN CHATBOT-READY FOR ALL PDF CONTENT.** The current seven JSON files preserve the complete PyMuPDF-extractable native text layer page by page and load successfully through the verified-document loader. However, table structure is unresolved on multiple pages, one reconstructed table is visibly fragmented, multi-column order warnings remain, OCR behavior is not exercised by the current PDFs, and the focused test suites are not green against the current V1 filenames/environment.

This was a read-only audit. No source code, PDF, JSON, manifest, or Chroma data was changed. The only artifact created is this report.

## 1. Scope and method

Reviewed the active call path beginning at `src/ingestion/prepare_processed_from_raw.py`, its layout and schema helpers, the JSON loader, the relevant tests, and the current `data/raw` / `data/processed` files. Rechecked current page counts, JSON validation, warning locations, native text equality, and loader behavior independently. Also ran:

```text
.venv\Scripts\python.exe -m pytest tests/test_task_pdf_to_structured_json.py tests/test_ingestion.py -q -p no:cacheprovider
```

No extraction/rebuild command was run because it would overwrite generated JSON and the audit was explicitly read-only.

## 2. Actual pipeline

1. `main()` parses paths and invokes `rebuild_structured_json()` (`prepare_processed_from_raw.py:671-695`).
2. `rebuild_structured_json()` checks the RAW manifest/file set, iterates RAW PDFs, and calls `convert_pdf_to_structured_json()` (`prepare_processed_from_raw.py:557-635`).
3. `convert_pdf_to_structured_json()` calls `_extract_pdf_pages()`, inherits continued table headers, builds the structured document, then writes JSON (`prepare_processed_from_raw.py:423-493`).
4. For existing RAW PDFs, `_extract_pdf_pages()` uses `pdf_layout.extract_pdf_pages()` and separately adds pypdf `semantic_text` for deterministic record parsing (`prepare_processed_from_raw.py:139-162`).
5. `extract_pdf_pages()` gathers PyMuPDF native blocks/words and `page.find_tables()`, conditionally OCRs pages with no native text or image blocks, merges supplemental OCR text, structures lists/tables, and attaches warnings (`pdf_layout.py:1080-1258`).
6. `build_structured_document()` serializes page fields, derives semantic records and aggregate counts, then calls `validate_structured_document()` (`structured_json.py:1220-1385`). `write_structured_json()` validates again and writes UTF-8 JSON (`structured_json.py:1838-1852`).
7. `load_verified_documents()` validates and chunks only verified documents matching the target year (`loader.py:72-138`). `build_chunk_documents()` indexes semantic records and adds page-text chunks as a supplement (`structured_json.py:1685-1805`).

## 3. Current output independently verified

| Current V1 source | PDF/JSON pages | Records | Tables | Warnings |
|---|---:|---:|---:|---:|
| `V1_DIEM_TRUNG_TUYEN_DHV_2026.pdf` | 2/2 | 62 | 2 | 1 |
| `V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf` | 6/6 | 16 | 4 | 2 |
| `V1_HOC_PHI_DHV_2024.pdf` | 1/1 | 1 | 0 | 1 |
| `V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` | 8/8 | 89 | 3 | 5 |
| `V1_THONG_TIN_TRUONG_DHV.pdf` | 7/7 | 1 | 0 | 0 |
| `V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` | 7/7 | 27 | 4 | 4 |
| `V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf` | 2/2 | 24 | 2 | 1 |
| **Total** | **33/33** | **220** | **15** | **14** |

All 33 JSON pages have non-empty `pages[].text`. A page-by-page comparison against the current PDFs' PyMuPDF text layer, using the same native ordering heuristic and cleaner, found exact equality for `native_text` on **33/33 pages**; `pages[].text` also equals `native_text` on all 33 pages. The current PDFs contain no embedded raster image objects, and all 33 pages have empty `ocr_text` and zero `ocr_boxes`. Thus native text preservation is confirmed for these files; OCR/image-text completeness is not empirically exercised by this corpus.

Every JSON passed `load_structured_json()` validation. A read-only loader run for target year 2026 saw 7 files, loaded 6 verified documents into 251 LangChain documents/chunks, skipped the unverified 2024 tuition JSON, and reported zero metadata errors. This confirms JSON-to-loader compatibility, not current Chroma freshness or answer quality.

## 4. Findings and coverage gaps

### F-01 — Table extraction is incomplete/unverified (HIGH)

Current warnings explicitly leave table-like content without a structured row/column relation:

- Enrollment PDF: pages 1 and 6 — `UNPARSED_TABLE`.
- Tuition 2024 PDF: page 1 — `UNPARSED_TABLE`.
- Admission-method/scholarship PDF: pages 4–8 — `UNPARSED_TABLE`.
- Admission overview PDF: pages 1, 2, and 7 — `UNPARSED_TABLE`.
- Admission overview PDF: page 6 — `PARTIAL_TABLE`.

Page text remains available, so this is not a silent text drop. It is still a material gap against the requirement that table headers, rows, and cells remain related. The method pages and enrollment pages must be compared visually with their PDFs before claiming full structured coverage.

The current JSON's overview page 6 table is especially concerning: it has 11 headers such as `"c. Xét"`, `"học"`, `"bổng"`, blank, `"bằng"`, `"học bạ"`, and data rows are fragments of bullet prose such as `"70%"`, `"học"`, `"phí"`, `"chuẩn"` rather than a dependable semantic column schema. It is marked `PARTIAL_TABLE`, but `validate_structured_document()` accepts it. It is stored as `source="native_layout"` while `reconstructed_from_ocr` is `true` (`pdf_layout.py:795-806`), which is also inaccurate provenance for this native-word fallback.

Relevant implementation:

- Native table handling relies on `page.find_tables()` (`pdf_layout.py:829-913`).
- The fallback keeps only a longest contiguous run of rows with numeric signals, chooses x-coordinate anchors, and guesses a header (`pdf_layout.py:609-826`). Non-numeric or irregular rows can therefore be excluded from the structured table.
- A page receives `UNPARSED_TABLE` only when **no** table at all was found (`pdf_layout.py:1168-1197`). A partially detected page can therefore lack an explicit warning for additional missed tables.
- The validator checks that headers/rows/cells have basic list/object/text shapes, but not header-to-cell cardinality, semantic alignment, or that warnings cover partial source tables (`structured_json.py:1474-1493`).

### F-02 — Reading order is heuristic and unresolved (MEDIUM)

Current warnings remain on score PDF page 2 and supplemental-admissions PDF page 2 (`READING_ORDER_UNCERTAIN`). `_has_interleaved_columns()` uses bbox thresholds (`pdf_layout.py:547-564`); when it fires, the final native text uses PyMuPDF's `sort=True`, which is still a heuristic, not a column-aware reading-order reconstruction (`pdf_layout.py:1095-1101`).

Additionally, `extract_pdf_pages()` concatenates native elements, OCR elements, native table elements, and fallback table elements before list reconstruction (`pdf_layout.py:1186-1190`); it does not globally interleave those sources by bbox. Supplemental OCR text is appended after native text (`pdf_layout.py:1131-1146`). The current tests do not establish correct visual reading order on the two flagged source pages or on a representative multi-column fixture.

### F-03 — OCR safety behavior is not validated by these seven PDFs (MEDIUM)

OCR is conditional: it runs only if native text is absent or image blocks are present (`pdf_layout.py:1102-1114`). That is reasonable for these image-free, text-layer PDFs, but the current run contributes no evidence about OCR recovery from a scanned page.

The OCR path retains bbox/text/confidence from RapidOCR/Tesseract (`pdf_layout.py:218-305`) and gates low-confidence/conflicting OCR from table cells. For a page with no native text, however, OCR lines become `final_text` without the supplemental confidence gate (`pdf_layout.py:1131-1146`); low confidence is warned later, so the text can still enter JSON and downstream page chunks. Numeric conflict detection only compares sufficiently similar text windows (`pdf_layout.py:940-1001`); OCR-only pages cannot be checked against native facts. Existing synthetic tests cover some of these gates, but no current source PDF exercises them.

### F-04 — Schema checks do not prove source completeness (MEDIUM)

The JSON validator checks page numbering and that at least one page in the document has text, and it compares `extraction.page_count` to the JSON page array (`structured_json.py:1442-1513`). It does not open the source PDF, compare source page count, compare extracted text to PDF text, or prove every meaningful visual element was captured. Those checks were performed separately for page count and native text above; they are not an automated ingestion gate.

`content_audit` counts are useful inventory metrics, not PDF-to-JSON completeness assertions. Semantic record parsers are category-specific; page-text chunks prevent unstructured paragraphs from being wholly excluded from the RAG loader, but do not repair missing table relationships (`structured_json.py:1080-1202`, `1685-1805`).

### F-05 — Source-version/repeatability provenance is incomplete (MEDIUM)

`raw_manifest.py` has a SHA-256 generator (`_raw_entry()`, line 163), but the current `data/raw/manifest.json` has no SHA-256 value for any of the seven files. `validate_manifest_sync()` checks referenced/missing files, unique IDs, year, and URLs, but does not require or compare checksums (`raw_manifest.py:67-106`). The processed JSON also does not copy a source checksum into its `source` object (`structured_json.py:1347-1360`). The manifest sync currently returns no errors, but it cannot prove that a processed JSON was built from the exact current PDF bytes. No idempotence/deterministic-output test was found in the relevant PDF tests.

One metadata field is misleading: because the current run has no OCR, `extraction.text_source` is serialized as `"pypdf"` (`structured_json.py:1361-1364`), although `pages[].text` and `native_text` were independently confirmed to match PyMuPDF output. The pypdf extraction is stored separately as `semantic_text` for record parsing.

### F-06 — Relevant test suite is not aligned/green (HIGH for release confidence)

The test command above finished with **12 failed, 12 passed, 5 subtests passed**. Several source-backed tests still refer to removed pre-V1 RAW filenames, for example `PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` and `HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf` (`tests/test_task_pdf_to_structured_json.py:369-386, 416-455, 490-524, 549-564`). Their assertions also expect old page counts (the methods fixture expects 10 pages; current V1 has 8). These failures do not validate the current V1 content.

The run also hit Windows temp-path `PermissionError` while creating or cleaning `TemporaryDirectory` test fixtures. This is an environment/test-infrastructure failure, not evidence of a production extraction defect, but it leaves OCR/layout and loader assertions unverified in this environment. The test suite should be pointed at the manifest/current V1 sources and rerun in a writable test temp directory before QA sign-off.

## 5. Current completeness-audit report drift

`reports/PDF_CONTENT_COMPLETENESS_AUDIT.md` does not describe the current V1 JSON snapshot. It reports 253 records, 14 tables, 116 rows, 475 cells, and 28 warnings. The current JSONs independently total 220 records, 15 tables, 113 rows, 489 cells, and 14 warnings. The current output may have been regenerated after that report; the report should not be used as proof for the current files.

## 6. Acceptance matrix

| Requirement | Audit result |
|---|---|
| Every current PDF page represented in JSON | **PASS** — 33/33 page counts match |
| Full searchable native text retained page-by-page | **PASS** — exact PyMuPDF text equality on 33/33 |
| Every page has non-empty `pages[].text` | **PASS** for these 33 pages |
| JSON schema and current 2026 loader compatibility | **PASS** — 7 validate; six 2026 verified docs load, 2024 unverified is skipped |
| Table headers/rows/cells preserved for every table-like region | **FAIL / UNPROVEN** — 11 `UNPARSED_TABLE` warnings; partial page 6 reconstruction is fragmented |
| Lists/order fully match source PDFs | **UNPROVEN** — only 9 structured lists; no full page-by-page visual audit; order warnings remain |
| OCR text/bbox/confidence correct on image content | **UNPROVEN** — no raster images and no OCR output in current corpus |
| Multi-column order is correct | **UNPROVEN** — two current reading-order warnings and no adequate source-page test |
| Numeric OCR conflict handling proven against source | **UNPROVEN** — synthetic coverage only; current corpus has no OCR |
| Reproducible source-to-JSON version provenance | **FAIL** — missing current manifest checksums, no validation/checksum in JSON |
| Relevant extraction regression suite green on current V1 files | **FAIL** — 12 failed / 12 passed; stale fixtures and Windows temp ACL |

## 7. Conclusion / next handoff

The JSONs are structurally consumable by the chatbot loader, and their current native text layer is complete relative to PyMuPDF's text extraction for all 33 pages. That does **not** establish that every table/list/visual fact in the PDFs was extracted correctly. Do not treat the current table structures or old completeness report as fully QA-certified, and do not claim the extraction pipeline is completely reliable for chatbot answers yet.

Before declaring the data stage complete, QA should visually compare every page with `UNPARSED_TABLE`, `PARTIAL_TABLE`, and `READING_ORDER_UNCERTAIN` against its current V1 PDF, especially admission methods/scholarship pages 4–8, enrollment pages 1/6, and overview page 6. Separately, update/reconcile the extraction tests with current V1 filenames, run OCR tests under a writable temp path, and verify source checksums/repeatability. No Chroma rebuild or deployment was performed or recommended by this audit.
