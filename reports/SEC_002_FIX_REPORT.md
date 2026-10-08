# SEC-002 FIX REPORT

## 1. Task

- Bug: `SEC-002 – GENERIC EXTERNAL SCHOOL BOUNDARY BYPASS`.
- Scope: generic phrases such as `trường đại học khác` were classified as
  `UNSPECIFIED`, allowing the DHV retrieval path to run.
- Explicitly out of scope: Priority 3 and unrelated CORE-001/STATE-001
  changes.
- Final verdict: `READY_FOR_QA`.

## 2. Root Cause Verification

The QA report was confirmed against the source:

- `src/chatbot/scope_guard.py` already defined `_OTHER_SCHOOL_MARKERS`, but
  `_school_mentions()` never consumed that registry.
- `detect_target_school()` derives its result from `_school_mentions()`. With
  no extracted mention, `trường đại học khác` fell through to
  `UNSPECIFIED`.
- The generic unknown-institution fallback did not reliably catch the phrase,
  because the non-overlapping institution regex consumed `trường đại` and did
  not re-evaluate the embedded `đại học` phrase.
- `rag_chain.py` already had the correct zero-retrieval boundary for
  `OTHER_SCHOOL`, `MIXED`, and `AMBIGUOUS`; the failure was upstream school
  classification.
- `output_validator.py` already supplied defense-in-depth for those targets,
  but could not protect a query incorrectly labelled `UNSPECIFIED`.

## 3. Previous Behavior

For `Điểm chuẩn trường đại học khác?`:

```text
target_school = UNSPECIFIED
scope_reason = in_scope_dhv
retrieval_calls = 1
```

The fixture returned no documents, so the observed status was `no_data`. A
non-empty DHV collection could have exposed DHV facts on this path.

## 4. Implementation

`src/chatbot/scope_guard.py` now:

1. Extends the normalized generic external marker registry to cover:
   `trường khác`, `trường đại học khác`, `trường ĐH khác`,
   `trường cao đẳng khác`, `đại học khác`, `cao đẳng khác`, `học viện khác`,
   and the corresponding unaccented forms.
2. Consumes `_OTHER_SCHOOL_MARKERS` in `_school_mentions()` using the existing
   token-boundary matcher after normalization.
3. Emits the semantic mention `trường khác` when a generic external marker is
   present.
4. Preserves existing precedence: explicit DHV plus a generic external marker
   becomes `MIXED`; a generic external marker alone becomes `OTHER_SCHOOL`.
5. Does not classify a generic occurrence of `trường` as external.

Because `query_analysis.py` already calls `detect_target_school()` and
`rag_chain.py` already stops before retrieval for the external targets, no
changes were required in those modules for SEC-002.

## 5. Files Changed

| File | Function/Area | Reason |
|---|---|---|
| `src/chatbot/scope_guard.py` | `_OTHER_SCHOOL_MARKERS`, `_school_mentions()` | Detect generic external-school language before the DHV default. |
| `tests/test_priority_1_2_fix.py` | `ExternalSchoolBoundaryTests` | Add SEC-002 marker, false-positive, mixed, and multi-turn coverage. |
| `SEC_002_FIX_REPORT.md` | This report | Record implementation, evidence, risks, and QA handoff. |

The pre-existing working-tree changes in `query_analysis.py`, `rag_chain.py`,
and `output_validator.py` were not altered in this task.

## 6. Generic External Marker Logic

All matching uses `normalize_scope_text()` and `_contains_scope_marker()`, so
accented and unaccented forms share the same semantic path. The rule is
specific to phrases containing `khác`/equivalent external-school markers; it
does not use the broad word `trường` by itself.

Expected target mapping:

| Input family | Target | Scope | Retrieval |
|---|---|---|---:|
| `trường đại học khác`, `đại học khác`, `trường khác` | `OTHER_SCHOOL` | `external_school` | 0 |
| `trường ĐH khác`, `trường cao đẳng khác`, `học viện khác` | `OTHER_SCHOOL` | `external_school` | 0 |
| DHV + generic external marker | `MIXED` | `mixed_school` | 0 |
| Generic `trường` without external marker | `UNSPECIFIED` | DHV default path | allowed |

## 7. False-Positive Protection

The following remained DHV-default/in-scope and retained retrieval permission
in the recording-retriever tests:

- `Điểm chuẩn CNTT?`
- `Trường có những ngành nào?`
- `Học phí của trường bao nhiêu?`
- `Trường xét tuyển bằng phương thức nào?`
- `Điểm chuẩn của trường năm 2026?`

No rule was added for the standalone word `trường`.

## 8. Runtime Traces

### SEC-002 real `ask_chatbot` runtime

Input: `Điểm chuẩn trường đại học khác?`

