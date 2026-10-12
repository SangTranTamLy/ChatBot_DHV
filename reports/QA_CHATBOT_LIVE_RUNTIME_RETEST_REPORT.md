# QA & SECURITY — CHATBOT LIVE RUNTIME RETEST REPORT

## 1. Scope and Snapshot

Independent QA retest of the current working tree after the DevOps local Ollama recovery report. Scope: live RAG/generation where reachable, QA-FUP-001, Security F-01/F-02/F-03, external-school boundary, relevant regressions, and active Chroma metadata.

- Date: 2026-10-11
- Repository HEAD: `f6016fb` (`chore(repo): organize files and ignore generated artifacts`)
- Working tree: contains pre-existing Lead changes; QA preserved them.
- Runtime target: `http://localhost:11434`, `qwen2.5:3b`, `nomic-embed-text`
- Chroma: `chroma_db/dhv_admissions_2026`
- QA did not edit source, tests, data, or configuration; did not rebuild/reset/upsert Chroma; did not deploy; did not start, restart, or stop Ollama.

## 2. Reports and Code Reviewed

Reports read:

- `reports/TONG_QUAN_AGENT`
- `reports/DEVOPS_OLLAMA_RUNTIME_RECOVERY_REPORT.md`
- `reports/QA_CHATBOT_FUP_SECURITY_RETEST_REPORT.md`
- `reports/CHATBOT_FUP_SECURITY_FIX_REPORT.md`
- `reports/CHATBOT_OVERVIEW_WEBSITE_FIX_REPORT.md`
- `reports/CHATBOT_PLAN_FOLLOWUP_IMPLEMENTATION_REPORT.md`
- `reports/QA_CHATBOT_PLAN_FOLLOWUP_RETEST_REPORT.md`

Implementation reviewed directly in the working tree:

- `src/chatbot/chat_service.py`
- `src/chatbot/query_analysis.py`
- `src/chatbot/query_decomposer.py`
- `src/chatbot/scope_guard.py`
- `src/chatbot/rag_chain.py`
- `src/chatbot/evidence.py`
- `src/chatbot/output_validator.py`
- `src/retrieval/retriever.py`
- `src/config/settings.py`

Regression tests reviewed/run include Task 09, query decomposition, Priority 1+2, Full Sweep P1, Phase 2/4, Task C/I/K/L/M, processed-JSON migration, and app/UI contract tests.

## 3. Environment and Read-Only Chroma Audit

The QA execution environment could not reach `127.0.0.1:11434`. A direct PowerShell request to `/api/version` returned a Windows socket permission error. No Ollama process/listener was visible through the QA shell at the time of its checks. This conflicts with the earlier DevOps host-level observation that PID 24528 was listening; QA could not independently verify whether that host process remained reachable from this execution context. QA did not stop it.

Active collection read-only audit, using collection `get`/`count` only:

| Property | QA observation |
|---|---:|
| Collection | `dhv_admissions_2026` |
| Record count | 310 |
| Year | 2026: 310 |
| Status | verified: 310 |
| School | DHV: 310 |
| Source hosts | `dhv.edu.vn`: 181; `tuyensinh.dhv.edu.vn`: 129 |

No collection mutation or rebuild was attempted.

## 4. Exact Commands and Test Results

### Live default-path attempts

The eight required questions were called sequentially through `src.chatbot.chat_service.ask_chatbot()` with its default retriever and LLM configuration. Calls completed, but seven DHV requests returned `ollama_offline` before retrieval because the configured local runtime was inaccessible. The external-school request terminated at the scope boundary as expected.

### Targeted regression suite

Command (workspace temp path was used to avoid the known Windows temp ACL issue):

```powershell
$env:PYTHONPATH='.'
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_task_09.py tests/test_query_decomposer.py tests/test_priority_1_2_fix.py tests/test_full_sweep_p1.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_task_c.py tests/test_task_i.py tests/test_task_k.py tests/test_task_l.py tests/test_task_m.py tests/test_task_processed_md_to_json_migration.py tests/test_app.py tests/test_task_response_ui.py
```

Result: **204 passed, 0 failed, 0 skipped; 168 subtests passed**.

### Full suite

Command:

```powershell
$env:PYTHONPATH='.'
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
```

Result: **294 passed, 0 failed, 4 skipped; 303 subtests passed**. The quiet output did not identify the four skipped test names/reasons; they are not counted as passes.

`git diff --check` could not run in this environment: Git returned `fatal: this operation must be run in a work tree`, although `git status` and `git rev-parse` succeeded. This is recorded as a tooling limitation, not a product test failure.

## 5. Live Query Trace Matrix

`intent/sub-intents` and scope below are from the actual `ask_chatbot` trace. `pre-RAG spans` are the plan's router subqueries; if Ollama was unavailable, no retrieved-document/evidence subplan execution occurred. For those rows, per-subplan results are therefore **not produced**, not zero-valued successful retrievals.

