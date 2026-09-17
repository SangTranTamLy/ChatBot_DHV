# TASK: FIX FINAL CHAT UI + EXACT GREETING + EXPAND SCHOOL-INFO RAW DATA

## MỤC TIÊU

Fix đồng thời 3 vấn đề đang còn tồn tại trong Chatbot DHV:

1. UI vẫn còn background/bubble ở tin nhắn của **người dùng**.
2. Câu chào mặc định chưa đúng nội dung yêu cầu.
3. RAW `thong_tin_truong` còn thiếu hệ sinh thái website chính thức của DHV.

Task này phải sửa có kiểm soát, không phá RAG, retrieval, validator, conversation state hoặc các regression đã pass trước đó.

---

# PHẦN A — FIX UI: BỎ BACKGROUND CẢ USER VÀ ASSISTANT

## A1. Yêu cầu mới

Yêu cầu trước đây "giữ bubble cho user" KHÔNG CÒN áp dụng.

Thiết kế mới:

- USER: không background.
- USER: không bubble.
- USER: không border/card.
- ASSISTANT: không background.
- ASSISTANT: không bubble.
- ASSISTANT: không border/card.
- Chỉ **TABLE** được phép có khung/container riêng.

Mục tiêu là giao diện sạch, tối giản.

---

## A2. User message

Hiện tại user message đang có dạng bubble/background như:

```text
┌──────────────────────────────────────────┐
│ CNTT có những chuyên ngành nào           │
└──────────────────────────────────────────┘
```

Phải bỏ hoàn toàn background đó.

Sau khi sửa, user message chỉ cần:

```text
CNTT có những chuyên ngành nào
```

Có thể dùng:
- căn phải hoặc phân biệt bằng khoảng cách/alignment
- icon/avatar nhỏ nếu hiện tại đang dùng
- font-weight vừa phải

Nhưng KHÔNG được dùng:

```css
background
border
box-shadow
card
bubble
```

để bao user text.

---

## A3. Assistant message

Assistant cũng render trực tiếp trên nền trang.

Ví dụ:

```text
Mình liệt kê các chương trình thuộc ngành Công nghệ thông tin:

1. Công nghệ phần mềm
2. Lập trình AI
3. An ninh mạng và hệ thống
4. Truyền thông đa phương tiện
5. Phân tích dữ liệu lớn
```

Không tạo card/bubble bao quanh.

---

## A4. Chỉ table được có khung

Ví dụ:

```text
So sánh hai ngành:

┌──────────────────────────────────────────────┐
│ Tiêu chí       │ CNTT       │ KT máy tính    │
├──────────────────────────────────────────────┤
│ ...            │ ...        │ ...            │
└──────────────────────────────────────────────┘

Các ngưỡng trên là ngưỡng nhận hồ sơ,
không phải kết luận trúng tuyển.
```

Chỉ phần `TABLE` có:
- border
- background nhẹ nếu cần
- border-radius nhẹ
- horizontal scroll nếu bảng rộng

Phần text trước và sau table phải nằm ngoài khung.

---

## A5. Audit CSS trước khi sửa

Agent phải tìm chính xác rule nào đang tạo background user hiện tại.

Kiểm tra tối thiểu:

```text
app.py
.streamlit/config.toml
các file CSS/style nếu có
helper render chat
st.chat_message
custom HTML
unsafe_allow_html
container wrapper
```

Tìm các CSS selector liên quan:

```text
user
assistant
chat-message
message
bubble
background
border
border-radius
box-shadow
```

Không được chỉ thêm một CSS override chồng lên rất nhiều rule cũ nếu có thể dọn sạch logic cũ.

---

# PHẦN B — BỎ HOÀN TOÀN GỢI Ý CÂU HỎI

Task trước đã yêu cầu bỏ suggested questions.

Agent phải kiểm tra lại để bảo đảm không còn:

- `Gợi ý tiếp theo`
- suggested question
- question chip
- suggestion button
- suggestion generator
- suggestion state
- suggestion event handler
- clickable follow-up
- default follow-up FAQ

Nếu còn code chết chỉ phục vụ tính năng này và không có dependency khác:

=> xóa.

Không chỉ dùng CSS `display: none`.

---

# PHẦN C — THAY CÂU CHÀO MẶC ĐỊNH

## C1. Bỏ câu chào cũ

Không sử dụng nữa:

```text
Chào bạn! Tôi có thể hỗ trợ tra cứu thông tin tuyển sinh DHV đã được kiểm chứng cho năm 2026. Bạn muốn hỏi điều gì?
```

