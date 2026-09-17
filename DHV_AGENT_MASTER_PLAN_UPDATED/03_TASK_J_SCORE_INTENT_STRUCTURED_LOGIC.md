# TASK J — Score Intent + Deterministic Logic
Phân biệt formula vs threshold vs admission score vs supplementary.
Regression bắt buộc:
- Cách tính điểm xét tuyển học bạ ngành Luật?
- Điểm xét tuyển học bạ ngành Luật bao nhiêu?
- Ngành Luật xét học bạ bao nhiêu điểm?
- Luật học bạ lấy bao nhiêu?
- Điểm chuẩn ngành Luật năm 2026 bao nhiêu?
- Ngành Luật xét bổ sung bao nhiêu điểm?
Không tự trả 18 cho học bạ Luật nếu verified threshold source chưa công bố; không dùng THPT admission score 20 thay học-bạ threshold; không dùng supplementary thay initial.
Score Engine Python: compare verified score/threshold; chỉ nói đạt/vượt ngưỡng, không kết luận đậu. Thiếu rule verified → insufficient-data.
Deliverable: `reports/TASK_J_SCORE_INTENT_RESULT.md`.