| # | Input | Intent / sub-intents | Target / scope | Planner or pre-RAG plan | Retrieval / docs / evidence | Validator | Final status; answer/source observation |
|---:|---|---|---|---|---:|---|---|
| 1 | `Em muốn biết cách đăng ký tuyển sinh DHV và học phí năm 2026.` | `HOI_DANG_KY_XET_TUYEN`; issue signal `HOI_HOC_PHI` | `DHV / in_scope_dhv` | No router subplans; pre-RAG decomposition rejected as `planner_unavailable`; categories registration/method | `0 / 0 / 0` | Not reached | `ollama_offline`; safe local-service-unavailable message; sources `[]`. The requested registration + tuition answer was not evaluated. |
| 2 | `Thông tin trường DHV và học bổng DHV` | `MULTI_ISSUE`; `SCHOOL_INFO`, `HOI_HOC_BONG` | `DHV / in_scope_dhv` | Two router subplans: overview and scholarship | `0 / 0 / 0` | Not reached | `ollama_offline`; no factual answer/source. Per-subplan retrieval/status unavailable. |
| 3 | `Trường DHV có bao nhiêu website?` | `HOI_CO_SO_LIEN_HE`, mode `COUNT` | `DHV / in_scope_dhv` | Website count request recognized | `0 / 0 / 0` | Not reached | `ollama_offline`; no count/URLs/sources returned in this QA run. |
| 4 | `Thông tin trường DHV và website trường?` | `MULTI_ISSUE`; `SCHOOL_INFO`, `HOI_CO_SO_LIEN_HE` | `DHV / in_scope_dhv` | Two router subplans: overview and official website | `0 / 0 / 0` | Not reached | `ollama_offline`; no answer/source to assess. |
| 5 | `website Viện Đào tạo Sau đại học?` | `HOI_CO_SO_LIEN_HE` | `UNSPECIFIED / in_scope_dhv` | Website request recognized; contact/website categories | `0 / 0 / 0` | Not reached | `ollama_offline`; no answer/source to assess. The controlled regressions and previous QA evidence cover missing-URL fail-closed behavior, but live behavior is blocked here. |
| 6 | `Điểm chuẩn Bách Khoa?` | `HOI_DIEM_TRUNG_TUYEN` | `OTHER_SCHOOL / external_school` | Boundary exits before retrieval | **`0 / 0 / 0`** | Deterministic scope boundary; validator not needed | `out_of_scope`; DHV-scope explanation only; sources `[]`. **Live boundary PASS.** |
| 7 | `Thông tin trường DHV và website Viện Đào tạo Sau đại học` | `MULTI_ISSUE`; `SCHOOL_INFO`, `HOI_CO_SO_LIEN_HE` | `DHV / in_scope_dhv` | Two router subplans: overview and unit website | `0 / 0 / 0` | Not reached | `ollama_offline`; no answer/source to assess. |
| 8 | `Thong tin truong DHV va su kien, website, hoc bong` | `MULTI_ISSUE`; `SCHOOL_INFO`, `HOI_CO_SO_LIEN_HE`, `HOI_HOC_BONG` | `DHV / in_scope_dhv` | Three router subplans: overview, contact/website, scholarship | `0 / 0 / 0` | Not reached | `ollama_offline`; exact F-01 live generation/evidence behavior is blocked. No per-subplan result or final factual answer was generated. |

Across these eight attempts: **8/8 calls completed; 7/8 were blocked before RAG by Ollama unavailability; 1/8 external boundary completed with zero retrieval/docs/evidence.**

## 6. Findings by ID

### QA-FUP-001 — specific institute website must not spill into overview

- Severity: Medium if reproduced; live severity status: **BLOCKED / not independently reverified**.
- Expected: a missing verified institute URL yields `no_data`, empty sources, and no unrelated school overview; an explicit overview + institute URL question retains separate issues.
- Current QA live evidence: unit-only case and explicit compound case both stop at `ollama_offline` before retrieval/generation, so no live answer leakage was observed or ruled out.
- Code/test evidence: current query analysis has a specific unit-website classifier; multi-issue overview is guarded by verified intro evidence. The targeted suite passed, including Task 09 cases. Prior independent controlled evidence reports missing unit URLs fail closed.
- Root-cause resolution status: deterministic/code-level regression is not reproduced by this QA suite; live RAG confirmation remains blocked.

### F-01 — overview bypass in detail-rich multi-intent questions

- Severity: High if intro evidence is bypassed; live status: **BLOCKED**.
- Exact adversarial query #8 is parsed as `MULTI_ISSUE` with overview, website/contact, and scholarship subplans. The Ollama failure occurs before retrieval, so this run cannot confirm selected evidence, LLM-call count, final completeness, or factual grounding.
- The controlled regression `test_multi_issue_school_overview_fails_closed_without_intro_evidence` and `test_overview_gate_survives_detail_markers_in_school_info_subplan` passed as part of the targeted suite. Those tests assert the overview subplan is `no_data`, the overview boundary is `school_overview_missing_matching_evidence`, the LLM is not called, and root retrieval/docs/evidence counters equal subplan sums.
- No live F-01 bypass was observed; the live criterion is not verified due environment block.

