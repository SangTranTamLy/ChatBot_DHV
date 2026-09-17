# TASK: FIX NATURAL RESPONSE + ANSWER PLANNER + CHAT UI

## MỤC TIÊU

Chatbot DHV hiện tại đã có thể truy xuất được dữ liệu, nhưng câu trả lời và giao diện vẫn có các vấn đề:

1. Câu trả lời còn máy móc, giống đọc dữ liệu từ database.
2. Câu hỏi ngắn nhưng đôi khi trả lời dài.
3. Câu hỏi tổng quan chưa được tổ chức thành các mục dễ đọc.
4. Câu trả lời thường xuất hiện các câu thừa như:
   - "Đây là các thông tin được công bố chính thức..."
   - "Theo dữ liệu tuyển sinh..."
   - các câu xác nhận nguồn lặp lại không cần thiết.
5. Bot chưa thay đổi cách trình bày theo từng loại câu hỏi.
6. "Gợi ý tiếp theo" hiện tại giống danh sách FAQ, chưa giống chatbot.
7. Giao diện user message và assistant message chưa tạo cảm giác hội thoại.
8. Nội dung assistant đang giống text đặt trực tiếp trên nền thay vì chat bubble/card.
9. User message đang chiếm gần toàn bộ chiều ngang.
10. Cần giữ nguyên tính chính xác của RAG, không được làm đẹp câu chữ bằng cách tự thêm dữ kiện.
11. UI KHÔNG hiển thị URL, source card, metadata retrieval hoặc internal RAG information.

**ĐÂY KHÔNG PHẢI TASK CHỈ CHỈNH PROMPT.**

Phải kiểm tra và sửa cả:
- query analysis
- answer planning
- generation
- validation
- related questions
- Streamlit UI rendering
- regression tests

---

## PHASE 1 — AUDIT CODE HIỆN TẠI

Trước khi sửa bất kỳ code nào, đọc toàn bộ các file liên quan, tối thiểu:

```text
src/chatbot/chat_service.py
src/chatbot/rag_chain.py
src/chatbot/query_analysis.py
src/chatbot/evidence.py
src/chatbot/output_validator.py
src/chatbot/intent_classifier.py
src/chatbot/scope_guard.py
src/prompts/rag_prompt.py
app.py
```

Ngoài ra kiểm tra tất cả helper/module hiện đang tham gia vào:
- router
- answer generation
- catalog response
- score response
- conversation state
- suggested questions

**KHÔNG tạo module mới ngay lập tức.**

Trước tiên xác định:
1. Question type hiện được xác định ở đâu?
2. Intent hiện được xác định ở đâu?
3. Evidence được đưa vào LLM như thế nào?
4. Prompt hiện tại ép output theo format nào?
5. Có code deterministic response hiện tại không?
6. Có logic trả lời catalog riêng không?
7. Related questions được sinh ở đâu?
8. Streamlit hiện render user/assistant message như thế nào?
9. Validator hiện kiểm tra factual grounding như thế nào?

Tạo report:

```text
reports/ANSWER_UI_AUDIT.md
```

Report phải chỉ rõ:
- current flow
- file/function chịu trách nhiệm
- root cause của response máy móc
- root cause của UI chưa đẹp
- phần nào tái sử dụng được
- phần nào cần refactor

---

## PHASE 2 — CHUẨN HÓA ANSWER MODES

Chatbot phải xác định loại câu trả lời trước khi gọi LLM.

Tạo hoặc hoàn thiện Answer Planner.

Không nhất thiết phải tạo file mới nếu project hiện tại đã có nơi phù hợp.

Phải hỗ trợ tối thiểu các response mode:

```text
DIRECT_SHORT
EXPLANATION
OVERVIEW
CATALOG_LIST
COMPARISON
TABLE
STEP_BY_STEP
RECOMMENDATION
CLARIFICATION
NO_DATA
OUT_OF_SCOPE
```

Ví dụ:

```text
User: Học phí học kỳ 1 bao nhiêu?
=> DIRECT_SHORT
```

