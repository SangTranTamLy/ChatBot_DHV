# CHATBOT ADMISSION RUNTIME FIX REPORT

## 1. Scope

Continued the bounded runtime work for the seven current DHV admission PDFs:

- Improve routing for admission-scholarship condition questions.
- Keep generated answers grounded in the matching verified evidence.
- Prevent unsupported personalized major/program recommendations.
- Preserve safe, narrow retrieval for multi-intent subplans.
- Do not deploy, edit the PDFs or processed JSON, modify evaluation Q&A, or rebuild Chroma.

## 2. Processed Data and Chroma Verification

All seven manifest PDFs have a processed JSON with the same page count, and each JSON `source_sha256` matches the current RAW PDF hash:

| PDF | PDF pages | JSON pages | JSON records | Raw hash matches |
|---|---:|---:|---:|---|
| V1_DIEM_TRUNG_TUYEN_DHV_2026.pdf | 2 | 2 | 69 | Yes |
| V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf | 7 | 7 | 10 | Yes |
| V1_HOC_PHI_DHV_2024.pdf | 1 | 1 | 1 | Yes |
| V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf | 8 | 8 | 94 | Yes |
| V1_THONG_TIN_TRUONG_DHV.pdf | 7 | 7 | 1 | Yes |
| V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf | 7 | 7 | 32 | Yes |
| V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf | 2 | 2 | 24 | Yes |

Active Chroma was inspected read-only:

- Collection: `dhv_admissions_2026`
- Records: 281
- Years: 2026 only
- Status: verified only
- School: DHV only
- Source hashes: the six verified 2026 processed PDFs match the six active Chroma source hashes.
- The 2024 tuition PDF is not in active Chroma because its manifest entry has `missing_source_url` and `verified=false`; it is not eligible for the verified corpus under the current gate. No DB rebuild was done.

Page count/hash equality confirms source freshness and page preservation; it does not by itself prove every semantic record is correct.

## 3. Confirmed Runtime Root Causes

1. Admission-scholarship conditions were retrieved through broad scholarship categories. Relevant page text could fall outside the evidence context budget, while unrelated records consumed the selection window.
2. Personal-fit questions could reach generation without a verified evidence relation that explicitly supports the requested fit claim.
3. Multi-intent scholarship subplans searched `hoc_bong` without consistently reaching the verified policy page stored under `phuong_thuc_xet_tuyen`; this produced a false `no_data` result despite corpus evidence.
4. The multi-intent root result reported `status=ok` when only some subplans were answerable, without a stable explicit partial-completion field.
5. A THPT follow-up phrased as “xét điểm như nào” was classified as method presence rather than score calculation. Once classified, the default top-k also omitted the method-description anchor, and the direct calculator only handled the học-bạ case.
6. After adding the scholarship source category to multi-issue plans, the scholarship subplan still inherited the root query's major/program entity filters. The retriever then excluded verified school-wide policy chunks that do not repeat the named major, leaving a program catalogue row as the only selected evidence.
7. The same major/program filter defect also affected ordinary single-intent scholarship questions such as `CNTT có học bổng gì?`; additionally, `học bổng gì` was left in `SINGLE_FACT`, so the deterministic catalogue renderer did not activate and the unrelated result could reach the LLM.

## 4. Implementation

