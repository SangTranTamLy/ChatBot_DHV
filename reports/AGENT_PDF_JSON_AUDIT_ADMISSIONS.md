# PDF ↔ JSON Audit — Admissions and School Information

**Audit date:** 2026-10-11  
**Verdict:** FAIL — source page text is substantially preserved, but the structured/semantic layer has confirmed factual mapping errors and incomplete list/table structure. Do not certify these four JSONs as fully ready for chatbot use until the listed defects and source conflicts are resolved.

## 1. Scope and method

Read-only comparison of only the current V1 PDFs listed by `data/raw/manifest.json` and the corresponding JSONs resolved from each manifest `category`. No source PDF, processed JSON, manifest, test, source code, or Chroma data was changed. The requested report is the only deliverable written.

The four PDFs have **22 pages total**. Each PDF page was visually rendered and inspected; page counts, native extracted text, JSON `pages[].text`, page-level elements, lists, tables/cells, semantic records, warnings, and source metadata were compared. For all 22 pages, normalized PDF word/punctuation tokens had no missing or extra tokens in the corresponding JSON page text. This establishes page-text coverage, not correctness of semantic records or proof of what is currently loaded in Chroma.

All four files have native text on every page (`ocr_pages=0`). OCR was not needed to recover page text. The JSON’s `native_text` agrees with its `text`; some extracted character counts differ from PyMuPDF because the JSON uses pypdf/layout formatting, but no page-text token loss was found.

## 2. Manifest-resolved file mapping

| PDF | Manifest raw path | Manifest category | Corresponding JSON | Pages | Verdict |
|---|---|---|---|---:|---|
| `V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf` | `data/raw/xet_tuyen_bo_sung/V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf` | `xet_tuyen_bo_sung` | `data/processed/xet_tuyen_bo_sung/V1_XET_TUYEN_BO_SUNG_DHV_2026.json` | 2/2 | **FAIL — semantic deadline record truncated; list structure incomplete** |
| `V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf` | `data/raw/ho_so/V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf` | `ho_so` | `data/processed/ho_so/V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.json` | 6/6 | **FAIL — incorrect fee record and contact-table key collision** |
| `V1_THONG_TIN_TRUONG_DHV.pdf` | `data/raw/thong_tin_truong/V1_THONG_TIN_TRUONG_DHV.pdf` | `thong_tin_truong` | `data/processed/thong_tin_truong/V1_THONG_TIN_TRUONG_DHV.json` | 7/7 | **FAIL — many PDF lists/headings are not structured in JSON** |
| `V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` | `data/raw/phuong_thuc_xet_tuyen/V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` | `thong_tin_truong` | `data/processed/thong_tin_truong/V1_TONG_QUAN_TUYEN_SINH_DHV_2026.json` | 7/7 | **FAIL — 16/20 major records have the wrong major name; false OCR table** |

The admissions-overview JSON’s folder follows the manifest category (`thong_tin_truong`), even though its PDF is physically under `phuong_thuc_xet_tuyen`. This is the current manifest-driven location; it was not changed. The category label is nevertheless a retrieval/routing risk because the document contains admissions methods, scholarship rules, and deadlines.

## 3. Cross-document findings

### 3.1 Confirmed extraction coverage

- Page counts match for all four PDFs.
- `pages[].text` retains the visible native text, headings, numbers, dates, email addresses, URLs, thresholds, and fee values across all inspected pages.
- The PDF tables’ principal cell values are preserved in the corresponding page text. Where structured native tables exist, their cell values were compared against the rendered PDFs.
- No OCR-only content or scanned-page text was identified in these four PDFs.

### 3.2 Source content conflicts — not extraction loss

These discrepancies are present in the current PDFs themselves; the JSON generally preserves both versions and cannot safely choose which is authoritative.

