# Program Catalog Source Audit

## Verdict

**SOURCE MISMATCH + THREE UNRESOLVED PROGRAM-NAME AMBIGUITIES.** The processed JSON preserves the table-cell text and its major-row grouping. The parent majors for the five disputed entries are supported by their table rows. However, the current evidence layer exposes 50 separate program strings while `test_task_f.py` / `test_task_g.py` expect 47 relations. Two expected names are misspelled/truncated relative to the source; three expected hyphenated names combine adjacent lines for which the PDF does not print a hyphen. The PDF's prose count (“more than 50”) is not reconciled by either representation.

No code, tests, raw PDF, processed JSON, or Chroma was modified. No deployment or pytest run was performed. Only this report was added.

## Scope and checks performed

- Source PDF: `data/raw/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` (8 pages).
- Processed JSON: `data/processed/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.json` (8 pages).
- Compared the visible/text-extracted “Bảng 1.1. Danh sách ngành” across PDF pages 1–3 with each page's JSON `tables[]` and major records in `records[]`.
- Visually inspected the table on PDF pages 1–3, including the three disputed adjacent-line pairs.
- Read the program-parent expectations/assertions in `tests/test_task_f.py` and `tests/test_task_g.py`.
- Read-only processed-corpus probe: loader returned 263 documents / splitter 281 chunks; `build_evidence()` emitted 50 distinct program-parent relations. No active Chroma query or mutation was made.

## Count discrepancy: 47 vs 50

PDF page 1, introductory prose, says: **“Năm 2026, DHV triển khai đào tạo 20 ngành học với hơn 50 chương trình đào tạo”** (20 majors with more than 50 training programs).

The catalog table itself continues over pages 1–3. Counting each separate program line in the source cells gives 50 entries, which agrees with the 50 `programs[]` items in the JSON major records and the 50 relations emitted by `build_evidence()`.

The tests define 47 pairs in `DHV_PROGRAM_PARENTS_2026`. Their per-major expected counts differ from the JSON/evidence count only for three rows:

| Parent major | JSON/PDF separate lines | Test expectation | Difference |
|---|---:|---:|---|
| Ngôn ngữ Nhật | 3 | 2 | −1 |
| Ngôn ngữ Trung Quốc | 5 | 4 | −1 |
| Tâm lý học | 5 | 4 | −1 |
| **Total** | **50** | **47** | **−3** |

The 47 test count results from treating each of the three adjacent line pairs below as one hyphenated title. That is a possible editorial interpretation, but it is not explicitly marked in the PDF. Conversely, counting every line as its own program yields 50, not the prose claim “more than 50.” The current source therefore does not settle the official exact count/name convention.

## Five disputed parent mappings

“PDF row” below numbers the extracted table grid including its header row. JSON `row_index` numbers data rows with the header omitted.

