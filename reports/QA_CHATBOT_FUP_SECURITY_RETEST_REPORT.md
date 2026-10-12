# QA & SECURITY – QA-FUP-001 / F-01 / F-02 / F-03 RETEST REPORT

## 1. Scope

This is an independent QA and Security retest of the current working tree for:

- QA-FUP-001: specific faculty/institute website requests must not fall through to an unrelated school overview.
- F-01: overview gating and multi-issue trace safety when detail markers are present and verified introduction evidence is absent.
- F-02: validator rejection of unsupported external-institution claims, including accented and unaccented "Đại học FPT".
- F-03/security regressions: unsafe links, unsupported contact channels, and external/mixed/ambiguous-school boundaries.

No source code, dataset, expected answer, or QA test source was modified by QA. No Chroma rebuild, reset, upsert, or deploy was performed.

## 2. Snapshot and Files Reviewed

Repository HEAD at review start:

- Commit: f6016fb — chore(repo): organize files and ignore generated artifacts
- Working tree: dirty because Lead Coder changes are not committed. QA did not alter those changes.

The following implementation areas were reviewed directly:

- src/chatbot/scope_guard.py
- src/chatbot/query_analysis.py
- src/chatbot/year_semantics.py
- src/chatbot/rag_chain.py
- src/retrieval/retriever.py
- src/chatbot/evidence.py
- src/chatbot/output_validator.py
- src/chatbot/query_decomposer.py
- src/prompts/rag_prompt.py
- app.py
- tests/test_task_09.py
- tests/test_priority_1_2_fix.py
- tests/test_query_decomposer.py
- regression tests for Phase 2, Phase 4, Task C, Task I, Task K, Task L, Task M, migration, full-sweep P1, and UI/app contracts.

Current modified/untracked paths reported by git status --short were preserved and not changed by QA:

app.py, src/chatbot/evidence.py, src/chatbot/output_validator.py, src/chatbot/query_analysis.py, src/chatbot/rag_chain.py, src/chatbot/scope_guard.py, src/ingestion/structured_json.py, src/prompts/rag_prompt.py, tests/test_app.py, tests/test_priority_1_2_fix.py, tests/test_task_09.py, tests/test_task_c.py, tests/test_task_m.py, tests/test_task_processed_md_to_json_migration.py, src/chatbot/query_decomposer.py, and the existing reports/ worktree content.

## 3. Runtime Environment

### Chroma

Read-only probe:

~~~text
collection = dhv_admissions_2026
count = 310
years = 2026: 310
status = verified: 310
school_code = DHV: 310
metadata source URL hosts currently observed = dhv.edu.vn, tuyensinh.dhv.edu.vn
~~~

The active collection was opened for read-only inspection only. It was not rebuilt, reset, or written.

### Ollama

Checks performed:

- Get-Process ollama returned no running process.
- Invoke-WebRequest -UseBasicParsing -Uri http://localhost:11434/api/tags -TimeoutSec 5 failed with:

~~~text
System.Net.Http.HttpRequestException:
An attempt was made to access a socket in a way forbidden by its access permissions. (localhost:11434)
~~~

A real default-path call for "Thông tin trường DHV" returned:

~~~text
status = ollama_offline
answer = Hiện tại dịch vụ trả lời cục bộ chưa sẵn sàng. Bạn vui lòng thử lại sau.
sources = []
retrieval_calls = 0
retrieved_docs_count = 0
evidence_count = 0
~~~

This is an environment block, not a product assertion failure. It prevents independent live embedding/LLM E2E confirmation.

## 4. Exact Commands and Test Results

### Targeted suites

~~~powershell
$env:PYTHONPATH='.'
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q tests/test_task_09.py tests/test_query_decomposer.py tests/test_priority_1_2_fix.py tests/test_full_sweep_p1.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_task_c.py tests/test_task_i.py tests/test_task_k.py tests/test_task_l.py tests/test_task_m.py tests/test_task_processed_md_to_json_migration.py tests/test_app.py
~~~

Result:

| Passed | Failed | Skipped | Subtests | Classification |
|---:|---:|---:|---:|---|
| 192 | 0 | 0 | 168 | PASS |