Kỳ vọng:
- trả con số chính trước
- giải thích breakdown ngắn nếu cần
- không viết đoạn văn dài

```text
User: Thông tin trường
=> OVERVIEW
```

Kỳ vọng:
- giới thiệu ngắn
- thông tin quan trọng chia thành các mục/bullet
- không dump toàn bộ knowledge base

```text
User: CNTT có những chuyên ngành nào?
=> CATALOG_LIST
```

Kỳ vọng:
- nói số lượng
- liệt kê tên
- không trả tất cả ngành của trường

```text
User: So sánh CNTT và Kỹ thuật máy tính
=> COMPARISON
```

Kỳ vọng:
- bảng nếu dữ liệu hỗ trợ
- sau bảng có nhận xét ngắn
- không tự suy đoán nghề nghiệp nếu evidence không có

```text
User: Tôi 720 điểm ĐGNL, thích làm video thì nên học gì?
=> RECOMMENDATION
```

Kỳ vọng:
- tách facts đã xác minh
- deterministic logic kiểm tra điều kiện
- chỉ tư vấn trong phạm vi DHV
- không khẳng định chắc chắn trúng tuyển
- không tự thêm trường khác

---

## PHASE 3 — ANSWER PLAN TRƯỚC KHI GENERATE

Trước khi LLM viết câu cuối cùng, hệ thống nên có cấu trúc nội bộ tương đương:

```json
{
  "mode": "OVERVIEW",
  "intent": "...",
  "entities": [],
  "facts": [],
  "sections": [],
  "constraints": [],
  "suggested_topics": []
}
```

Tên field có thể khác tùy kiến trúc hiện tại.

Không bắt buộc dùng đúng JSON trên.

Mục tiêu:

**LLM KHÔNG được tự quyết định facts.**

Python / retrieval / evidence layer quyết định:
- facts nào được phép dùng
- con số nào đúng
- ngành nào đúng
- danh sách nào đúng
- count nào đúng
- section nào nên xuất hiện

LLM chỉ làm:
- viết câu tự nhiên
- nối ý
- thay đổi cách diễn đạt
- giữ đúng nội dung evidence

---

## PHASE 4 — SỬA NATURAL RESPONSE

Prompt/generation phải tuân theo nguyên tắc:

> LOCK FACTS, NOT WORDING.

Không hard-code toàn bộ câu trả lời.

Không tạo FAQ template cố định cho từng câu.

Cho phép LLM thay đổi cách diễn đạt tự nhiên nhưng:
- không thêm fact ngoài evidence
- không đổi số
- không đổi ngành
- không đổi điều kiện
- không suy diễn
- không tự tạo deadline
- không tự tạo địa chỉ
- không tự tạo học bổng
- không tự tạo tổ hợp xét tuyển

Câu trả lời nên giống một người tư vấn tuyển sinh.

Ví dụ hiện tại KHÔNG tốt:

```text
Trường Đại học Hùng Vương TP.HCM (DHV) được thành lập từ năm 1995 và đã tồn tại đến nay.
```

Sửa cách diễn đạt tự nhiên hơn, ví dụ:

```text
Trường Đại học Hùng Vương TP.HCM (DHV) được thành lập năm 1995, với định hướng đào tạo gắn với thực hành.
```

Lưu ý: Đây chỉ là ví dụ style, **KHÔNG hard-code câu này**.

Không lặp những câu kiểu:

```text
Đây là các thông tin được công bố chính thức từ Trường Đại học Hùng Vương TP.HCM.
```

ở cuối mọi câu trả lời.

Chỉ nói về độ chắc chắn của nguồn khi:
- người dùng hỏi nguồn
- dữ liệu có xung đột
- dữ liệu chưa xác minh hoàn toàn
- validator yêu cầu cảnh báo

---

## PHASE 5 — RESPONSE LENGTH

Phải điều chỉnh độ dài theo câu hỏi.

Câu hỏi đơn giản:
- 1–4 câu là đủ.

