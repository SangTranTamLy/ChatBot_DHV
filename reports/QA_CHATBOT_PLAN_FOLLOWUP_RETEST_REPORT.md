# QA & SECURITY – CHATBOT PLAN FOLLOW-UP RETEST REPORT

## 1. Scope

Independent QA/Security review of the current working tree for:

- compound-question decomposition and per-issue retrieval/evidence;
- school overview, scholarship, website/cổng tuyển sinh and missing-evidence behavior;
- verified DHV website counting;
- external, mixed and ambiguous school boundaries;
- output-validator link/contact-channel defenses;
- welcome quick actions;
- Task 09, SEC-001/SEC-002, CORE/STATE, count/list, wrong-year, Task C, Task M and processed-JSON migration regressions.

QA did not modify source code, datasets, expected answers, Chroma contents or deployment configuration. No Chroma rebuild/reset and no deployment were performed.

Independent verdict: FAIL. One reproducible product regression remains. Full Ollama E2E is additionally blocked by the local Windows environment.

## 2. Snapshot and Files Reviewed

Snapshot:

- Project: C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV
- HEAD: f6016fb chore(repo): organize files and ignore generated artifacts
- Working tree contains Lead-Coder changes in app.py, chatbot routing/RAG/validator/scope/evidence/prompt modules, ingestion metadata, regression tests, and the new src/chatbot/query_decomposer.py plus tests/test_query_decomposer.py.
- Active Chroma: chroma_db, collection dhv_admissions_2026.
- Chroma read-only audit: 310 records; all records observed as year=2026, status=verified, school_code=DHV; no 2024/unverified record observed.

Reports reviewed:

- reports/TONG_QUAN_AGENT
- reports/CHATBOT_PLAN_FOLLOWUP_IMPLEMENTATION_REPORT.md
- reports/CHATBOT_OVERVIEW_WEBSITE_FIX_REPORT.md
- reports/FULL_SWEEP_P1_FIX_REPORT.md
- reports/SEC_002_FIX_REPORT.md

Implementation files reviewed:

- app.py
- src/chatbot/query_decomposer.py
- src/chatbot/query_analysis.py
- src/chatbot/scope_guard.py
- src/chatbot/rag_chain.py
- src/chatbot/evidence.py
- src/chatbot/output_validator.py
- src/chatbot/year_semantics.py
- src/retrieval/retriever.py
- src/prompts/rag_prompt.py
- src/ingestion/structured_json.py

Regression files reviewed/run:

- tests/test_query_decomposer.py
- tests/test_task_09.py
- tests/test_priority_1_2_fix.py
- tests/test_full_sweep_p1.py
- tests/test_phase2_runtime.py
- tests/test_phase4_answer_behavior.py
- tests/test_task_c.py
- tests/test_task_f.py
- tests/test_task_i.py
- tests/test_task_k.py
- tests/test_task_l.py
- tests/test_task_m.py
- tests/test_task_processed_md_to_json_migration.py
- tests/test_app.py
- tests/test_task_response_ui.py

## 3. Environment and Runtime Boundary

Configured runtime:

- Python: 3.12.14
- LLM: qwen2.5:3b
- Embedding: nomic-embed-text
- Chroma collection: dhv_admissions_2026
- Target year: 2026
- OS: Windows

Ollama probe:

~~~powershell
Invoke-WebRequest -UseBasicParsing http://localhost:11434/api/tags -TimeoutSec 5
Get-Process ollama
~~~

Result: endpoint access failed with an attempt to access a socket in a way forbidden by its access permissions; no ollama process was available. This is classified as ENVIRONMENT_BLOCKED, not as a product assertion failure.

Consequences:

- Real Ollama planner/generation and real embedding retrieval could not be independently rerun in this environment.
- Deterministic production paths, current Chroma evidence boundaries, controlled evidence replay, scope guards and validator defenses were still exercised.
- Claims in Lead reports that depend on a live Ollama trace are not independently confirmed here.

## 4. Exact Test Commands and Results