1. **Enrollment location numbering conflicts within one PDF.** On enrollment PDF page 1, Cơ sở 1 is `194 Lê Đức Thọ` and Cơ sở 2 is `37 Kinh Dương Vương`. On page 3, the “Hình thức 1” instructions reverse those labels: Cơ sở 1 is `37 Kinh Dương Vương`, Cơ sở 2 is `194 Lê Đức Thọ`. JSON pages 1 and 3 preserve these conflicting statements.
2. **Address list differs across the two current PDFs.** Enrollment PDF page 1 names two sites, including `37 Kinh Dương Vương` as Cơ sở 2. School-information PDF page 7 lists Cơ sở 2 as `736 Nguyễn Trãi` and Cơ sở 3 as `37 Kinh Dương Vương`. This is a source-level conflict, not an extraction omission.
3. **Admissions count conflicts with its table.** Admissions-overview PDF page 2 says `23 mã xét tuyển`; its program/major table on pages 3–5 contains 20 rows. The JSON table has the same 20 rows. This inconsistency already exists in the PDF and needs an owner/source decision.

## 4. Per-document findings

### 4.1 `V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf` — FAIL (text and table mostly pass)

**Content and structure that match:**

- PDF pages 1–2 correspond to JSON `/pages/0`–`/pages/1`.
- The supplementary-admission table is represented as page 1: 9 data rows × 6 columns and page 2: 3 data rows × 6 columns. Combined: 12 programs and 72 data cells, matching the PDF table. Codes, quotas, and score columns were visually checked; values such as 15.0/18.0 and 20.0/20.0 (*) remain attached to the proper rows.
- JSON records include the overall quota (`345`), 12 programs, and per-program threshold records.
- The PDF page 2 `READING_ORDER_UNCERTAIN` warning was reviewed visually. The three continuation rows 10–12 appear in the correct order in the table and JSON; this warning is conservative and did not correspond to an observed row-order defect.

**Confirmed semantic-record defect:**

- PDF page 2 says the application period lasts through 21/8/2026 and continues with the free-application information. JSON `/records/5` (`record_id=deadline_001`) has `deadline_date="21/8/2026"`, but `description="ời gian nhận hồ sơ đến hết ngày 21/8/2026, DHV miễn phí xét tuyển đối với thí"` is clipped at both ends. The date is intact, but the record text is not a complete source sentence.
- PDF page 2 includes a numbered list of two campuses. JSON `/pages/1/lists` is empty; the words remain in `/pages/1/text`, so this is a structure loss, not page-text loss.

**Result:** table/cell extraction **PASS**; page-text coverage **PASS**; complete structured representation **FAIL**.

### 4.2 `V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf` — FAIL (critical wrong numeric record)

**Content that matches:**

- PDF pages 1–6 map to JSON `/pages/0`–`/pages/5`; every page’s native text, enrollment dates, required documents, tuition/fees, scholarship/support amounts, and deadlines is present in page text.
- The page 3 tuition table is preserved in JSON `/pages/2/tables/0`: 10 credits = 12,500,000 VND; admission fee = 1,500,000 VND; electronic learning account = 250,000 VND; optional English test = 250,000 VND; listed total = 14,250,000 VND plus the optional 250,000 VND.
- Scholarship/support tables on PDF pages 4–5 are represented with headers and cells in JSON `/pages/3/tables/0` and `/pages/4/tables/0`.

**Confirmed defects:**