Ví dụ:

```text
Học phí HK1 bao nhiêu?
```

Không cần:
- giới thiệu trường
- giải thích RAG
- nguồn
- kết luận dài

Câu hỏi tổng quan:
- có thể dài hơn nhưng chia mục.

Câu hỏi nhiều ý:
- chia section.

Không được trả mọi câu hỏi theo cùng một template.

---

## PHASE 6 — FORMAT OUTPUT

Không bắt buộc tất cả câu trả lời đều dùng Markdown giống nhau.

Planner quyết định format.

```text
DIRECT_SHORT:
text ngắn.

CATALOG_LIST:
intro + bullet list.

COMPARISON:
table + explanation.

OVERVIEW:
heading nhỏ + bullet/section.

STEP_BY_STEP:
numbered steps.

RECOMMENDATION:
facts → analysis → suggestion → caveat nếu cần.

CLARIFICATION:
1 câu hỏi làm rõ, không dump dữ liệu.

NO_DATA:
nói rõ chưa có dữ liệu xác minh.

OUT_OF_SCOPE:
từ chối ngắn và hướng user về tuyển sinh DHV.
```

---

## PHASE 7 — THÔNG TIN TRƯỜNG

Fix riêng query như:

```text
thông tin trường
thông tin DHV
giới thiệu DHV
trường DHV là trường gì
giới thiệu Trường Đại học Hùng Vương TP.HCM
```

Phải route đúng `SCHOOL_INFO` / `SCHOOL_OVERVIEW` tương đương.

Không trả một paragraph dài.

Nếu evidence hỗ trợ, cấu trúc ưu tiên:
- giới thiệu ngắn
- năm thành lập
- định hướng
- thông tin tuyển sinh hiện tại
- cơ sở/liên hệ nếu user hỏi hoặc overview phù hợp

Không dump mọi địa chỉ nếu câu hỏi chỉ hỏi "trường là gì".

Không tự gọi hệ thống là chatbot chính thức của DHV nếu chưa được ủy quyền.

---

## PHASE 8 — HỌC BỔNG

Fix style cho các query như:

```text
Điều kiện nhận học bổng tuyển sinh
Học bổng DHV 2026
Tôi được học bổng nào?
```

Đối với hỏi chính sách:
- intro ngắn
- từng điều kiện tách rõ
- số liệu giữ nguyên evidence
- tránh paragraph dài

Đối với hỏi "tôi được học bổng nào":
- lấy điểm user cung cấp
- deterministic comparison nếu rule đủ rõ
- tuyệt đối không để LLM tự tính
- nếu thiếu dữ liệu cần thiết → hỏi lại

---

## PHASE 9 — RELATED QUESTIONS

"Gợi ý tiếp theo" không được là danh sách FAQ cố định.

Sinh 2–3 câu liên quan trực tiếp đến:
- current intent
- current entity
- answer vừa trả

Ví dụ user hỏi học bổng:

```text
Tôi có đủ điều kiện nhận học bổng không?
Học bổng áp dụng cho ngành CNTT thế nào?
Học phí sau khi áp dụng học bổng là bao nhiêu?
```

Không bắt buộc đúng chính xác wording này.

Không gợi ý câu ngoài dữ liệu.

Không tạo 5–10 câu.

---

## PHASE 10 — UI CHAT MESSAGE

Sửa Streamlit UI.

Mục tiêu nhìn giống một ứng dụng chat hiện đại hơn.

### USER MESSAGE

- căn bên phải
- bubble chỉ rộng theo nội dung
- max-width khoảng 65–75%
- padding hợp lý
- border-radius rõ
- không kéo full width
- avatar/icon nhỏ
- khoảng cách trên dưới đồng đều

### ASSISTANT MESSAGE

- căn bên trái
- max-width khoảng 75–85%
- có container/card/bubble nhẹ
- text dễ đọc
- line-height thoáng
- Markdown table hiển thị không vỡ
- bullet có spacing hợp lý
- heading có hierarchy rõ

