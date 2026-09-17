# 🎓 ChatBot DHV – Trợ lý tư vấn tuyển sinh

ChatBot DHV là chatbot hỏi đáp tiếng Việt về tuyển sinh Trường Đại học Hùng Vương TP.HCM (DHV), sử dụng kiến trúc RAG. Ứng dụng chạy local bằng Streamlit, Ollama và ChromaDB; không cần API key của dịch vụ AI bên ngoài.

> Đây là project demo phục vụ học tập, nghiên cứu và kiểm thử. Dữ liệu hiện tại ưu tiên thông tin tuyển sinh DHV năm 2026. Với thông tin quan trọng hoặc có thể thay đổi, hãy kiểm tra lại thông báo chính thức của nhà trường.

## 🚀 Chạy nhanh sau khi tải project

Các lệnh bên dưới dành cho Windows PowerShell và được chạy tại thư mục gốc `ChatBot_DHV`.

### 1. Tải source code

Có thể chọn một trong hai cách:

- Trên GitHub: chọn **Code → Download ZIP**, giải nén rồi mở thư mục project.
- Hoặc clone repository:

```powershell
git clone <URL_REPOSITORY_CUA_NHOM>
cd ChatBot_DHV
```

Nếu đã tải ZIP, chỉ cần mở PowerShell tại thư mục vừa giải nén:

```powershell
cd "duong-dan-den\ChatBot_DHV"
```

### 2. Tạo môi trường Python và cài thư viện

Yêu cầu Python 3.11 trở lên.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu máy không nhận lệnh `python`, hãy cài Python rồi mở lại PowerShell. Có thể kiểm tra bằng:

```powershell
python --version
```

Nếu PowerShell báo không cho chạy file kích hoạt, chạy lại lệnh `Set-ExecutionPolicy` ở trên trong đúng cửa sổ PowerShell hiện tại.

### 3. Tạo file cấu hình local

Sao chép `.env.example` thành `.env`:

```powershell
Copy-Item .env.example .env
```

File `.env` chỉ chứa cấu hình local và không được commit lên Git. Cấu hình mặc định đã phù hợp để chạy thử, nên không cần thêm API key.

### 4. Cài và chuẩn bị Ollama

Cài Ollama trên máy, sau đó mở một cửa sổ PowerShell riêng và chạy:

```powershell
ollama serve
```

Giữ cửa sổ này mở trong lúc test. Nếu Ollama Desktop đã tự chạy nền thì có thể bỏ qua lệnh `ollama serve`.

Tải hai model mà project sử dụng:

```powershell
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
ollama list
```

Trong kết quả `ollama list` cần thấy `qwen2.5:3b` và `nomic-embed-text`.

### 5. Tạo dữ liệu xử lý và cơ sở dữ liệu tìm kiếm

Sau khi clone/tải ZIP, bắt buộc chạy hai lệnh dưới đây một lần. `data/processed_json/`, `data/processed/` và `chroma_db/` là dữ liệu sinh tự động nên không lưu trong Git:

```powershell
python -m src.ingestion.prepare_processed_from_raw
python -m src.ingestion.build_vector_db --data-dir data/processed_json --embedding-backend ollama --embedding-model nomic-embed-text --reset
```

Nếu thêm hoặc thay file PDF trong `data/raw/`, chạy lại cả hai lệnh trên. Lệnh prepare sinh JSON có cấu trúc từ PDF và đồng thời xuất Markdown tương thích cho consumer cũ; JSON là input chính của vector builder. Không đổi embedding model sau khi build index; nếu đổi thì phải build lại với `--reset`.

### 6. Khởi động chatbot

```powershell
python -m streamlit run app.py
```

