# CHATBOT FOLLOW-UP SECURITY FIX REPORT

## 1. Scope

- Fix QA finding `QA-FUP-001`: a specific faculty/institute website request must not return an unrelated DHV overview.
- Harden Security finding `F-01`: a `SCHOOL_INFO` subplan containing an overview request must remain behind the verified-introduction evidence gate even when detail markers such as `website` or `sự kiện` are present or moved into a neighboring subquery.
- Re-verify Security findings `F-02` (unaccented external institution validation) and `F-03` (root multi-intent trace aggregation).
- No deployment, dataset edit, Chroma rebuild, or Chroma write.

## 2. Root Cause Verification

### QA-FUP-001

`_is_school_info_request()` and `_is_verified_school_info_request()` treated the unit name `Viện Đào tạo Sau đại học` as a school-information/overview signal even when the actual request was for that unit's website. The router therefore produced both `HOI_CO_SO_LIEN_HE` and `SCHOOL_INFO`; `_ask_multi_issue()` could merge a successful general overview into a website request whose requested URL had no verified evidence.

### Security F-01

The overview detector excluded a `SCHOOL_INFO` subplan when it also contained detail markers (including `website`). In multi-intent routing, this could allow the detail-only evidence to reach LLM generation without the required introduction-document check.

### Security F-02 and F-03

The current working tree already normalizes generated answers before organization detection and checks the complete normalized institution name against evidence. Root multi-issue retrieval/document/evidence counters are already aggregated from per-subplan traces. Existing focused regression tests confirm both behaviors; no additional production-code change was needed for these findings.

## 3. Implementation

- A specific named DHV unit website request is now classified as `HOI_CO_SO_LIEN_HE` only, unless the user separately asks for an explicit school overview.
- Overview intent is no longer disabled by detail words. The overview gate also checks the original parent question, not only the generated subquery. If matching verified introduction evidence is absent, the overview subplan returns `no_data` and does not call the answer LLM.
- Explicit compound requests such as “Thông tin trường DHV và website Viện Đào tạo Sau đại học” remain two independently routed issues.

## 4. Files Changed

| File | Area | Reason |
|---|---|---|
| `src/chatbot/query_analysis.py` | School-info and unit-website classification | Keep a specific faculty/institute website query from creating a false overview issue. |
| `src/chatbot/rag_chain.py` | Overview evidence gate in multi-issue orchestration | Preserve the verified-introduction boundary despite detail markers or subquery changes. |
| `tests/test_task_09.py` | Website, overview, and trace regressions | Cover accented/unaccented unit names, missing URL, compound requests, detail-marker bypass, and aggregated trace counts. |
| `reports/CHATBOT_FUP_SECURITY_FIX_REPORT.md` | Handoff report | Record root cause, changes, verification, and remaining runtime limitation. |

Other files already modified in the working tree predate this follow-up and were not changed by this fix.

## 5. Tests

### Targeted suites

Command covered Task 09, Priority 1/2 security, intent analysis, pre-RAG decomposition, Full Sweep P1, Phase 2 runtime, and Phase 4 conversation tests.

- Passed: **155**
- Failed: **0**
- Skipped: **0**
- Subtests passed: **153**

Focused validator regression for accented/unaccented `Đại học FPT`: **1 passed, 2 subtests passed**.

### Full suite

- Default Windows temp location: **283 passed, 4 skipped, 11 failed**. The failures were caused by `TemporaryDirectory` creation/cleanup permission errors under the sandbox temp path (`WinError 5`), not by failed chatbot assertions.
- Re-run with `TEMP`, `TMP`, and `TMPDIR` pointed at the existing project `.test_tmp`: **294 passed, 4 skipped, 0 failed, 303 subtests passed**.

## 6. Security Regression Checks

- Specific unit website, with and without Vietnamese diacritics: contact/website intent only; no implicit overview subplan.
- Missing verified unit URL with only generic overview evidence: `no_data`, empty sources, one requested retrieval, no overview text, no answer-LLM call.
- Explicit overview plus unit website: both requested intents remain represented.
- Overview plus detail markers and detail-only evidence: overview subplan is `no_data`; answer LLM is not called for that subplan.
- External institution validator, including unaccented `Dai hoc FPT`: focused regression passes.
- Root multi-issue trace counters: regression asserts root retrieval/doc/evidence totals equal the sums of subplan totals.

## 7. Runtime Trace

The current execution environment could not access Ollama at `127.0.0.1:11434` (`WinError 10013`, socket access denied). Consequently, DHV live queries returned `ollama_offline` before retrieval; this does not validate a successful live Chroma/RAG answer.

Read-only trace observations:

| Query | Intent / target | Retrieval | Status |
|---|---|---:|---|
| `website Viện Đào tạo Sau đại học?` | `HOI_CO_SO_LIEN_HE` / `UNSPECIFIED` | 0 before retrieval because Ollama unavailable | `ollama_offline` |
| `Thông tin trường DHV` | `SCHOOL_INFO` / `DHV` | 0 before retrieval because Ollama unavailable | `ollama_offline` |
| `Điểm chuẩn Bách Khoa?` | `HOI_DIEM_TRUNG_TUYEN` / `OTHER_SCHOOL`, `external_school` | 0 | `out_of_scope` |

The earlier DevOps report recorded a healthy Ollama endpoint. The endpoint was inaccessible from this verification run, so live E2E should be rechecked in the intended local runtime environment.

## 8. Data and Deployment

- Processed data and canonical evaluation data were not changed.
- Active or staging Chroma was not rebuilt, reset, or written.
- No deployment or process restart was performed.

## 9. Remaining Risks

- Live Ollama + active Chroma answer generation remains unverified in this execution environment due the socket permission block.
- The institute website URL remains absent from verified evidence; the intended behavior is a grounded `no_data` response with no substitute URL or unrelated overview.
- QA must review the actual code changes and rerun the regression cases independently before any final PASS.

## 10. Handoff to QA & Security

Please review the changed code (not only this report) and write a Markdown retest report. The report must include:

1. Snapshot/commit and exact commands run.
2. Each test case with input, expected, actual, status, retrieval count, evidence count, sources, and LLM-call count where applicable.
3. Accented and unaccented institute/faculty website cases, including missing verified URL and explicit overview-plus-website compound.
4. Security F-01 no-introduction-evidence case with detail markers; F-02 unaccented institution claim; F-03 root/subplan trace totals.
5. External/mixed/ambiguous school regression and the Task 09 / Phase 2 / Phase 4 / full-suite results.
6. Live Ollama/Chroma result, or the precise environment error and an explicit `BLOCKED` classification.
7. Final QA verdict `PASS`, `FAIL`, or `BLOCKED`, plus remaining issues.

Do not modify source/data, rebuild Chroma, or deploy during QA. DevOps/SRE is not being asked to deploy; runtime follow-up should occur only after QA review or through an explicitly scoped environment check.

## 11. Lead Coder Handoff Verdict

`READY_FOR_QA` — code-level targeted and full-suite tests pass. This is not a QA PASS; live runtime verification remains pending because Ollama was inaccessible from this run.
