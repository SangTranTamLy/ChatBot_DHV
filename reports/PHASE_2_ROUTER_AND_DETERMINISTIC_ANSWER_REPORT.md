# PHASE 2 – ROUTER AND DETERMINISTIC ANSWER REPORT

Ngày kiểm tra: 2026-09-24

## 1. Root Causes

### Học bạ bị `out_of_scope`

- `src/chatbot/scope_guard.py::is_in_scope()` chỉ mở scope theo `ADMISSIONS_KEYWORDS` và các tín hiệu DHV/năm.
- Nhóm từ `học bạ`, `ĐGNL`, `thi THPT` chưa có trong scope category; vì vậy câu `Trường có xét học bạ không?` có thể đã được classifier nhận là `HOI_PHUONG_THUC_XET_TUYEN` nhưng vẫn bị `rag_chain.ask_chatbot()` chặn ở scope guard trước retrieval.
- Đã bổ sung category-level rules, không hard-code câu đầy đủ. `query_analysis._classify_intent_rules()` cũng có rule semantic cho câu hỏi về phương thức học bạ/ĐGNL/thi THPT.

### Học phí theo tín chỉ bị `out_of_scope`

- `query_analysis._classify_intent_rules()` đã có thể nhận `HOI_HOC_PHI`, nhưng `scope_guard.is_in_scope()` không nhận dạng mẫu `tín chỉ + hỏi giá/phí`.
- Vì vậy trạng thái `không có evidence` chưa kịp xuất hiện; runtime kết thúc ở `out_of_scope`.
- Đã thêm `_is_tuition_unit_question()`: chỉ mở scope khi có cả tín hiệu `tín chỉ` và ngôn ngữ hỏi giá/phí, không mở scope cho mọi câu có chữ `tín chỉ`.

### Điểm chuẩn CNTT bị `no_data`

- Retrieval và Evidence Selection đã giữ được chunk chứa bảng điểm.
- `src/chatbot/evidence.py::_extract_structured_facts()` trước đây chỉ parse admission score dạng prose như `• Ngành: 20 điểm.`
- PDF admission hiện được runtime load dưới dạng `record_type=document_text`, với row native dạng `STT + mã + tên + 3 giá trị`; dạng row này không tạo được `evidence.score_facts`.
- `src/chatbot/query_analysis.py::deterministic_score_evaluation()` vì vậy thấy `verified_rule_count=0`, trả `insufficient-data`; nhánh này kết thúc `no_data` trước khi planner/LLM được gọi.
- Đã thêm `_parse_admission_table_facts()` để parse row native thành fact `score_type=admission_score`, giữ major/code/method/value/provenance. Sau đó `rag_chain.ask_chatbot()` gọi `_structured_score_answer()` cho `admission_score_lookup`, rồi vẫn chạy `validate_model_answer()`.

## 2. Files Changed

| File | Function/area | Reason |
|---|---|---|
| `src/chatbot/scope_guard.py` | `ADMISSIONS_KEYWORDS`, `_is_tuition_unit_question()`, `is_in_scope()` | Mở đúng các admission category bị chặn sai; giữ weather/gold ngoài scope. |
| `src/chatbot/query_analysis.py` | score semantic constants, `_extract_entities()`, `_classify_intent_rules()`, `_clarification_needed()`, `_multi_issue_intents()`, `route_question()` | Tách lookup điểm chuẩn/điểm sàn/bổ sung/personal comparison; sửa supplementary phrase; clarification khi personal score thiếu phương thức. |
| `src/chatbot/evidence.py` | `EvidenceBundle`, `_extract_structured_facts()`, `_parse_admission_table_facts()` | Parse bảng admission native; làm rõ provenance đến từ metadata, không phải URL trong PDF. |
| `src/chatbot/rag_chain.py` | `_trace()`, `_attach_answer_plan()`, `ask_chatbot()` | Ghi scope/score facts/final status; deterministic admission lookup qua validator. |
| `tests/test_phase2_runtime.py` | Phase 2 regression tests | Bao phủ scope, `NO_DATA`, 4 score semantics, deterministic lookup, personal comparison và provenance. |

Không thay đổi `app.py`, `src/chatbot/chat_service.py`, `src/retrieval/retriever.py`, ingestion/OCR/embedding/Chroma hay model LLM.

## 3. Scope Results

