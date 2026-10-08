# QA & SECURITY – PRIORITY 1 + 2 RETEST REPORT

Ngày retest: 2026-10-07  
Project: `ChatBot_DHV`  
Vai trò: `QA & SECURITY AGENT`  
Phạm vi: retest độc lập sau patch Lead Coder cho `SEC-001`, `CORE-001`, `STATE-001`.

## 1. Scope

Retest này kiểm tra:

- `SEC-001`: wrong-school factual leakage, đặc biệt `Bách Khoa`.
- `CORE-001`: coreference cho major, program, method, list và ordinal.
- `STATE-001`: semantic context inheritance, generic reset, explicit override và non-factual reset.

Không xử lý Priority 3. Không sửa source code, test expectation, dataset, model, Chroma hoặc deployment.

## 2. Files Reviewed

Files Lead Coder thực tế thay đổi hoặc thêm trong working tree:

- `src/chatbot/scope_guard.py`
- `src/chatbot/query_analysis.py`
- `src/chatbot/rag_chain.py`
- `src/chatbot/output_validator.py`
- `tests/test_priority_1_2_fix.py`
- `reports/PRIORITY_1_2_FIX_REPORT.md`

Đối chiếu diff thực tế cho thấy bốn file source có modified tracked diff; targeted test và hai report là untracked trong working tree. Không phát hiện hard-code full user question hoặc factual admission answer trong patch. Patch thêm alias semantic `bach khoa`, coreference/state resolver bounded, `THANKS`, trace counters và validator scope guard.

## 3. Lead Coder Claims Verified

| Claim | Verified? | Evidence |
|---|---|---|
| `Bách Khoa`/`bach khoa` không còn `UNSPECIFIED` | PASS | Independent `analyze_question` và runtime matrix đều cho `OTHER_SCHOOL` |
| External/mixed/ambiguous kết thúc trước retrieval | PARTIAL | Named aliases, mixed DHV/Văn Hiến và Hùng Vương pass; generic `trường đại học khác` vẫn retrieval |
| Validator là defense-in-depth | PASS | Direct validator test với DHV evidence + `OTHER/MIXED/AMBIGUOUS` trả `school_scope_boundary` |
| Full list coreference giữ toàn bộ candidate | PASS | Targeted test và independent state/route check |
| Program/method ordinal giữ đúng entity type/parent | PASS | Targeted test và independent check |
| Semantic tuition follow-up giữ major | PASS | `route_question` giữ `major_name=Công nghệ thông tin` |
| Generic tuition không inherit stale major | PASS | Hai generic tuition query có entity filters rỗng |
| Greeting/thanks không retrieval | PASS | Independent multi-turn run |
| Real DHV-positive E2E | BLOCKED | Ollama endpoint không khả dụng trong môi trường retest |
| Targeted suite không có Priority 1/2 assertion failure | PASS | `14 passed, 10 subtests`; suite liên quan `82 passed, 148 subtests` |
| Full regression pass | FAIL | `168 passed, 12 failed, 4 skipped`; failures gồm environment và pre-existing contract/data failures |

## 4. SEC-001 Retest

### Original reproduction

Input: `Điểm chuẩn Bách Khoa?`

Kết quả độc lập sau patch:

- `target_school=OTHER_SCHOOL`.
- `scope_reason=external_school`.
- `status=out_of_scope`.
- `retrieval_calls=0`.
- `retrieved_docs_count=0`.
- `evidence_count=0`.
- Final answer không chứa các factual values DHV `15`, `18`, `600`.

Input không dấu `diem chuan bach khoa?` cho kết quả tương tự.

Kết luận: reproduction gốc của `SEC-001` **đã được sửa đúng cho alias Bách Khoa đã nêu**.

### Implementation review

Điểm đúng:

- Alias được thêm ở registry semantic, không hard-code cả câu hỏi.
- Scope boundary chạy trước retrieval.
- Validator có `_school_scope_boundary_failure()` và từ chối `OTHER_SCHOOL`, `MIXED`, `AMBIGUOUS` dù caller truyền DHV evidence.
- Không có factual answer hard-code mới trong patch.

