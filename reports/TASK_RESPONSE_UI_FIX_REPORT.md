# TASK_RESPONSE_UI_FIX_REPORT

## 1. Task

Thực hiện `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_FIX_NATURAL_RESPONSE_ANSWER_PLANNER_UI.md`:
audit và sửa query analysis, answer planner, generation/validation, related-question
UI và Streamlit chat rendering; giữ nguyên factual/RAG invariants.

## 2. Baseline và audit

Đã đọc task file, các module router/RAG/evidence/state/service/validator/prompt/UI,
`00_MASTER_PLAN.md` trong phạm vi kế hoạch của repository và `Tong_quan_xay_dung_chatbot_AI.pdf`.
PDF chỉ được dùng để đối chiếu phương pháp pipeline, không dùng làm nguồn dữ liệu tuyển sinh.

Audit trước khi sửa được ghi tại [ANSWER_UI_AUDIT.md](ANSWER_UI_AUDIT.md).

Baseline command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Baseline: `116 tests`, `111 ok`, `1 skipped`, `5 errors`. Năm lỗi là lỗi quyền
Windows sandbox khi các test ingestion tạo/dọn thư mục tạm; không có failure assertion
ở các test logic hiện có.

## 3. Root cause và current → expected

| Khu vực | Current | Expected / đã sửa |
| --- | --- | --- |
| Identity | Câu hỏi về chatbot tuyển sinh có thể rơi vào route cơ sở/liên hệ và retrieval | Nhận diện `SYSTEM_IDENTITY`, trả lời deterministic, không RAG và không tự nhận là kênh chính thức |
| Score | Cụm “đủ điều kiện nộp hồ sơ” che mất điểm ĐGNL; điểm đơn chưa gắn method | Chuẩn hóa điểm ĐGNL, phân biệt application threshold, admission score và supplementary; so sánh số bằng Python, không kết luận đậu/rớt |
| Tổ hợp | `A00` có thể nhận nhầm facts điểm sàn | Tổ hợp 2026 chưa verified trả `NO_DATA`, không gọi model và không rò threshold khác loại |
| Interest | Interest extractor ăn cả mệnh đề “nên học ngành nào” | Cắt theo mệnh đề tự nhiên, giữ sở thích ngắn để planner tư vấn đúng |
| Response | Model có thể echo context, trả comparison thành văn xuôi hoặc gộp điều kiện học bổng | Plan được áp dụng sau generation: overview/comparison/scholarship dùng format evidence-owned khi evidence đủ; fallback cục bộ vẫn giữ đúng dòng fact |
| Length | Câu hỏi đơn giản có thể nhận paragraph/context dump | `DIRECT_SHORT` đưa fact chính trước; catalog count không dump danh sách |
| Related questions | Markdown list giống FAQ và không đi cùng submit flow | `st.pills` 2–3 chip theo intent/entity; click đưa query vào cùng `_record_and_render_exchange` → ChatService/RAG |
| Chat UI | User/assistant chưa có bubble phân biệt rõ; selector CSS nhắm sai wrapper | User bubble căn phải, max 72%; assistant căn trái, max 84%; bảng có overflow ngang; vẫn dùng native `st.chat_message` |

## 4. Files và functions đã thay đổi

- `src/chatbot/query_analysis.py`: nhận diện identity, score ĐGNL cá nhân, score type,
  admission combination, interest clause và route liên quan.
- `src/chatbot/answer_planner.py`: mode selection theo question shape, `AnswerPlan.is_catalog_list`,
  semantic alias `CATALOG_LIST` cho contract catalog nhưng giữ `ANSWER_MODES` lịch sử để tương thích caller/test.
- `src/chatbot/rag_chain.py`: evidence-only formatters cho overview/tuition/scholarship/score/
  comparison/recommendation; artifact realization; structured comparison sau validation;
  deterministic combination boundary; local-model fallbacks an toàn.
- `src/chatbot/output_validator.py`: cho phép historical year literal chỉ khi literal đó có trong
  selected verified evidence; mở rộng nhận diện claim so sánh và vẫn giữ các guard entity/date/score/admission.
- `src/prompts/rag_prompt.py`: ép plan/format/độ dài và cấm echo metadata, evidence wrapper, URL và boilerplate nguồn.
- `app.py`: CSS độc lập cho bubble/card, căn user/assistant đúng native DOM, `st.pills` cho related questions,
  route chip về cùng submit flow và vẫn ẩn sources/URL/metadata ở UI.
- `tests/test_task_response_ui.py`: regression cho các query/behavior cases trọng tâm của task, gồm AppTest chip flow và
  local-generation fallback cho tuition/scholarship.
- `reports/ANSWER_UI_AUDIT.md`: audit bắt buộc trước sửa.
- `reports/screenshots/task_response_ui_initial.png`: screenshot UI sau sửa.

## 5. Architecture trước và sau

### Trước