Mở trình duyệt tại [http://localhost:8501](http://localhost:8501).

Mỗi lần test sau đó chỉ cần:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

## 💬 Câu hỏi mẫu để kiểm thử

- `DHV năm 2026 có những ngành đào tạo nào?`
- `Ngành Công nghệ thông tin có những chương trình nào?`
- `Điểm trúng tuyển ngành Luật là bao nhiêu?`
- `Học phí học kỳ 1 năm 2026 bao nhiêu?`
- `Hồ sơ nhập học cần những gì?`
- `Lịch tuyển sinh năm 2026 như thế nào?`
- `Cho tôi website/cổng tuyển sinh của DHV.`
- `Thời tiết hôm nay thế nào?` — dùng để kiểm tra câu hỏi ngoài phạm vi.

Chatbot có hỗ trợ ngữ cảnh hội thoại giới hạn, vì vậy có thể hỏi tiếp như: `Còn ngành Marketing thì sao?`

## 🧪 Kiểm thử project

Các lệnh sau chạy từ thư mục gốc, sau khi đã activate `.venv`:

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -p "test_*.py" -v
```

> Nếu full test báo thiếu `DHV_AGENT_MASTER_PLAN_UPDATED/08_CANDIDATE_DHV_SOURCES.md`, đó là hai test audit tài liệu cũ (`test_task_08`), không ảnh hưởng việc chạy chatbot. Có thể bỏ qua hai test này khi kiểm thử chức năng chatbot.

Kiểm tra riêng việc truy xuất dữ liệu:

```powershell
python -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text
python -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text --top-k 25
```

Chạy bộ đánh giá offline:

```powershell
python -m evaluation.run_evaluation --split all
```

Model phân loại intent offline đã được lưu tại `models/intent_classifier.json`. Nếu file này chưa có trong bản tải về, tạo lại bằng:

```powershell
python -m src.chatbot.train_intent_model
```

Kiểm thử với model Qwen thật là tùy chọn và cần Ollama đang chạy:

```powershell
$env:RUN_REAL_QWEN_TESTS="1"
python -m unittest tests.test_qwen_integration -v
```

## 🏗️ Kiến trúc tổng quan

```text
Người dùng
    ↓
Streamlit (app.py)
    ↓
ChatService → phân loại intent, nhận diện entity, kiểm tra phạm vi
    ↓
DHV Retriever → ChromaDB + tìm kiếm hybrid
    ↓
Evidence Builder → dữ liệu đã kiểm chứng
    ↓
Danh sách/catalog deterministic hoặc prompt RAG
    ↓
Ollama (qwen2.5:3b) → kiểm tra grounding → câu trả lời
```

Các thành phần chính:

- `app.py`: giao diện Streamlit.
- `src/chatbot/`: service, phân tích câu hỏi, intent, evidence, prompt và validator.
- `src/retrieval/`: truy xuất dữ liệu từ ChromaDB.
- `src/ingestion/`: đọc PDF, tạo JSON có cấu trúc (và Markdown tương thích), chia chunk và build vector database.
- `data/raw/`: PDF nguồn DHV đã được thu thập để đối chiếu.
- `data/intent/`: dữ liệu huấn luyện và holdout cho intent model.
- `models/intent_classifier.json`: model intent offline dùng lúc runtime.
- `data/processed_json/`: JSON có cấu trúc sinh tự động từ RAW PDF, không commit.
- `data/processed/`: Markdown tương thích sinh tự động, không commit.
- `chroma_db/`: vector database sinh tự động, không commit.
- `tests/`: unit test và regression test.

## 🔄 Pipeline dữ liệu

```text
RAW PDF trong data/raw/
    ↓ extraction hiện tại (pypdf text layer)
Structured JSON + schema/domain validation
    ↓ record-level chunk builder
LangChain Documents + embedding
    ↓ build_vector_db
ChromaDB → Retriever → Evidence → RAG
```

JSON là lớp dữ liệu xử lý trung gian có cấu trúc: giữ metadata nguồn, page traceability, sections, records, quan hệ ngành–chương trình và các trường deterministic trước khi tạo chunk. RAW PDF vẫn là source of truth; runtime chatbot không parse PDF/JSON lớn.

`data/raw/manifest.json` lưu checksum SHA-256, nguồn, ngày kiểm tra và trạng thái xác minh. Chỉ tài liệu chính thức, đúng năm và đã xác minh mới được đưa vào index. Metadata nguồn được giữ ở backend để audit; chatbot không tự đoán số liệu, ngày tháng hoặc URL.

## ⚙️ Cấu hình mặc định

Các giá trị dưới đây nằm trong `.env.example`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT_SECONDS=90
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL=nomic-embed-text
CHROMA_PERSIST_DIR=chroma_db
CHROMA_COLLECTION=dhv_admissions_2026
PROCESSED_JSON_DIR=data/processed_json
PROCESSED_DATA_DIR=data/processed
RETRIEVER_TOP_K=4
TARGET_YEAR=2026
RAG_MAX_CONTEXT_CHARS=12000
```

Không cần chỉnh cấu hình nếu chỉ muốn chạy bản demo. Nếu dùng embedding backend khác, phải build lại `chroma_db` trước khi chạy chatbot.

## 🛠️ Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `python` không được nhận diện | Cài Python 3.11+, mở lại PowerShell và kiểm tra `python --version`. |
| `Ollama offline` hoặc không kết nối được | Mở Ollama Desktop hoặc chạy `ollama serve`; kiểm tra `ollama list`. |
| `model not found` | Chạy lại `ollama pull qwen2.5:3b` và `ollama pull nomic-embed-text`. |
| ChromaDB bị thiếu/rỗng | Chạy lại bước tạo `data/processed_json` và build vector database với `--reset`. |
| Chatbot trả lời thiếu dữ liệu | Kiểm tra câu hỏi có thuộc tuyển sinh DHV năm 2026 không; dữ liệu ngoài corpus sẽ được từ chối an toàn. |
| Đã sửa PDF nhưng kết quả chưa đổi | Rebuild lại processed data và ChromaDB như ở bước 5. |

## 🔒 Phạm vi và dữ liệu cá nhân

- Chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh DHV.
- Không nhập CCCD, số điện thoại, email, địa chỉ hoặc hồ sơ cá nhân vào khung chat.
- Chatbot không dự đoán hoặc cam kết đậu/trượt, không tra cứu kết quả cá nhân và không đăng ký xét tuyển thay người dùng.
- Nếu không có bằng chứng trong knowledge base, chatbot phải nói chưa biết thay vì tự suy đoán.

Nếu chatbot khác với thông báo chính thức, ưu tiên thông tin do DHV công bố.

## 📦 Checklist trước khi push cho nhóm

Đảm bảo commit kèm các thành phần cần thiết để thành viên khác có thể build lại project:

- `app.py`, `src/`, `requirements.txt`, `.env.example`.
- `data/raw/` và `data/raw/manifest.json`.
- `data/intent/` và `models/intent_classifier.json`.
- `evaluation/` và `tests/` nếu muốn mọi người chạy test.

Không commit `.env`, `.venv/`, `data/processed_json/`, `data/processed/` hoặc `chroma_db/`; thành viên sẽ tự tạo các thư mục generated này theo hướng dẫn ở trên.