Initial targeted command, with the default Windows temporary directory:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_query_decomposer.py tests/test_task_09.py tests/test_priority_1_2_fix.py tests/test_full_sweep_p1.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_task_c.py tests/test_task_f.py tests/test_task_i.py tests/test_task_k.py tests/test_task_l.py tests/test_task_m.py tests/test_task_processed_md_to_json_migration.py tests/test_app.py tests/test_task_response_ui.py
~~~

Initial result: 222 passed, 2 failed, 265 subtests. Both failures were Windows WinError 5 cleanup errors from tempfile.TemporaryDirectory, not assertion failures.

The same targeted command was rerun with the existing ignored workspace temp directory:

~~~powershell
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q tests/test_query_decomposer.py tests/test_task_09.py tests/test_priority_1_2_fix.py tests/test_full_sweep_p1.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_task_c.py tests/test_task_f.py tests/test_task_i.py tests/test_task_k.py tests/test_task_l.py tests/test_task_m.py tests/test_task_processed_md_to_json_migration.py tests/test_app.py tests/test_task_response_ui.py
~~~

Final targeted result: 224 passed, 0 failed, 265 subtests.

Full regression:

~~~powershell
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q
~~~

Full result: 291 passed, 4 skipped, 0 failed, 295 subtests.

Additional checks:

- python -m compileall -q src app.py: PASS.
- python -m pip check: PASS (No broken requirements found).
- git diff --check: could not be executed because the current Git invocation reported fatal: this operation must be run in a work tree; this did not affect pytest or source inspection.

The four skipped tests were not converted to PASS. No test expectation was changed by QA.

## 5. Compound Question

Input:

Em muốn biết cách đăng ký tuyển sinh DHV và học phí năm 2026.

Expected:

- split into registration and tuition issues;
- MULTI_ISSUE;
- two independent retrieval/evidence paths;
- no evidence cross-use;
- answer both issues with official 2026 sources.

Controlled current-Chroma evidence replay, using a strict verbatim-span planner double and grounded answer double:

| Field | Actual |
|---|---|
| intent | MULTI_ISSUE |
| target school / scope | DHV / in_scope_dhv |
| pre-RAG parts | Em muốn biết cách đăng ký tuyển sinh DHV; học phí năm 2026 |
| sub-intents | HOI_DANG_KY_XET_TUYEN; HOI_HOC_PHI |
| retrieval calls | 2 |
| retrieved docs | 16 total, subplans 15 + 1 |
| selected evidence | 5 total, subplans 4 + 1 |
| sub-status | ok, ok with grounded answer double |
| sources | https://tuyensinh.dhv.edu.vn/; https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026-va-thong-tin-tu-van-vien-ho-tro-tan-sinh-vien/ |

The code-level split contract and trace aggregation pass tests/test_query_decomposer.py.

Real default runtime attempt:

- planner result: rejected / planner_unavailable;
- fallback intent: HOI_DANG_KY_XET_TUYEN;
- with an empty test retriever: 1 retrieval call, 0 docs, 0 evidence, no_data;
- this is an Ollama environment block, not evidence that the production planner is correct or incorrect under Qwen.

Assessment: deterministic/controlled path PASS; live LLM E2E BLOCKED.

## 6. Overview and Multi-Issue Answers

### 6.1 Single overview

Input: Thông tin trường DHV

| Field | Actual |
|---|---|
| intent / mode | SCHOOL_INFO / OVERVIEW |
| school / scope | DHV / in_scope_dhv |
| retrieval / docs / evidence | 1 / 25 / 25 |
| validator | ok |
| status | ok |
| source | https://dhv.edu.vn/ |
| factual leakage check | no tuition numeric, scholarship numeric, hotline or social-link claim |

The response is bounded to the verified introduction evidence.

### 6.2 Overview + scholarship

Input: Thông tin trường DHV và học bổng DHV

Controlled current-Chroma trace:

- intent: MULTI_ISSUE;
- sub-intents: SCHOOL_INFO, HOI_HOC_BONG;
- retrieval calls: 2;
- docs/evidence: 62 / 43 total, split 25+37 docs and 6+37 evidence;
- sub-statuses: ok, ok;
- answer sections: both Thông tin trường and Học bổng;
- LLM generation calls: 0 on this deterministic path;
- no (#), Fanpage or Hotline claim.

Scholarship evidence legitimately contains policy wording referring to tuition support. It is not a fabricated tuition amount and was not used as the single-overview answer.

### 6.3 Overview + website / admissions portal

Inputs:

- Thông tin trường DHV và website trường?
- Giới thiệu về trường DHV và cổng tuyển sinh?

Actual controlled traces:

| Input | Intents | Calls | Docs | Evidence | Status | Sources |
|---|---|---:|---:|---:|---|---|
| overview + website | SCHOOL_INFO, HOI_CO_SO_LIEN_HE | 2 | 50 | 12 | ok | https://dhv.edu.vn/ |
| overview + portal | SCHOOL_INFO, HOI_CO_SO_LIEN_HE | 2 | 50 | 12 | ok | https://dhv.edu.vn/, https://tuyensinh.dhv.edu.vn/ |

Both requested sections were rendered. No model-generated link was required.

### 6.4 Missing overview evidence

Single overview with intro chunks deliberately removed:

- status: no_data;
- intent: SCHOOL_INFO;
- retrieval/docs/evidence: 1 / 20 / 20 candidate/selected trace in the replay;
- validator/boundary: overview_intro_evidence_unavailable;
- sources: empty;
- LLM generation: not called.

Multi-issue missing-intro regression in tests/test_task_09.py also passes: the overview subplan is no_data with school_overview_missing_matching_evidence, scholarship remains independently evidence-backed, and no LLM fallback is called. Evidence counts are aggregated from subplans rather than overwritten.

Assessment: PASS for bounded overview and fail-closed missing-intro behavior.

## 7. Website Count and Specific Websites

Inputs:

- Trường DHV có bao nhiêu website?
- DHV có mấy trang web?
- truong DHV co may trang web?

Each actual current-Chroma deterministic trace:

- intent: HOI_CO_SO_LIEN_HE;
- query mode: COUNT;
- target/scope: DHV / in_scope_dhv;
- retrieval/docs/evidence: 1 / 25 / 25;
- status: ok;
- count: 2;
- URLs: https://dhv.edu.vn/ and https://tuyensinh.dhv.edu.vn/;
- sources carry titles Website trường and Cổng tuyển sinh 2026.

The implementation accepts only HTTPS DHV hosts/subdomains, deduplicates by hostname and does not invent a URL. The website branch uses its own verified-provenance gate rather than generic LLM validation.

Specific website regression:

- website chính của DHV là gì?: ok, 1/25/25, source https://dhv.edu.vn/.
- Cổng tuyển sinh DHV ở đâu?: ok, 1/25/25, source https://tuyensinh.dhv.edu.vn/.
- website Khoa Kỹ thuật Công nghệ là gì?: safe no_data, no source and no fabricated tec.dhv.edu.vn.
- website Viện Đào tạo Sau đại học?: FAIL; detailed finding QA-FUP-001 below.

## 8. External, Mixed and Ambiguous School

The following matrix was run with a counting retriever. Every row below had retriever calls 0, docs 0, evidence 0 and empty sources:

| Input | Target school | Scope | Status |
|---|---|---|---|
| Điểm chuẩn Bách Khoa? | OTHER_SCHOOL | external_school | out_of_scope |
| diem chuan bach khoa? | OTHER_SCHOOL | external_school | out_of_scope |
| Điểm chuẩn Văn Hiến? | OTHER_SCHOOL | external_school | out_of_scope |
| Học phí Hoa Sen? | OTHER_SCHOOL | external_school | out_of_scope |
| Văn Lang có học bổng không? | OTHER_SCHOOL | external_school | out_of_scope |
| Nguyễn Tất Thành có xét học bạ không? | OTHER_SCHOOL | external_school | out_of_scope |
| Điểm chuẩn Bách Khoa TP.HCM? | OTHER_SCHOOL | external_school | out_of_scope |
| Học phí trường Bách Khoa? | OTHER_SCHOOL | external_school | out_of_scope |
| Điểm chuẩn trường đại học khác? | OTHER_SCHOOL | external_school | out_of_scope |
| So sánh DHV và Văn Hiến | MIXED | mixed_school | out_of_scope |
| DHV và Đại học FPT có bao nhiêu website? | MIXED | mixed_school | out_of_scope |
| Điểm chuẩn Hùng Vương? | AMBIGUOUS | ambiguous_school | clarification |

The external-school boundary is also covered by Priority/SEC-002 tests, including accented/unaccented external names and explicit DHV override.

Assessment: PASS. No DHV factual leakage was observed in this matrix.

## 9. Validator and Security Retest

Evidence used for the direct validator test was verified DHV 2026 contact evidence.

| Input answer | Expected | Actual |
|---|---|---|
| Tổng đài... 0287 1000 888. [Xem thêm](#) https://evil.example/ | strip unsafe targets, keep grounded fact | ok; answer retains fact and label, no URL |
| Fanpage DHV: https://facebook.com/evil | reject unsupported channel | no_data, reason unsupported_contact_channel |
| Hotline DHV: 0909 999 999 with evidence lacking that channel/value | reject and retry | runtime retry returned verified 0287 1000 888 |
| DHV hợp tác với Đại học FPT with generic partnership evidence | reject named unsupported institution | no_data, institution_mismatch |
| DHV hop tac voi Dai hoc FPT with same evidence | reject unaccented bypass | no_data, institution_mismatch |
| DHV evidence supplied while analysis target is OTHER_SCHOOL | reject cross-school evidence | no_data, school_scope_boundary |

javascript:/# link destinations are removed by sanitize_answer. No unsafe URL reached the returned answer in this test. This is sanitization, not proof that every natural-language claim is entailed; live Qwen generation remains environment-blocked.

## 10. Conversation State, Coreference and Scope Regression

Targeted suites passed for:

- Điểm chuẩn CNTT? → Còn học phí?: current major remains conversation state, but tuition plan has no major_name filter.
- generic Học phí của trường bao nhiêu?: no stale major retrieval filter.
- Còn Luật?: explicit major override changes current major to Luật.
- Văn Hiến... → Còn điểm chuẩn?: external school remains external, zero retrieval.
- Văn Hiến... → Còn DHV?: explicit DHV override enables DHV retrieval.
- Xin chào and Cảm ơn: system intents, zero retrieval and no factual answer.
- list/coreference and ordinal method/program/major cases: targeted CORE/STATE assertions pass.

One design note: greeting/thanks preserve bounded state slots for a later follow-up, but they do not retrieve or emit stale facts in the tested turn. This is existing state policy, not classified as a failure in this retest.

## 11. Welcome Quick Action and UI

tests/test_app.py passed. The welcome screen exposes four quick actions:

- Chỉ tiêu tuyển sinh
- Học phí
- Điểm chuẩn 2026
- Cách thức nộp hồ sơ

AppTest verified that the empty state renders without exception and selected starters use the normal chatbot service path. No browser/Ollama UI E2E was claimed because Ollama was unavailable.

## 12. Wrong-Year, Count/List, Task C/M and Migration

- Active Chroma audit found only verified 2026 DHV records.
- Thông tin trường DHV 2027? and website count with 2027 returned no_data, zero retrieval and zero evidence.
- Task 09 runtime-year tests passed.
- Count/list and query-mode tests passed in the targeted and full suites.
- Task C tests passed after workspace-temp rerun.
- Task M and processed JSON migration tests passed in the current working tree.

This differs from the older FULL_SWEEP_P1_FIX_REPORT.md, which records three historical full-pytest failures. On the current snapshot, the corrected/updated suite is green. The older report is therefore stale for those three metrics (REPORT_CODE_MISMATCH / STALE_REPORT), not evidence that the current runtime is failing those tests.

## 13. Findings

### QA-FUP-001 — Institute website request returns unrelated overview

- Severity: MEDIUM
- Component: query analysis and multi-issue orchestration
- Input: website Viện Đào tạo Sau đại học?
- Expected: one specific website/contact issue; because current verified evidence has no ipic.dhv.edu.vn record, return no_data with empty sources and no unrelated overview.
- Actual:
  - intent: MULTI_ISSUE;
  - sub-intents: HOI_CO_SO_LIEN_HE, SCHOOL_INFO;
  - retrieval calls: 2;
  - retrieved docs: 50;
  - selected evidence: 12;
  - website sub-status: no_data, boundary requested_website_not_in_verified_evidence;
  - overview sub-status: ok;
  - final status: ok;
  - final answer includes a generic Thông tin trường overview even though the user asked for the institute website;
  - source includes https://dhv.edu.vn/, but not a verified institute URL.
- Root cause: _is_school_info_request() treats vien dao tao sau dai hoc as SCHOOL_INFO even when the same question is a specific website request. That adds an unintended overview subplan; _ask_multi_issue() then merges the unrelated successful overview with the requested website no_data section.
- Evidence: independent current-Chroma replay and direct analyze_question()/route_question() inspection; the same routing behavior is not caught by the current Task 09 suite.
- Affected files: src/chatbot/query_analysis.py, src/chatbot/rag_chain.py.
- Owner: LEAD_CODER.
- Acceptance criterion failed: specific school-unit website queries must not omit the requested issue or add unrelated overview content; missing verified URL must fail closed.
- Required regression:
  - website Viện Đào tạo Sau đại học? must be HOI_CO_SO_LIEN_HE, not MULTI_ISSUE;
  - retrieval may search only the requested website/contact evidence;
  - with no verified institute URL: final no_data, sources empty, no Thông tin trường section;
  - add equivalent tests for a faculty and an institute, accented and unaccented.

### ENV-FUP-001 — Ollama local endpoint unavailable

- Severity: environment blocker, not product severity.
- Reproduction: Invoke-WebRequest http://localhost:11434/api/tags -TimeoutSec 5.
- Actual: Windows socket permission error; no Ollama process.
- Impact: no independent live Qwen planner/generation/embedding trace.
- Owner: DEVOPS_SRE.
- This blocks live-runtime confirmation but does not convert deterministic test results into PASS.

## 14. Report/Code Consistency

The Lead implementation report claims the exact compound and overview traces were run with live Ollama. The current QA environment cannot reproduce those live traces because Ollama is unavailable, so those claims remain unverified rather than accepted blindly.

The older P1 report records 3 failed full-pytest tests. The current snapshot/full command produced 291 passed, 4 skipped, 0 failed; this is a stale-report mismatch, not a current test failure.

## 15. Handoff to Lead Coder

Priority 1:

- QA-FUP-001: fix specific institute/faculty website routing so a missing requested URL cannot trigger an unrelated SCHOOL_INFO subplan or final overview answer.
- Add runtime-path tests for website Viện Đào tạo Sau đại học?, website Khoa Kỹ thuật Công nghệ là gì?, and unaccented variants.
- Re-run Task 09, query-analysis, multi-issue, validator and external-school suites.

Priority 2:

- Re-run exact compound registration + tuition and multi-issue overview cases with Ollama enabled.
- Record per-subplan answer/source mapping in the QA trace and verify no LLM unsupported claims.

Priority 3:

- Verify the full canonical runtime sweep after the routing fix; inspect skipped tests and keep environment failures separate from product failures.

QA rerun acceptance:

- no unrelated overview in specific unit website queries;
- missing verified unit URL returns no_data, empty sources and no fabricated URL;
- overview + website/portal still returns both requested sections;
- external/mixed/ambiguous school cases remain zero retrieval/docs/evidence;
- targeted and full pytest remain green;
- Ollama live trace is available or explicitly documented as blocked.

## 16. Final Verdict

FAIL

Reason:

1. QA-FUP-001 is a reproducible functional regression in the requested website/unit path.
2. Live Ollama E2E could not be independently confirmed due an environment block.
3. The targeted and full offline/controlled regression suites pass, and external-school/security boundaries pass, but those results do not close the specific website regression or justify a full QA PASS.

No deployment was performed.
