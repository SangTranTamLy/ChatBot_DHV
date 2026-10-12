# QA & SECURITY — REVIEW LƯỢT 2, WORKING TREE MỚI NHẤT (2026-10-12)

> Đây là kết quả có thẩm quyền cho patch mới nhất và thay thế kết luận về scholarship ở các addendum lịch sử phía dưới. Review/trace là read-only; QA chỉ cập nhật report. Không chạy full pytest theo yêu cầu Lead; không sửa source, tests, data, processed JSON hoặc Chroma; không deploy.

## Verdict

**FAIL tổng thể targeted review; scholarship patch PASS trong hai case được yêu cầu.** Single-intent và multi-intent hiện đều loại bảng ngành khỏi selected evidence, chọn được evidence học bổng, trả danh sách chính sách bằng deterministic renderer và không gọi LLM. External/mixed boundary và advisory fail-closed PASS. Ollama live BLOCKED. Targeted suite còn 5 subtest lỗi ánh xạ chương trình-ngành cha; chúng độc lập với scholarship patch.

## Diff / thay đổi được review

- `src/chatbot/query_analysis.py`: `HOI_HOC_BONG` bỏ major/program entity filters trong `route_question`; “học bổng gì/nào” có `query_mode=LIST`; giữ categories phù hợp câu hỏi.
- `src/chatbot/evidence.py`: content filter cho `HOI_HOC_BONG` loại chunk đồng thời chứa header `tên ngành`, `chương trình đào tạo`, `mã ngành` với lý do `unrelated_program_catalogue`; chunk không nói về học bổng bị loại bằng `intent_content_mismatch`.
- `src/chatbot/rag_chain.py`: dùng evidence scholarship/catalog renderer trước fallback/generation; multi-issue vẫn trả từng subplan và partial flag.
- `tests/test_task_f.py`: regression đơn ý `CNTT có học bổng gì?` và câu nhiều ý; assertion query mode, filters, scholarship heading/evidence, loại bảng chương trình và không gọi LLM.
- Đọc thêm `tests/test_task_i.py`, `tests/test_priority_1_2_fix.py`, `tests/test_admission_conditions.py`, `tests/test_intent_classifier.py`, `tests/test_task_response_ui.py`, `tests/test_runtime_enrollment.py`, `tests/test_full_sweep_p1.py`, cùng validator/admission paths.

## Test commands và kết quả

QA dùng temp riêng `.test_tmp\qa_security_round2`; không chạy full pytest.

```powershell
$qaTmp = Join-Path (Resolve-Path .test_tmp).Path 'qa_security_round2'
$env:TEMP = $qaTmp
$env:TMP = $qaTmp
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_task_f.py tests/test_task_i.py tests/test_priority_1_2_fix.py `
  tests/test_admission_conditions.py tests/test_intent_classifier.py `
  tests/test_task_response_ui.py tests/test_runtime_enrollment.py `
  tests/test_full_sweep_p1.py
```

Kết quả: **5 failed, 199 passed, 232 subtests passed (25.87s)**. Năm lỗi duy nhất là `TaskFAnalysisTests.test_declared_programs_resolve_and_keep_evidence_parent`, mỗi lỗi actual `parent_major=None`:

| Giá trị chương trình trong test | Expected | Actual | Phân loại |
|---|---|---|---|
| `Quản trị Marketin` | `Marketing` | `None` | Entity/parent relation resolution |
| `Phân tích dữ liệu kinh doan` | `Thương mại điện tử` | `None` | Entity/parent relation resolution |
| `Ngôn ngữ - Văn hóa Nhật Bản` | `Ngôn ngữ Nhật` | `None` | Entity/parent relation resolution |
| `Tiếng Trung văn hóa - Du lịch` | `Ngôn ngữ Trung Quốc` | `None` | Entity/parent relation resolution |
| `Tâm lý tổ chức - Nhân sự` | `Tâm lý học` | `None` | Entity/parent relation resolution |

Phân loại: lỗi test/runtime mapping đang còn, chưa xác định là regression của scholarship patch; mức Medium. Các test khác trong lệnh, gồm requested external/mixed, admission conditions, method formula, advisory và Task I/F/runtime, đã pass.

Hai regression scholarship được chạy độc lập:

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_task_f.py::TaskFGenerationTests::test_single_issue_major_scholarship_question_uses_policy_not_program_table `
  tests/test_task_f.py::TaskFGenerationTests::test_multi_issue_scholarship_retrieves_verified_policy_and_marks_partial_result
```

Kết quả: **2 passed in 16.80s**.

## Traces — positive fixture/corpus-backed runtime

Các trace dùng `ask_chatbot`, processed corpus hiện có qua test `DHVRetriever`/`CorpusStore`, và `EchoEvidenceLLM`; đây **không phải** production Chroma/Ollama E2E. Retrieval/evidence/source counts dưới đây là đúng trace của lần chạy này.

### Single intent: `CNTT có học bổng gì?`

| Trường | Kết quả |
|---|---|
| Intent / query mode | `HOI_HOC_BONG` / `LIST` |
| Categories | `hoc_bong`, `phuong_thuc_xet_tuyen`, `ho_so` |
| Entity context / effective entity filters | Context vẫn nhận `major_name=Công nghệ thông tin`, `candidate_majors=[Công nghệ thông tin]`; `route_question.entity_filters={}` |
| Retrieval / docs / selected evidence | **1 / 70 / 55**; selection candidate count 70, selected 55 |
| Selected categories | `hoc_bong`: 37; `phuong_thuc_xet_tuyen`: 11; `ho_so`: 7 |
| Filter reasons | `unrelated_program_catalogue`: 3; `intent_content_mismatch`: 12 |
| Catalogue guard | 0 selected preview chứa đủ ba header ngành/chương trình/mã ngành; 3 catalogue chunks bị loại với `unrelated_program_catalogue` |
| Selected policy preview | `hoc_bong` evidence gồm “Mức học bổng: Lên đến 50% học phí học kỳ 2”, điều kiện học bổng tuyển sinh và nội dung hỗ trợ học phí |
| LLM / status / answer | **0** LLM calls; `ok`; deterministic answer liệt kê 8 tên/chính sách học bổng; không có header bảng hoặc tên chương trình |
| Sources | `https://tuyensinh.dhv.edu.vn/`; `https://dhv.edu.vn/huong-dan-thu-tuc-nhap-hoc-dhv-2026-va-thong-tin-tu-van-vien-ho-tro-tan-sinh-vien/` |

**Case verdict: PASS.** Scholarship policy evidence không bị loại; bảng chương trình không được chọn, gửi LLM hay hiển thị trong câu trả lời.

### Multi intent: `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?`

Root: `MULTI_ISSUE`; query mode `LIST`; entity context có CNTT; **3 calls / 62 retrieved docs / 18 evidence chunks**, final `ok`, `partial=true`, `complete=false`; LLM calls **0**. Sources giống trace single-intent trên.

