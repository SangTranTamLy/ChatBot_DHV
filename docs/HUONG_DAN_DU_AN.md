# Hướng dẫn nhanh dự án ChatBot DHV

## 1. Dự án làm gì?

Chatbot **tư vấn tuyển sinh Đại học Hùng Vương TP.HCM (DHV)**. Thí sinh hỏi, ví dụ *"Học phí ngành CNTT bao nhiêu?"*,
bot tìm trong **PDF chính thức của trường** rồi trả lời kèm nguồn.

**Nguyên tắc số 1: không bịa.** Không có dữ liệu thì bot nói "chưa có thông tin".

Cách làm: **tìm tài liệu trước, trả lời sau**. Cách này gọi là **RAG**.

**Ví dụ dễ hình dung:** chatbot giống **một nhân viên tư vấn ngồi cạnh tủ hồ sơ**.

| Nhân viên tư vấn | Chatbot |
|---|---|
| Tủ hồ sơ chứa thông báo của trường | PDF trong `data/raw/` |
| Sắp xếp hồ sơ cho dễ tìm | Chuyển PDF thành kho tìm kiếm |
| Nghe khách hỏi, hiểu khách cần gì | Phân tích câu hỏi |
| Lục tủ lấy đúng tờ giấy | Tìm tài liệu |
| Đọc tờ giấy rồi trả lời | Trả lời (bằng code hoặc AI) |
| Trưởng phòng kiểm tra trước khi nói với khách | Kiểm duyệt câu trả lời |
| Tủ không có giấy nào nói về chuyện đó → "Em chưa có thông tin" | Bot nói "chưa có thông tin", không đoán |

Công nghệ:
- **Streamlit**: giao diện web
- **Ollama + Qwen**: AI chạy ngay trên máy
- **ChromaDB**: kho tìm kiếm theo nghĩa
- **Supabase**: đăng nhập

## 2. Chạy dự án

```bash
source .venv/bin/activate
# Lần đầu, hoặc khi đổi PDF:
python -m src.ingestion.prepare_processed_from_raw            # PDF -> JSON
python -m src.ingestion.build_vector_db --all-years --reset   # JSON -> kho tìm kiếm
streamlit run app.py                                          # mở http://localhost:8501
```

Cần bật Ollama trước. Cấu hình (model AI, năm, key Supabase) nằm trong file `.env`.

## 3. Thư mục chính

```text
app.py            Giao diện web (chat, hồ sơ, trang admin)
src/chatbot/      Bộ não: hiểu câu hỏi -> chọn cách trả lời -> kiểm tra câu trả lời
src/retrieval/    Tìm tài liệu liên quan
src/ingestion/    Đọc PDF, tạo kho tìm kiếm
src/models/       Gọi AI Ollama
data/raw/         PDF gốc + manifest.json  <- nguồn của mọi thông tin
tests/            Kiểm thử tự động
```

## 4. Một câu hỏi đi qua những đâu?

```text
Bạn gõ câu hỏi
 -> app.py              nhận câu hỏi
 -> chat_service.py     LỄ TÂN: chào hỏi thì đáp ngay, câu cũ thì lấy cache,
                        câu nối tiếp ("thế còn ngành Luật?") thì ghép với lịch sử chat
 -> rag_chain.py        TRƯỞNG NHÓM điều phối các bước:
      1. Hiểu câu hỏi: hỏi gì? ngành nào? năm nào?
      2. Ngoài tuyển sinh DHV -> từ chối. Mơ hồ -> hỏi lại.
      3. Tìm tài liệu, lọc giữ phần đúng
      4. Trả lời: câu dạng cố định (điểm, học phí...) thì code tự ghép,
                  câu cần diễn giải thì nhờ AI Qwen viết
      5. Kiểm duyệt: AI bịa số hoặc đưa link lạ -> chặn
 -> app.py              hiện câu trả lời + nguồn
```

AI chỉ là **một bước**. Nhiều câu được trả lời bằng code, và câu trả lời của AI luôn bị kiểm tra lại.

**Ví dụ cụ thể:**

