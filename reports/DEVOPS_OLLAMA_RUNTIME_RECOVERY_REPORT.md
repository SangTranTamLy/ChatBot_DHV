# DEVOPS / SRE REPORT — LOCAL OLLAMA RUNTIME RECOVERY

**Ngày kiểm tra:** 2026-10-11 (+07:00)  
**Phạm vi:** Khôi phục Ollama local phục vụ QA live retest; chỉ đọc dữ liệu ứng dụng/Chroma.  
**Deployment target:** Local — không deploy.

## 1. Deployment Target

- Target: máy phát triển Windows local.
- Không deploy lên staging/production, không publish và không thay đổi hạ tầng từ xa.
- Mục tiêu là làm endpoint Ollama và hai model đã cài sẵn sẵn sàng cho QA chạy live chatbot retest.

## 2. Pre-deployment Checks

### QA status trước khi xử lý

Đã đọc `reports/QA_CHATBOT_FUP_SECURITY_RETEST_REPORT.md` trước khi kiểm tra runtime.

- QA verdict hiện có: `BLOCKED` vì Ollama không truy cập được; QA ghi nhận các kiểm tra offline/controlled và regression suites đạt.
- QA report ghi targeted suites: 192 passed; full pytest: 294 passed, 4 skipped, 0 failed.
- Các con số trên là kết quả do QA report cung cấp, không phải test do DevOps chạy lại. Việc khôi phục runtime không xác nhận factual QA PASS.

### Process, endpoint và nguyên nhân quyền socket

1. Lượt kiểm tra trong sandbox không đọc được CIM (`Access to a CIM resource was not available`) và request tới `127.0.0.1:11434` bị Windows trả về socket permission error.
2. Kiểm tra host-level read-only sau đó cho thấy không có `ollama.exe`, không có listener trên cổng 11434; HTTP trả `actively refused`. Điều này xác nhận Ollama thực sự đang dừng tại thời điểm kiểm tra host, không chỉ là lỗi sandbox.
3. Khi gọi client `ollama list`, Ollama Desktop hiện có tự khởi chạy theo cơ chế Windows on-demand. Không tải/cài/cập nhật Ollama và không pull model.
4. Sau khi khởi chạy, process `ollama.exe` PID 24528 lắng nghe trên `127.0.0.1:11434`; health endpoint hoạt động.

**Kết luận nguyên nhân:** Có cả hai hiện tượng ở hai lớp khác nhau: sandbox ban đầu chặn socket/CIM; đồng thời host thực tế chưa có Ollama server chạy. Host-level refusal trước khi startup là bằng chứng xác nhận service đang dừng.

### Dependencies, cấu hình và cổng

- Python dependencies: `pip check` báo `No broken requirements found`.
- Cấu hình hiệu dụng được đọc qua settings của project; chỉ in các trường không nhạy cảm, không đọc/hiển thị secret.
- Ollama listener: `127.0.0.1:11434`, PID 24528.
- Streamlit UI health `127.0.0.1:8501/_stcore/health`: connection refused; UI không chạy trong lần kiểm tra này. Không tự khởi chạy UI vì scope task là khôi phục Ollama/backend cho QA.

## 3. Environment

| Thành phần | Giá trị / trạng thái |
|---|---|
| OS | Windows 11 Pro 64-bit, version 10.0.26300, build 26300 |
| Python | 3.12.14, `.venv` của project |
| Ollama executable | `C:\Users\Sang\AppData\Local\Programs\Ollama\ollama.exe` |
| Ollama version | 0.34.4 |
| Ollama endpoint | `http://localhost:11434` |
| Chat model configured | `qwen2.5:3b` |
| Chat model installed | `qwen2.5:3b`, ID `357c53fb659c`, 1.9 GB |
| Embedding backend/model | `ollama` / `nomic-embed-text` |
| Embedding model installed | `nomic-embed-text:latest`, ID `0a109f422b47`, 274 MB |
| Model store | `E:\OllamaModels` (được chỉ ra bởi `OLLAMA_MODELS`) |
| Chroma path | `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db` |
| Chroma collection | `dhv_admissions_2026` |
| Target year | 2026 |
| Deployment platform | Local; không deploy |

Sau smoke test, `/api/ps` cho thấy cả hai model đã loaded: Qwen khoảng 2.2 GB và Nomic khoảng 323 MB; cả hai dùng GPU theo trạng thái do Ollama báo.

### Chroma read-only audit