Không copy pixel-perfect UI của chatbot trường khác.

Không copy:
- logo
- màu thương hiệu của trường khác
- avatar
- phrase
- CSS
- layout pixel-perfect

Chỉ tham khảo UX.

---

## PHASE 11 — RELATED QUESTION CHIPS

Thay danh sách bullet:

```text
Gợi ý tiếp theo
• ...
• ...
```

bằng UI giống button/chip.

Ví dụ concept:

```text
[ Học phí DHV 2026 ]
[ Hồ sơ xét tuyển ]
[ Học bổng ]
```

Khi click:
- đưa nội dung câu hỏi tương ứng vào flow chatbot
hoặc
- trigger cùng logic như user submit message

Không bypass ChatService/RAG.

Không hard-code một bộ chip giống nhau cho mọi response.

---

## PHASE 12 — SOURCE DISPLAY

TUYỆT ĐỐI KHÔNG hiển thị trên UI:
- source URL
- source cards
- "Nguồn chính thức"
- metadata
- chunk id
- retrieval score
- evidence id
- RAG context

Backend vẫn giữ:

```python
{
    "answer": ...,
    "sources": ...,
    "status": ...
}
```

để:
- test
- audit
- provenance

UI chỉ render những gì cần cho người dùng.

---

## PHASE 13 — KHÔNG PHÁ VỠ DATA/FUNCTIONAL LOGIC

Không thay đổi factual source-of-truth.

Phải giữ các rule hiện có:

- Truyền thông đa phương tiện là chương trình thuộc CNTT nếu current verified KB quy định như vậy.
- Không biến nó thành ngành độc lập.
- Không import tổ hợp 2025 vào 2026 nếu chưa xác minh.
- Không dùng admission score thay cho application threshold.
- Không trả threshold học bạ ngành Luật bằng 18 nếu dữ liệu 04/07 chưa xác nhận.
- Không dự đoán trúng tuyển.
- Không đưa trường khác vào tư vấn DHV.
- Không dùng screenshot chatbot trường khác làm knowledge base.

---

## PHASE 14 — VALIDATOR

Sau generation phải kiểm tra:

1. Numbers in answer có nằm trong evidence không.
2. Major/program names có đúng không.
3. Answer có trả đúng intent không.
4. Answer có dùng entity ngoài DHV không.
5. Answer có trả nhầm score type không.
6. Answer có thêm unsupported factual statement không.

Nếu generation fail grounding:

Không đưa thẳng câu sai lên UI.

Phải:
- regenerate có giới hạn
hoặc
- fallback deterministic
hoặc
- `NO_DATA` / `CLARIFICATION` tùy trường hợp.

---

## PHASE 15 — TEST CASES BẮT BUỘC

Thêm regression tests cho tối thiểu các query:

1. `hello`
   - greeting tự nhiên
   - không retrieval dài

2. `bạn tên gì`
   - giới thiệu chatbot phù hợp
   - không nói là chatbot chính thức của DHV nếu chưa được ủy quyền

3. `đây có phải chatbot tuyển sinh của trường không`
   - nói rõ đây là hệ thống/chatbot hỗ trợ trong phạm vi dự án, dựa trên dữ liệu DHV đã thu thập và kiểm chứng

4. `thông tin trường`
   - OVERVIEW
   - không paragraph dài máy móc
   - không dump toàn KB

5. `DHV có bao nhiêu ngành`
   - trả đúng số ngành từ verified data

6. `CNTT có những chuyên ngành nào`
   - chỉ các chương trình thuộc CNTT

7. `CNTT có mấy chuyên ngành`
   - count đúng

8. `Học phí học kỳ 1 bao nhiêu`
   - DIRECT_SHORT

9. `Điều kiện nhận học bổng tuyển sinh`
   - structured conditions

10. `720 điểm ĐGNL có đủ điều kiện nộp hồ sơ không`
    - deterministic comparison với verified threshold
    - không khẳng định trúng tuyển