---

## C2. Câu chào mới — phải dùng đúng nội dung

Thay bằng:

```text
Xin chào! Tôi là ChatBot DHV – Trợ lý Tuyển sinh Trường Đại học Hùng Vương TP.HCM.

Tôi có thể giải đáp nhanh cho bạn về:

- Phương thức & điều kiện xét tuyển
- Chỉ tiêu & ngành đào tạo
- Hồ sơ, lịch trình & thủ tục nhập học

Bạn đang cần hỗ trợ nội dung nào?
```

Yêu cầu:

- giữ xuống dòng như trên
- render Markdown bullet đúng
- không đặt cả greeting vào card/background
- không thêm "Gợi ý tiếp theo" bên dưới
- không tự động thêm source
- không đổi thành một paragraph dài

---

## C3. Greeting phải deterministic

Greeting mặc định lúc mở app không cần gọi RAG/LLM.

Nó nên là system/static UI copy.

Flow:

```text
App khởi động
↓
chưa có hội thoại
↓
render greeting mặc định
↓
user nhập câu hỏi
↓
ChatService
↓
RAG
```

Không tốn retrieval hoặc LLM chỉ để tạo câu chào mặc định.

Lưu ý:

Greeting có nhắc "Chỉ tiêu".

Nếu user hỏi chỉ tiêu cụ thể nhưng KB hiện không có dữ liệu xác minh tương ứng:

```text
không được hallucinate
↓
NO_DATA / trả theo verified evidence hiện có
```

---

# PHẦN D — MỞ RỘNG RAW `THONG_TIN_TRUONG`

## D1. Có được gộp chung không?

**CÓ.**

Các thông tin ở mức:

- website chính của trường
- website tuyển sinh
- các viện
- các khoa
- cổng thông tin đào tạo

có thể gộp chung vào RAW:

```text
data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf
```

Không cần tạo một RAW Markdown riêng.

RAW mới vẫn phải là **PDF** theo quy tắc của project.

---

## D2. Mục đích của file này

`thong_tin_truong_dhv_2026.pdf` nên trở thành tài liệu tổng quan chính thức về:

```text
- thông tin nhận diện trường
- giới thiệu ngắn
- năm thành lập
- định hướng
- website chính thức
- website tuyển sinh
- hệ sinh thái đơn vị trực thuộc
- cổng thông tin chính thức
- cơ sở/liên hệ đã xác minh
```

---

## D3. Bổ sung section mới

Trong PDF hiện tại, thêm section:

```text
HỆ SINH THÁI WEBSITE CHÍNH THỨC CỦA DHV
```

Bổ sung các website sau.

### Website cấp trường

**Website chính Trường Đại học Hùng Vương TP.HCM**

```text
https://dhv.edu.vn/
```

**Cổng tuyển sinh DHV**

```text
https://tuyensinh.dhv.edu.vn/
```

---

### Các viện

**Viện Đào tạo Sau đại học**

```text
https://ipic.dhv.edu.vn/
```

**Viện Liên kết Giáo dục và Đào tạo từ xa**

```text
https://epdl.dhv.edu.vn/
```

---

### Các khoa trực thuộc

**Khoa Khoa học Sức khỏe**

```text
https://heal.dhv.edu.vn/
```

**Khoa Kỹ thuật Công nghệ**

```text
https://tec.dhv.edu.vn/
```

**Khoa Tài chính - Ngân hàng - Kế toán**

```text
https://fba.dhv.edu.vn/
```

**Khoa Quản trị Kinh doanh - Marketing**

```text
https://bam.dhv.edu.vn/
```

**Khoa Ngôn ngữ**

```text
https://lan.dhv.edu.vn/
```

**Khoa Du lịch - Nhà hàng - Khách sạn**

```text
https://host.dhv.edu.vn/
```

---

### Cổng thông tin đào tạo

**Cổng thông tin đào tạo dành cho sinh viên/giảng viên**

```text
https://online.dhv.edu.vn/
```

---

## D4. Audit thêm đơn vị chính thức

Không dừng ở danh sách trên.

Agent phải kiểm tra:

```text
https://dhv.edu.vn/
https://tuyensinh.dhv.edu.vn/
```

để xem còn website đơn vị/khoa chính thức nào đang được trường liên kết trực tiếp mà RAW chưa ghi nhận.

Ví dụ:

- nếu trang tuyển sinh/trang trường chính thức liên kết một khoa khác
- nếu có Khoa Luật hoặc đơn vị khác với subdomain chính thức

=> xác minh trước khi thêm.

