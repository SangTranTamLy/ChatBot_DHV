# Báo cáo: Sửa lỗi Aggregation / Enumeration / Counting (Đếm và liệt kê)

## Vấn đề ban đầu
Chatbot gặp lỗi không đếm đúng hoặc không liệt kê đầy đủ danh sách khi người dùng hỏi các câu hỏi dạng:
- "Có bao nhiêu..."
- "Có mấy..."
- "Liệt kê tất cả..."
- "Gồm những gì..."

Nguyên nhân gốc rễ là:
1. **Truy xuất bị giới hạn (Retrieval Truncation):** Thuật toán retrieval mặc định chỉ trả về `top_k = 5` chunks. Nếu danh sách (ví dụ: các phương thức xét tuyển, danh sách ngành) trải dài trên nhiều chunks, mô hình sẽ không nhận đủ ngữ cảnh và đếm sai.
2. **LLM Inference Limitation:** Mô hình ngôn ngữ tự động sinh số liệu hoặc tóm tắt thiếu sót thay vì đếm chính xác dựa trên danh mục.

## Giải pháp triển khai

### 1. Phân loại Query Intent (Query Analysis)
- Đã thêm trường `query_mode` vào `QueryPlan` với các giá trị: `SINGLE_FACT`, `COUNT`, `LIST`, `LIST_AND_COUNT`.
- Quá trình xử lý câu hỏi (`_extract_entities`) giờ đây có khả năng nhận diện các từ khóa liệt kê/đếm ("có bao nhiêu", "liệt kê", "danh sách", "gồm những") để thiết lập `query_mode` một cách chính xác.

### 2. Mở rộng Retrieval (Dynamic Top-K)
- Trong `rag_chain.py`, hàm `_retrieve` đã được điều chỉnh để tăng `top_k` lên `64` khi `query_mode` là dạng yêu cầu đếm hoặc liệt kê. Điều này đảm bảo toàn bộ các chunks liên quan đều được thu thập, khắc phục tình trạng thiếu dữ liệu.

### 3. Đếm có tính định chuẩn (Deterministic Counting)
Các câu hỏi đếm hoặc liệt kê được ưu tiên xử lý định chuẩn thông qua logic code để đảm bảo tính nhất quán (không giao cho LLM tự đếm):
- **Ngành & Chương trình (`DANH_SACH_NGANH`, `DANH_SACH_CHUONG_TRINH`):** Xử lý trong `_evidence_catalog_answer` (chỉnh sửa từ trước, nhưng nay lấy thông tin từ `query_mode`).
- **Phương thức xét tuyển (`HOI_PHUONG_THUC_XET_TUYEN`):** 
  - `evidence.py` được chỉnh sửa để trích xuất `admission_method` thành các `score_facts`.
  - `_evidence_catalog_answer` giờ đây hỗ trợ liệt kê và đếm phương thức xét tuyển bằng cách deduplicate (loại bỏ trùng lặp) các methods nhận được, qua đó trả về số lượng chính xác (ví dụ "DHV có 4 phương thức...").
- **Hồ sơ nhập học (`HOI_HO_SO`):** `_evidence_enrollment_answer` được nâng cấp để đếm số lượng tài liệu hồ sơ thông qua `query_mode`.
- **Học bổng (`HOI_HOC_BONG`):** `_evidence_scholarship_answer` được nâng cấp để hỗ trợ trả về số lượng các loại học bổng.
- **Lịch tuyển sinh (`HOI_LICH_TUYEN_SINH`):** Cung cấp `_evidence_schedule_answer` để rà soát các định dạng ngày tháng trong các chunk thuộc loại lịch trình và đếm/cung cấp danh sách. (Nếu không đủ định dạng, fallbacks về LLM cũng đã an toàn hơn nhờ top-k lớn).

## Kết quả kiểm tra
Tất cả các truy vấn dạng đếm và liệt kê (như "có bao nhiêu phương thức", "hồ sơ nhập học gồm những gì", "trường có những loại học bổng nào") đều hoạt động chính xác và đếm dựa trên toàn bộ records thu thập được, đồng thời đảm bảo không rơi vào fallback NO_DATA.