| Subplan | Categories / effective entity filters | Calls / docs / evidence | Selected/filtered evidence và kết quả |
|---|---|---:|---|
| `HOI_HOC_PHI` | `hoc_phi`; giữ major CNTT + candidate major | **1 / 0 / 0** | Không có selected/filtered candidate trong kết quả truy xuất; status `no_data`, phần học phí nói rõ thiếu dữ liệu đã xác minh. |
| `HOI_HOC_BONG` | `hoc_bong`, `phuong_thuc_xet_tuyen`; filters `{}` | **1 / 58 / 16** | Evidence selection selected 48; category counts: `hoc_bong` 37, `phuong_thuc_xet_tuyen` 11. Policy previews có mức hỗ trợ đến 50% học phí HK2, điều kiện và “Học bổng tuyển sinh 2026: 70%...”. Filtered: 3 `unrelated_program_catalogue`, 7 `intent_content_mismatch`; 0 selected preview có đủ header bảng. Status `ok`; câu trả lời liệt kê 8 policy/headings, không render chương trình. |
| `DANH_SACH_CHUONG_TRINH` | `nganh_dao_tao`; giữ major CNTT + candidate major | **1 / 4 / 2** | Selected evidence là hai record ngành CNTT và danh sách 5 chương trình; status `ok`. 2 catalog summaries bị loại với `catalog_summary_shadowed_by_entity_row`. Bảng/chương trình chỉ nằm trong section chương trình riêng. |

**Case verdict: PASS cho xử lý scholarship; response tổng thể PARTIAL.** Học phí là subplan `no_data`, nhưng không làm mất phần học bổng hoặc danh sách chương trình. Không có bảng chương trình trong selected scholarship evidence, prompt LLM, hoặc section “Học bổng”. Evidence policy có mặt; các catalogue chunks bị chặn bằng lý do cụ thể.

## Boundary, advisory và live Ollama

| Case | Trace | Verdict |
|---|---|---|
| `Điểm chuẩn trường đại học khác?` | `HOI_DIEM_TRUNG_TUYEN`; target `OTHER_SCHOOL`; `external_school`; retrieval/docs/evidence **0/0/0**; LLM 0; `out_of_scope` | **PASS** — external boundary trước retrieval. |
| `So sánh DHV và Văn Hiến` | `HOI_CO_SO_LIEN_HE`; target `MIXED`; `mixed_school`; retrieval/docs/evidence **0/0/0**; LLM 0; `out_of_scope` | **PASS** — mixed boundary trước retrieval. |
| `Tôi thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH`; categories `nganh_dao_tao`, `nguong_dau_vao`; **1/82/82**; validator `clarification`, `personal_fit_not_in_verified_evidence`; LLM 0 | **PASS** — không sinh tư vấn cá nhân thiếu căn cứ. |
| Ollama live | `ollama list` → `connectex` socket permission error ở `127.0.0.1:11434` | **BLOCKED** — không xác minh Qwen/active Chroma E2E. |

## Handoff / verdict cuối

- Lead: duy trì hai sửa đổi scholarship đã pass; thêm boundary regression nếu cần bảo vệ không lọt bảng vào selected evidence khi taxonomy/page thay đổi.
- Lead: xử lý riêng năm `parent_major=None` nếu chúng nằm trong acceptance scope; xác minh relation theo processed source, không sửa expected chỉ để xanh.
- QA: đọc kết quả full pytest do Lead chạy riêng và lặp live Ollama/Chroma khi socket khả dụng.
- **Scholarship single-intent: PASS. Scholarship multi-intent: PASS, response partial do học phí no-data. External/mixed: PASS. Advisory: PASS. Live runtime: BLOCKED. Targeted suite: FAIL do 5 entity-parent failures. Overall verdict: FAIL.**

---

# LATEST QA & SECURITY REVIEW — 2026-10-12

> This section is the authoritative review of the latest working-tree snapshot for the scholarship-filter follow-up. It supersedes all earlier traces, test counts, and verdicts retained below as historical context. QA performed no source, test, corpus, processed-JSON, or Chroma edits. The full pytest run was intentionally not started because the user is running it separately.

## Verdict

**FAIL — return to Lead Coder.** The requested multi-intent scholarship response now uses verified scholarship-policy evidence and renders no program catalogue under “Học bổng”. External/mixed boundaries and unsupported personal-fit fail-closed also pass. However, the natural single-intent query `CNTT có học bổng gì?` still retrieves a program catalogue as its only evidence, passes it to generation, and returns it with `status=ok`. The fix is therefore not consistent across the multi-intent and ordinary single-intent paths. The focused test run also has five existing program-parent relation failures. Live Ollama/active-Chroma E2E is **BLOCKED** by the local socket error.

## Scope and diff reviewed

Read `reports/TONG_QUAN_AGENT`; followed the QA & Security read-only role. Reviewed the latest working-tree edits and the relevant live paths/tests:

| File | Area reviewed |
|---|---|
| `src/chatbot/rag_chain.py` | `_ask_multi_issue`: scholarship retrieval plan removes major/program metadata filters while retaining question/entity context; scholarship document prioritization; deterministic scholarship catalog answer before fallback/general generation. Also compared the ordinary single-intent scholarship path. |
| `src/chatbot/query_analysis.py` | Scholarship subplan categories and entity/subplan analysis; verified that the ordinary `HOI_HOC_BONG` route still carries major filters. |
| `src/chatbot/output_validator.py` | Current advisory/factual defense path; no validator gate prevented the single-intent irrelevant catalogue answer. |
| `tests/test_task_f.py` | New exact multi-intent regression assertions for scholarship headings/evidence, absence of program-table text, categories, cleared entity filters, and partial result; existing program-parent tests. |
| `tests/test_task_i.py` | Scholarship category routing assertion. |
| `tests/test_admission_conditions.py` | Admission condition/method regressions. |
| `tests/test_priority_1_2_fix.py` | External-school/security regression coverage. |
| `tests/test_intent_classifier.py` | Advisory intent/fail-closed coverage. |
| `tests/test_task_response_ui.py` | Output/advisory regressions. |
| `tests/test_runtime_enrollment.py` | Enrollment runtime regression coverage. |
| `tests/test_data_pipeline_recovery.py` | Manifest/data-pipeline regression coverage. |
| `tests/test_full_sweep_p1.py` | Bounded retrieval/config regression coverage. |

The reviewed source/test files were already modified in the shared working tree; QA did not change them. QA updated only this report. No Chroma rebuild or deployment occurred.

## Commands and test results

The targeted run used its own temporary directory to avoid colliding with the user's full-suite run:

```powershell
$qaTmp = Join-Path (Resolve-Path .test_tmp).Path 'qa_security'
if (-not (Test-Path -LiteralPath $qaTmp)) { New-Item -ItemType Directory -Path $qaTmp | Out-Null }
$env:TEMP = $qaTmp
$env:TMP = $qaTmp
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_task_i.py tests/test_task_f.py tests/test_priority_1_2_fix.py `
  tests/test_admission_conditions.py tests/test_intent_classifier.py `
  tests/test_task_response_ui.py tests/test_runtime_enrollment.py `
  tests/test_data_pipeline_recovery.py tests/test_full_sweep_p1.py
```

**Result: 5 failed, 203 passed, 232 subtests passed (27.62s).** The five failures are the Task F program-parent subcases listed below. The exact new multi-intent scholarship regression passed. Full pytest: **NOT RUN by QA**, at the user's request; its result must be read from the user's separate run, not inferred here.

## Runtime trace methodology and limits

Positive DHV traces below use `ask_chatbot` with the current processed corpus via `tests/test_task_f.py`'s `DHVRetriever`/`CorpusStore` and `EchoEvidenceLLM`. This is a corpus-backed deterministic diagnostic, **not** active Chroma + Ollama production E2E. Boundary traces use the current scope detector and a call-recording/never-call test path. The Echo model intentionally exposes exactly what context the ordinary generation path receives; do not interpret these traces as a live Qwen response.

### Exact multi-intent query

Input: `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?`

Root trace: `intent=MULTI_ISSUE`; **retrieval_calls=3**, **retrieved_docs_count=62**, **evidence_count=15**, `status=ok`, `partial=true`, `complete=false`. The root answer preserves the tuition `no_data` section, lists scholarships, and lists CNTT programs. `EchoEvidenceLLM` prompts: **0**.

| Subplan | Categories | Effective entity filters | Calls / docs / evidence | Selected evidence preview | Status / rendered result |
|---|---|---|---:|---|---|
| `HOI_HOC_PHI` | `hoc_phi` | `major_name=Công nghệ thông tin`, `candidate_majors=[Công nghệ thông tin]` | **1 / 0 / 0** | None | `no_data`; partial answer clearly says data was not found. |
| `HOI_HOC_BONG` | `hoc_bong`, `phuong_thuc_xet_tuyen` | `{}` after the subplan strips major/program filters; major remains in the parent question/entity context | **1 / 58 / 13** | Selected verified `hoc_bong` chunks include “Chính sách học bổng … lên đến 50% học phí học kỳ 2”, scholarship eligibility/policy text, and “Học bổng Đôi bạn cùng tiến”. | `ok`; deterministic catalog answer lists eight evidence-backed scholarship headings. Rendered section contains **no** `TÊN NGÀNH`, `CHƯƠNG TRÌNH ĐÀO TẠO`, or program names; no LLM prompt. No scholarship heading/policy list was dropped for this query. |
| `DANH_SACH_CHUONG_TRINH` | `nganh_dao_tao` | `major_name=Công nghệ thông tin`, `candidate_majors=[Công nghệ thông tin]` | **1 / 4 / 2** | Verified `nganh_dao_tao` previews identify CNTT and its five program rows. | `ok`; program list is rendered in its own section, not under scholarship. |

The scholarship subplan's selected evidence includes relevant policy passages and the effective retrieval filters are empty as intended. The trace also shows a program-table document can remain among the scholarship candidates from the shared method source category; deterministic evidence-owned rendering suppresses it in this multi-intent case. Thus the **rendered-output criterion passes**, but the selection set is not perfectly uncontaminated and must not be treated as generally safe for an LLM fallback.

### Natural single-intent variant — confirmed failure

Input: `CNTT có học bổng gì?`

Trace: `intent=HOI_HOC_BONG`; categories `hoc_bong`, `phuong_thuc_xet_tuyen`, `ho_so`; entity filters retain `major_name=Công nghệ thông tin` and `candidate_majors=[Công nghệ thông tin]`; **retrieval_calls=1, docs=1, evidence=1**; selected document category is `phuong_thuc_xet_tuyen`, with preview beginning `TÊN NGÀNH | CHƯƠNG TRÌNH ĐÀO TẠO | MÃ NGÀNH`. Scholarship-policy evidence was not selected. The ordinary answer path made **one LLM call**; the fixture Echo returned that program catalogue. Final `status=ok`, despite the evidence not answering the scholarship question.

**FAIL — HIGH correctness/grounding finding.** The multi-intent fix is scoped to `_ask_multi_issue`; the equivalent ordinary single-intent path retains major filters and permits an irrelevant program table to become the only evidence and generation context. The successful multi-intent assertion does not cover this one-intent boundary. Lead should make scholarship-policy eligibility/prioritization consistent for entity-conditioned single-intent queries and add a regression asserting selected evidence and output relevance; do not merely loosen the validator or accept nonzero evidence counts.

Control input: `DHV có những học bổng nào?` returned `status=ok`, intent `HOI_HOC_BONG`, one retrieval, 70 docs/evidence, and a deterministic list of scholarship headings from the processed-corpus-backed retriever. This indicates the failure is associated with the major-conditioned route, not a total absence of scholarship data.

## Security and advisory traces

| Input | Target / intent | Categories / filters | Calls / docs / evidence | Validator / LLM / final status | Result |
|---|---|---|---:|---|---|
| `Điểm chuẩn trường đại học khác?` | `OTHER_SCHOOL`, `external_school`; `HOI_DIEM_TRUNG_TUYEN` | `diem_trung_tuyen`; no evidence filters applied after boundary | **0 / 0 / 0** | Validator not reached; LLM **0**; `out_of_scope` | **PASS:** stops before retrieval. |
| `So sánh DHV và Văn Hiến` | `MIXED`, `mixed_school`; `HOI_CO_SO_LIEN_HE` | `co_so_lien_he`; no retrieval plan executed | **0 / 0 / 0** | Validator not reached; LLM **0**; `out_of_scope` | **PASS:** stops before retrieval. |
| `Tôi thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH` | `nganh_dao_tao`, `nguong_dau_vao`; no explicit entity filter | **1 / 82 / 82** | Validator returns `clarification`, reason `personal_fit_not_in_verified_evidence`; LLM **0**; final `clarification` | **PASS:** evidence retrieval does not lead to unsupported personal-fit generation. |

## Five focused test failures

**Classification:** entity-relation resolution gaps against the processed structured records / query aliases. **Severity: Medium.** The assertion expects a parent major, actual is `None` for each:

| Program query/test value | Expected parent | Actual | Evidence/root-cause note |
|---|---|---|---|
| `Quản trị Marketin` | `Marketing` | `None` | The processed record uses canonical `Quản trị Marketing`; `enrich_analysis_from_evidence` joins only by exact normalized program-name equality, so the truncated alias does not match. |
| `Phân tích dữ liệu kinh doan` | `Thương mại điện tử` | `None` | Processed relation is `Phân tích dữ liệu kinh doanh`; exact normalized join does not resolve the truncated alias. |
| `Ngôn ngữ - Văn hóa Nhật Bản` | `Ngôn ngữ Nhật` | `None` | Structured processed records split the displayed wording into separate program entries (`Ngôn ngữ` and `Văn hóa Nhật Bản`); exact relation lookup has no combined key. |
| `Tiếng Trung văn hóa - Du lịch` | `Ngôn ngữ Trung Quốc` | `None` | Runtime evidence relation does not contain the exact combined normalized query key; the processed table representation must be checked before choosing a canonical mapping. |
| `Tâm lý tổ chức - Nhân sự` | `Tâm lý học` | `None` | Expected mapping is not resolved by the evidence relation available to `build_evidence`; exact normalized lookup returns no relation. |

The direct implementation evidence is `enrich_analysis_from_evidence`, which matches `normalize_question(relation.program_name) == normalize_question(entities.program_name)` without a canonical alias/compound-name bridge. Do not alter expected parents without confirming the processed source relationship. These failures are separate from the scholarship output finding.

## Ollama / active Chroma

`ollama list` was retried on this snapshot; the local Ollama service at `127.0.0.1:11434` fails with a Windows socket permission/connect error. **BLOCKED:** no live Qwen generation, embedding call, or active Chroma retrieval could be validated. Fixture-backed runs are not counted as production E2E passes.

## Acceptance and handoff

| Criterion | Result |
|---|---|
| Exact multi-intent scholarship subplan retrieves verified policy evidence | **PASS** in processed-corpus-backed trace (13 evidence chunks; relevant policy previews present). |
| No program catalogue is rendered under the multi-intent “Học bổng” heading | **PASS**; program list appears in its own subplan/heading. |
| Scholarship list/policy is not dropped from that multi-intent answer | **PASS**; eight named scholarships are rendered. |
| Ordinary entity-conditioned scholarship question avoids unrelated program-table answer | **FAIL**; `CNTT có học bổng gì?` returns program table with final `status=ok`. |
| External/mixed questions stop before retriever and LLM | **PASS**; both tested cases have 0 calls/docs/evidence and 0 LLM calls. |
| Unsupported personal-fit advice fails closed before LLM | **PASS** in the tested case; clarification, 0 LLM calls. |
| Targeted suites clean | **FAIL**; 5 program-parent subcases fail. |
| Full pytest | **NOT RUN by QA**; user is running independently. |
| Live Ollama + active Chroma | **BLOCKED** by local socket permission error. |

**Handoff to Lead Coder:** (1) fix the single-intent, major-conditioned scholarship route so verified scholarship-policy evidence is selected ahead of unrelated catalogue chunks and a wrong-context generation cannot return `status=ok`; add the requested one-intent natural regression. (2) Consider excluding irrelevant table chunks at evidence selection, not relying solely on the multi-intent deterministic formatter. (3) Resolve the five program-parent relations against canonical processed JSON without rewriting expected answers to force green. (4) Ask QA to rerun targeted tests and review the user's full-pytest result; rerun live Chroma/Ollama only when the local service is available. No deploy was performed.

**Authoritative latest-snapshot verdict: FAIL.**

---

# QA & Security Review — Post-Admission Runtime Fix

## FINAL WORKING-TREE ADDENDUM — method formula follow-up and học-bạ format

This addendum reviews the latest working tree after the Lead's THPT follow-up fix and the subsequent formatting adjustment. It supersedes earlier test counts and formula traces in this report.

### Verdict

**FAIL — hand back to Lead Coder.** The THPT method follow-up and the `Cách 1`/`Cách 2` học-bạ formatting regression both pass in the final targeted rerun. External/mixed boundaries and personal-fit fail-closed also pass on this tree. The independent multi-intent scholarship case still places a program catalogue under the “Học bổng” section instead of selecting scholarship-policy evidence; five program-parent subtests also remain failing. Ollama is still unavailable, so live model/active-Chroma E2E remains blocked.

### Latest implementation reviewed

- `src/chatbot/query_analysis.py`: the follow-up phrase resolves to `HOI_CACH_TINH_DIEM`, preserves `admission_method=thpt`, and routes to `phuong_thuc_xet_tuyen`.
- `src/chatbot/rag_chain.py`: method formula retrieval is bounded at `top_k=16`; deterministic method calculation runs from verified method details before LLM generation. For `hoc_ba`, exactly two verified bullet formulae are rendered as `Cách 1` and `Cách 2`.
- `tests/test_admission_conditions.py` and `tests/test_task_f.py`: cover paraphrases and the multi-turn THPT follow-up; the latter checks method/category, one retrieval, evidence, direct-answer status, expected formula content, source, and zero mock-LLM prompts.
- `tests/test_task_response_ui.py`: existing formula regression expects both học-bạ labels; it now passes after the latest formatter adjustment.
- Latest snapshot also includes the previously reviewed changes in `output_validator.py`, `test_task_i.py`, and related admission/advisory tests; `tests/test_data_pipeline_recovery.py` now resolves processed/raw files through the manifest.

### Final targeted test result

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_task_i.py tests/test_task_f.py tests/test_priority_1_2_fix.py `
  tests/test_admission_conditions.py tests/test_intent_classifier.py `
  tests/test_task_response_ui.py tests/test_runtime_enrollment.py `
  tests/test_data_pipeline_recovery.py