Collection được mở bằng thao tác list/get/count, không gọi add/upsert/delete/reset/rebuild.

| Kiểm tra | Kết quả |
|---|---:|
| Collection | `dhv_admissions_2026` |
| Record count | 310 |
| `year=2026` | 310/310 |
| `status=verified` | 310/310 |
| `verification_status=verified` | 310/310 |
| `school_code=DHV` | 310/310 |
| Có `source_url` | 310/310 |
| Host nguồn | `dhv.edu.vn`: 181; `tuyensinh.dhv.edu.vn`: 129 |

## 4. Deployment Steps / Local Runtime Action

Không có deployment. Các bước vận hành đã thực hiện:

1. Kiểm tra executable, process, listener, endpoint và cấu hình model.
2. Xác nhận trên host server chưa chạy và endpoint bị từ chối kết nối.
3. Dùng Ollama client hiện có; `ollama list` kích hoạt Ollama Desktop đang cài trên máy. Đây là hành động khởi chạy service local được task cho phép; không thực hiện restart service khác.
4. Xác nhận model list, API health, chat, embedding và pipeline chatbot.

Không sửa source, prompt, `.env`, model, embedding config, dữ liệu processed hoặc Chroma config.

## 5. Health Checks

| Check | Kết quả |
|---|---|
| Ollama `/api/version` | HTTP thành công; `{"version":"0.34.4"}` |
| Process/listener | `ollama.exe` PID 24528; `127.0.0.1:11434 LISTENING` |
| `ollama list` | Có `qwen2.5:3b` và `nomic-embed-text:latest` |
| Qwen `/api/chat` | Thành công, `done=true`, nội dung `OK` |
| Nomic `/api/embed` | Thành công, 1 vector, 768 chiều, mọi giá trị hữu hạn |
| `ollama ps` | Cả hai model loaded sau smoke test |
| Python dependency check | `pip check`: không có dependency hỏng |
| Streamlit UI health :8501 | Không chạy; không thuộc thao tác khôi phục Ollama này |

## 6. Smoke Tests

### Kiểm tra trực tiếp API model

- Chat: POST `/api/chat`, model `qwen2.5:3b`, prompt kiểm tra trả một từ `OK` → thành công.
- Embedding: POST `/api/embed`, model `nomic-embed-text`, test input không chứa dữ liệu cá nhân → thành công, 768 chiều.

### Truy vấn qua runtime chatbot thật

Chạy `ask_chatbot` mặc định của `src.chatbot.rag_chain`, với retriever/embedding và Ollama local thật, collection active hiện tại. Không dùng fake retriever, không inject document. Các câu hỏi là các smoke query được giao; câu trả lời bên dưới là kết quả quan sát runtime, không phải xác nhận factual QA.

| Câu hỏi | Status / intent | School / scope | Retrieval / docs / evidence | Sources | Kết quả quan sát |
|---|---|---|---:|---|---|
| `website Viện Đào tạo Sau đại học?` | `no_data` / `HOI_CO_SO_LIEN_HE` | `UNSPECIFIED` / `related_no_data` | 1 / 25 / 25 | `[]` | Trả thông báo chưa tìm thấy URL đã kiểm chứng; không phát URL viện hay overview thay thế. |
| `Thông tin trường DHV` | `ok` / `SCHOOL_INFO` | `DHV` / `in_scope_dhv` | 1 / 25 / 25 | `https://dhv.edu.vn/` | Trả phần giới thiệu trường từ evidence. Factual correctness cần QA đánh giá độc lập. |
| `Điểm chuẩn Bách Khoa?` | `out_of_scope` / `HOI_DIEM_TRUNG_TUYEN` | `OTHER_SCHOOL` / `external_school` | 0 / 0 / 0 | `[]` | Bị chặn trước retrieval; không trả dữ kiện điểm chuẩn DHV. |
| `Thông tin trường DHV và website Viện Đào tạo Sau đại học` | `ok` / `MULTI_ISSUE` | `DHV` / `in_scope_dhv` | 2 / 50 / 18 | Chỉ `https://dhv.edu.vn/` | Giữ hai phần: overview DHV có nguồn và phần website viện báo chưa có dữ liệu. Không tạo URL viện. |

### Câu trả lời cuối quan sát được

**Website Viện Đào tạo Sau đại học?**

> Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM.

**Thông tin trường DHV**

