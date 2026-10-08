# CHATBOT RUNTIME NO-DATA FIX REPORT

## 1. Bug

`nhập học cần những gì` was in the DHV domain and its verified content was
already present in `data/processed`, but runtime returned the generic `no_data`
answer. This task changed downstream runtime only; RAW PDFs, OCR extraction
and folder organization were not changed.

## 2. Confirmed Root Cause

Confirmed from code and runtime trace:

1. `CATEGORY_TAXONOMY_MISMATCH` and `RETRIEVAL_FILTER_ERROR`: `HOI_NHAP_HOC`
   routed only to `category=nhap_hoc`, while the verified 2026 enrollment
   corpus is stored under `category=ho_so`.
2. `STALE_VECTOR_DB`: the old collection had 247 chunks while the current
   processed loader produced 251 chunks; the old collection did not match the
   current processed chunk set.

After the category bridge and local rebuild, BM25/dense/RRF returned relevant
chunks, evidence selection retained them, and the validator accepted the
evidence-grounded answer. `BM25_MISS`, `DENSE_MISS`, `RRF_FAILURE`,
`EVIDENCE_OVER_FILTERING` and `VALIDATOR_FALSE_REJECTION` were not confirmed.

## 3. Processed Data Verification

`DATA_PRESENT_IN_PROCESSED = TRUE`.

| File | document_id | category | year/status | records |
|---|---|---|---|---:|
| `data/processed/ho_so/HO_SO_NHAP_HOC_DAY_DU_DHV_2026.json` | `ho-so-nhap-hoc-day-du-dhv-2026` | `ho_so` | 2026 / verified | 42 |

The document contains enrollment documents on page 3 (invitation/Zalo
confirmation, transcript, identity card, 2026 graduation result), the original
document/no-notarization note, enrollment dates, tuition, enrollment fee and
e-learning fee. Its source is the official DHV URL:

`https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026-va-thong-tin-tu-van-vien-ho-tro-tan-sinh-vien/`

Current processed loader audit: 7 files seen, 5 verified 2026 documents loaded,
2 unverified files skipped, 251 record/chunk documents before supplemental
page-text indexing.

## 4. Chroma Freshness Check

### Old

- Collection: `dhv_admissions_2026`
- Count: 247
- Metadata was 2026 / verified / DHV, but processed-vs-Chroma comparison found
  5 current chunks missing and one old chunk remaining.
- The enrollment records existed, but `category=nhap_hoc` filtered them out.

### New

The local collection was rebuilt from the canonical processed-data loader:

```text
.venv\Scripts\python.exe -m src.ingestion.build_vector_db --reset --data-dir data/processed --persist-dir chroma_db --collection dhv_admissions_2026 --year 2026 --embedding-backend ollama --embedding-model nomic-embed-text --ollama-base-url http://127.0.0.1:11434
```

Post-build audit:

- count: 258;
- years: `2026=258`;
- statuses: `verified=258`;
- school codes: `DHV=258`;
- source URLs: official DHV host, none missing in the audited collection;
- 2024/unverified/wrong-school records: none;
- record types include `enrollment_document=35` and supplemental
  `page_text=7`.

Categories: `diem_trung_tuyen=66`, `hoc_bong=37`, `ho_so=42`, `hoc_phi=1`,
`lich_tuyen_sinh=2`, `phuong_thuc_xet_tuyen=1`, `nganh_dao_tao=42`,
`nguong_dau_vao=40`, `cach_tinh_diem=3`, `xet_tuyen_bo_sung=24`.

## 5. Intent Trace

Before the fix:

```text
query: nhập học cần những gì
intent: HOI_NHAP_HOC
target_school: UNSPECIFIED
scope_reason: in_scope_dhv
route: nhap_hoc
metadata filter: year=2026 AND category=nhap_hoc
retrieved_docs_count: 0
evidence_count: 0
status: no_data
```

After the fix:

```text
normalized_question: nhập học cần những gì
intent: HOI_NHAP_HOC
target_school: UNSPECIFIED
scope_reason: in_scope_dhv
route: ho_so, nhap_hoc
retrieval_calls: 1
retrieved_docs_count: 42
evidence_count: 42
status: ok
```

The legacy `nhap_hoc` label remains supported while `ho_so` is included as the
current verified-corpus alias. Schedule wording such as `Khi nào tuyển sinh?`
and `bao giờ tuyển sinh?` now maps to `HOI_LICH_TUYEN_SINH`.

## 6. Category Mapping

```text
HOI_NHAP_HOC / HOI_HO_SO -> ho_so, nhap_hoc
fee/e-learning enrollment -> ho_so, nhap_hoc, hoc_phi when fee signals exist
```

This is a semantic compatibility bridge; it does not rename or merge processed
JSON categories.

## 7. Retrieval Trace

### BM25

Post-fix hybrid audit returned enrollment hits from
`HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf`; relevant document records had BM25 ranks.

### Dense

The same audit returned dense ranks for the verified `ho_so` enrollment source.

### RRF

The final audit retained the same source with RRF scores. The expanded
enrollment retrieval passed 42 documents to evidence selection for the main
query.

## 8. Evidence Selection

