# TASK: BẮT BUỘC OCR CHO TOÀN BỘ RAW PDF TRƯỚC KHI ĐƯA VÀO RAG

## MỤC TIÊU

Cập nhật pipeline ingestion của project Chatbot tuyển sinh Trường Đại học Hùng Vương TP. Hồ Chí Minh để:

- MỌI file RAW PDF đều phải đi qua OCR.
- OCR không còn là fallback.
- Text chính dùng để tạo processed data phải lấy từ kết quả OCR.
- Sau OCR mới thực hiện clean text, tạo Markdown + metadata, chunk, embedding và đưa vào ChromaDB.
- Không làm hỏng cấu trúc dữ liệu, metadata, retrieval, validator hoặc các regression test hiện có.

> Lưu ý: thuật ngữ đúng là **OCR (Optical Character Recognition)**.

---

## 1. KIẾN TRÚC CŨ

Luồng hiện tại có thể đang gần như:

```text
RAW PDF
↓
pypdf extract text
↓
clean / normalize
↓
processed Markdown
↓
split chunk
↓
embedding
↓
ChromaDB
```

Pipeline này phải được thay đổi.

---

## 2. KIẾN TRÚC MỚI BẮT BUỘC

```text
RAW PDF
↓
đọc từng trang
↓
render từng trang PDF thành ảnh
↓
OCR từng trang
↓
thu text OCR theo đúng thứ tự trang
↓
normalize / clean
↓
processed Markdown + YAML metadata
↓
split chunk
↓
embedding
↓
ChromaDB
↓
retriever
↓
RAG
```

Tức là:

```text
PDF có text thật
→ vẫn OCR

PDF scan
→ OCR

PDF ảnh
→ OCR

PDF vừa text vừa ảnh
→ OCR
```

Không được bỏ qua OCR vì PDF có sẵn text layer.

---

## 3. AUDIT CODE TRƯỚC KHI SỬA

Đọc tối thiểu:

```text
src/ingestion/loader.py
src/ingestion/prepare_processed_from_raw.py
src/ingestion/build_vector_db.py
src/ingestion/splitter.py
src/ingestion/embeddings.py
src/ingestion/chroma_lifecycle.py
src/ingestion/rebuild_smoke_test.py
src/ingestion/smoke_test_vector_db.py
requirements.txt
```

Ngoài ra tìm toàn project các từ:

```text
pypdf
PdfReader
extract_text
loader
pdf
ocr
tesseract
pymupdf
pdf2image
poppler
easyocr
paddleocr
```

Phải xác định:

1. RAW PDF hiện được đọc ở đâu.
2. Hàm nào đang extract text.
3. Processed Markdown được sinh ở đâu.
4. Metadata được gắn ở đâu.
5. Số trang/source/page hiện đang được lưu thế nào.
6. Test nào phụ thuộc text extraction cũ.
7. Có code nào đang gọi trực tiếp `pypdf.extract_text()` để tạo nội dung RAG hay không.

Tạo:

```text
reports/OCR_PIPELINE_AUDIT.md
```

---

## 4. YÊU CẦU OCR

### 4.1 Mọi trang phải được OCR

```text
PDF
↓
page 1 → image → OCR
page 2 → image → OCR
page 3 → image → OCR
...
↓
ghép text theo thứ tự trang
```

Không được dùng logic:

```text
if PDF có text:
    dùng extract_text()
else:
    OCR
```

Trong task này OCR là mandatory.

### 4.2 Ngôn ngữ

OCR phải hỗ trợ tối thiểu:

```text
Vietnamese
English
```

Vì dữ liệu có thể chứa:
- tiếng Việt
- tên ngành tiếng Anh
- acronym
- mã ngành
- URL
- email
- hotline
- số liệu

Nếu engine hỗ trợ, cấu hình phù hợp cho `vie + eng`.

---

## 5. CHỌN OCR ENGINE

Agent phải audit môi trường project và chọn giải pháp local phù hợp.

Ưu tiên:

