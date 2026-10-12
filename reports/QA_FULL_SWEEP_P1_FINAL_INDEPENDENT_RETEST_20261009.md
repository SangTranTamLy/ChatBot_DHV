# QA & SECURITY – FULL-SWEEP P1 FINAL INDEPENDENT RETEST

## 1. Scope and restrictions

Independent QA retest of the final Lead Coder state on 2026-10-09.

- Read `reports/TONG_QUAN_AGENT`, `reports/FULL_SWEEP_P1_FIX_REPORT.md`, and the Lead rerun `reports/FULL_SWEEP_P1_120_LEAD_RERUN_20261009_V6.jsonl`.
- Reviewed `scope_guard.py`, `query_analysis.py`, `year_semantics.py`, `rag_chain.py`, `retriever.py`, evidence/validator/planner paths, and related tests.
- Reran all 120 rows independently through the real `ask_chatbot` path.
- Reran the canonical 500-row sweep sequentially through Ollama and Chroma.
- Did not modify source code, canonical data, expected answers, Chroma, model configuration, or deployment state.
- `source="Tự làm"` was not treated as verified evidence.

## 2. Final verdict

**`FULL_SWEEP_P1_FINAL_QA_FAIL`**

The final patch closes several previous factual failures and the single-turn/multi-turn external-school boundary passes when the returned conversation state is passed back correctly. It does not pass independent QA because four specified no-data rows remain, one scholarship answer is incomplete, an unsupported recommendation is still generated, and full pytest still has three failures.

No deployment is authorized.

## 3. Runtime environment and collection verification

| Item | Observed |
|---|---|
| LLM | Ollama `qwen2.5:3b`, available through localhost |
| Embedding | Ollama `nomic-embed-text`, available |
| Chroma collection | `dhv_admissions_2026` |
| Active Chroma records | **310** |
| Target year | 2026 |
| Retrieval | BM25 + dense + RRF |
| 120-row independent runtime errors | 0 |
| 120 latency avg / median / p95 / max | 1205.78 / 5.05 / 2306.63 / 9708.49 ms |
| 500 latency avg / median / p95 / max | 3835.02 / 2244.35 / 10944.29 / 43013.38 ms |

The prior independent report used a 270-record snapshot. The current active collection is 310 records; this mismatch is documented and was not silently merged.

## 4. 120-row independent rerun

### Runtime distribution

| Runtime status | Count |
|---|---:|
| `ok` | 53 |
| `no_data` | 4 |
| `out_of_scope` | 63 |
| runtime error | 0 |

This matches the Lead V6 runtime distribution, but the QA classification below is based on answer/evidence review, not status alone.

### QA classification

| QA classification | Count | Meaning |
|---|---:|---|
| Factual PASS | 46 | answer and selected evidence satisfy the question |
| Factual FAIL | 11 | wrong/incomplete answer or no-data despite relevant evidence/contract expectation |
| Contract blocked | 63 | safe out-of-scope boundary; not counted as PASS |

### Lead claims verified

| Claim / ID | Result | Evidence |
|---|---|---|
| Active Chroma has 310 records | PASS | direct read-only collection count |
| UQ0007 year 2026 | PASS | `year=2026`, 15 retrieved/evidence chunks, eligibility answer returned |
| UQ0010 basic eligibility | PASS | graduation/equivalent condition returned; no timeout in this run |
| UQ0013 method list | PASS | all five methods listed |
| UQ0017 flexible Toán + 2 highest subjects | PASS | both supported structures and subject set returned |
| UQ0078 highest-benefit date | PASS | 13/08/2026 returned |
| UQ0085 13/8 vs 21/8 | PASS | distinct meanings and dates returned |
| UQ0134 supplementary list | PASS | all 12 programs listed in 500 sweep |
| UQ0179 Psychology score comparison | PASS | 20 vs 15 and no unsupported cause invented |
| UQ0321 scholarship by three-subject score | PASS | 50% and 70% thresholds returned correctly |
| UQ0328 per-credit tuition | PASS | 1,250,000 VND/credit returned |
| UQ0339 notification channels | PASS | Ministry system, DHV website and letter/Zalo channels all present |

