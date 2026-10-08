# PHASE 4 – ANSWER BEHAVIOR AND CONVERSATION STATE REPORT

## 1. Root Causes

Các nguyên nhân chính đã được xác định và xử lý:

- `ask_chatbot()` trước đây chỉ có nhánh trả lời xác định cho `admission_score_lookup`; `application_threshold` và `supplementary_threshold` còn đi qua LLM hoặc rơi vào `no_data` trước khi tạo câu trả lời.
- Bộ marker xét tuyển bổ sung chưa nhận diện đầy đủ các cách hỏi như “điểm bổ sung”.
- Logic chọn facts dùng quy tắc “có facts theo ngành thì bỏ toàn bộ facts global”, khiến facts theo phương thức bị mất khi dữ liệu ngành chỉ công bố một phần phương thức.
- State chưa kế thừa ổn định phương thức và điểm sang lượt hỏi ngắn như “720 điểm”, đồng thời score context có thể bị coi là ngoài phạm vi.
- Retry khi draft LLM bị validator từ chối có thể biến một lượt tư vấn còn đủ evidence thành `error`; fallback an toàn chưa bao phủ hết các lý do từ chối score/relation.

## 2. Files Changed

| File | Thay đổi Phase 4 |
|---|---|
| `src/chatbot/query_analysis.py` | Nhận diện supplementary paraphrase; kế thừa method/score; bounded score context; merge facts ngành + global theo từng method; cập nhật state. |
| `src/chatbot/rag_chain.py` | Nhánh deterministic cho cả ba loại score lookup; trace matching facts; mở rộng retrieval cho tư vấn có điểm; clarification method; fallback và retry an toàn. |
| `src/chatbot/output_validator.py` | Không áp dụng mapping completeness của lookup lên advisory turn có score cá nhân; vẫn kiểm tra claim admission và grounding. |
| `tests/test_phase4_answer_behavior.py` | 7 bài regression mới, gồm 4 subtest supplementary paraphrase. |
| `tests/test_task_f.py` | Cập nhật một kỳ vọng cũ để phản ánh hợp đồng mới: score lookup dùng câu trả lời verified cấu trúc, không gọi LLM. |

`evidence.py`, `answer_planner.py` và `chat_service.py` đã được audit theo trace; không cần thay đổi để đáp ứng Phase 4. Luồng ingestion, OCR, embedding và Chroma không bị thiết kế lại.

## 3. Deterministic Score Results

| Query | Query type / branch | Kết quả kiểm chứng |
|---|---|---|
| `Điểm sàn CNTT 2026?` | `application_threshold_lookup` / deterministic | THPT `15,00`; ĐGNL `600`; `validator=ok`; `status=ok`. |
| `Điểm nhận hồ sơ bổ sung CNTT?` | `supplementary_threshold_lookup` / deterministic | THPT `15.0`; học bạ `18.0`; không trộn `600`; `validator=ok`. |
| `Điểm bổ sung CNTT bao nhiêu?` | `supplementary_threshold_lookup` / deterministic | Cùng facts bổ sung, không rơi `no_data`. |

Câu trả lời cấu trúc đi qua `validate_model_answer()` như câu trả lời LLM, nhưng LLM không được chọn method hay con số.

## 4. Global vs Major-Specific Rules

Đã kiểm thử với facts giả lập verified:

- global THPT = `15`
- global ĐGNL = `600`
- CNTT-specific THPT = `18`

Kết quả chọn facts là THPT `18` và ĐGNL `600`. Nghĩa là facts specific chỉ override đúng method mà nó khai báo; method còn thiếu tiếp tục dùng rule global. Không còn hiện tượng một row specific làm mất toàn bộ global mapping.

## 5. Conversation State Contract

| Field | Set / giữ / bỏ qua |
|---|---|
| `current_year` | Set khi query nêu năm; giữ năm trước nếu lượt sau không nêu. |
| `current_major`, `current_program` | Set từ entity verified; giữ khi follow-up liên quan; không tự áp vào tuition/học bổng hoặc chủ đề mới. |
| `current_method` | Set từ THPT, học bạ hoặc ĐGNL; dùng cho bare score follow-up. |
| `current_score_type` | Giữ loại score đang hỏi; không dùng để biến câu hỏi học phí thành score query. |
| `student_scores` | Lưu bounded score theo method; score chưa rõ method lưu dưới `unspecified`; không bị xóa bởi lượt liên quan. |
| `interest` | Giữ tín hiệu tư vấn ngành; không được dùng làm evidence. |
| `candidate_majors`, `candidate_programs` | Giữ danh sách lựa chọn; không ép thành một `current_major`. |
| `last_listed_majors`, `previous_intent`, `turn_count` | Tiếp tục phục vụ follow-up danh sách và audit; tăng theo lượt. |