### F-02 — unsupported external institution claim, accented/unaccented

- Severity: High if accepted.
- Synthetic validator test used one verified 2026 DHV evidence chunk with generic partnership wording and no FPT mention. Both generated answers were independently passed to `validate_model_answer`:
  - `DHV hợp tác với Đại học FPT.` → `no_data`, reason `institution_mismatch`, `sources=[]`.
  - `DHV hop tac voi Dai hoc FPT.` → `no_data`, reason `institution_mismatch`, `sources=[]`.
- Result: **PASS** for the validator defense in both forms. The question-level live generation path remains untested because Ollama was inaccessible.

### F-03 — root multi-intent trace aggregation

- Severity: Low (observability integrity), with potential security-audit impact.
- Controlled regressions passed assertions that root `retrieval_calls` equals subplan count, root `retrieved_docs_count` equals `sum(retrieved_docs_counts)`, and root `evidence_count` equals `sum(evidence_counts)` for exact/detail-rich multi-intent cases.
- Actual numeric live aggregation could not be observed because the default runtime stopped before retrieval. Result: **PASS controlled regression; live trace BLOCKED**.

## 7. External/Scope and CORE/STATE Regressions

- Live `Điểm chuẩn Bách Khoa?`: `OTHER_SCHOOL`, `external_school`, status `out_of_scope`, retrieval/docs/evidence `0/0/0`, sources empty — PASS.
- The targeted run included SEC-001/SEC-002 cases in `tests/test_priority_1_2_fix.py`, plus scope, Phase 2/4, full-sweep P1 and conversation regressions. All passed in the run summary.
- This run did not complete a live multi-turn Ollama conversation; CORE/STATE are verified only by automated regressions here.
- Mixed and ambiguous live traces were not part of the required eight-query live matrix; their relevant regression coverage passed in the targeted suite, but no new live evidence is claimed.

## 8. Factual and Evidence Quality

No factual DHV answer was generated for the seven blocked requests, so factual correctness, completeness, per-issue evidence isolation, source attribution, and no-hallucination quality cannot be scored in this live run. The runtime returned an explicit offline status and empty sources rather than fabricating an answer. The external-school case returned the deterministic scope boundary with no DHV facts. This is safe behavior under the observed environment failure, not a live RAG PASS.

## 9. Blocked Items

- **ENVIRONMENT_BLOCKED:** QA's local endpoint access was denied by Windows socket permissions despite the DevOps report's earlier healthy host-level check.
- Live Nomic embedding, Chroma similarity retrieval through the default retriever, Qwen generation, real pre-RAG decomposition, and live F-01/FUP answer quality remain unverified.
- QA did not modify permissions/sandbox settings, launch/restart/stop Ollama, or substitute fake live results.
- The four skipped tests in the full suite were not expanded by `pytest -q`; they remain skipped and are not counted as passes.
- `git diff --check` could not execute because Git reported that the operation must be run in a work tree; `git status` and HEAD lookup succeeded.

## 10. Acceptance Status

| Acceptance item | Status |
|---|---|
| Required eight default-path query attempts completed | PASS — all eight calls returned a result |
| Default endpoint and model availability independently verified | BLOCKED — localhost socket access denied in QA environment |
| Real embedding/retrieval/generation verified | BLOCKED |
| Website-count live answer and provenance verified | BLOCKED |
| Unit website no-data/no-spill live answer verified | BLOCKED; controlled regressions pass |
| Overview + scholarship live completeness/grounding verified | BLOCKED; router recognizes both issues; controlled tests pass |
| Exact F-01 live answer/evidence bypass ruled out | BLOCKED; controlled fail-closed tests pass |
| F-02 accented and unaccented synthetic validator defense | PASS |
| F-03 aggregate counters equal controlled subplan totals | PASS in tests; live aggregate unavailable |
| Bách Khoa external-school retrieval/docs/evidence are zero | PASS — live trace `0/0/0` |
| Read-only Chroma snapshot is 310 verified 2026 DHV records | PASS |
| Targeted regression suite | PASS — 204 passed, 168 subtests |
| Full pytest | PASS — 294 passed, 4 skipped, 303 subtests |
| No source/test/data/config modifications, Chroma writes/rebuild, or deployment by QA | PASS |

## 11. Final QA Verdict

# BLOCKED

The required runtime endpoint was inaccessible from the QA execution environment. Regression tests and synthetic F-02/F-03 checks passed, and the external Bách Khoa boundary was confirmed live at `0/0/0`; however, seven DHV cases could not reach retrieval or generation. QA cannot certify live evidence quality, F-01/FUP answer behavior, website counting, or multi-intent completeness from this run.

## 12. Handoff to Lead / Runtime Owner

No confirmed new product defect was established by this run. Keep the existing implementation unchanged pending a QA-accessible local Ollama endpoint. Re-run the same eight-case live matrix, especially exact F-01, overview + scholarship, website count, unit website, and compound registration + tuition, once the runtime is reachable from the QA process. Preserve read-only Chroma access. This report does not authorize deployment and is not a final product PASS.