Không tự đoán URL.

Không thêm domain ngoài hệ sinh thái DHV nếu không có bằng chứng chính thức.

---

# PHẦN E — QUY TẮC KHI GỘP RAW

## E1. Chỉ gộp thông tin tổng quan

Trong `thong_tin_truong_dhv_2026.pdf`, với mỗi website chỉ cần ghi:

```text
- tên đơn vị
- loại đơn vị
- URL chính thức
- vai trò/mục đích chung của trang
```

Ví dụ:

```text
Khoa Kỹ thuật Công nghệ
Website: https://tec.dhv.edu.vn/
Loại: Khoa trực thuộc
Mục đích: Trang thông tin chính thức của Khoa Kỹ thuật Công nghệ.
```

---

## E2. Không dump toàn bộ nội dung từng khoa vào file này

KHÔNG copy tất cả:

- chương trình đào tạo chi tiết
- bài báo
- tin tức
- giảng viên
- danh sách nhân sự
- nội dung dài của từng khoa

vào `thong_tin_truong`.

File này là **school overview / official website directory**, không phải nơi chứa toàn bộ website.

---

## E3. Nếu sau này cần dữ liệu chi tiết của khoa

Ví dụ cần:

```text
chương trình CNTT
mô tả chương trình
định hướng đào tạo
nội dung chuyên ngành
```

thì phải:

```text
xác minh trang khoa
↓
đối chiếu với nguồn tuyển sinh trung tâm 2026
↓
tạo RAW PDF đúng category tương ứng
```

Không nhét tất cả vào `thong_tin_truong`.

---

# PHẦN F — SOURCE PRIORITY

Khi có dữ liệu tuyển sinh bị khác nhau giữa các website:

```text
1. Cổng tuyển sinh DHV 2026
2. Thông báo chính thức DHV 2026
3. Website trường chính
4. Website khoa/viện hiện hành
5. Trang cũ
```

Không để trang khoa cũ override dữ liệu tuyển sinh 2026 ở nguồn trung tâm.

Nếu conflict:

Tạo/update:

```text
reports/DATA_CONFLICTS_2026.md
```

Ghi:

```text
- field bị conflict
- nguồn A
- nguồn B
- ngày/năm của mỗi nguồn
- source được ưu tiên
- lý do
```

---

# PHẦN G — PRIVACY / ONLINE PORTAL

Đối với:

```text
https://online.dhv.edu.vn/
```

Chỉ ghi nhận đây là cổng thông tin đào tạo chính thức.

KHÔNG:

- đăng nhập
- thu thập tài khoản
- thu thập dữ liệu sinh viên
- thu thập dữ liệu giảng viên
- crawl nội dung cá nhân sau đăng nhập
- lưu PII

Chatbot tuyển sinh không cần dữ liệu riêng tư từ portal này.

---

# PHẦN H — WEBSITE URL TRONG CÂU TRẢ LỜI

Quy tắc UI hiện tại vẫn là:

Không tự động hiển thị:

```text
Nguồn:
https://...
```

sau mỗi câu trả lời.

Tuy nhiên nếu user hỏi trực tiếp:

```text
website trường là gì?
web tuyển sinh DHV?
website Khoa Kỹ thuật Công nghệ?
cổng thông tin đào tạo ở đâu?
```

thì URL chính là **nội dung được yêu cầu**.

Trong trường hợp đó được phép trả URL.

Phân biệt:

```text
URL như provenance/source card
→ KHÔNG HIỂN THỊ

URL là câu trả lời trực tiếp cho câu hỏi "website/link là gì"
→ ĐƯỢC HIỂN THỊ
```

---

# PHẦN I — CẬP NHẬT PIPELINE SAU KHI RAW THAY ĐỔI

Sau khi cập nhật:

```text
data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf
```

phải chạy lại đúng pipeline hiện tại:

```text
RAW PDF
↓
prepare processed
↓
Markdown + YAML metadata
↓
split chunks
↓
embedding
↓
ChromaDB rebuild/update
↓
retrieval smoke test
↓
regression
```

Không chỉnh trực tiếp processed để giả lập dữ liệu.

Source of truth vẫn là RAW PDF.

---

# PHẦN J — METADATA

Processed document sinh từ RAW này phải giữ category tương đương:

```text
category: thong_tin_truong
```

Nếu schema hiện tại có field:

```text
source_url
source_name
year
verified
```

thì sử dụng đúng convention hiện tại.

Không tự tạo schema mới nếu không cần.

---