Giới hạn phát hiện: registry fix chưa bao phủ marker tổng quát `trường đại học khác`; xem `SEC-002`.

## 5. External School Matrix

Matrix được chạy với `ask_chatbot` + recording retriever để đo call path độc lập.

| Input | Target School | Scope | Retrieval Calls | Evidence Count | Final Status | PASS/FAIL |
|---|---|---|---:|---:|---|---|
| `Điểm chuẩn Bách Khoa?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `diem chuan bach khoa?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Điểm chuẩn Văn Hiến?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Học phí Hoa Sen?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Văn Lang có học bổng không?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Nguyễn Tất Thành có xét học bạ không?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Điểm chuẩn Bách Khoa TP.HCM?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Học phí trường Bách Khoa?` | `OTHER_SCHOOL` | `external_school` | 0 | 0 | `out_of_scope` | PASS |
| `Điểm chuẩn trường đại học khác?` | `UNSPECIFIED` | `in_scope_dhv` | **1** | 0 | `no_data` | **FAIL** |
| `So sánh DHV và Văn Hiến` | `MIXED` | `mixed_school` | 0 | 0 | `out_of_scope` | PASS |

Với case fail, fixture retriever rỗng nên chưa có DHV numeric leakage trong output cụ thể. Tuy vậy retrieval đã được gọi, vi phạm invariant external-school và có thể leak factual DHV data khi collection trả kết quả.

## 6. DHV False-Positive Regression

| Input | Expected | Actual | Result |
|---|---|---|---|
| `Điểm chuẩn DHV CNTT?` | `DHV`, retrieval allowed | `DHV`, recording retriever called 1 | PASS |
| `Điểm chuẩn CNTT?` | `UNSPECIFIED`, DHV default allowed | `UNSPECIFIED`, recording retriever called 1 | PASS |
| `Trường có những ngành nào?` | generic DHV default allowed | `UNSPECIFIED`, recording retriever called 1 | PASS |

Không thấy patch chặn nhầm các câu DHV explicit hoặc domain-default trong fake retriever contract.

## 7. Mixed/Ambiguous School Tests

| Input | Expected | Actual | Retrieval | Result |
|---|---|---|---:|---|
| `Điểm chuẩn Hùng Vương?` | `AMBIGUOUS`/clarification | `AMBIGUOUS`, clarification | 0 | PASS |
| `So sánh DHV và Văn Hiến` | `MIXED` | `MIXED`, out-of-scope | 0 | PASS |
| `Điểm chuẩn trường đại học khác?` | external/ambiguous, no retrieval | `UNSPECIFIED`, in-scope | **1** | FAIL |

`_OTHER_SCHOOL_MARKERS` vẫn được khai báo trong `src/chatbot/scope_guard.py` nhưng không được sử dụng trong `detect_target_school()` để biến marker `trường đại học khác` thành external/ambiguous. Đây là probable root cause của `SEC-002`.

## 8. CORE-001 Retest

Kết quả independent query-analysis/route checks:

| Context | Follow-up | Result |
|---|---|---|
| `last_listed_majors=(Công nghệ thông tin, Marketing)` | `Điểm sàn các ngành nêu trên?` | `candidate_majors` giữ đủ 2; `major_name=None` |
| `current_major=Công nghệ thông tin` | `Điểm chuẩn ngành đó?` | `major_name=Công nghệ thông tin` |
| programs `Digital Marketing`, `Truyền thông số`, parent `Marketing` | `Chương trình thứ hai học gì?` | `program_name=Truyền thông số`, `parent_major=Marketing`, `entity_type=program` |
| methods `hoc_ba`, `dgnl` | `Phương thức thứ hai cần bao nhiêu điểm?` | `admission_method=dgnl`, `entity_type=method` |
| major list, không đủ alternative context | `Còn cái kia?` | `needs_clarification=True` |
| empty context | `cái đó` | `needs_clarification=True` |

Không thấy random major selection hoặc program-to-major type collapse trong các case đã test.

## 9. STATE-001 Retest

Đã kiểm tra các policy sau:

- `Điểm chuẩn CNTT?` -> `Còn học phí?`: route giữ `major_name=Công nghệ thông tin`.
- `Điểm chuẩn CNTT?` -> `Học phí DHV hiện nay?`: entity filters generic, không có `major_name`.
- `Điểm chuẩn CNTT?` -> `Học phí của trường bao nhiêu?`: entity filters generic, không có `major_name`.
- `Điểm chuẩn CNTT?` -> `Còn Luật?`: explicit major override thành `Luật`.
- `Văn Hiến...` -> `Còn điểm chuẩn?`: external school giữ nguyên, retrieval 0.
- `Văn Hiến...` -> `Còn DHV thì sao?`: explicit DHV override, DHV path được phép và recording retriever gọi 1 lần.
- `Điểm chuẩn DHV CNTT?` -> `Còn Bách Khoa?`: switch sang `OTHER_SCHOOL`, retrieval 0.
- `Điểm chuẩn Bách Khoa?` -> `Cảm ơn`: intent `THANKS`, status `ok`, retrieval 0, không external fallback.

Kết luận: STATE-001 behavior **PASS trong targeted/fake-retriever runtime**.

## 10. Multi-turn Tests

| Scenario | Target/Intent | Retrieval | Result |
|---|---|---:|---|
| External school -> `Còn điểm chuẩn?` | external retained | 0 | PASS |
| External school -> `Còn DHV thì sao?` | explicit DHV override | 1 in fake path | PASS |
| DHV CNTT -> `Còn Bách Khoa?` | external switch | 0 | PASS |
| Bách Khoa -> `Cảm ơn` | `THANKS` | 0 | PASS |
| CNTT -> `Còn học phí?` | major follow-up | fake path allowed | PASS |
| CNTT -> generic school tuition | generic | fake path allowed, no major filter | PASS |
| CNTT -> `Còn Luật?` | explicit major override | route only | PASS |

## 11. Unsupported Recommendation Test

Input: `Học lực không giỏi thì ngành nào phù hợp?` với empty evidence fixture.

Observed:

- status `no_data`;
- no recommendation such as “ngành X phù hợp” hoặc “bạn nên học ngành Y”;
- recording retriever called 1 because this is an in-scope query requiring evidence;
- output is safe evidence-grounded fallback.

Kết luận: không tái hiện `UNSUPPORTED_RECOMMENDATION` trong case này.

## 12. Validator Defense Test

Synthetic verified DHV evidence có score `15`, `18`, `600` được truyền trực tiếp vào validator với cùng question external.

| Analysis target/scope | Validator status | Reason | Result |
|---|---|---|---|
| `OTHER_SCHOOL` / `external_school` | `no_data` | `school_scope_boundary` | PASS |
| `MIXED` / `mixed_school` | `no_data` | `school_scope_boundary` | PASS |
| `AMBIGUOUS` / `ambiguous_school` | `no_data` | `school_scope_boundary` | PASS |
| `DHV` / `in_scope_dhv` control | `ok` | none | PASS control |

Source review confirms `validate_model_answer()` is called from `rag_chain.py` generated and structured answer paths; validator is not dead code. Limitation: validator cannot reject a query that upstream incorrectly labels `UNSPECIFIED`, which is why `SEC-002` remains a boundary failure.

## 13. Real Runtime Traces

### Service availability

- `ollama list`: failed because `127.0.0.1:11434` was unavailable/forbidden by the current environment.
- HTTP `http://localhost:11434/api/tags`: same environment socket error.
- Chroma metadata read-only check: collection `dhv_admissions_2026`, count 247, years `[2026]`, statuses `[verified]`.