11. `điểm xét tuyển bằng học bạ của ngành luật bao nhiêu`
    - không nhầm sang công thức tính điểm
    - không tự trả 18 nếu chưa verified

12. `Cách tính điểm xét tuyển học bạ`
    - formula/method
    - không trả threshold

13. `điểm chuẩn ngành luật`
    - admission-score intent

14. `so sánh CNTT và Kỹ thuật máy tính`
    - comparison format

15. `tôi thích dựng video thì nên học ngành nào`
    - chỉ recommendation dựa trên verified DHV evidence
    - không hallucinate

16. `thế ngành còn lại thì sao?`
    - sau một conversation phù hợp
    - conversation state resolve được entity

17. `Hôm nay giá vàng bao nhiêu`
    - OUT_OF_SCOPE

18. `Môn A00 của CNTT năm 2026 là gì`
    - nếu KB chưa có verified tổ hợp: NO_DATA
    - không dùng dữ liệu 2025

---

## PHASE 16 — UI MANUAL TEST

Chạy Streamlit và kiểm tra thủ công ít nhất:
- desktop width
- chat dài nhiều lượt
- bullet list
- Markdown table
- related question chips
- long assistant response
- short assistant response
- user message dài
- error/fallback state

Chụp screenshot sau khi sửa.

Đặt tại:

```text
reports/screenshots/
```

---

## PHASE 17 — TESTING WORKFLOW

Bắt buộc thực hiện theo thứ tự:

```text
1. Run baseline tests BEFORE change.
2. Ghi kết quả baseline.
3. Implement.
4. Run targeted tests.
5. Run full regression suite.
6. Launch Streamlit.
7. Test manually.
8. Chụp screenshot.
9. Viết report.
```

Không được báo PASS chỉ vì app chạy được.

---

## PHASE 18 — ACCEPTANCE CRITERIA

Task chỉ được PASS khi:
- retrieval cũ không bị phá
- factual regression tests pass
- response style thay đổi theo question type
- simple question không bị over-answer
- overview có cấu trúc
- catalog đúng parent/child relation
- score intent không bị nhầm
- recommendation không hallucinate
- UI phân biệt rõ user và assistant
- user bubble không full-width
- assistant answer dễ đọc hơn
- related questions hiển thị dạng chip/button
- related questions liên quan context
- UI không hiển thị source URL/card
- backend vẫn giữ provenance
- conversation state vẫn hoạt động
- full regression pass

---

## PHASE 19 — FINAL REPORT

Tạo:

```text
reports/TASK_RESPONSE_UI_FIX_REPORT.md
```

Report phải có:

1. Root causes.
2. Files changed.
3. Functions changed.
4. Architecture before.
5. Architecture after.
6. Answer modes implemented.
7. UI changes.
8. Related-question changes.
9. Tests added.
10. Baseline result.
11. Final regression result.
12. Manual test result.
13. Remaining limitations.
14. Screenshot paths.

Cuối report ghi một trong hai:

```text
STATUS: PASS
```

hoặc

```text
STATUS: FAIL
```

Không ghi PASS nếu còn lỗi factual hoặc regression.

---

## KIẾN TRÚC ĐÍCH

Luồng sau khi sửa phải gần tương đương:

```text
User
↓
Input normalization
↓
Intent + Entity + Question Type
↓
Conversation State
↓
Router
↓
Retrieval / Deterministic Logic
↓
Evidence
↓
Answer Planner
↓
LLM natural-language realization
↓
Grounding / Relevance Validator
↓
ChatService
↓
UI Renderer
↓
User
```

---

## NGUYÊN TẮC CUỐI CÙNG

### FACTS
Do verified data + deterministic logic kiểm soát.

### LLM
Chỉ diễn đạt tự nhiên.

### UI
Chỉ trình bày kết quả.

Không để LLM:
- tự tính toán admission rule
- tự tạo facts
- tự quyết định source-of-truth
- tự thêm ngành
- tự thêm điều kiện
- tự tạo thông tin DHV không có evidence.
