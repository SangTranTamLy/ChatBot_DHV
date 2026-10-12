# CHATBOT PLAN FOLLOW-UP IMPLEMENTATION REPORT

## 1. Scope

Implemented the approved runtime plan for safe multi-issue handling, verified answers, and first-turn navigation. This work covers the pre-RAG question splitter, prompt safeguards, deterministic evidence answers in multi-issue routes, website counting regression, and welcome quick actions.

Out of scope and unchanged: production deployment, model/embedding changes, evaluation Q&A data, RAW PDFs, PDF/OCR extraction, dataset expansion, and Chroma rebuild.

## 2. Confirmed Root Causes

1. Some natural compound questions were not split by deterministic rules. Their first detected intent could govern retrieval and omit another requested issue.
2. Multi-issue processing used an LLM for scholarship answers even though a deterministic evidence formatter existed on the single-issue path. The validator's global token overlap could accept an unrelated generated sentence or fabricated `(#)` link.
3. The answer prompt's generic Fanpage/Hotline fallback could encourage unsupported contact claims.
4. A full-suite ingestion test attempted to write semantically identical page-text and structured-record chunks with the same Chroma ID.
5. Two other full-suite failures were stale test contracts: Task M treated every URL printed inside a PDF as provenance, and the processed-data migration test hard-coded an unverified-file count that no longer matched the manifest.

## 3. Architecture Before / After

**Before:** deterministic analysis/router → retrieval → evidence → LLM answer. Simple known intents could use deterministic responses, but unplanned compound questions had no separate LLM decomposition stage; multi-issue scholarship could fall back to free generation.

**After:** deterministic safety/scope/year/clarification gates → optional split-only local LLM for eligible complex in-scope questions → re-analyse and deterministically route every verbatim sub-question → independent retrieval/evidence/answer per issue → merge in user order. The planner cannot answer, select evidence, or change scope. Unsafe, ambiguous, or unroutable splits are rejected before retrieval.

## 4. Implementation

- Added a pre-RAG decomposer for eligible, unresolved compound questions. It accepts only 2–4 ordered verbatim spans, checks source coverage, and re-runs existing school/scope/intent/router checks for each span. Simple facts, existing deterministic multi-plans, list/count requests, clarification, and external/mixed/ambiguous scope bypass the planner.
- Updated the answer prompt to preserve issue order, keep evidence isolated by issue, state unsupported portions, and prohibit invented contact channels or inline/generated links.
- Multi-issue scholarship answers now use the evidence-backed deterministic formatter and validator rather than free generation. No-evidence cases remain fail-closed. Scholarship document/section headings that contain no answer fact are excluded from the rendered summary.
- The validator strips arbitrary Markdown link destinations (including `#` and `javascript:`) and rejects Fanpage/hotline/social-channel claims absent from selected evidence. Unsupported contact-channel output is retryable so the model can correct it from the source.
- Added four first-turn quick actions in the Streamlit welcome state. They submit normal chatbot questions through the existing service; the score label is explicitly 2026 because the active verified collection is 2026-only.
- Prevented duplicate Chroma IDs when page text is identical to a semantic record, preserving the structured record.
- Corrected stale test assertions to follow the current manifest/provenance contract; no expected factual answers or evaluation questions were changed.

## 5. Files Changed