| Test's expected pair | Exact source PDF table cell (page / table / row) | JSON table and record | Audit finding |
|---|---|---|---|
| `Quản trị Marketin` → `Marketing` | p.1, Bảng 1.1 / extracted table 1 / row 4: `Marketing \| Quản trị Marketing / Digital Marketing / Truyền thông và quan hệ / công chúng / Truyền thông số \| 7340115` | `page_1_table_1`, data row 3: cell text `Quản trị Marketing`; record `major_003`, parent `Marketing`, code `7340115`, page 1 | Parent is clear from the row. Test spelling omits the final **g**; the PDF and JSON say `Quản trị Marketing`. The test's exact string is not source-confirmed. |
| `Phân tích dữ liệu kinh doan` → `Thương mại điện tử` | p.1, Bảng 1.1 / table 1 / row 5: `Thương mại điện tử \| Quản trị thương mại điện tử / Kinh doanh số / Phân tích dữ liệu kinh doanh \| 7340122` | `page_1_table_1`, data row 4: cell text ends `Phân tích dữ liệu kinh doanh`; record `major_004`, parent `Thương mại điện tử`, code `7340122`, page 1 | Parent is clear. Test spelling omits the final **h** in `doanh`; source and JSON contain the complete word. |
| `Ngôn ngữ - Văn hóa Nhật Bản` → `Ngôn ngữ Nhật` | p.2, Bảng 1.1 continuation / table 1 / row 9: `Ngôn ngữ Nhật \| Tiếng Nhật thương mại / Ngôn ngữ / Văn hóa Nhật Bản \| 7220209` | `page_2_table_1`, data row 8 has the cell as newline-separated text; record `major_012` contains two separate entries: `Ngôn ngữ` and `Văn hóa Nhật Bản`, each parent `Ngôn ngữ Nhật`, code `7220209`, page 2 | Parent is clear from the major row. The PDF visually shows two adjacent lines and no printed hyphen; it does not establish whether the intended official title is one combined program or two entries. |
| `Tiếng Trung văn hóa - Du lịch` → `Ngôn ngữ Trung Quốc` | p.2, Bảng 1.1 continuation / table 1 / row 10: `Ngôn ngữ Trung Quốc \| Tiếng Trung thương mại / Tiếng Trung hành chính văn phòng / Giảng dạy Tiếng Trung / Tiếng Trung văn hóa / Du lịch \| 7220204` | `page_2_table_1`, data row 9 has newline-separated cell text; record `major_013` contains separate entries `Tiếng Trung văn hóa` and `Du lịch`, each parent `Ngôn ngữ Trung Quốc`, code `7220204`, page 2 | Parent is clear. The source visibly has two lines with no hyphen; whether these form one compound program name is unresolved. |
| `Tâm lý tổ chức - Nhân sự` → `Tâm lý học` | p.3, Bảng 1.1 continuation / table 1 / row 3: `Tâm lý học \| Tâm lý học đường / Tâm lý lâm sàng / Tâm lý tổ chức / Nhân sự / Ứng dụng AI trong tâm lý \| 7310401` | `page_3_table_1`, data row 2 has newline-separated cell text; record `major_020` contains separate entries `Tâm lý tổ chức` and `Nhân sự`, each parent `Tâm lý học`, code `7310401`, page 3 | Parent is clear. The source visibly has two lines with no hyphen; whether these form one compound program name is unresolved. |

The slash separators above represent line breaks in the PDF/JSON cell, not punctuation printed between program titles.

## Test relationship

- `tests/test_task_f.py` defines `DHV_PROGRAM_PARENTS_2026` with 47 entries. `test_declared_programs_resolve_and_keep_evidence_parent` checks each literal as a program name and checks its evidence parent.
- `tests/test_task_g.py::test_verified_corpus_has_complete_unique_program_parent_audit` requires `len(actual) == 47`, exact equality with that tuple, and parent counts including Nhật=2, Chinese=4, Tâm lý=4.
- `tests/test_task_g.py::test_global_program_catalog_does_not_inherit_current_major` also hard-codes a global catalog count of 47.
- The processed JSON's `major_003`, `major_004`, `major_012`, `major_013`, and `major_020` records retain the exact row grouping, and the local evidence probe preserved those parent assignments. This audit did not run pytest and does not claim a test execution result.

## Confirmed vs unresolved

**Confirmed from source:** The five expected parent majors are the majors in the corresponding table rows. The exact source spellings for the first two disputed names are `Quản trị Marketing` and `Phân tích dữ liệu kinh doanh`. The three later disputed cells contain adjacent lines without a visible hyphen in the PDF; JSON retains those line breaks and records the lines separately.

**Not confirmed:** Whether the three adjacent pairs are two official program names each or three single compound titles; whether the catalog's authoritative program count is 47, 50, or greater than 50; and whether any program is omitted from Bảng 1.1 despite the prose saying “more than 50.” No source evidence justifies silently merging, renaming, or adding entries.

## Questions for the source owner

1. What are the exact official names for the Ngôn ngữ Nhật entries shown as `Ngôn ngữ` and `Văn hóa Nhật Bản`? Is there intentionally a hyphen or other joining punctuation in the authoritative catalog?
2. Are `Tiếng Trung văn hóa` and `Du lịch` separate programs, or one official compound title?
3. Are `Tâm lý tổ chức` and `Nhân sự` separate programs, or one official compound title?
4. Is the official total exactly 47, exactly 50, or greater than 50? If greater than 50, where are the additional programs documented?
5. Should the two test literals be corrected to the source spellings `Quản trị Marketing` and `Phân tích dữ liệu kinh doanh` after the official catalog owner confirms them? This audit intentionally does not change expected tests.

## Limits

This is a source-mapping audit only. It does not assess all content in the PDF/JSON, retrieval ranking, live chatbot answers, active Chroma state, or final admission facts. The extracted PDF text and visible layout support the observations above; the three title-boundary questions require an authoritative source-owner decision.
