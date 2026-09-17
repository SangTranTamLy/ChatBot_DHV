# TASK: SIMPLIFY CHAT RESPONSE UI + REMOVE SUGGESTED QUESTIONS COMPLETELY

## MỤC TIÊU

Thiết kế lại phần hiển thị câu trả lời của chatbot DHV theo hướng tối giản.

Yêu cầu:
- Bỏ toàn bộ background/card/container bao quanh câu trả lời thông thường của AI.
- Chỉ giữ khung/container khi nội dung cần hiển thị dạng bảng.
- Text, bullet, heading hiển thị trực tiếp trên nền trang.
- Bỏ hoàn toàn tính năng **Gợi ý tiếp theo / suggested questions**.
- Không còn suggestion chip, button hoặc câu hỏi đề xuất.
- Không làm ảnh hưởng RAG, retrieval, validator, conversation state.
- Không hiển thị source card, URL, metadata, chunk id, retrieval score.

---

## 1. AUDIT UI HIỆN TẠI

Trước khi sửa, kiểm tra:
- `app.py`
- file CSS / Streamlit style
- helper render message
- code render assistant answer
- code render table
- code render suggested questions
- `session_state` liên quan suggested questions

Xác định:
- background/card assistant được tạo ở đâu
- border-radius assistant được tạo ở đâu
- padding/container assistant được tạo ở đâu
- table render bằng Markdown hay custom HTML
- suggested questions sinh ở backend hay frontend
- click suggestion đang trigger luồng nào

Không sửa RAG nếu UI có thể giải quyết độc lập.

---

## 2. ASSISTANT RESPONSE — BỎ BACKGROUND

Đối với câu trả lời thông thường của assistant, bỏ:
- background
- border
- border-radius
- box-shadow
- card/container bao ngoài

Không muốn:

```text
┌───────────────────────────────────────┐
│ Nội dung chatbot...                   │
│                                       │
│ Các ngưỡng trong bảng là...           │
│                                       │
│ [ gợi ý 1 ]                           │
│ [ gợi ý 2 ]                           │
└───────────────────────────────────────┘
```

Mong muốn:

```text
Nội dung chatbot...

Các ngưỡng trong bảng là ngưỡng nhận hồ sơ,
không phải kết luận trúng tuyển.
```

Text hiển thị trực tiếp trên nền trang.

---

## 3. CHỈ DÙNG KHUNG KHI CÓ BẢNG

Ví dụ:

```text
┌───────────────────────────────────────┐
│ Tiêu chí        │ Công nghệ thông tin │
│ Mã ngành        │ 7480201             │
│ Ngưỡng THPT     │ 15                  │
│ Ngưỡng học bạ   │ 18                  │
│ Ngưỡng ĐGNL     │ 600                 │
└───────────────────────────────────────┘
```

Sau bảng:

```text
Các ngưỡng trên là ngưỡng nhận hồ sơ,
không phải kết luận trúng tuyển.
```

Phần giải thích phía dưới:
- không nằm trong card
- không background
- không border

---

## 4. TABLE UI

Table phải:
- border nhẹ, rõ
- header dễ đọc
- padding hợp lý
- responsive
- nếu rộng thì horizontal scroll
- container chỉ bao đúng table
- không bao luôn phần giải thích phía dưới

Không tạo card lớn bao cả:
`table + explanation + buttons`.

---

## 5. TEXT RESPONSE

Các mode sau render trực tiếp, không có card:

```text
DIRECT_SHORT
OVERVIEW
CATALOG_LIST
EXPLANATION
STEP_BY_STEP
RECOMMENDATION
CLARIFICATION
NO_DATA
OUT_OF_SCOPE
```

Ví dụ:

```text
### Công nghệ thông tin

Ngành Công nghệ thông tin của DHV có mã ngành 7480201.

Các chương trình đã ghi nhận gồm:

- Công nghệ phần mềm
- Lập trình AI
- An ninh mạng và hệ thống
- Truyền thông đa phương tiện
- Phân tích dữ liệu lớn
```

---

## 6. USER MESSAGE

Có thể giữ bubble riêng cho user.

User:
- căn phải
- bubble gọn
- không full width
- max-width hợp lý
- background nhẹ
- border-radius

Assistant:
- căn trái
- không bubble
- không background
- chỉ text/content

---

## 7. BỎ HOÀN TOÀN "GỢI Ý TIẾP THEO"

Xóa toàn bộ tính năng suggested questions, không chỉ ẩn CSS.

Bỏ:
- label `Gợi ý tiếp theo`
- suggested question list
- buttons
- chips
- clickable suggestion
- suggestion generator
- suggestion template
- suggestion state
- event handler của suggestion
- `session_state` chỉ phục vụ suggestions

Nếu backend đang return:

```python
{
    "answer": "...",
    "suggested_questions": [...]
}
```

thì kiểm tra dependency.

Nếu field không còn dùng ở nơi khác:
- loại bỏ.

