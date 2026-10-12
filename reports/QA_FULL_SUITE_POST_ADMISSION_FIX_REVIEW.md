# QA & Security Review — Latest Shared Workspace Snapshot

## 1. Verdict

**FAIL — chưa đủ cơ sở xác nhận QA PASS.**

Full pytest trên snapshot được review ngày 2026-10-12: **24 failed, 328 passed, 4 skipped, 323 subtests passed**. Focused security/advisory suite: **16 failed, 116 passed, 168 subtests passed**. Ollama không truy cập được tại `127.0.0.1:11434`, nên live Ollama/Chroma runtime **BLOCKED**.

Các lượt trước ghi 15 lỗi hoặc ít hơn đã lỗi thời so với snapshot này. Không dùng các số đó làm kết quả hiện tại.

QA chỉ đọc code/test và chạy kiểm thử. Không sửa source, tests, data, Chroma hoặc deploy. Report này là artefact QA được cập nhật theo yêu cầu.

## 2. Scope và latest tree đã review

Đã đọc toàn bộ `reports/TONG_QUAN_AGENT`, xác nhận nhiệm vụ QA & Security và giới hạn read-only. Đã đọc working-tree status, so sánh các file thay đổi với `HEAD` (Git `diff` trực tiếp báo không ở work tree; so sánh read-only bằng nội dung `HEAD:<path>` và file hiện tại), và kiểm tra riêng thay đổi chặn advisory trước generation.

Working tree cho thấy tám file source/test đã sửa:

| File | Khu vực thay đổi đã review | Nhận xét QA |
|---|---|---|
| `src/chatbot/output_validator.py` | Gọi thêm `_advisory_fit_failure`; phát hiện câu khẳng định chương trình phù hợp với sở thích và trả `unsupported_advisory_fit` | Là defense thứ hai sau generation; điều kiện dựa trên intent/sở thích được parse và pattern từ vựng. |
| `src/chatbot/query_analysis.py` | Paraphrase câu hỏi tổ hợp 3 môn/ngưỡng theo phương thức/đợt bổ sung; ưu tiên intent tư vấn; điều kiện Luật | Có các thay đổi routing admission ngoài phạm vi security advisory mới; full-suite failures vẫn phải được xử lý. |
| `src/chatbot/rag_chain.py` | Mở rộng evidence lookup; helper trả lời dựa evidence; `_has_verified_advisory_fit_evidence`; dừng và trả clarification trước LLM nếu không có evidence fit đã xác minh | Gate chạy sau retrieval/evidence usability nhưng **trước generation**. Cách chặn có hiệu lực trên đường code đọc được; phạm vi intent rộng có thể làm mất luồng trả lời factual nằm trong cùng câu tư vấn. |
| `tests/test_admission_conditions.py` | Thêm test cho câu hỏi tuyển sinh paraphrase, Luật, ngưỡng, ngày bổ sung và validator advisory | Test validator chống fit claim mới được chạy trong focused suite. |
| `tests/test_full_sweep_p1.py` | Đổi expected scholarship retrieval `top_k` từ 64 lên 96 | Test-only budget thay đổi; không thấy thay đổi tương ứng con số này trong diff hiện tại. Lead cần nêu contract/lý do. |
| `tests/test_intent_classifier.py` | Cập nhật test advisory để mong clarification, không khẳng định chương trình phù hợp | Một assertion cũ vẫn mong LLM được gọi, mâu thuẫn với yêu cầu gate trước generation. |
| `tests/test_task_f.py` | Chuyển một số expected advisory sang clarification/không tư vấn chọn; vẫn còn nhiều test kỳ vọng generation/status cũ | Các failure nêu ở mục 4 cho thấy bộ contract advisory chưa được đồng bộ nhất quán. |
| `tests/test_task_response_ui.py` | Cập nhật test recommendation để cấm suy ra personal fit từ quan hệ chương trình–ngành | Test mới không nằm trong failure list; test scholarship độc lập vẫn fail về format. |

Không thấy thay đổi dataset 500 câu trong status đã đọc. Working tree báo `reports/` là thư mục untracked; QA chỉ cập nhật report được yêu cầu, không sửa/xóa report hay artefact khác.

## 3. Kiểm thử mới nhất