- Added a semantic route for admission-scholarship condition questions to include the verified admission-method source category.
- Prioritized the verified page-text section for the admission-scholarship policy and rendered its conditions from evidence only when the complete section is present. The deterministic response does not call the LLM for this fact pattern.
- Kept standalone broad scholarship questions on their broader source categories, but marked decomposed multi-issue subplans so they use only their own relevant category unless the subplan itself asks for admission-scholarship conditions.
- Multi-issue scholarship routing now includes `phuong_thuc_xet_tuyen` alongside `hoc_bong`, while excluding unrelated `ho_so`; standalone broad scholarship routing remains unchanged.
- For a multi-issue scholarship subplan, retrieval now omits major/program entity filters while preserving those entities in the answer-analysis context. Selected scholarship documents are policy-prioritized, and the subplan tries the deterministic evidence-backed scholarship catalogue renderer before generation. This prevents a major/program table from becoming the scholarship answer.
- The same entity-filter relaxation is now part of ordinary `HOI_HOC_BONG` routing, so single- and multi-intent behavior match. Phrases such as `học bổng gì/nào` and `các/những học bổng` set `query_mode=LIST`. Scholarship evidence selection rejects intent-mismatched chunks and a mixed page that contains the full major/program/code table headers; the policy list therefore cannot be derived from an unrelated catalogue row or passed as sole LLM context.
- Multi-issue responses now expose `partial` at the response root and expose `complete`, `partial`, and ordered `subplan_statuses` in the trace. This keeps the existing `status` enum compatible while making missing subanswers observable.
- THPT calculation paraphrases now route to `HOI_CACH_TINH_DIEM` and the verified `phuong_thuc_xet_tuyen` source. A bounded top-k of 16 is used for named THPT formula lookups so the page text explaining the method is not dropped by the default retrieval window.
- The THPT formula answer is assembled from verified method details (three-subject total and both published subject structures). If matching evidence is absent, the request fails closed instead of letting the LLM fill the gap. Graduation-year-only statements are not treated as a named THPT method.
- Added/used a verified-evidence gate for personalized-fit claims. Without a direct, current-year, verified DHV evidence relation, the path returns a clarification/evidence-grounded response before LLM generation.
- Hardened validator fallback recognition so generic “not in evidence/data” text cannot be accepted as a factual success solely through token overlap.

No answer facts were copied into Python as static data. The scholarship answer is built from the verified evidence section.

## 5. Files Changed

| File | Function/area | Reason |
|---|---|---|
| `src/chatbot/query_analysis.py` | Scholarship routing and multi-issue subplan metadata | Restrict retrieval categories to the requested topic while preserving the standalone broad-scholarship path. |
| `src/chatbot/evidence.py` | Intent-aware scholarship evidence filtering | Reject non-scholarship content and mixed catalogue pages with the full major/program/code table header before evidence is passed downstream. |
| `src/chatbot/rag_chain.py` | Scholarship evidence prioritization/answering and advisory evidence gate | Keep the complete verified policy section in context and fail closed on unsupported personal-fit claims. |
| `src/chatbot/output_validator.py` | Fallback and advisory-fit validation | Reject unsupported model fallback/advisory output as a successful factual answer. |
| `tests/test_admission_conditions.py` | Admission/advisory regressions | Verify evidence-bound output and unsupported-fit rejection. |
| `tests/test_intent_classifier.py` | Advisory route behavior | Assert the unsupported-fit path does not call generation. |
| `tests/test_task_f.py` | Evidence-backed advisory behavior | Cover current-year/source/school evidence requirements. |
| `tests/test_task_response_ui.py` | Scholarship policy response | Verify the complete evidence-backed policy is returned without generation. |
| `tests/test_full_sweep_p1.py` | Broad scholarship and multi-intent regression | Keep standalone scholarship behavior while checking the full source context. |
| `tests/test_task_i.py` | Multi-issue category plan | Assert isolated scholarship category routing. |
| `tests/test_task_f.py` | Processed-corpus multi-intent runtime regression | Assert scholarship docs/evidence/status, narrow categories, and explicit partial result. |
| `tests/test_data_pipeline_recovery.py` | Tuition manifest fixture paths | Resolve the current PDF/JSON path from canonical manifest document identity rather than a stale filename. |
| `tests/test_admission_conditions.py` | THPT formula paraphrases | Assert calculation intent, method entity and verified-source routing for natural variants. |
| `tests/test_task_f.py` | Two-turn method/formula replay | Reproduce the screenshot-like follow-up with processed-corpus retrieval and assert answer, evidence, official source and zero LLM prompts. |

## 6. Runtime/Test Traces

### Admission-scholarship conditions

- Query: `Điều kiện nhận học bổng tuyển sinh`
- Intent: `HOI_HOC_BONG`
- Route categories: `hoc_bong`, `phuong_thuc_xet_tuyen`
- Verified source section: admission scholarship section from the 2026 method/scholarship PDF
- Answer: rendered from the complete matching evidence section; includes the available method conditions
- LLM calls: 0 on the deterministic evidence-backed branch
- Status: `ok` in the targeted fixture-backed runtime test

### Two-turn THPT score calculation (processed-corpus replay)

- Turn 1: `trường có bao nhiêu phương thức xét, và hãy liệt kê chi tiết về những phương thức xét tuyển đấy`
  - Intent: `HOI_PHUONG_THUC_XET_TUYEN`; status `ok`; the deterministic answer lists five methods.
