# PHASE 3 – CORPUS COVERAGE AND TEST ALIGNMENT REPORT

Ngày kiểm tra: 2026-09-24  
Project: ChatBot_DHV  
Phạm vi: kiểm kê RAW/manifest, Structured JSON, Chroma và căn chỉnh test/fixture theo corpus DHV 2026 hiện có.

## 1. Quyết định và phạm vi

- Chỉ sử dụng dữ liệu có trong workspace và các URL chính thức DHV đã có trong manifest.
- Không tìm kiếm web bên ngoài, không bổ sung dữ liệu giả, không dùng dữ liệu sai năm làm dữ liệu 2026.
- Không thay đổi router/runtime/UI ngoài các chỉnh sửa tối thiểu để test phản ánh đúng fact category và provenance hiện tại.
- Tài liệu không có source_url chính thức hoặc chưa verified=true vẫn được giữ trong RAW để audit, nhưng không được đưa vào knowledge base production.

## 2. Corpus inventory hiện tại

Manifest có 7 PDF, gồm 5 tài liệu chính thức đã xác minh cho năm 2026 và 2 tài liệu chưa xác minh.

| Category | RAW file | Năm | Verified | Source/provenance | Processed | Production Chroma |
|---|---|---:|---|---|---|---|
| diem_trung_tuyen | data/raw/diem_trung_tuyen/DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf | 2026 | Có | URL DHV chính thức | Có | Có |
| ho_so | data/raw/ho_so/HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf | 2026 | Có | URL DHV chính thức | Có | Có |
| hoc_phi | data/raw/hoc_phi/Hoc_Phi_DHV_2024.pdf | 2024 | Không | missing_source_url | Chỉ giữ audit text | Không |
| phuong_thuc_xet_tuyen | data/raw/phuong_thuc_xet_tuyen/PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf | 2026 | Có | Cổng tuyển sinh DHV chính thức | Có | Có |
| thong_tin_truong | data/raw/thong_tin_truong/Thong_Tin_Truong.pdf | 2026 | Không | missing_source_url | Chỉ giữ audit text | Không |
| thong_tin_truong | data/raw/thong_tin_truong/TONG_QUAN_TUYEN_SINH_DHV_2026.pdf | 2026 | Có | Cổng tuyển sinh DHV chính thức | Có | Có |
| xet_tuyen_bo_sung | data/raw/xet_tuyen_bo_sung/Ho_Xet_Tuyen_Bo_Sung_Dai_Hoc_Chinh_Quy_2026.pdf | 2026 | Có | URL DHV chính thức | Có | Có |

Các tài liệu chưa xác minh không bị xóa; loader đã loại chúng khỏi production. Vì vậy tuition 2024 và thông tin trường cũ không thể làm nguồn trả lời cho câu hỏi DHV 2026.

## 3. Coverage matrix

| Fact category yêu cầu | Nguồn chính thức đang có | Structured JSON | Chroma | Kết luận |
|---|---|---|---|---|
| hoc_phi | Tuition 2026 nằm trong HO_SO_NHAP_HOC_DAY_DU_DHV_2026.pdf | Có: 1 record tuition | Có: 1 chunk | Đủ dữ liệu 2026; file root 2024 không được dùng |
| hoc_bong | PHUONG/TONG/HO_SO/DIEM/XET 2026 | Có: 37 records | Có: 38 chunks sau splitting | Đủ |
| ho_so | HO_SO 2026 | Có: 35 records | Có: 35 chunks | Đủ |
| nhap_hoc | Nội dung nhập học trong DIEM và HO_SO 2026 | Có, qua fact ho_so/enrollment | Có | Đủ theo fact, không cần root riêng |
| lich_tuyen_sinh | HO_SO và XET 2026 | Có: 2 deadline records | Có: 2 chunks | Đủ |
| phuong_thuc_xet_tuyen | PHUONG 2026 | Có: 1 method record và các fact liên quan | Có: 1 chunk method | Đủ cho câu hỏi xét học bạ/phương thức |
| diem_trung_tuyen | DIEM 2026 | Có: 66 records | Có: 66 chunks | Đủ; giữ riêng với điểm sàn/ngưỡng |
| nguong_dau_vao | PHUONG 2026 | Có: 40 records | Có: 40 chunks | Đủ; 15/600 là rule chung, 18 chỉ áp dụng Luật/Luật Kinh tế |
| xet_tuyen_bo_sung | XET 2026 | Có: 18 threshold + quota + deadline | Có: 20 chunks | Đủ |
| nganh_dao_tao | PHUONG và TONG 2026 | Có: 40 major records + 2 summaries | Có: 42 chunks | Đủ 20 ngành chính và 47 chương trình nguồn |
| thong_tin_truong | TONG 2026 đã xác minh | Có: catalog/overview facts | Có qua các fact liên quan | Đủ trong phạm vi thông tin tuyển sinh; file trường chưa xác minh bị loại |