```

**5 failed, 128 passed, 170 subtests passed (36.93s).** The six-failure intermediate run occurred before the latest formula-label adjustment; on the final rerun `test_formula_does_not_turn_into_a_threshold_answer` passes. All five remaining subfailures are the Task F program-parent mappings (`parent_major=None`): `Quản trị Marketin` → `Marketing`; `Phân tích dữ liệu kinh doan` → `Thương mại điện tử`; `Ngôn ngữ - Văn hóa Nhật Bản` → `Ngôn ngữ Nhật`; `Tiếng Trung văn hóa - Du lịch` → `Ngôn ngữ Trung Quốc`; `Tâm lý tổ chức - Nhân sự` → `Tâm lý học`. Full pytest was not rerun.

### Latest traces

Positive query traces below use the current processed corpus through the test `DHVRetriever` and mock LLM; they are not live Chroma/Ollama E2E. Boundary cases use a recording retriever and never-call LLM.

| Case | Intent / method / category | Calls / docs / evidence / top-k | Direct validator; final status; LLM | QA result |
|---|---|---:|---|---|
| Turn 1: `trường có bao nhiêu phương thức xét, và hãy liệt kê chi tiết về những phương thức xét tuyển đấy` | `HOI_PHUONG_THUC_XET_TUYEN` | Initial method-list answer `ok` | — | Establishes method context. |
| Turn 2: `xét kết quả kỳ thi tốt nghiệp THPT thì xét điểm như nào` | `HOI_CACH_TINH_DIEM`; `method=thpt`; `phuong_thuc_xet_tuyen` | **1 / 16 / 16 / 16** | direct-answer `ok`; final `ok`; **0** mock LLM prompts | **PASS:** deterministic, evidence-derived answer includes the THPT total of 03 subjects and both verified alternative combinations; source is `https://tuyensinh.dhv.edu.vn/`. Conversation state retains `current_method=thpt`. |
| `Cách tính điểm xét tuyển học bạ` | `HOI_CACH_TINH_DIEM`; `method=hoc_ba`; `phuong_thuc_xet_tuyen` | **1 / 16 / 16 / 16** | direct-answer `ok`; final `ok`; **0** mock LLM prompts | **PASS:** the verified three-year rule is returned with `Cách 1` and `Cách 2`; the regression test is green. |
| `Điểm chuẩn trường đại học khác?` | `HOI_DIEM_TRUNG_TUYEN`; `OTHER_SCHOOL` | **0 / 0 / 0 / n/a** | validator not reached; `out_of_scope`; LLM not called | **PASS:** external boundary stops before retrieval. |
| `So sánh DHV và Văn Hiến` | `HOI_CO_SO_LIEN_HE`; `MIXED` | **0 / 0 / 0 / n/a** | validator not reached; `out_of_scope`; LLM not called | **PASS:** mixed boundary stops before retrieval. |
| `Tôi thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH`; `nganh_dao_tao`, `nguong_dau_vao` | **1 / 82 / 82 / default** | validator `clarification`, `personal_fit_not_in_verified_evidence`; final `clarification`; **0** mock LLM calls | **PASS:** no unsupported personal-fit claim is generated. |
| `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?` | `MULTI_ISSUE`; tuition [`hoc_phi`], scholarship [`hoc_bong`, `phuong_thuc_xet_tuyen`], programs [`nganh_dao_tao`] | **3 / 5 / 3** overall; subplan docs/evidence `0/0`, `1/1`, `4/2` | aggregate validator absent; statuses `no_data, ok, ok`; root `ok`; `partial=true`, `complete=false` | **FAIL:** scholarship evidence remains a `phuong_thuc_xet_tuyen` major/program table, not a scholarship-policy passage. Relevant verified `hoc_bong` candidates are still excluded as `entity_not_in_document`; the answer under “Học bổng” is therefore irrelevant. |