### Full pytest

~~~powershell
$env:PYTHONPATH='.'
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q
~~~

Result:

| Passed | Failed | Skipped | Subtests | Classification |
|---:|---:|---:|---:|---|
| 294 | 0 | 4 | 303 | PASS with 4 intentional/environment-dependent skips |

The four skips were not converted to passes and no expected result was changed.

### Static/dependency checks

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q src app.py
.\.venv\Scripts\python.exe -m pip check
~~~

Results:

- compileall: PASS.
- pip check: PASS — no broken requirements found.

## 5. Runtime Architecture Verified

The current code path is:

ask_chatbot → analyze_question → state enrichment/scope boundary → route_question → optional decomposition → retriever → evidence selection → deterministic website/overview/catalog logic or validated generation → output validator → final result and trace.

For external/mixed/ambiguous schools, ask_chatbot exits before retriever invocation. For website answers, _official_links_answer derives URLs from verified DHV metadata and returns no_data when the requested host is absent. For overview answers, _overview_intro_evidence and _evidence_overview_answer require a verified 2026 DHV overview introduction; the no-intro multi-issue branch does not enter LLM generation.

## 6. QA-FUP-001 Retest

The current guard _is_specific_school_unit_website_request() is checked before general school-info classification. It recognizes accented and unaccented faculty/institute names and preserves explicit overview wording for compound questions.

### Specific website matrix on active Chroma evidence replay

The following traces used a read-only adapter over the active 310-record Chroma collection. This verifies answer/evidence policy without pretending that the unavailable embedding service was live.

| Input | Expected | Actual trace | Actual answer/source | Result |
|---|---|---|---|---|
| website Viện Đào tạo Sau đại học? | HOI_CO_SO_LIEN_HE; missing requested URL must be no_data, no overview | intent HOI_CO_SO_LIEN_HE; target UNSPECIFIED; calls 1; docs 25; evidence 25; LLM calls 0; boundary requested_website_not_in_verified_evidence | status=no_data; fallback only; sources=[]; no overview facts | PASS |
| website Vien Dao tao Sau dai hoc? | Same behavior after normalization | intent HOI_CO_SO_LIEN_HE; target UNSPECIFIED; calls 1; docs 25; evidence 25; LLM calls 0; same boundary | status=no_data; sources=[]; no institute URL or overview | PASS |
| website Khoa Kỹ thuật Công nghệ là gì? | Missing faculty URL must not return overview | intent HOI_CO_SO_LIEN_HE; calls 1; docs 25; evidence 25; LLM calls 0; requested-host boundary | status=no_data; sources=[]; no overview | PASS |
| website Khoa Ky thuat Cong nghe la gi? | Same behavior without accents | intent HOI_CO_SO_LIEN_HE; calls 1; docs 25; evidence 25; LLM calls 0; requested-host boundary | status=no_data; sources=[]; no overview | PASS |

The nonzero internal selected-evidence count in these rows is not exposed as a factual answer: the requested unit URL is absent from verified source metadata, so the final answer and sources are fail-closed.

### Website/cổng tuyển sinh regression

| Input | Expected | Actual | Result |
|---|---|---|---|
| Website của trường là gì? | Main verified DHV website only | status=ok; intent HOI_CO_SO_LIEN_HE; calls 1; docs 25; evidence 25; LLM 0; source https://dhv.edu.vn/ only | PASS |
| Web tuyển sinh DHV? | Admissions portal only | status=ok; calls 1; docs 25; evidence 25; LLM 0; source https://tuyensinh.dhv.edu.vn/ only | PASS |

### Overview + institute/faculty website