Nếu cần backward compatibility:
- có thể giữ field nội bộ nhưng UI tuyệt đối không render.

Ưu tiên xóa code chết nếu an toàn.

---

## 8. KHÔNG ẢNH HƯỞNG CHAT FLOW

Sau khi bỏ suggestions, flow vẫn là:

```text
User nhập câu hỏi
↓
UI
↓
ask_chatbot()
↓
ChatService
↓
RAG
↓
answer
↓
UI render answer
```

User vẫn nhập câu hỏi bằng chat input bình thường.

---

## 9. KHÔNG HIỂN THỊ SOURCE

UI tiếp tục không hiển thị:
- source URL
- source card
- evidence id
- metadata
- chunk
- retrieval score
- internal RAG data

Backend có thể giữ sources để test/audit.

---

## 10. CSS / STYLE

Assistant text:
- `background: transparent`
- `border: none`
- `box-shadow: none`
- padding tối thiểu
- line-height dễ đọc

Paragraph:
- spacing khoảng 6–12px

Bullet:
- spacing rõ

Heading:
- hierarchy rõ, không quá lớn

Table:
- nền sáng
- border riêng
- border-radius nhẹ
- `overflow-x: auto`

Không tạo nested cards.

---

## 11. RESPONSIVE

Kiểm tra:
- desktop
- màn hình nhỏ
- bảng dài
- text dài
- bullet dài

Table được phép scroll ngang.

Text không vượt viewport.

---

## 12. TEST CASES UI

### Case 1
User:
`học phí học kỳ 1 bao nhiêu`

Expected:
- text trực tiếp
- không card
- không suggested questions

### Case 2
User:
`thông tin trường`

Expected:
- overview
- heading/bullet trực tiếp
- không background bao quanh

### Case 3
User:
`CNTT có những chuyên ngành nào`

Expected:
- list
- không card

### Case 4
User:
`so sánh CNTT và Kỹ thuật máy tính`

Expected:
- table có khung
- explanation dưới bảng không có khung

### Case 5
User:
`điểm xét tuyển ngành CNTT`

Expected:
- nếu planner chọn table thì table có container riêng
- phần giải thích ngoài table

### Case 6
Sau mọi câu trả lời:

Không được xuất hiện:
- `Gợi ý tiếp theo`
- suggestion chip
- suggestion button
- câu hỏi đề xuất

---

## 13. REGRESSION

Không được làm hỏng:
- conversation history
- ChatService
- rag_chain
- retrieval
- answer planner
- Markdown
- tables
- score logic
- catalog logic
- validator

Chạy full tests sau khi sửa.

---

## 14. MANUAL CHECK

Chạy:

```bash
streamlit run app.py
```

Kiểm tra thủ công:
1. normal text answer
2. bullet/list answer
3. table answer
4. multi-turn conversation

Chụp screenshot và lưu tại:

```text
reports/screenshots/ui_simplified/
```

---

## 15. ACCEPTANCE CRITERIA

PASS chỉ khi:
- assistant normal response không còn background/card
- assistant normal response không còn border
- table vẫn có khung rõ ràng
- table container chỉ bao table
- explanation dưới table nằm ngoài khung
- user bubble vẫn phân biệt rõ
- suggested questions biến mất hoàn toàn khỏi UI
- không còn `Gợi ý tiếp theo`
- không còn suggestion buttons/chips
- chat input vẫn hoạt động
- conversation history vẫn hoạt động
- full regression pass
- không hiển thị source cards/URLs
- không phá logic RAG

---

## 16. REPORT

Tạo:

```text
reports/TASK_UI_SIMPLIFICATION_REPORT.md
```

Report gồm:
1. UI root cause
2. Files changed
3. CSS changed
4. Components/functions removed
5. Suggested-question code removed
6. Table rendering changes
7. Before behavior
8. After behavior
9. Tests run
10. Regression result
11. Screenshot paths
12. Remaining issues

Cuối report ghi:

```text
STATUS: PASS
```

hoặc:

```text
STATUS: FAIL
```

---

## THIẾT KẾ ĐÍCH

Normal answer:

```text
User
                         ┌───────────────┐
                         │ thông tin CNTT│
                         └───────────────┘

Assistant

Công nghệ thông tin có mã ngành 7480201.

Các chương trình gồm:

- Công nghệ phần mềm
- Lập trình AI
- An ninh mạng và hệ thống
- Truyền thông đa phương tiện
- Phân tích dữ liệu lớn
```

Answer có bảng:

```text
Assistant

So sánh hai ngành:

┌────────────────────────────────────────┐
│                TABLE                   │
└────────────────────────────────────────┘

Các ngưỡng trên chỉ là ngưỡng nhận hồ sơ,
không phải kết luận trúng tuyển.
```

**Chỉ bảng có khung.**

Toàn bộ nội dung chatbot thông thường hiển thị trực tiếp trên nền trang.

**Bỏ hoàn toàn tính năng suggested_questions / Gợi ý tiếp theo.**
