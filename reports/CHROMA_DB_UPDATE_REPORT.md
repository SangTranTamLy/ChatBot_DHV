# BÁO CÁO CẬP NHẬT VECTOR DB (CHROMA) TỪ JSON PROCESSED

Ngày cập nhật: 2026-10-11  
Vai trò: Lead Coder — báo cáo bàn giao, không phải kết luận QA cuối.

## 1. Phát hiện trước khi cập nhật

Runtime dùng `chroma_db` / collection `dhv_admissions_2026`. Collection cũ có 310 chunks, metadata vẫn trỏ đến các tên PDF cũ và không có `source_sha256`; vì vậy không đại diện cho bộ JSON V1 vừa trích xuất.

## 2. Quy trình cập nhật

Đọc `data/processed` bằng loader chuẩn, chỉ lấy tài liệu qua gate verified, trường DHV, năm mục tiêu 2026 và nguồn HTTPS chính thức. Dựng collection ứng viên riêng bằng cấu hình đang dùng (`Ollama`, `nomic-embed-text`), audit ứng viên, sau đó mới chuyển thành đường dẫn active.

Lệnh build tương đương:

```powershell
.\.venv\Scripts\python.exe -m src.ingestion.build_vector_db `
  --data-dir data/processed `
  --persist-dir chroma_db_refresh_candidate_20261011 `
  --collection dhv_admissions_2026 `
  --year 2026 `
  --embedding-backend ollama `
  --embedding-model nomic-embed-text `
  --ollama-base-url http://localhost:11434
```

Collection cũ ban đầu được giữ ở `chroma_db_pre_json_refresh_20261011` trong lúc kiểm định. Theo yêu cầu tiếp theo của người dùng, backup cũ và staging rỗng đã được xóa sau khi xác nhận `chroma_db` active là bản mới. Hiện không còn bản rollback local. Không deploy và không rebuild từ RAW trực tiếp.

## 3. Kết quả nạp

| Chỉ số | Kết quả |
|---|---:|
| JSON được quét | 7 |
| Tài liệu verified năm 2026 được nạp | 6 |
| JSON bị loại bởi verification gate | 1 |
| Metadata/schema errors | 0 |
| Semantic documents từ loader | 263 |
| Chunks trong Chroma active | 281 |
| Model embedding | `nomic-embed-text` |
| Collection | `dhv_admissions_2026` |
| Năm / trạng thái / trường | `2026` / `verified` / `DHV` |

`V1_HOC_PHI_DHV_2024.json` không được index: nội dung thuộc năm 2024 và nguồn hiện có `verified=false`, `status=missing_source_url`. File JSON vẫn được giữ; collection active không có dữ liệu năm 2024.

## 4. Freshness và provenance

Đã bổ sung `source_sha256` vào metadata của record/chunk khi có trong JSON. Sau build, cả 6 nguồn verified đều có mặt trong Chroma; hash của từng nguồn trong metadata trùng hash JSON và PDF RAW hiện tại. Không có chunk sai năm, sai trường, unverified hoặc thiếu/không hợp lệ nguồn HTTPS.

## 5. Category counts

| Category | Chunks |
|---|---:|
| `cach_tinh_diem` | 2 |
| `diem_trung_tuyen` | 71 |
| `ho_so` | 12 |
| `hoc_bong` | 37 |
| `hoc_phi` | 1 |
| `lich_tuyen_sinh` | 1 |
| `nganh_dao_tao` | 42 |
| `nguong_dau_vao` | 40 |
| `phuong_thuc_xet_tuyen` | 21 |
| `thong_tin_truong` | 27 |
| `xet_tuyen_bo_sung` | 27 |

## 6. Retrieval smoke test trên collection active

Các truy vấn được chạy bằng embedding Ollama thật và collection runtime đang cấu hình; đây là kiểm tra retrieval, không gọi LLM để kết luận chất lượng câu trả lời.

| Query | Kết quả |
|---|---|
| `nhap hoc can giay to gi` | PASS — top source là PDF hồ sơ nhập học; có kết quả category `ho_so` |
| `cac phuong thuc xet tuyen DHV 2026` | PASS — top source là PDF tổng quan tuyển sinh; có category phương thức |
| `diem trung tuyen Luat 2026` | PASS — kết quả từ PDF điểm trúng tuyển |
| `hoc phi HKI 2026` | PASS — truy xuất được dữ liệu có `12.500.000` và `14.250.000` trong evidence |

## 7. Build compatibility và kiểm thử

- BGE-M3 fast tokenizer trên máy này phát sinh `MemoryError` khi đọc `tokenizer.json`; slow tokenizer dùng cùng cache/từ vựng hoạt động. Splitter nay thử fast trước rồi fallback sang slow, vẫn chỉ dùng tokenizer cục bộ và vẫn chia theo token.
- `tests/test_ingestion.py -k tokenizer_loader_falls_back_to_local_slow_variant`: **1 passed**.
- Kiểm tra metadata loader kèm fixture bằng pytest bị Windows `WinError 5: Access denied` khi tạo thư mục lồng trong temp; lần thử với temp trong workspace cũng bị ACL từ chối. Đây là `TEST_INFRA_FAILURE`, không phải assertion lỗi sản phẩm. Provenance đã được xác nhận trực tiếp trên toàn bộ 281 chunks active.
- Chưa chạy full pytest và chưa có QA độc lập.

## 8. Handoff QA & Security

Đề nghị QA kiểm tra trực tiếp code và collection active: hash 6 nguồn verified, gate năm/trường/status/source, loại trừ học phí 2024, retrieval cho nhập học/phương thức/điểm/học phí, và regression các câu external-school. Sau đó đánh giá answer grounding qua runtime chatbot. Lead Coder chưa kết luận QA PASS.

## 9. Dọn DB cũ theo yêu cầu người dùng

- Đã xóa `chroma_db_pre_json_refresh_20261011` (310 chunks, tên nguồn PDF cũ, không có `source_sha256`).
- Đã xóa `chroma_db_full_sweep_p1_stage` (chỉ có SQLite rỗng, không có collection).
- Xác minh sau xóa: chỉ còn thư mục `chroma_db`; collection active vẫn có 281 chunks, hash hiện diện trên 281/281 chunks, năm 2026, verified, DHV.
- Không còn bản Chroma cũ để rollback.

Không deploy.
