# PRIORITY 1 + 2 FIX REPORT

Ngày thực hiện: 2026-10-07  
Vai trò: Lead Coder  
Phạm vi: SEC-001, CORE-001, STATE-001

## 1. Scope

- SEC-001: chặn wrong-school factual leakage.
- CORE-001: resolve coreference cho entity đơn, list và ordinal.
- STATE-001: phân biệt semantic follow-up với câu hỏi generic/unrelated.
- Không xử lý Priority 3: SMOKE-001, DATA-001, EVAL-001, VAL-001, TEST-001 environment ACL, PERF-001.
- Không sửa QA report cũ, raw PDF, dataset, model, embedding, Chroma hoặc deployment.

## 2. Root Cause Verification

- `Bách Khoa`/`bach khoa` không có trong registry alias bare-institution, nên `detect_target_school()` trả `UNSPECIFIED`; downstream mặc định DHV và retrieval.
- State có `last_listed_majors` nhưng không có resolver semantic chuyển reference thành candidate entities; vì vậy `các ngành nêu trên` bị mất list.
- `HOI_HOC_PHI` bị loại khỏi context inheritance chung, chưa có quyết định follow-up riêng; đồng thời bỏ exclusion mù quáng sẽ làm generic tuition kéo major cũ.
- Validator chỉ thấy evidence DHV hợp lệ theo target đã bị phân loại sai, nên không thể tự sửa lỗi upstream.

## 3. Architecture Before

```text
question
  -> query analysis / classifier
  -> target school detection
  -> state merge bằng intent exclusion
  -> router
  -> scope boundary hoặc retrieval
  -> evidence / deterministic answer / LLM
  -> output validator
```

Các điểm thiếu: bare institution alias, generic coreference resolver, bounded program/method list state và semantic inherit decision.

## 4. Architecture After

```text
question
  -> normalize
  -> institution registry + unknown-name boundary
  -> bounded coreference resolver (major/program/method/school)
  -> intent + semantic should_inherit_context()
  -> explicit school boundary before retrieval
  -> retrieval only for DHV/valid unspecified default
  -> evidence / deterministic answer / LLM
  -> validator scope invariant + evidence validation
  -> bounded state update
```

Named `OTHER_SCHOOL`, `MIXED` hoặc `AMBIGUOUS` kết thúc trước retrieval; không gọi BM25, dense, Chroma, RRF hoặc evidence selection.

## 5. Files Changed

| File | Function/Area | Reason |
|---|---|---|
| `src/chatbot/scope_guard.py` | external institution alias registry | Nhận diện bare alias `Bách Khoa`/`bach khoa` qua semantic institution registry, không để rơi vào DHV default. |
| `src/chatbot/query_analysis.py` | `ConversationState`, coreference, intent/state routing | Thêm bounded lists cho program/method; resolve list/single/ordinal; thêm `should_inherit_context`; thêm `THANKS`; giữ entity type/parent. |
| `src/chatbot/rag_chain.py` | state capture, system answer, trace | Lưu program list context, trace retrieval/evidence counts, xử lý THANKS deterministic. |
| `src/chatbot/output_validator.py` | validator boundary | Defense thứ hai cho external/mixed/ambiguous scope. |
| `tests/test_priority_1_2_fix.py` | targeted regression matrix | Test SEC-001, CORE-001, STATE-001 và invariants retrieval/evidence. |
| `PRIORITY_1_2_FIX_REPORT.md` | handoff report | Bàn giao cho QA & Security. |

## 6. SEC-001 Implementation

- Bổ sung bare institution alias vào registry đã có; không hard-code nguyên câu hỏi hoặc factual data.
- `OTHER_SCHOOL`, `MIXED`, `AMBIGUOUS` vẫn đi qua `_school_scope_boundary_result()` trước khi active retriever được khởi tạo.
- Validator từ chối nếu analysis có target/scope reason external, mixed hoặc ambiguous, kể cả khi caller truyền nhầm evidence DHV vào validator.
- Bảo toàn behavior:
  - Văn Hiến, Hoa Sen, Văn Lang, Nguyễn Tất Thành: `OTHER_SCHOOL`.
  - Bách Khoa có dấu/không dấu: `OTHER_SCHOOL`.
  - DHV explicit: `DHV`.
  - Không nêu trường: `UNSPECIFIED`, được phép default DHV.
  - DHV + trường khác: `MIXED`, không chạy unsupported comparison retrieval.