Evidence selection now receives category-compatible enrollment documents. The
evidence-grounded response contains:

- Căn cước/Căn cước công dân;
- Học bạ THPT;
- thư mời nhập học bản chính hoặc Zalo confirmation;
- giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026;
- original-document/no-notarization note.

No enrollment fact was inserted into Python source.

## 9. Validator

The validator accepted the real answer with status `ok`, and the result retained
the official DHV source URL. No validator-only workaround was used.

## 10. Implementation

- Added enrollment category aliasing in query routing and direct retriever
  category inference.
- Added bounded admissions follow-up scope handling for topic-only state, so
  `còn phí thì sao?` and `cần nộp khi nào?` do not require a major/program slot.
- Kept external/mixed/ambiguous school boundaries authoritative; state cannot
  widen them into DHV retrieval.
- Added semantic schedule intent detection for “khi nào/bao giờ/thời gian +
  tuyển sinh”.
- Added evidence-grounded enrollment response handling and sufficient
  enrollment retrieval breadth.
- Added supplemental verified page-text chunks downstream of structured JSON.
- Rebuilt only the local/development Chroma collection from `data/processed`.

## 11. Files Changed

| File | Function/area | Reason |
|---|---|---|
| `src/chatbot/query_analysis.py` | intent rules, category routing, follow-up scope | bridge `ho_so`, preserve topic-only enrollment follow-up, recognize schedule queries |
| `src/retrieval/retriever.py` | category inference | normalize legacy `nhap_hoc` to `ho_so + nhap_hoc` |
| `src/chatbot/rag_chain.py` | retrieval/evidence/state path | retain enrollment evidence and prevent false no-data/model dependency |
| `src/chatbot/scope_guard.py` | admissions boundary keywords | keep enrollment-related terms in scope |
| `src/ingestion/structured_json.py` | downstream loader | preserve retrievable verified page text |
| `tests/test_runtime_enrollment.py` | regression coverage | category, evidence, follow-up and schedule tests |
| `tests/test_task_c.py` | existing taxonomy expectation | align route expectation with verified `ho_so` taxonomy bridge |
| `CHATBOT_RUNTIME_NODATA_FIX_REPORT.md` | handoff report | root cause, trace, tests and QA instructions |

RAW PDFs and extraction source files were not modified.

## 12. Chroma Rebuild

The command and final collection audit are recorded in section 4. The rebuild
used `data/processed -> verified/year=2026 loader -> splitter -> Ollama
embedding -> Chroma`, with the final collection containing 258 DHV-only verified
2026 chunks.

## 13. Runtime Query Matrix

Counts are `retrieval_calls / retrieved_docs_count`.

| Query | Intent | Category | Retrieval | Evidence | Status |
|---|---|---|---:|---:|---|
| `nhập học cần những gì` | HOI_NHAP_HOC | ho_so, nhap_hoc | 1 / 42 | 42 | PASS |
| `hồ sơ nhập học gồm những gì` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `nhập học cần giấy tờ gì` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `thủ tục nhập học như thế nào` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `tân sinh viên cần chuẩn bị gì` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `phí nhập học bao nhiêu` | HOI_NHAP_HOC | ho_so, nhap_hoc, hoc_phi | 1 / 43 | 43 | PASS |
| `học liệu điện tử bao nhiêu` | HOI_HOC_PHI | hoc_phi | 1 / 1 | 1 | PASS |
| `nhập học khi nào` | HOI_NHAP_HOC | ho_so, nhap_hoc | 1 / 42 | 42 | PASS |
| `cần làm gì để nhập học DHV` | HOI_NHAP_HOC | ho_so, nhap_hoc | 1 / 42 | 42 | PASS |
| `hồ sơ xét tuyển gồm những gì` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `DHV học phí bao nhiêu?` | HOI_HOC_PHI | hoc_phi | 1 / 1 | 1 | PASS |
| `Có học bổng nào?` | HOI_HOC_BONG | hoc_bong | 1 / 4 | 4 | PASS |
| `Hồ sơ xét tuyển cần gì?` | HOI_HO_SO | ho_so | 1 / 42 | 42 | PASS |
| `Khi nào tuyển sinh?` | HOI_LICH_TUYEN_SINH | lich_tuyen_sinh | 1 / 2 | 2 | PASS |
| `DHV xét tuyển bằng phương thức nào?` | HOI_PHUONG_THUC_XET_TUYEN | phuong_thuc_xet_tuyen | 1 / 1 | 1 | PASS |
| `Điểm chuẩn CNTT?` | HOI_DIEM_TRUNG_TUYEN | diem_trung_tuyen | 1 / 3 | 3 | PASS |
| `Điểm sàn là bao nhiêu?` | HOI_NGUONG_DAU_VAO | nganh_dao_tao, nguong_dau_vao | 1 / 4 | 4 | PASS |
| `DHV có những ngành nào?` | DANH_SACH_NGANH | nganh_dao_tao | 1 / 42 | 42 | PASS |
| `Có xét tuyển bổ sung không?` | HOI_XET_TUYEN_BO_SUNG | xet_tuyen_bo_sung | 1 / 4 | 4 | PASS |

