# 🎓 ChatBot DHV – Trợ lý tư vấn tuyển sinh

<div align="center">

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)
![LangChain](https://img.shields.io/badge/RAG-LangChain-1C3C1C.svg)
![Ollama](https://img.shields.io/badge/LLM-Local%20Ollama-orange.svg)
![ChromaDB](https://img.shields.io/badge/Vector%20DB-ChromaDB-5B21B6.svg)
![Knowledge Base](https://img.shields.io/badge/Knowledge%20Base-DHV%202026-0F766E.svg)

**Chatbot AI hỗ trợ tra cứu thông tin tuyển sinh đã được kiểm chứng của Trường Đại học Hùng Vương TP.HCM (DHV).**

[Tính năng](#-tính-năng) • [Kiến trúc](#-kiến-trúc) • [Cài đặt](#-cài-đặt-và-khởi-chạy) • [Kiểm thử](#-kiểm-thử-và-đánh-giá)

</div>

---

## 📖 Giới thiệu

**ChatBot DHV** là ứng dụng hỏi đáp tiếng Việt theo kiến trúc Retrieval-Augmented Generation (RAG). Người dùng đặt câu hỏi tự nhiên về tuyển sinh DHV năm 2026; hệ thống truy xuất dữ liệu đã được kiểm chứng rồi dùng mô hình chạy cục bộ để tạo câu trả lời.

Project phục vụ học tập, nghiên cứu và thực hành kỹ thuật AI/RAG. Chatbot không phải kênh tư vấn tuyển sinh chính thức và không đại diện cho DHV.

## 🚀 Tính năng

- Tra cứu ngành, chương trình đào tạo, phương thức xét tuyển, điểm, học phí, học bổng, hồ sơ, lịch tuyển sinh, nhập học và thông tin liên hệ.
- Phân tích intent, entity, năm dữ liệu và phạm vi câu hỏi bằng logic deterministic.
- Phân biệt DANH_SACH_NGANH với DANH_SACH_CHUONG_TRINH.
- Lọc chương trình theo parent_major và đếm catalog bằng Python từ structured evidence.
- Conversation state dạng bounded slots cho các câu hỏi follow-up.
- Chạy local với Ollama, ChromaDB và không yêu cầu API key AI bên ngoài.
- Grounding validator kiểm tra entity, số liệu, ngày tháng, quan hệ ngành – chương trình và fallback khi evidence không đủ.

Metadata nguồn được giữ ở backend để audit. UI hiện tại chỉ hiển thị nội dung trả lời, không hiển thị source cards hoặc URL nguồn.

## 🏗️ Kiến trúc

~~~mermaid
flowchart TD
    User([Người dùng]) --> UI[Streamlit UI - app.py]
    UI --> Service[ChatService]
    Service --> Scope[Scope Guard]
    Scope --> Analysis[Query Analysis + Conversation State]
    Analysis --> Retriever[DHV Retriever]
    Retriever --> Chroma[(ChromaDB)]
    Chroma --> Evidence[Evidence Builder]
    Evidence --> Catalog{Catalog request?}
    Catalog -- Có --> Deterministic[Filter + Deduplicate + Count]
    Catalog -- Không --> Prompt[RAG Prompt Builder]
    Prompt --> Ollama[Ollama - qwen2.5:3b]
    Ollama --> Validator[Output Validator]
    Deterministic --> Answer[Answer + State]
    Validator --> Answer
    Answer --> UI
~~~

~~~text
User question
    ↓ normalize
intent / entity / conversation state
    ↓ scope guard và retrieval plan
verified Chroma documents
    ↓ evidence và structured facts
catalog deterministic hoặc RAG generation
    ↓ grounding validation
Streamlit answer
~~~

## 🔄 Pipeline dữ liệu

Nguồn dữ liệu được tách thành hai lớp:

- data/raw/: PDF tuyển sinh DHV dùng để lưu trữ và đối chiếu.
- data/processed/: Markdown sinh từ RAW, có YAML metadata và chỉ được index khi status là verified.

Pipeline build index:

~~~text
PDF trong data/raw/
        ↓
Trích xuất và chuẩn hóa
        ↓
Markdown có YAML metadata
        ↓
Loader lọc verified và đúng năm
        ↓
Heading-aware chunking
        ↓
Embedding
        ↓
ChromaDB
~~~

Metadata quan trọng gồm title, category, year, school, source_url, source_date, document_type và status. URL nguồn chỉ được lấy từ metadata backend; LLM không tự tạo URL.

## 📁 Cấu trúc thư mục

~~~text
ChatBot_DHV/
├── app.py                              # Streamlit entrypoint
├── data/raw/                           # PDF nguồn DHV
├── data/processed/                     # Markdown verified sinh từ RAW
├── chroma_db/                          # ChromaDB local sinh khi build
├── docs/                               # Scope và architecture documents
├── src/config/settings.py              # Cấu hình project
├── src/ingestion/                      # Load, chuẩn hóa, chunk và build index
├── src/retrieval/retriever.py          # Chroma retrieval + keyword rerank
├── src/prompts/rag_prompt.py           # Prompt grounded bằng context
├── src/models/local_llm.py             # Ollama adapter
├── src/chatbot/                        # Service, analysis, evidence, chain, validator
├── tests/                              # Unit và regression tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
~~~

## ⚙️ Cài đặt và khởi chạy

Yêu cầu: Python 3.11+, Ollama chạy tại http://localhost:11434 và đủ dung lượng cho model cùng ChromaDB.

### 1. Cài môi trường Python

Windows PowerShell:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Nếu không activate được:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

macOS/Linux:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

### 2. Chuẩn bị Ollama

~~~bash
ollama serve
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
ollama list
~~~

Embedding model phải giống nhau giữa lúc build và lúc query. Nếu thay đổi model, cần build lại ChromaDB.

### 3. Tạo processed data và build index

~~~bash
python -m src.ingestion.prepare_processed_from_raw
python -m src.ingestion.build_vector_db --embedding-backend ollama --reset
~~~

Chỉ Markdown có YAML hợp lệ, status verified và đúng TARGET_YEAR mới được loader đưa vào ChromaDB. data/processed/ và chroma_db/ là dữ liệu sinh local, không commit.

Kiểm tra retrieval:

~~~bash
python -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text
python -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text
~~~

### 4. Chạy chatbot

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
~~~

Hoặc khi môi trường ảo đã được activate:

~~~bash
streamlit run app.py
~~~

Mở http://localhost:8501.

## 🧾 Cấu hình mặc định

~~~env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL=nomic-embed-text
CHROMA_PERSIST_DIR=chroma_db
CHROMA_COLLECTION=dhv_admissions_2026
PROCESSED_DATA_DIR=data/processed
RETRIEVER_TOP_K=4
TARGET_YEAR=2026
RAG_MAX_CONTEXT_CHARS=12000
~~~

## 🧪 Kiểm thử và đánh giá

~~~bash
python -m compileall -q src tests
python -m unittest discover -s tests -p "test_*.py" -v
~~~

Test suite bao phủ app boundary, Streamlit session state, loader YAML, verified filtering, chunking, retrieval, metadata, intent, scope guard, conversation state, prompt, grounding và catalog ngành/chương trình.

Corpus fixture hiện tại xác nhận 20 ngành chính, 47 quan hệ program_name – parent_major và 5 chương trình thuộc Công nghệ thông tin. Đây là dữ liệu kiểm thử theo corpus hiện tại; business logic không hard-code riêng cho ngành nào.

## 📚 Nguyên tắc dữ liệu và giới hạn

- Chỉ dùng nguồn tuyển sinh chính thức của DHV đã được kiểm chứng.
- Ưu tiên knowledge base năm 2026.
- Không đưa RAW trực tiếp vào ChromaDB.
- Không suy đoán deadline, học phí, học bổng, điều kiện hoặc URL khi evidence không có.
- Không lưu CCCD, số điện thoại, email, địa chỉ hoặc hồ sơ cá nhân.
- Không dự đoán hoặc cam kết đậu/trượt.
- Không tra cứu kết quả tuyển sinh cá nhân.
- Không đăng ký xét tuyển hoặc nhập học thay người dùng.

Khi thiếu dữ liệu:

> Hiện tại tôi chưa tìm thấy thông tin này trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM.

Khi ngoài phạm vi:

> Xin lỗi, tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh Trường Đại học Hùng Vương TP.HCM.

## 🛠️ Quy trình thay đổi

~~~text
RAW / source verification → prepare processed → validate metadata
→ build ChromaDB → smoke tests → full regression → review UI behavior
~~~

Khi thay đổi code, giữ ranh giới giữa UI, service, retrieval, ingestion, model, evidence và validator. Không sửa knowledge base để che lỗi logic.

---

Nếu có khác biệt giữa chatbot và thông báo chính thức, hãy ưu tiên thông tin do DHV công bố.
