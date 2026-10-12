# DevOps/SRE Local Runtime Verification Report

**Ngày kiểm tra:** 2026-10-09, khoảng 18:31–18:34 (+07:00)  
**Phạm vi:** local runtime, read-only; không deploy và không đánh giá factual QA.  
**Kết luận:** `local-runtime-ready` cho active runtime hiện tại; baseline Chroma khác report Lead/QA và staging collection không khả dụng nên cần QA/owner xác nhận riêng trước khi dùng làm baseline tái lập.

## 1. Quy tắc an toàn

- Không sửa business logic.
- Không sửa `.env`; project hiện chỉ thấy `.env.example`, không thấy `.env`.
- Không rebuild, reset, upsert, add, delete, swap hoặc ghi collection.
- Không đổi model/embedding, không thay dữ liệu.
- Không deploy.
- Các phép Chroma chỉ dùng `list_collections`, `get_collection`, `count` và `get(include=["metadatas"])`.
- Smoke query chỉ gọi đường runtime đọc dữ liệu và inference local.
- File report này là artifact duy nhất được tạo theo yêu cầu deliverable.

## 2. Lệnh/check đã chạy

Các nhóm kiểm tra đã thực hiện:

1. OS/process/listener: `Get-CimInstance Win32_OperatingSystem`, `Get-Process`, `Get-CimInstance Win32_Process`, `Get-NetTCPConnection`.
2. Python/runtime: `.venv\Scripts\python.exe --version`, `python -m pip check`, kiểm tra version bằng `importlib.metadata`.
3. Ollama: HTTP GET `/api/version`, `/api/tags`, `/api/ps`; POST `/api/chat` 5 lần với `qwen2.5:3b`; POST `/api/embed` 5 lần với `nomic-embed-text`.
4. Health endpoint: `http://127.0.0.1:11434/api/version` và `http://127.0.0.1:8501/_stcore/health`.
5. Chroma: mở read-only hai persist directory, liệt kê collection, đếm record và kiểm tra metadata.
6. Smoke query: `DHV năm 2026 có những phương thức xét tuyển nào?` qua `src.chatbot.rag_chain.ask_chatbot` với settings hiện hành.
7. Log/change audit: tìm `*.log`, `*.out`, `*.err` và đọc `git status --short`.

## 3. OS, Python và dependency

| Thành phần | Kết quả |
|---|---|
| OS | Windows 11 Pro 64-bit, version `10.0.26300`, build `26300` |
| PowerShell | `7.6.5` |
| Python system PATH | Không có Python system qua `py`/`python`; không ảnh hưởng runtime vì app dùng venv |
| Project Python | `.venv\Scripts\python.exe`, Python `3.12.14` |
| `pip check` | `No broken requirements found` |
| Streamlit CLI | `1.63.0` |

Dependency chính:

| Package | Version | Trạng thái |
|---|---:|---|
| `streamlit` | 1.63.0 | cài đặt |
| `langchain` | 0.3.30 | cài đặt |
| `langchain-community` | 0.3.31 | cài đặt |
| `langchain-chroma` | 0.2.6 | cài đặt |
| `langchain-text-splitters` | 0.3.11 | cài đặt |
| `langchain-ollama` | 0.3.10 | cài đặt |
| `chromadb` | 1.5.9 | cài đặt |
| `ollama` | 0.6.2 | cài đặt |
| `python-dotenv` | 1.2.3 | cài đặt |
| `pypdf` | 6.18.1 | cài đặt |
| `PyMuPDF` | 1.28.2 | cài đặt |
| `pytesseract` | 0.3.13 | cài đặt |
| `sentence-transformers` | 5.7.0 | cài đặt |
| `transformers` | 5.17.0 | cài đặt |
| `openpyxl` | 3.1.5 | cài đặt |
| `pytest` | 9.1.1 | cài đặt |
| `rapidocr_onnxruntime` | — | **thiếu**, dù có khai báo trong `requirements.txt` |

`rapidocr_onnxruntime` là dependency của OCR fallback; không chặn đường runtime RAG đã smoke-test, nhưng sẽ là blocker nếu cần fallback OCR bằng package này.

Import `src.chatbot.chat_service`, `src.chatbot.rag_chain` và `app` trong process mới đều thành công. Import trực tiếp `src.retrieval.retriever` trước package chatbot phát hiện circular-import (`ImportError: cannot import name 'DHVRetriever' from partially initialized module`); đây là rủi ro code/import-order, không chặn đường khởi động app hiện tại.

## 4. Process, port và health

| Thành phần | Quan sát |
|---|---|
| Ollama process | `ollama.exe serve`, PID `2836` |
| Ollama listener | `127.0.0.1:11434`, `Listen` |
| Streamlit process | `streamlit run app.py`, PID `2804` với worker Python PID `24044` |
| Streamlit listener | `[::]:8501`, `Listen` |
| Ollama health | HTTP `200`, `{"version":"0.34.4"}` |
| Streamlit health | HTTP `200`, body `ok` |

Kết quả health không có lỗi connection trong lần kiểm tra hiện tại.

## 5. Ollama model và độ ổn định

`/api/tags` xác nhận model có sẵn:

- `qwen2.5:3b`
- `nomic-embed-text:latest` (được gọi bằng tên cấu hình `nomic-embed-text`)

Kết quả 5 lần gọi liên tiếp, không song song:

| Test | Thành công | Latency min / avg / max | Kết quả |
|---|---:|---:|---|
| Chat `qwen2.5:3b` | 5/5 | 28.8 / 754.2 / 3623.6 ms | HTTP 200, `done=true`, trả `OK` |
| Embed `nomic-embed-text` | 5/5 | 5.4 / 120.6 / 557.6 ms | HTTP 200, 1 vector, dimension 768 |

Lần đầu chậm hơn do cold-load; các lần sau ổn định hơn. Sau smoke calls, `/api/ps` cho thấy cả hai model đang loaded. Không đổi `keep_alive` hay runtime config.

## 6. Cấu hình runtime hiệu dụng

Settings được app load thực tế:

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL=nomic-embed-text
CHROMA_PERSIST_DIR=chroma_db
CHROMA_COLLECTION=dhv_admissions_2026
TARGET_YEAR=2026
OLLAMA_TIMEOUT_SECONDS=90.0
```

Các giá trị trên là effective settings; không đọc/ghi secret và không sửa `.env`.

## 7. Chroma metadata audit

### Active runtime hiện tại

| Trường | Kết quả |
|---|---|
| Path | `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db` |
| Collections | `dhv_admissions_2026` |
| Record count | **310** |
| `year` | 310/310 là `2026` |
| `status` | 310/310 là `verified` |
| `verification_status` | 310/310 là `verified` |
| `school_code` | 310/310 là `DHV` |
| `source_url` | 310/310 có URL HTTP(S) |
| Host nguồn | `dhv.edu.vn`: 181; `tuyensinh.dhv.edu.vn`: 129 |
| Boolean metadata `verified` | Không có giá trị (`null`) trên 310 record; verification canonical nằm ở `status` và `verification_status` |

### Staging đối chiếu

`C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db_full_sweep_p1_stage` vẫn tồn tại và có `chroma.sqlite3`, nhưng hiện `list_collections()` trả collection rỗng; collection cấu hình `dhv_admissions_2026` không tồn tại trong staging. Không thể xác nhận count/metadata staging ở trạng thái hiện tại.

Đây khác report Lead/QA trước đó, trong đó active được ghi nhận 270 records và staging 310 records, xem [FULL_SWEEP_P1_FIX_REPORT.md](C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/FULL_SWEEP_P1_FIX_REPORT.md:226). Report hiện tại không suy đoán actor hay nguyên nhân của drift; trong lượt kiểm tra này không có thao tác swap, rebuild hoặc ghi collection.

## 8. Read-only smoke query

Query:

```text
DHV năm 2026 có những phương thức xét tuyển nào?
```

Kết quả:

- elapsed: `2383.0 ms`
- status: `ok`
- retrieval calls: `1`
- retrieved documents: `15`
- evidence count: `15`
- final status: `ok`
- runtime error: `null`
- path/collection: active `chroma_db` / `dhv_admissions_2026`

Đây chỉ xác nhận local runtime truy xuất và sinh phản hồi được; không phải factual QA PASS.

## 9. Log, lỗi và giới hạn quyền

- Không tìm thấy file `*.log`, `*.out` hoặc `*.err` trong workspace.
- Khi import `app` bằng Python bare process, Streamlit phát cảnh báo `missing ScriptRunContext`/`Session state does not function...`; đây là cảnh báo do chạy sai chế độ CLI, không xuất hiện ở health endpoint `streamlit run app.py`.
- Lần kiểm tra không qua host privilege bị giới hạn CIM/socket; các lệnh OS/process/listener và HTTP local cần quyền host read-only đã chạy lại thành công. Đây là giới hạn sandbox, không phải kết luận Ollama offline.
- Không có runtime exception trong smoke query.
- Report Lead/QA trước đây ghi nhận một `ollama_offline` đơn lẻ ở UQ0010 sau retrieval/evidence; lần kiểm tra hiện tại health và smoke query đều thành công. Đây là thông tin lịch sử, không kết luận factual QA.
- Thiếu log request-level và exception gốc khiến việc phân biệt socket timeout/model stall trong các lỗi đơn lẻ sau này bị hạn chế.

## 10. Kiểm tra thay đổi và deploy

Trước khi tạo report, working tree đã có các thay đổi/untracked artifacts có sẵn, gồm source/test files và `reports/`; không quy các thay đổi đó cho kiểm tra này. Kiểm tra này không sửa các file đó, không sửa `.env`, không ghi Chroma và không thay model/embedding.

Không chạy lệnh deploy, publish, rebuild, reset, upsert, add, delete hoặc swap collection. Không dừng/restart process.

## 11. Kết luận

**`local-runtime-ready`** cho active local runtime:

- OS/venv/dependency lõi hoạt động.
- Ollama endpoint hoạt động; `qwen2.5:3b` và `nomic-embed-text` có sẵn, gọi liên tiếp thành công.
- Streamlit health hoạt động.
- Active Chroma truy xuất được, metadata boundary đạt 2026/verified/DHV/source URL.
- Smoke query read-only thành công.

Các điểm cần QA/owner theo dõi nhưng không chặn active smoke runtime:

1. Chroma baseline đã drift so với Lead/QA: active hiện 310 thay vì 270; staging hiện không có collection.
2. `rapidocr_onnxruntime` thiếu, chỉ ảnh hưởng OCR fallback.
3. Direct import `src.retrieval.retriever` có circular-import theo một import order; actual app import path hiện vẫn chạy.
4. Không có structured persistent runtime log cho timeout đơn lẻ.

Không có deploy.