### Default `ask_chatbot` runtime

| Input | Target | Scope reason | Intent | Retrieval calls | Docs | Evidence | Status |
|---|---|---|---|---:|---:|---:|---|
| `Điểm chuẩn Bách Khoa?` | `OTHER_SCHOOL` | `external_school` | `HOI_DIEM_TRUNG_TUYEN` | 0 | 0 | 0 | `out_of_scope` |
| `diem chuan bach khoa?` | `OTHER_SCHOOL` | `external_school` | `HOI_DIEM_TRUNG_TUYEN` | 0 | 0 | 0 | `out_of_scope` |
| `Điểm chuẩn DHV CNTT?` | `DHV` | `in_scope_dhv` | `HOI_DIEM_TRUNG_TUYEN` | 0 before embedding failure | 0 | 0 | `ollama_offline` |
| `Điểm chuẩn CNTT?` | `UNSPECIFIED` | `in_scope_dhv` | `HOI_DIEM_TRUNG_TUYEN` | 0 before embedding failure | 0 | 0 | `ollama_offline` |

The real positive DHV retrieval path could not be completed, so the DHV-positive runtime criterion is **BLOCKED_BY_ENVIRONMENT**, not PASS.

## 14. Regression Suites

| Suite | Passed | Failed | Skipped | Blocked | Classification |
|---|---:|---:|---:|---:|---|
| `tests/test_priority_1_2_fix.py` | 14 tests + 10 subtests | 0 | 0 | 0 | PASS |
| Intent/Phase 2/Phase 4/Task F/Task I/Task J/UI targeted | 82 tests + 148 subtests | 0 | 0 | 0 | PASS |
| `python -m compileall -q src tests app.py` | PASS | 0 | 0 | 0 | PASS |
| `python -m pip check` | PASS | 0 | 0 | 0 | PASS |
| Full `pytest tests -q -p no:cacheprovider` | 168 | 12 | 4 | 0 | FAIL; 8 temp ACL, 3 Task 09 data/path, 1 Task C wording |
| Real DHV-positive Ollama/Chroma runtime | 0 | 0 | 0 | 4 positive cases | BLOCKED_BY_ENVIRONMENT |