## 7. CORE-001 Implementation

- Resolver hỗ trợ:
  - list: `các ngành trên`, `các ngành nêu trên`, `những ngành vừa kể`, chương trình/phương thức tương ứng;
  - single: `ngành đó`, `chương trình đó`, `phương thức đó`, `cái đó`;
  - ordinal: `cái thứ hai`, `chương trình thứ hai`, `phương thức thứ hai`;
  - alternative/ambiguous: `cái kia`, `còn cái kia`.
- List reference tạo `candidate_majors`/`candidate_programs`, không tự chọn một entity.
- Ordinal chỉ resolve khi list đủ rõ; nếu thiếu/không hợp lệ thì `needs_clarification=True`.
- State mới giữ `last_listed_programs`, `last_listed_program_parents`, `last_listed_methods` và `candidate_methods` bounded.
- `entity_type` và `parent_major` được giữ khi resolve program; method không bị trộn vào major.
- Câu catalog first-turn kiểu “liệt kê những ngành đó” vẫn được hiểu là list request, không bị biến thành unresolved reference.

## 8. STATE-001 Implementation

- Thêm `should_inherit_context()` dựa trên câu hiện tại, intent, previous intent và state.
- `Còn học phí?` kế thừa major/program khi có tín hiệu follow-up.
- `Học phí của trường bao nhiêu?`, `Học phí DHV hiện nay?` không tự kéo major cũ.
- `Học phí ngành khác thì sao?` đi vào clarification khi entity mới chưa được resolve.
- Explicit major/school ở turn mới luôn override state cũ.
- Greeting/thanks/system/out-of-scope không inject factual state vào câu trả lời; thêm intent deterministic `THANKS` để `Cảm ơn` không rơi vào scope fallback.
- Candidate majors/programs được coi là context hợp lệ cho multi-turn recommendation có score, bảo toàn regression Task F.

## 9. Runtime Traces

| Case | target/scope | retrieval calls | retrieved chunks | evidence | status |
|---|---|---:|---:|---:|---|
| `Điểm chuẩn Bách Khoa?` real runtime | `OTHER_SCHOOL / external_school` | 0 | 0 | 0 | `out_of_scope` |
| `diem chuan bach khoa?` targeted | `OTHER_SCHOOL / external_school` | 0 | 0 | 0 | `out_of_scope` |
| `Điểm chuẩn Văn Hiến?` targeted | `OTHER_SCHOOL / external_school` | 0 | 0 | 0 | `out_of_scope` |
| `Học phí Hoa Sen?` targeted | `OTHER_SCHOOL / external_school` | 0 | 0 | 0 | `out_of_scope` |
| `So sánh DHV và Văn Hiến` targeted | `MIXED / mixed_school` | 0 | 0 | 0 | `out_of_scope` |
| `Điểm chuẩn DHV CNTT?` fake retriever contract | `DHV / in_scope_dhv` | 1 | 0 | 0 | `no_data` |
| `Điểm chuẩn CNTT?` fake retriever contract | `UNSPECIFIED / in_scope_dhv` | 1 | 0 | 0 | `no_data` |
| external turn 1 `Văn Hiến...` -> `Còn điểm chuẩn?` | external state retained | 0 + 0 | 0 | 0 | `out_of_scope` |
| external -> `Còn DHV thì sao?` | explicit `DHV` override | 1 | adapter-dependent | adapter-dependent | DHV path allowed |
| list -> `Điểm sàn các ngành nêu trên?` | `candidate_majors` = previous full list | not required for analysis assertion | n/a | n/a | list resolved |

Real default runtime for `Điểm chuẩn DHV CNTT?` was attempted but returned `ollama_offline` before a completed retrieval trace in this environment. This is recorded as runtime infrastructure limitation; the DHV/no-regression contract is covered by the targeted deterministic/retriever tests above.

## 10. Tests

