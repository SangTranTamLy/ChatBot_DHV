<div align="center">

# 🎓 ChatBot DHV

### Trợ lý tư vấn tuyển sinh Trường Đại học Hùng Vương TP.HCM

Chatbot sử dụng mô hình **RAG** để tìm kiếm và trả lời dựa trên dữ liệu tuyển sinh của trường.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)
![RAG](https://img.shields.io/badge/AI-RAG-6C63FF)

</div>

> **Phạm vi hỗ trợ:** Chatbot chỉ trả lời các câu hỏi liên quan đến tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Các câu hỏi về trường khác hoặc nội dung ngoài phạm vi sẽ được từ chối rõ ràng.

<details>
<summary><strong>📚 Mục lục</strong></summary>

- [1. Giới thiệu dự án](#1-giới-thiệu-dự-án)
- [2. Tính năng](#2-tính-năng)
- [3. Kiến trúc hệ thống](#3-kiến-trúc-hệ-thống)
- [4. Công nghệ sử dụng](#4-công-nghệ-sử-dụng)
- [5. Yêu cầu môi trường](#5-yêu-cầu-môi-trường)
- [6. Cài đặt](#6-cài-đặt)
- [7. Cấu hình môi trường](#7-cấu-hình-môi-trường)
- [8. Chuẩn bị model Ollama](#8-chuẩn-bị-model-ollama)
- [9. Chạy chatbot](#9-chạy-chatbot)
- [10. Xây dựng dữ liệu và ChromaDB](#10-xây-dựng-dữ-liệu-và-chromadb)
- [11. Dataset Phase 5](#11-dataset-phase-5)
- [12. Kiểm thử](#12-kiểm-thử)
- [13. Cấu trúc project](#13-cấu-trúc-project)
- [14. Câu hỏi mẫu](#14-câu-hỏi-mẫu)
- [15. GitHub workflow và file không commit](#15-github-workflow-và-file-không-commit)
- [16. Giới hạn, quyền riêng tư và thông tin nhóm](#16-giới-hạn-quyền-riêng-tư-và-thông-tin-nhóm)

</details>

## 1. Giới thiệu dự án

ChatBot DHV hỗ trợ tra cứu thông tin tuyển sinh năm 2026 như ngành học, phương thức xét tuyển, học phí, điểm chuẩn, hồ sơ và quy trình nhập học.

Chatbot chỉ trả lời trong phạm vi dữ liệu của Trường Đại học Hùng Vương TP.HCM. Các câu hỏi về trường khác hoặc nội dung ngoài tuyển sinh sẽ được từ chối rõ ràng.

## 2. Tính năng

- Tra cứu thông tin tuyển sinh bằng tiếng Việt.
- Tìm kiếm kết hợp BM25 và vector embedding.
- Xếp hạng kết quả bằng RRF.
- Trả lời có kiểm tra bằng nguồn dữ liệu liên quan.
- Từ chối câu hỏi ngoài phạm vi DHV.
- Có giao diện web trực quan bằng Streamlit.
- Có bộ dữ liệu và kịch bản đánh giá chất lượng trả lời.

## 3. Kiến trúc hệ thống

```text
Câu hỏi người dùng
        ↓
Phân tích intent và trường đích
        ↓
Kiểm tra phạm vi câu hỏi
        ↓
Tìm kiếm dữ liệu DHV
        ↓
Evidence và kiểm tra câu trả lời
        ↓
Trả lời hoặc thông báo ngoài phạm vi
```

## 4. Công nghệ sử dụng

- Python
- Streamlit
- Ollama
- ChromaDB
- LangChain
- Qwen `qwen2.5:3b`
- Embedding `nomic-embed-text`
- Tokenizer `BAAI/bge-m3`
- BM25, vector search và Reciprocal Rank Fusion
- Pytest

## 5. Yêu cầu môi trường

- Windows, macOS hoặc Linux.
- Python 3.10 trở lên.
- Ollama đã được cài đặt.
- RAM và dung lượng phù hợp để chạy mô hình ngôn ngữ cục bộ.

## 6. Cài đặt

```powershell
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
cd ChatBot_DHV

python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 7. Cấu hình môi trường

Tạo file cấu hình từ file mẫu:

```powershell
Copy-Item .env.example .env
```

Kiểm tra lại các biến cấu hình trong `.env` nếu cần. Không đưa file `.env` lên GitHub vì có thể chứa thông tin riêng tư hoặc khóa API.

## 8. Chuẩn bị model Ollama

Khởi động Ollama và tải các model cần thiết:

```powershell
ollama serve
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Nếu tokenizer chưa được tải về máy:

```powershell
python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-m3')"
```

## 9. Chạy chatbot

```powershell
streamlit run app.py
```

Sau đó mở trình duyệt tại [http://localhost:8501](http://localhost:8501).

## 10. Xây dựng dữ liệu và ChromaDB

Chuẩn hóa dữ liệu nguồn:

```powershell
python -m src.ingestion.prepare_processed_from_raw
```

Tạo lại cơ sở dữ liệu vector:

```powershell
python -m src.ingestion.build_vector_db `
  --data-dir data/processed `
  --embedding-backend ollama `
  --embedding-model nomic-embed-text `
  --chunk-size 512 `
  --chunk-overlap 50 `
  --tokenizer-model BAAI/bge-m3 `
  --reset
```

Tài liệu được cắt theo token với kích thước 512 token và phần chồng lấn 50 token. Metadata của mỗi đoạn gồm mã đoạn, nguồn, tiêu đề và số token.

## 11. Dataset Phase 5

Dataset Phase 5 gồm 500 câu hỏi - đáp án chuẩn, được dùng để đánh giá chatbot. Dataset được tạo từ file Excel nguồn bằng các lệnh:

```powershell
python scripts/build_phase5_dataset.py
python scripts/evaluate_phase5.py --skip-e2e
```

Kết quả đánh giá được lưu trong `reports/`, còn dữ liệu đánh giá nằm trong `data/evaluation/`.

Project không dùng Q&A sinh tự động để thay thế dữ liệu chuẩn và không fine-tune Qwen. Chatbot sử dụng RAG để truy xuất dữ liệu khi người dùng đặt câu hỏi.

## 12. Kiểm thử

Chạy toàn bộ test:

```powershell
python -m pytest -q
python -m compileall -q src tests
```

Nên chạy kiểm thử sau khi thay đổi logic truy xuất, bộ lọc phạm vi hoặc dữ liệu tuyển sinh.

## 13. Cấu trúc project

```text
ChatBot_DHV/
├── app.py
├── src/
│   ├── chatbot/
│   ├── config/
│   ├── ingestion/
│   ├── models/
│   ├── prompts/
│   └── retrieval/
├── data/
│   ├── raw/
│   ├── processed/
│   └── evaluation/
├── models/
├── scripts/
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## 14. Câu hỏi mẫu

Câu hỏi được hỗ trợ:

- Học phí DHV năm 2026 bao nhiêu?
- Trường có xét học bạ không?
- Điểm chuẩn ngành Công nghệ thông tin là bao nhiêu?
- Hồ sơ nhập học cần những gì?

Câu hỏi bị từ chối:

- Điểm chuẩn Trường Đại học Văn Hiến?
- Học phí Đại học FPT?
- So sánh điểm chuẩn DHV và Văn Hiến?
- Hôm nay trời mưa không?

## 15. GitHub workflow và file không commit

Sau khi cập nhật project:

```powershell
git switch main
git pull origin main
git add src tests README.md
git commit -m "Cap nhat chatbot"
git push origin main
```

Nên phát triển trên branch riêng và tạo Pull Request trước khi gộp vào `main`.

Các file hoặc thư mục sau không nên commit:

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
pytest-cache-files-*/
data/processed/
chroma_db/
*.log
```

## 16. Giới hạn, quyền riêng tư và thông tin nhóm

Chatbot chỉ cung cấp thông tin dựa trên dữ liệu tuyển sinh DHV đã có. Nếu không tìm thấy bằng chứng phù hợp, chatbot cần thông báo chưa có dữ liệu thay vì tự suy đoán.

Thông tin quan trọng như điểm chuẩn, học phí và thời hạn nộp hồ sơ nên được kiểm tra lại trên kênh chính thức của nhà trường. Không nhập CCCD, số điện thoại, email hoặc thông tin cá nhân nhạy cảm vào chatbot.

> Đây là đồ án được thực hiện với mục đích học tập và nghiên cứu.

### 👥 Nhóm 4

- Đặng Đinh Đức Độ
- Đoàn Quang Khang
- Hồ Viết Bảo
- Châu Thanh Sang