### Runtime / remaining handoff

`ollama list` was retried against the latest tree and remains **BLOCKED** by Windows socket permissions at `127.0.0.1:11434`; no live Qwen or active Chroma trace was possible. Lead should retain the new deterministic formula behavior, fix scholarship entity filtering/relevance and its under-specified regression assertion, and resolve the five parent mappings against canonical evidence. QA should then rerun targeted + full pytest and live E2E when Ollama is available. No source/tests/data/Chroma were changed by QA; no deployment was performed.

**Latest-tree handoff verdict: FAIL.**

## LATEST SNAPSHOT REVIEW — 2026-10-12 (supersedes the historical review below)

### Current verdict

**FAIL — hand back to Lead Coder.** The latest patch now includes scholarship categories for the multi-issue scholarship subplan and exposes an explicit `partial` flag. However, the exact requested multi-intent case still selects a verified *program catalogue* chunk as scholarship evidence while verified scholarship-policy chunks are filtered out as `entity_not_in_document`. The scholarship section is therefore not evidence-relevant despite `status=ok` and `evidence_count=1`. External/mixed boundaries and advisory fail-closed passed the rerun.

### Latest diff reviewed

Compared the current working-tree files with `HEAD` and reviewed the changes, including the latest Task I/F edits. Files in the current modified snapshot:

| File | Reviewed area |
|---|---|
| `src/chatbot/query_analysis.py` | Multi-issue subplan tagging; scholarship subplan category expansion to `hoc_bong` + `phuong_thuc_xet_tuyen`; admission/paraphrase routing updates. |
| `src/chatbot/rag_chain.py` | Scholarship evidence prioritization; explicit multi-issue `partial`/`complete` aggregation; admission/advisory answer guards. |
| `src/chatbot/output_validator.py` | Secondary rejection for unsupported personal-fit claims. |
| `tests/test_task_i.py` | Expects the added scholarship source category. |
| `tests/test_task_f.py` | Asserts scholarship docs/evidence are nonzero and response is partial; advisory zero-generation coverage. |
| `tests/test_data_pipeline_recovery.py` | Replaces stale tuition file paths with manifest/document-identity lookup; both affected tests pass in the latest rerun. |
| `tests/test_admission_conditions.py` | Admission-condition, threshold, Law eligibility and scholarship regressions. |
| `tests/test_full_sweep_p1.py` | Retrieval configuration regression. |
| `tests/test_intent_classifier.py` | Advisory intent/fail-closed regression. |
| `tests/test_task_response_ui.py` | No personal-fit inference from a program-parent relation. |

### Latest targeted tests

Command:

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_task_i.py tests/test_task_f.py tests/test_priority_1_2_fix.py `
  tests/test_admission_conditions.py tests/test_intent_classifier.py `
  tests/test_task_response_ui.py tests/test_runtime_enrollment.py `
  tests/test_data_pipeline_recovery.py
```

Latest result: **5 failed, 126 passed, 167 subtests passed (30.13s)**. All five failures are the existing Task F program-to-parent mappings (`parent_major=None` for five fixture names); none are in the requested scholarship, boundary, advisory, or manifest-fixture cases. The two manifest-based recovery tests passed. Full pytest was **not rerun for this handoff**; the full-suite count in the historical section below belongs to the prior snapshot and is not a latest-tree result.

The five current failing subcases are: `Quản trị Marketin` → expected parent `Marketing`; `Phân tích dữ liệu kinh doan` → `Thương mại điện tử`; `Ngôn ngữ - Văn hóa Nhật Bản` → `Ngôn ngữ Nhật`; `Tiếng Trung văn hóa - Du lịch` → `Ngôn ngữ Trung Quốc`; and `Tâm lý tổ chức - Nhân sự` → `Tâm lý học`. Actual parent is `None` in each case.

### Latest runtime traces

The positive multi-intent/advisory cases use the current processed corpus via `tests/test_task_f.py`'s corpus-backed retriever and a mock LLM. They are **not live Chroma/Ollama E2E**. Boundary cases use the recording retriever and a never-call LLM.