The matrix was run against real local Ollama and Chroma.

## 14. Multi-turn

| Conversation | Result |
|---|---|
| `nhập học cần những gì` -> `còn phí thì sao?` | Stayed `in_scope_dhv`; second turn retrieved 1 fee document, had evidence and returned `ok`. |
| `hồ sơ nhập học gồm những gì` -> `cần nộp khi nào?` | Stayed `in_scope_dhv`; second turn retrieved 42 enrollment documents and returned `ok`. |
| `Điểm chuẩn CNTT` -> `nhập học cần gì?` | Enrollment route worked without stale CNTT narrowing the generic answer. |
| `Văn Hiến điểm chuẩn bao nhiêu?` -> `Còn DHV?` | Explicit DHV override worked and DHV retrieval was allowed. |

## 15. External/Scope Regression

| Query | Target/scope | Retrieval | Evidence | Result |
|---|---|---:|---:|---|
| `Điểm chuẩn Bách Khoa?` | OTHER_SCHOOL / external_school | 0 | 0 | PASS |
| `Điểm chuẩn trường đại học khác?` | OTHER_SCHOOL / external_school | 0 | 0 | PASS |
| `Giá vàng hôm nay?` | UNSPECIFIED / general_out_of_scope | 0 | 0 | PASS |
| `Trường có những ngành nào?` | UNSPECIFIED / in_scope_dhv | 1 | 42 | PASS |
| `Học phí DHV 2024?` | DHV / wrong year | 0 | 0 | PASS (`no_data`) |
| `Điểm chuẩn DHV 2026?` | DHV / in_scope_dhv | 1 | 4 | PASS |

The school boundary remains upstream of BM25, dense retrieval, RRF, evidence
selection and LLM generation.

## 16. Tests

| Suite | Passed | Failed | Skipped | Blocked |
|---|---:|---:|---:|---:|
| `tests/test_runtime_enrollment.py` | 6 | 0 | 0 | 0 |
| Targeted runtime/data suite: enrollment, Phase 2, Phase 4, Priority 1+2, data recovery | 44 | 0 | 0 | 0 |
| Intent classifier + Task F + Task C | 56 | 3 | 0 | 0 |
| Full `pytest -q` | 179 | 14 | 4 | 0 |
| `compileall` for `src/chatbot`, `src/ingestion` | PASS | 0 | 0 | 0 |
| Real Ollama + Chroma traces | PASS | 0 | 0 | 0 |

The three Task C failures were not hidden:

- two Windows temp-directory ACL cleanup failures (`WinError 5`), classified
  as `TEST_INFRA_FAILURE`;
- one existing threshold wording assertion expecting `từ 15 điểm` while the
  current validated answer is `15 điểm`.

Full-suite failure classification:

- 10 failures are the same Windows sandbox temp-directory ACL failure across
  ingestion, Task C temp fixtures and structured-JSON temp-output tests;
- 3 Task09 failures depend on the stale/missing school-PDF fixture filename;
- 1 failure is the Task C threshold wording assertion above.

These failures did not occur in the targeted runtime/no-data suite and were not
altered in this task.

## 17. Remaining Risks

- The verified corpus uses `ho_so` for enrollment; future manifests should keep
  the taxonomy contract explicit rather than relying only on the compatibility
  alias.
- Some source page continuation lines are short layout fragments, so schedule
  wording can be improved later by a bounded text-merge pass.
- `hồ sơ xét tuyển` currently reaches the verified enrollment document because
  the available 2026 verified corpus is enrollment-focused; review this if a
  separate verified application-file document is added.
- QA should rerun the ACL-sensitive Task C tests in a normal local Windows
  environment.

## 18. Acceptance Criteria

- [x] Processed JSON contains enrollment data.
- [x] Chroma freshness was verified.
- [x] Local Chroma was rebuilt from the canonical processed-data path.
- [x] 2024/unverified/wrong-school data is absent from the final collection.
- [x] `nhập học cần những gì` no longer returns false `no_data`.
- [x] Enrollment document, paper, procedure, fee and e-learning queries return evidence.
- [x] Tuition, scholarship, methods, scores, thresholds and majors still work.
- [x] External-school retrieval remains zero.
- [x] Wrong-year query does not leak 2026 data.
- [x] Evidence and source are official DHV data.
- [x] No factual enrollment answer is hard-coded.
- [x] Real Ollama + Chroma runtime was checked.

## 19. Handoff To QA

QA & Security should review the changed code and rerun:

1. the full enrollment matrix;
2. `nhập học cần những gì` -> `còn phí thì sao?`;
3. `hồ sơ nhập học gồm những gì` -> `cần nộp khi nào?`;
4. `Khi nào tuyển sinh?` and `bao giờ tuyển sinh?`;
5. Bách Khoa, generic external school, Văn Hiến and DHV control queries;
6. `Học phí DHV 2024?` for wrong-year isolation;
7. Chroma metadata audit for year, status, school, category and source URL;
8. ACL-sensitive Task C tests in a normal local Windows environment.

No deployment was performed. This is a Lead Coder handoff; QA retains final
PASS authority.

READY_FOR_QA
