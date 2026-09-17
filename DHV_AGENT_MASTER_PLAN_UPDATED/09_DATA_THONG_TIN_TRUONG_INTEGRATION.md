# BỔ SUNG DATA - THONG_TIN_TRUONG

File đã chuẩn bị:
`data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf`

Agent cần:
1. Đưa file này vào RAW corpus.
2. Cập nhật loader/category mapping để nhận `thong_tin_truong`.
3. Sinh processed bằng pipeline hiện tại, không viết tay nếu pipeline đã hỗ trợ.
4. Metadata tối thiểu: category=thong_tin_truong, year=2026, verification_status=verified, source URLs từ PDF.
5. Thêm/hoàn thiện intent `SCHOOL_INFO` / `HOI_THONG_TIN_TRUONG`.
6. Route câu hỏi tổng quan trường vào category này.
7. Không dùng tài liệu này thay cho các source chuyên biệt về điểm, học phí, học bổng, hồ sơ, phương thức.
8. Rebuild Chroma + smoke test + regression.
9. Test:
   - “DHV là trường gì?”
   - “Trường thành lập khi nào?”
   - “Website của trường là gì?”
   - “Web tuyển sinh DHV?”
   - “DHV có những cơ sở nào?”
   - “Đây có phải toàn bộ thông tin về trường không?” → SYSTEM_SCOPE, không phải dump toàn bộ KB.