## 5. Confirmed 120-row failures

| ID | Input | Expected | Actual/evidence | Severity |
|---|---|---|---|---|
| UQ0009 | `Đối với thí sinh khuyết tật...` | intervention via medical records and suitable-study support | generic scholarship/fee-support text mentions disability but omits the requested intervention policy | MEDIUM |
| UQ0041 | no English-test fee: total HKI | 14,250,000 VND | returns only 12,500,000 VND tuition; omits 1,500,000 fee and 250,000 e-learning fee | HIGH |
| UQ0076 | already admitted but not confirmed on Ministry system | confirmation is required; failure may mean refusal and needs counselor handling | says to confirm, but omits the consequence and case-handling guidance; incomplete procedural answer | MEDIUM/HIGH |
| UQ0083 | where guidance is published | official DHV admissions website | points to a PDF/document and does not clearly provide the official publication location | MEDIUM |
| UQ0138 | Chosun cooperation in 2026 | 28/01/2026 MOU and purpose | only says MOU in January 2026; omits exact date and purpose | MEDIUM |
| UQ0160 | IATAI undergraduate AI | yes, official IATAI source | `no_data`; 4 retrieved, 2 evidence candidates, no selected source | MEDIUM / DATA_REVIEW |
| UQ0222 | trung cấp cùng nhóm ngành | DHV method 5 eligibility | answer names **Đại học Sư phạm TP.HCM**, a wrong institution, and adds H-SCA wording | HIGH |
| UQ0236 | Học viện Hạnh phúc Việt Nam / 19-06-2026 | named cooperation fact | `no_data`; 25 retrieved/evidence candidates, no selected source | MEDIUM / DATA_REVIEW |
| UQ0327 | six-enterprise signing opportunities | enterprise semester, expert sharing, internship/career/recruitment | `no_data`; 25 retrieved/evidence candidates, no selected source | MEDIUM / DATA_REVIEW |
| UQ0378 | Marketing market-research knowledge | how students identify demand/trends/business opportunities | `no_data`; 4 retrieved, 2 evidence candidates | MEDIUM / DATA_REVIEW |
| UQ0409 | e-commerce business/environment knowledge | expected curriculum fact | runtime `ok` but gives a no-information fallback; 1 retrieved/evidence candidate | MEDIUM / FALSE_NO_DATA |

The four residual no-data IDs requested by the Lead task remain unresolved: **UQ0160, UQ0236, UQ0327, UQ0378**.

## 6. External, mixed and ambiguous school safety

### Single-turn matrix

| Query | Result | Retrieval | Evidence |
|---|---|---:|---:|
| Bách Khoa, unaccented Bách Khoa, Bách Khoa TP.HCM | `OTHER_SCHOOL` | 0 | 0 |
| Văn Hiến, Hoa Sen, Văn Lang, Nguyễn Tất Thành | `OTHER_SCHOOL` | 0 | 0 |
| `trường đại học khác` | `OTHER_SCHOOL` | 0 | 0 |
| `So sánh DHV và Văn Hiến` | `MIXED` | 0 | 0 |
| `Hùng Vương` without enough identity | ambiguous/clarification | 0 | 0 |
| `Điểm chuẩn DHV CNTT?` | DHV allowed | 4 | 4 |
| `Điểm chuẩn CNTT?` | DHV default | 4 | 4 |
| `Trường có những ngành nào?` | DHV default | 42 | 42 |

SEC-001 single-turn acceptance passes. No DHV fact leaked into the external/mixed/ambiguous answers.

The 63 original `out_of_scope` rows were adjudicated as contract-blocked content about IATAI, laboratories, events, research, student life, career outcomes and other non-admissions topics; no approved admissions query was found among them:

`UQ0108,UQ0150,UQ0189,UQ0209,UQ0231,UQ0245,UQ0246,UQ0248,UQ0249,UQ0250,UQ0254,UQ0256,UQ0258,UQ0261,UQ0262,UQ0264,UQ0265,UQ0267,UQ0268,UQ0269,UQ0271,UQ0272,UQ0274,UQ0275,UQ0280,UQ0281,UQ0282,UQ0284,UQ0292,UQ0296,UQ0297,UQ0300,UQ0302,UQ0305,UQ0329,UQ0330,UQ0331,UQ0332,UQ0333,UQ0336,UQ0341,UQ0343,UQ0344,UQ0345,UQ0346,UQ0347,UQ0349,UQ0363,UQ0367,UQ0372,UQ0389,UQ0393,UQ0415,UQ0419,UQ0441,UQ0442,UQ0445,UQ0453,UQ0455,UQ0456,UQ0467,UQ0471,UQ0497`.

### Multi-turn school regression

The first exploratory matrix passed the same mutable state object into the second call. That is not the runtime contract: `ask_chatbot` returns the updated state in `result["conversation_state"]`. The matrix was rerun using that returned state before adjudication.

- `Văn Hiến có xét học bạ không?` → `Còn điểm chuẩn?`: preserves `OTHER_SCHOOL`, retrieval 0, evidence 0 — **PASS**.
- `Văn Hiến có xét học bạ không?` → `Còn DHV thì sao?`: explicit DHV override enters the DHV path, retrieval 15, evidence 15 — **PASS**.
- `Điểm chuẩn DHV CNTT?` → `Còn Bách Khoa?`: switches to `OTHER_SCHOOL`, retrieval 0, evidence 0 — **PASS**.

The corrected harness results replace the earlier invalid mutable-object observation and are stored in `QA_FULL_MULTITURN_CORRECT_20261009.jsonl` in the temporary QA checkpoint.

## 7. State, coreference and recommendation checks

| Scenario | Actual | Verdict |
|---|---|---|
| `Điểm chuẩn CNTT?` → `Còn học phí?` | retains suitable generic tuition path; returns 12.5m with evidence | PASS |
| `Điểm chuẩn CNTT?` → `Còn Luật?` | switches to Law and returns Law evidence | PASS |
| 20-major list → `Điểm sàn các ngành nêu trên?` | resolves all 20 majors and returns a grounded threshold table | PASS |
| CNTT programs → `Chương trình thứ hai học gì?` | resolves `Lập trình AI` with parent CNTT | PASS |
| factual → greeting / external → thanks | no retrieval and no factual repetition | PASS |
| weak academic performance → “ngành nào phù hợp?” | recommends Quản trị kinh doanh from generic evidence, without evidence that academic fit is supported | FAIL, MEDIUM/HIGH `UNSUPPORTED_RECOMMENDATION` |

## 8. Count/list and focused 500-row checks

The final 500 sweep completed with:

| Runtime status | Count |
|---|---:|
| `ok` | 318 |
| `no_data` | 76 |
| `out_of_scope` | 105 |
| `clarification` | 1 |

The 500 runtime sweep is coverage evidence, not an automatic 318/500 factual PASS. `source="Tự làm"` remains evaluation-only.

Focused final checks:

- UQ0134: exact 12 supplementary programs — PASS.
- UQ0205: returns 80% score-based scholarship but omits the expected distinction that Talent scholarship can reach 100% full-course tuition — **PARTIAL FAIL**, MEDIUM.
- UQ0321: 21–25.5 → 50%, over 25.5 → 70% — PASS.
- UQ0328: 1,250,000 VND/credit — PASS.
- method count/list and count-plus-list: 5 and five unique methods — PASS.
- major count/list smoke: 20 major records and complete list response — PASS in focused matrix.

## 9. Wrong-year behavior

Focused runtime matrix:

- 2024 and 2025 tuition: `no_data`, retrieval 0.
- 2026 tuition: grounded answer, retrieval/evidence present.
- 2027 tuition: `no_data`, retrieval 0.

No wrong-year leakage was observed in this matrix.

## 10. Regression test results

### Targeted final regression

Command group covered full-sweep P1, priority fix, Task F, Phase 2 runtime and Phase 4 behavior tests.

| Result | Count |
|---|---:|
| Passed | 129 |
| Failed | 0 |
| Subtests passed | 209 |

Task F wrong program-parent relation passes in the current targeted run; no Task F failure reproduced.

### Full pytest

