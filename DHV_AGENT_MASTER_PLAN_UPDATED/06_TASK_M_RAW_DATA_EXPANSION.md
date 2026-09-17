# TASK M — RAW Data Expansion
Chỉ official `dhv.edu.vn`/subdomain. RAW mới PDF. Ảnh tham khảo không vào KB.
Thu thập/audit: thong_tin_truong (giới thiệu ngắn phục vụ tư vấn, cơ sở, hotline/email, portal); trang ngành/mô tả/cơ hội nghề nghiệp; admissions methods; registration guidance; freshness học phí/học bổng/nhập học/lịch/điểm.
Không ingest dữ liệu cá nhân từ form. Metadata: source_url,title,date,collected_at,category,verification_status.
Nếu faculty page mâu thuẫn central admissions 2026, không ghi đè; tạo `reports/DATA_CONFLICTS_2026.md`.
Sau ingest: processed rebuild + Chroma rebuild + smoke/regression.
Deliverable: raw PDFs + manifest + conflict report + `reports/TASK_M_RAW_DATA_EXPANSION_RESULT.md`.