- Turn 2: `xét kết quả kỳ thi tốt nghiệp THPT thì xét điểm như nào`
  - Intent: `HOI_CACH_TINH_DIEM`; method `thpt`; category `phuong_thuc_xet_tuyen`.
  - Retrieval calls: 1; retrieved documents > 0; selected evidence > 0; final status `ok`.
  - The evidence-grounded response includes the 3-subject total and both source-published subject structures. The regression asserts the official source and no LLM prompt. This is processed-corpus replay, not live Ollama/active-Chroma E2E.

### Standalone scholarship vs. multi-issue scholarship

- Standalone `DHV có những học bổng nào?`: retains the broad scholarship sources needed for a catalog answer.
- Scholarship subplan inside a combined tuition/scholarship/program query: uses the narrow scholarship category, not unrelated `ho_so` retrieval.
- Query `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?`: scholarship subplan categories are `hoc_bong` + `phuong_thuc_xet_tuyen`, excluding `ho_so`; it retrieves documents and evidence, has `status=ok`, and contributes scholarship content.
- After the multi-issue scholarship fix, the same processed-corpus replay reports root retrieval calls/docs/evidence `3/62/15`; subplan docs are `[0, 58, 4]`, evidence `[0, 13, 2]`, statuses `[no_data, ok, ok]`. The scholarship subplan's effective major/program `entity_filters` are empty. Its answer lists eight headings extracted from verified page-text evidence, contains no catalogue row (`TÊN NGÀNH` / `Công nghệ phần mềm` absent), and makes zero LLM calls. This is a corpus-backed test runtime, not live Chroma/Ollama E2E.
- Single-intent `CNTT có học bổng gì?` now resolves to `HOI_HOC_BONG`, `query_mode=LIST`, scholarship retrieval categories, and empty major/program filters. Processed-corpus replay: **1 call / 70 retrieved docs / 55 selected evidence chunks**, final `status=ok`; deterministic output lists the eight verified policy headings, contains no `TÊN NGÀNH` or CNTT program table, and invokes the mock LLM **0** times. This confirms catalogue content is rendered from scholarship policy evidence, not generated from the program table.
- The unsupported fee subplan remains `no_data`; root status stays API-compatible as `ok` because other sections are answerable, but root `partial=true` and trace reports `complete=false`, `partial=true`, `subplan_statuses=[no_data, ok, ok]`.
- The dedicated processed-corpus runtime regression passes.

### Unsupported personal-fit recommendation

- If corpus evidence does not explicitly connect the student’s stated interest/criteria to a named major/program, the system does not let the LLM invent a recommendation.
- Direct evidence-contract tests passed for verified/current-year/DHV positive evidence and negative, unverified, wrong-year, and wrong-school cases.

### Live runtime

Live Ollama was not available. `ollama list` failed to connect to `127.0.0.1:11434` with Windows socket permission error. Therefore production embedding/retriever + Qwen E2E is **BLOCKED**, not passed. No mock result is presented as live E2E.

## 7. Tests

| Test run | Result |
|---|---|
| Scholarship deterministic policy regressions | 2 passed; single- and multi-intent content/evidence/filter/zero-LLM assertions |
| Focused runtime/security/advisory/data-manifest regressions (Lead, latest) | 229 passed, 5 known program-parent subcases failed, 250 subtests passed |
| Independent QA targeted review (latest) | 199 passed, 5 known program-parent subcases failed, 232 subtests passed |
| Independent scholarship-specific QA regressions | 2 passed (single-intent + multi-intent) |
| Current manifest-based data recovery tests | 5 passed |
| Latest full pytest with isolated `.test_tmp\lead_recheck` | 346 passed, 10 failed, 4 skipped, 327 subtests passed |

The prior Windows temporary-directory ACL failures did not recur when the full suite used `.test_tmp`.

## 8. Remaining Full-Suite Failures

- Five program-parent subtests plus three catalog tests disagree with the current verified catalog: runtime evidence yields 50 program relations while older expectations assume 47. The PDF table’s line-broken entries include `Ngôn ngữ` / `Văn hóa Nhật Bản`, `Tiếng Trung văn hóa` / `Du lịch`, and `Tâm lý tổ chức` / `Nhân sự`. The page-table text is preserved, but deciding whether/how to combine these labels requires source-owner confirmation; no hyphen or merged title was invented.
- One PDF audit test sees literal `\\n` sequences in two extracted table headers where it expects spaces.
- One PDF score-table test expects `header_inherited` on a continued table, but the current extraction output does not set that field.