# PHẦN K — QUERY PHẢI HỖ TRỢ SAU KHI REBUILD

Thêm test cho ít nhất các câu:

```text
website chính của DHV là gì?
```

Expected:
- trả `https://dhv.edu.vn/`

```text
web tuyển sinh DHV là gì?
```

Expected:
- trả `https://tuyensinh.dhv.edu.vn/`

```text
website Khoa Kỹ thuật Công nghệ là gì?
```

Expected:
- trả `https://tec.dhv.edu.vn/`

```text
web Khoa Ngôn ngữ?
```

Expected:
- trả `https://lan.dhv.edu.vn/`

```text
Khoa Khoa học Sức khỏe có website không?
```

Expected:
- trả đúng website verified

```text
DHV có Viện Đào tạo Sau đại học không?
```

Expected:
- trả đúng theo verified RAW

```text
website Viện Đào tạo Sau đại học?
```

Expected:
- `https://ipic.dhv.edu.vn/`

```text
DHV có đào tạo từ xa không?
```

Expected:
- chỉ trả điều được nguồn xác minh
- không tự suy diễn chương trình cụ thể nếu RAW không có

```text
cổng thông tin đào tạo của DHV là gì?
```

Expected:
- `https://online.dhv.edu.vn/`

---

# PHẦN L — UI TEST BẮT BUỘC

## Case 1 — User message

User:

```text
CNTT có những chuyên ngành nào
```

Expected:

- user text KHÔNG có background
- KHÔNG bubble
- KHÔNG border/card

---

## Case 2 — Assistant list

Expected:

```text
Mình liệt kê...

1. ...
2. ...
```

- không background
- không card

---

## Case 3 — Table

Expected:

- chỉ table có khung
- text trước/sau table không có khung

---

## Case 4 — Greeting

Mở app mới.

Expected hiển thị đúng:

```text
Xin chào! Tôi là ChatBot DHV – Trợ lý Tuyển sinh Trường Đại học Hùng Vương TP.HCM.

Tôi có thể giải đáp nhanh cho bạn về:

- Phương thức & điều kiện xét tuyển
- Chỉ tiêu & ngành đào tạo
- Hồ sơ, lịch trình & thủ tục nhập học

Bạn đang cần hỗ trợ nội dung nào?
```

Không background/card.

---

## Case 5 — Suggested questions

Sau bất kỳ response nào:

KHÔNG được xuất hiện:

```text
Gợi ý tiếp theo
```

hoặc chip/button câu hỏi.

---

# PHẦN M — REGRESSION

Không được phá:

- ChatService
- rag_chain
- hybrid retrieval
- evidence selection
- answer planner
- validator
- conversation state
- score intent
- catalog logic
- program parent-child
- source provenance backend
- Streamlit chat input

Chạy baseline trước và full regression sau.

---

# PHẦN N — REPORT

Tạo:

```text
reports/TASK_UI_GREETING_SCHOOL_RAW_FIX_REPORT.md
```

Report phải gồm:

1. Root cause user background còn tồn tại.
2. CSS/UI files changed.
3. Greeting location before/after.
4. Suggested-question cleanup status.
5. RAW file updated.
6. Website sources added.
7. Additional official units discovered during audit.
8. Processed rebuild result.
9. Chroma rebuild/result.
10. New retrieval tests.
11. UI manual tests.
12. Full regression result.
13. Remaining limitations.
14. Screenshot paths.

Chụp screenshot sau sửa:

```text
reports/screenshots/ui_final/
```

Tối thiểu:
- greeting
- normal user + assistant message
- list answer
- table answer
- website answer

---

# ACCEPTANCE CRITERIA

Chỉ ghi `STATUS: PASS` khi tất cả điều sau đúng:

- user message không còn background
- assistant message không còn background
- không còn user/assistant bubble/card
- chỉ table có khung
- greeting đúng chính xác nội dung yêu cầu
- greeting không gọi LLM/RAG không cần thiết
- `Gợi ý tiếp theo` biến mất hoàn toàn
- suggested questions không còn trên UI
- RAW `thong_tin_truong_dhv_2026.pdf` đã được cập nhật
- các website chính thức đã được ghi nhận
- processed được regenerate từ RAW
- vector DB/retrieval được rebuild/update đúng pipeline
- website query test pass
- existing factual regression pass
- không có hallucination mới
- không crawl PII từ online portal
- không hiển thị source URL tự động
- URL chỉ hiện khi nó chính là nội dung user hỏi

Cuối report:

```text
STATUS: PASS
```

hoặc:

```text
STATUS: FAIL
```