| Input | Expected | Actual trace | Result |
|---|---|---|---|
| Thông tin trường DHV và website Viện Đào tạo Sau đại học | Preserve both issues; overview may answer from verified intro, missing institute URL must remain no_data | root MULTI_ISSUE; subplans SCHOOL_INFO, HOI_CO_SO_LIEN_HE; root calls 2; docs 50; evidence 12 (6+6); substatuses ok,no_data; boundaries null,requested_website_not_in_verified_evidence; LLM 0; sources only https://dhv.edu.vn/ | PASS |
| Thông tin trường DHV và website Khoa Kỹ thuật Công nghệ | Same two-issue behavior; no fabricated faculty URL | root MULTI_ISSUE; subplans SCHOOL_INFO, HOI_CO_SO_LIEN_HE; root calls 2; docs 50; evidence 12; substatuses ok,no_data; sources only verified overview source | PASS |

The compound answer retained an overview section and an explicit no-data contact section. It did not add institute/faculty URLs, tuition, scholarship, or unrelated contact facts.

## 7. F-01 Overview Gate and Trace Retest

Controlled evidence case:

Thông tin trường DHV và sự kiện, website, học bổng

The retriever returned verified 2026 detail-only evidence but deliberately no approved TỔNG QUAN VỀ TRƯỜNG introduction heading.

| Field | Actual |
|---|---|
| Root intent | MULTI_ISSUE |
| Subplans | SCHOOL_INFO, HOI_CO_SO_LIEN_HE, HOI_HOC_BONG |
| Root retrieval calls | 3 |
| Root retrieved docs | 3 |
| Root evidence count | 3 |
| Per-subplan statuses | no_data, ok, ok |
| Overview boundary | school_overview_missing_matching_evidence |
| LLM calls | 0 |
| Sources | Only the verified source attached to the website subplan; no overview source was emitted |

The unaccented detail-marker variant is covered by the targeted Task 09 regression test and passed. The overview subplan did not call the LLM and did not synthesize an overview from detail-only evidence. Root counts matched the sum of the subplan counts.

Result: PASS.

## 8. F-02 Validator and F-03 Security Retest

Generic evidence used:

DHV có hợp tác với các trường đại học quốc tế theo các thỏa thuận chung.

Evidence metadata was year=2026, school_code=DHV, status=verified, and official DHV source URL. It did not name FPT.

| Candidate model answer | Expected | Actual | Result |
|---|---|---|---|
| DHV hợp tác với Đại học FPT. | Reject unsupported institution | status=no_data; validation_reason=institution_mismatch; sources=[] | PASS |
| DHV hop tac voi Dai hoc FPT. | Same after accent folding | status=no_data; validation_reason=institution_mismatch; sources=[] | PASS |

Unsafe-link/contact checks:

| Input | Expected | Actual | Result |
|---|---|---|---|
| Xem [Fanpage](#) hoặc [trang lạ](javascript:alert(1)). | Strip unsafe link targets | Sanitized text retained labels only; no executable destination | PASS |
| Answer containing unsupported Fanpage | Reject unsupported channel | status=no_data; validation_reason=unsupported_contact_channel | PASS |
| Answer containing unsupported Hotline/Facebook | Reject unsupported channel/value | status=no_data; validation_reason=unsupported_contact_channel | PASS |

The validator checks school scope before accepting evidence, enforces verified year/school/source metadata, rejects unsupported institution names, and rejects unsupported contact-channel claims. The targeted tests also exercise these checks through the production ask_chatbot path where applicable.

## 9. External, Mixed, and Ambiguous School Boundary

All cases were run with recording retrievers that would fail the audit if called.

| Input | Expected target/scope | Actual status | Retrieval / docs / evidence | Result |
|---|---|---|---|---|
| Điểm chuẩn Bách Khoa? | OTHER_SCHOOL / external | out_of_scope | 0 / 0 / 0; LLM 0; sources [] | PASS |
| diem chuan bach khoa? | Same after normalization | out_of_scope | 0 / 0 / 0; sources [] | PASS |
| So sánh DHV và Văn Hiến | MIXED | out_of_scope | 0 / 0 / 0; sources [] | PASS |
| Điểm chuẩn Hùng Vương? | AMBIGUOUS; clarify before retrieval | clarification | 0 / 0 / 0; sources [] | PASS |
| DHV và Đại học FPT có bao nhiêu website? | MIXED; no DHV-only answer | out_of_scope | 0 / 0 / 0; sources [] | PASS |

No DHV factual numeric value or source leaked into these cases.

## 10. Regression Coverage

The targeted run included:

- Task 09 overview, website, portal, faculty/institute directory, count, missing URL, and no-intro overview gate.
- SEC-001/SEC-002 external school and validator regressions.
- CORE/STATE coreference and context inheritance.
- Phase 2 runtime behavior.
- Phase 4 answer behavior.
- Task C offline/error boundary.
- Task I/K/L/M.
- processed Markdown-to-JSON migration.
- query decomposition.
- app/welcome quick-action contract.
- full-sweep P1 regression suite.

The full pytest run covered the complete repository test inventory. No assertion failure or new regression was observed in the available offline/controlled environment.

## 11. Findings

### No reproducible product finding in the tested patch

QA-FUP-001, F-01, F-02, and the requested F-03 security boundaries passed the independent deterministic and controlled checks above.

### ENV-FUP-001 — Live Ollama E2E unavailable

- Severity: MEDIUM — environment blocker, not a product assertion.
- Reproduction: http://localhost:11434/api/tags fails with the Windows socket access error recorded in Section 3; no ollama process is running.
- Impact: Cannot independently verify live nomic-embed-text retrieval and qwen2.5:3b generation for the required questions.
- Evidence: default ask_chatbot("Thông tin trường DHV") returns ollama_offline with empty retrieval/evidence and the safe offline message.
- Owner: DEVOPS_SRE.
- Acceptance criterion: Ollama must expose the configured endpoint and required models; rerun the live smoke matrix and compare answer/evidence/source traces.

### Data availability note — unit URLs absent from active Chroma

- Severity: LOW / DATA_REVIEW note, not a failed safety behavior.
- Active Chroma currently exposes verified official source hosts for the main website and admissions portal. It does not expose verified metadata for the ipic.dhv.edu.vn or tec.dhv.edu.vn unit URLs.
- The implementation correctly returns no_data, empty sources, and no overview instead of inventing those URLs.
- Owner if unit URLs are required as a product feature: DATA_REVIEW.

## 12. Report / Code Consistency

- The previous QA report recorded QA-FUP-001 as a failure on an earlier working-tree state. The current helper, routing tests, and independent active-Chroma traces no longer reproduce that failure; that earlier result is a stale baseline for the current patch, not evidence that the old failure remains open.
- The Lead implementation report claimed deterministic website count, overview gating, and validator defenses. Those claims were independently reproduced in the current tests and controlled traces.
- The Lead report's live-runtime claims cannot be fully revalidated in this environment because Ollama is currently unavailable. They are therefore not promoted to live-E2E PASS.

## 13. Acceptance Criteria

| Criterion | Status |
|---|---|
| Accented and unaccented institute/faculty website requests do not misroute to overview | PASS |
| Missing institute/faculty URL returns no_data | PASS |
| Missing institute/faculty URL has empty sources | PASS |
| Missing institute/faculty URL does not return overview facts | PASS |
| Overview + institute/faculty website keeps both requested issue results | PASS |
| F-01 missing intro evidence blocks overview generation | PASS |
| F-01 overview subplan does not call LLM without intro evidence | PASS |
| F-01 root retrieval/docs/evidence trace equals subplan aggregation | PASS |
| F-02 rejects Đại học FPT claim | PASS |
| F-02 rejects Dai hoc FPT claim | PASS |
| Unsafe (#)/abnormal links are sanitized | PASS |
| Unsupported Fanpage/Hotline/Facebook claims are rejected | PASS |
| External/mixed/ambiguous school retrieval/docs/evidence are zero | PASS |
| Task 09 / Phase 2 / Phase 4 and full regression suites pass | PASS |
| Live Ollama + real embedding/LLM trace verified | BLOCKED |

## 14. Final Verdict

## BLOCKED

Offline/controlled QA evidence is PASS for QA-FUP-001, F-01, F-02, F-03, website/overview behavior, security validator cases, external-school boundaries, and regression suites. The required live Ollama + embedding runtime cannot be verified because the local endpoint is unavailable and Windows returns a socket-permission error. No deployment was performed.