Full-suite failure classification:

- `TEST_INFRA_FAILURE`: 8 failures caused by Windows sandbox/OneDrive temp directory permission/path cleanup (`PermissionError`/`FileNotFoundError`).
- Current non-scope contract/data failures: 3 Task 09 tests for stale school PDF/metadata path.
- Current non-scope wording failure: 1 Task C threshold assertion (`từ 15 điểm` vs output containing `15 điểm`).
- No Priority 1/2 targeted assertion failed.

## 15. Security Regression

Pass:

- No hard-coded user question or factual admission answer added.
- Alias registry is bounded and uses normalized text; no unbounded regex or recursive pattern was introduced.
- Coreference lists are bounded by `_MAX_CANDIDATES`, `_MAX_LISTED_MAJORS`, `_MAX_LISTED_ENTITIES` and method limit 4.
- External/mixed/ambiguous named-school paths do not call retriever or LLM.
- Validator defense rejects DHV evidence for explicit external/mixed/ambiguous analysis.
- Greeting/thanks do not reopen stale factual state.

Residual/regression finding:

- Generic external marker `trường đại học khác` bypasses school boundary and calls retrieval. This is a cross-domain data-integrity/security boundary failure, not merely a wording issue.
- `_OTHER_SCHOOL_MARKERS` is present but unused by `detect_target_school()`.
- No duplicate retrieval was observed in the fake-retriever cases; DHV positive real path was blocked before retrieval by Ollama failure.

## 16. New Bugs Found

### SEC-002

- Severity: **HIGH**
- Input: `Điểm chuẩn trường đại học khác?`
- Expected: `OTHER_SCHOOL`, `MIXED` hoặc `AMBIGUOUS`; retrieval calls 0; evidence 0; no DHV factual path.
- Actual: `target_school=UNSPECIFIED`, `scope_reason=in_scope_dhv`, recording retriever called once; status `no_data` only because fixture returned no documents.
- Probable root cause: `_OTHER_SCHOOL_MARKERS` contains generic external markers but is not consumed by `detect_target_school()`/`_school_mentions`; no unknown-school boundary is triggered for this phrase.
- Affected files: `src/chatbot/scope_guard.py`, `src/chatbot/query_analysis.py`, `src/chatbot/rag_chain.py`, `tests/test_priority_1_2_fix.py`.
- Owner: `LEAD_CODER`.
- Classification: **HIGH** because the user contract explicitly requires external-school retrieval to be zero; with a non-empty DHV collection this path can leak DHV facts.

No new CORE-001 or STATE-001 regression was reproduced in targeted tests or independent fixtures.

## 17. Acceptance Criteria

### SEC-001

