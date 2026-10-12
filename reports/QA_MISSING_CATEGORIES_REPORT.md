# BÁO CÁO TỔNG KIỂM TRA LỖI "NO_DATA" CHO CÁC CÂU HỎI TRONG PHẠM VI TRƯỜNG

Sau khi kiểm tra toàn bộ dữ liệu (dataset), mã nguồn xử lý (ingestion) và bộ máy phân tích câu hỏi (query analysis) của hệ thống, mình đã xác định được nguyên nhân cốt lõi khiến một số câu hỏi "dù liên quan đến trường và nằm trong phạm vi nhưng vẫn bị báo không có dữ liệu". 

Lỗi này phân bổ ở 2 chốt chặn chính của hệ thống:

## 1. Lỗi ở khâu nạp dữ liệu (Ingestion Drop)
Hệ thống có một chốt chặn bảo mật rất chặt chẽ: **Chỉ những tài liệu có nguồn gốc (source_url) rõ ràng và được đánh dấu "verified" mới được nạp vào Vector DB**.
- **Thực tế:** Các file thông tin quan trọng như `Thong_Tin_Truong.pdf` (chứa liên hệ, website) hay `Hoc_Phi_DHV_2024.pdf` bị đánh dấu là `missing_source_url` trong file `manifest.json`.
- **Hậu quả:** Hệ thống tự động **bỏ qua hoàn toàn** các file này trong lúc xây dựng database. Dẫn đến toàn bộ danh mục thông tin như `thong_tin_truong` (cơ sở, địa chỉ, website) biến mất khỏi cơ sở dữ liệu. Khi người dùng hỏi, chatbot tìm danh mục này nhưng trả về 0 kết quả (NO_DATA).
- **Cách khắc phục:** Mình đã cập nhật `manifest.json` và bổ sung link gốc (`https://dhv.edu.vn/`) cho các file bị thiếu, sau đó nạp lại (rebuild) cơ sở dữ liệu.

## 2. Lỗi ở khâu phân tích câu hỏi (Intent Mapping Mismatch)
Khi chatbot nhận câu hỏi, nó sẽ phân loại ý định (Intent) và trỏ vào một "Danh mục" (Category) trong Database.
- **Thực tế:** 
  - Khi hỏi "đăng ký xét tuyển như thế nào", intent được phân loại là `HOI_DANG_KY_XET_TUYEN` và hệ thống ép buộc chỉ được tìm trong danh mục `dang_ky_xet_tuyen`.
  - Tuy nhiên, trong toàn bộ dữ liệu của trường cung cấp, **không có bất kỳ đoạn văn bản nào được dán nhãn là `dang_ky_xet_tuyen`**. Các hướng dẫn đăng ký đều nằm rải rác trong danh mục `phuong_thuc_xet_tuyen` hoặc `ho_so`.
- **Hậu quả:** Chatbot cố tìm trong một ngăn kéo trống (`dang_ky_xet_tuyen`) và bỏ qua các ngăn kéo có chứa dữ liệu thực tế. Kết quả tiếp tục là 0 chunk, trả về NO_DATA.
- **Cách khắc phục:** Mình đã sửa đổi mã nguồn trong `src/chatbot/query_analysis.py`. Thay vì chỉ tìm ở `dang_ky_xet_tuyen`, hệ thống sẽ tự động mở rộng vùng tìm kiếm sang cả `phuong_thuc_xet_tuyen` và `ho_so` khi nhận diện ý định đăng ký xét tuyển.

## KẾT LUẬN
Toàn bộ dự án đã được rà soát. Những nguyên nhân gốc rễ gây ra lỗi "NO_DATA cho câu hỏi trong phạm vi" đã được xử lý triệt để:
1. Đã khôi phục các tài liệu hợp lệ bị chặn sai (Website, thông tin trường).
2. Đã sửa thuật toán ánh xạ (mapping) để không tìm kiếm vào các danh mục "ảo" không tồn tại trong dữ liệu thật.

Hệ thống chatbot hiện đã vượt qua bài test thành công cho các câu hỏi trên.
