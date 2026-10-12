# QA & SECURITY – INDEPENDENT FULL-SWEEP P1 REVIEW

## 1. Scope

Independent retest after `reports/FULL_SWEEP_P1_FIX_REPORT.md`.

Executed all 120 original `result=FAIL` IDs and all 500 rows in `data/evaluation/qa_master_500.jsonl` through the real `ask_chatbot` path. Reviewed the scope guard, query analysis, year semantics, RAG chain, retriever, evidence/validator/planner paths, related tests, and the four full-pytest failures named by Lead Coder.

QA did not modify source code, datasets, expected answers, Chroma, model configuration, or deployment artifacts.

## 2. Executive Summary

**Overall status: FAIL**  
**Final verdict: `FULL_SWEEP_P1_INDEPENDENT_FAIL`**

Ollama and Chroma were available, therefore this is not an environment block. All 500 runtime calls completed, but factual correctness is not established.

Confirmed high-impact findings:

- UQ0007 still returns `no_data` although the analysis year is 2026 and the trace has four verified 2026 chunks. The validator records `year_mismatch`.
- UQ0010 answers an admission-threshold question instead of the requested basic eligibility condition.
- UQ0339 omits the Ministry admission system and official admissions website, returning only letter/Zalo/document evidence.
- 61 additional `status=ok` rows were independently confirmed as semantically wrong, incomplete, contradictory, or answering a different question.
- Multi-turn tuition, school override, and full-list coreference regressions remain.
- The wrong program-major relation is still accepted as `ok` by Task F.
- Full pytest still has four failures.

No new CRITICAL secret leak or external-school DHV factual leakage was observed in the adversarial matrix. HIGH functional issues remain; P1 is not closed.

## 3. Reports and Code Reviewed

Reports:

- `reports/TONG_QUAN_AGENT`
- `reports/FULL_SWEEP_P1_FIX_REPORT.md`
- task context under `ChatBot_DHV_Agent_Tasks_V2/`

Key code:

- `src/chatbot/scope_guard.py`
- `src/chatbot/query_analysis.py`
- `src/chatbot/year_semantics.py`
- `src/chatbot/rag_chain.py`
- `src/chatbot/retriever.py`
- related evidence, output-validator, planner and deterministic-score modules

Tests:

- P1/full-sweep tests, `tests/test_priority_1_2_fix.py`, Task C/F/G/I/J/K/L/N, UI contract tests, and full pytest collection.

## 4. Runtime Environment

| Item | Observed |
|---|---|
| LLM | Ollama `qwen2.5:3b`, available |
| Embedding | Ollama `nomic-embed-text`, available |
| Chroma | `dhv_admissions_2026`, 270 active records |
| Target year | 2026 |
| Retrieval | BM25 + dense + RRF |
| Runtime errors | 0/500 |
| Average / median / p95 / max | 3442.41 / 2171.90 / 7107.49 / 19873.99 ms |

The Lead report used a 310-record staging collection. This retest used the configured active 270-record collection; different status counts are therefore material and are reported as a runtime/report mismatch.

## 5. Sweep Completeness and Artifacts

| Set | Executed | Result |
|---|---:|---|
| Original FAIL IDs | 120/120 | complete; no environment block |
| Canonical active set | 500/500 | complete; no runtime error |

The canonical field is `reference_answer`. The 237 rows with `source="Tự làm"` were not treated as verified evidence; they are evaluation references only.

Artifacts:

- [500-row results](C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\reports\QA_FULL_QUESTION_SWEEP_INDEPENDENT_RESULTS.jsonl)
- [120-row P1 results](C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\reports\QA_FULL_SWEEP_P1_INDEPENDENT_120_RESULTS.jsonl)
- [failure and non-pass records](C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\reports\QA_FULL_QUESTION_SWEEP_INDEPENDENT_FAILURES.jsonl)

## 6. Runtime Summary

### 500/500

| Status | Count | Interpretation |
|---|---:|---|
| `ok` | 319 | not automatic QA PASS; answer/evidence must be adjudicated |
| `no_data` | 75 | not PASS where relevant verified evidence exists |
| `out_of_scope` | 105 | contract boundary unless it is approved admissions content |
| `clarification` | 1 | review required; may be correct for ambiguity |

Modes: `SINGLE_FACT=422`, `COUNT=47`, `LIST=30`, `LIST_AND_COUNT=1`.

### 120 original FAIL IDs

| Status | Count |
|---|---:|
| `ok` | 45 |
| `no_data` | 12 |
| `out_of_scope` | 63 |
| runtime error/offline | 0 |

The Lead distribution `52 ok / 4 no_data / 63 out_of_scope / 1 ollama_offline` was not reproduced on the active collection. It is historical evidence only.

## 7. Focused P1 Findings