1. **Wrong fee in semantic record (HIGH).** PDF page 3, table “Mức phí”, gives `Kiểm tra năng lực Tiếng Anh (nếu có) = 250.000 đồng`. The page table JSON is correct, but JSON `/records/10` (`record_id=tuition_semester_1`) says `english_test_fee_vnd=5000000`. Any answer path using this record can return a five-million VND fee instead of 250,000 VND.
2. **Wrong record page provenance.** The same `/records/10` says `page=1`, although its fee facts are in PDF/JSON page 3; it separately says `per_credit_page=6`, which does match the per-credit statement on page 6. The single `page` field is not a valid locator for the fee table.
3. **Duplicate table headers overwrite contact data.** PDF page 2 table has two adjacent `Tên Zalo`/`SĐT/Zalo` pairs. JSON `/pages/1/tables/0/headers` repeats those labels, and each row’s `values`/`cells` retains all four cells. But `/pages/1/tables/0/rows/0/data` is a dictionary keyed by the repeated headers, so the first advisor/phone pair is overwritten by the second pair. This data object is incomplete even though the parallel `values` and `cells` arrays remain complete.
4. **List structure is incomplete.** PDF page 3 presents the four required documents as a set of items, but JSON `/pages/2/lists` is empty. PDF page 5 has a numbered four-item welcome-gift list, but JSON `/pages/4/lists` is empty. Text remains in page text.
5. `UNPARSED_TABLE` warnings appear on PDF pages 1 and 6 even though visual inspection shows prose/list-like content, not a table. These warnings do not indicate missing page text; they appear to be false table-like detections.

**Result:** page-text coverage **PASS**; core fee table cells **PASS**; semantic records/contact data/list structure **FAIL**.

### 4.3 `V1_THONG_TIN_TRUONG_DHV.pdf` — FAIL (text present, structured lists substantially incomplete)

**Content that matches:**

- PDF pages 1–7 map to JSON `/pages/0`–`/pages/6`; all visible text was found in the matching page text, including history dates, names, addresses, phone, emails, social URLs, partner names, and organization descriptions.
- The PDF has no data tables; JSON also has no table objects. The sole `document_text` record retains the document-wide text, and each page retains page-local text.

**Confirmed structure loss:**

- PDF page 3 has a three-item numbered list describing the logo. JSON `/pages/2/lists/0/items` contains only the `Link logo` entry; the first two numbered items remain in page text but are not represented as list items.
- PDF page 4 contains a five-item organizational-unit list. JSON `/pages/3/lists/0/items` contains only one person/leadership item, not those five units.
- PDF pages 5–7 contain numerous bullets/numbers for leadership, international partners, business partners, cooperation objectives, campus addresses, and social channels. JSON `/pages/4/lists/0/items` contains one item; `/pages/5/lists` and `/pages/6/lists` are empty. These source lists remain flattened into paragraph text.
- `content_audit` claims only 3 lists and 3 list items for the entire seven-page PDF, whereas the rendered source visibly has many more. The heading structure is also sparse relative to the many numbered sections/headings in the PDF.

**Provenance caveat:**

- JSON source metadata points to `https://dhv.edu.vn/` and marks the document verified, but `source_type="unknown"` and `source_date` is blank. The manifest’s `collected_at` is 2026-09-23 while this V1 file’s current filesystem modification date is 2026-10-11. That timestamp may be a copy/edit date, but provenance does not identify the exact V1 revision/source capture.

**Result:** page-text coverage **PASS**; list/heading structured completeness **FAIL**; provenance completeness **WARN**.

### 4.4 `V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` — FAIL (critical wrong major entities and false table)

**Content that matches:**

- PDF pages 1–7 map to JSON `/pages/0`–`/pages/6`; all visible admissions text is present, including the five methods on PDF page 5, score formula text, scholarship conditions and percentages on page 6, and schedule dates on page 7.
- The actual major/program table is preserved as page fragments in JSON `/pages/2/tables/0`, `/pages/3/tables/0`, and `/pages/4/tables/0`. Those fragments contain 20 rows × 3 columns, and the table cell values match the PDF table visually.

**Confirmed critical semantic-record defect:**

