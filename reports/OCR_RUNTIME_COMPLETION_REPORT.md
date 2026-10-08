# OCR RUNTIME COMPLETION REPORT

Date: 2026-09-23  
Project: `ChatBot_DHV`  
Target year: `2026`

## 1. Environment

| Component | Result |
|---|---|
| Python | `.venv` Python 3.12.14 |
| PyMuPDF | PASS — 1.28.2 |
| pytesseract | PASS — 0.3.13 |
| Tesseract version | PASS — 5.5.3.20260724 |
| Tesseract path | `C:\Users\Sang\AppData\Local\Programs\Tesseract-OCR\tesseract.exe` |
| Languages | PASS — `eng`, `osd`, `vie` |
| Configuration | `TESSERACT_CMD` is stored as a user environment variable and supported by `_ocr_page()` |

`tesseract --version`, `tesseract --list-langs`, and
`pytesseract.get_tesseract_version()` all completed successfully. The
Vietnamese traineddata was installed from the official Tesseract tessdata
repository.

## 2. OCR Call Path

```text
PDF page
  ↓
_extract_pdf_pages()
  ↓
_is_text_usable() quality gate
  ↓
_ocr_page()
  ↓
PyMuPDF fitz.open() / load_page() / get_pixmap()
  ↓
pytesseract.image_to_string(image, lang="vie+eng")
  ↓
_normalize_extracted_text()
  ↓
page object: text + extraction_method
  ↓
build_structured_document()
  ↓
validated processed JSON
```

| Role | File / function |
|---|---|
| Rebuild caller | `src/ingestion/prepare_processed_from_raw.py:rebuild_structured_json()` |
| Document caller | `src/ingestion/prepare_processed_from_raw.py:convert_pdf_to_structured_json()` |
| Page extractor | `src/ingestion/prepare_processed_from_raw.py:_extract_pdf_pages()` |
| Quality gate | `src/ingestion/prepare_processed_from_raw.py:_is_text_usable()` |
| OCR implementation | `src/ingestion/prepare_processed_from_raw.py:_ocr_page()` |
| Normalizer | `src/ingestion/prepare_processed_from_raw.py:_normalize_extracted_text()` |
| JSON builder/validator | `src/ingestion/structured_json.py:build_structured_document()` and `validate_structured_document()` |

The runtime uses a real Tesseract process. No mock is used in the acceptance
integration test.

## 3. Real OCR Test

| Field | Result |
|---|---|
| PDF | Runtime-generated image-only scan fixture in `tests/test_ocr_runtime_integration.py` |
| Page | 1 |
| Native text usable | No — image-only page produced no usable native text |
| OCR triggered | Yes — `_ocr_page()` was called through `_extract_pdf_pages()` |
| OCR engine | Tesseract 5.5.3.20260724, `vie+eng` |
| OCR output length | 61 characters |
| Extraction method | `ocr` |
| Processed JSON | OCR text was normalized, written to `pages[0].text`, and schema-validated |
| Result | PASS |

Observed OCR output was:

```text
Trường Dai hoc Hung Vuong TP. Hồ Chi Minh
Tuyén sinh nam 2026
```

The output contains the expected school/year content with normal OCR
diacritic imperfections; no deterministic numeric correction was applied.

## 4. Production Page Previously Failing

| Field | Result |
|---|---|
| Document | `DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf` |
| Page | 8 |
| Previous status | `OCR_FAILED` because Tesseract was not installed/discoverable |
| New status | Tesseract executes successfully; page is classified as `OCR_EMPTY_OR_LOW_QUALITY` |
| OCR output used | None — the source page is genuinely blank |
| Warnings | `OCR_EMPTY_OR_LOW_QUALITY` plus `EMPTY_EXTRACTED_PAGE`; no `OCR_FAILED` |

The page was inspected with PyMuPDF: it has no image object, drawings,
links, or meaningful text. Rendering it produces a blank white page. It is
therefore technically impossible for OCR to produce factual content from
this page without changing the RAW PDF or inventing text. The runtime itself
is proven by the real image-only integration fixture above.

## 5. Processed JSON

| Metric | Result |
|---|---:|
| Documents | 7 |
| Pages | 44 |
| Native pages | 44 |
| OCR pages in production corpus | 0 |
| Documents schema-validated | 7/7 |
| OCR_FAILED warnings | 0 |
| Remaining production warnings | 2, both attributable to blank page 8 |

The rebuild preserved document IDs, page numbers, years, source metadata,
categories, verification status, and provenance. The 2024 document remains
year `2024` and unverified; it was not promoted into the 2026 collection.

## 6. Chroma

| Field | Result |
|---|---|
| Rebuilt | Yes |
| Collection | `dhv_admissions_2026` |
| Embedding backend | Ollama |
| Embedding model | `nomic-embed-text` |
| Collection count | 71 |
| Verified 2026 documents indexed | 5 |
| Unverified documents skipped | 2 |
| Records with `year=2024` | 0 |
| Chroma `where={"year": 2024}` | 0 records |

No embedding backend, Chroma architecture, model, router, intent logic, BM25,
RRF, Answer Planner, or UI code was changed.

## 7. Regression Tests

| Test | Result |
|---|---|
| `tests/test_data_pipeline_recovery.py` | PASS — 5/5 |
| `tests/test_ocr_runtime_integration.py` | PASS — 3/3 |
| Schema validation after processed rebuild | PASS — 7/7 documents |
| Production query: `Trường có xét học bạ không?` | PASS — 4 results, all year 2026 |
| Production query: `Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu?` | PASS — 4 results, all year 2026 |
| Production query: `Hồ sơ nhập học gồm những gì?` | PASS — 4 results, all year 2026 |
| Production query: `DHV có xét tuyển bổ sung không?` | PASS — 4 results, all year 2026 |
| Production year isolation | PASS — no 2024 records |

The broader legacy ingestion suite still contains environment/corpus-specific
failures unrelated to OCR: Python temp-directory ACL failures and tests that
expect the older 15-document/2026-only corpus. Those tests were not changed
to manufacture a pass.

## 8. Remaining Issues

1. Production PDF page 8 is blank. It cannot yield OCR content; the processed
   page correctly retains empty text with `OCR_EMPTY_OR_LOW_QUALITY`.
2. The source uses the date spelling `21/8/2026`, not `21/08/2026`; no OCR
   transformation changed it.
3. Legacy ingestion tests outside the OCR acceptance scope remain stale or
   blocked by the managed Windows temp-directory ACL.

## 9. Final Verdict

# OCR_RUNTIME_READY

The Phase 1.5 OCR runtime blocker is resolved: Tesseract is installed,
Vietnamese language data is available, real OCR execution returns text, the
OCR text is normalized and stored in validated processed JSON, and the
production Chroma/retrieval path remains operational. The blank production
page is reported as a source-data limitation, not misreported as successful
OCR.