The two stale tuition fixture-path failures are fixed by resolving the current file paths from the canonical manifest `document_id`; the corresponding recovery suite passes (5 tests). An independent source audit in `reports/PROGRAM_CATALOG_SOURCE_AUDIT.md` confirms the current tests include two misspelled/truncated program names and three proposed hyphenated names that are not explicit in the PDF. The official exact catalog count/name boundary remains unresolved; no source-owner decision or test expectation was fabricated.

These are not silently waived. The PDF/table findings affect catalog/data completeness and need QA/source-owner review; this task did not modify extraction code or processed data.

## 9. Scope and Data Safety Regressions

The full suite completed with no reported failure in the existing external-school/scope guard tests. The active collection was not modified. The unverified 2024 tuition document remains excluded rather than being presented as verified 2026 evidence.

## 10. Remaining Plan Gaps and Risks

- A separately invoked LLM pre-RAG decomposition stage and a wholesale prompt redesign were not introduced in this bounded fix. Current safety-critical school/year/entity routing remains deterministic and upstream of retrieval; multi-intent decomposition remains the existing planner path.
- Live Ollama E2E has not been verified because of the socket restriction.
- The structured program catalog has unresolved line-break semantics; do not claim the 47/50 count is QA-approved until resolved against the source owner.
- Independent QA initially found program-table leakage in multi-intent scholarship and then in single-intent `CNTT có học bổng gì?`. The latest working tree fixes both: QA confirms policy evidence is selected, catalogue chunks are filtered, the answer is deterministic, and zero LLM calls occur in both cases.
- The 2024 tuition source is present in processed JSON but unverified and absent from Chroma due missing official provenance.

## 11. Acceptance Criteria

| Criterion | Result |
|---|---|
| Current seven PDF page counts match their JSON page counts | PASS |
| Current processed JSON hashes match the seven RAW PDFs | PASS |
| Active Chroma matches all six eligible verified 2026 JSON source hashes | PASS |
| 2024 unverified tuition is excluded from the active verified collection | PASS |
| Admission-scholarship conditions use the matching verified evidence and avoid generic no-data | PASS in targeted fixture-backed runtime test |
| Scholarship multi-intent route avoids unrelated categories | PASS in targeted regression |
| Multi-intent scholarship reaches the verified policy category and returns evidence | PASS in processed-corpus runtime regression |
| Single-intent `CNTT có học bổng gì?` avoids program catalogue and returns policy headings | PASS — independent QA: 1/70/55 call/docs/evidence; zero LLM calls |
| Multi-intent scholarship avoids program catalogue and retains policy evidence | PASS — independent QA: scholarship subplan 1/58/16 call/docs/evidence; zero LLM calls |
| Partial multi-intent completion is explicitly represented | PASS (`partial` response field and trace status list) |
| THPT score-calculation paraphrases use the method evidence and answer both published structures | PASS in two-turn processed-corpus replay; live model remains untested |
| Unsupported personal-fit claims are blocked absent direct verified evidence | PASS in unit/evidence-contract tests |
| Standalone broad scholarship answer retains its broader source route | PASS in targeted regression |
| Full pytest clean | FAIL — 10 failures: 5 parent-mapping subcases, 3 catalog-count tests, 2 structured-JSON table tests |
| Live Ollama + Chroma E2E | BLOCKED — Windows socket permission error |
| Program catalog semantics proven identical to PDF | BLOCKED — line-break ambiguity remains |

## 12. Handoff to QA & Security

Carver completed a second read-only review of the single- and multi-intent scholarship fix and updated `reports/QA_POST_ADMISSION_RUNTIME_FIX_REVIEW.md` with exact traces, filtered-evidence reasons, targeted counts and verdict. QA confirms the two scholarship cases pass. Locke completed the source audit at `reports/PROGRAM_CATALOG_SOURCE_AUDIT.md`. Live Ollama remains `BLOCKED` unless the local socket becomes available.

## 13. Lead Verdict

**BLOCKED** — the scholarship single- and multi-intent fixes passed independent QA, but the targeted suite is not clean because five program-parent mappings still fail. Latest Lead full pytest: 346 passed, 10 failed, 4 skipped, 327 subtests; the ten failures are the known program-catalog/source-boundary and structured-table groups. Ollama/active-Chroma E2E remains blocked by the Windows socket permission error. No deployment was performed.
