# DHV Chatbot — Master Refactor & Expansion Plan

## Mục tiêu
Nâng cấp Chatbot AI tuyển sinh DHV thành trợ lý hội thoại tự nhiên, hiểu câu đơn giản/phức tạp, giữ context có giới hạn, truy xuất đúng evidence và không bịa.

## Bản quyền ảnh tham khảo
`reference_images/` là ảnh người dùng chụp chatbot của một trường khác. Chỉ tham khảo **hành vi/UX**: greeting, identity, scope, overview, bảng khi phù hợp, related questions, độ tự nhiên. CẤM copy logo, avatar, background, CSS, layout pixel-perfect, màu nhận diện, câu chữ, prompt, source card, dữ liệu, tên trường hay mã nguồn. Ảnh không phải dữ liệu RAG.

## Data invariants
- Chỉ nguồn chính thức `dhv.edu.vn` và subdomain chính thức.
- RAW mới = PDF.
- Processed = Markdown/YAML do pipeline sinh.
- Không trộn: score formula / application threshold / admission score / supplementary threshold / scholarship condition.
- Không suy diễn tổ hợp, điểm, mã, chương trình nếu 2026 chưa verified.
- Không đưa PII không cần thiết vào KB.
- Nguồn tuyển sinh trung tâm 2026 ưu tiên hơn trang khoa cũ khi có conflict.

## Kiến trúc đích
```text
User
→ Normalizer
→ Intent + Entity + Audience + Question Type
→ Bounded Conversation State
→ Router
   ├─ Greeting / Identity / Scope → deterministic response
   ├─ Admissions / School info → Retrieval
   ├─ Score → Retrieval + deterministic Score Engine
   ├─ Catalog → structured evidence + deterministic list/count
   ├─ Multi-issue → Query Decomposition
   ├─ Recommendation → verified facts + bounded logic
   └─ Out-of-scope → Scope Guard
→ Hybrid Retrieval (BM25 + Dense + RRF)
→ Evidence Selection
→ Structured Facts
→ Deterministic Engines
→ Answer Planner
→ LLM natural-language realization
→ Grounding + Relevance Validator
→ ChatService → Streamlit
```

## Intent tối thiểu
GREETING, SYSTEM_IDENTITY, SYSTEM_SCOPE, SCHOOL_INFO, HOI_NGANH, HOI_CHUONG_TRINH,
DANH_SACH_NGANH, DANH_SACH_CHUONG_TRINH, HOI_PHUONG_THUC_XET_TUYEN,
HOI_CACH_TINH_DIEM, HOI_NGUONG_DAU_VAO, HOI_DIEM_TRUNG_TUYEN,
HOI_XET_TUYEN_BO_SUNG, HOI_HOC_PHI, HOI_HOC_BONG, HOI_HO_SO,
HOI_DANG_KY_XET_TUYEN, HOI_LICH_TUYEN_SINH, HOI_NHAP_HOC, HOI_CO_SO_LIEN_HE,
TU_VAN_CHON_NGANH, MULTI_ISSUE, OUT_OF_SCOPE.

## Conversation state
Session-only: current_major, current_program, current_method, current_score_type, user_scores,
interests, candidate_majors, audience (chỉ khi có căn cứ), previous_intent, last_answer_topic, turn_count.
Không ghi điểm/sở thích/PII vào Chroma.

## Query decomposition
Chỉ cho multi-issue. Ví dụ “CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?”
→ tuition + scholarship + programs; retrieve riêng rồi merge/dedup evidence.

## Retrieval/Evidence
Hybrid BM25+dense+RRF; metadata/entity/category filter. Top-k retrieval chưa phải evidence cuối.
Evidence Selection phải loại fact ngoài intent/entity trước LLM.

## Structured/deterministic logic
List/count/filter/score comparison làm bằng Python. LLM không phải calculator/database/admission engine.
720 >= verified threshold 600 chỉ được diễn đạt là đạt/vượt ngưỡng nhận hồ sơ, không đảm bảo trúng tuyển.

## Answer Planner
Modes: DIRECT_SHORT, EXPLANATION, OVERVIEW, COMPARISON, TABLE, STEP_BY_STEP,
RECOMMENDATION, CLARIFICATION, NO_DATA, OUT_OF_SCOPE.
Cùng dữ liệu có thể trình bày khác nhau theo câu hỏi. Không ép một template cho mọi câu.

## Identity/Scope
Identity nội bộ: trợ lý AI hỗ trợ tra cứu tuyển sinh DHV được xây dựng trong khuôn khổ đồ án học tập/nghiên cứu.
Không tự nhận là chatbot/kênh chính thức của DHV.
Scope: KB tập trung tuyển sinh 2026 + thông tin trường liên quan trực tiếp; không phải toàn bộ thông tin DHV.

## Related questions
Có thể sinh 2–3 gợi ý theo intent/entity bằng thiết kế riêng DHV. Không copy ảnh tham khảo.
UI hiện không hiển thị source cards/URLs; backend vẫn giữ provenance.

## Validator
Kiểm grounding, relevance, entity, parent-major, score type, method, year, target institution,
official-status wording, count/list. “ĐGNL ĐHQG-HCM” không được làm target institution thành ĐHQG-HCM.

## Evaluation
Tạo evaluation/: 80% dev/regression + 20% holdout độc lập. Đánh giá retrieval và answer riêng.
Critical factual hallucination = blocker.

## Definition of Done
Full tests pass; bug đã biết có regression; greeting/identity/scope không RAG; score intent đúng;
catalog đúng parent/count; multi-turn đúng; multi-issue đúng; answer linh hoạt; không hallucination trọng yếu;
không source cards/URLs UI; data/Git policy đúng; report đầy đủ.