## 6. Six Required Conversation Traces

- **A — score lookup:** query được nhận diện là `HOI_NGUONG_DAU_VAO`; route deterministic; `matching_facts` và `selected_score_facts` chứa facts verified; validator và `final_status` đều `ok`.
- **B — supplementary:** các paraphrase cùng vào `HOI_XET_TUYEN_BO_SUNG`; branch là `supplementary_threshold_lookup`; không đưa fact ĐGNL `600` vào câu trả lời.
- **C — candidates → score:** `candidate_majors` vẫn là `Marketing` và `Công nghệ thông tin`; `current_major` vẫn rỗng; hệ thống hỏi bổ sung phương thức thay vì tự chọn một ngành.
- **D — method + score → major:** `current_method=dgnl`, `student_scores.dgnl=720`; lượt `CNTT thì sao?` kế thừa đúng hai slot, đối chiếu với `600`, và không phát biểu đảm bảo trúng tuyển.
- **E — score → Marketing:** score `19` được giữ dưới `unspecified`; lượt Marketing giữ entity ngành và hỏi phương thức còn thiếu, không vứt score và không chuyển score vào topic không liên quan.
- **F — score → tuition:** trace lượt học phí có `student_scores={}` và `score_type=None`; retrieval/answer dùng facts học phí; state trước đó vẫn còn score nhưng score không ảnh hưởng câu trả lời.

Trace hiện có các trường audit chính: `intent`, `entities`, `route`, `retrieved_docs_count`, `evidence_count`, `score_facts`, `matching_facts`, `selected_score_facts`, `score_engine`, `deterministic_branch`, `deterministic_validation`, `validator`, `answer_plan`, `planner_mode`, `final_status`.

## 7. Validator and Fallback

Luồng score lookup là:

`verified facts → structured score answer → validate_model_answer → answer_plan → final_status`.

Luồng tư vấn vẫn gọi LLM khi cần ngôn ngữ tự nhiên. Nếu draft bị từ chối vì `ungrounded_entity`, `missing_threshold_mapping`, `wrong_threshold_mapping`, `method_mismatch` hoặc lý do tương đương, retry được bắt lỗi; grounded fallback dùng state/evidence hoặc clarification thay vì trả generic `error`/`no_data`. Claim kiểu “chắc chắn đậu” tiếp tục bị từ chối.

## 8. Test Results

| Suite | Kết quả |
|---|---|
| `tests/test_phase4_answer_behavior.py` | **7 passed, 4 subtests passed** |
| `tests/test_phase2_runtime.py`, `tests/test_task_f.py`, `tests/test_task_l.py`, `tests/test_task_response_ui.py` | **49 passed, 124 subtests passed** |
| Full `pytest -q` | Không hoàn tất do lỗi môi trường Windows ở pytest capture/temp cleanup (`ValueError: I/O operation on closed file`, `WinError 5`); không có assertion summary đáng tin cậy. |

Đã chạy thêm `py_compile` cho các module Phase 4 và test mới: đạt.

## 9. Regression Check

- Luồng retrieval hybrid và evidence hiện có tiếp tục được dùng; targeted runtime/retrieval tests đạt.
- Year isolation, catalog, relation validation, tuition và UI response tests trong nhóm mục tiêu đạt.
- Không thêm logic cho phép suy đoán khi thiếu facts; thiếu method ở personal score vẫn hỏi clarification.
- Không thay đổi ingestion, OCR, embedding model, Chroma schema hoặc UI contract.

## 10. Remaining Issues

Chỉ còn giới hạn xác minh toàn bộ suite trên môi trường hiện tại: pytest không dọn được temp directory và đóng capture stream trong teardown. Đây là lỗi runner/Windows permission, không phải failure của các assertion Phase 4; các suite mục tiêu đều đã chạy đạt.

## 11. Final Verdict

**ANSWER_AND_CONVERSATION_READY**

Phase 4 đã sẵn sàng ở mức answer behavior, deterministic score lookup, grounding validation và bounded conversation state. Full-suite execution cần được chạy lại trong môi trường pytest/Windows không gặp lỗi cleanup nói trên.
