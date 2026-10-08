# Task UI simplification — remove suggestions

## 1. Task

Thực hiện `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_UI_SIMPLIFICATION_REMOVE_SUGGESTIONS.md`:

- assistant response thông thường hiển thị trực tiếp trên nền trang;
- chỉ bảng được đặt trong container có border riêng;
- user bubble vẫn gọn và phân biệt rõ;
- loại bỏ hoàn toàn suggested-question UI;
- không làm thay đổi RAG, retrieval, validator, planner hoặc bounded conversation state;
- không hiển thị source card, URL, metadata, chunk id hoặc retrieval score.

## 2. UI root cause

Trước task, `app.py` áp style card chung cho phần content của mọi `st.chat_message`, nên assistant có background, border, border-radius và box-shadow. Cùng file này còn có quick-question pills ở empty state, related-question pills sau mỗi assistant answer, callback `_capture_related_question`, state `_selected_related_question` và nhánh submit riêng cho chip.

Table trước đây đi qua cùng luồng Markdown của assistant, chưa có container chỉ bao đúng phần bảng.

## 3. Current → expected

| Hạng mục | Trước | Sau |
|---|---|---|
| Assistant text/bullet/heading | Nằm trong card style chung | Markdown phẳng, nền trong suốt, không border/shadow |
| User message | Có bubble nhưng parent row còn nền mặc định và hướng đảo chưa phù hợp | Bubble gọn căn phải bằng `margin-left: auto`; hàng chat trong suốt |
| Table | Chưa cô lập container riêng | Tách Markdown table, chỉ table nằm trong `st.container(border=True)` |
| Explanation quanh table | Có thể đi cùng content card | Render ngoài table container |
| Empty state | Có quick-question pills | Chỉ greeting và chat input |
| Assistant follow-up | Có related-question pills/click handler | Không render, không tạo UI state, không submit từ suggestion |
| Source/provenance | Backend có thể giữ audit data | UI tiếp tục strip URL và không render provenance |

## 4. Files changed

- `app.py`
  - reset style của `stChatMessage` và assistant content về transparent/no border/no shadow;
  - giữ user bubble bằng CSS scoped cho user content;
  - thêm style border/padding/header/overflow ngang cho table;
  - thêm `_is_markdown_table_separator`, `_split_markdown_table` và `_render_answer_markdown`;
  - render tất cả status bằng Markdown phẳng để `CLARIFICATION`, `NO_DATA`, `OUT_OF_SCOPE` và lỗi không tạo alert card;
  - bỏ quick-question constant và toàn bộ suggestion rendering/state/event flow;
  - không thay đổi boundary gọi `ask_chatbot` hoặc đồng bộ `conversation_state`/`state`.
- `tests/test_app.py`
  - cập nhật empty-state contract không có pills;
  - cập nhật status contract sang direct Markdown;
  - thêm regression chứng minh container chỉ chứa table còn intro/explanation nằm ngoài.
- `tests/test_task_response_ui.py`
  - thay test click chip cũ bằng test backend `related_questions` không được render/submit ở UI;
  - giữ nguyên các test planner/RAG/natural-response hiện có.
- `reports/screenshots/ui_simplified/empty_state_no_suggestions.png`
  - screenshot empty state sau thay đổi.

## 5. Components/functions removed from UI

Đã bỏ khỏi `app.py`:

- `QUICK_QUESTIONS`;
- `_normalise_related_questions` ở UI boundary;
- `_capture_related_question`;
- `suggestion_key` và `st.pills` trong assistant renderer;
- quick-question `st.pills` và label gợi ý ở welcome;
- `_selected_related_question` session state;
- nhánh submit suggestion và việc lưu `related_questions` vào chat history mới.

Backend `related_questions` trong planner/service vẫn được giữ nội bộ để không phá contract audit/backward compatibility mà `tests/test_task_l.py` đang kiểm tra. UI không đọc, không hiển thị và không biến field này thành widget.

