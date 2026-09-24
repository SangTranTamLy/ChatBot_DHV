# ChatBot DHV – Trợ lý tư vấn tuyển sinh

ChatBot DHV là chatbot tiếng Việt hỗ trợ tra cứu thông tin tuyển sinh của Trường Đại học Hùng Vương TP.HCM (DHV). Ứng dụng chạy local bằng Streamlit, Ollama và ChromaDB, sử dụng kiến trúc RAG với dữ liệu PDF chính thức đã được kiểm chứng.

Project hiện ưu tiên dữ liệu tuyển sinh năm 2026. Với thông tin quan trọng hoặc có thể thay đổi, hãy kiểm tra lại thông báo chính thức của nhà trường.

## Tính năng

- Hỏi đáp về ngành đào tạo, phương thức xét tuyển, điểm, học phí, học bổng, hồ sơ, lịch tuyển sinh và thông tin liên hệ.
- Nhận diện intent và entity tiếng Việt, gồm tên ngành, mã ngành và chương trình đào tạo.
- Duy trì ngữ cảnh hội thoại giới hạn qua nhiều lượt hỏi.
- Truy xuất hybrid BM25 + dense retrieval + RRF từ ChromaDB.
- Chỉ sử dụng evidence đã xác minh; nếu không có dữ liệu phù hợp, chatbot trả lời an toàn thay vì tự đoán.
- Có kiểm tra grounding, quan hệ ngành–chương trình và phạm vi câu hỏi.
- Có bộ test unit, regression, AppTest của Streamlit và đánh giá offline cố định.

## Yêu cầu môi trường

- Windows PowerShell hoặc môi trường tương đương.
- Python 3.11 trở lên.
- Ollama nếu muốn chạy đầy đủ chatbot với LLM local.
- Tesseract OCR chỉ cần khi xử lý PDF scan không có text layer.

## Cài đặt và chạy lần đầu

Các lệnh dưới đây chạy từ thư mục gốc của project.

### 1. Clone project

```powershell
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
cd ChatBot_DHV
```

### 2. Tạo virtual environment và cài thư viện

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu máy không nhận lệnh `python`, hãy cài Python 3.11+ rồi mở lại PowerShell.

### 3. Tạo cấu hình local

```powershell
Copy-Item .env.example .env
```

`.env` chỉ dùng cho máy local và không được commit lên Git. Cấu hình mặc định không cần API key bên ngoài.

### 4. Cài và chuẩn bị Ollama

Mở Ollama Desktop hoặc chạy trong một cửa sổ PowerShell riêng:

```powershell
ollama serve
```

Tải model chat và model embedding:

```powershell
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
ollama list
```

Kết quả `ollama list` cần có `qwen2.5:3b` và `nomic-embed-text`.

### 5. Tạo dữ liệu processed và ChromaDB

`data/raw/` là dữ liệu nguồn. Hai thư mục `data/processed/` và `chroma_db/` là dữ liệu sinh tự động và không cần commit.

```powershell
python -m src.ingestion.prepare_processed_from_raw
python -m src.ingestion.build_vector_db `
  --data-dir data/processed `
  --embedding-backend ollama `
  --embedding-model nomic-embed-text `
  --reset
```

Nếu thêm hoặc thay PDF trong `data/raw/`, chạy lại cả hai lệnh trên. Không đổi embedding model giữa các lần chạy nếu chưa build lại ChromaDB.

### 6. Khởi động ứng dụng

```powershell
python -m streamlit run app.py
```