| Case | Intent; subplans/categories | Retrieval calls / docs / evidence | Validator; status; partial | QA result |
|---|---|---:|---|---|
| `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?` | `MULTI_ISSUE`; `HOI_HOC_PHI` [`hoc_phi`], `HOI_HOC_BONG` [`hoc_bong`, `phuong_thuc_xet_tuyen`], `DANH_SACH_CHUONG_TRINH` [`nganh_dao_tao`] | **3 / 5 / 3** overall; subplans respectively **0/0**, **1/1**, **4/2** docs/evidence | Subplan statuses `no_data, ok, ok`; root `ok`; `partial=true`, `complete=false` | **FAIL:** scholarship's one selected evidence chunk is category `phuong_thuc_xet_tuyen` but its content is the major/program table, not a scholarship policy. Verified `hoc_bong` policy candidates are rejected by the entity filter as `entity_not_in_document`. The section headed “Học bổng” consequently contains programme-catalogue text. |
| `Điểm chuẩn trường đại học khác?` | `HOI_DIEM_TRUNG_TUYEN`; `OTHER_SCHOOL`; no subplans | **0 / 0 / 0** | validator not reached; `out_of_scope`; partial n/a | **PASS:** no DHV retrieval/evidence. |
| `So sánh DHV và Văn Hiến` | `HOI_CO_SO_LIEN_HE`; `MIXED`; no subplans | **0 / 0 / 0** | validator not reached; `out_of_scope`; partial n/a | **PASS:** stopped before retrieval. |
| `Tôi thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH`; [`nganh_dao_tao`, `nguong_dau_vao`] | **1 / 82 / 82** | validator `clarification`, reason `personal_fit_not_in_verified_evidence`; status `clarification`; partial n/a; LLM calls **0** | **PASS:** no unsupported fit recommendation was generated. |

For the multi-intent trace, the aggregate validator field is absent; subplan status/evidence traces are present. The scholarship retrieval query is tied to `Công nghệ thông tin`. Its filtered-candidate audit includes verified 2026 DHV `hoc_bong` chunks describing scholarship conditions/amounts, but those are discarded because the general scholarship-policy text does not repeat the major name. The only selected hit is a verified `phuong_thuc_xet_tuyen` chunk whose preview is a major/program catalogue. The new test checks category membership and nonzero counts, but not that the selected evidence semantically answers the scholarship subquestion; it therefore passes while the runtime answer is wrong for that section.

The partial-response change does correctly set `trace.partial_response=true`, `result.partial=true`, `multi_issue.partial=true`, and `multi_issue.complete=false`; it preserves the no-data tuition section rather than silently implying all subquestions were answered. `status=ok` coexists with `partial=true`, so callers must use the partial field when describing completeness. A repository search found no separate UI consumer for that field beyond the returned result object; this review does not claim a visible UI badge.

### Ollama / live runtime

Retried `ollama list`: **BLOCKED** — connection to `127.0.0.1:11434` failed with Windows socket permission error (`connectex`). No live Qwen generation or active Chroma search was verified. Do not count fixture-backed traces as production E2E PASS.

### Handoff to Lead Coder

1. Keep the external/mixed pre-retrieval guard and advisory pre-generation fail-closed behavior; both passed this rerun.
2. Fix the multi-issue scholarship entity filtering so general, verified DHV scholarship policies remain eligible when the question also names CNTT, without accepting unrelated evidence. Avoid treating any nonzero retrieval/evidence count as sufficient proof of relevance.
3. Strengthen the regression to assert the selected scholarship evidence contains a scholarship policy/condition/list item and that the rendered “Học bổng” section is grounded in it; retain explicit per-subplan categories, counts, `status`, and partial assertions.
4. Keep `partial=true` visible in the API result and confirm separately whether the UI should surface partial completion. Do not reinterpret `status=ok` as complete.
5. Resolve the five current Task F program-parent subfailures against canonical processed evidence; do not alter expected values without source verification.
6. After the fixes, ask QA to rerun this focused suite and full pytest; rerun live Ollama + active Chroma once the socket environment permits. No deployment was performed.

**Current handoff verdict: FAIL.** The older report sections below preserve findings/results from the preceding snapshot only; where they conflict with this latest review, this latest review is authoritative.

## 1. Verdict

**FAIL — hand back to Lead Coder.**

Latest working-tree review and tests show the new advisory boundary blocks unsupported fit advice before generation in covered cases, and external-school boundary tests remain safe. However, a processed-corpus-backed runtime trace found that the newly isolated scholarship multi-issue subplan retrieves no scholarship evidence even though the same source corpus returns verified scholarship evidence when the relevant source category is included. Full pytest also has 12 failures.

Full pytest: **12 failed, 340 passed, 4 skipped, 324 subtests passed**. Targeted suite: **5 failed, 216 passed, 241 subtests passed**. Ollama/live runtime: **BLOCKED** by the Windows socket permission error at `127.0.0.1:11434`.

QA is read-only. No source, tests, dataset, processed JSON, Chroma, or deployment was changed. This report is the only QA deliverable written.

## 2. Scope and latest diff reviewed

Read `reports/TONG_QUAN_AGENT` and reviewed the latest working-tree changes against `HEAD`. The relevant modified files are:

| File | Change reviewed | QA observation |
|---|---|---|
| `src/chatbot/query_analysis.py` | Admission paraphrase/routing updates; sets `multi_issue_subplan`; scholarship categories vary by condition-question vs broad/multi-issue question | Routing tests pass, but the multi-issue scholarship category restriction loses verified evidence in the runtime trace below. |
| `src/chatbot/rag_chain.py` | Raises scholarship retrieval `top_k` to 96; direct evidence answers; personal-fit pre-generation gate; clarification fallback | The advisory gate returns before LLM generation when fit evidence is insufficient. Multi-issue root trace exposes each subplan’s status/counts. |
| `src/chatbot/output_validator.py` | Adds `unsupported_advisory_fit`; expands fallback phrases recognized by `_is_model_fallback` | Relevant focused validator/retry tests pass. |
| `tests/test_admission_conditions.py` | Tests conditions, paraphrases, threshold, scholarship conditions and deadlines | Covered tests pass in the targeted run. |
| `tests/test_intent_classifier.py` | Updates advisory case to expect clarification and zero LLM calls | This revised fail-closed test passes. |
| `tests/test_task_f.py` | Tests verified fit evidence requirements, including year/status/school and direct negation; tests zero prompts for unsupported fit | New advisory tests pass; five program-parent subcases still fail. |
| `tests/test_full_sweep_p1.py` | Expects scholarship retrieval `top_k=96` | Matches current runtime code; covered test passes. |
| `tests/test_task_response_ui.py` | Prevents inferring personal fit from a program-parent relation | Covered advisory test passes. |

No change was made to scope-guard source in this snapshot. External boundary regression tests were rerun against the unchanged guard and current caller path.

## 3. Test commands and results

### Targeted runtime/security/advisory suite

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_admission_conditions.py `
  tests/test_intent_classifier.py `
  tests/test_priority_1_2_fix.py `
  tests/test_task_f.py `
  tests/test_task_i.py `
  tests/test_runtime_enrollment.py `
  tests/test_task_response_ui.py `
  tests/test_task_c.py `
  tests/test_full_sweep_p1.py
```

Result: **5 failed, 216 passed, 241 subtests passed, 37.54s**. All five failures are the program-parent mapping subcases detailed in §6. The external-school, admission-condition/paraphrase, enrollment, current advisory-boundary, scholarship routing, validator fallback, and Task I subplan assertions in this command passed.

### Full suite

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider
```

