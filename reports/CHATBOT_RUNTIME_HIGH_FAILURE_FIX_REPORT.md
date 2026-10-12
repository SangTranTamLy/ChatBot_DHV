# CHATBOT RUNTIME HIGH-FAILURE FIX REPORT

## 1. Scope

Implemented the two confirmed HIGH runtime failures from the latest independent full-sweep retest:

- UQ0041 — semester-I expense total omitted verified enrollment/material fees and did not honor exclusion of the optional English test fee.
- UQ0222 — vocational applicants with a same-group intermediate-vocational diploma could be answered using an unrelated nearby institution/H-SCA passage instead of DHV Method 5.

No deployment, Chroma rebuild, raw/processed corpus edit, evaluation dataset edit, model change, or embedding change was performed.

## 2. Root Cause Verification

### UQ0041 — `CATEGORY_TAXONOMY_MISMATCH` + `EVIDENCE/ANSWER_SEMANTICS`

The question was classified as `HOI_HOC_PHI`, but its wording (“tổng các khoản học kỳ I”) did not match the router's narrow phrases for adding `ho_so`. Retrieval therefore selected tuition evidence and omitted the page-text fee breakdown. In addition, the deterministic total helper always added the optional English-test amount, even when the user said they were not in that test group.

The verified page-text table is the required source because it preserves the base semester total and the additional conditional English-test charge together.

### UQ0222 — `RETRIEVAL_QUERY_MISS` + `UNSAFE_FREE_GENERATION_FALLBACK`

The DHV verified 2026 Method 5 condition exists in category `phuong_thuc_xet_tuyen`, page 5. The ordinary natural-language query could rank the relevant passage below the default candidate window, while nearby H-SCA text mentions Đại học Sư phạm TP.HCM. That made free generation vulnerable to conflating the test organizer with DHV's institution.

The source condition is: intermediate vocational graduation in the same intended major group, plus completion of the prescribed high-school cultural curriculum. The answer must state this as an application-method condition, not as guaranteed admission.

## 3. Implementation

- Added shared, accent-insensitive semantic predicates for semester fee totals and whether the optional English-test fee is explicitly included/excluded.
- Expanded tuition routing to retrieve both `hoc_phi` and `ho_so` for semantic semester-total questions and explicit English-test fee questions.
- Made the deterministic semester-total answer parse only the verified DHV page-text fee row for the active target year and an official HTTPS DHV source. It excludes the optional amount when the question excludes it, includes it only when the question explicitly includes the test, and otherwise identifies it separately as conditional.
- Updated validator arithmetic to use the same inclusion/exclusion semantics. It rejects a 14,500,000 VND answer for a question explicitly excluding the optional fee and rejects sums without the verified page-text row.
- Added semantic retrieval cues for same-group vocational eligibility questions; no full test question or question ID is hard-coded.
- Added a deterministic Method 5 answer guarded by verified 2026 DHV evidence containing both eligibility conditions. This branch returns before LLM generation and does not repeat the unrelated H-SCA organizer name.

## 4. Files Touched For This Fix

| File | Function/area | Reason |
|---|---|---|
| `src/chatbot/query_semantics.py` | Shared question predicates | Normalize Vietnamese text and classify total-fee inclusion/exclusion semantically. |
| `src/chatbot/query_analysis.py` | Tuition categories and retrieval query | Include `ho_so` for semester totals and expand same-group vocational retrieval. |
| `src/chatbot/rag_chain.py` | Deterministic tuition total and Method 5 eligibility | Calculate from the verified page row and answer the vocational condition from matching source text. |
| `src/chatbot/output_validator.py` | Verified fee arithmetic | Apply the same optional-fee semantics and verified-source/year gate as generation. |
| `tests/test_full_sweep_p1.py` | UQ0041 regression | Test included, excluded, invalid total, stale-only evidence, and category routing. |
| `tests/test_priority_1_2_fix.py` | UQ0222 regression | Test verified Method 5 evidence, answer grounding, and that the LLM is not called. |

The worktree already contained unrelated earlier changes in several of these files. Those changes were preserved.

## 5. Test Results

| Check | Result |
|---|---|
| Two focused UQ0041/UQ0222 regressions | 2 passed |
| Full-sweep P1 + Priority 1/2 suites | 97 passed, 92 subtests passed |
| Full pytest, Python stdout UTF-8 | 296 passed, 4 skipped, 303 subtests passed |
| `compileall` | PASS |
| `pip check` | PASS — no broken requirements |
| `git diff --check` | PASS; only Git line-ending notices (LF/CRLF) |

An initial full-suite run without UTF-8 reported one failure in the legacy `scripts/test_natural_responses.py::test_chatbot`: Windows `cp1252` could not print a Vietnamese character before the smoke function called the chatbot. Re-running with `PYTHONIOENCODING=utf-8` completed the whole suite successfully; this is an environment/console encoding issue, not a product assertion failure.

## 6. Real Runtime Traces

Ollama was reachable at `http://127.0.0.1:11434/api/tags` during this run and reported:

- `qwen2.5:3b`
- `nomic-embed-text:latest`

Both queries below were run through the default `ask_chatbot` path with the configured local Chroma retriever; neither used a mock retriever.

### UQ0041

