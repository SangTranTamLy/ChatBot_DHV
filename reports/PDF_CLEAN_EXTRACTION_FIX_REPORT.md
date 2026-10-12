# PDF Clean Extraction Fix Report

## 1. Scope

Improve the PDF-to-structured-JSON extraction path after comparing source PDFs with extracted content. Preserve source PDFs, keep page text for RAG, retain layout/table/list structure, and avoid promoting incomplete output.

This report does not claim that the complete corpus has been freshly re-extracted or is ready for Chroma. OCR is currently unavailable in this environment, so the staged regeneration was intentionally not promoted.

## 2. Root Cause Verified

- On pages containing both a native text layer and images, the previous path OCRed the full page and appended OCR output as a whole. This could duplicate native text and introduce noisy or conflicting numbers.
- OCR results did not consistently preserve coordinate/confidence details needed for table and reading-order reconstruction.
- Continued tables on subsequent pages could lose their original headers, leaving generic columns or detached numeric values.
- Wrapped list items could be split into unrelated paragraphs.
- Useful image-only content exists in the admission-methods PDF (including scholarship graphics); a working Vietnamese OCR path is required before those pages can be considered complete.

## 3. Source and Processed Data Verification

- RAW inventory: 7 PDFs, 44 pages total. No RAW PDF was edited.
- A native-only comparison against current processed JSON found normalized native text matching on 44/44 pages.
- A staged regeneration was run separately under `.test_tmp/pdf_clean_candidate_20261011`. It was not copied into `data/processed`.
- The staged audit reported 0 OCR characters because neither a usable RapidOCR installation nor a working Tesseract language model was available. Therefore it does not prove full PDF content coverage.
- A second staged attempt used the local Tesseract executable with an explicit English tessdata path. All 7 PDFs / 44 pages converted into a separate candidate (257 records, 36 warnings), but OCR on the image-bearing pages still failed to load `eng.traineddata`; OCR chars remained 0. This candidate was not promoted.
- No files under `data/processed` were changed by this task. Lead did not invoke a Chroma rebuild/write operation; however, a later QA snapshot hash differs from the earlier QA snapshot, so Chroma identity/history is not certified unchanged.

RAW PDF SHA-256 values verified after the work:

| PDF | SHA-256 |
|---|---|
| `DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf` | `D4AAB8095D6CB6D431DA72C97C652F6AC15EB003A0E3BFEF8C05CD6193717732` |
| `Hoc_Phi_DHV_2024.pdf` | `A0A78928319563717C5BEBDC0BDCA132A24935381344B3F1C81F7BF5650DCB62` |
| `HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf` | `836212A00F60E8824FECA838A7E1E8A7C240C00160CB6ED50DA5F21D161570CF` |
| `PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` | `906E5521E69DEA05672C780C6DB0CF6C16AF9C0195F37C4854996073DC197AD9` |
| `Thong_Tin_Truong.pdf` | `84C590AA899DFF0745E15B4A0244F5748EA263150CD1A6821F481D8814A92B99` |
| `TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` | `1456AAEDA00C640DB50A8F7F6FBF78CF9AD3C601B093CB2BD474464BAAA82116` |
| `Ho_Xet_Tuyen_Bo_Sung_Dai_Hoc_Chinh_Quy_2026.pdf` | `6EA39280EF7174EDCECCFF31D8F68FA5DBF0D56022B7C9BC02F43474268A4800` |

## 4. Implementation

- OCR can now run on image regions of pages that already have native text; image-only/scan pages retain full-page OCR fallback.
- OCR region coordinates are translated back to page coordinates. OCR text, bounding boxes, confidence, language/engine metadata, and warnings are retained.
- Low-confidence or duplicate OCR supplements are not blindly appended to native text. Numeric conflicts are warned and retained in OCR provenance rather than silently trusted as final RAG text.
- OCR table reconstruction applies the confidence threshold and native/OCR numeric-conflict check before creating cells. Rejected lines remain in raw OCR fields and produce explicit untrusted/partial-table warnings; fallback warnings are aggregated instead of overwritten.
- URL line-wrap repair is constrained to URLs.
- Table header detection covers fee/scholarship/contact structures. A continued table can inherit headers only when the prior table reaches the page end, the next starts near the top, horizontal table footprints align, there is exactly one table per page, and no independent text/heading occurs before it. Page geometry and provenance are retained; otherwise no inheritance is claimed.
- Adjacent wrapped list lines can be merged only when source, tight vertical spacing, an 8–36 point hanging indent, horizontal overlap, and unfinished/lowercase continuation signals all agree. Independent paragraphs remain separate.
- The staged output remains disposable and is not a replacement for current processed JSON.

## 5. Files Changed

| File | Area | Reason |
|---|---|---|
| `src/ingestion/pdf_layout.py` | OCR/layout merge, table/list reconstruction | Preserve per-region OCR geometry, avoid noisy OCR promotion, improve structured table/list capture |
| `src/ingestion/prepare_processed_from_raw.py` | Continued table headers | Carry headers across compatible page breaks with provenance/warning |
| `src/ingestion/structured_json.py` | Page model | Preserve page bounding box required to validate table continuation geometry |
| `tests/test_task_pdf_to_structured_json.py` | Regression tests | Cover OCR dedup/conflicts/confidence, page-extraction-to-table gate, coordinate mapping, URL repair, positive/negative header continuation, fee/scholarship cells, and positive/negative list continuation |
| `reports/PDF_CLEAN_EXTRACTION_FIX_REPORT.md` | Handoff report | Record verified state, limits, test outcomes, and QA requests |