```text
target_school         = OTHER_SCHOOL
scope_reason          = external_school
intent                = HOI_DIEM_TRUNG_TUYEN
retrieval_calls       = 0
retrieved_docs_count  = 0
evidence_count        = 0
status                = out_of_scope
```

The final answer was the external-school boundary response and contained no
DHV factual values.

### Recording-retriever matrix

The generic matrix, including accented/unaccented forms, produced
`OTHER_SCHOOL`, `external_school`, zero retrieval calls, zero retrieved
documents, zero evidence, and `out_of_scope` for every case.

Controls produced:

```text
Trường có những ngành nào?   -> UNSPECIFIED, DHV path allowed
Điểm chuẩn CNTT?             -> UNSPECIFIED, DHV path allowed
Điểm chuẩn DHV CNTT?         -> DHV, DHV path allowed
```

With the fake recording retriever, each control called retrieval once. The
default positive-DHV runtime could not complete because Ollama at
`127.0.0.1:11434` was unavailable in this environment; this is recorded as an
environment limitation, not a SEC-002 failure.

## 9. Tests

| Suite | Passed | Failed | Skipped | Blocked |
|---|---:|---:|---:|---:|
| SEC-002 generic/false-positive/mixed/multi-turn tests | 5 tests, 16 subtests | 0 | 0 | 0 |
| `tests/test_priority_1_2_fix.py` | 19 tests, 26 subtests | 0 | 0 | 0 |
| Combined Priority 1/2 + intent/Phase 2/Phase 4/Task F/Task I/UI/app | 97 tests, 168 subtests | 0 | 0 | 0 |
| `compileall -q src tests app.py` | PASS | 0 | 0 | 0 |
| `pip check` | PASS | 0 | 0 | 0 |
| Default positive-DHV runtime with Ollama | 0 | 0 | 0 | Ollama unavailable |

## 10. SEC-001 Regression

The existing named-school matrix remained passing:

- `Bách Khoa` and `bach khoa`
- `Văn Hiến`
- `Hoa Sen`
- `Văn Lang`
- `Nguyễn Tất Thành`
- mixed `DHV` and `Văn Hiến`

All external/mixed cases retained zero retrieval and zero evidence. The
existing validator synthetic defense also remained passing in the combined
targeted suite.

## 11. CORE/STATE Regression

The combined targeted suite passed without changes to CORE-001 or STATE-001.
This includes list/single/ordinal coreference, tuition inheritance versus
generic tuition, explicit school/major overrides, and greeting/thanks reset.

## 12. Acceptance Criteria

- [PASS] `trường đại học khác` is not `UNSPECIFIED`.
- [PASS] `đại học khác` is not `UNSPECIFIED`.
- [PASS] `trường khác` is not `UNSPECIFIED`.
- [PASS] Accented and unaccented forms are handled.
- [PASS] Generic external retrieval is 0.
- [PASS] Generic external evidence is 0.
- [PASS] No DHV factual leakage occurs on the boundary path.
- [PASS] Bách Khoa regression remains protected.
- [PASS] Văn Hiến/Hoa Sen/Văn Lang/Nguyễn Tất Thành remain protected.
- [PASS] Mixed-school retrieval remains 0.
- [PASS] `Trường có những ngành nào?` is not falsely blocked.
- [PASS] `Điểm chuẩn CNTT?` remains DHV-default eligible.
- [PASS] Explicit DHV remains eligible.
- [PASS] CORE-001 targeted regression passes.
- [PASS] STATE-001 targeted regression passes.
- [BLOCKED] Full default positive-DHV runtime could not reach retrieval because Ollama was unavailable.

## 13. Remaining Risks

- QA/Security should rerun the real positive-DHV path with Ollama and the
  active Chroma collection.
- The full suite is not globally green: `173 passed, 12 failed, 4 skipped`
  with `221` subtests. The failures are outside SEC-002 and include Windows
  temporary-directory ACL/path failures plus existing Task 09/Task C and
  ingestion pipeline issues. They were not modified in this task.
- Generic unknown institutions beyond the explicit registry still depend on
  the existing unknown-institution heuristic; this task only closes the
  generic external marker bypass specified by SEC-002.

## 14. Handoff To QA

QA & Security should review the code diff and rerun:

1. The eight required generic external phrases, both accented and unaccented.
2. `Bách Khoa`, `Văn Hiến`, `Hoa Sen`, `Văn Lang`, and `Nguyễn Tất Thành`.
3. DHV + external mixed-school queries.
4. The five generic DHV false-positive controls.
5. Multi-turn DHV → `Còn trường khác?` and external → `Còn DHV?` overrides.
6. Validator synthetic defense with DHV evidence.
7. The combined Priority 1/2 regression suite.
8. Real `ask_chatbot` with Ollama/Chroma available.

No deployment was performed. No Priority 3 work was performed.

## Final Verdict

`READY_FOR_QA`
