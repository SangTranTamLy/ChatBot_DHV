# QA PDF Clean Extraction Fix Review

## 1. Kết luận

**FAIL CÓ ĐIỀU KIỆN / BLOCKED — chưa chấp nhận patch để tạo và đưa JSON mới vào sử dụng.**

Các test hiện có đều pass, nhưng review độc lập xác nhận ba lỗ hổng cấu trúc chưa được test/fix. Quan trọng nhất, OCR token có confidence thấp hoặc xung đột vẫn có thể đi vào bảng dù đã bị loại khỏi `pages[].text`. Môi trường hiện không có engine OCR khả dụng, vì vậy chưa thể kiểm chứng text trong ảnh trên PDF thật. Không kết luận PDF completeness PASS, không promote JSON và không rebuild Chroma.

## 2. Phạm vi và cách review

Đã đọc trực tiếp diff so với `HEAD` và code hiện tại trong:

- `src/ingestion/pdf_layout.py`
- `src/ingestion/prepare_processed_from_raw.py`
- `tests/test_task_pdf_to_structured_json.py`
- `reports/PDF_CLEAN_EXTRACTION_FIX_REPORT.md`

Đã kiểm tra luồng OCR region/confidence/conflict, OCR-to-table reconstruction, header inheritance, list continuation, coverage test và tình trạng môi trường/dữ liệu. Review không sửa code, RAW PDF, `data/processed`, Chroma hay report QA cũ. Chỉ report này được tạo.

## 3. Findings

### F-01 — HIGH: OCR confidence/conflict gate không áp dụng cho bảng

**Vị trí:** `src/ingestion/pdf_layout.py:912-958`, `src/ingestion/pdf_layout.py:1051-1055`.

`_supplemental_ocr_lines()` loại OCR line confidence thấp và đánh dấu text trùng native nhưng sai số. Tuy nhiên, sau đó `_coordinate_table_from_tokens()` nhận nguyên `ocr_tokens`, không lọc confidence và không nhận danh sách line bị conflict. Vì vậy cùng một OCR token có thể bị loại khỏi `pages[].text` nhưng vẫn được đưa vào `tables[].rows[].cells[]`.

**Reproduction độc lập:** truyền vào table reconstruction một bảng synthetic với confidence của các hàng dữ liệu là `0.20`. Hàm vẫn trả bảng có các giá trị `7480201`, `15`, `7380101`, `18`, `7340301`, `19`; confidence cell thấp nhất vẫn là `0.20`, và không có warning.

**Ảnh hưởng:** cấu trúc bảng có thể chứa số liệu sai/không đủ tin cậy, đi ngược mục tiêu numeric integrity và có nguy cơ downstream tiêu thụ fact không được final-text gate chấp nhận. Test hiện chỉ kiểm tra confidence filtering ở text supplement, chưa kiểm tra table output.

**QA yêu cầu trước khi nhận:** áp dụng confidence/conflict gate cho token/cell khi dựng bảng; nếu không đủ tin cậy thì phải giữ raw OCR/provenance, gắn warning/partial status và không trình bày cell đó như dữ liệu bảng đã xác minh. Bổ sung regression test cho low-confidence và conflicting numeric token qua cả page extraction → table.

### F-02 — MEDIUM: Header continuation có thể gán header của bảng khác

**Vị trí:** `src/ingestion/prepare_processed_from_raw.py:276-355`.

Điều kiện kế thừa chủ yếu là: hai trang liền nhau, mỗi trang có một bảng, số cột bằng nhau, trang trước có header rõ và phần đầu trang sau không khớp một regex hẹp (`Bảng N` hoặc số mục dạng `2.1`). Điều này chưa chứng minh bảng sau thực sự là phần tiếp của bảng trước.

**Reproduction độc lập:** trang 1 có bảng `Major / Code / Score`; trang 2 bắt đầu bằng heading `Scholarship details`, có một bảng 3 cột không header. Hàm vẫn gán ba header của trang 1 cho bảng học bổng trang 2 và ghi `TABLE_HEADER_INHERITED`.

**Ảnh hưởng:** row/cell có thể được gắn sai nghĩa cột dù provenance nói header được kế thừa. Test hiện xác nhận các trường hợp continuation thật, nhưng không có negative test cho bảng mới cùng số cột.

**QA yêu cầu trước khi nhận:** xác nhận continuity bằng tín hiệu nội dung/layout mạnh hơn và không kế thừa khi trang mới có heading/caption/bảng mới; thêm test âm với hai bảng độc lập cùng số cột.

### F-03 — MEDIUM: List continuation có thể nuốt đoạn văn độc lập

**Vị trí:** `src/ingestion/pdf_layout.py:448-479`.

Rule hiện nối mọi `paragraph` cùng source với list item trước nếu khoảng dọc từ 0–24 point và x của paragraph không nằm lệch trái quá 2 point. Không có giới hạn lệch phải, kiểm tra marker/paragraph break hay tín hiệu cho biết đoạn đó thực sự là phần xuống dòng của item.

**Reproduction độc lập:** một list item ở bbox `[40,100,230,112]` và một paragraph độc lập ở `[40,120,330,132]` bị gộp thành một list item.