### UQ0007 — year 2026

- Input: `Nếu thí sinh có bằng tốt nghiệp THPT từ năm 2025 trở về trước, có được tham gia xét tuyển năm 2026 không?`
- Expected: a Vietnamese high-school graduate or equivalent may apply.
- Actual: fixed `no_data` answer.
- Trace: `year=2026`, intent `HOI_DANG_KY_XET_TUYEN`, retrieval 1, four retrieved/evidence chunks; chunks show `year=2026`, `status=verified`.
- Validator: `year_mismatch`; planner: `NO_DATA`.
- Severity: **HIGH**. Codes: `FALSE_NO_DATA`, `WRONG_YEAR`.
- Failed criterion: matching 2026 evidence must not be discarded.

This is a report/runtime mismatch: Lead says the final row was `ok`; current active runtime is `no_data`.

### UQ0339 — notification channel

- Input: `khi trúng tuyển thì trường sẽ thông báo vào đâu ạ?`
- Expected: Ministry common admissions system, official DHV admissions website, and the letter/Zalo/registered contact channel.
- Actual: only admission-document and letter/Zalo content is returned.
- Evidence: 32 retrieved and 32 selected chunks from official DHV sources, but the required channels are not all represented in the final answer.
- Severity: **HIGH**. Code: `LLM_PARTIAL_ANSWER` / evidence-planner incompleteness.
- Failed criterion: procedural factual answer must include all required channels supported by evidence.

### UQ0010 — basic eligibility

- Input: `Muốn xét tuyển vào trường đại học Hùng Vương Tp.Hồ Chí Minh thì điều kiện cơ bản là gì?`
- Expected: graduated THPT or equivalent under Ministry rules.
- Actual: answer discusses missing thresholds and redirects to hotline/fanpage.
- Trace: four verified chunks, validator `ok`, planner `STEP_BY_STEP`; the historical Ollama timeout was not reproduced.
- Severity: **HIGH**. Codes: `WRONG_INTENT`, `UNSUPPORTED_ANSWER`.

### Specified no-data rows

| ID | Expected fact | Current result | Trace | Severity |
|---|---|---:|---:|---|
| UQ0160 | IATAI offers AI at undergraduate level | `no_data` | 4 retrieved / 2 evidence | MEDIUM |
| UQ0236 | Học viện Hạnh phúc Việt Nam, 19/06/2026 | `no_data` | 8 / 8 | MEDIUM |
| UQ0327 | six-enterprise event opportunities | `no_data` | 8 / 8 | MEDIUM |
| UQ0378 | Marketing market-research knowledge | `no_data` | 4 / 2 | MEDIUM |

These are not accepted as PASS. They indicate verified-corpus coverage or evidence-planner gaps. Additional evidence-present no-data rows include UQ0009, UQ0074, UQ0076, UQ0085 and UQ0089.

## 8. External, Mixed and Ambiguous School Safety

Adversarial matrix results:

- Bách Khoa, unaccented Bách Khoa, Bách Khoa TP.HCM, Văn Hiến, Hoa Sen, Văn Lang, Nguyễn Tất Thành and generic “trường đại học khác”: `OTHER_SCHOOL`, retrieval 0, evidence 0.
- `So sánh DHV và Văn Hiến`: `MIXED`, retrieval 0, evidence 0.
- bare `Hùng Vương`: ambiguous/clarification, retrieval 0.
- explicit `DHV CNTT`: DHV retrieval allowed.
- unspecified `CNTT` and generic `Trường có những ngành nào?`: DHV default retrieval allowed.

No DHV factual value leaked in this matrix. SEC-001 safety criteria pass for these cases.

The 63 original out-of-scope IDs were all rerun and classified as contract-boundary content (IATAI/labs/events/research/student-life/career), not approved admissions questions incorrectly blocked. All had retrieval 0/evidence 0:

`UQ0108,UQ0150,UQ0189,UQ0209,UQ0231,UQ0245,UQ0246,UQ0248,UQ0249,UQ0250,UQ0254,UQ0256,UQ0258,UQ0261,UQ0262,UQ0264,UQ0265,UQ0267,UQ0268,UQ0269,UQ0271,UQ0272,UQ0274,UQ0275,UQ0280,UQ0281,UQ0282,UQ0284,UQ0292,UQ0296,UQ0297,UQ0300,UQ0302,UQ0305,UQ0329,UQ0330,UQ0331,UQ0332,UQ0333,UQ0336,UQ0341,UQ0343,UQ0344,UQ0345,UQ0346,UQ0347,UQ0349,UQ0363,UQ0367,UQ0372,UQ0389,UQ0393,UQ0415,UQ0419,UQ0441,UQ0442,UQ0445,UQ0453,UQ0455,UQ0456,UQ0467,UQ0471,UQ0497`.

