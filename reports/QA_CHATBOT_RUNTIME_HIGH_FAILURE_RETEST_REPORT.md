# QA & Security — Runtime High-Failure Retest

## 1. Independent verdict

**PASS — scoped retest for UQ0041 and UQ0222, including the requested focused and full test runs.** This is not a full-project QA sign-off and does not close unrelated findings from earlier full-sweep reports.

No product source, tests, dataset, expected answers, Chroma data, or configuration were changed. No deployment was performed. This report is the only intended artifact written by this QA run.

## 2. Snapshot and materials reviewed

- Repository HEAD: `f6016fb9b6d35ab1f5b38c1c8d399565ce830549`.
- Working tree was already dirty at review start. Relevant modified/untracked files reviewed for this scope:
  - `src/chatbot/query_semantics.py` (untracked)
  - `src/chatbot/query_analysis.py`
  - `src/chatbot/rag_chain.py`
  - `src/chatbot/output_validator.py`
  - `tests/test_full_sweep_p1.py`
  - `tests/test_priority_1_2_fix.py`
- Other unrelated dirty paths were present; QA did not modify them.
- Read `reports/TONG_QUAN_AGENT`, `reports/CHATBOT_RUNTIME_HIGH_FAILURE_FIX_REPORT.md`, `reports/QA_FULL_SWEEP_P1_FINAL_INDEPENDENT_RETEST_20261009.md`, `reports/QA_CHATBOT_FUP_SECURITY_RETEST_REPORT.md`, and `reports/QA_FUP_001_RETEST_REPORT.md`. The prior full-sweep report records the original UQ0041/UQ0222 failures; the current Lead report claims both were fixed.

## 3. Code review findings

### UQ0041 — semester-I total without optional English test

The current diff adds shared accent-insensitive question predicates in `query_semantics.py`. Tuition routing includes both `hoc_phi` and `ho_so` when a semester total or optional English-test fee is requested. The deterministic answer and validator independently require a verified DHV `page_text` record in `ho_so`, page 4, matching target year, and an HTTPS DHV source. The answer uses the source row's base amount when the question explicitly excludes the test fee and only adds the optional amount when inclusion is explicit.

The regression in `test_full_sweep_p1.py` covers included and excluded totals, rejection of 14,500,000 VND for the excluded case, and the category route. The reviewed exact UQ0041 phrase is not hard-coded.

### UQ0222 — intermediate-vocational applicants, same major group

The query route adds canonical Method 5 retrieval cues for the semantic combination “trung cấp” + “cùng nhóm ngành.” The deterministic answer requires verified DHV 2026 `page_text` evidence in `phuong_thuc_xet_tuyen`, official HTTPS DHV provenance, and both source conditions: same intended major group and completion of the prescribed high-school cultural curriculum. It runs before free generation and does not repeat the unrelated H-SCA organizer/institution.

The regression in `test_priority_1_2_fix.py` uses a `NeverCalledLLM` and asserts the two conditions and absence of the unrelated institution/H-SCA claim.

No blocker or bypass was found in the reviewed UQ-specific paths. The logic is intentionally bound to the currently verified source format/page; a source layout/year change should fail closed and needs a corresponding evidence/parser review.

## 4. Test commands and results

An initial default shell launch failed before process start with `CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)`. The workspace command runner succeeded when invoked with the approved elevated read/test permission; therefore this was a transient process-launch blocker, not a test failure and not an outstanding blocker.

Both commands used UTF-8 stdout and the existing workspace temp directory:

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONPATH='.'; $env:TEMP=(Resolve-Path .test_tmp).Path; $env:TMP=$env:TEMP; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_full_sweep_p1.py tests/test_priority_1_2_fix.py
```

**Result on the resumed narrowed QA run: 97 passed, 0 failed, 92 subtests passed in 8.58 seconds.**

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONPATH='.'; $env:TEMP=(Resolve-Path .test_tmp).Path; $env:TMP=$env:TEMP; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

**Earlier independent QA run in this review session: 296 passed, 0 failed, 4 skipped, 303 subtests passed (145.74 seconds).** The resumed narrowed QA task did not rerun full pytest, per instruction. This is the QA-observed command output, not an attribution of the Lead's result. The quiet run did not print the individual skip reasons; skipped tests are not counted as passes. `compileall` was not run because pytest imported and executed the changed modules successfully; no separate static compilation claim is made.

## 5. Live environment

- `http://127.0.0.1:11434/api/tags`: HTTP 200.
- Ollama models observed: `qwen2.5:3b` and `nomic-embed-text:latest`.
- Live cases used `ask_chatbot` with `DHVRetriever(settings_obj=settings)`, the configured collection, and no mock retriever. Runtime traces report the configured 2026 year/category filters. No Chroma rebuild or write was performed.

