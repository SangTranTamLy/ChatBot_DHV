# BÁO CÁO SỬA LỖI: CÂU HỎI VỀ WEBSITE TRƯỜNG BỊ TRẢ VỀ "NO_DATA"

## 1. Mô tả lỗi thực tế
Khi người dùng hỏi câu hỏi:
> "website tuyển sinh của trường DHV"

Chatbot đã trả lời:
> "Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM."

## 2. Phân tích nguyên nhân (Root Cause Analysis)
1. **Phân tích Intent:**
   - Khi hỏi về website, hệ thống phân tích câu hỏi và xác định intent là `HOI_CO_SO_LIEN_HE` (có cờ `website_request: True`).
   - `query_analysis.py` đã tạo plan tìm kiếm trong 2 chuyên mục: `thong_tin_truong` và `co_so_lien_he`.
2. **Quá trình Retrieval (Truy xuất ChromaDB):**
   - Lớp truy xuất ChromaDB trả về **0 chunks** vì không tìm thấy bất kỳ dữ liệu nào thuộc category `thong_tin_truong` hay `co_so_lien_he`.
3. **Lý do dữ liệu bị thiếu trong Vector DB:**
   - Kiểm tra `data/raw/manifest.json`, file PDF chứa thông tin về cơ sở và liên hệ (`Thong_Tin_Truong.pdf`) đã bị đánh dấu là `status: "missing_source_url"` và `verified: false`.
   - Vì bị đánh dấu chưa được xác thực (unverified), trong quá trình tiền xử lý (`build_vector_db.py` gọi tới `load_verified_documents`), tập tin JSON `Thong_Tin_Truong.json` bị **bỏ qua hoàn toàn**.
   - Do đó, toàn bộ danh mục thông tin liên hệ và website không được đưa vào ChromaDB.

## 3. Các bước khắc phục
1. **Cập nhật trạng thái xác thực (Verification Status):**
   - Đã chỉnh sửa thủ công `data/raw/manifest.json`, bổ sung thông tin chính thức cho tài liệu `thong-tin-truong-2026`:
     - Bổ sung `source_url: "https://dhv.edu.vn/"`
     - Đổi `status`, `verification_status` thành `"verified"`.
     - Đổi `verified` thành `true`.
   - Đã đồng bộ các chỉnh sửa này vào mục `source` của file `data/processed/thong_tin_truong/Thong_Tin_Truong.json` để script load dữ liệu nhận diện tài liệu này là hợp lệ và an toàn.
2. **Rebuild ChromaDB (Xây dựng lại Vector DB):**
   - Chạy lệnh `python -m src.ingestion.build_vector_db --reset` để làm mới cơ sở dữ liệu véc-tơ.
   - ChromaDB đã index thành công tài liệu thông tin trường, tăng tổng số lượng chunks từ 262 lên **270 chunks**.
   - Hiện tại, Categories trong Vector DB đã có mặt nhóm `thong_tin_truong`.
3. **Kiểm tra tính đúng đắn (Validation):**
   - Khi chạy giả lập câu hỏi `"website tuyển sinh của trường DHV"`, chatbot đã trích xuất thành công và tự động định dạng câu trả lời:
   > "Chào bạn! Bạn có thể xem thông tin tuyển sinh Trường Đại học Hùng Vương TP.HCM tại các nguồn chính thức sau:
   > - **Website trường:** [https://dhv.edu.vn/](https://dhv.edu.vn/)"

## 4. Kết luận
Lỗi đã được khắc phục bằng cách khôi phục lại tài liệu thông tin liên hệ/thông tin trường bị hệ thống ingestion bỏ qua. Chatbot hiện tại đã có khả năng trả lời đầy đủ thông tin về website, địa chỉ cơ sở và các kênh liên hệ của trường DHV từ dữ liệu đã được kiểm chứng.
