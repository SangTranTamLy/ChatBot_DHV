# QA & SECURITY – QUERY RECOGNITION / PRE-RAG DECOMPOSITION REVIEW

## 1. Scope

Independent review of only the current changes relevant to:

- admission-method recognition in src/chatbot/query_analysis.py;
- pre-RAG multi-issue decomposition in src/chatbot/query_decomposer.py;
- related tests in tests/test_query_decomposer.py;
- the existing rag_chain integration call that activates the decomposer.

Unrelated working-tree changes were not considered part of this review.

QA did not modify source code, datasets, expected answers, or tests. No Chroma rebuild/write and no deployment were performed.

## 2. Snapshot and Files

- HEAD: f6016fb
- Review date: 2026-10-11
- Working tree: contains unrelated Lead Coder changes and the new untracked query_decomposer.py/test file. They were preserved.

Reviewed directly:

- src/chatbot/query_analysis.py
- src/chatbot/query_decomposer.py
- tests/test_query_decomposer.py

Integration inspected only for this task:

- src/chatbot/rag_chain.py: _try_pre_rag_decomposition() and its call before retriever invocation.

## 3. Diff Review

### Admission-method recognition

The relevant changes:

- add natural-language markers for hình thức tuyển sinh, hình thức xét tuyển, phương án tuyển sinh, các/những cách tuyển sinh, tuyển sinh như thế nào, and related variants;
- add those markers to multi-issue detection;
- preserve list/count routing and category phuong_thuc_xet_tuyen;
- order detected issues by their first position in the normalized question;
- preserve target-school scope classification before retrieval.

The two requested list phrasings resolve to HOI_PHUONG_THUC_XET_TUYEN with query_mode LIST and category phuong_thuc_xet_tuyen.

### Pre-RAG decomposition

The new decomposer:

- is eligible only for supported in-scope intents;
- does not run for blocked school targets, clarification, list/count modes, or already split plans;
- limits output to 2–4 parts and bounded response/part lengths;
- requires contiguous verbatim spans from the original question;
- rejects reordered, overlapping, duplicate, rewritten, or omitted-content spans;
- re-analyzes and re-routes every span deterministically;
- rejects a part that is external, mixed, ambiguous, out of scope, system-only, or not independently routable;
- revalidates the school/year boundary before retrieval;
- records accepted/rejected pre_rag_decomposition trace data.

The integration runs after the initial scope boundary and before retrieval. External-school and out-of-scope requests therefore do not invoke the planner.

Security review result: no arbitrary planner text is used as a factual query without verbatim-span and deterministic-route validation. The prompt treats user question content as untrusted data.

## 4. Exact Test Command

~~~powershell
$env:PYTHONPATH='.'
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_query_decomposer.py tests/test_intent_classifier.py tests/test_priority_1_2_fix.py tests/test_full_sweep_p1.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_task_09.py
~~~

Result:

| Passed | Failed | Skipped | Subtests | Result |
|---:|---:|---:|---:|---|
| 162 | 0 | 0 | 155 | PASS |

The exact command completed successfully in 24.67 seconds.

## 5. Independent Case Traces

The primary traces below used a recording retriever returning no documents and recording planner/answer doubles. This validates routing, planner activation, call boundaries, and trace fields. They are controlled tests, not live Ollama results.

The final trace scope_reason becomes related_no_data for in-scope empty-evidence results because the result planner annotates a safe no-data boundary. The initial normalized analysis scope_reason is recorded separately where relevant.

### Case 1

Input: Trường mình có những hình thức tuyển sinh nào?

Expected:

- intent HOI_PHUONG_THUC_XET_TUYEN;
- query_mode LIST;
- category phuong_thuc_xet_tuyen;
- not OUT_OF_SCOPE.

Actual:

- analysis intent: HOI_PHUONG_THUC_XET_TUYEN;
- target_school: UNSPECIFIED;
- initial scope_reason: in_scope_dhv;
- query_mode: LIST;
- status: no_data because controlled retriever returned no evidence;
- pre_rag_decomposition: absent/null;
- subplans: none;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 1;
- retrieved_docs_count: 0;
- evidence_count: 0;
- sources: [].

Result: PASS for recognition/routing.

### Case 2

Input: DHV có những cách tuyển sinh nào?

Expected:

- same method/list route;
- not OUT_OF_SCOPE.

Actual:

- analysis intent: HOI_PHUONG_THUC_XET_TUYEN;
- target_school: DHV;
- initial scope_reason: in_scope_dhv;
- query_mode: LIST;
- router category: phuong_thuc_xet_tuyen;
- status: no_data because controlled retriever returned no evidence;
- pre_rag_decomposition: absent/null;
- subplans: none;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 1;
- retrieved_docs_count: 0;
- evidence_count: 0;
- sources: [].

Result: PASS for recognition/routing.

### Case 3

Input: DHV tuyển sinh như thế nào, học phí có cao không?

Expected:

- root intent MULTI_ISSUE;
- subplan order HOI_PHUONG_THUC_XET_TUYEN then HOI_HOC_PHI;
- independent categories.

Actual:

- analysis/root intent: MULTI_ISSUE;
- target_school: DHV;
- initial scope_reason: in_scope_dhv;
- root query_mode: SINGLE_FACT;
- pre_rag_decomposition: absent/null because deterministic multi-issue rules already produced subplans;
- subplan 1: HOI_PHUONG_THUC_XET_TUYEN, category phuong_thuc_xet_tuyen, query_mode SINGLE_FACT;
- subplan 2: HOI_HOC_PHI, category hoc_phi, query_mode SINGLE_FACT;
- subplan order: correct;
- status: no_data because controlled retriever returned no documents;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 2;
- retrieved_docs_count: 0 (0 + 0);
- evidence_count: 0 (0 + 0);
- sources: [].

Result: PASS for deterministic multi-issue routing.

### Case 4

Input: Em quan tâm ngành Luật, mức học phí mỗi tín chỉ ra sao?

Expected:

- planner may split into ngành Luật and học phí;
- result must state whether planner is live or controlled.

Actual controlled planner:

- planner type: controlled/fake planner, not live Ollama;
- initial analysis intent: HOI_HOC_PHI;
- target_school: UNSPECIFIED;
- initial scope_reason: in_scope_dhv;
- root result intent: MULTI_ISSUE;
- query_mode: SINGLE_FACT;
- pre_rag_decomposition:

~~~json
{
  "status": "accepted",
  "reason": "validated_verbatim_spans_and_deterministic_routes",
  "parts": [
    "Em quan tâm ngành Luật",
    "mức học phí mỗi tín chỉ ra sao"
  ],
  "routed_intents": [
    "HOI_NGANH",
    "HOI_HOC_PHI"
  ],
  "scope_revalidated": true
}
~~~

- subplan 1: HOI_NGANH, category nganh_dao_tao, query_mode SINGLE_FACT;
- subplan 2: HOI_HOC_PHI, categories hoc_phi and ho_so, query_mode SINGLE_FACT;
- planner LLM calls: 1 controlled call;
- answer LLM calls: 0 because controlled retriever returned no documents;
- retrieval_calls: 2;
- retrieved_docs_count: 0 (0 + 0);
- evidence_count: 0 (0 + 0);
- status: no_data;
- sources: [].

Result: PASS for controlled pre-RAG activation and routing. Live planner/generation status is BLOCKED by Ollama availability.

### Case 5

Input: Điểm chuẩn CNTT theo học bạ là bao nhiêu?

Expected:

- one issue only;
- no pre-RAG LLM call;
- no multi-issue split.

Actual:

- intent: HOI_DIEM_TRUNG_TUYEN;
- target_school: UNSPECIFIED;
- initial scope_reason: in_scope_dhv;
- query_mode: SINGLE_FACT;
- category: diem_trung_tuyen;
- pre_rag_decomposition: absent/null;
- subplans: none;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 1;
- retrieved_docs_count: 0;
- evidence_count: 0;
- status: no_data due empty controlled retriever.

Result: PASS. The method phrase học bạ did not cause an unwanted split.

### Case 6

Input: Điểm chuẩn Bách Khoa?

Expected:

- external school;
- planner LLM not called;
- retrieval, documents, and evidence all zero.

Actual:

- intent: HOI_DIEM_TRUNG_TUYEN;
- target_school: OTHER_SCHOOL;
- scope_reason: external_school;
- query_mode: SINGLE_FACT;
- pre_rag_decomposition: absent/null;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 0;
- retrieved_docs_count: 0;
- evidence_count: 0;
- status: out_of_scope;
- sources: [].

Result: PASS.

### Case 7

Input: Giá vàng hôm nay?

Expected:

- OUT_OF_SCOPE;
- no admissions intent;
- no planner/retrieval call.

Actual:

