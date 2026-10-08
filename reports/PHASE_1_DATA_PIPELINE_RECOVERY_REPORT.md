# PHASE 1 – DATA PIPELINE RECOVERY REPORT

## 1. Files changed

- `data/raw/manifest.json` — synchronized the active manifest with the seven PDFs currently present; added explicit document IDs, years, status, and independent provenance.
- `src/ingestion/raw_manifest.py` — added manifest loading, exact RAW/manifest coverage validation, and metadata-preserving manifest rebuild behavior.
- `src/ingestion/prepare_processed_from_raw.py` — added native page extraction with quality checks and OCR fallback; threaded manifest metadata into the conversion call path.
- `src/ingestion/structured_json.py` — removed the document-year hard-code, separated manifest provenance from extracted links, preserved extraction method/page warnings, and allowed clearly marked unverified documents to be processed but not indexed.
- `src/ingestion/loader.py` — uses the configured runtime target year instead of a builder-level hard-coded year.
- `src/ingestion/build_vector_db.py` — verifies Chroma collection count after indexing and reports `collection_count`.
- `requirements.txt` — added `PyMuPDF` and `pytesseract` for the OCR fallback; the Tesseract binary remains an environment dependency.
- `tests/test_data_pipeline_recovery.py` — added regression tests for manifest sync, OCR fallback, provenance, normalization, and year preservation.

No changes were made to the LLM prompt, answer planner, intent classifier, UI, or evaluation logic.

## 2. Manifest result

- RAW PDFs found: **7**
- Active manifest entries: **7**
- RAW/manifest mismatches: **0**
- Duplicate document IDs: **0**
- `Hoc_Phi_DHV_2024.pdf`: `year=2024`, `status=missing_source_url`, `verified=false`; it is retained for traceability and excluded from the verified 2026 index.

## 3. PDF extraction

- Native engine: `pypdf` page extraction.
- Fallback: PyMuPDF render + Tesseract through `pytesseract`.
- Quality gate: empty/short text, low alphanumeric density, or replacement-character corruption triggers fallback.
- Extracted pages: **49 native**, **0 OCR** on the current corpus.
- One low-quality page triggered the OCR branch and recorded `OCR_FAILED` because the current environment has neither PyMuPDF/Tesseract runtime nor a Tesseract binary installed.
- OCR call-path test: **PASS**.

## 4. Structured JSON

- JSON documents generated: **7**.
- Validation: **7/7 PASS**.
- `year` now flows from manifest → processed JSON → chunk metadata.
- Source URL now flows from manifest; URLs found inside PDFs are kept as `extracted_links` and are not required for ingestion.
- Structured facts retain explicit semantic types such as `application_threshold`, `admission_score`, and `supplementary_threshold`.

## 5. Chunking

- Verified 2026 documents loaded: **5**.
- Unverified documents skipped: **2**.
- Offline smoke chunks created: **71**.
- Chunk metadata includes document identity, category, year, status, source file, source URL when available, page, and record type.

## 6. Chroma

- Production collection: `dhv_admissions_2026`.
- Production Ollama embedding build: **PASS**, using `nomic-embed-text`; collection count **71**.
- Offline Chroma pipeline smoke collection: **PASS**, count **71**; all indexed chunks were `year=2026`, and `year=2024` query count was **0**.

## 7. Retrieval smoke

- Production hybrid/RRF smoke: **PASS**; dense and BM25 inputs reached the fusion path and returned only `year=2026` documents.
- Runtime retrieval returned documents for **5/7** required queries with no `vector_db_error`.
- The tuition-2026 and CNTT-category queries returned no document because the current RAW set contains no verified 2026 tuition PDF and no active `nganh_dao_tao` PDF. The 2024 tuition source was correctly excluded rather than relabeled as 2026.
- The legacy `smoke_test_vector_db.py` harness still fails its hard-coded expectation that a 2026 tuition-category document exists; this is a corpus coverage failure, not a Chroma or Ollama failure.

## 8. Tests

- `tests/test_data_pipeline_recovery.py`: **PASS 5/5**.
- Compile check for `src` and `tests`: **PASS**.
- Legacy tests referring to deleted RAW filenames or requiring URLs inside PDF text are stale relative to this recovery task and were not treated as acceptance criteria.
- `pytest`: **SKIPPED** because the active project environment does not have pytest installed; equivalent targeted unittest coverage was run.

## 9. Remaining action

Install the declared OCR dependencies and Tesseract binary if scanned PDFs must be OCRed. Add verified 2026 tuition and ngành đào tạo RAW sources if those two question types must return production evidence.