| File | Area | Reason |
|---|---|---|
| `app.py` | Welcome quick actions | Add four tested starter queries without changing the chat service contract. |
| `src/chatbot/query_decomposer.py` | New pre-RAG split-only stage | Validate model-proposed question spans before routing/retrieval. |
| `src/chatbot/query_analysis.py` | Intent ordering/category mapping | Preserve issue order and map registration questions to canonical verified categories. |
| `src/chatbot/rag_chain.py` | Pre-RAG orchestration, multi-issue answers and trace | Re-route validated spans; keep each evidence bundle separate; use deterministic scholarship answer and aggregate trace counts. |
| `src/chatbot/evidence.py` | Evidence intent filter | Keep category-compatible evidence relevant to the requested issue. |
| `src/chatbot/output_validator.py` | Link/contact defense | Remove untrusted Markdown links and reject unsupported contact-channel claims. |
| `src/chatbot/scope_guard.py` | School boundary safeguards | Preserve the external/mixed/ambiguous boundary regressions already in this worktree. |
| `src/prompts/rag_prompt.py` | Overall answer prompt | Strengthen evidence-only, no-cross-issue, no-invented-contact/link instructions. |
| `src/ingestion/structured_json.py` | Chunk identity | Avoid duplicate IDs for semantically duplicated page-text/record content. |
| `tests/test_app.py` | Welcome action tests | Verify four choices and that a selected choice reaches the normal chat service. |
| `tests/test_query_decomposer.py` | New planner tests | Cover strict spans, unsafe routes, prompt contract and independent retrievals. |
| `tests/test_task_09.py` | Multi-issue regressions | Cover overview, scholarship, no unrelated claim, and fail-closed behavior. |
| `tests/test_priority_1_2_fix.py` | Validator regressions | Cover unsafe links and unsupported contact channels. |
| `tests/test_task_c.py` | Contact retry tests | Keep evidence-correct retry behavior. |
| `tests/test_task_m.py` | Provenance contract | Validate manifest source provenance separately from links printed inside PDF content. |
| `tests/test_task_processed_md_to_json_migration.py` | Manifest-based count | Derive skipped-unverified count from current canonical manifest. |

No dataset, RAW PDF, model, embedding, or Chroma files were changed.

## 6. Runtime Traces

Runtime used local Ollama (`qwen2.5:3b` and `nomic-embed-text`) and the configured active Chroma collection; no mock retriever was used for the traces below.

| Query | Scope / intent | Retrieval | Evidence | Result |
|---|---|---:|---:|---|
| `Em muốn biết cách đăng ký tuyển sinh DHV và học phí năm 2026.` | DHV / `MULTI_ISSUE`; pre-RAG split accepted into registration + tuition | 2 calls, 5 docs | 3 | `ok`; both sections answered from official DHV sources; sub-statuses both `ok`. |
| `Thông tin trường DHV` | DHV / `SCHOOL_INFO` | 1 call, 25 docs | 25 | `ok`; overview only, source `https://dhv.edu.vn/`. |
| `Thông tin trường DHV và học bổng DHV` | DHV / overview + scholarship | 2 calls, 29 docs | 14 | `ok`; both sections answered. Scholarship uses selected evidence, with no generated tuition relationship or `(#)` link. |
| `Trường DHV có bao nhiêu website?` | DHV / website count (`COUNT`) | 1 call, 25 docs | 25 | `ok`; count 2 with `https://dhv.edu.vn/` and `https://tuyensinh.dhv.edu.vn/`. |
| `Điểm chuẩn Bách Khoa?` | `OTHER_SCHOOL` / `external_school` | **0** | **0** | `out_of_scope`; no DHV evidence/source in answer. |

## 7. Chroma / Data

- Active path: `chroma_db`; collection: `dhv_admissions_2026`.
- Read-only collection audit: **310 records**, only `year=2026`, `status=verified`, `school_code=DHV`; categories are the configured DHV admissions/school-information categories.
- Live retrieval returned relevant registration, tuition, overview, scholarship and website evidence.
- **No Chroma rebuild**: this task did not regenerate or change processed facts. The ingestion change prevents duplicate IDs on a future canonical build; it does not require changing the active collection now.
- Full source-hash equality between every processed JSON file and Chroma was not independently recomputed in this follow-up; QA may check it if required by its corpus-freshness protocol.

## 8. Tests

| Suite | Result |
|---|---|
| Targeted query decomposition, Task C, UI, Priority 1+2, Task 09, Task L, intent, full-sweep, ingestion, Task M, migration | **196 passed, 155 subtests passed** |
| Full pytest suite | **291 passed, 4 skipped, 295 subtests passed, 0 failed** |

Windows sandbox Temp ACL initially blocked tests that created temporary directories outside the workspace. Rerunning with Python's temporary directory directed to the existing project `.test_tmp` completed both suites successfully. Existing `.test_tmp` contents were not deleted.