**Ảnh hưởng:** paragraph sau danh sách có thể bị chuyển nhầm thành nội dung item, làm sai cấu trúc/thứ tự semantic. Test hiện có chỉ kiểm tra case continuation đúng, không kiểm tra paragraph tiếp theo không thuộc list.

**QA yêu cầu trước khi nhận:** thêm điều kiện layout đáng tin cậy hơn để nhận diện wrap và negative tests cho paragraph sau list, heading, item mới và cột khác.

## 4. Kiểm tra OCR và các trang cần kiểm tra lại

Kết quả kiểm tra runtime thật trong `.venv`:

- `rapidocr_onnxruntime`: **không cài**.
- Tesseract executable: chạy được, phiên bản `5.5.3.20260724`.
- Tesseract languages: trả `[]`; không có `vie`, cũng không có `eng` khả dụng.
- Ba OCR integration tests bị skip vì yêu cầu Tesseract cùng Vietnamese traineddata.

PDF có image blocks cần OCR/đối chiếu trực quan sau khi sửa môi trường:

| PDF | Trang có image block |
|---|---|
| `DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf` | 3, 5, 6 |
| `PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` | 6, 9 |

Đặc biệt phải kiểm nội dung scholarship/percentage trong ảnh ở phương thức-xét tuyển trang 6 và 9. Chưa thể xác nhận OCR text, bbox, số liệu hoặc các trang ảnh này có đầy đủ trong JSON.

## 5. Test results

### Targeted ingestion suite

Lệnh:

```powershell
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
& .\.venv\Scripts\python.exe -m pytest tests/test_task_pdf_to_structured_json.py tests/test_data_pipeline_recovery.py tests/test_ingestion.py tests/test_ocr_runtime_integration.py tests/test_task_processed_md_to_json_migration.py -q -rs
```

Kết quả: **25 passed, 3 skipped, 7 subtests passed; 0 failed**. Cả 3 skip là OCR integration yêu cầu Vietnamese traineddata khả dụng.

### Full suite

Lệnh:

```powershell
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
& .\.venv\Scripts\python.exe -m pytest -q -rs
```

Kết quả: **302 passed, 4 skipped, 303 subtests passed; 0 failed** trong `60.89s`.

Skip: 3 OCR integration tests cần Tesseract/Vietnamese traineddata; 1 Qwen integration test cần `RUN_REAL_QWEN_TESTS=1`. Test pass không xác nhận OCR completeness hay nội dung OCR đúng.

## 6. Trạng thái dữ liệu — read-only snapshot

- RAW: **7 PDF**, SHA-256 hiện tại khớp toàn bộ giá trị trong report của Lead; không có RAW PDF nào được sửa bởi QA.
- `data/processed`: hiện có **7 JSON, 44 pages, 257 records**. QA không ghi hoặc promote JSON.
- Đối chiếu native text của PDF với `pages[].native_text`: so sánh được **44/44 trang**. 41 khớp sau chuẩn hóa whitespace; 3 khác biệt là Unicode NFC/NFD ở “Hình” trên hai trang và khoảng trắng bị sửa trong URL bị ngắt dòng. Không tìm thấy mất fact native trong ba khác biệt này; kiểm tra này không chứng minh nội dung nằm trong ảnh đã đủ.
- Chroma active read-only: collection `dhv_admissions_2026`, **310 embeddings**, metadata `year=2026`, `status=verified`, `school_code=DHV`. QA không rebuild hoặc ghi Chroma.
- Snapshot Chroma tại lúc review: `chroma.sqlite3`, 4,313,088 bytes, SHA-256 `53acefe99e04618e19518182714c6f72308f517ca8f4d0d543fb4bbd25ebe5d1`.

Các con số trên mô tả snapshot hiện tại; chúng không thay thế một baseline hash trước patch cho từng file processed/Chroma để chứng minh lịch sử không đổi.

## 7. Đánh giá coverage test

Các test hiện bao phủ positive case cho OCR de-dup/conflict ở text, confidence filter ở text, crop bbox, header inheritance mong muốn, fee/scholarship tables và list wrap cụ thể. Còn thiếu các negative/integration assertions cho:

- confidence thấp hoặc numeric conflict đi vào OCR table/cell;
- headerless table không liên quan nhưng cùng số cột ở trang kế tiếp;
- paragraph độc lập ngay sau list;
- OCR thật trên các trang có ảnh với Vietnamese traineddata.

## 8. Blockers và handoff

Lead cần xử lý F-01 đến F-03 và gửi lại đúng patch/report để QA rerun. Sau khi có RapidOCR hoạt động hoặc Tesseract với `vie.traineddata` (và executable xác thực được), QA cần stage extraction riêng, không ghi đè `data/processed`; đối chiếu 44 trang, OCR/image text, numeric facts, table header/row/cell, list order và warning trước. Chỉ xem xét promote/rebuild Chroma sau khi các kiểm tra nội dung hoàn tất và được duyệt.

**Verdict: BLOCKED — không phải PDF completeness PASS, không phải project QA PASS.**