### Focused security/advisory

Lệnh đã chạy trong PowerShell, với temporary directory trong workspace:

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider `
  tests/test_admission_conditions.py `
  tests/test_intent_classifier.py `
  tests/test_priority_1_2_fix.py `
  tests/test_task_f.py `
  tests/test_task_k.py `
  tests/test_task_l.py `
  tests/test_task_n.py `
  tests/test_task_response_ui.py
```

Kết quả: **16 failed, 116 passed, 168 subtests passed, 30.14s**.

### Full pytest

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest --tb=short -q -p no:cacheprovider
```

Kết quả: **24 failed, 328 passed, 4 skipped, 323 subtests passed, 42.74s**.

Focused suite chồng lấp 16 lỗi advisory/catalog/UI với full suite; full suite có thêm 8 lỗi ở data-pipeline fixtures, catalog count, multi-issue routing và structured JSON. Không có pytest environment/ACL error ở lượt này.

Lệnh gọi `python.exe` qua WindowsApps shim ban đầu không khởi chạy được; các kết quả bên trên được chạy thành công bằng interpreter trong `.venv`. Lỗi khởi chạy shim không được tính là pytest failure.

## 4. Tất cả lỗi full-suite — nhóm, bằng chứng, phân loại

### 4.1. Advisory pre-generation gate và test contract chưa đồng bộ — 9 failures

**Phân loại:** trực tiếp liên quan thay đổi mới; gồm test expectation cũ và khả năng over-block cần Lead quyết định. **Severity:** Medium; tính an toàn có vẻ fail-closed, nhưng behavior/contract chưa được xác nhận đồng nhất.

Code hiện tại gọi `_has_verified_advisory_fit_evidence(...)` cho intent `TU_VAN_CHON_NGANH`. Helper yêu cầu sở thích và candidate có quan hệ fit trong cùng chunk DHV, verified, đúng năm; khi không đạt, nhánh trả `clarification` và return trước khu vực generation. Đây là defense chính mới; validator chỉ là lớp sau generation.

Focused/full tests cung cấp bằng chứng đường chạy không gọi LLM: trong `test_major_passion_dilemma_is_dynamic_admissions_advice`, mock LLM có `called == False`, trong khi assertion còn mong `True`. Kết quả thực tế là nhánh clarification trước LLM. Failure đó phù hợp với mục tiêu an toàn mới, nhưng test chưa được cập nhật để xác nhận contract mới.

Các failure advisory còn lại:

| Test | Expected | Actual | Đánh giá/root cause |
|---|---|---|---|
| `test_advisory_rejects_named_major_and_organization_outside_evidence` | `no_data` | `clarification` | Pre-generation gate kết thúc trước draft độc hại; status contract của test cũ không đồng bộ. Nên assertion trực tiếp là không generation/không claim ngoài evidence. |
| `test_advisory_retries_and_rejects_wrong_program_parent` | `ok`, thử lại draft sai parent | `clarification` | Fixture chỉ chứng minh quan hệ catalog, không chứng minh personal fit; gate bỏ qua retry path cũ. Test hiện không còn kiểm đúng invariant mới. |
| `test_generation_is_separate_and_echo_is_grounded` (`regression_major_program_confusion`) | `ok` | `clarification` | Assertion phân nhánh của test chỉ nhìn `analysis.entities.interest`; gate cũng xét context state và yêu cầu fit evidence. Đây là mismatch giữa test với gate mới; cần xác minh state/evidence cụ thể của case trước khi đổi expected. |
| `test_personal_admission_guarantee_is_rejected` | `no_data` | `clarification` | Gate dừng trước generation, trả trạng thái clarification thay vì validator no-data. Cần thống nhất expected status và xác minh không có guarantee trong answer. |
| `test_advisory_fallback_keeps_verified_context_when_candidate_filter_is_empty` | 2 LLM prompts | 0 prompts | Gate chạy trước generation; test đang yêu cầu gọi lại LLM trong trường hợp không có fit evidence. Cần viết lại để xác nhận evidence-only context vẫn được giữ trong clarification. |
| `test_advisory_keeps_two_non_program_candidates_without_parent_claim` | `ok` | `clarification` | Candidate list không tự chứng minh mức phù hợp; status cũ cần đối chiếu policy. Kiểm tra riêng phần dữ kiện/candidate có bị mất không. |
| `test_ollama_like_quoted_relation_and_grounded_major_list` | lượt đầu `ok` | `clarification` | Gate áp dụng cho cả intent tư vấn khi không có fit evidence; cần quyết định có được trả phần danh sách/quan hệ factual như một phần an toàn hay phải clarification toàn lượt. |
| `test_two_turn_multiple_choices_then_scores_keeps_candidates_and_grounding` | lượt đầu `ok` | `clarification` | Luồng nhiều lượt tư vấn hiện bị dừng trước generation; xem xét giữ phần score/catalog có evidence mà không suy luận personal fit. |
| `test_major_passion_dilemma_is_dynamic_admissions_advice` | `llm.called == True` | `False` | Test kỳ vọng cũ trái với yêu cầu mới chặn unsupported personal-fit trước generation; nên đổi test thành assertion không gọi LLM và answer không chọn thay người học. |

