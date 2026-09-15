Kiến trúc hệ thống Chatbot tư vấn tuyển sinh DHV

1. Tên đề tài

Xây dựng Chatbot AI hỗ trợ tư vấn tuyển sinh Trường Đại học Hùng Vương
TP.HCM

2. Mục tiêu

Xây dựng hệ thống chatbot bằng Python, cho phép thí sinh và phụ huynh
đặt câu hỏi bằng tiếng Việt về tuyển sinh. Chatbot truy xuất thông tin
từ nguồn dữ liệu tuyển sinh đã được chuẩn bị và kiểm chứng trước khi sử
dụng mô hình ngôn ngữ để tổng hợp câu trả lời.

3. Stack công nghệ đã chốt

Thành phần         Công nghệ

Ngôn ngữ chính     Python
Website chatbot    Streamlit
AI Framework       LangChain
LLM                Ollama
RAG                LangChain Retrieval
Vector Database    ChromaDB
Embedding          Ollama Embedding hoặc Sentence Transformers
Nguồn dữ liệu      Website, PDF, DOCX tuyển sinh chính thức
Quản lý mã nguồn   Git + GitHub

4. Kiến trúc hệ thống

Người dùng
    ↓
Website Streamlit
    ↓
LangChain
    ↓
Retriever
    ↓
ChromaDB
    ↓
Context liên quan
    ↓
Ollama
    ↓
Câu trả lời
    ↓
Streamlit hiển thị

5. Luồng chuẩn bị dữ liệu

Website tuyển sinh + PDF + DOCX + tài liệu chính thức
                        ↓
                    Thu thập
                        ↓
                 Kiểm tra nguồn
                        ↓
              Làm sạch / chuẩn hóa
                        ↓
             Loại trùng / lỗi thời
                        ↓
                      Chunk
                        ↓
                    Metadata
                        ↓
                    Embedding
                        ↓
                    ChromaDB

Metadata nên lưu: tên tài liệu, nguồn/URL, nhóm nội dung, năm hoặc phiên
bản, loại tài liệu và nội dung chunk.

6. Luồng xử lý câu hỏi

Người dùng nhập câu hỏi tiếng Việt trên Streamlit.

Streamlit chuyển câu hỏi vào pipeline LangChain.

Retriever truy xuất dữ liệu liên quan trong ChromaDB.

ChromaDB trả về các chunk và metadata phù hợp.

LangChain đưa câu hỏi cùng context cho mô hình chạy qua Ollama.

Ollama tổng hợp câu trả lời dựa trên context.

Hệ thống trả câu trả lời và nguồn về Streamlit.

Nếu thiếu dữ liệu, câu hỏi mơ hồ hoặc ngoài phạm vi, hệ thống sử
dụng fallback thay vì tự suy đoán.

7. Nguyên tắc

Chỉ sử dụng dữ liệu tuyển sinh đã được kiểm tra và xác minh.

Ưu tiên thông tin hiện hành; quản lý rõ năm/phiên bản.

Không tự suy đoán khi nguồn dữ liệu không cung cấp thông tin.

Không đủ dữ liệu hoặc ngoài phạm vi thì fallback.

Câu hỏi mơ hồ thì yêu cầu làm rõ.

Không xử lý dữ liệu cá nhân hoặc dữ liệu nhạy cảm.

Không dự đoán đậu/trượt hoặc đưa ra quyết định tuyển sinh.

Không sử dụng Agent nếu workflow RAG hiện tại đã đáp ứng yêu cầu.

Website và chatbot sử dụng Python để đơn giản hóa phát triển và tích
hợp.

8. Cấu trúc project dự kiến

chatbot-tuyen-sinh-dhv/
├── app.py
├── rag/
│   ├── loader.py
│   ├── chunking.py
│   ├── embedding.py
│   ├── retriever.py
│   └── chatbot.py
├── data/
│   ├── raw/
│   │   ├── website/
│   │   ├── pdf/
│   │   └── docx/
│   └── processed/
├── vector_db/
├── tests/
├── docs/
│   ├── project_scope.md
│   └── architecture.md
├── requirements.txt
├── README.md
└── .gitignore

9. Definition of Done -- T02

T02 được xem là hoàn thành khi: - Cả nhóm thống nhất Python +
Streamlit + LangChain + Ollama + ChromaDB. - Thống nhất luồng Người
dùng → Streamlit → LangChain → Retriever → ChromaDB → Context → Ollama →
Câu trả lời → Streamlit. - Thống nhất nguồn dữ liệu gồm website và tài
liệu tuyển sinh chính thức như PDF/DOCX. - Có luồng chuẩn bị dữ liệu
trước khi đưa vào Vector Database. - Có nguyên tắc fallback khi không
tìm thấy nguồn hoặc ngoài phạm vi. - Cả 4 thành viên hiểu kiến trúc và
phần việc liên quan.s