1. Chạy local.
2. Không gửi dữ liệu ra dịch vụ OCR bên ngoài.
3. Hỗ trợ tiếng Việt.
4. Chạy được trên Windows.
5. Tích hợp Python dễ.
6. Xử lý PDF nhiều trang.
7. Có hướng dẫn cài đặt rõ cho thành viên nhóm.

Có thể cân nhắc:

```text
Tesseract OCR
PaddleOCR
EasyOCR
```

Chỉ chọn một engine chính nếu không có lý do cần nhiều engine.

---

## 6. RENDER PDF → IMAGE

Trước OCR phải render từng page sang ảnh đủ chất lượng.

Yêu cầu:

- không render quá thấp làm OCR sai
- không render quá cao gây tốn RAM không cần thiết
- giữ đúng thứ tự trang
- cleanup temporary images sau xử lý
- không để file temp rác trong project
- test trên Windows

---

## 7. QUẢN LÝ FILE TEMP

Không commit ảnh OCR trung gian.

Ưu tiên dùng:

```text
system temp directory
```

Luồng:

```text
PDF
↓
temporary page images
↓
OCR
↓
delete temporary images
```

Phải cleanup cả khi lỗi.

---

## 8. KHÔNG DÙNG TEXT TỪ PYPDF LÀM TEXT CHÍNH

Sau khi task hoàn thành, `pypdf` nếu còn dùng chỉ nên phục vụ:

```text
- đọc metadata
- kiểm tra số trang
- validate PDF
- cross-check kỹ thuật
```

Không dùng:

```python
page.extract_text()
```

làm text chính đưa vào processed/RAG.

Text chính phải là:

```text
OCR output
```

---

## 9. PRESERVE PAGE BOUNDARY

Không ghép toàn bộ OCR thành một chuỗi mất dấu trang.

Processed layer nên giữ được page boundary hoặc metadata page tương đương để phục vụ:

- audit
- debugging
- evidence trace
- kiểm tra lỗi OCR theo trang

Không cần hiển thị page number cho user cuối.

---

## 10. TEXT NORMALIZATION SAU OCR

Được phép:

- trim whitespace
- gộp khoảng trắng thừa
- sửa line break bất thường
- loại ký tự control
- chuẩn hóa nhiều dòng trống
- giữ Unicode tiếng Việt
- giữ bullet nếu nhận diện được

Không được tự ý:

- sửa số liệu bằng suy đoán
- đổi mã ngành
- đổi điểm
- đổi URL
- đổi ngày tháng
- đổi tên ngành vì "có vẻ OCR sai"

Nếu nghi OCR sai factual field:
- ghi log
- đánh dấu review
- không tự sửa nếu không có rule deterministic chắc chắn

---

## 11. OCR QUALITY CHECK

Phải phát hiện tối thiểu:

- page OCR trả rỗng
- text quá ngắn bất thường
- tỷ lệ ký tự lạ quá cao
- PDF có trang nhưng OCR không lấy được text

Nếu OCR thất bại:

```text
không âm thầm bỏ trang
↓
ghi warning/error
↓
đưa file/page vào report
```

Tạo:

```text
reports/OCR_QUALITY_REPORT.md
```

Ghi:
- file
- page
- trạng thái
- số ký tự OCR
- warning nếu có

---

## 12. BẢNG VÀ DỮ LIỆU CẤU TRÚC

Các PDF tuyển sinh có thể chứa bảng như:

```text
ngành
mã ngành
điểm sàn
học phí
học bổng
phương thức
```

OCR phải cố giữ thứ tự đọc đủ để downstream hiểu.

Đặc biệt không để các số như:

```text
15 / 18 / 600
```

bị gán nhầm sang ngành khác.

---

## 13. URL / EMAIL / SỐ ĐIỆN THOẠI

Sau OCR có thể dùng regex validation để flag dữ liệu bất thường.

Cần chú ý các pattern:

```text
https://...
@...
028...
7480201
2026
15
18
600
```

Không được silently biến URL thành giá trị khác.

---

## 14. PIPELINE PROCESSED

Sau OCR:

```text
OCR text
↓
normalize
↓
processed Markdown
↓
YAML metadata
```

Giữ convention hiện tại.

Có thể bổ sung:

```yaml
extraction_method: ocr
```

nếu không phá parser/test hiện có.

---

## 15. RAW VẪN LÀ SOURCE OF TRUTH

Không chỉnh tay `data/processed` để né lỗi OCR.

Luồng đúng:

```text
data/raw/*.pdf
↓
OCR pipeline
↓
data/processed/*.md
```

Nếu OCR output sai:

```text
fix OCR pipeline / preprocessing
↓
regenerate
```

---

## 16. REQUIREMENTS

Cập nhật:

```text
requirements.txt
```

Nếu engine cần dependency ngoài Python thì cập nhật README rõ ràng cho Windows:

- cần cài gì
- kiểm tra cài thành công thế nào
- command test
- PATH/environment nếu cần

---

## 17. README

Cập nhật README phần ingestion thành:

```text
RAW PDF
↓
OCR toàn bộ tài liệu
↓
Text normalization
↓
Processed Markdown
↓
Chunk
↓
Embedding
↓
ChromaDB
```

Ghi rõ:

> Project sử dụng OCR cho toàn bộ RAW PDF, không phụ thuộc vào việc PDF có text layer hay không.

---

## 18. SCRIPT BEHAVIOR

Script hiện có như:

```text
prepare_processed_from_raw.py
```

nên tiếp tục là entry point nếu phù hợp.

Ví dụ:

```bash
python -m src.ingestion.prepare_processed_from_raw
```

phải tự thực hiện:

```text
find RAW PDFs
↓
OCR all PDFs
↓
generate processed
```

Không yêu cầu thành viên nhóm OCR thủ công từng file.

---

## 19. PROGRESS LOG

Vì OCR chậm hơn extract text trực tiếp, script phải có log tiến trình.

Ví dụ:

```text
[1/14] hoc_phi_2026.pdf
  page 1/2 OCR...
  page 2/2 OCR...
  OK
```

---

## 20. ERROR HANDLING

Nếu 1 PDF fail OCR:

- báo file lỗi
- ghi exception
- không đánh dấu processed hoàn tất cho file đó
- cuối pipeline báo summary

Ví dụ:

```text
OCR SUMMARY
PDF total: 14
Success: 13
Failed: 1
```

---

## 21. CACHE OCR — TÙY CHỌN

Có thể implement cache dựa trên:

```text
file hash
modified timestamp
OCR version
```

Nếu dùng cache:
- phải có force rebuild
- không để cache dùng dữ liệu cũ sau khi RAW thay đổi

Nếu chưa cần thì bỏ qua ở phiên bản đầu.

---

## 22. TEST BẮT BUỘC

### Test 1 — PDF có text layer
Expected:

```text
vẫn OCR
```

### Test 2 — PDF scan
Expected:
- OCR đọc được nội dung

### Test 3 — Multi-page PDF
Expected:
- đủ tất cả trang
- đúng thứ tự

### Test 4 — Vietnamese text
Expected:
- giữ dấu tiếng Việt ở mức chấp nhận được

### Test 5 — Numbers

Kiểm tra:

```text
15
18
600
7480201
2026
12.500.000
```

### Test 6 — URL

Kiểm tra:

```text
https://dhv.edu.vn/
https://tuyensinh.dhv.edu.vn/
```

### Test 7 — OCR empty page
Expected:
- warning
- log
- không silently bỏ qua

### Test 8 — Temp cleanup
Expected:
- không còn page image rác

---

## 23. FULL DATA REBUILD

Sau khi implement:

```text
clear/regenerate processed
↓
OCR ALL RAW PDFs
↓
generate processed
↓
split
↓
embedding
↓
rebuild ChromaDB
↓
smoke test
↓
full regression
```

---

## 24. KIỂM TRA DỮ LIỆU QUAN TRỌNG SAU OCR

Audit thủ công:

- tên 20 ngành
- mã ngành
- 15 / 18 / 600
- điểm chuẩn
- học phí
- học bổng
- deadline
- địa chỉ
- hotline
- website
- quan hệ CNTT → các chương trình

Đặc biệt:

```text
Truyền thông đa phương tiện
```

phải vẫn đúng là chương trình thuộc ngành Công nghệ thông tin nếu RAW verified hiện tại quy định như vậy.

---

## 25. RETRIEVAL REGRESSION

Chạy lại:

```text
DHV có bao nhiêu ngành?
CNTT có những chuyên ngành nào?
CNTT có mấy chuyên ngành?
Học phí học kỳ 1 bao nhiêu?
Điều kiện nhận học bổng?
Điểm sàn CNTT?
Điểm chuẩn ngành Luật?
Web tuyển sinh là gì?
Thông tin trường?
```

Không chấp nhận:
- mất chunk
- sai số
- sai mã
- sai parent-child
- retrieval giảm nghiêm trọng

---

## 26. PERFORMANCE REPORT

Report phải ghi:

- tổng số PDF
- tổng số page
- tổng thời gian OCR
- thời gian trung bình/page
- engine dùng
- version
- lỗi/warning

---

## 27. KHÔNG OCR Ở RUNTIME CHAT

OCR chỉ chạy ở ingestion/data preparation.

Không làm:

```text
User hỏi
↓
OCR toàn bộ PDF lại
↓
retrieval
```

Runtime vẫn là:

```text
User query
↓
Retriever
↓
ChromaDB
↓
Evidence
↓
LLM
```

---

## 28. ARCHITECTURE SAU KHI FIX

```text
Official RAW PDF
↓
PDF Renderer
↓
OCR Engine
↓
OCR Quality Check
↓
Text Normalizer
↓
Processed Markdown + Metadata
↓
Text Splitter
↓
Embedding
↓
ChromaDB
↓
Retriever
↓
Evidence
↓
RAG
↓
Chatbot
```

---

## 29. KHÔNG ĐƯỢC PHÁ CÁC RULE HIỆN CÓ

Giữ nguyên:

- RAW mới là PDF.
- Processed là Markdown + metadata.
- Không lấy dữ liệu ngoài nguồn verified.
- Không hallucinate.
- Không import dữ liệu 2025 vào 2026 nếu chưa xác minh.
- Không đổi admission score thành threshold hoặc ngược lại.
- Không hiển thị source card/URL tự động trên UI.
- Backend vẫn giữ provenance.
- Không thu thập PII.

---

## 30. FINAL REPORT

Tạo:

```text
reports/TASK_MANDATORY_OCR_PIPELINE_REPORT.md
```

Report gồm:

1. Pipeline cũ.
2. Pipeline mới.
3. OCR engine được chọn.
4. Lý do chọn.
5. Files changed.
6. Functions added/changed.
7. Dependencies added.
8. Cách cài trên Windows.
9. OCR quality checks.
10. Tổng số PDF/page đã OCR.
11. OCR failures/warnings.
12. Processed rebuild result.
13. Chroma rebuild result.
14. Retrieval regression result.
15. Full test result.
16. Performance.
17. Remaining limitations.

Cuối report:

```text
STATUS: PASS
```

hoặc:

```text
STATUS: FAIL
```

---

## ACCEPTANCE CRITERIA

Task chỉ được PASS khi:

- mọi RAW PDF đều đi qua OCR
- PDF có text layer cũng vẫn OCR
- text chính đưa vào RAG lấy từ OCR
- OCR hỗ trợ tiếng Việt
- processed được regenerate từ OCR output
- metadata không bị mất
- temporary image được cleanup
- OCR lỗi được log
- không silently bỏ page
- ChromaDB rebuild thành công
- retrieval regression pass
- dữ liệu số quan trọng không bị sai do OCR
- parent-child catalog không bị phá
- README có hướng dẫn cài OCR rõ ràng
- thành viên nhóm có thể clone project và chạy lại pipeline
- OCR chỉ chạy lúc ingestion, không chạy mỗi câu hỏi runtime
- full regression pass