Result: **12 failed, 340 passed, 4 skipped, 324 subtests passed, 67.39s**. The two raw/processed tuition fixture failures, five parent-mapping subcases, three catalog-count failures and two structured-JSON table failures are itemized in §6.

`python.exe` through the WindowsApps alias did not start in an initial invocation; successful test runs used the project `.venv` interpreter. No Windows temp ACL failure occurred in these successful pytest runs.

### Ollama check

```powershell
ollama list
```

Result: cannot connect to `127.0.0.1:11434`; Windows reports that socket access is forbidden. No live Ollama generation or active Chroma retrieval was run.

## 4. Per-case runtime traces

Except where noted, these are read-only, fixture-backed runs using the current processed corpus through the test `DHVRetriever`/`CorpusStore` and a mock LLM, **not production Chroma/Ollama E2E**. Values are from `ask_chatbot` trace; `validator=—` means that trace path did not emit a validator result field, not an independent validator PASS.

| Input | Intent / subplans and categories | Retrieval calls; docs; evidence | Validator / status | Result |
|---|---|---:|---|---|
| `Nhập học cần những gì?` | `HOI_NHAP_HOC`; categories `ho_so, nhap_hoc`; no subplans | 1; 12; 12 | validator field absent; `ok` | Processed-corpus-backed answer path returned enrollment evidence. This does not prove live Chroma freshness. |
| `Muốn vào DHV thì phải đáp ứng gì?` | `HOI_DANG_KY_XET_TUYEN`; category `phuong_thuc_xet_tuyen` | 1; 4; 2 | validator field absent; `ok` | Paraphrase reached verified-condition category. |
| `Kết quả ĐGNL tối thiểu để đăng ký xét tuyển là mấy?` | `HOI_NGUONG_DAU_VAO`; categories `nganh_dao_tao, nguong_dau_vao` | 1; 4; 4 | validator `ok`; `ok` | Method-specific threshold route resolved. |
| `DHV xét học bổng cần điều kiện gì?` | `HOI_HOC_BONG`; categories `hoc_bong, phuong_thuc_xet_tuyen` | 1; 58; 58 | validator field absent; `ok` | Condition-question path includes the admissions-method page category. |
| `DHV có những học bổng nào?` | `HOI_HOC_BONG`; categories `hoc_bong, phuong_thuc_xet_tuyen, ho_so` | 1; 70; 70 | validator field absent; `ok` | Broad single-issue lookup found scholarship material in the processed-corpus-backed retriever. |
| `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?` | `MULTI_ISSUE`; subplans: `HOI_HOC_PHI(hoc_phi)`, `HOI_HOC_BONG(hoc_bong)`, `DANH_SACH_CHUONG_TRINH(nganh_dao_tao)` | 3; root 4; root 2. Per subplan docs/evidence: fee `0/0`, scholarship `0/0`, programs `4/2` | per-subplan statuses `no_data, no_data, ok`; root `ok` | Answer explicitly shows no-data for tuition and scholarship and lists programs. Scholarship miss is confirmed against the same corpus; see §5. |
| `Tôi thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH`; categories `nganh_dao_tao, nguong_dau_vao` | 1; 82; 82 | validator trace: `clarification / personal_fit_not_in_verified_evidence`; final `clarification` | Covered test confirms mock LLM prompt count is zero. Gate runs after retrieval/evidence selection but before generation. |
| `Điểm chuẩn CNTT?` | `HOI_DIEM_TRUNG_TUYEN`; `UNSPECIFIED` defaults to DHV; category `diem_trung_tuyen` | 1; 3; 3 | validator `ok`; `ok` | Control case confirms the external guard does not block a genuine unspecified DHV-domain question. |
| `Điểm chuẩn trường đại học khác?` | `HOI_DIEM_TRUNG_TUYEN`; target `OTHER_SCHOOL`; planned category `diem_trung_tuyen`; no subplans | 0; 0; 0 | validator not reached; `out_of_scope` | Scope boundary stops before retrieval. |
| `So sánh DHV và Văn Hiến` | `HOI_CO_SO_LIEN_HE`; target `MIXED`; planned category `co_so_lien_he`; no subplans | 0; 0; 0 | validator not reached; `out_of_scope` | Mixed-school boundary stops before retrieval. |
| `Cổng đăng ký xét tuyển DHV ở đâu?` (synthetic verified fixture; LLM first emits a wrong date, then corrected draft) | `HOI_DANG_KY_XET_TUYEN`; categories `dang_ky_xet_tuyen, phuong_thuc_xet_tuyen` | 1; 1; 1 | validator `ok`; final `ok`; 2 mock LLM calls | Validator/retry path discarded unsupported `01/01/2099` and returned the source-supported text. No live model was involved. |

### Scholarship category comparison

For the exact scholarship subplan query generated from the multi-intent question, I compared read-only retrieval using the fixture-backed retriever:

| Retrieval category filter | Selected docs | Selected document categories |
|---|---:|---|
| `hoc_bong` | 0 | — |
| `hoc_bong, phuong_thuc_xet_tuyen` | 1 | `phuong_thuc_xet_tuyen` |
| `hoc_bong, phuong_thuc_xet_tuyen, ho_so` | 1 | `phuong_thuc_xet_tuyen` |

The exact subquery is `Công nghệ thông tin học bổng 2026 intent:HOI_HOC_BONG year:2026 major_name:Công nghệ thông tin candidate_majors:Công nghệ thông tin`. With `hoc_bong` only, retrieval audit had zero hits and selected docs. Adding `phuong_thuc_xet_tuyen` returned one selected document. Meanwhile a broad single-issue scholarship request retrieved 70 docs/evidence in the same test corpus. This is evidence of a category-boundary/retrieval mismatch, not just a test expectation issue. The multi-intent response does expose a no-data section instead of fabricating scholarship facts, but it fails to use available verified corpus content.

## 5. Current findings by implementation area

### Verified admission conditions and paraphrase/routing — PASS in targeted coverage, live E2E blocked

- Natural “muốn vào DHV thì phải đáp ứng gì” routes to `HOI_DANG_KY_XET_TUYEN` and `phuong_thuc_xet_tuyen`.
- “Kết quả ĐGNL tối thiểu ... là mấy” routes to `HOI_NGUONG_DAU_VAO`, retains `admission_method=dgnl`, and reaches `nganh_dao_tao, nguong_dau_vao`.
- Test cases for scholarship conditions, 3-subject admission, Law conditions and supplementary deadline ran in the targeted suite; no failures among them.
- Traces above are not live Chroma/Ollama proof.

### Personal-fit advisory — PASS for covered fail-closed cases; residual semantic coverage needed