## 9. Count/List and Deterministic Findings

The small matrix passed method count/list (`5`, five unique methods), count-plus-list, major count (`20`) and generic DHV default. The full sweep still found failures:

- UQ0006 asks for a minimum score and gets the number of methods.
- UQ0134 asks for 12 supplementary majors and gets one.
- UQ0214/UQ0215/UQ0216 ask subgroup counts and get overall count 20.
- UQ0328 asks per-credit tuition and gets the 10-credit total 12,500,000.
- UQ0040 answers a conditional English-test fee as an unconditional total.
- UQ0068 returns 13/08/2026 where the expected intake start is 11/08/2026.
- UQ0104/UQ0105 return general thresholds instead of Psychology-specific values.

Failure codes: `COUNT_WRONG`, `LIST_INCOMPLETE`, `WRONG_NUMERIC_FACT`, `WRONG_DATE`, `WRONG_INTENT`.

## 10. Multi-turn State and Coreference

Observed regressions:

1. `Điểm chuẩn CNTT?` → `Còn học phí?`: CNTT is retained, but tuition retrieval is over-filtered and returns no data.
2. `Điểm chuẩn CNTT?` → `Học phí DHV hiện nay?`: explicit generic DHV correctly avoids stale major.
3. `Văn Hiến có xét học bạ không?` → `Còn điểm chuẩn?`: external state is retained; retrieval/evidence remain zero.
4. `Văn Hiến có xét học bạ không?` → `Còn DHV thì sao?`: DHV retrieval is allowed, but stale `current_method=hoc_ba` remains and only 4/5 methods are returned.
5. Full list of 20 majors → `Điểm sàn các ngành nêu trên?`: only eight candidates are carried into the follow-up and it returns no data.
6. `CNTT có những chương trình nào?` → `Chương trình thứ hai học gì?`: resolves `Lập trình AI` correctly; isolated ordinal case passes.
7. factual → greeting and external → thanks: no retrieval and no factual leakage in the current turn.

Failures:

- `STATE-RET-001`, HIGH: over-inherited major causes valid tuition follow-up no-data.
- `STATE-OVERRIDE-001`, HIGH: explicit DHV override leaves stale method/list context.
- `CORE-001-RET`, HIGH: full-list coreference truncates the previous list.

## 11. Confirmed Semantic Failures with Runtime `ok`

61 rows were confirmed from the current answer and trace as wrong, incomplete, contradictory or answering a different question. The full records are in the failure artifact:

`UQ0001,UQ0006,UQ0010,UQ0016,UQ0017,UQ0024,UQ0025,UQ0027,UQ0028,UQ0032,UQ0033,UQ0034,UQ0040,UQ0049,UQ0054,UQ0057,UQ0061,UQ0063,UQ0067,UQ0068,UQ0070,UQ0075,UQ0078,UQ0080,UQ0081,UQ0090,UQ0096,UQ0098,UQ0100,UQ0104,UQ0105,UQ0133,UQ0134,UQ0147,UQ0148,UQ0151,UQ0156,UQ0158,UQ0174,UQ0176,UQ0177,UQ0179,UQ0180,UQ0204,UQ0205,UQ0214,UQ0215,UQ0216,UQ0217,UQ0218,UQ0240,UQ0241,UQ0242,UQ0306,UQ0310,UQ0311,UQ0313,UQ0321,UQ0326,UQ0328,UQ0339`.

Examples:

| ID | Expected | Actual | Severity |
|---|---|---|---|
| UQ0061 | certificate is required at intake | says it is not required | HIGH |
| UQ0068 | intake starts 11/08/2026 | says 13/08/2026 | HIGH |
| UQ0134 | list 12 supplementary majors | lists one | HIGH |
| UQ0205 | maximum scholarship amount/condition | returns number of scholarship types | HIGH |
| UQ0321 | scholarship rule based on three-subject score | adds unsupported `75 tỷ` and misses the rule | HIGH |
| UQ0328 | per-credit tuition | returns 10-credit total | HIGH |
| UQ0339 | Ministry + website + letter/Zalo | only letter/Zalo/document evidence | HIGH |

## 12. Regression Suites

### Targeted Phase 2/4 group

`142 passed, 1 failed, 197 subtests passed`.

Failure: `tests/test_task_f.py::TaskFGenerationTests::test_wrong_program_major_code_is_rejected`; expected `no_data`, actual `ok` for a wrong program/major relation. Severity HIGH.

### Full pytest

`236 passed, 4 skipped, 4 failed, 275 subtests passed`.

Failures:

1. `tests/test_ingestion.py::IngestionTests::test_build_persists_chroma_and_smoke_query_keeps_source_metadata`: `DuplicateIDError`; deterministic chunk IDs collide across distinct documents. HIGH data-integrity/reproducibility risk.
2. `tests/test_task_f.py::TaskFGenerationTests::test_wrong_program_major_code_is_rejected`: wrong parent relation accepted as `ok`. HIGH.
3. `tests/test_task_m.py::TaskMRawDataTests::test_raw_pdfs_have_official_urls_and_no_form_submission_data`: URL predicate fails for `data/raw/thong_tin_truong/Thong_Tin_Truong.pdf` although manifest marks it verified. MEDIUM/HIGH provenance issue.
4. `tests/test_task_processed_md_to_json_migration.py::ProcessedJSONMigrationTests::test_loader_reads_canonical_json_only`: expected `skipped_unverified=2`, loader returns 1. MEDIUM contract mismatch.

Current fresh `tests/test_task_c.py` alone passes (`19 passed`, `12 subtests passed`); that does not override the full regression failure.

## 13. Security Regression

Passes observed: external retrieval/evidence boundary; non-accent external-school detection; wrong-year smoke behavior; explicit/unspecified DHV behavior; no new hard-coded secret in reviewed P1 files; no new `eval`, `exec`, `shell=True`, unsafe pickle or command-execution path in reviewed P1 files; sequential execution only.

Security result: no new CRITICAL blocker found. Admissions factual errors remain HIGH risk.

## 14. Report/Code/Runtime Mismatches

| Claim | Independent result |
|---|---|
| UQ0007 ended `ok` in Lead report | Active runtime returns `no_data`, validator `year_mismatch` |
| only four no-data rows remain | Current 120 rerun has 12 no-data rows |
| `status=ok` is usable | UQ0010, UQ0061, UQ0068, UQ0134, UQ0328 and UQ0339 disprove this |
| validator defense is complete | Task F wrong parent relation still accepted |
| staging and active sweep are interchangeable | 310-record staging and 270-record active collection produce different distributions |

## 15. Handoff to Lead Coder

### Priority 1

- **BUG-P1-001** — Fix UQ0007 2026 evidence rejection. Acceptance: grounded answer, no `year_mismatch`; rerun multi-year variants.
- **BUG-P1-002** — Fix eligibility routing for UQ0010. Acceptance: graduation/equivalent condition, not threshold fallback.
- **BUG-P1-003** — Fix UQ0339 completeness. Acceptance: Ministry system + official website + letter/Zalo channels when supported.
- **BUG-P1-004** — Fix confirmed wrong numeric/date/count/list answers, including UQ0061, UQ0068, UQ0134, UQ0205, UQ0321 and UQ0328.

### Priority 2

- **BUG-P2-001** — Tuition follow-up over-inherits major; preserve applicable context without blocking general tuition retrieval.
- **BUG-P2-002** — Explicit DHV override must clear incompatible external/method state.
- **BUG-P2-003** — Preserve the complete previous list for “các ngành nêu trên”, or clarify instead of truncating.
- **BUG-P2-004** — Validator must reject wrong program-parent mapping.

### Priority 3 / data and infrastructure

- **BUG-P3-001** — DATA_REVIEW verified coverage for UQ0160/UQ0236/UQ0327/UQ0378 and evidence-present no-data rows.
- **BUG-P3-002** — Resolve duplicate deterministic Chroma IDs in ingestion.
- **BUG-P3-003** — Resolve official-URL manifest mismatch and processed JSON skipped-unverified accounting.

## 16. Acceptance Criteria

| Criterion | Result |
|---|---|
| 120 original FAIL IDs rerun | PASS: 120/120 |
| 500/500 runtime sweep completed | PASS: 500/500 |
| Ollama/Chroma available | PASS |
| UQ0007 grounded 2026 answer | **FAIL** |
| UQ0339 complete answer | **FAIL** |
| UQ0010 correct eligibility answer | **FAIL** |
| Four specified no-data rows proven correct | **FAIL / NOT PASS** |
| 63 original out-of-scope safely blocked | PASS as contract boundary |
| External/mixed/ambiguous retrieval zero | PASS in adversarial matrix |
| Generic DHV default preserved | PASS in adversarial matrix |
| Count/list consistency | **FAIL** |
| Multi-turn state/coreference | **FAIL** |
| Validator rejects wrong parent relation | **FAIL** |
| Targeted Phase 2/4 tests | **FAIL**: 1 failed |
| Full pytest | **FAIL**: 4 failed |
| No unresolved HIGH issue | **FAIL** |

## 17. Final Verdict

**`FULL_SWEEP_P1_INDEPENDENT_FAIL`**

The complete runtime sweep executed successfully, but the current patch still produces wrong or incomplete factual answers, no-data with relevant evidence, state/coreference regressions, and a validator regression. Do not deploy. Lead Coder handoff is required before retest.