```text
User → app.py → ChatService → query analysis/router
     → retrieval/evidence → AnswerPlan + prompt → LocalLLM
     → validator → Streamlit renderer
```

Planner và evidence đã tồn tại nhưng chưa kiểm soát chặt hình thức cuối; overview,
comparison và scholarship policy còn phụ thuộc nhiều vào cách model tự dàn trang; related
questions được render như Markdown list.

### Sau

```text
User
  → normalize + intent/entity/state
  → router + Evidence Selection
  → deterministic score/catalog/boundary logic
  → AnswerPlan
  → LLM natural-language realization khi phù hợp
  → grounding/relevance validator + bounded retry/fallback
  → ChatService payload/provenance
  → UI answer/status/chips only
```

Không tạo module trùng chức năng và giữ nguyên API `ChatService`/`ask_chatbot`. Facts, số,
count, filter, parent-child relation và score comparison vẫn do Python/evidence quyết định.
LLM chỉ diễn đạt; nếu output không grounded hoặc không đúng shape thì regenerate/fallback/
`NO_DATA` theo boundary. `sources` và trace vẫn giữ ở backend, không render ra UI.

## 6. Answer modes

Planner hỗ trợ:

```text
DIRECT_SHORT
EXPLANATION
OVERVIEW
CATALOG_LIST (semantic alias trên contract TABLE để giữ tương thích)
COMPARISON
TABLE
STEP_BY_STEP
RECOMMENDATION
CLARIFICATION
NO_DATA
OUT_OF_SCOPE
```

Các ví dụ đã kiểm tra: tuition → `DIRECT_SHORT`, school overview → `OVERVIEW`, catalog
count → short deterministic, program list → table/list có parent, comparison → bảng cạnh nhau,
scholarship policy → bullet conditions, personal score → deterministic comparison,
out-of-scope/unknown combination → boundary không gọi model.

## 7. Generation, validation và data invariants

- Không thêm nguồn hoặc dữ liệu mới; không dùng `reference_images/` làm KB.
- Chỉ giữ evidence verified DHV 2026 và official `dhv.edu.vn`/subdomain theo corpus hiện tại.
- Không trộn formula với threshold, admission score, supplementary hay scholarship policy.
- `Truyền thông đa phương tiện` vẫn là chương trình thuộc ngành Công nghệ thông tin.
- Học bạ ngành Luật chưa có rule verified phù hợp vẫn trả `NO_DATA`.
- Tổ hợp `A00` năm 2026 chưa verified vẫn trả `NO_DATA`.
- Không hiển thị URL, source card, chunk/evidence id, retrieval score hoặc metadata trong UI.

## 8. Tests và kết quả

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_task_response_ui tests.test_task_f tests.test_task_k tests.test_task_l tests.test_app -v
```

Kết quả targeted cuối: `19 tests`, `OK`.

Full regression command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Kết quả full cuối chạy ngoài sandbox Windows: `Ran 128 tests in 4.562s`,
`OK (skipped=1)`. Test Qwen thật được skip theo thiết kế nếu không bật
`RUN_REAL_QWEN_TESTS=1` và không có Ollama/model tương ứng.

Static check:

```text
git diff --check
```

Không có whitespace error; chỉ có cảnh báo line-ending LF/CRLF của working tree.

## 9. Manual UI smoke

Đã chạy Streamlit bằng process sạch trên local ports 8506/8507 và kiểm tra bằng computer-use
trên viewport desktop 1280×720:

- welcome/quick questions/privacy reminder hiển thị.
- câu hỏi học phí trả một bubble ngắn, fact chính ở trước.
- comparison hiển thị Markdown table trong assistant card; bảng có cuộn ngang ở viewport hẹp.
- scholarship policy hiển thị từng điều kiện dạng bullet, không gộp thành paragraph.
- related chip click tạo user message mới và chạy cùng chat flow.
- user bubble co theo nội dung và căn phải; assistant bubble căn trái.
- out-of-scope hiển thị cảnh báo ngắn, không retrieval/model.
- chat nhiều lượt, long assistant response và long user message đã được kiểm tra.

Screenshot: [task_response_ui_initial.png](screenshots/task_response_ui_initial.png)

## 10. Limitations / unverified

- Real Qwen integration chưa chạy trong regression vì môi trường không bật Ollama/model;
  offline suite và LocalLLM fallback/validator đã được kiểm tra.
- Comparison table trên màn hình hẹp giữ tính đúng bằng horizontal overflow; người dùng
  có thể cuộn để xem đủ cột.
- Các câu hỏi mà corpus 2026 chưa xác minh (ví dụ học bạ Luật phù hợp hoặc A00) vẫn cố ý
  trả `NO_DATA`, không dùng dữ liệu cũ để làm câu trả lời đẹp hơn.

## 11. Exact reproduce commands

```powershell
Set-Location C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV
.\.venv\Scripts\python.exe -m unittest tests.test_task_response_ui tests.test_task_f tests.test_task_k tests.test_task_l tests.test_app -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501
```

STATUS: PASS