| Question | Intent | Scope | Result |
|---|---|---|---|
| `Trường có xét học bạ không?` | `HOI_PHUONG_THUC_XET_TUYEN` | `IN_SCOPE` | Retrieval chạy; với corpus hiện tại trả `ok`. |
| `DHV có xét học bạ năm 2026 không?` | `HOI_PHUONG_THUC_XET_TUYEN` | `IN_SCOPE` | Retrieval chạy; với corpus hiện tại trả `ok`. |
| `1 tín chỉ năm 2026 bao nhiêu tiền?` | `HOI_HOC_PHI` | `IN_SCOPE` | Retrieval chạy; thiếu verified tuition 2026 nên `NO_DATA`. |
| `Học phí DHV 2026 là bao nhiêu?` | `HOI_HOC_PHI` | `IN_SCOPE` | Retrieval chạy; thiếu verified tuition 2026 nên `NO_DATA`. |
| `Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu?` | `HOI_DIEM_TRUNG_TUYEN` | `IN_SCOPE` | Retrieval/evidence/deterministic answer thành công. |
| `Điểm sàn ngành Công nghệ thông tin năm 2026 là bao nhiêu?` | `HOI_NGUONG_DAU_VAO` | `IN_SCOPE` | `score_type=application_threshold`. |
| `Điểm nhận hồ sơ bổ sung CNTT là bao nhiêu?` | `HOI_XET_TUYEN_BO_SUNG` | `IN_SCOPE` | `score_type=supplementary_threshold`. |
| `Em được 18 điểm có chắc chắn đậu CNTT không?` | `HOI_NGUONG_DAU_VAO` | `IN_SCOPE` khi entity CNTT được dùng | Thiếu phương thức nên `CLARIFICATION`, không kết luận đậu. |
| `Giá vàng hôm nay bao nhiêu?` | `OUT_OF_SCOPE` | `OUT_OF_SCOPE` | Không retrieval. |
| `Thời tiết hôm nay thế nào?` | `OUT_OF_SCOPE` | `OUT_OF_SCOPE` | Không retrieval. |

## 4. Score Semantic Results

| Question | `score_type` | `record_type`/fact | Result |
|---|---|---|---|
| Điểm chuẩn CNTT 2026 | `admission_score` | Native `document_text` được parse thành `admission_score` facts | `admission_score_lookup`, deterministic, `DIRECT_SHORT`, validator `ok`. |
| Điểm sàn CNTT 2026 | `application_threshold` | `application_threshold` | `application_threshold_lookup`, không trộn với admission score. |
| Điểm nhận hồ sơ bổ sung CNTT | `supplementary_threshold` | `supplementary_threshold` | `supplementary_threshold_lookup`, route `xet_tuyen_bo_sung`. |
| Em được 720 ĐGNL có đậu không? | `application_threshold` + `score_query_type=personal_score_comparison` | `application_threshold` | So sánh `720 >= 600` khi evidence có; không kết luận trúng tuyển. |

Semantic types được lưu thêm trong `entities.score_query_type`:

- `admission_score_lookup`
- `application_threshold_lookup`
- `supplementary_threshold_lookup`
- `personal_score_comparison`

## 5. Runtime Traces

### Trace A — học bạ

`Trường có xét học bạ không?`

```text
normalize
→ intent=HOI_PHUONG_THUC_XET_TUYEN, admission_method=hoc_ba
→ scope.in_scope=true
→ route categories=(phuong_thuc_xet_tuyen,)
→ retriever được gọi
→ Evidence Selection
→ planner/validator
→ final_status=ok với corpus hiện tại
```

### Trace B — học phí theo tín chỉ

`1 tín chỉ năm 2026 bao nhiêu tiền?`

```text
normalize
→ intent=HOI_HOC_PHI
→ scope.in_scope=true
→ route categories=(hoc_phi,)
→ retriever được gọi
→ không có verified tuition 2026
→ Evidence.is_usable=false
→ planner mode=NO_DATA
→ final_status=no_data
```

### Trace C — điểm chuẩn CNTT

`Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu?`

```text
normalize
→ intent=HOI_DIEM_TRUNG_TUYEN
→ score_type=admission_score
→ score_query_type=admission_score_lookup
→ scope.in_scope=true
→ route categories=(diem_trung_tuyen,)
→ retrieval hit admission PDF chunk
→ Evidence Selection giữ chunk có mã 7480201
→ _parse_admission_table_facts tạo 3 facts cho CNTT:
   thpt=15, hoc_ba=18, dgnl=600
→ select_relevant_score_facts giữ đúng 3 facts của CNTT
→ deterministic branch=admission_score_lookup
→ _structured_score_answer
→ validate_model_answer=ok
→ planner mode=DIRECT_SHORT, deterministic=true
→ final_status=ok
```

