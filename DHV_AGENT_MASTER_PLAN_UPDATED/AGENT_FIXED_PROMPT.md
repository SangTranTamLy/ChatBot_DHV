# PROMPT CỐ ĐỊNH GỬI AGENT

Bạn đang làm việc trên repository ChatBot_DHV.

Đọc `00_MASTER_PLAN.md`, task file được giao, code/tests liên quan và `Tong_quan_xay_dung_chatbot_AI.pdf` nếu task cần phương pháp. Không sửa mù.

Ảnh trong `reference_images/` là ảnh chủ dự án chụp chatbot của một trường khác, CHỈ để tham khảo hành vi/UX và độ tự nhiên. Tuyệt đối không copy logo, avatar, background, CSS, layout pixel-perfect, màu nhận diện, câu chữ, prompt, source card, dữ liệu, tên trường hay mã nguồn. Không đưa ảnh vào RAG KB. Thiết kế DHV phải độc lập.

Data rules: chỉ official dhv.edu.vn/subdomain; RAW mới PDF; không bịa fact; không trộn formula/threshold/admission/supplementary/scholarship; không import dữ liệu cũ vào 2026 nếu chưa verified; không ingest PII không cần thiết.

Architecture rules: ưu tiên refactor tối thiểu; không tạo module trùng chức năng; giữ ChatService/Streamlit tương thích nếu có thể; greeting/identity/scope không RAG; retrieval phải qua Evidence Selection; list/count/filter/score deterministic bằng Python khi có thể; LLM không tính điểm/đậu-rớt/tạo fact; UI không source cards/URLs; không hard-code riêng CNTT/Luật để pass test.

Mỗi task: baseline/reproduce → tests → code fix → targeted tests → full regression → rebuild/smoke nếu liên quan data/retrieval → report. Không xóa test cũ để pass, không sửa data để che bug.

Report bắt buộc: task, root cause, current→expected, files changed, architecture decisions, tests, targeted/full results, metrics nếu có, sources/data mới, conflicts/unverified, limitations, exact reproduce commands, PASS/FAIL.

PASS chỉ khi targeted tests + full regression pass và invariants còn đúng.

Bây giờ chỉ thực hiện task sau, không tự nhảy task:
TASK CẦN THỰC HIỆN: <THAY_BẰNG_TÊN_FILE_TASK>
