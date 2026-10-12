# QA & Security — Multi-Issue Completeness Retest Report

## 1. Scope and Snapshot

Requested scope: independently retest the new Lead patch for multi-issue event isolation, scholarship answer formatting/numeric fidelity, F-01/F-02/F-03, scope/website/coreference/state/decomposition/count-list regressions, targeted/full pytest, and three default-path live queries.

**QA verdict: BLOCKED before inspection or test execution.** The current execution host failed to create any shell/Node process with `CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)`. PowerShell, `cmd.exe`, and the Node REPL launcher each returned this process-creation error. As a result, this QA run could not read the requested reports, inspect the new diff, query Ollama, or run tests. No claims below are represented as independently verified results.

- Project: `ChatBot_DHV`
- Snapshot/HEAD and dirty state: **UNVERIFIED**; Git could not be queried.
- Report date: 2026-10-11 (from the provided task environment context).
- QA did not edit source, tests, data, or config; did not write/rebuild Chroma; did not install/change models; did not deploy; did not stop Ollama.
- This report is the only intended QA artifact for this interrupted retest.

## 2. Required Reports and Files

The requested read of the following full reports was attempted, but the command process failed before opening any file:

- `reports/TONG_QUAN_AGENT`
- `reports/CHATBOT_MULTIISSUE_COMPLETENESS_FIX_REPORT.md`
- `reports/QA_CHATBOT_LIVE_RUNTIME_RETEST_REPORT.md`
- `reports/DEVOPS_OLLAMA_RUNTIME_RECOVERY_REPORT.md`

Direct inspection of the requested patch hunks was also **not performed**:

- `src/chatbot/query_analysis.py`
- `src/chatbot/rag_chain.py`
- `tests/test_task_09.py`

Other tests and implementation files in the requested regression scope were not inspected in this run.

## 3. Environment and Chroma

- Process-launch error: `MXC launcher: failed to create the process security environment: CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)`.
- Reproduced by attempts using PowerShell and `cmd.exe`; Node REPL initialization failed with the same launcher error.
- Ollama endpoint reachability in this follow-up: **NOT TESTED**. The QA process could not start, so this report does not claim the endpoint itself failed or succeeded now.
- The previous QA run had reported localhost socket denial, and the user-provided handoff says DevOps observed Ollama running. Those are prior/supplied observations, not independently rechecked in this follow-up.
- Chroma: **NOT OPENED** in this run. No reads or writes were attempted; no rebuild/reset/upsert occurred.

## 4. Tests and Commands

No test command could be started. Exact attempted report-read command:

```powershell
Get-Content -Raw reports/TONG_QUAN_AGENT; Get-Content -Raw reports/CHATBOT_MULTIISSUE_COMPLETENESS_FIX_REPORT.md; Get-Content -Raw reports/QA_CHATBOT_LIVE_RUNTIME_RETEST_REPORT.md; Get-Content -Raw reports/DEVOPS_OLLAMA_RUNTIME_RECOVERY_REPORT.md
```

Result: process launcher failure before command execution. Retrying with the same command failed identically. A read-only `cmd.exe` directory listing and Node REPL initialization also failed at process creation.

| Suite | Result in this QA run |
|---|---|
| Requested targeted regression suite | NOT RUN — environment/process-launch blocked |
| Full pytest | NOT RUN — environment/process-launch blocked |
| Lead-reported targeted result | 205 passed / 168 subtests — **supplied claim, not verified** |
| Lead-reported full suite | 295 passed / 4 skipped / 303 subtests — **supplied claim, not verified** |

## 5. Requested Live Matrix — Not Executed

No default `ask_chatbot` invocation was possible because the execution process could not be created. Therefore there are no current intent, scope, retrieval, evidence, validator, final-status, or source traces from this QA run.

| Query | Expected behavior | Actual QA observation |
|---|---|---|
| `Thong tin truong DHV va su kien, website, hoc bong` | Keep explicit event issue separate and OUT_OF_SCOPE/no-data with no retrieval; independently answer supported overview, website, and scholarship issues | NOT RUN — no runtime trace |
| No-event compound control | Must not add an event section | NOT RUN — no runtime trace |
| `Thông tin trường DHV và học bổng DHV` | Answer both requested issues without event spill | NOT RUN — no runtime trace |

Per-subplan retrieval/docs/evidence/status/sources: **NOT AVAILABLE**. No `PASS` or `FAIL` is assigned to these live cases.

## 6. Scholarship Evidence and Formatting

Requested verification items:

- Omit numbered scholarship section headings from the answer.
- Preserve dotted monetary amounts such as `10.000.000 VNĐ`.
- Compare `50%` wording with the exact selected evidence.
- Compare “học bổng lên đến 75 tỷ đồng” wording with the exact selected evidence; do not infer that a total fund amount is a per-student award or guaranteed benefit.

Status: **NOT VERIFIED**. The new Lead report and selected Chroma evidence were not readable in this run. The exact selected evidence passage and answer wording cannot be responsibly reconstructed from the task prompt or prior report summaries.

## 7. Findings and Severity

### ENV-QA-EXEC-001 — QA execution process cannot start

- Severity: **Environment blocker; product severity undetermined**.
- Reproduction: shell and Node launcher return `CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)`.
- Impact: prevents report/code inspection, tests, Chroma read-only audit, and live `ask_chatbot` traces.
- Owner: QA execution environment / host runtime.
- Product finding: **none established**. This is not evidence that the Lead patch passes or fails.

### Event isolation / scholarship heading and numeric fidelity / F-01–F-03

- Status: **UNVERIFIED**, not PASS and not a confirmed product failure.
- Root cause: cannot be assessed without current code/test/report access.

## 8. Environment Distinction

This run is blocked at process creation, before any localhost request. It must not be mislabeled as “Ollama offline” or as a chatbot product failure. The previous QA report's socket-denial observation remains prior evidence only; the new attempt did not independently test endpoint connectivity. DevOps's reported host status is treated as supplied evidence, not independent QA verification.

## 9. Acceptance Matrix

| Criterion | Status |
|---|---|
| Full reports read | BLOCKED |
| Current patch/diff inspected | BLOCKED |
| Explicit event subplan is retained as OUT_OF_SCOPE/no-data and skips retrieval | BLOCKED |
| No-event control avoids an event section | BLOCKED |
| Overview/website/scholarship answer independently and completely | BLOCKED |
| Scholarship heading omitted | BLOCKED |
| Dotted money values preserved | BLOCKED |
| 50% wording is supported by selected evidence | BLOCKED |
| “up to 75 billion VND” wording matches selected evidence | BLOCKED |
| F-01/F-02/F-03 regression | BLOCKED |
| External/mixed/ambiguous, scope and website regression | BLOCKED |
| CORE/STATE, decomposition, count/list, Phase 2/4 regression | BLOCKED |
| Targeted suite independently rerun | BLOCKED — not started |
| Full pytest independently rerun | BLOCKED — not started |
| Three requested live default-path queries attempted | BLOCKED — not started |
| No source/data/Chroma mutation or deployment by QA | PASS — none performed |

## 10. Final QA Verdict

# BLOCKED

This is a process-execution blocker, not a code verdict. The Lead-reported test counts and live traces remain unverified by this QA retest. Do not treat this report as a patch PASS, a full-project PASS, or a full-sweep PASS.

## 11. Handoff

Retry this independent review when the workspace process launcher is available. Resume by reading all four required reports, checking the current dirty snapshot and exact diff hunks, reviewing selected scholarship evidence against exact output text, running the requested targeted and full suites, then attempting the three live default-path queries. Preserve read-only Chroma access and do not deploy.