| Suite | Passed | Failed | Skipped | Blocked |
|---|---:|---:|---:|---:|
| `tests/test_priority_1_2_fix.py` | 14 tests + 10 subtests | 0 | 0 | 0 |
| Targeted intent/Phase 2/Phase 4/Task F/Task I/UI/App + new regression | 92 tests + 152 subtests | 0 | 0 | 0 |
| `python -m compileall -q src/chatbot tests` | PASS | 0 | 0 | 0 |
| `python -m pip check` | PASS | 0 | 0 | 0 |
| Full `pytest -q -p no:cacheprovider` | 168 | 12 | 4 | 0 |

Full-suite failures are classified separately: 8 Windows temp/ACL failures, 3 pre-existing Task 09 raw/data-contract failures, and 1 pre-existing Task C wording/contract failure. No Priority 1/2 targeted assertion failed.

## 11. Regression Results

- Phase 2 runtime: PASS.
- Phase 4 answer behavior: PASS.
- Intent classifier: PASS.
- Task F conversation/recommendation grounding: PASS after preserving candidate-list inheritance.
- Task I system router/state: PASS.
- UI/App contract suites: PASS.
- Existing full-suite non-scope failures remain unchanged and were not masked or deleted.
- Unsupported recommendation defense remains evidence/state constrained; no recommendation engine redesign was introduced.

## 12. Remaining Risks

- Real DHV Chroma/Ollama E2E could not complete because Ollama was offline in the current environment; QA must rerun with services available.
- The deterministic institution registry cannot identify every arbitrary unknown bare proper name without a broader approved institution directory; structural `trường/đại học/học viện/cao đẳng` detection remains the fallback.
- Full-suite Windows temp ACL and existing Task 09/Task C contract drift remain outside this task.
- QA should verify mixed-school responses do not claim a factual side-by-side comparison after real retrieval/runtime wiring.

## 13. Acceptance Criteria

### SEC-001

- [PASS] `Bách Khoa` is no longer `UNSPECIFIED`.
- [PASS] `bach khoa` is detected without diacritics.
- [PASS] Văn Hiến, Hoa Sen, Văn Lang, Nguyễn Tất Thành remain external.
- [PASS] Mixed school target is blocked before retrieval.
- [PASS] External retrieval calls = 0 and evidence count = 0 in targeted matrix and real Bách Khoa trace.
- [PASS] DHV explicit query remains allowed; targeted regression passes.
- [PASS] Genuine unspecified DHV-default query remains allowed; targeted regression passes.

### CORE-001

- [PASS] `last_listed_majors` resolves to the full candidate list.
- [PASS] `các ngành nêu trên` does not choose a random major.
- [PASS] Single entity references resolve from bounded state.
- [PASS] Program/method ordinal references resolve when list context is sufficient.
- [PASS] Ambiguous reference returns clarification.
- [PASS] Entity type and program parent are preserved.

### STATE-001

- [PASS] `Điểm chuẩn CNTT?` -> `Còn học phí?` keeps CNTT in semantic follow-up plan.
- [PASS] Generic school tuition does not inherit stale major.
- [PASS] Explicit major overrides previous major.
- [PASS] Explicit DHV overrides external-school state.
- [PASS] Greeting and thanks do not retrieve or reuse factual answer state.
- [PASS] No stale external-school fallback leaks into greeting/thanks.
- [PASS] No stale major leak was observed in targeted state tests.

## 14. Handoff To QA

QA & Security should review the changed files and rerun at minimum:

1. Real Chroma/Ollama `Điểm chuẩn Bách Khoa?` and `diem chuan bach khoa?`; verify `target_school`, `scope_reason`, `retrieval_calls`, `retrieved_docs_count`, `evidence_count`, final status and absence of DHV numbers.
2. External matrix: Văn Hiến, Hoa Sen, Văn Lang, Nguyễn Tất Thành.
3. Mixed: `So sánh DHV và Văn Hiến`.
4. Multi-turn external retention and explicit DHV override.
5. `Liệt kê các ngành DHV` -> `Điểm sàn các ngành nêu trên?`.
6. `CNTT có những chương trình nào?` -> `Chương trình thứ hai học gì?`.
7. `Điểm chuẩn CNTT?` -> `Còn học phí?`, plus generic tuition and explicit-major override.
8. Greeting/thanks reset and unsupported recommendation adversarial case.
9. Targeted suites listed in section 10, then full regression with temp ACL result separated.

Không deploy. Không xử lý Priority 3. Lead Coder không kết luận QA PASS cuối cùng.

## Final Verdict

READY_FOR_QA