## 6. Live UQ traces

| Field | UQ0041 — exclude English test | UQ0222 — vocational same-group |
|---|---|---|
| Query | `Nếu em không thuộc diện kiểm tra tiếng Anh thì tổng các khoản học kỳ I trong bảng là bao nhiêu?` | `Thí sinh tốt nghiệp trung cấp cùng nhóm ngành có thể vào DHV không?` |
| Intent | `HOI_HOC_PHI` | `HOI_PHUONG_THUC_XET_TUYEN` |
| School / scope | `UNSPECIFIED` / `in_scope_dhv` | `DHV` / `in_scope_dhv` |
| Category filter | `hoc_phi`, `ho_so` | `phuong_thuc_xet_tuyen` |
| Retrieval calls | 1 | 1 |
| Retrieved documents | 4 | 4 |
| Selected evidence | 4 | 4 |
| Direct answer / validator | direct evidence answer `ok` | direct evidence answer `ok` |
| Final status | `ok` | `ok` |
| Source | `https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026-va-thong-tin-tu-van-vien-ho-tro-tan-sinh-vien/` | `https://tuyensinh.dhv.edu.vn/` |
| Answer check | States the total is **14,250,000 VND** and explicitly excludes the conditional 250,000 VND English-test charge. | States Method 5 and both conditions; does not mention Đại học Sư phạm TP.HCM or H-SCA. |

UQ0041 retrieval audit used year 2026 and the `hoc_phi`/`ho_so` category union; returned chunks included the tuition chunk `c145b7cc158b-000-000-8008c933` and `ho_so` chunks including `c145b7cc158b-000-000-b655a47f`. UQ0222 retrieval audit used year 2026 and `phuong_thuc_xet_tuyen`; all four returned documents were in that category. The direct-answer implementation and focused regression assertions verify the answer against the verified page-text evidence conditions described above.

## 7. Live controls and regression coverage

| Control | Observed | Result |
|---|---|---|
| Included English-test fee: `Tổng chi phí học kỳ I bao gồm kiểm tra năng lực tiếng Anh là bao nhiêu?` | `HOI_HOC_PHI`; `hoc_phi` + `ho_so`; retrieval/docs/evidence `1/4/4`; direct answer `ok`; total 14,500,000 VND with official DHV source | PASS |
| `Điểm chuẩn Văn Hiến?` | `OTHER_SCHOOL`, `external_school`, `out_of_scope`; retrieval/docs/evidence `0/0/0`; no sources | PASS |
| `So sánh DHV và Văn Hiến` | `MIXED`, `mixed_school`, `out_of_scope`; retrieval/docs/evidence `0/0/0`; no sources | PASS |
| `Điểm chuẩn Hùng Vương?` | `AMBIGUOUS`, `ambiguous_school`, `clarification`; retrieval/docs/evidence `0/0/0`; no sources | PASS |
| F-01/F-02/F-03, CORE/STATE, Task 09, Phase 2/4, count/list, decomposition | Included in the full pytest discovery on this snapshot; full command reported 296 passed, 4 skipped, no failures. These were not each independently replayed as live Ollama conversations during this scoped retest. | PASS — automated suite coverage; live E2E not separately claimed |

## 8. Findings and remaining limits

- **No new scoped product finding** was reproduced for UQ0041/UQ0222 or the three live school-boundary controls.
- Four tests were skipped in the full suite; the quiet command did not report their identities/reasons. They remain skipped, not passed.
- This report does not adjudicate unrelated full-sweep data gaps, recommendations, incomplete answers, or prior non-scoped findings. The previous independent full-sweep report remains the authority for those open items.
- The previous QA finding UQ0222 is considered closed only for this current snapshot and the tested query/evidence path; the full 500-question sweep was not rerun here.

## 9. Handoff

**Scoped QA verdict: PASS.** The two HIGH regressions passed code review, focused tests, full pytest, and live `ask_chatbot` checks; external/mixed/ambiguous controls remained fail-closed. This is not `FULL_QUESTION_SWEEP_PASS` or a general production-readiness/deployment approval. No deploy is authorized.