- [PASS] Bách Khoa không còn `UNSPECIFIED`.
- [PASS] `bach khoa` không dấu được nhận diện.
- [PASS] External named-school retrieval/evidence là 0.
- [PASS] Mixed-school retrieval/evidence là 0.
- [PASS] Không có DHV factual leakage trong các named external cases đã chạy.
- [PASS] Explicit DHV và genuine unspecified queries vẫn đi được DHV/default path trong fake retriever.
- [BLOCKED] Real DHV-positive runtime xác nhận với Ollama/Chroma vì Ollama không khả dụng.
- [FAIL] External boundary tổng quát chưa đạt do `trường đại học khác` vẫn retrieval (`SEC-002`).

### CORE-001

- [PASS] List reference giữ toàn bộ `candidate_majors`.
- [PASS] Single reference resolve đúng major.
- [PASS] Program ordinal resolve đúng program và `parent_major`.
- [PASS] Method ordinal resolve đúng method.
- [PASS] Ambiguous reference trả clarification.
- [PASS] Không random entity và không trộn program thành major trong các case đã test.

### STATE-001

- [PASS] Semantic tuition follow-up giữ major.
- [PASS] Generic tuition không inherit stale major.
- [PASS] Explicit major override.
- [PASS] Explicit school override.
- [PASS] Greeting/thanks reset retrieval/factual output đúng.
- [PASS] External state không leak trong các multi-turn case đã chạy.
- [BLOCKED] Positive DHV retrieval E2E bằng Ollama thật.

## 18. Remaining Risks

- `SEC-002` là unresolved HIGH boundary risk dù `SEC-001` exact reproduction đã pass.
- Ollama unavailable làm chưa thể chứng minh đầy đủ retrieval/evidence của query DHV-positive bằng default runtime.
- Full test suite vẫn có 12 failures; phần lớn là infrastructure/stale contract nhưng vẫn cần tách và xử lý trước full release gate.
- Coreference production first-turn list/program extraction với dữ liệu Chroma thật chưa chạy được end-to-end do Ollama offline; direct resolver và targeted tests pass.
- Generic unknown institutions ngoài registry vẫn cần boundary policy được phê duyệt; không được default DHV nếu câu hỏi đã biểu thị trường khác.

## 19. Final Verdict

**`PRIORITY_1_2_QA_FAIL`**

Lý do:

1. Case gốc `SEC-001` (`Bách Khoa` có/không dấu) đã pass.
2. `CORE-001` và `STATE-001` pass trong targeted tests và independent fixture/runtime checks.
3. Nhưng external-school matrix bắt buộc vẫn có `Điểm chuẩn trường đại học khác?` đi vào retrieval; theo rule của audit đây là HIGH failure.
4. Real DHV-positive E2E bị blocked bởi Ollama unavailable, nên không thể tự gọi full PASS.

# HANDOFF TO LEAD CODER

- Bug ID: `SEC-002`
- Severity: **HIGH**
- Reproduce: gọi `ask_chatbot("Điểm chuẩn trường đại học khác?", retriever=RecordingRetriever())`.
- Expected: `target_school` external/ambiguous; `retrieval_calls=0`; `evidence_count=0`.
- Actual: `target_school=UNSPECIFIED`; `scope_reason=in_scope_dhv`; recording retriever calls = 1; status `no_data` với empty fixture.
- Probable root cause: `_OTHER_SCHOOL_MARKERS` chưa được nối vào target-school detection.
- Affected files: `src/chatbot/scope_guard.py`, `src/chatbot/query_analysis.py`, `src/chatbot/rag_chain.py`, `tests/test_priority_1_2_fix.py`.
- Acceptance criteria: mọi generic external markers (`trường đại học khác`, `đại học khác`, tương đương có dấu/không dấu) phải không retrieval/evidence; không false-positive với `Trường có những ngành nào?`; các case Bách Khoa/Văn Hiến/Hoa Sen/Văn Lang/Nguyễn Tất Thành vẫn pass.
- Tests QA sẽ rerun: full external matrix, false-positive DHV matrix, validator synthetic defense, targeted Priority 1+2 suite và real runtime sau khi Ollama khả dụng.

Không deploy. Không sửa code trong lượt retest.