| Passed | Failed | Skipped | Subtests |
|---:|---:|---:|---:|
| 265 | 3 | 4 | 283 |

The three failures are:

1. `tests/test_ingestion.py::IngestionTests::test_build_persists_chroma_and_smoke_query_keeps_source_metadata`
   - `DuplicateIDError`: distinct test documents generate duplicate deterministic Chroma IDs.
   - Severity: HIGH data-integrity/reproducibility risk.

2. `tests/test_task_m.py::TaskMRawDataTests::test_raw_pdfs_have_official_urls_and_no_form_submission_data`
   - `data/raw/thong_tin_truong/Thong_Tin_Truong.pdf` contains a URL rejected by the official-DHV URL predicate while its manifest entry is verified.
   - Severity: MEDIUM/HIGH provenance inconsistency.

3. `tests/test_task_processed_md_to_json_migration.py::ProcessedJSONMigrationTests::test_loader_reads_canonical_json_only`
   - expected `skipped_unverified=2`, loader returns `1`.
   - Severity: MEDIUM migration/accounting contract mismatch.

These are existing unresolved failures, not environment failures.

## 11. Report/code/runtime consistency

| Lead statement | Independent result |
|---|---|
| Current active collection is 310 | confirmed |
| 120 V6 runtime distribution is 53/4/63 | confirmed |
| UQ0007 year semantics fixed | confirmed for current answer/evidence path |
| UQ0010 eligibility fixed | confirmed |
| UQ0339 complete notification channels | confirmed in final 310-record runtime |
| four residual no-data rows remain | confirmed |
| status `ok` proves factual PASS | rejected; UQ0041, UQ0222, UQ0409 and UQ0205 demonstrate otherwise |

## 12. Handoff to Lead Coder

### Priority 1 — HIGH

- **P1-ENTITY-001:** Prevent wrong institution substitution in UQ0222. Acceptance: answer names DHV only and method 5, never Đại học Sư phạm TP.HCM.
- **P1-EVIDENCE-001:** Resolve UQ0041 total-cost selection and prevent tuition-only partial answer.

### Priority 2 — MEDIUM/HIGH

- **P2-LLM-001:** Block unsupported academic-fit recommendation or ask clarification.
- **P2-ANSWER-001:** Complete UQ0076, UQ0083, UQ0138 and UQ0205 required facts.

### Data/infrastructure

- **DATA-001:** Add or explicitly exclude verified evidence for UQ0160/UQ0236/UQ0327/UQ0378.
- **DATA-002:** Resolve the Task M official URL/manifest inconsistency.
- **DEVOPS/LEAD-001:** Fix deterministic Chroma ID collisions in ingestion.
- **LEAD-002:** Correct `skipped_unverified` accounting.

## 13. Acceptance criteria

| Criterion | Result |
|---|---|
| Active collection verified at 310 | PASS |
| 120 rows independently executed | PASS: 120/120 |
| 500 rows independently executed | PASS: 500/500 |
| UQ0007/UQ0010/UQ0013/UQ0017/UQ0078/UQ0085 fixed | PASS |
| UQ0134/UQ0179/UQ0321/UQ0328 fixed | PASS |
| UQ0205 complete | **FAIL / PARTIAL** |
| UQ0339 complete | PASS |
| UQ0160/UQ0236/UQ0327/UQ0378 closed | **FAIL** |
| External single-turn retrieval/evidence zero | PASS |
| External multi-turn state cannot leak DHV | PASS with returned-state harness |
| Explicit DHV override after external school | PASS with returned-state harness |
| Coreference | PASS in corrected multi-turn matrix |
| Unsupported recommendation | **FAIL** |
| Full pytest clean | **FAIL: 3 failures** |
| No unresolved HIGH issue | **FAIL** |

## 14. Final verdict

**`FULL_SWEEP_P1_FINAL_QA_FAIL`**

The Lead fixes successfully close several prior single-turn factual defects and the corrected multi-turn state harness passes school isolation and coreference. Four evidence/data gaps, one wrong-institution answer, one unsupported recommendation, one incomplete scholarship answer, and three full-pytest failures remain. Lead Coder and data/infrastructure handoff is required before the next QA retest.