```yaml
question: Nếu em không thuộc diện kiểm tra tiếng Anh thì tổng các khoản học kỳ I trong bảng là bao nhiêu?
status: ok
intent: HOI_HOC_PHI
target_school: UNSPECIFIED
scope_reason: in_scope_dhv
categories: [hoc_phi, ho_so]
retrieval_calls: 1
retrieved_docs_count: 4
evidence_count: 4
deterministic_answer: ok
source: https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026-va-thong-tin-tu-van-vien-ho-tro-tan-sinh-vien/
answer_total: 14.250.000 VND
```

The response identifies the additional 250,000 VND English-test fee as conditional and excludes it for the stated case.

### UQ0222

```yaml
question: Thí sinh tốt nghiệp trung cấp cùng nhóm ngành có thể vào DHV không?
status: ok
intent: HOI_PHUONG_THUC_XET_TUYEN
target_school: DHV
scope_reason: in_scope_dhv
categories: [phuong_thuc_xet_tuyen]
retrieval_calls: 1
retrieved_docs_count: 4
evidence_count: 4
deterministic_answer: ok
source: https://tuyensinh.dhv.edu.vn/
```

The answer states the two Method 5 conditions. It does not mention Đại học Sư phạm TP.HCM or H-SCA, and it does not call the LLM.

## 7. Data and Runtime Integrity

- Active collection was used read-only; no rebuild/reset/upsert was performed.
- Existing independent inventory reports the active collection as `dhv_admissions_2026` with 310 verified DHV records for 2026. This task did not alter that collection.
- No factual answer was hard-coded into a question-specific branch; answers are derived from selected evidence.
- No 500-Q&A item or expected answer was changed.

## 8. Remaining Issues / Risks

- The independent full-sweep report also listed non-HIGH incomplete cases and corpus gaps (including UQ0009, UQ0076, UQ0083, UQ0138, UQ0160, UQ0236, UQ0327, UQ0378, and UQ0409). They were not changed in this scoped fix and require their own evidence/contract review.
- The fee parser intentionally requires the verified page-text row and a matching optional-condition cue for exclusion answers. If future source PDFs change their table wording/layout, the path fails closed and needs a parser regression update based on new verified evidence.
- Independent QA/Security sign-off remains pending; Lead results do not constitute a final QA pass or a full 500-question pass.

## 9. Acceptance Criteria

| Criterion | Status |
|---|---|
| UQ0041 routes to both `hoc_phi` and `ho_so` | PASS |
| Excluded optional English-test fee is not added | PASS |
| Validator rejects the included total when the fee is explicitly excluded | PASS |
| Included optional fee retains the 14,500,000 VND total behavior | PASS |
| UQ0222 retrieves verified Method 5 evidence | PASS — real runtime trace |
| Vocational answer contains both source conditions and avoids unrelated institution claims | PASS |
| UQ0222 deterministic path avoids LLM generation | PASS — regression test |
| Targeted and full test suites | PASS — UTF-8 full pytest: 296 passed, 4 skipped |
| Live Ollama/Chroma path exercised | PASS — two target traces |
| No dataset, Chroma, raw PDF, model, embedding, or deployment changes | PASS |

## 10. Handoff To QA & Security

Required independent retest report: `reports/QA_CHATBOT_RUNTIME_HIGH_FAILURE_RETEST_REPORT.md`.

Please inspect the exact current diff and rerun:

1. UQ0041 exact question; assert `hoc_phi + ho_so`, evidence contains the verified page-text total, final total is 14,250,000 VND, and validator rejects 14,500,000 VND for this excluded case.
2. Positive included-English-test control; assert the correct 14,500,000 VND total.
3. UQ0222 exact question through real Chroma/Ollama; assert Method 5 evidence and both eligibility conditions, no unrelated institution/H-SCA claim, and correct final status.
4. External/mixed/ambiguous school boundary, wrong-year, fee stale-evidence, Task 09, F-01/F-02/F-03, CORE/STATE, count/list, Phase 2/4, and query-decomposition regressions.
5. Full pytest using UTF-8 stdout on Windows; document intentional skips and environment failures separately.

QA must not modify source, data, expected results, or Chroma. End with QA's own `PASS`, `FAIL`, or `BLOCKED` verdict. No deployment is authorized.

## 11. Independent Handoff Results

### QA & Security

Report: `reports/QA_CHATBOT_RUNTIME_HIGH_FAILURE_RETEST_REPORT.md`

Independent verdict: **PASS for the scoped UQ0041/UQ0222 retest**. QA independently reviewed the changed paths, ran the focused suites (**97 passed, 92 subtests**) and full pytest (**296 passed, 4 skipped, 303 subtests**), and exercised both target questions plus included-fee and external/mixed/ambiguous controls through live `ask_chatbot`.

QA did not claim a full 500-question sweep or close unrelated prior findings. The four skips remain skips.

### DevOps/SRE

Report: `reports/DEVOPS_RUNTIME_HIGH_FAILURE_VERIFICATION_REPORT.md`

Independent verdict: **LOCAL_RUNTIME_READY** at verification time. Ollama served both required models; active Chroma was confirmed as `dhv_admissions_2026` with 310 records and all inspected metadata gates satisfied; a real default-path smoke call completed. This is runtime readiness only, not factual QA approval.

## 12. Final Lead Verdict

**Scoped UQ0041/UQ0222: QA PASS. Overall project status: READY_FOR_QA for remaining non-scoped/full-sweep findings.** This is not a `FULL_QUESTION_SWEEP_PASS`, not deployment approval, and does not close the unrelated full-sweep data gaps or incomplete-answer findings.
