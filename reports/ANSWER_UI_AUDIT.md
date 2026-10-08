# Answer + UI audit

## Scope

Audit cho `TASK_FIX_NATURAL_RESPONSE_ANSWER_PLANNER_UI.md`. Không đưa ảnh trong
`reference_images/` hoặc dữ liệu ngoài corpus vào hệ thống; tài liệu PDF tổng quan
chỉ được dùng để đối chiếu nguyên tắc router → evidence → planner → realization →
validator → UI.

## Current flow

```text
app.py
  -> ChatService.ask / ask_chatbot
  -> rag_chain.ask_chatbot
  -> query_analysis.analyze_question + route_question
  -> retriever.retrieve_with_audit
  -> evidence.select_evidence_documents + build_evidence
  -> deterministic score/catalog helpers
  -> answer_planner.plan_answer
  -> rag_prompt.build_rag_prompt
  -> LocalLLM.generate
  -> output_validator.validate_model_answer (retry tối đa một lần)
  -> ChatService payload
  -> Streamlit chat_message renderer
```

### Responsibilities

| Concern | Current owner | Audit result |
| --- | --- | --- |
| Normalization, intent, entity, state | `query_analysis.py` | Có rule + classifier; state bị giới hạn trong slots. |
| Router/category/query | `query_analysis.route_question` | Có tách score/catalog/multi-issue nhưng thứ tự rule còn bắt nhầm. |
| Evidence selection | `evidence.py` | Có metadata/entity/category filtering trước prompt; có structured facts/relations. |
| Catalog response | `rag_chain._evidence_catalog_answer` | Deterministic, giữ parent program và count. |
| Score logic | `query_analysis.deterministic_score_*` | Deterministic cho threshold/comparison; giữ tách score type. |
| Answer planning | `answer_planner.py` | Đã có đủ 10 mode, nhưng chưa gắn chặt với response realization/rendering. |
| Prompt/generation | `rag_prompt.py`, `rag_chain.py` | Prompt có plan/evidence; model vẫn có thể echo wrapper hoặc mở đầu máy móc. |
| Validation | `output_validator.py` | Kiểm grounding/entity/year/score/parent; chưa kiểm tra rõ chất lượng hình thức/độ dài. |
| Related questions | `answer_planner.related_questions_for` | Có 2–3 gợi ý theo intent/entity, nhưng UI còn render list tĩnh. |
| Chat history/UI | `app.py` | Có `st.chat_message`, strip URL và giữ state; user bubble chưa được giới hạn/căn chỉnh, chip chưa trigger flow. |

## Reproduction baseline

Lệnh chuẩn của repository:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Kết quả baseline: `Ran 116 tests`, `111 ok`, `1 skipped`, `5 errors` do sandbox
Windows không cho các test ingestion tạo/dọn thư mục tạm trong `TEMP`; không có
failure assertion ở các test logic hiện có. Khi chạy trong môi trường Windows có
quyền thư mục tạm bình thường, cần chạy lại full suite để xác nhận môi trường.

Các case audit bằng retriever/LLM double hiện tại:

| Query | Current | Expected |
| --- | --- | --- |
| `đây có phải chatbot tuyển sinh của trường không` | `HOI_CO_SO_LIEN_HE`, trả dữ liệu cơ sở | `SYSTEM_IDENTITY`, deterministic, không retrieval |
| `thông tin trường` | Có thể đi vào retrieval nhưng với double echo có thể thành `NO_DATA` | `SCHOOL_INFO` + `OVERVIEW`, các mục ngắn |
| `Học phí học kỳ 1 bao nhiêu` | Simple query có thể thành `NO_DATA` nếu model double echo wrapper/caveat | `DIRECT_SHORT`, học phí trước, không dump context |
| `720 điểm ĐGNL có đủ điều kiện nộp hồ sơ không` | `HOI_HO_SO`, không chạy score engine | Score comparison deterministic với ngưỡng verified; không kết luận đậu |
| `tôi thích dựng video thì nên học ngành nào` | Interest extractor ăn cả phần “thì nên học ngành nào” | Interest ngắn, recommendation có điều kiện từ evidence |
| `Môn A00 của CNTT năm 2026 là gì` | `HOI_NGANH`, có thể trả ngưỡng | `NO_DATA` nếu tổ hợp 2026 chưa verified |
| Related questions | Markdown bullet | Native pills/button, 2–3 câu theo context, click qua ChatService |

## Root causes

1. `query_analysis._is_system_identity_request` chỉ nhận marker “chatbot chính
   thức”/tương tự, không nhận câu hỏi về chatbot tuyển sinh của trường nếu không
   có chữ “chính thức”; rule liên hệ nằm trước school/identity fallback.
2. Rule “hồ sơ” chạy trước khi xử lý điểm cá nhân; cụm “nộp hồ sơ” làm mất tín hiệu
   ĐGNL. `_extract_scores` lưu điểm đơn là `unspecified`, nên score comparison
   không có method để so sánh.
3. Tổ hợp dạng `A00` chưa được coi là yêu cầu phương thức/tổ hợp; câu hỏi bị route
   như hỏi ngành và có thể nhận các facts điểm sàn không liên quan.
4. `_extract_interest` dùng lookahead quá rộng nên lưu cả phần mệnh đề tư vấn vào
   slot `interest`; planner/generator vì thế nhận tín hiệu không tự nhiên.
5. Prompt đã có ANSWER_PLAN nhưng model vẫn được phép trả lại context wrapper và
   các nhãn “Dữ liệu tuyển sinh”; validator chủ yếu kiểm tính đúng, chưa có lớp
   lọc wrapper/độ ngắn hoặc realization fallback theo mode.
6. `_evidence_catalog_answer` chỉ xử lý catalog. School overview, short facts và
   scholarship conditions vẫn phụ thuộc model tự tổ chức văn bản.
7. `app.py` dùng chat container nhưng related questions được in bằng Markdown list;
   message content không có lớp trình bày riêng để user bubble co theo nội dung và
   assistant bubble/card dễ đọc.

## Reusable parts

- `AnswerPlan`/`plan_answer` và trace contract.
- Deterministic system answers, catalog formatter, score engines.
- Evidence Selection, structured facts, provenance backend và validator hiện có.
- `ChatService` API và session-only `ConversationState`.
- URL/source sanitization ở boundary UI.

## Minimal refactor needed

- Mở rộng rule phân loại identity, personal-score và unknown admission combination;
  không thêm module trùng chức năng.
- Chuẩn hóa score entity `dgnl` từ câu có “điểm ĐGNL”, và route personal threshold
  comparison vào bounded counselling/score branch.
- Làm interest extraction theo mệnh đề/ngữ cảnh tự nhiên.
- Bổ sung realization hậu xử lý/fallback theo `AnswerPlan`: short fact, overview,
  scholarship conditions và comparison có cấu trúc; facts vẫn do evidence/
  deterministic layer kiểm soát.
- Đổi related renderer sang pills với key ổn định, trả selected query về một điểm
  xử lý chung để không bypass ChatService.
- Thêm style độc lập cho chat bubbles, không dùng logo/avatar/màu/copy/layout của
  chatbot tham khảo; giữ UI không render source URL/card/metadata.

## Invariants to preserve

- Chỉ evidence verified DHV 2026; không trộn formula/threshold/admission/
  supplementary/scholarship.
- Program vẫn là child của major; list/count/filter bằng Python.
- LLM không tính điểm, không khẳng định đậu-rớt, không tự tạo fact/URL.
- Greeting/identity/scope không retrieval; provenance chỉ ở backend.
- Full regression phải được chạy lại sau targeted tests.