- intent: OUT_OF_SCOPE;
- target_school: UNSPECIFIED;
- scope_reason: general_out_of_scope;
- query_mode: SINGLE_FACT;
- pre_rag_decomposition: absent/null;
- subplans: none;
- planner LLM calls: 0;
- answer LLM calls: 0;
- retrieval_calls: 0;
- retrieved_docs_count: 0;
- evidence_count: 0;
- status: out_of_scope;
- sources: [].

Result: PASS.

## 6. Active Chroma Controlled Evidence Replay

A read-only adapter over collection dhv_admissions_2026 was used to verify method-list output against active evidence. This is not a live production retriever because Ollama embeddings were unavailable.

| Input | Status | Intent / mode | Docs / evidence | LLM calls | Answer/source result |
|---|---|---|---:|---:|---|
| Trường mình có những hình thức tuyển sinh nào? | ok | HOI_PHUONG_THUC_XET_TUYEN / LIST | 21 / 21 | 0 | Five methods listed; source https://tuyensinh.dhv.edu.vn/ |
| DHV có những cách tuyển sinh nào? | ok | HOI_PHUONG_THUC_XET_TUYEN / LIST | 21 / 21 | 0 | Same five methods; source https://tuyensinh.dhv.edu.vn/ |

The five listed methods were:

1. Tốt nghiệp THPT 2026.
2. Học bạ.
3. Đánh giá năng lực.
4. Đánh giá năng lực chuyên biệt H-SCA.
5. Tốt nghiệp trung cấp.

For the two-issue method/tuition query, a controlled active-Chroma replay confirmed root MULTI_ISSUE, subplans HOI_PHUONG_THUC_XET_TUYEN then HOI_HOC_PHI, retrieval_calls 2, retrieved docs 22, and selected evidence 14. It required three calls to a stub answer generator for the evidence-backed generation path; that stub is not treated as a factual/live PASS.

## 7. Live Ollama Check

Checks:

- no ollama process was running;
- GET http://localhost:11434/api/tags failed with:

~~~text
System.Net.Http.HttpRequestException:
An attempt was made to access a socket in a way forbidden by its access permissions. (localhost:11434)
~~~

A default production-path probe for DHV có những cách tuyển sinh nào? returned:

~~~text
status = ollama_offline
intent = HOI_PHUONG_THUC_XET_TUYEN
pre_rag_decomposition = null
retrieval_calls = 0
retrieved_docs_count = 0
evidence_count = 0
sources = []
~~~

Therefore, live Ollama/embedding/RAG verification is BLOCKED. Controlled/fake planner and read-only Chroma replay results are not promoted to live PASS.

## 8. Findings

### No functional finding reproduced

The requested method-recognition, ordering, no-split, scope-boundary, and pre-RAG validation behaviors passed in the independent controlled traces and targeted regression suite.

### ENV-QUERY-001

- Severity: MEDIUM environment blocker.
- Component: Ollama endpoint / embedding runtime.
- Expected: live production-like trace through configured local Ollama and Chroma.
- Actual: localhost:11434 is inaccessible with a Windows socket-permission error; no ollama process is running; default chatbot path returns ollama_offline before retrieval.
- Owner: DEVOPS_SRE.
- Acceptance criterion: make the configured Ollama endpoint and required models available, then rerun the seven-case live matrix without fake planner/retriever doubles.

No business-logic handoff is raised because no product assertion failure was reproduced.

## 9. Acceptance Summary

| Criterion | Status |
|---|---|
| Natural method phrases route to HOI_PHUONG_THUC_XET_TUYEN | PASS |
| Method phrases use LIST mode | PASS |
| Method category is phuong_thuc_xet_tuyen | PASS |
| Method + tuition deterministic subplan order is correct | PASS |
| Comma-separated Luật + tuition can activate pre-RAG decomposition | PASS controlled |
| Decomposer validates verbatim/order/content/scope | PASS |
| Single score-by-method question does not invoke pre-RAG planner | PASS |
| External-school question blocks planner/retriever/evidence | PASS |
| Out-of-scope gold question does not enter admissions intent | PASS |
| Live Ollama trace verified | BLOCKED |

## 10. Final Verdict

## BLOCKED

Recognition and pre-RAG decomposition pass independent controlled QA and the requested targeted pytest suite. The overall review cannot be marked PASS because the configured Ollama runtime is inaccessible, so live planner/embedding/RAG behavior remains unverified. No source/test/data changes or deployment were performed.