Ngoài các test này, `test_two_turn_screenshot_lists_verified_majors_and_corrects_count_followup` cũng fail nhưng thuộc nhóm test contract stale riêng: test vừa đổi expected sang `clarification`, actual là `ok` cho câu hỏi factual đính chính số lượng và liệt kê ngành đã xác minh. Không thấy đây là lỗi của pre-generation gate vì intent ở lượt hai là list, không phải `TU_VAN_CHON_NGANH`.

**Security conclusion có giới hạn:** code path chứng minh gate chạy trước generation đối với intent tư vấn và evidence không đủ. Tuy nhiên chưa có live Ollama test; test suite còn mâu thuẫn nên chưa thể kết luận E2E. Helper có rủi ro từ vựng: fit marker không phân tích polarity/ngữ nghĩa đầy đủ (ví dụ câu nguồn phủ định “không phù hợp” vẫn chứa marker); cần test negative/contradictory source trước khi cho generation dựa trên fit evidence.

### 4.2. Fixture học phí 2024 còn dùng filename cũ — 2 failures

**Phân loại:** stale fixture/data contract. **Severity:** Medium.

| Test | Expected | Actual | Bằng chứng |
|---|---|---|---|
| `test_manifest_provenance_survives_pdf_without_url` | mở `data/raw/hoc_phi/Hoc_Phi_DHV_2024.pdf` | `FileNotFoundError` ở `_file_sha256` | Manifest hiện trỏ `data/raw/hoc_phi/V1_HOC_PHI_DHV_2024.pdf`; test còn tham chiếu tên cũ. |
| `test_processed_corpus_keeps_2024_and_loader_source_is_not_verified` | mở `data/processed/hoc_phi/Hoc_Phi_DHV_2024.json` | `FileNotFoundError` | Processed file hiện là `V1_HOC_PHI_DHV_2024.json`; cùng drift filename. Không chứng minh nội dung học phí 2024 sai/thiếu. |

Handoff: dùng manifest/document identity hiện hành, không tạo file PDF/JSON trùng để đáp ứng fixture.

### 4.3. Program-parent/catalog tests kỳ vọng tên hoặc số lượng cũ — 8 failures

**Phân loại:** stale fixture/data contract cần đối chiếu nguồn canonical. **Severity:** Medium.

- 5 subtests của `TaskFAnalysisTests.test_declared_programs_resolve_and_keep_evidence_parent`: parent thực tế `None`, trong khi test kỳ vọng lần lượt `Marketing`, `Thương mại điện tử`, `Ngôn ngữ Nhật`, `Ngôn ngữ Trung Quốc`, `Tâm lý học` cho các tên đầu vào `Quản trị Marketin`, `Phân tích dữ liệu kinh doanh`, `Ngôn ngữ - Văn hóa Nhật Bản`, `Tiếng Trung văn hóa - Du lịch`, `Tâm lý tổ chức - Nhân sự`.
- `TaskGCatalogTests.test_all_program_catalog_keeps_parent_relations`: expected 47, actual 50.
- `TaskGCatalogTests.test_global_program_catalog_does_not_inherit_current_major`: expected 47, actual 50.
- `TaskGCatalogTests.test_verified_corpus_has_complete_unique_program_parent_audit`: expected 47 cặp, actual 50.

