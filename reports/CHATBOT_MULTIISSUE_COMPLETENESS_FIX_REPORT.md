# CHATBOT MULTI-ISSUE COMPLETENESS FIX REPORT

## 1. Scope

Follow-up implementation for the approved chatbot plan. Fixed two confirmed live-answer quality issues:

- A supported multi-intent answer silently omitted an explicitly mentioned school-event topic that is outside the currently verified admissions-data scope.
- A numbered scholarship section heading was rendered as if it were a useful policy fact.

No event data was added. No dataset, prompt, model, PDF, processed JSON, Chroma collection, or deployment was changed.

## 2. Root Cause Verification

The live query `Thong tin truong DHV va su kien, website, hoc bong` was classified into school overview, contact/website, and scholarship subplans. The event marker was intentionally excluded from verified school-information routing, but it was not retained as a separate unsupported issue. The final response therefore omitted it despite returning `status=ok`.

The scholarship formatter excluded a few exact/uppercase heading forms. A numbered title such as `1.16. Học bổng Cam kết hoàn học phí` could be merged with nearby text and pass that check.

## 3. Implementation

- Retain a recognized school-event/activity topic as an `OUT_OF_SCOPE` sub-issue when it appears alongside supported issues.
- The event sub-issue returns a clear no-verified-data message, has no source, and skips retrieval entirely. Supported DHV sub-issues continue independently.
- Root `retrieval_calls` now counts actual retriever invocations, not the number of planned sub-issues.
- Filter numbered scholarship headings only when the heading names a scholarship section and contains no value/rule detail. A dotted monetary amount such as `10.000.000 VNĐ` remains factual content and is preserved.

## 4. Files Changed in This Follow-up

| File | Area | Reason |
|---|---|---|
| `src/chatbot/query_analysis.py` | Multi-issue signals and ordering | Preserve explicit unsupported event topics without expanding supported scope. |
| `src/chatbot/rag_chain.py` | Multi-issue handling, trace count, scholarship formatter | Return event no-data without retrieval; remove orphan numbered scholarship headings. |
| `tests/test_task_09.py` | Regression coverage | Assert event no-retrieval/no-evidence response, keep supported issues, and filter a heading while preserving 50%, 75-billion, and currency facts. |

These are the files changed by this follow-up; the existing working tree also contains earlier approved Lead Coder changes.

## 5. Verification

### Targeted regression

Command covered Task 09, query decomposition, Priority 1+2, Full Sweep P1, Phase 2/4, Task C/I/K/L/M, processed JSON migration, app, and UI contract.

- Passed: **205**
- Failed: **0**
- Skipped: **0**
- Subtests: **168 passed**

### Full suite and static checks

- Full pytest: **295 passed, 4 skipped, 0 failed; 303 subtests passed**.
- `git diff --check`: exit 0; Git emitted only existing LF-to-CRLF working-tree notices.
- `python -m compileall -q src app.py`: PASS.
- Focused event, scholarship-heading, and numeric-integrity tests: **4 passed**, 4 subtests.

## 6. Live Runtime Traces

Read-only host smoke used the configured local Ollama models and active Chroma collection. It was run by Lead Coder; it is supplementary evidence, not an independent QA verdict.

### Exact detail-rich event query

Input: `Thong tin truong DHV va su kien, website, hoc bong`

- `status=ok`, intent `MULTI_ISSUE`, target `DHV`, scope `in_scope_dhv`.
- Sub-issues: `SCHOOL_INFO`, `OUT_OF_SCOPE`, `HOI_CO_SO_LIEN_HE`, `HOI_HOC_BONG`.
- Sub-statuses: `ok`, `out_of_scope`, `ok`, `ok`.
- Root retrieval/docs/evidence: **3 / 54 / 22**.
- Per-sub-issue docs: **25 / 0 / 25 / 4**; evidence: **10 / 0 / 8 / 4**.
- Event retrieval audit: `null`; the response explicitly says verified event/activity information is unavailable. The overview, website, and scholarship sections remain present.
- Sources are verified DHV sources; the event no-data section contributes none.

### Overview plus scholarship

Input: `Thông tin trường DHV và học bổng DHV`

- `status=ok`; retrieval/docs/evidence: **2 / 29 / 14**.
- Overview and scholarship sections are returned from verified DHV evidence.
- Numbered heading `1.16. Học bổng Cam kết hoàn học phí` is no longer rendered.
- Verified values `50%` and `75 tỷ đồng` remain. The selected evidence describes the latter as “học bổng lên đến 75 tỷ đồng”; QA should review whether that wording is sufficiently clear without additional source context.

The active Chroma collection was not written, rebuilt, or reset.

## 7. Remaining Risks / QA Review

- The independent QA report `QA_CHATBOT_LIVE_RUNTIME_RETEST_REPORT.md` is `BLOCKED`: its sandbox could not access localhost Ollama. It predates this follow-up patch.
- QA/Security must review this new patch, rerun the event/no-retrieval and numeric-integrity regressions, and independently attempt live runtime from an environment that can reach Ollama.
- The scholarship evidence selected for the 75-billion wording does not include the word “quỹ”; QA should check whether the answer is appropriately bounded and understandable.
- This report does not claim final QA approval or full question-sweep pass.

## 8. Handoff to QA & Security

Review current code and rerun at least:

1. `Thong tin truong DHV va su kien, website, hoc bong` and accented variant: event is an explicit no-data section, retrieval/docs/evidence are zero for that sub-issue, and other issues still answer.
2. The control compound without event: no false `OUT_OF_SCOPE` event section.
3. `Thông tin trường DHV và học bổng DHV`: heading omitted; numeric integrity test retains `10.000.000 VNĐ`, `50%`, and the selected 75-billion wording for factual review.
4. External/mixed/ambiguous-school, F-01/F-02/F-03, website, Phase 2/4, and full regression suites.
5. Live Ollama + Chroma verification if reachable; otherwise document the exact environment boundary and do not convert it into a QA PASS.

## 9. Lead Coder Verdict

**READY_FOR_QA** — the code change and regression suites are complete. The latest independent QA verdict remains `BLOCKED` pending QA review of this patch and a QA-accessible live runtime. No deployment was performed.