- JSON has 20 `record_type="major"` records, but **16 of 20 `major_name` values do not match the major name in the source table row for that same major code**. The record generator has promoted a child-program name into the major field and leaves `programs=[]`.
- Examples:
  - PDF page 3: major `Quản trị kinh doanh`, code `7340101`; `Đổi mới sáng tạo` appears as a program. JSON `/records/0` instead labels code `7340101` as major `Đổi mới sáng tạo`.
  - PDF page 3: major `Tài chính ngân hàng`, code `7340201`; `Tài chính doanh nghiệp` is a program. JSON `/records/4` labels code `7340201` as `Tài chính doanh nghiệp`.
  - PDF page 4: major `Công nghệ thông tin`, code `7480201`; `Phân tích dữ liệu lớn` is a program. JSON `/records/8` labels code `7480201` as `Phân tích dữ liệu lớn`.
  - PDF page 4: major `Quản trị Khách sạn`, code `7810201`; JSON `/records/14` uses `Quản trị nhà hàng và dịch vụ ẩm thực` as the major.
- The table cells themselves are correct, so this is not PDF text extraction loss; it is a semantic-record/entity assignment failure. It can directly cause wrong answers to major-name or major-code questions if the chatbot consumes `records[]`.

**False table reconstruction and missing list structure:**

- PDF page 6 contains scholarship prose and bullet conditions, not a grid/table. JSON `/pages/5/tables/0` is labeled `page_6_table_ocr_1`, with fragmented headers such as `c. Xét`, `học`, `bổng`, `bằng`, `học bạ`, plus rows made from separate words like `70%`, `học`, `phí`, `chuẩn`, `HK1`. This is not a valid row/column representation of the scholarship rules. The page emits `PARTIAL_TABLE`; `content_audit` consequently counts 4 tables/23 rows, although the PDF has one major/program table continued across pages 3–5 and no scholarship table on page 6.
- The source has visible numbered/bulleted lists on PDF pages 1, 5, 6, and 7. JSON `/pages/0/lists`, `/pages/4/lists`, `/pages/5/lists`, and `/pages/6/lists` are empty. Page text is preserved, but list order/type is not represented.
- The five admission methods on PDF page 5 are preserved in `/pages/4/text` but there is no `record_type="admission_method"` in `records[]`; method-specific semantic records are absent.

**Source and routing caveats:**

- PDF page 2 says there are 23 admission codes; the table across pages 3–5 contains 20 rows. This is an internal source contradiction (see §3.2), not a JSON extraction omission.
- Manifest/JSON category is `thong_tin_truong` although the PDF is physically under `data/raw/phuong_thuc_xet_tuyen` and contains admissions methods, scholarships, and deadlines. The `source.raw_file` points to the right PDF, but category-based filtering may route or filter it incorrectly.
- Source URL is the broad portal root `https://tuyensinh.dhv.edu.vn/`, rather than a page-specific URL. It is an official host but weak document-level provenance.
- Page 6’s table source is marked `ocr`, but `pages[5].ocr_text` is empty and document `extraction.ocr_char_count=0`; the supposed partial OCR table therefore has no preserved OCR text in the advertised OCR field for independent review.

**Result:** page-text coverage **PASS**; table cell extraction for the actual major table **PASS**; semantic records, scholarship table reconstruction, list structure, and routing metadata **FAIL/WARN**.

## 5. Chatbot readiness

**Not ready to certify for ingestion/answering from these JSONs.** Page text is broadly complete and contains enough raw wording for many RAG lookups, but the JSON also exposes structured/semantic records. At least one numeric record is demonstrably wrong (English test fee: 5,000,000 vs PDF 250,000), and 16/20 admission major records bind a program name to the wrong major code. The admissions overview also has a false scholarship table and missing typed admission-method/list structures. These can produce wrong or incomplete deterministic answers even though `pages[].text` is present.

Before relying on these outputs, correct the confirmed extraction/record defects, resolve the PDF-internal and cross-PDF campus/count conflicts with the document owner, regenerate only after approval, then rerun this PDF↔JSON audit. This audit did **not** inspect active Chroma contents or runtime retrieval, so it makes no claim that the current chatbot is using these exact files.

## 6. Changed files

- Created: `reports/AGENT_PDF_JSON_AUDIT_ADMISSIONS.md` (this audit report).
- No RAW PDF, processed JSON, manifest, code, tests, or Chroma files were changed.