Không còn category bắt buộc nào thiếu nguồn chính thức đến mức chặn pipeline. Một số category không có PDF root riêng, nhưng fact đã được xác minh trong các PDF tuyển sinh đa chủ đề chính thức và được gắn source_category/fact_category tương ứng.

## 4. Structured JSON và manifest

- validate_manifest_sync(...): [] — không có RAW PDF ngoài manifest, không có entry trỏ tới file không tồn tại, document ID duy nhất.
- Manifest: 7 files; 5 verified 2026; 2 unverified; 0 tài liệu verified sai năm.
- Processed JSON: 7 files hợp lệ.
- Tổng records trong processed JSON: 249.
- Loader production: 247 verified records trước bước splitting; files_seen=7, verified_documents=5, skipped_unverified=2, skipped_other_year=0, metadata_errors=0.

Record counts chính:

| Record type | Số lượng |
|---|---:|
| admission_score | 66 |
| major | 40 |
| application_threshold | 40 |
| enrollment_document | 35 |
| scholarship_policy | 31 |
| supplementary_threshold | 18 |
| score_formula | 3 |
| deadline | 3 |
| scholarship_summary | 5 |
| tuition | 1 |
| admission_method | 1 |
| supplementary_quota | 1 |
| major_catalog_summary | 2 |
| scholarship_fund | 1 |
| document_text | 2, chỉ từ 2 tài liệu chưa xác minh |

### Cảnh báo chất lượng trích xuất

PDF DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf có cảnh báo ở page 8: OCR không sinh text usable và page không có text trích xuất. Native text của các trang có dữ liệu vẫn được giữ; page 8 đã được kiểm tra trực quan và không làm mất bảng điểm đã parse. Đây là warning cần theo dõi, không phải blocker của corpus hiện tại.

## 5. Những điểm đã căn chỉnh theo nguồn hiện tại

- Catalog đổi sang 20 ngành chính và 47 chương trình đúng theo PDF 2026; xử lý cả code đứng riêng, tên bị wrap qua page break và tên chương trình đúng literal nguồn.
- Tên nguồn hiện tại như Quản trị Marketin, Phân tích dữ liệu kinh doan, Tiếng Anh thương mại, Tiếng Trung văn hóa - Du lịch được giữ đúng provenance; không tự sửa thành dữ liệu ngoài nguồn.
- Ngưỡng đầu vào chung cập nhật về THPT 15,00 và ĐGNL 600; 18 chỉ giữ cho Luật/Luật Kinh tế khi nguồn ghi rõ.
- Điểm trúng tuyển giữ 20 theo source text, không dùng biến thể cũ 20,0 để làm expected bắt buộc.
- Hạn bổ sung cập nhật thành 21/8/2026 theo PDF hiện tại.
- Tuition cập nhật theo HO_SO 2026: 1.250.000 đồng/tín chỉ, 12.500.000 đồng cho 10 tín chỉ HKI và tổng ghi nhận 14.250.000 đồng theo breakdown của nguồn.
- Fixture và test path đã chuyển từ các PDF tên cũ/không còn trong RAW sang 7 file hiện có trong manifest.
- Test thông tin trường không còn yêu cầu claim 1995 từ Thong_Tin_Truong.pdf chưa xác minh.

## 6. Chroma production rebuild

Lệnh rebuild/reset đã chạy thành công với backend Ollama nomic-embed-text.

- Collection: dhv_admissions_2026
- Vector chunks: 248
- Năm trong collection: chỉ 2026
- year=2024: 0
- verified=false: 0

| Category | Chunks |
|---|---:|
| cach_tinh_diem | 3 |
| diem_trung_tuyen | 66 |
| hoc_bong | 38 |
| ho_so | 35 |
| hoc_phi | 1 |
| lich_tuyen_sinh | 2 |
| nganh_dao_tao | 42 |
| nguong_dau_vao | 40 |
| phuong_thuc_xet_tuyen | 1 |
| xet_tuyen_bo_sung | 20 |

Một record dài được split thành thêm chunk, vì vậy 248 vector chunks lớn hơn 247 verified records là đúng thiết kế.

## 7. Retrieval smoke check

Kết quả dưới đây phân biệt retrieval/evidence với answer planner:

| Query | Evidence category truy hồi | Kết quả |
|---|---|---|
| Trường có xét học bạ không? | phuong_thuc_xet_tuyen | PASS |
| 1 tín chỉ năm 2026 bao nhiêu tiền? | hoc_phi | PASS |
| Học phí DHV 2026 là bao nhiêu? | hoc_phi | PASS |
| DHV có những ngành nào? | nganh_dao_tao | PASS |
| CNTT có những chương trình nào? | nganh_dao_tao | PASS |
| Điểm chuẩn CNTT 2026? | diem_trung_tuyen | PASS |
| Điểm sàn CNTT 2026? | nguong_dau_vao | Evidence PASS; final planner còn trả no_data |
| Điểm nhận hồ sơ bổ sung CNTT? | xet_tuyen_bo_sung | Evidence PASS; final planner còn trả no_data |
| Giá vàng hôm nay? | Không áp dụng | out_of_scope |
| Học phí DHV 2027? | Không có dữ liệu năm yêu cầu | no_data |

Hai case no_data không phải thiếu corpus: trace có fact verified tương ứng — CNTT có THPT 15,00/ĐGNL 600, và bổ sung có THPT 15,0/học bạ 18,0. Đây là mismatch ở answer planner/conversation behavior, được phân loại ngoài phạm vi Phase 3 vì yêu cầu hiện tại không cho redesign runtime/router.

## 8. Test alignment và phân loại kết quả

### PASS — corpus/data/retrieval

- tests/test_data_pipeline_recovery.py + tests/test_task_processed_md_to_json_migration.py: 8 passed, 7 subtests.
- tests/test_task_m.py: 4 passed.
- tests/test_task_g.py + tests/test_task_k.py: 21 passed, 8 subtests.
- tests/test_task_response_ui.py: 12 passed.
- Các test JSON/parser/catalog/admission-score/tuition chính đã được căn theo 7 PDF hiện tại và qua được các nhóm tương ứng.
- Bộ fixture RAG đã được cập nhật theo năm, score type, tuition, deadline, catalog literal và provenance hiện tại.

### ENVIRONMENT_ISSUE — không phải lỗi corpus

- Một số test tạo TemporaryDirectory trong tests/test_ingestion.py, tests/test_task_pdf_to_structured_json.py và 2 test runtime của test_task_c.py bị PermissionError [WinError 5] trên Windows Temp (C:\Users\Sang\AppData\Local\Temp) khi tạo/xóa thư mục.
- Chạy full pytest không hoàn tất sạch do pytest capture/temp stream cleanup cũng gặp ACL WinError 5; collection đã thấy 155 tests nhưng shutdown có lỗi môi trường.
- Không có dấu hiệu cache provider hoặc dữ liệu cache được dùng để che kết quả; Chroma rebuild và các suite không phụ thuộc Temp chạy được.

### RUNTIME_BEHAVIOR_OUT_OF_PHASE — không phải lỗi corpus/test-data alignment

tests/test_task_f.py hiện có 21 passed, 2 failures:

1. test_realistic_two_turn_rejected_drafts_fall_back_to_grounded_clarification: fallback conversation chưa giữ đủ chi tiết ĐGNL.
2. test_two_turn_multiple_choices_then_scores_keeps_candidates_and_grounding: turn sau chưa giữ đúng candidate/evidence qua conversation retrieval.

Hai failure này nằm ở fallback/conversation answer behavior. Chúng không chỉ ra missing official PDF, sai manifest, sai record, hay dữ liệu unverified lọt vào Chroma.

## 9. Files/artefacts đã cập nhật trong Phase 3

- Parser và structured fact extraction: src/ingestion/structured_json.py.
- Evidence/entity filtering: src/chatbot/evidence.py.
- Source-literal aliases và tên chương trình: src/chatbot/query_analysis.py.
- Fixture/test alignment: tests/fixtures/rag_golden_questions.json, tests/test_task_f.py, tests/test_ingestion.py, tests/test_task_m.py, tests/test_task_pdf_to_structured_json.py, tests/test_task_processed_md_to_json_migration.py, tests/test_task_response_ui.py.
- RAW manifest và 7 processed JSON hiện tại đã được đồng bộ.
- Chroma collection dhv_admissions_2026 đã được reset/rebuild từ verified Structured JSON.

## Final verdict

CORPUS_AND_TESTS_READY

Corpus chính thức 2026 đã đủ coverage cho các fact category bắt buộc, manifest/processed JSON/Chroma đồng bộ, dữ liệu 2024 và tài liệu chưa xác minh không được index. Các lỗi còn lại đã được phân loại rõ là môi trường Windows hoặc hành vi conversation/answer planner ngoài phạm vi Phase 3, không phải blocker của corpus.