Các test/PDF audit khác trong workspace đang dùng catalog 50; tuy nhiên QA không xác nhận chỉ bằng số lượng rằng cả 50 mục đều đúng. Lead cần so sánh tên và parent với processed JSON/PDF canonical trước khi đổi fixture.

### 4.4. Multi-issue scholarship subplan mở rộng category — 1 failure

**Test:** `TaskISystemRouterTests.test_multi_issue_is_decomposed_into_independent_subplans`  
**Phân loại:** routing/evidence contract hiện hành, root cause cần xác minh. **Severity:** Medium.

- Input: `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?`
- Expected categories: `('hoc_phi',)`, `('hoc_bong',)`, `('nganh_dao_tao',)`.
- Actual: subplan học bổng có `('hoc_bong', 'phuong_thuc_xet_tuyen', 'ho_so')`.

Có nguy cơ kéo nội dung hồ sơ/phương thức vào ý học bổng; cần xác minh category canonical và evidence từng subplan. Không nới expected chỉ để pass.

### 4.5. Structured JSON table integrity — 2 failures

**Phân loại:** lỗi structured extraction/data contract ngoài diff runtime. **Severity:** Medium–High.

| Test | Expected | Actual | Rủi ro |
|---|---|---|---|
| `test_content_audit_counts_page_structures_and_keeps_import_data` | header `Học bổng đầu vào`, `Giảm tiếp HKII` | text JSON chứa line break trong cell: `Học bổng đầu\\nvào`, `Giảm tiếp\\nHKII` | Chuẩn hóa line wrapping của table cell/header chưa đúng. |
| `test_score_types_are_separate_and_numeric_values_are_preserved` | bảng tiếp trang có `header_inherited` | `KeyError: 'header_inherited'` | Quan hệ header–cell của bảng tiếp trang chưa được xác nhận/ghi metadata như contract test yêu cầu. |

Không thuộc diff runtime advisory, nhưng có thể ảnh hưởng độ chính xác dữ liệu mà chatbot tra cứu. Giữ nguyên numeric/provenance khi Lead điều tra.

### 4.6. Scholarship answer format assertion — 1 failure

**Test:** `TaskResponseRegressionTests.test_verified_scholarship_policy_is_structured_without_generation`  
**Phân loại:** output/test contract chưa rõ. **Severity:** Low–Medium.

- Expected: answer có ít nhất 3 chuỗi literal `- `.
- Actual: `str(result["answer"]).count("- ") == 0`.
- Chưa xác minh actual answer có bullet Unicode/format khác hay không; assertion dừng ngay ở literal dash. Cần xem exact output và xác định contract cấu trúc trước khi đổi test.

### 4.7. Factual list follow-up expected status không đúng — 1 failure

**Test:** `TaskFConversationTests.test_two_turn_screenshot_lists_verified_majors_and_corrects_count_followup`  
**Phân loại:** test contract stale/over-broad. **Severity:** Low.

- Expected: `clarification`.
- Actual: `ok`.
- Lượt hai yêu cầu đính chính tổng số và liệt kê ngành từ verified evidence; không yêu cầu chọn ngành phù hợp. Cần kiểm answer/source assertion rồi mới thống nhất status, không ép clarification cho câu factual.

## 5. Đối chiếu focused và full suite

Focused run có 16 failures. Cả 16 xuất hiện trong full run: 9 advisory/test-contract mismatches, 5 subtests program-parent, 1 list-follow-up expectation và 1 scholarship format. Full run có thêm 8 failures: 2 stale tuition filenames, 3 catalog-count expectations, 1 subplan category expansion và 2 structured JSON table failures.

Full run là kết quả tổng hợp mới nhất. Không coi các lượt trước hoặc kết quả tập trung nhỏ hơn là thay thế full suite.

## 6. Review security cho personal-fit advice

### Kết quả code review