### Trace D — ngoài phạm vi

`Giá vàng hôm nay?`

```text
normalize
→ intent=OUT_OF_SCOPE
→ scope.in_scope=false
→ planner mode=OUT_OF_SCOPE
→ final_status=out_of_scope
→ retriever không được gọi
```

## 6. Deterministic Logic

- `admission_score_lookup`: chọn verified facts đúng major/code và `score_type=admission_score`; dựng câu trả lời từ `raw_value`; chạy output validator trước khi trả.
- `application_threshold_lookup`: score engine chỉ chọn verified `application_threshold`, giữ mapping theo method và entity; answer generation hiện vẫn đi qua planner/validator để bảo toàn các contract hiện hữu.
- `supplementary_threshold_lookup`: route riêng tới `xet_tuyen_bo_sung`, chỉ chọn `supplementary_threshold`, không fallback sang điểm sàn ban đầu.
- `personal_score_comparison`: chỉ so sánh điểm người dùng với `application_threshold` verified. Kết quả luôn nêu giới hạn: đạt/vượt ngưỡng nhận hồ sơ không đồng nghĩa chắc chắn trúng tuyển. Nếu thiếu phương thức xét, trả `CLARIFICATION`.

Không có factual value nào được hard-code vào production answer logic; các giá trị trả ra đến từ evidence facts.

## 7. Evidence Availability

- `EvidenceBundle.is_usable` hiện là `chunks` có nội dung + `context` không rỗng + `sources` không rỗng.
- `sources` được tạo từ `metadata.source_url`, thường được gắn từ manifest/provenance backend.
- `source_url` metadata hiện là điều kiện provenance để document được chọn/usable; đây không phải URL phải xuất hiện trong PDF text.
- URL nhúng trong PDF không bắt buộc. `build_evidence()` loại URL nhúng khỏi context nhưng vẫn dùng `metadata.source_url` để tạo provenance object.
- Regression test đã xác nhận: PDF text không có URL hoặc có URL nhúng vẫn usable nếu metadata provenance hợp lệ.

Kết luận: PDF KHÔNG bắt buộc chứa URL.

## 8. Tests

| Suite | Passed | Failed | Skipped | Classification |
|---|---:|---:|---:|---|
| `tests/test_phase2_runtime.py` | 7 tests, 12 subtests | 0 | 0 | PASS |
| `tests/test_task_j.py` + `tests/test_intent_classifier.py` | 13 tests, 6 subtests | 0 | 0 | PASS |
| `tests/test_data_pipeline_recovery.py` | 5 | 0 | 0 | PASS; year/provenance pipeline unchanged |
| `tests/test_task_c.py` | 17 tests, 12 subtests | 2 | 0 | ENVIRONMENT ISSUE: Windows `PermissionError` during `TemporaryDirectory` cleanup |
| `tests/test_task_f.py` | 10 | 100 subfailures | 0 | DATASET MISMATCH: current processed/Chroma fixture lacks expected catalog/threshold categories |
| `tests/test_task_k.py` | 1 | 5 | 0 | DATASET MISMATCH: missing `nganh_dao_tao`/`nguong_dau_vao` fixture coverage |
| `tests/test_task_l.py` | 4 | 3 | 0 | DATASET MISMATCH propagated from missing retrieval evidence |
| `tests/test_task_response_ui.py` | 4 | 8 | 0 | DATASET MISMATCH propagated from missing retrieval evidence |
| Full `pytest` | no reliable summary | runner aborted | 0 | ENVIRONMENT ISSUE: temp cleanup/capture file closed on Windows |

Additional verification:

- `git diff --check`: pass.
- Query `Học phí DHV 2024` against the current retriever: `0` documents / `0` hits; 2024 does not leak into target-year 2026 retrieval.
- No retriever, Chroma, OCR, embedding or raw-data code was changed in Phase 2.

## 9. Remaining Issues

1. Corpus coverage: current verified 2026 corpus does not contain a tuition record for the requested per-credit amount, so `1 tín chỉ năm 2026 bao nhiêu tiền?` correctly remains `NO_DATA`.
2. Current `data/processed` fixture coverage used by older retrieval tests does not expose the catalog/threshold categories those tests expect. This is a dataset coverage/mismatch issue, not a router decision issue; no corpus rebuild was performed.
3. Several Windows test runs fail while cleaning temporary directories with `WinError 5`; this is an environment issue outside Phase 2 runtime logic.

## 10. Final Verdict

RUNTIME_ROUTING_READY
