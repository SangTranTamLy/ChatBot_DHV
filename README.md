# DHV Admissions Chatbot

> Trợ lý AI giúp tra cứu thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM (DHV) từ tài liệu chính thức đã xác minh.

Ứng dụng chạy cục bộ bằng Streamlit, dùng Ollama để tạo câu trả lời và ChromaDB để tìm kiếm tài liệu. Khi không có bằng chứng phù hợp, chatbot được thiết kế để báo chưa có thông tin thay vì tự suy đoán.

## Mục lục

- [Tổng quan](#tong-quan)
- [Công nghệ](#cong-nghe)
- [Bắt đầu nhanh](#bat-dau-nhanh)
- [Cấu hình](#cau-hinh)
- [Tài khoản Supabase](#tai-khoan-supabase)
- [Khu quản trị](#khu-quan-tri)
- [Dữ liệu, huấn luyện và đánh giá](#du-lieu-huan-luyen-va-danh-gia)
- [Kiểm thử](#kiem-thu)
- [Cấu trúc dự án](#cau-truc-du-an)
- [Giới hạn và bảo mật](#gioi-han-va-bao-mat)

## Tổng quan

Chatbot hỗ trợ các câu hỏi về:

- Ngành và chương trình đào tạo.
- Phương thức, điều kiện và điểm xét tuyển.
- Học phí, các khoản thu và học bổng.
- Hồ sơ, thủ tục và quyền lợi nhập học.
- Thông tin chung về DHV.

Luồng trả lời kết hợp phân tích câu hỏi, kiểm tra phạm vi, tìm kiếm từ khóa và vector, lọc bằng chứng rồi mới tạo câu trả lời. Khu quản trị là một trang riêng, chỉ tài khoản được cấp vai trò admin mới truy cập được.

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Giao diện | Streamlit |
| Mô hình trả lời | Ollama, mặc định trong mẫu là Qwen 2.5 7B |
| Tìm kiếm ngữ nghĩa | ChromaDB và Sentence Transformers |
| Xác thực, hồ sơ và đổi mật khẩu | Supabase Auth và PostgreSQL |
| Kiểm thử | Pytest |

Python `3.12` được khuyến nghị. Python `3.10` trở lên được hỗ trợ.

## Bắt đầu nhanh

### 1. Tạo môi trường Python

Windows PowerShell:

~~~powershell
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
Set-Location ChatBot_DHV
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
~~~

macOS hoặc Linux:

~~~bash
git clone https://github.com/SangTranTamLy/ChatBot_DHV.git
cd ChatBot_DHV
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
~~~

Nếu PowerShell không cho kích hoạt môi trường, chỉ áp dụng chính sách cho cửa sổ hiện tại:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
~~~

### 2. Cài và chạy Ollama

Cài Ollama từ [ollama.com](https://ollama.com/), sau đó tải model khớp với biến `OLLAMA_MODEL` trong file `.env`:

~~~bash
ollama pull qwen2.5:7b-instruct-q4_0
~~~

Ollama thường tự chạy nền. Nếu chưa chạy, mở một terminal riêng và chạy:

~~~bash
ollama serve
~~~

Máy cấu hình thấp có thể đổi OLLAMA_MODEL thành qwen2.5:3b trong .env rồi tải model đó bằng ollama pull qwen2.5:3b.

### 3. Tạo dữ liệu truy xuất lần đầu

PDF nguồn và manifest nằm trong data/raw/. Các tệp JSON đã xử lý và ChromaDB được sinh cục bộ, không lưu trong Git. Chạy từ thư mục gốc dự án:

~~~bash
python -m src.ingestion.prepare_processed_from_raw
python -m src.ingestion.build_vector_db --all-years --reset
~~~

Lệnh đầu trích xuất và kiểm tra các tài liệu nguồn. Lệnh thứ hai tạo lại ChromaDB từ tài liệu đã xác minh. Tùy chọn `--reset` xóa vector store đang cấu hình trước khi xây lại; không chạy lệnh này khi chỉ muốn khởi động ứng dụng.

Nếu chỉ cần năm mặc định, có thể xây collection cho `TARGET_YEAR` bằng:

~~~bash
python -m src.ingestion.build_vector_db --reset
~~~

Mẫu `.env` đặt `TARGET_YEAR=2026`. Dùng `--all-years` để đưa các năm có trong nguồn vào cùng collection; câu hỏi lịch sử nên nêu rõ năm.

### 4. Khởi động ứng dụng

~~~bash
streamlit run app.py
~~~

Mở địa chỉ Streamlit in ra trong terminal, mặc định là http://localhost:8501.

## Cấu hình

Sao chép .env.example thành .env rồi chỉnh các giá trị phù hợp với máy. Các biến thường dùng:

| Biến | Giá trị trong mẫu | Mục đích |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Địa chỉ Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct-q4_0` | Model tạo câu trả lời |
| `OLLAMA_TIMEOUT_SECONDS` | `90` | Thời gian chờ model |
| `EMBEDDING_BACKEND` | `sentence-transformers` | Backend tạo embedding |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Model embedding |
| `TARGET_YEAR` | `2026` | Năm dữ liệu mặc định |
| `RETRIEVER_TOP_K` | `4` | Số kết quả truy xuất |
| `CHROMA_PERSIST_DIR` | `chroma_db` | Thư mục lưu vector store |
| `CHROMA_COLLECTION` | `dhv_admissions_2026` | Tên collection |
| `PROCESSED_DATA_DIR` | `data/processed` | Thư mục JSON đã xử lý |
| `SUPABASE_URL` | để trống | URL của dự án Supabase |
| `SUPABASE_PUBLISHABLE_KEY` | để trống | Publishable key dùng cho ứng dụng |
| `SUPABASE_ANON_KEY` | để trống | Tên biến tương thích ngược với anon key |

Nếu dùng Ollama làm embedding thay cho Sentence Transformers, đặt EMBEDDING_BACKEND=ollama, đổi EMBEDDING_MODEL thành nomic-embed-text, tải model bằng ollama pull nomic-embed-text và xây lại ChromaDB.

Chatbot có thể chạy ở chế độ khách khi chưa cấu hình Supabase. Supabase là cần thiết cho đăng ký, đăng nhập, hồ sơ cá nhân, đổi mật khẩu và quyền admin.

## Tài khoản Supabase

### Cấu hình ban đầu

1. Tạo dự án Supabase và điền SUPABASE_URL cùng SUPABASE_PUBLISHABLE_KEY vào .env.
2. Trong Supabase SQL Editor, chạy migration [20261024000000_create_profiles.sql](supabase/migrations/20261024000000_create_profiles.sql) một lần để tạo hồ sơ, trigger và chính sách RLS.
3. Trong Authentication → Sign In / Providers, bật đăng ký Email và mật khẩu. Cấu hình hiện tại tắt xác nhận email để phù hợp bản demo; người đăng ký chưa phải chứng minh quyền sở hữu email.
4. Trong Authentication → URL Configuration, thêm URL sau vào danh sách Redirect URLs để dùng luồng quên mật khẩu khi chạy cục bộ:

   http://localhost:8501/?auth=recovery

Không đưa service-role/secret key vào .env của ứng dụng hoặc mã nguồn. Chỉ dùng publishable key; ứng dụng không cần quyền vượt RLS để thao tác tài khoản thông thường.

### Đăng nhập và khôi phục mật khẩu

Người dùng đăng ký bằng tên, email và mật khẩu; hồ sơ tên được tạo trong public.profiles. Email thuộc Supabase Auth, mật khẩu do Supabase Auth quản lý dưới dạng hash và không được lưu trong bảng hồ sơ.

Luồng quên mật khẩu gửi liên kết qua email. Giao diện luôn dùng cùng một thông báo để không tiết lộ email nào đã đăng ký; email không có tài khoản sẽ không nhận liên kết. Email thử nghiệm có thể bị giới hạn bởi SMTP mặc định của Supabase; xem [hướng dẫn SMTP](https://supabase.com/docs/guides/auth/auth-smtp) nếu cần gửi đến địa chỉ ngoài phạm vi dự án.

## Khu quản trị

Khu quản trị không có liên kết từ giao diện chatbot. Mở trực tiếp:

http://localhost:8501/?console=admin

Sau đó đăng nhập bằng tài khoản Supabase đã được quản trị viên cấp vai trò admin. Ứng dụng chỉ tin app_metadata.role; không cấp quyền bằng user_metadata.

Để cấp quyền cho tài khoản, chạy trong Supabase SQL Editor và thay địa chỉ mẫu bằng email admin:

~~~sql
update auth.users
set raw_app_meta_data =
    coalesce(raw_app_meta_data, '{}'::jsonb) || '{"role":"admin"}'::jsonb
where lower(email) = lower('admin@example.com');
~~~

Kiểm tra câu lệnh chỉ cập nhật đúng một tài khoản. Admin cần đăng xuất rồi đăng nhập lại để tải vai trò mới. Để gỡ quyền, chạy:

~~~sql
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) - 'role'
where lower(email) = lower('admin@example.com');
~~~

Trang quản trị hiện phục vụ kiểm tra trạng thái dữ liệu và chạy thử câu hỏi qua pipeline; không chỉnh sửa trực tiếp tài liệu nguồn.

## Dữ liệu, huấn luyện và đánh giá

### Nguồn kiến thức

- data/raw/ chứa PDF tuyển sinh DHV và manifest ghi nguồn, năm, trạng thái xác minh.
- data/processed/ chứa JSON được sinh từ PDF; đây là dữ liệu cục bộ.
- chroma_db/ chứa vector store được xây từ JSON đã kiểm tra.

Chỉ tài liệu được xác minh, thuộc DHV và đáp ứng quy tắc nguồn mới được nạp vào bộ truy xuất.

### Dữ liệu huấn luyện và ví dụ trả lời

- data/intent/samples.jsonl chứa câu hỏi đã gán nhãn để huấn luyện bộ nhận diện intent. Chạy python -m src.chatbot.train_intent_model để sinh lại train/test và model.
- data/training/response_examples.jsonl chứa ví dụ hỗ trợ cách diễn đạt. Các ví dụ này không thay thế bằng chứng truy xuất và không dùng để học thuộc số liệu.
- data/evaluation/qa_master_500.jsonl là bộ 500 câu dùng đánh giá/regression, không phải dữ liệu fine-tune Qwen.

Bộ 500 câu chuẩn hóa xuất phát từ data/evaluation/raw/Nhóm 4_Thu_Thap_Q&A.xlsx. Quy trình và quy tắc dữ liệu được mô tả trong [data/evaluation/README.md](data/evaluation/README.md).

### Đánh giá offline

evaluation/ chứa bộ dev/holdout nhỏ để kiểm tra hợp đồng truy xuất và trả lời. Chạy báo cáo từ thư mục gốc:

~~~bash
python -m evaluation.run_evaluation --split all
~~~

Kết quả đánh giá cục bộ được ghi vào reports/ và không commit.

## Kiểm thử

Chạy unit và regression tests:

~~~bash
python -m pytest tests -q
~~~

Chạy riêng các kiểm thử xác thực Supabase:

~~~bash
python -m pytest tests/test_supabase_auth_service.py tests/test_ui_auth.py -q
~~~

## Cấu trúc dự án

~~~text
app.py                         Giao diện Streamlit và điều hướng
assets/                        CSS giao diện
static/                        Ảnh, font và tài nguyên tĩnh
src/chatbot/                   Phân tích câu hỏi, truy xuất và tạo câu trả lời
src/retrieval/                 Tìm kiếm và lọc bằng chứng
src/ingestion/                 Đọc PDF, tạo JSON và xây ChromaDB
src/models/                    Kết nối Ollama
src/config/                    Đọc cấu hình
src/ui_auth.py                 Giao diện xác thực
src/supabase_auth.py           Tích hợp Supabase Auth
supabase/migrations/            Migration hồ sơ và RLS
data/raw/                       PDF nguồn và manifest
data/processed/                 JSON sinh cục bộ
data/intent/                    Mẫu và nhãn nhận diện intent
data/training/                  Ví dụ diễn đạt
data/evaluation/                Bộ câu hỏi đánh giá
evaluation/                     Công cụ đánh giá offline
models/                         Model intent
scripts/                        Công cụ kiểm tra và đánh giá
tests/                          Unit và regression tests
~~~

## Giới hạn và bảo mật

- Dự án đang trong giai đoạn phát triển; cần đánh giá và cấu hình thêm trước khi dùng production.
- Chatbot chỉ tra cứu dữ liệu DHV đã nạp. Thông tin quan trọng cần đối chiếu các kênh chính thức của trường.
- Không nhập CCCD, mật khẩu, số điện thoại hoặc thông tin cá nhân nhạy cảm vào câu hỏi.
- .env, Supabase secret key, dữ liệu sinh cục bộ, ChromaDB và báo cáo riêng không được commit.
- Tắt xác nhận email là lựa chọn cho bản demo, không xác thực quyền sở hữu địa chỉ email.