- `_has_verified_advisory_fit_evidence` requires a named candidate and interest tied by a fit phrase in the same current-year, verified DHV chunk.
- It rejects wrong school/year/unverified evidence and a directly negated fit sentence in new regression coverage; those tests passed.
- `ask_chatbot` sets `advisory_boundary=personal_fit_not_in_verified_evidence`, returns `clarification`, and exits before LLM generation when evidence does not establish fit. The new tests assert zero prompts.
- `output_validator` provides a second defense after generation. `_is_model_fallback` also recognizes additional Vietnamese fallback phrasings; the focused retry/validator tests passed.
- Residual risk: lexical matching is narrow. Negation variants beyond the tested direct “không phù hợp”, paraphrased interests, conflicting evidence, and multi-turn aliases should be added to QA coverage. Live generation remains untested.

### Scholarship multi-intent — FAIL: routing isolation currently hides evidence

The revised routing test in `tests/test_task_i.py` passes and shows each subplan has separate categories. However, the scholarship subplan is limited to `hoc_bong`; the actual verified scholarship evidence selected by the same corpus fixture for that subquery is in `phuong_thuc_xet_tuyen`. Result: scholarship subplan returns `no_data` with 0 documents/evidence while the single-issue scholarship path returns an answer with 70 documents/evidence. Lead should preserve subplan isolation while routing to the verified source category and add a runtime assertion for per-subplan evidence/status. Do not broaden categories indiscriminately: unrelated evidence still must be excluded.

### External-school boundary — PASS in targeted tests

Generic/named external-school matrices, Bách Khoa with/without accents, mixed DHV/external comparisons, external-school follow-up overrides, and explicit DHV overrides passed. Representative traces confirm `OTHER_SCHOOL` and `MIXED` return before retrieval: **calls=0, docs=0, evidence=0**. `Điểm chuẩn CNTT?` remains `UNSPECIFIED` with the DHV retrieval path enabled.

## 6. Full pytest failures — all groups

### A. Tuition 2024 fixture filename drift — 2 failures

**Classification:** stale fixture/data contract. **Severity:** Medium.

| Test | Expected | Actual / evidence |
|---|---|---|
| `DataPipelineRecoveryTests.test_manifest_provenance_survives_pdf_without_url` | Fixture opens `data/raw/hoc_phi/Hoc_Phi_DHV_2024.pdf` | `FileNotFoundError`; current manifest points to `data/raw/hoc_phi/V1_HOC_PHI_DHV_2024.pdf`. |
| `DataPipelineRecoveryTests.test_processed_corpus_keeps_2024_and_loader_source_is_not_verified` | Fixture opens `data/processed/hoc_phi/Hoc_Phi_DHV_2024.json` | `FileNotFoundError`; current processed file is `V1_HOC_PHI_DHV_2024.json`. |

Handoff: update fixtures by canonical manifest/document identity after checking the current files; do not add duplicate files.

### B. Program-parent name resolution — 5 subfailures

**Classification:** unresolved catalog/alias contract mismatch. **Severity:** Medium.

`TaskFAnalysisTests.test_declared_programs_resolve_and_keep_evidence_parent` receives `parent_major=None` for all five expected mappings:

| Program string in test | Expected parent | Actual |
|---|---|---|
| `Quản trị Marketin` | `Marketing` | `None` |
| `Phân tích dữ liệu kinh doanh` | `Thương mại điện tử` | `None` |
| `Ngôn ngữ - Văn hóa Nhật Bản` | `Ngôn ngữ Nhật` | `None` |
| `Tiếng Trung văn hóa - Du lịch` | `Ngôn ngữ Trung Quốc` | `None` |
| `Tâm lý tổ chức - Nhân sự` | `Tâm lý học` | `None` |

The first two strings are truncated in the fixture/catalog constant itself. Confirm canonical program names and parent relations against processed JSON/PDF before changing aliases or expectations.

### C. Program catalog count disagreement — 3 failures

**Classification:** data/test contract drift; source-of-truth confirmation required. **Severity:** Medium.

- `TaskGCatalogTests.test_all_program_catalog_keeps_parent_relations`: expected 47, actual 50.
- `TaskGCatalogTests.test_global_program_catalog_does_not_inherit_current_major`: expected 47, actual 50.
- `TaskGCatalogTests.test_verified_corpus_has_complete_unique_program_parent_audit`: expected 47 unique pairs, actual 50.

Do not simply change 47 to 50 without verifying every name, parent and duplication status against the canonical source.

### D. Structured JSON table representation — 2 failures

**Classification:** extraction/data-shape failure outside this runtime diff. **Severity:** Medium–High.

| Test | Expected | Actual / risk |
|---|---|---|
| `StructuredJSONPipelineTests.test_content_audit_counts_page_structures_and_keeps_import_data` | Header cells `Học bổng đầu vào`, `Giảm tiếp HKII` | Extracted header text retains line breaks (`đầu\\nvào`, `tiếp\\nHKII`). Cell wrapping normalization is incomplete. |
| `StructuredJSONPipelineTests.test_score_types_are_separate_and_numeric_values_are_preserved` | Continued table includes `header_inherited` | `KeyError: 'header_inherited'`; continued-page header/cell relationship is not represented as the test contract expects. |

No environment-only pytest failure was observed. Task I scholarship subplan unit test passed, but the separate runtime trace still demonstrates missing evidence due to its category filter.

## 7. Environment and live runtime

`ollama list` failed with a Windows socket permission error when connecting to `127.0.0.1:11434`. Consequently:

- no live Qwen generation was exercised;
- no active Chroma similarity search was exercised;
- fixture-backed processed-corpus traces and mocked LLM retry tests must not be described as production E2E PASS.

**Environment status: BLOCKED.** Do not count as product PASS or product FAIL.

## 8. Handoff to Lead Coder

1. Fix scholarship multi-issue retrieval so its isolated subplan reaches the verified source category (`phuong_thuc_xet_tuyen` in the trace) without mixing evidence into fee/program subplans. Add an end-to-end subplan regression asserting category, retrieved docs, evidence count, answer section and subplan status.
2. Investigate why root multi-issue `status=ok` while two subplans are `no_data`; ensure the response contract exposes partial failures consistently. The current text does show no-data sections, but the root status is not a complete-answer signal.
3. Keep the new advisory zero-generation behavior; extend tests for more negation/paraphrase/state variants and for preservation of independently answerable score/catalog facts.
4. Confirm the 47-vs-50 catalog and five parent mappings against canonical processed JSON/PDF; repair aliases/fixtures only after source verification.
5. Update 2024 tuition fixtures to current manifest filenames.
6. Resolve the two structured JSON table failures without flattening numeric values or losing header provenance.
7. When the environment is available, have QA rerun the focused tests and full suite, then run a live Ollama + active Chroma trace. Do not deploy before QA re-review.

## 9. Final QA status

**FAIL / handoff to Lead Coder.** Focused and full-suite results are documented above; external-school zero-retrieval invariant passed; personal-fit gate passed covered tests; scholarship multi-intent evidence path failed in fixture-backed runtime trace; Ollama is blocked. No overall PASS is declared.