Other modified files observed in the workspace pre-existed this scoped work and were not changed as part of this PDF fix.

## 6. Extraction Structure Checks

Targeted tests verify that:

- OCR bounding boxes/confidence survive conversion and region coordinates map to page coordinates.
- Duplicate OCR does not duplicate native text; low-confidence/conflicting numeric text is not silently promoted into final page text.
- Continued tables retain header-to-cell relationships and source-page provenance.
- Fee/scholarship table cells retain their row/column associations.
- Wrapped list text remains attached to the correct ordered item.
- URL repair does not rewrite unrelated text.

These are code-level regression checks. They are not a substitute for a successful OCR pass and PDF-to-JSON completeness audit on every source page.

## 7. OCR Environment Status

- `rapidocr_onnxruntime` is not installed in the active environment.
- Tesseract 5.5.3 is present through `TESSERACT_CMD`; its default tessdata location is invalid. With `TESSDATA_PREFIX` pointed at `C:\Program Files\Tesseract-OCR\tessdata`, the CLI lists `eng` only, but actual image OCR still fails to load `eng.traineddata`.
- Vietnamese trained data (`vie.traineddata`) is absent.
- Three OCR integration tests are skipped when the required language data is unavailable.

Result: image-contained Vietnamese text cannot currently be verified or recovered reliably. A working Vietnamese OCR runtime is a prerequisite for fresh complete JSON output.

## 8. Tests

| Suite | Result |
|---|---|
| `tests/test_task_pdf_to_structured_json.py` | 19 passed, 8 subtests passed |
| `tests/test_task_pdf_to_structured_json.py`, `tests/test_data_pipeline_recovery.py`, `tests/test_ingestion.py`, `tests/test_ocr_runtime_integration.py`, `tests/test_task_processed_md_to_json_migration.py` | 31 passed, 3 skipped, 15 subtests passed |
| Full `pytest -q` | 308 passed, 4 skipped, 311 subtests passed |

The Windows temporary-directory ACL issue was avoided by directing test temporary files to the workspace-local `.test_tmp` directory. No test failure was reported in these runs.

## 9. QA Review Findings and Lead Follow-up

The independent first review is recorded in `reports/QA_PDF_CLEAN_EXTRACTION_FIX_REVIEW.md`. It found:

- F-01 HIGH: confidence/numeric conflict filtering applied to final text but not OCR table cells.
- F-02 MEDIUM: equal column count on adjacent pages was insufficient proof of table continuation.
- F-03 MEDIUM: a nearby paragraph could be merged into a list item.

Lead follow-up addressed these paths and added negative/integration regression tests. Independent QA retest is recorded in `reports/QA_PDF_CLEAN_EXTRACTION_FIX_RETEST.md`; it marks F-01/F-02/F-03 closed at deterministic code level (7 passed, 3 skipped, 2 subtests). The QA retest did not rerun the full suite; the Lead full-suite result above is separate.

The QA retest found a Chroma hash different from the earlier QA snapshot. Final read-only checks found three distinct snapshots at the same 4,313,088-byte file size: initial QA `53acefe99e04618e19518182714c6f72308f517ca8f4d0d543fb4bbd25ebe5d1`, QA retest `D2308F45371F13DFC865565896C8FDD9E18CA37F1D1C48250A45326AE6139C0E`, and final `8A8035FE3819163886C7439EF49BA16BCC2FF59B5BB50372C5B040D5C4D1EF15`. The final hash was stable across two immediate reads; the SQLite and HNSW files share mtime `2026-10-11 07:26:11 UTC`. Lead invoked no Chroma rebuild/write command, and source review found tests use temporary Chroma paths, but the snapshot change is still unattributed. Do not claim the active database unchanged or rely on it until an owner reconciles its logical contents and provenance.

## 10. Data Promotion and Chroma

- Staged candidate output: **not promoted**; it has zero OCR characters and may omit image-only facts.
- `data/processed`: **unchanged**.
- Active Chroma collection: **no rebuild/write operation was invoked by Lead**. Its file hashes changed between QA snapshots; final hash `8A8035FE3819163886C7439EF49BA16BCC2FF59B5BB50372C5B040D5C4D1EF15` was read twice with the same result. Cause and logical contents remain unverified.
- RAW PDFs: **unchanged**, with post-work SHA-256 values listed above.

## 11. Remaining Risks / Blockers

- Image-only Vietnamese text, including scholarship graphics, remains unverified until OCR is operational with usable language data.
- The active `data/processed` corpus has not been regenerated using these changes, so this implementation alone does not establish that runtime now uses a complete cleaned extraction.
- A full PDF-versus-JSON visual/content comparison and subsequent Chroma freshness validation remain pending.
- The active Chroma snapshot hash changes need reconciliation before future runtime validation or promotion.

## 12. Handoff to QA

QA should independently:

1. F-01/F-02/F-03 have been retested closed at deterministic code level; when continuing, rerun targeted/full suites if code changes again.
2. Reconcile the current Chroma hash against the earlier snapshot and confirm its logical record/metadata state before any runtime validation.
3. Once OCR is operational with Vietnamese data, stage fresh extraction for all 7 PDFs, compare all 44 pages against source, and audit image-only text, numeric facts, page counts, table headers/rows/cells, and list order.
4. Block promotion/rebuild until OCR and completeness checks pass; report findings in a separately named QA report.

## 13. Verdict

**BLOCKED** for complete fresh extraction and data promotion because Vietnamese OCR is unavailable. The ingestion code changes are ready for independent QA review, but this is not a claim that corpus completeness or chatbot answer correctness has passed QA.