## 6. Table rendering

`_split_markdown_table` nhận diện block Markdown có header + separator, tách thành `before/table/after`. `before` và `after` render bằng Markdown trực tiếp; chỉ `table` nằm trong `st.container(border=True)`. CSS table được giới hạn trong chat content, có border nhẹ cho cell/header, padding hợp lý, `max-width: 100%`, `overflow-x: auto` và không tạo nested card cho phần giải thích.

## 7. Before behavior / after behavior

### Before

- Empty state hiển thị các câu hỏi khởi đầu.
- Assistant answer có card nền chung.
- Related questions có thể xuất hiện thành pills và click sẽ đưa câu hỏi vào submit flow.
- Alert status dùng các container nền của `st.info`, `st.warning`, `st.error`.

### After

- Empty state chỉ còn greeting, chat input và privacy notice.
- Assistant text/list/status hiển thị trực tiếp trên nền trang.
- User bubble vẫn căn phải, max-width giới hạn và có background nhẹ.
- Table có khung riêng; explanation nằm ngoài khung.
- Không còn label, button, chip, click handler hoặc UI state cho suggested questions.
- URL/source/backend metadata tiếp tục không xuất hiện trong UI.

## 8. Tests

### Baseline / reproduce

Targeted baseline trước sửa:

```text
Ran 22 tests in 1.073s
OK
```

Full baseline trong sandbox:

```text
Ran 128 tests in 2.495s
FAILED (errors=5, skipped=1)
```

5 lỗi baseline là lỗi quyền ghi/xóa thư mục tạm của sandbox ở các test ingestion/retriever; không phải lỗi assertion của task.

### Targeted result

```text
.venv\Scripts\python.exe -m unittest tests.test_app tests.test_task_response_ui tests.test_task_l -v
Ran 23 tests in 2.574s
OK
```

Bao phủ empty state, no-suggestion contract, status rendering, table container, source hiding, multi-turn UI contract và planner/RAG response regressions.

### Full regression result

```text
.venv\Scripts\python.exe -m py_compile app.py tests/test_app.py tests/test_task_response_ui.py
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
Ran 129 tests in 7.334s
OK (skipped=1)
```

`skipped=1` là real Qwen integration test chỉ chạy khi bật `RUN_REAL_QWEN_TESTS=1`; không ảnh hưởng UI task.

### Manual smoke

Đã chạy local:

```text
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8510 --server.headless true
```

Đã kiểm tra trên tab local bằng Computer Use:

1. Empty state không có suggestion.
2. `học phí học kỳ 1 bao nhiêu`: text trực tiếp, không assistant card.
3. `thông tin trường`: heading/bullet trực tiếp.
4. `CNTT có những chuyên ngành nào`: list trực tiếp.
5. `so sánh CNTT và Kỹ thuật máy tính`: table có border riêng, explanation nằm dưới và ngoài container.
6. Nhiều lượt hỏi liên tiếp: user bubble, assistant answer và chat input vẫn hoạt động.

## 9. Sources/data/conflicts

- Không thêm hoặc sửa data/RAG source.
- Không dùng `reference_images/` làm dữ liệu hay asset.
- Không truy cập nguồn web ngoài; task chỉ thay đổi UI.
- Không có conflict dữ liệu hoặc fact mới cần verify.
- Backend provenance vẫn tồn tại cho audit/tests nhưng không được đưa lên UI.

## 10. Remaining limitations

- Screenshot file là empty-state artifact; các trạng thái list/table/multi-turn đã được xác nhận trực tiếp trên local browser smoke nhưng không lưu thành artifact riêng.
- Real Qwen integration test không chạy do được skip theo cấu hình hiện tại.
- CSS vẫn dùng selector theo Streamlit `data-testid`; đây là phạm vi styling hiện có và không thay đổi business logic.

## 11. Status

Targeted tests pass, full regression pass và các UI/RAG invariants liên quan vẫn đúng.

STATUS: PASS