- **PASS ở static control-flow:** intent `TU_VAN_CHON_NGANH` không có evidence fit thì `_has_verified_advisory_fit_evidence` trả false; `ask_chatbot` tạo grounded clarification và return trước generation. Mock assertion `llm.called == False` xác nhận một case cụ thể.
- **PASS về nguyên tắc defense-in-depth:** `_advisory_fit_failure` nằm trong validator sau generation; primary boundary ở upstream, không chỉ dựa validator.
- **Chưa xác nhận E2E:** Ollama không chạy được; không có live prompt/generation/retrieval trace.
- **Risk — gate rộng hơn claim cần chặn:** gate áp dụng cho toàn intent tư vấn, không chỉ draft có personal-fit claim. Các test hiện cho thấy status/LLM-generation path cũ bị đổi; cần chốt policy để vừa không chọn thay người học, vừa không làm rơi score/catalog facts đã có verified evidence.
- **Risk — fit evidence lexical:** helper yêu cầu candidate, interest và cụm fit trong một verified chunk nhưng không kiểm polarity/mâu thuẫn. Cần test nguồn phủ định, nguồn nói “không có căn cứ”, và paraphrase interest/candidate trước khi coi evidence là đủ cho tư vấn cá nhân.
- **Coverage gap:** cần test interest chỉ có trong conversation state, named candidate chỉ trong state, nhiều lượt explicit override, paraphrase không dấu/đồng nghĩa, và chứng minh `llm_calls=0` cho từng case unsupported.

Không có bằng chứng trong lượt QA này rằng một unsupported personal-fit claim đã lọt qua gate mới. Cũng chưa đủ bằng chứng để tuyên bố toàn bộ advisory behavior đúng.

## 7. Ollama và live runtime

Đã thử:

```powershell
ollama list
```

Kết quả: lỗi kết nối `127.0.0.1:11434` — Windows báo socket bị cấm bởi quyền truy cập (`connectex`). Vì Ollama unavailable, không chạy live Chroma similarity retrieval/Qwen generation hoặc runtime smoke.

**Ollama/live E2E: BLOCKED — environment failure, không tính PASS hay product failure.**

## 8. Trạng thái theo nhóm

| Nhóm | Kết quả |
|---|---|
| Diff/latest tree review | Hoàn tất, read-only; 8 file source/test được sửa và report QA được cập nhật |
| Advisory unsupported-fit pre-generation control | Control-flow có guard trước LLM; một mock chứng minh `llm.called=False`; chưa có live E2E |
| Focused security/advisory | FAIL: 16 failed, 116 passed, 168 subtests |
| Full pytest | FAIL: 24 failed, 328 passed, 4 skipped, 323 subtests |
| Failure classification | 9 advisory-contract, 2 stale filename, 8 catalog/name, 1 multi-issue, 2 structured table, 1 scholarship format, 1 factual follow-up contract |
| Ollama runtime | BLOCKED bởi socket permission Windows |
| Overall QA | **FAIL — không tuyên bố PASS** |

## 9. Handoff cho Lead Coder

1. Đồng bộ các advisory tests với contract mới: unsupported personal-fit phải trả lời không chọn thay user và phải chứng minh không gọi LLM. Không chỉ thay status expected; giữ test kiểm candidate/evidence, state, source và score facts.
2. Xác định policy cho câu tư vấn nhiều phần: nếu personal-fit chưa được chứng minh, có được trả các dữ kiện score/catalog verified rồi clarification cho phần fit không? Hiện gate dừng toàn bộ generation path.
3. Bổ sung negative/contradictory fit-source tests; không cho cụm từ “phù hợp” trong câu phủ định mở cổng generation.
4. Cập nhật parent/catalog fixture chỉ sau đối chiếu canonical JSON/PDF; giải thích 47 vs 50.
5. Sửa fixture học phí 2024 dựa manifest/document identity hiện hành.
6. Điều tra độc lập category expansion của subplan học bổng và giữ intent isolation.
7. Sửa/điều tra 2 lỗi bảng structured JSON, nhất là header inheritance và giữ liên hệ header-cell.
8. Xác minh exact deterministic scholarship answer trước khi chốt bullet-format contract.
9. Chốt test factual count/list follow-up: không buộc `clarification` nếu câu hỏi đã được evidence giải quyết.
10. Giải trình test-only `top_k: 64 → 96` trong `tests/test_full_sweep_p1.py`.
11. Sau khi Lead xử lý, QA cần chạy lại focused suite và full pytest trên snapshot ổn định; khi Ollama hoạt động, chạy live runtime trace. **Không deploy trước khi QA review lại.**