## 9. Known Remaining Risks

1. The pre-RAG model step is intentionally optional and only attempts eligible complex questions; it does not run for every user message. Invalid splits fail closed to the existing deterministic route.
2. LLM validation is not a general natural-language entailment proof. Known structured paths now use deterministic evidence answers, but QA should adversarially test free-form explanations and partial multi-issue evidence.
3. The verified corpus is 2026-only. The live registration answer quotes a source deadline of 13/08/2026; that date is now past relative to 09/10/2026. This task did not alter corpus facts or add a current-cycle policy, so QA/product owner should decide how the chatbot should present elapsed dates.
4. The welcome actions are covered by Streamlit AppTest, not a separately launched browser session.
5. Website URLs are rendered as direct evidence-backed links; model-generated links are stripped.

## 10. Acceptance Snapshot

| Requirement | Status |
|---|---|
| Separate pre-RAG splitter for eligible complex questions | PASS — validates spans and re-routes before retrieval. |
| Scope boundary runs before planner/retrieval | PASS — external Bách Khoa live trace has zero retrieval/docs/evidence. |
| Compound question returns separate requested issues in order | PASS — live registration + tuition trace. |
| Multi-issue overview/scholarship does not generate unrelated claims/links | PASS — deterministic scholarship answer and validator defense; QA review pending. |
| Website count answers both verified official sites | PASS — live count 2. |
| Welcome menu routes through normal service | PASS — AppTest. |
| Full pytest and targeted suite | PASS — results above. |
| Active Chroma rebuilt | NOT DONE — not needed; no processed facts changed. |
| QA/Security final approval | PENDING — Lead Coder cannot issue final QA verdict. |
| Deployment | NOT DONE — prohibited for this task. |

## 11. Handoff To QA & Security

Review the actual changed code and independently rerun the targeted/full suites. Required cases include:

1. The live compound registration + tuition query, checking split spans, sub-intents, per-subplan evidence, source URLs and final answer.
2. Natural overview + scholarship, overview + website, overview + admissions portal, and missing-intro-evidence cases; verify every asked issue is either answered with its own evidence or explicitly no-data.
3. Scholarship output must not invent tuition conditions, Fanpage/Hotline, social URLs, or placeholder links; test accented and unaccented content if model generation is involved.
4. Website count returns only verified DHV hostnames; external/mixed/ambiguous school queries stop before retrieval.
5. Welcome action selection sends the expected question through the chat service.
6. Existing Task 09, SEC-001/SEC-002, CORE/STATE, count/list, wrong-year, Task C, Task M and migration regressions.

**Required QA deliverable:** `reports/QA_CHATBOT_PLAN_FOLLOWUP_RETEST_REPORT.md`. It must identify the exact snapshot/files reviewed; list the exact test command and passed/failed/skipped counts; record each query's input, expected/actual, intent, school/scope, retrieval calls, docs, evidence, validator/status and sources; include repro/severity/root-cause for every finding; distinguish product failures from Windows/Ollama environment blocks; and end with QA's own `PASS`, `FAIL` or `BLOCKED`. A task is not complete without this report.

## 12. Handoff To DevOps/SRE (After QA PASS Only)

No deployment is authorized. After QA reports PASS, DevOps/SRE may independently verify only the local runtime environment: Python/dependencies, Ollama endpoint and required models, configured Chroma path/collection/count, ports/health and reproducibility of the smoke trace. Do not rebuild Chroma, change business logic, or deploy.

**Required DevOps/SRE deliverable:** `reports/DEVOPS_LOCAL_RUNTIME_VERIFICATION_REPORT.md`, including OS/Python/dependency versions, Ollama health/models, Chroma configuration/count, exact checks/commands and results, logs/errors, whether anything was changed, and a clear `BLOCKED` or local-runtime-ready conclusion. No report means no completed handoff.

## 13. Lead Coder Verdict

**READY_FOR_QA** — implementation and regression checks are complete. This is not `FULL_QUESTION_SWEEP_PASS` and not QA's final approval. Do not deploy.