> Thông tin khái quát về DHV theo tài liệu đã xác minh: Trường Đại học Hùng Vương Thành Phố Hồ Chí Minh là một trong những trường đại học lâu năm tại Thành phố lớn nhất nước; với sứ mệnh đào tạo và phát triển nguồn nhân lực cho xã hội; trường tự hào là nơi đào tạo các thế hệ sinh viên trở thành người có Trách nhiệm, Trung Nghĩa và Tự tin trong cuộc sống.

**Điểm chuẩn Bách Khoa?**

> Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, học phí, học bổng, hồ sơ hoặc ngành đào tạo của Trường Đại học Hùng Vương TP.HCM.

**Thông tin trường DHV và website Viện Đào tạo Sau đại học**

> Phần “Thông tin trường” trả overview nêu trên. Phần “Cơ sở và liên hệ” trả thông báo chưa tìm thấy thông tin đã kiểm chứng. Source list chỉ có website DHV; không có URL của viện.

Lưu ý: `evidence_count=25` ở câu website viện là số evidence được chọn nội bộ trước khi kiểm tra URL được yêu cầu; nó **không** chứng minh URL viện có trong evidence. Runtime kết thúc `no_data`, `sources=[]`, đúng với ranh giới an toàn đã quan sát. QA vẫn cần đánh giá case này độc lập.

## 7. Logs / Errors

- Trước khi service chạy, host request tới `127.0.0.1:11434` trả `No connection could be made because the target machine actively refused it`; không có process/listener.
- Trong sandbox, request localhost ban đầu báo socket access bị cấm và CIM không khả dụng. Host-level kiểm tra sau đó phân biệt được lỗi này với trạng thái service thực tế.
- Ollama startup log báo khởi chạy Ollama Desktop/server và updater kiểm tra có bản mới hơn. Không tải hoặc cài bản cập nhật.
- Một lần in trace thử đầu tiên thất bại do console Python mặc định `cp1252` không encode được tiếng Việt (`UnicodeEncodeError`). Smoke query được chạy lại với output UTF-8 và cả bốn trace nhận được bình thường; đây là lỗi encoding của bộ ghi output, không phải lỗi Ollama/chatbot.
- `tasklist` trong sandbox trả lỗi credentials; thay vào đó process/listener được xác nhận ở host bằng `Get-Process` và `netstat`.
- Sau khi runtime lên, không thấy lỗi API chat/embed hoặc exception runtime trong bốn query.

## 8. Security / Secret Checks

- Chỉ in các setting không nhạy cảm cần thiết để xác minh model, endpoint, collection và năm.
- `.env` không tồn tại; `.env.example` tồn tại. Không đọc/ghi token, password hoặc secret; report không chứa secret.
- Ollama listener bind loopback `127.0.0.1`, không bind ra địa chỉ mạng bên ngoài theo listener quan sát được.
- Không tải/cài Ollama, không pull model, không gửi prompt/dữ liệu chatbot tới dịch vụ từ xa.
- External-school smoke (`Bách Khoa`) dừng trước retrieval: 0 call, 0 docs, 0 evidence.
- Chroma chỉ được truy vấn đọc; không có thao tác ghi hoặc rebuild.

## 9. Rollback Status

- Không có deployment để rollback.
- Không có thay đổi persistent trong project/config/model/Chroma cần rollback.
- Ollama local đang được giữ chạy để QA có thể dùng endpoint. Không dừng service theo yêu cầu không dừng service ngoài scope và để runtime sẵn sàng cho retest.
- Không có model/version rollback.

## 10. Final Verdict

# DEPLOYMENT_READY

Verdict này chỉ xác nhận **local Ollama/backend runtime sẵn sàng cho QA live retest**: endpoint khỏe, hai model hiện có gọi được, collection đọc được và bốn smoke query chạy qua pipeline thật. Đây **không phải** QA factual PASS, không phải `FULL_PROJECT_QA_PASS`, và không có deployment.

### Còn cần QA/owner xác nhận

1. QA & Security chạy lại live embedding + Qwen retest độc lập và đánh giá factual correctness/evidence cho bốn câu trong mục 6.
2. Streamlit UI không chạy trên cổng 8501 trong lượt này. Nếu QA yêu cầu kiểm thử qua browser UI thay vì gọi chatbot service trực tiếp, cần khởi chạy app riêng trong bước vận hành do QA/owner điều phối.
3. URL verified cho website viện/khoa chưa có trong collection; chatbot hiện fail-closed `no_data`, không phải lỗi runtime.

**Không deploy. Không rebuild/reset/upsert/write Chroma. Không sửa code, prompt, `.env`, model hoặc dữ liệu.**