| Bạn hỏi | Bot xử lý thế nào |
|---|---|
| "Xin chào" | Lễ tân đáp ngay, không cần tìm tài liệu |
| "Học phí ngành CNTT năm 2026 bao nhiêu?" | Hiểu là *hỏi học phí*, *ngành CNTT*, *năm 2026* → tìm bảng học phí → **code tự ghép** câu trả lời từ bảng, kèm nguồn |
| "Thế còn ngành Luật?" (hỏi ngay sau câu trên) | Ghép với lịch sử thành *"Học phí ngành Luật năm 2026 bao nhiêu?"* rồi xử lý như trên |
| "Học phí và học bổng ngành CNTT?" | Tách thành 2 câu nhỏ, trả lời từng phần |
| "Trường DHV có những điểm gì nổi bật?" | Câu cần diễn giải → đưa tài liệu cho **AI Qwen viết** → kiểm duyệt rồi mới hiện |
| "Điểm chuẩn Đại học Bách Khoa?" | Hỏi về trường khác → từ chối lịch sự |
| "Hôm nay thời tiết thế nào?" | Ngoài tuyển sinh → từ chối |
| "Ký túc xá DHV giá bao nhiêu?" | Đúng là chuyện của DHV nhưng tài liệu không có → "chưa có thông tin" |

## 5. File quan trọng (đọc theo thứ tự)

| File | Làm gì |
|---|---|
| [chat_service.py](../src/chatbot/chat_service.py) | Lễ tân. Đọc hàm `ChatService.ask()` |
| [rag_chain.py](../src/chatbot/rag_chain.py) | Trưởng nhóm. Đọc hàm `ask_chatbot()` |
| [query_analysis.py](../src/chatbot/query_analysis.py) | Hiểu câu hỏi |
| [retriever.py](../src/retrieval/retriever.py) | Tìm tài liệu |
| [local_llm.py](../src/models/local_llm.py) | Gửi câu hỏi cho AI, nhận câu trả lời |
| [output_validator.py](../src/chatbot/output_validator.py) | Kiểm duyệt câu trả lời |
| [app.py](../app.py) | Giao diện (dài, chỉ đọc phần cần) |

## 6. Trang admin (`?console=admin`)

Mở `http://localhost:8501/?console=admin`. Phần `?console=admin` báo cho app hiện trang quản trị thay cho trang chat.

**Chỉ biết link thì chưa vào được.** Phải đăng nhập bằng tài khoản được cấp quyền admin trên Supabase,
và người dùng không tự cấp quyền này cho mình được.

Trang admin dùng để **xem trạng thái dữ liệu** và **chạy thử câu hỏi**. Nó không sửa được PDF.

**Ví dụ:** giống cửa phòng hiệu trưởng. Ai biết phòng ở đâu cũng đi tới cửa được (biết link),
nhưng chỉ người có chìa khóa mới vào được (tài khoản admin).

## 7. Muốn sửa gì thì mở đâu?

| Muốn sửa | Mở |
|---|---|
| Giao diện | `app.py`, `assets/chat.css` |
| Bot hiểu sai câu hỏi | `query_analysis.py`, `intent_classifier.py` |
| Bot từ chối sai | `scope_guard.py` |
| Tìm sai tài liệu | `retriever.py`, `evidence.py` |
| Sai số học phí / điểm / học bổng | các file `*_formatters.py`, `admission_answers.py` |
| Thêm thông tin mới | bỏ PDF vào `data/raw/` + sửa `manifest.json`, rồi chạy lại 2 lệnh ở mục 2 |
| Đăng nhập | `supabase_auth.py`, `ui_auth.py` |

## 8. Thuật ngữ

- **RAG**: tìm tài liệu trước rồi mới trả lời. *Ví dụ: làm bài thi được mở sách, phải tìm đúng trang rồi mới viết.*
- **Intent**: loại câu hỏi. *Ví dụ: "Học phí bao nhiêu?" → intent `HOI_HOC_PHI`.*
- **Vector / embedding**: dãy số đại diện cho *nghĩa* của câu. *Ví dụ: "tiền học" và "học phí" khác chữ nhưng có vector gần nhau, nên bot vẫn tìm ra.*
- **Prompt**: "đề bài" gửi cho AI. *Ví dụ: "Chỉ dựa vào tài liệu sau, trả lời câu hỏi..."*
- **Cache**: lưu câu trả lời cũ. *Ví dụ: 10 người cùng hỏi "Trường có những ngành nào?", chỉ lần đầu phải tìm, 9 lần sau lấy lại kết quả.*
