# ChatBot DHV

> Trợ lý tra cứu thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM.

Chatbot chạy cục bộ bằng Streamlit, Ollama và ChromaDB. Câu trả lời được tạo từ dữ liệu DHV đã xác minh; nếu không có evidence phù hợp, bot cần báo chưa có thông tin thay vì tự đoán.

## Chức năng

- Tra cứu thông tin trường/website DHV, ngành/chương trình, phương thức và điều kiện xét tuyển, điểm, học phí, học bổng, hồ sơ và nhập học.
- Phân tích ý định, trường, năm và ngữ cảnh câu hỏi; hỗ trợ tách một số câu hỏi nhiều ý trước khi tìm dữ liệu.
- Tìm kiếm kết hợp từ khóa BM25 và vector, sau đó lọc evidence trước khi tạo câu trả lời.
- Chặn câu hỏi trường ngoài hoặc ngoài phạm vi trước khi truy xuất dữ liệu DHV.

## Luồng xử lý

```text
Câu hỏi
  → Nhận diện ý định, trường, năm và ngữ cảnh
  → Kiểm tra phạm vi an toàn
  → Tách câu phức tạp khi phù hợp
  → Tìm kiếm BM25 + vector trong ChromaDB
  → Lọc và kiểm tra evidence
  → Qwen trả lời hoặc báo chưa có dữ liệu
```

## Công nghệ

- Python 3.10 trở lên (khuyến nghị Python 3.12)
- Streamlit
- Ollama: model trong `.env` (mẫu dùng `qwen2.5:7b-instruct-q4_0`; máy nhẹ có thể dùng `qwen2.5:3b`)
- Embedding: mẫu dùng Sentence Transformers `paraphrase-multilingual-MiniLM-L12-v2`; hỗ trợ Ollama nếu Chroma được xây với backend đó
- ChromaDB, BM25, RRF và Pytest

## Cài đặt và chạy trên Windows

Tải project và mở PowerShell tại thư mục vừa tải:

```powershell
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
Set-Location ChatBot_DHV
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Nếu PowerShell chặn kích hoạt môi trường, chỉ áp dụng cho cửa sổ hiện tại rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Ollama

Trên Windows, Ollama có thể đã chạy nền. Nếu chưa chạy, mở terminal riêng và chạy:

```powershell
ollama serve
```

Ở terminal khác, kiểm tra/tải model:

```powershell
ollama list
ollama pull qwen2.5:7b-instruct-q4_0
```

Tải model đúng với `OLLAMA_MODEL` trong `.env`. Nếu dùng embedding Ollama, tải thêm model tương ứng với `EMBEDDING_MODEL`; cấu hình mẫu dùng Sentence Transformers nên không cần tải `nomic-embed-text` qua Ollama.

Nếu `ollama serve` báo cổng `11434` đã được sử dụng, thường là Ollama đã chạy; kiểm tra bằng `ollama list`, không cần mở thêm server.

## Dữ liệu lần chạy đầu

Các file nguồn gồm PDF trong `data/raw/` và `data/raw/manifest.json`. `data/processed/` và `chroma_db/` là dữ liệu sinh cục bộ, không được lưu trong Git; vì vậy một bản clone mới cần tạo chúng trước khi chạy chatbot.

```powershell
python -m src.ingestion.prepare_processed_from_raw
python -m src.ingestion.build_vector_db --all-years --reset
```

**Lưu ý:** lệnh trích xuất mặc định làm mới thư mục JSON đầu ra. `--reset` ở lệnh xây Chroma sẽ đặt lại vector store được cấu hình trong `.env`. Chỉ chạy khi chủ động tái tạo dữ liệu; không cần chạy lại mỗi lần mở chatbot.

- Mặc định project dùng `TARGET_YEAR=2026`.
- Nếu chỉ lập chỉ mục năm mặc định, dùng `python -m src.ingestion.build_vector_db --reset`.
- Dùng `--all-years` nếu cần tra cứu cả dữ liệu 2024 và 2026. Dữ liệu học phí 2024 chỉ áp dụng cho câu hỏi năm 2024.
- Loader chỉ nạp tài liệu đã xác minh, đúng năm, đúng trường và có nguồn hợp lệ.

## Cấu hình

Các giá trị mặc định nằm trong `.env.example`; chỉnh trong `.env` nếu môi trường của bạn khác.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Địa chỉ Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct-q4_0` | Model trả lời |
| `EMBEDDING_BACKEND` | `sentence-transformers` | Backend embedding |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Model embedding |
| `TARGET_YEAR` | `2026` | Năm dữ liệu mặc định |
| `PROCESSED_DATA_DIR` | `data/processed` | JSON đã xử lý |
| `CHROMA_PERSIST_DIR` | `chroma_db` | Vector store cục bộ |
| `CHROMA_COLLECTION` | `dhv_admissions_2026` | Tên collection |

## Khởi động giao diện

Từ thư mục gốc, sau khi môi trường và dữ liệu đã sẵn sàng:

```powershell
streamlit run app.py
```

Mở địa chỉ được Streamlit hiển thị, mặc định là <http://localhost:8501>.

## Kiểm thử

```powershell
python -m pytest tests -q
python -m compileall -q src tests
```

Bộ 500 câu tại `data/evaluation/qa_master_500.jsonl` dùng để đánh giá/regression, không phải dữ liệu để chatbot học thuộc hay fine-tune model.

## Ví dụ câu hỏi

- `DHV xét tuyển bằng những phương thức nào?`
- `Điều kiện xét tuyển học bạ năm 2026 là gì?`
- `Học phí DHV năm 2024 bao nhiêu?`
- `Hồ sơ nhập học cần những gì?`

## Cấu trúc chính

```text
app.py                 Giao diện Streamlit
src/chatbot/           Phân tích câu hỏi, state, điều phối RAG và trả lời
src/retrieval/         Tìm kiếm, hợp nhất và lọc kết quả
src/ingestion/         Trích xuất, kiểm tra JSON và xây ChromaDB
src/prompts/           Prompt cho model
src/models/            Kết nối model cục bộ
data/raw/              PDF nguồn và manifest
data/processed/        JSON sinh từ PDF (local, không commit)
data/evaluation/       Dataset đánh giá chuẩn
chroma_db/             Vector store (local, không commit)
scripts/               Công cụ audit, kiểm tra và đánh giá
tests/                 Unit/regression tests
```

## Phạm vi và giới hạn

- Chỉ trả lời theo dữ liệu DHV đã xác minh; trường ngoài phạm vi được chặn, dữ liệu thiếu thì bot báo chưa có thông tin.
- Năm mặc định là 2026. Để hỏi dữ liệu lịch sử, nêu rõ năm trong câu hỏi; hội thoại kế thừa năm cũ hiện vẫn cần QA kiểm tra thêm.
- Project đang trong giai đoạn phát triển và kiểm thử, chưa có xác nhận QA cuối cùng để dùng production.
- Không nhập CCCD, số điện thoại, email hoặc thông tin cá nhân nhạy cảm vào chatbot. Với thông tin quan trọng, hãy đối chiếu kênh chính thức của trường.

`.env`, môi trường Python, JSON đã xử lý, ChromaDB và `reports/` là file/thư mục cục bộ được loại khỏi Git. Không đưa khóa bí mật lên GitHub.