Mở [http://localhost:8501](http://localhost:8501) trong trình duyệt.

## Cấu hình

Các biến môi trường nằm trong `.env.example`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT_SECONDS=90
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL=nomic-embed-text
SENTENCE_TRANSFORMER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
CHROMA_PERSIST_DIR=chroma_db
CHROMA_COLLECTION=dhv_admissions_2026
PROCESSED_DATA_DIR=data/processed
RETRIEVER_TOP_K=4
TARGET_YEAR=2026
RAG_MAX_CONTEXT_CHARS=12000
```

Có thể dùng embedding local thay cho Ollama bằng cách đặt:

```env
EMBEDDING_BACKEND=sentence-transformers
```

Sau đó build lại ChromaDB với backend tương ứng:

```powershell
python -m src.ingestion.build_vector_db --embedding-backend sentence-transformers --reset
```

## Kiểm thử

Sau khi activate `.venv`:

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -p "test_*.py" -v
```

Các test giao diện dùng `streamlit.testing.v1.AppTest`, không cần mở browser hoặc chạy server riêng.

Kiểm tra riêng vector database:

```powershell
python -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text
python -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text --top-k 25
```

Chạy đánh giá offline trên bộ `dev` và `holdout` cố định:

```powershell
python -m evaluation.run_evaluation --split all
```

Bộ đánh giá được mô tả tại [evaluation/README.md](evaluation/README.md). `holdout` chỉ dùng để báo cáo, không dùng để chỉnh rule, prompt hoặc threshold.

### Kiểm thử với Qwen thật

Đây là test tùy chọn và yêu cầu Ollama đang chạy:

```powershell
$env:RUN_REAL_QWEN_TESTS="1"
python -m unittest tests.test_qwen_integration -v
```

## Huấn luyện intent model

Model intent runtime mặc định là `models/intent_classifier.json`. Có thể train lại bằng:

```powershell
python -m src.chatbot.train_intent_model
```

Project cũng có pipeline Phase 5 độc lập:

```powershell
python scripts/train_phase5_intent.py
python scripts/evaluate_phase5.py --split all
```

Model Phase 5 được lưu tại `models/phase5_intent_classifier.json`; không thay thế model runtime mặc định nếu chưa được cấu hình hoặc kiểm thử đầy đủ.

## Cấu trúc project

```text
ChatBot_DHV/
├── app.py                         # Giao diện Streamlit
├── src/
│   ├── chatbot/                   # Phân tích câu hỏi, service, RAG, validator
│   ├── config/                    # Đọc và kiểm tra cấu hình từ .env
│   ├── ingestion/                 # PDF → Structured JSON → ChromaDB
│   ├── models/                    # Adapter LLM local
│   ├── prompts/                  # Prompt RAG
│   └── retrieval/                 # BM25, dense retrieval và RRF
├── data/
│   ├── raw/                       # PDF nguồn
│   ├── intent/                    # Dữ liệu intent cơ bản
│   ├── evaluation/                # Dataset Phase 5 và holdout
│   └── processed/                 # Structured JSON sinh tự động
├── models/                        # Model intent đã serialize
├── evaluation/                    # Bộ đánh giá offline cố định
├── scripts/                       # Script train/evaluate Phase 5
├── tests/                         # Unit, regression và AppTest
├── requirements.txt
└── .env.example
```

## Luồng xử lý dữ liệu

```text
PDF chính thức trong data/raw/
        ↓
Structured JSON có metadata và record-level traceability
        ↓
Chunking + embedding
        ↓
ChromaDB
        ↓
Retriever hybrid
        ↓
Evidence selector + deterministic facts + RAG validator
        ↓
Streamlit chat UI
```

`data/raw/manifest.json` lưu checksum, nguồn, năm, trạng thái xác minh và URL chính thức. Chỉ tài liệu đúng năm, đúng trường, có nguồn chính thức và `status=verified` mới được đưa vào runtime corpus.

## Câu hỏi mẫu

- `DHV năm 2026 có những ngành đào tạo nào?`
- `Ngành Công nghệ thông tin có những chương trình nào?`
- `Điểm trúng tuyển ngành Luật là bao nhiêu?`
- `Học phí học kỳ 1 năm 2026 bao nhiêu?`
- `Hồ sơ nhập học cần những gì?`
- `Lịch tuyển sinh năm 2026 như thế nào?`
- `Cho tôi website/cổng tuyển sinh của DHV.`
- `Thời tiết hôm nay thế nào?` — dùng để kiểm tra câu hỏi ngoài phạm vi.

Chatbot hỗ trợ hỏi tiếp trong cùng phiên, ví dụ: `Còn ngành Marketing thì sao?`

## Cộng tác bằng GitHub

Repository: [github.com/SangTranTamLy/ChatBot_DHV](https://github.com/SangTranTamLy/ChatBot_DHV)

Project hiện dùng cách cộng tác đơn giản: các thành viên cùng làm việc trên nhánh `main`.

### Người chỉnh sửa và push code

```powershell
git switch main
git pull origin main

# Sau khi chỉnh sửa, kiểm tra danh sách file trước khi stage
git status
git add .
git status
git commit -m "Mo ta thay doi"
git push origin main
```

### Thành viên khác cập nhật code

Lần đầu tải project:

```powershell
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
cd ChatBot_DHV
```

Những lần sau lấy code mới nhất:

```powershell
git switch main
git pull origin main
```

Nếu thành viên khác cũng có thay đổi riêng, họ cần commit hoặc lưu tạm thay đổi trước khi pull. Sau khi pull thành công, họ có thể chỉnh sửa rồi dùng lại chuỗi `git add`, `git commit` và `git push origin main` ở trên.

Với cách làm chung trên `main`, mỗi người nên pull trước khi bắt đầu và trước khi push để giảm xung đột. Nếu GitHub bật branch protection, cần dùng Pull Request thay cho push trực tiếp.

Không commit các file local hoặc generated:

- `.env`, `.venv/`, `.streamlit/secrets.toml`.
- `data/processed/`, `chroma_db/`.
- `__pycache__/`, `.pytest_cache/`, `tmp*/` và log runtime.
- API key, dữ liệu cá nhân hoặc hồ sơ tuyển sinh cá nhân.

## Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `python` không được nhận diện | Cài Python 3.11+ và mở lại PowerShell. |
| Ollama offline | Mở Ollama Desktop hoặc chạy `ollama serve`. |
| `model not found` | Chạy lại `ollama pull qwen2.5:3b` và `ollama pull nomic-embed-text`. |
| ChromaDB thiếu hoặc rỗng | Chạy lại bước tạo processed data và build ChromaDB với `--reset`. |
| Đã sửa PDF nhưng chatbot chưa đổi | Chạy lại pipeline `prepare_processed_from_raw` rồi build ChromaDB. |
| Git không cho pull vì có thay đổi local | Commit thay đổi, hoặc lưu tạm bằng `git stash` trước khi pull. |

## Phạm vi và quyền riêng tư

- Chatbot chỉ tư vấn trong phạm vi dữ liệu tuyển sinh DHV đã kiểm chứng.
- Không nhập CCCD, số điện thoại, email, địa chỉ hoặc thông tin hồ sơ cá nhân vào khung chat.
- Chatbot không cam kết đậu/trượt, không tra cứu kết quả cá nhân và không đăng ký xét tuyển thay người dùng.
- Khi không có bằng chứng trong knowledge base, chatbot phải nói rõ chưa có dữ liệu.

Nếu câu trả lời khác với thông báo chính thức, ưu tiên thông tin do DHV công bố.
