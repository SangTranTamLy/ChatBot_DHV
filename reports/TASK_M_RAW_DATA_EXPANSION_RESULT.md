# TASK M — RAW Data Expansion

Ngày thực hiện: 15/09/2026  
Trạng thái: **PASS**

## Task và phạm vi

Mở rộng/audit corpus tuyển sinh DHV 2026 theo `DHV_AGENT_MASTER_PLAN_UPDATED/06_TASK_M_RAW_DATA_EXPANSION.md`: chỉ nguồn chính thức `dhv.edu.vn`/subdomain, RAW mới ở dạng PDF, không ingest PII không cần thiết, rebuild processed + Chroma và kiểm tra hồi quy.

Đã đọc `DHV_AGENT_MASTER_PLAN_UPDATED/00_MASTER_PLAN.md` và `Tong_quan_xay_dung_chatbot_AI.pdf`. Phương pháp provenance sử dụng catalog nguồn, ngày hiệu lực/ngày kiểm tra, trạng thái xác minh, metadata và ranh giới dev/regression theo phần chuẩn bị RAG trong PDF (tr. 36–40).

## Baseline → expected → current

| Hạng mục | Baseline trước TASK M | Expected | Current |
|---|---:|---:|---:|
| RAW PDF | 14 | Corpus chỉ PDF, provenance đầy đủ | 15 |
| Processed verified documents | 13 | Mọi RAW hợp lệ được prepare | 15 |
| Chunks trong Chroma | 18 | Rebuild từ corpus mới | 25 |
| Manifest | Chưa có | SHA-256 + source/date/status/privacy | `data/raw/manifest.json`, 15/15 verified |
| Conflict audit | Chưa có | Có report, không ghi đè nguồn khoa | `reports/DATA_CONFLICTS_2026.md` |

## Root cause và thay đổi

1. Pipeline cũ chưa có owner cho RAW manifest; metadata mới chỉ lấy URL đầu tiên và date parser không nhận các nhãn `Ngày thu thập/kiểm tra`/`Ngày kiểm tra`. Vì vậy RAW thông tin trường bị loại ở bước prepare.
2. Không có capture riêng cho mô tả ngành/cơ hội nghề nghiệp từ nguồn khoa chính thức.
3. Khi thêm tài liệu mô tả vào cùng domain `nganh_dao_tao`, parser bảng catalog đã coi prose như bảng ngành. Đây là nguyên nhân regression làm lệch retrieval/catalog.

Đã xử lý bằng:

- `src/ingestion/raw_manifest.py`: manifest deterministic, SHA-256, official HTTPS host policy, source URLs, date/collected_at, category, `verification_status`, document type và cờ PII.
- `src/ingestion/prepare_processed_from_raw.py`: kiểm tra toàn bộ URL provenance, nhận dạng ngày kiểm tra, metadata `source_urls`, `date`, `collected_at`, `verification_status` và `data_role` tổng quát (`catalog`/`description`).
- `src/chatbot/evidence.py`: Evidence Selection/structured fact parser không parse tài liệu `description` thành score/quan hệ catalog; category `nganh_dao_tao` vẫn giữ tương thích router.
- `src/retrieval/retriever.py` và `src/chatbot/rag_chain.py`: truyền entity filters xuống retriever; truy vấn mã ngành được giữ khỏi prose; truy vấn liệt kê thuần túy ưu tiên candidate catalog có cấu trúc. Không hard-code ngành CNTT/Luật.
- `src/ingestion/rebuild_smoke_test.py`: default smoke top-k là 25, phù hợp corpus 25 chunks sau rebuild; runtime retriever vẫn giữ top-k cấu hình 4.
- `tests/test_task_m.py`: thêm kiểm tra manifest, official-host policy, PDF-only, privacy, processed metadata và capture mô tả nghề nghiệp. `tests/test_ingestion.py` chỉ cập nhật invariant số lượng corpus hợp lệ; không xóa test.

## Data mới và provenance

Đã revalidate/ghi lại:

- `data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf`: giới thiệu ngắn, portal, địa chỉ/hotline/email tổng quát và boundary note; kiểm tra 15/09/2026.
- `data/raw/nganh_dao_tao/mo_ta_cntt_co_hoi_nghe_nghiep_2026.pdf`: mô tả định hướng đào tạo và cơ hội nghề nghiệp từ bài TEC chính thức ngày 21/03/2026; không chứa điểm, công thức, học phí, điều kiện hoặc PII.

Nguồn chính thức được ghi ngay trong PDF/manifest và chỉ dùng HTTPS DHV:

- `https://tuyensinh.dhv.edu.vn/`
- `https://tuyensinh.dhv.edu.vn/dangky`
- `https://dhv.edu.vn/truong-dai-hoc-hung-vuong-tp-ho-chi-minh-cong-bo-diem-san-xet-tuyen-nam-2026-trien-khai-quy-hoc-bong-75-ty-dong/`
- `https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm`
- `https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc`

Không sử dụng `reference_images/` làm dữ liệu RAG. Không ingest dữ liệu submit từ form đăng ký; PDF form chỉ giữ hướng dẫn/boundary, không giữ PII thực tế.

## Conflicts, unverified và limitations

- `reports/DATA_CONFLICTS_2026.md` ghi nhận mapping địa chỉ khác thứ tự giữa nguồn trung tâm và trang khoa, email/hotline theo footer khoa, cùng trang curriculum TEC hiển thị năm 2023/2024.
- Quyết định: nguồn tuyển sinh trung tâm 2026 là authority cho địa chỉ chung, catalog, điểm và lịch answer-critical; trang khoa chỉ dùng khi hỏi đúng đơn vị và không dùng để ghi đè catalog 2026.
- Curriculum 2023/2024 của TEC không được import vào catalog 2026. Không có fact mới nào được suy diễn từ phần chưa xác nhận 2026.
- Smoke dùng Ollama `nomic-embed-text`; test Qwen thật vẫn skip theo điều kiện test hiện hữu. Full test trong môi trường mặc định gặp Windows temp permission của test cũ, nên chạy lại bằng temp directory writable; đây không phải lỗi sản phẩm.
- Nguồn web có thể thay đổi; manifest `sha256` và `collected_at` là điểm kiểm tra để audit/re-capture lần sau.

## Verification

Kết quả cuối:

- Targeted TASK M: `4/4 PASS`.
- Targeted retrieval/catalog/ingestion: `46/46 PASS`.
- Full regression: `101 tests`, `OK (skipped=1)`.
- Processed rebuild: `raw_pdfs=15`, `processed_documents=15`.
- Chroma rebuild: `files_seen=15`, `verified_documents=15`, `metadata_errors=0`, `chunks_indexed=25`.
- Vector smoke: `SMOKE_PASS`.
- Rebuild regression smoke: `REGRESSION_PASS (12 cases)`.
- `compileall`: PASS; `git diff --check`: PASS.

## Exact reproduce commands

Chạy từ repository root `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV`:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m src.ingestion.raw_manifest --audited-at 2026-09-15
.\.venv\Scripts\python.exe -m src.ingestion.prepare_processed_from_raw
.\.venv\Scripts\python.exe -m src.ingestion.build_vector_db --embedding-backend ollama --embedding-model nomic-embed-text --reset
.\.venv\Scripts\python.exe -m unittest tests.test_task_m -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
.\.venv\Scripts\python.exe -m src.ingestion.smoke_test_vector_db --persist-dir .\chroma_db --collection dhv_admissions_2026 --embedding-backend ollama --embedding-model nomic-embed-text --top-k 4
.\.venv\Scripts\python.exe -m src.ingestion.rebuild_smoke_test --persist-dir .\chroma_db --collection dhv_admissions_2026 --embedding-backend ollama --embedding-model nomic-embed-text --top-k 25
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

**PASS** — targeted tests, full regression, processed rebuild, Chroma rebuild và smoke/regression invariants đều đạt.
