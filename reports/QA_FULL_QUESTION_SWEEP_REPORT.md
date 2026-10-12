# QA FULL QUESTION SWEEP REPORT

## 1. Scope

- QA & Security Agent full sweep of the active chatbot question set.
- Product source, dataset, expected answers, model, Chroma, and deployment were not modified.
- Five required reports were read first: `QA_RUNTIME_NODATA_RETEST_REPORT.md`, `AGGREGATION_COUNTING_FIX_REPORT.md`, `reports/SEC_002_FIX_REPORT.md`, `reports/FULL_PDF_STRUCTURED_JSON_REPORT.md`, and `reports/PDF_CONTENT_COMPLETENESS_AUDIT.md`.
- Sweep execution was sequential and checkpointed after every question.

## 2. Dataset Inventory

| File | Rows/items | Role | Active | Loaded/used |
|---|---:|---|---|---|
| `data/evaluation/qa_master_500.jsonl` | 500 | Canonical user-provided Q&A | Yes | Yes; source of truth for this sweep |
| `data/evaluation/raw/Nhóm 4_Thu_Thap_Q&A.xlsx` | 500 questions | Canonical source workbook | Yes | Source for canonical JSONL |
| `data/intent/samples.jsonl` | 180 | Intent diagnostic data | Yes | Classifier/evaluation support |
| `data/intent/train.jsonl` | 144 | Intent train split | Yes | Classifier training |
| `data/intent/test.jsonl` | 36 | Intent test split | Yes | Classifier evaluation |
| `evaluation/dev.jsonl` | 16 | Fixed development evaluation | Yes | Evaluation support |
| `evaluation/holdout.jsonl` | 4 | Fixed holdout evaluation | Yes | Final evaluation support |
| `tests/fixtures/rag_golden_questions.json` | 16 | RAG fixture questions | Yes | Test fixtures |
| `reports/phase5/evaluation_results.csv` | 500 | Generated historical output | No | Report artifact, not source of truth |
| `reports/phase5_1000_legacy/*`, legacy scripts | legacy | Archived 1000-Q&A pipeline | No | Not used for this sweep |

Canonical set: `data/evaluation/qa_master_500.jsonl`, exactly 500/500 rows. Train/dev/holdout data were not merged into this sweep.

## 3. Canonical Question Set

- Total canonical questions: **500**.
- Executed: **500/500**.
- Checkpoint: [`QA_FULL_QUESTION_SWEEP_RESULTS.jsonl`](C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/QA_FULL_QUESTION_SWEEP_RESULTS.jsonl).
- Non-pass records (FAIL + BLOCKED): [`QA_FULL_QUESTION_SWEEP_FAILURES.jsonl`](C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/QA_FULL_QUESTION_SWEEP_FAILURES.jsonl).
- The initial harness incorrectly promoted several refusal/clarification responses to PASS. Those classifications were corrected after comparing the runtime output to the canonical expected answers.

## 4. Runtime Environment

- Python compile check: PASS (`python -m compileall -q src app.py`).
- Dependency consistency: PASS (`pip check`).
- Ollama `qwen2.5:3b`: **UNAVAILABLE** from the current environment; the endpoint/process could not be reached.
- Embedding model `nomic-embed-text`: not verifiable through the real Ollama path because the Ollama service was unavailable.
- Chroma collection: `dhv_admissions_2026`; current read-only check: **262 records**, all `year=2026`, `status=verified`, `school_code=DHV`. No 2024 or `verified=false` records were observed in the active collection.
- No Chroma reset or rebuild was performed.
- Current raw/processed school files are `data/raw/thong_tin_truong/Thong_Tin_Truong.pdf`, `TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` and their JSON outputs; the filename expected by `tests/test_task_09.py` (`thong_tin_truong_dhv_2026.pdf`) is absent.

## 5. Overall Results

| Metric | Count |
|---|---:|
| Total | 500 |
| Confirmed PASS | 0 |
| Confirmed FAIL | 120 |
| BLOCKED by environment | 380 |
| Confirmed pass rate | 0.00% |

The full sweep is **not a PASS**. There are 120 deterministic/runtime failures already proven without Ollama, and 380 factual paths that cannot be adjudicated until Ollama is available.

Failure-code totals: WRONG_ENTITY=45, WRONG_INTENT=6, WRONG_SCOPE=68, WRONG_YEAR=1.
Failure-severity totals: HIGH=68, MEDIUM=52.

## 6. Results By Intent

| Intent | Total | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| DANH_SACH_CHUONG_TRINH | 28 | 0 | 4 | 24 |
| DANH_SACH_NGANH | 12 | 0 | 1 | 11 |
| HOI_CACH_TINH_DIEM | 3 | 0 | 3 | 0 |
| HOI_CHUONG_TRINH | 73 | 0 | 4 | 69 |
| HOI_CO_SO_LIEN_HE | 21 | 0 | 4 | 17 |
| HOI_DANG_KY_XET_TUYEN | 5 | 0 | 1 | 4 |
| HOI_DIEM_TRUNG_TUYEN | 9 | 0 | 2 | 7 |
| HOI_HOC_BONG | 21 | 0 | 10 | 11 |
| HOI_HOC_PHI | 14 | 0 | 2 | 12 |
| HOI_HO_SO | 15 | 0 | 4 | 11 |
| HOI_LICH_TUYEN_SINH | 2 | 0 | 0 | 2 |
| HOI_NGANH | 162 | 0 | 15 | 147 |
| HOI_NGUONG_DAU_VAO | 19 | 0 | 6 | 13 |
| HOI_NHAP_HOC | 14 | 0 | 2 | 12 |
| HOI_PHUONG_THUC_XET_TUYEN | 17 | 0 | 3 | 14 |
| HOI_XET_TUYEN_BO_SUNG | 6 | 0 | 1 | 5 |
| MULTI_ISSUE | 20 | 0 | 0 | 20 |
| OUT_OF_SCOPE | 57 | 0 | 57 | 0 |
| SCHOOL_INFO | 1 | 0 | 0 | 1 |
| SYSTEM_SCOPE | 1 | 0 | 1 | 0 |

The runtime exposed 20 intent labels. Several canonical admissions/school-information questions were classified as `OUT_OF_SCOPE`, and several full DHV legal-name questions were stopped at school clarification.

## 7. Results By Domain

| Domain | Total | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| Admission method | 34 | 0 | 3 | 31 |
| Enrollment/documents | 28 | 0 | 6 | 22 |
| Majors | 168 | 0 | 16 | 152 |
| Programs | 98 | 0 | 7 | 91 |
| Schedule/supplementary | 7 | 0 | 1 | 6 |
| Scholarship | 23 | 0 | 10 | 13 |
| School information | 22 | 0 | 5 | 17 |
| Scope/system | 58 | 0 | 58 | 0 |
| Scores/thresholds | 34 | 0 | 12 | 22 |
| Tuition | 28 | 0 | 2 | 26 |

## 8. Results By Query Mode

| Query mode | Total | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| COUNT | 47 | 0 | 13 | 34 |
| LIST | 30 | 0 | 7 | 23 |
| LIST_AND_COUNT | 1 | 0 | 0 | 1 |
| SINGLE_FACT | 422 | 0 | 100 | 322 |

The parser observed `SINGLE_FACT=422`, `COUNT=47`, `LIST=30`, and `LIST_AND_COUNT=1`. All factual paths needing Ollama were BLOCKED; therefore COUNT/LIST content accuracy was not promoted to PASS.

## 9. COUNT/LIST Tests

- The mode classifier produced all four required modes.
- The canonical set contains 78 COUNT/LIST/LIST_AND_COUNT questions.
- Exact count/list reconciliation against runtime evidence is **BLOCKED** for the Ollama-dependent paths.
- Deterministic failures in this sweep include count/list or enumeration questions that were rejected at scope or ambiguity before retrieval, including `UQ0003`, `UQ0010`, `UQ0013`, `UQ0016`, `UQ0103`, and multiple catalog questions in the complete failure table.
- No count/list answer was treated as correct merely because a numeric token was present.

## 10. Enrollment Tests

Enrollment/document questions were present in the canonical set, but the real embedding/retrieval path was blocked for the majority. The prior no-data report could not be independently confirmed as a full current runtime PASS. Relevant scope false-positive examples include `UQ0057`, `UQ0064`, `UQ0068`, `UQ0074`, `UQ0076`, and `UQ0083`.

## 11. Tuition Tests

Tuition questions requiring factual retrieval were BLOCKED. The sweep did not accept unsupported values such as `1.250.000`, `12.500.000`, or `14.250.000` without live evidence.

## 12. Scholarship Tests

Scholarship questions requiring factual retrieval were BLOCKED or rejected by query analysis. No unsupported scholarship number was promoted to PASS.

## 13. Admission Method Tests

Admission-method questions were represented in the canonical set. Real retrieval/generation was BLOCKED. At least one canonical method question (`UQ0013`) was deterministically routed to `OUT_OF_SCOPE` despite explicit DHV/admission wording.

## 14. Scores/Threshold Tests

Score and threshold retrieval was BLOCKED for Ollama-dependent cases. Deterministic query-analysis failures were observed for `UQ0011`, `UQ0017`, `UQ0103`, and `UQ0179`. A separate test assertion (`tests/test_task_c.py::TaskCTests::test_threshold_validator_repairs_model_omission_from_evidence`) failed under a writable temp environment because the generated answer said `15 điểm` instead of the test's required literal `từ 15 điểm`; the numeric mapping itself remained 15/18/600 and was not treated as a full functional PASS.

## 15. Majors/Programs Tests

Many major/program factual paths were BLOCKED. The scope resolver also falsely marked generic phrases containing `trường` or `các trường khác` as external/mixed, affecting valid DHV canonical questions such as `UQ0224`, `UQ0338`, `UQ0343`, and career/program questions listed in the failure table.

## 16. Schedule/Supplementary Tests

Schedule/supplementary factual paths were BLOCKED or misclassified. `UQ0250` and `UQ0296` received an unrelated score clarification instead of answering event dates/times.

## 17. External School

A current runtime boundary probe was executed with a recording retriever (no production facts injected):

| Input | Target | Retrieval calls | Evidence | Status | Result |
|---|---|---:|---:|---|---|
| Điểm chuẩn Bách Khoa? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| diem chuan bach khoa? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Điểm chuẩn Văn Hiến? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Học phí Hoa Sen? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Văn Lang có học bổng không? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Nguyễn Tất Thành có xét học bạ không? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Điểm chuẩn Bách Khoa TP.HCM? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Học phí trường Bách Khoa? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| Điểm chuẩn trường đại học khác? | OTHER_SCHOOL | 0 | 0 | out_of_scope | PASS boundary |
| So sánh DHV và Văn Hiến | MIXED | 0 | 0 | out_of_scope | PASS boundary |
| Điểm chuẩn Hùng Vương? | AMBIGUOUS | 0 | 0 | clarification | PASS boundary |

This confirms the SEC-002 generic external guard for this matrix. It does not prove the Ollama factual positive path.

## 18. Wrong Year

- Current Chroma contains only 2026 verified records.
- The canonical question `UQ0007` mentions eligibility for 2026 while referring to graduates from 2025 or earlier. Runtime extracted `year=2025` and returned `no_data`, producing a confirmed `WRONG_YEAR` failure rather than answering the eligibility rule.
- Future-year no-data behavior was not promoted to PASS for the full factual path because Ollama was unavailable.

## 19. Multi-turn

A deterministic boundary/state probe showed:

- External school → short follow-up retained `OTHER_SCHOOL` and retrieval remained 0: PASS for domain containment.
- External school → explicit `DHV` switched to `DHV` and retrieval became allowed: PASS for routing; factual answer BLOCKED.
- DHV → `Còn Bách Khoa?` switched to external and retrieval remained 0: PASS for routing.
- External → `Cảm ơn` produced THANKS with retrieval 0, but the returned state still retained `current_school=OTHER_SCHOOL`.
- `Điểm chuẩn CNTT?` → `Xin chào` produced GREETING with retrieval 0, but returned state retained `current_major=Công nghệ thông tin`.
- Explicit major `Còn Luật?` replaced `current_major` with Luật.

No stale factual answer leaked in these probes, but retained slots after GREETING/THANKS remain a regression risk and need explicit product-contract confirmation.

## 20. Evidence Grounding

For the 380 Ollama-blocked questions, evidence relevance and LLM grounding could not be verified. For all scope/clarification failures, `retrieval_calls=0` and `evidence_count=0`, which is safe against hallucination but incorrect for canonical questions that require answers. No factual answer without evidence was promoted to PASS.

## 21. Performance

Measured sequential sweep latency (includes early boundary paths and Ollama-unavailable failures):

- All questions: avg=146.72 ms; median=182.96 ms; p95=209.94 ms; max=302.62 ms.
- SINGLE_FACT: avg=147.37 ms; median=183.63 ms; p95=209.52 ms; max=302.62 ms.
- COUNT/LIST/LIST_AND_COUNT: avg=143.20 ms; median=180.24 ms; p95=211.29 ms; max=230.83 ms.

These timings are not a production latency benchmark because Ollama was unavailable.

## 22. Complete Failure List

The following are all 120 confirmed FAIL records. Full unabridged traces are in `QA_FULL_QUESTION_SWEEP_FAILURES.jsonl`.

| ID | Question | Expected (abridged) | Actual | Failure code | Severity |
|---|---|---|---|---|---|
| UQ0001 | Giới thiệu về trường | Trường Đại học Hùng Vương TP. Hồ Chí Minh được thành lập năm 1995. Trường định hướng phát triển theo mô hình đại học ứng dụng, chú trọng thực học – thực hành, gắn đào tạo với thực tiễn, doanh nghiệp và tinh thần khởi ng… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0003 | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh đào tạo bao nhiêu ngành đại học chính quy? | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh triển khai 20 ngành đại học chính quy với hơn 50 chương trình đào tạo. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0004 | Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì? | Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là DHV. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0007 | Nếu thí sinh có bằng tốt nghiệp THPT từ năm 2025 trở về trước, có được tham gia xét tuyển năm 2026 không? | Thí sinh đã được công nhận tốt nghiệp THPT của Việt Nam (hoặc tương đương) đều đủ điều kiện dự tuyển. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng V… | WRONG_YEAR | HIGH |
| UQ0009 | Đối với thí sinh khuyết tật, Trường có những chính sách hỗ trợ nào? | Hiệu trưởng sẽ thực hiện các biện pháp can thiệp (thông qua kiểm tra hồ sơ y tế) và tạo điều kiện tốt nhất để thí sinh được đăng ký dự tuyển và theo học các ngành phù hợp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0010 | Muốn xét tuyển vào trường đại học Hùng Vương Tp.Hồ Chí Minh thì điều kiện cơ bản là gì? | Thí sinh đã tốt nghiệp THPT hoặc có trình độ tương đương theo quy định của Bộ Giáo dục và Đào tạo được đăng ký xét tuyển vào Trường đại học Hùng Vương Tp.Hồ Chí Minh. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0011 | Tổng điểm 3 môn thi tốt nghiệp của tôi được 15 điểm thì có đủ điều kiện nộp hồ sơ vào trường không? | Có. Đối với thí sinh dự thi tốt nghiệp THPT từ năm 2026, tổng điểm 3 môn theo tổ hợp xét tuyển đạt tối thiểu 15,00/30 là đủ điều kiện chung để đăng ký xét tuyển. Mức này là ngưỡng đủ điều kiện nộp hồ sơ, không đồng nghĩ… | Bạn cho mình biết điểm này theo phương thức nào: thi tốt nghiệp THPT, học bạ hay ĐGNL? | WRONG_INTENT | HIGH |
| UQ0013 | DHV năm 2026 có những cách xét tuyển nào vậy ạ? | Trong mùa tuyển sinh năm 2026, DHV mở rộng cơ hội trúng tuyển cho thí sinh với 5 phương thức xét tuyển đa dạng: Xét điểm thi tốt nghiệp THPT 2026 Xét kết quả học bạ THPT Xét điểm thi Đánh giá năng lực ĐHQG-HCM Xét điểm … | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0016 | Nếu xét bằng điểm thi tốt nghiệp thì trường lấy mấy môn ạ? | Khi xét tuyển theo phương thức điểm thi tốt nghiệp THPT vào Trường Đại học Hùng Vương Tp.Hồ Chí Minh, điểm xét tuyển là tổng điểm 3 môn thuộc tổ hợp môn xét tuyển tương ứng của từng ngành, cộng với điểm ưu tiên (theo kh… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0017 | Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ? | Có bạn nhé! Nhà trường có áp dụng cấu trúc tổ hợp linh hoạt gồm môn Toán cộng với 2 môn có điểm cao nhất trong danh sách các môn: Ngữ văn, Ngoại ngữ, Vật lí, Hóa học, Sinh học, Lịch sử, Địa lí, Tin học, Giáo dục kinh tế… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0024 | Cho em hỏi trường mình có chính sách cộng điểm khuyến khích cho thí sinh có chứng chỉ MOS không? | Theo quy định tuyển sinh của Trường Đại học Hùng Vương Tp.Hồ Chí Minh, thí sinh sở hữu chứng chỉ tin học quốc tế (như MOS, ICDL, IC3) hoặc chứng chỉ ngoại ngữ đạt trình độ từ B1 trở lên (theo khung tham chiếu CEFR hoặc … | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0025 | Giải Nhì học sinh giỏi cấp Tỉnh/Thành phố được cộng bao nhiêu điểm khi xét tuyển vào trường? | Nhà trường áp dụng chính sách cộng điểm ưu tiên thành tích đối với thí sinh đạt giải trong các kỳ thi, cuộc thi (trong 03 năm gần nhất) theo các mức cụ thể như sau: Cộng 1,50 điểm: Đạt giải Khuyến khích cấp Quốc gia trở… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0026 | Em được 18,5 điểm ba môn nhưng học lực lớp 12 không Giỏi thì có xét Luật được không ạ? | Riêng đối với các ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng đồng thời các điều kiện sau: Về học lực: Học lực cả năm lớp 12 xếp loại Giỏi (hoặc Tốt) trở lên, điểm trung bình chung cả năm lớp 12 đạt từ 8,0 trở lên.… | Bạn cho mình biết điểm này theo phương thức nào: thi tốt nghiệp THPT, học bạ hay ĐGNL? | WRONG_INTENT | HIGH |
| UQ0032 | Xét bổ sung em phải đến trường nộp hay đăng ký online được ạ? | Thí sinh có thể lựa chọn 1 trong 2 hình thức nộp hồ sơ xét tuyển bổ sung: Hình thức trực tuyến: Đăng ký trực tiếp tại cổng thông tin tuyển sinh của trường: tuyensinh.dhv.edu.vn. Hình thức trực tiếp: Nộp hồ sơ tại Ban Tư… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0040 | Kiểm tra năng lực tiếng Anh có phải ai cũng đóng 250.000 đồng không? | Lệ phí kiểm tra năng lực tiếng Anh đầu vào là 250.000 đồng, nhưng khoản này không bắt buộc với tất cả mọi người. Trường chỉ thu nếu bạn tham gia thi xếp lớp; bạn nào đã có chứng chỉ quốc tế hợp lệ hoặc thuộc diện được m… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0041 | Nếu em không thuộc diện kiểm tra tiếng Anh thì tổng các khoản học kỳ I trong bảng là bao nhiêu? | Khi không phát sinh phí kiểm tra năng lực tiếng Anh, các khoản học phí học kỳ I gồm 12.500.000 đồng học phí, 1.500.000 đồng phí nhập học và 250.000 đồng học liệu điện tử, tổng cộng 14.250.000 đồng. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0042 | Nếu có kiểm tra năng lực tiếng Anh thì số tiền học kỳ I theo bảng sẽ thành bao nhiêu? | Nếu cộng thêm 250.000 đồng phí kiểm tra năng lực tiếng Anh vào ba khoản còn lại, tổng chi phí theo bảng là 14.500.000 đồng. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0057 | Khi đến trường làm thủ tục nhập học, tôi cần mang những giấy tờ chính nào? | Tân sinh viên cần mang thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học, học bạ trung học phổ thông, căn cước và giấy chứng nhận kết quả thi tốt nghiệp trung học phổ thông năm 2026. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0061 | Giấy chứng nhận kết quả thi tốt nghiệp năm 2026 có cần mang theo không? | Có. Hướng dẫn nhập học yêu cầu tân sinh viên mang giấy chứng nhận kết quả thi tốt nghiệp trung học phổ thông năm 2026 để đối chiếu hồ sơ. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0064 | Nếu ở xa, tôi có thể nhập học mà chưa đến trường ngay không? | Về vấn đề này, Trường Đại học Hùng Vương TP. Hồ Chí Minh có hỗ trợ hình thức nhập học trực tuyến cho tân sinh viên ở xa: Hình thức nhập học: Bạn có thể lựa chọn nhập học trực tiếp tại trường hoặc nhập học trực tuyến. Nế… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0068 | Trường bắt đầu tiếp nhận tân sinh viên từ ngày nào? | Theo lịch trình tuyển sinh đại học chính quy tuyển mới năm 2026, thời gian nhập học cho thí sinh trúng tuyển là từ ngày 11/08/2026. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0074 | Ngoài thủ tục của trường, thí sinh trúng tuyển có phải xác nhận trên hệ thống của Bộ không? | Có. Thí sinh trúng tuyển phải xác nhận nhập học trên hệ thống hỗ trợ xét tuyển chung của Bộ Giáo dục và Đào tạo, sau đó tiếp tục hoàn tất thủ tục theo hướng dẫn của trường. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0076 | Tôi đã trúng tuyển nhưng chưa xác nhận trên hệ thống của Bộ thì chỉ đến trường làm hồ sơ có đủ không? | Được, đến hết thời hạn xác nhận nhập học, nếu thí sinh không hoàn tất các thủ tục cần thiết, bao gồm xác nhận trên hệ thống của Bộ Giáo dục và Đào tạo và hoàn thiện hồ sơ nhập học, thí sinh có thể được xem là từ chối nh… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0078 | Muốn hưởng mức ưu đãi cao nhất thì em nên hoàn tất xác nhận trước mốc nào? | Về việc xác nhận để đảm bảo quyền lợi và các ưu đãi tuyển sinh, em cần lưu ý các mốc thời gian quan trọng sau: Thời hạn để hưởng mức ưu đãi cao nhất: Tân sinh viên nên hoàn tất xác nhận trước ngày 13/8/2026 để được áp d… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0083 | Thông tin chi tiết về hồ sơ và các bước nhập học được trường công bố ở đâu? | Tài liệu điểm trúng tuyển cho biết các hướng dẫn về hồ sơ, thời gian, địa điểm và quy trình nhập học được đăng trên website tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0085 | Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng một ý nghĩa không? | Mốc 13/08/2026 và mốc 21/08/2026 là hai mốc khác nhau và có ý nghĩa khác nhau trong quá trình nhập học tại Trường Đại học Hùng Vương TP. Hồ Chí Minh. Mốc 13/08/2026: Liên quan đến quyền lợi và chính sách hỗ trợ của trườ… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0086 | Thông điệp tuyển sinh năm 2026 của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì? | Thông điệp được sử dụng trong cổng tuyển sinh năm 2026 là “Giá trị thật - Tương lai thật”, gắn với định hướng thực học, thực hành và khả năng thích ứng với môi trường làm việc. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0087 | Triết lý giáo dục của Trường Đại học Hùng Vương TP. Hồ Chí Minh được thể hiện bằng những từ khóa nào? | Triết lý giáo dục của trường được thể hiện qua sáu chữ “GIÁO DỤC - KHAI PHÓNG - KHỞI NGHIỆP”. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0089 | Tổ hợp môn xét tuyển của trường gồm những môn nào? | Năm 2026, khi xét tuyển bằng kết quả kỳ thi tốt nghiệp trung học phổ thông, Trường Đại học Hùng Vương TP. Hồ Chí Minh xây dựng tổ hợp xét tuyển theo 2 cấu trúc chính, thay vì cố định một số tổ hợp truyền thống. Tổ hợp 1… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0091 | Tầm nhìn phát triển của Trường Đại học Hùng Vương TP. Hồ Chí Minh hướng tới mô hình nào? | Trường định hướng trở thành đại học khởi nghiệp hàng đầu Việt Nam và khu vực châu Á, đồng thời phát triển theo mô hình đại học ứng dụng. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0092 | Ba giá trị cốt lõi của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì? | Ba giá trị cốt lõi được trường xác định là Trách nhiệm, Trung nghĩa và Tự tin. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0093 | Mốc thành lập chính thức của Trường Đại học Hùng Vương TP. Hồ Chí Minh là ngày nào? | Mốc thành lập chính thức của trường là ngày 14/08/1995, gắn với Quyết định 470-TTg của Thủ tướng Chính phủ. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0095 | Ngày truyền thống hằng năm của Trường Đại học Hùng Vương TP. Hồ Chí Minh là ngày nào? | Trường lấy ngày 9 tháng 3 âm lịch hằng năm làm ngày truyền thống, gắn với dịp tưởng niệm Quốc tổ Hùng Vương. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0096 | Đạt giải Khuyến khích cấp quốc gia thì được cộng bao nhiêu điểm? | Thí sinh có giải từ Khuyến khích cấp quốc gia được cộng 1,50 điểm theo chính sách cộng điểm khuyến khích. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0097 | Trường Đại học Dân lập Hùng Vương được phép đổi tên thành Trường Đại học Hùng Vương TP. Hồ Chí Minh vào thời điểm nào? | Ngày 14/05/2008, Bộ Giáo dục và Đào tạo ban hành văn bản cho phép Trường Đại học Dân lập Hùng Vương đổi tên thành Trường Đại học Hùng Vương TP. Hồ Chí Minh. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0098 | Giải Ba cấp tỉnh hoặc thành phố được cộng mấy điểm? | Giải Ba hoặc Khuyến khích cấp tỉnh, thành phố được cộng 1,00 điểm. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0099 | Giải cấp trường có được tính điểm khuyến khích không? | Có. Giải Nhất, Nhì hoặc Ba cấp trường trong phạm vi được quy định sẽ được cộng 0,50 điểm. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0103 | Phần lớn các ngành còn lại lấy bao nhiêu điểm theo kết quả thi tốt nghiệp? | Ngoài các ngành có mức riêng như Tâm lý học, Luật và Luật kinh tế, nhiều ngành còn lại trong bảng công bố có mức 15 điểm theo kết quả thi tốt nghiệp. | Bạn muốn biết điểm sàn (ngưỡng đầu vào), điểm trúng tuyển hay điểm của đợt xét tuyển bổ sung? | WRONG_INTENT | HIGH |
| UQ0106 | Cơ cấu tổ chức của Trường Đại học Hùng Vương TP. Hồ Chí Minh gồm những nhóm đơn vị chính nào? | Cơ cấu của trường gồm Hội đồng trường, Hội đồng Khoa học và Đào tạo, Ban Giám hiệu, các khoa và viện đào tạo, cùng các phòng ban và đơn vị trực thuộc. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0107 | Quỹ Vườn ươm Khởi nghiệp của trường được giới thiệu với quy mô ban đầu bao nhiêu? | Tài liệu tổng quan tuyển sinh giới thiệu Quỹ Vườn ươm Khởi nghiệp với giá trị ban đầu 1 triệu USD để đồng hành cùng các ý tưởng sáng tạo và khởi nghiệp của sinh viên. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0108 | Viện IATAI của trường phụ trách những lĩnh vực đào tạo và nghiên cứu nào? | Viện Công nghệ Tiên tiến và Trí tuệ Nhân tạo tập trung vào kỹ thuật, công nghệ cao, khoa học dữ liệu, công nghệ thông tin, trí tuệ nhân tạo, chuyển đổi số và đổi mới sáng tạo. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0133 | Sinh viên Trường Đại học Hùng Vương TP. Hồ Chí Minh có được tiếp cận môi trường doanh nghiệp từ sớm không? | Có. Tài liệu tuyển sinh năm 2026 cho biết trường phát triển mô hình học tập gắn với thực hành và doanh nghiệp để sinh viên sớm tiếp cận môi trường nghề nghiệp. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0138 | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh có ký hợp tác với Đại học Chosun của Hàn Quốc không? | Có. Ngày 28/01/2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh và Đại học Chosun ký biên bản ghi nhớ nhằm thúc đẩy hợp tác trong đào tạo và nghiên cứu khoa học. | Bạn đang hỏi Trường Đại học Hùng Vương TP.HCM phải không? Vui lòng nêu rõ TP.HCM hoặc DHV để mình tra cứu chính xác. | WRONG_ENTITY | HIGH |
| UQ0150 | Việc hợp tác giữa trường và Công ty Công nghệ PREP năm 2026 hướng tới những lợi ích nào cho sinh viên? | Thỏa thuận hợp tác với PREP hướng tới nâng cao chất lượng đào tạo, gắn lý thuyết với thực tiễn và mở rộng cơ hội học tập, trải nghiệm, phát triển nghề nghiệp cho sinh viên. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0160 | Viện Công nghệ Tiên tiến và Trí tuệ Nhân tạo có đào tạo trình độ đại học về Trí tuệ nhân tạo không? | Có. Trang chính thức của Viện IATAI liệt kê Trí tuệ nhân tạo trong nhóm chương trình đào tạo bậc đại học. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0179 | Điểm trúng tuyển ngành Tâm lý học DHV 2026 cao hơn các ngành khác vì sao? | Điểm trúng tuyển ngành Tâm lý học đợt 1 là 20,0 điểm (cùng với Luật và Luật Kinh tế), trong khi các ngành còn lại là 15,0 điểm. | Bạn muốn biết điểm sàn (ngưỡng đầu vào), điểm trúng tuyển hay điểm của đợt xét tuyển bổ sung? | WRONG_INTENT | HIGH |
| UQ0189 | Các phòng lab công nghệ của DHV chỉ dùng cho giờ thực hành trên lớp hay còn có mô hình hoạt động khác? | Các phòng lab được xây dựng theo mô hình mở, kết nối sinh viên, giảng viên, chuyên gia và doanh nghiệp trong cùng một hệ sinh thái. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0202 | Khoa Ngôn ngữ hợp tác với doanh nghiệp nhằm hỗ trợ sinh viên trong những hoạt động học tập nào? | Các quan hệ hợp tác được xây dựng để đưa sinh viên đi trải nghiệm thực tế, nâng cao kỹ năng ngôn ngữ và kỹ năng mềm, đồng thời tạo cơ sở cho hoạt động thực tập tốt nghiệp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0209 | DHV có trung tâm Công nghệ riêng không? | Có, Trung tâm Công nghệ của DHV có website là https://tek.dhv.edu.vn/ | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0222 | Thí sinh tốt nghiệp trung cấp cùng nhóm ngành có thể vào DHV không? | Có, thí sinh tốt nghiệp trung cấp nghề cùng nhóm ngành và đã hoàn thành chương trình văn hóa THPT theo quy định có thể đăng ký xét tuyển vào DHV theo Phương thức 5. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0224 | DHV có đào tạo Logistics không? | Có, DHV có chuyên ngành Quản trị Logistics thuộc ngành Quản trị kinh doanh (mã 7340101). Đây cũng là một trong 12 chương trình có chỉ tiêu xét tuyển bổ sung 2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0228 | Đối tác DAISO INDUSTRIES của Nhật Bản trao đổi với trường về chương trình nào dành cho sinh viên? | Tài liệu thông tin trường nêu DAISO INDUSTRIES Co., Ltd. trao đổi về chương trình thực tập sinh tại Nhật Bản kéo dài 6 tháng hoặc 1 năm dành cho sinh viên. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0231 | Aero Space Lab tại DHV phục vụ nghiên cứu những công nghệ nào? | Aero Space Lab tập trung vào UAV và công nghệ vệ tinh. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0236 | DHV hợp tác với đơn vị nào để mở rộng cơ hội thực tập tại Hoa Kỳ cho sinh viên? | Nhà trường ký biên bản ghi nhớ hợp tác với Công ty Cổ phần Học viện Hạnh phúc Việt Nam trong chương trình được công bố ngày 19/06/2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0245 | UniHackfest Unitour × DHV giúp sinh viên tiếp cận những xu hướng công nghệ nào? | Sinh viên được cập nhật về nền kinh tế số, tài sản số, hệ sinh thái Web3 và các xu hướng đổi mới sáng tạo trong công nghệ. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0246 | Tại UniHackfest Unitour × DHV, sinh viên được nghe chia sẻ gì về hệ sinh thái Solana? | Chương trình có nội dung về hành trình xây dựng và phát triển sản phẩm trên hệ sinh thái Solana từ những người trực tiếp triển khai dự án. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0248 | DHV ký biên bản ghi nhớ với SCTV vào thời điểm nào trong năm 2026? | Trường ký Biên bản ghi nhớ hợp tác với Công ty Truyền hình Cáp Saigontourist (SCTV) vào sáng ngày 02/06/2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0249 | UniHackfest Unitour × DHV có đề cập đến cơ hội nghề nghiệp trong các lĩnh vực công nghệ mới không? | Có. Chương trình giới thiệu cơ hội nghề nghiệp trong các ngành công nghệ mới nổi và giúp sinh viên hiểu thêm về yêu cầu kỹ năng trong bối cảnh chuyển đổi số. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0250 | Khoa Quản trị Kinh doanh – Marketing tổ chức tọa đàm về mô hình CO-OP vào thời điểm nào? | Tọa đàm “Mô hình CO-OP trong đào tạo Kinh tế quốc tế” được tổ chức ngày 27/03/2026 và bài tổng kết được đăng ngày 30/03/2026. | Bạn muốn biết điểm sàn (ngưỡng đầu vào), điểm trúng tuyển hay điểm của đợt xét tuyển bổ sung? | WRONG_INTENT | HIGH |
| UQ0252 | Mạng lưới đối tác của Khoa Ngôn ngữ trải rộng ở những nhóm lĩnh vực nào? | Khoa có các đối tác hoạt động trong nhiều lĩnh vực như thương mại, xuất nhập khẩu, tài chính và giáo dục – đào tạo. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0254 | Workshop “La bàn nghề nghiệp” của Khoa BAM hỗ trợ sinh viên về nội dung gì? | Chương trình tập trung giúp sinh viên khám phá tiềm năng và định hướng con đường nghề nghiệp trong lĩnh vực Thương mại điện tử. | Mình hỗ trợ tra cứu thông tin tuyển sinh DHV năm 2026 và thông tin về trường liên quan trực tiếp đã được kiểm chứng. Đây không phải toàn bộ thông tin của DHV; mình không tự suy đo… | WRONG_SCOPE | MEDIUM |
| UQ0256 | Sinh viên Khoa Kỹ thuật Công nghệ đã báo cáo bao nhiêu đề tài nghiên cứu khoa học cấp trường trong đợt công bố tháng 7/2026? | Ba nhóm sinh viên đã trình bày kết quả của ba đề tài nghiên cứu khoa học cấp trường trước Hội đồng khoa học. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0258 | Đề tài SV-19-24 của sinh viên Khoa Kỹ thuật Công nghệ hướng đến nhu cầu nào? | Nhóm nghiên cứu xây dựng một website thương mại điện tử dành cho sinh viên DHV. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0261 | Sinh viên Khoa Kỹ thuật Công nghệ có nghiên cứu phần mềm phục vụ các cuộc thi không? | Có. Đề tài SV-20-24 thiết kế phần mềm thi trắc nghiệm để phục vụ các cuộc thi. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0262 | Hoạt động nghiên cứu khoa học cấp trường giúp sinh viên Khoa Kỹ thuật Công nghệ rèn những kỹ năng gì? | Thông qua đề tài, sinh viên có điều kiện vận dụng kiến thức vào thực tiễn, rèn tư duy nghiên cứu, kỹ năng làm việc nhóm, quản lý dự án và phát triển giải pháp công nghệ. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0264 | Lễ ra quân Chiến dịch Mùa Hè Xanh 2026 của DHV được tổ chức vào ngày nào? | Trường tổ chức lễ ra quân vào sáng ngày 30/07/2026 để chính thức khởi động chiến dịch tình nguyện. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0265 | Sinh viên Khoa Kỹ thuật Công nghệ tham gia Mùa Hè Xanh 2026 tại địa bàn nào? | Đội hình sinh viên tham gia các hoạt động tình nguyện tại xã Long Sơn, TP. Hồ Chí Minh. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0267 | Chiến dịch Mùa Hè Xanh 2026 tạo cơ hội gì cho sinh viên DHV ngoài hoạt động học tập? | Chiến dịch tạo môi trường để sinh viên phát huy tinh thần xung kích, trách nhiệm và vận dụng sức trẻ, tri thức vào các hoạt động phục vụ cộng đồng. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0268 | Food & Hospitality Vietnam 2026 tạo môi trường quốc tế cho sinh viên DHV ở quy mô ra sao? | Triển lãm quy tụ hơn 400 đơn vị đến từ 36 quốc gia và vùng lãnh thổ, tạo điều kiện để sinh viên quan sát một môi trường kinh doanh đa văn hóa. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0269 | Trong Học kỳ Doanh nghiệp năm 2026, sinh viên lớp TN07 đã được đưa đến thực tập ở đâu? | Ngày 11/09/2026, sinh viên lớp TN07 được giảng viên của khoa đưa đến thực tập tại MB Bank – Chi nhánh Bắc Sài Gòn. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0271 | Sinh viên DHV đạt những hạng giải nào tại Talent Administrator 2026? | Sinh viên Khoa Kỹ thuật Công nghệ đạt hai Giải Ba và hai Giải Khuyến khích tại cuộc thi. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0272 | Talent Administrator 2026 là sân chơi học thuật gắn với nhóm kiến thức nào? | Cuộc thi được giới thiệu là sân chơi học thuật chuyên sâu về quản trị hệ thống và mạng. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0274 | SCFF26 đề cập đến những lĩnh vực công nghệ nổi bật nào? | Hội thảo tập trung vào các lĩnh vực như trí tuệ nhân tạo, học máy, dữ liệu lớn, chuyển đổi số, nhà máy thông minh và phát triển bền vững. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0275 | Giảng viên Khoa Kỹ thuật Công nghệ tham dự IAAA 2026 vào thời gian và địa điểm nào? | Các giảng viên tham dự và báo cáo tại IAAA 2026 trong hai ngày 27–28/07/2026 tại Trường Đại học Bách khoa – Đại học Quốc gia TP. Hồ Chí Minh. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0280 | Workshop “Chiến lược bán lẻ đa kênh toàn diện” của Khoa BAM được tổ chức khi nào? | Workshop được Khoa Quản trị Kinh doanh – Marketing tổ chức vào sáng ngày 09/07/2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0281 | DHV thành lập những câu lạc bộ công nghệ nào cùng với hệ thống phòng lab năm 2026? | Nhà trường thành lập các Câu lạc bộ Trí tuệ nhân tạo, Robotics và UAV để tạo môi trường học tập, nghiên cứu và sáng tạo về STEM. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0282 | Workshop về bán lẻ đa kênh mang đến cho sinh viên những nội dung thực tiễn nào? | Chương trình giúp sinh viên cập nhật xu hướng bán lẻ hiện đại và cách doanh nghiệp xây dựng trải nghiệm khách hàng trong thời đại số. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0284 | Sinh viên có thể học được những nội dung chuyên môn nào trong Học kỳ Doanh nghiệp của FBA? | Chương trình tạo điều kiện để sinh viên tìm hiểu sâu hơn về nghiệp vụ ngân hàng, kế toán và tích lũy kinh nghiệm phục vụ học tập cũng như nghiên cứu tốt nghiệp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0292 | Sinh viên tìm hiểu công nghệ nhân sự nào trong chuyến tham quan JobTest? | Sinh viên được giới thiệu hệ thống AIHR – HRM Software và các ứng dụng công nghệ trong quản trị nguồn nhân lực. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0296 | Chương trình “Khởi nghiệp cùng Sinh viên DHV 2026” của Khoa BAM diễn ra vào thời điểm nào? | Chương trình được tổ chức vào chiều ngày 20/07/2026 với sự tham gia của đông đảo sinh viên quan tâm đến đổi mới sáng tạo. | Bạn muốn biết điểm sàn (ngưỡng đầu vào), điểm trúng tuyển hay điểm của đợt xét tuyển bổ sung? | WRONG_INTENT | HIGH |
| UQ0297 | Sinh viên Khoa BAM tham gia Company Tour 2026 tại Kim Oanh Group vào ngày nào? | Chuyến trải nghiệm thực tế tại Kim Oanh Group diễn ra ngày 17/07/2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0300 | Chuyến tham quan Kim Oanh Group mang lại giá trị gì cho sinh viên Khoa BAM? | Hoạt động giúp sinh viên tiếp cận môi trường làm việc thực tế, nâng cao kỹ năng nghề nghiệp và tăng cường kết nối với doanh nghiệp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0302 | Sinh viên FBA tham gia sân chơi “Nhà đầu tư tương lai 2026” do đơn vị nào tổ chức? | Vòng chung kết cuộc thi “Nhà đầu tư tương lai 2026” mùa 4 được Trường Đại học Văn Lang tổ chức vào ngày 25/04/2026. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0305 | Đội sinh viên FBA đạt kết quả gì tại cuộc thi “Nhà đầu tư tương lai 2026”? | Đội của Khoa Tài chính – Ngân hàng – Kế toán đã vào Top 5 chung cuộc và nhận Giải Khuyến khích. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0327 | Lễ ký kết với 6 doanh nghiệp ngày 26/06/2026 mang lại những cơ hội nào cho sinh viên? | Hoạt động ký kết với 6 doanh nghiệp hướng tới xây dựng học kỳ doanh nghiệp, mời chuyên gia chia sẻ thực tiễn và kết nối thực tập, hướng nghiệp, tuyển dụng cho sinh viên. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0329 | Công việc của một AI Researcher được Viện IATAI mô tả gồm những nhiệm vụ nào? | Viện IATAI mô tả AI Researcher là người nghiên cứu và cải tiến công nghệ AI, phát triển thuật toán, tạo nguyên mẫu phần mềm và công bố kết quả nghiên cứu khoa học. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0330 | AI Developer thường đảm nhiệm những công việc gì theo thông tin của Viện IATAI? | AI Developer thiết kế và triển khai phần mềm thông minh, lập trình mô hình học máy, xử lý dữ liệu, tối ưu hệ thống và phối hợp với kỹ sư phần mềm để tích hợp AI vào thực tế. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0331 | Mạng lưới đối tác của Viện IATAI có hoạt động trong lĩnh vực học máy không? | Có. Danh sách lĩnh vực hợp tác của Viện IATAI năm 2026 có trí tuệ nhân tạo và học máy. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0332 | Mạng lưới đối tác công nghệ của Viện IATAI có bao gồm lĩnh vực điện toán đám mây không? | Có. Điện toán đám mây là một trong những lĩnh vực hoạt động của các đối tác công nghệ mà Viện IATAI kết nối. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0333 | Viện IATAI có kết nối đối tác trong lĩnh vực an toàn thông tin không? | Có. An toàn thông tin được liệt kê trong nhóm lĩnh vực của mạng lưới đối tác công nghệ thuộc Viện IATAI. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0336 | khi là sinh viên của trường DHV thì sẽ được những quyền lợi gì ạ? | Khi trở thành sinh viên của Trường Đại học Hùng Vương TP. Hồ Chí Minh, bạn có một số quyền lợi nổi bật như: Được đào tạo kỹ năng ứng dụng AI và cấp tài khoản AI Pro trong suốt thời gian học. Có cơ hội tiếp cận doanh ngh… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0338 | Trường DHV có kết nối và giao lưu với các trường khác không ạ? | Có. Trường Đại học Hùng Vương TP. Hồ Chí Minh có các hoạt động hợp tác, kết nối và giao lưu quốc tế với nhiều trường và tổ chức nước ngoài. Một số đối tác được tài liệu của trường nhắc đến gồm Trường Đại học Khai Nam – … | Mình có dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nhưng không có dữ liệu đã xác minh của trường còn lại để thực hiện so sánh đầy đủ. | WRONG_ENTITY | HIGH |
| UQ0339 | khi trúng tuyển thì trường sẽ thông báo vào đâu ạ? | Khi trúng tuyển, bạn nên kiểm tra kết quả trên hệ thống hỗ trợ tuyển sinh chung của Bộ Giáo dục và Đào tạo và theo dõi website tuyển sinh chính thức của Trường Đại học Hùng Vương TP. Hồ Chí Minh để xem hướng dẫn nhập họ… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0340 | đóng tiền mặt thì đóng ở đâu ạ vào thời gian nào ạ? | Theo thông tin nhập học năm 2026, trường chưa nêu rõ riêng quầy hoặc địa điểm thu học phí bằng tiền mặt. Trường chỉ công bố hai địa điểm tiếp nhận nhập học trực tiếp là: 194 Lê Đức Thọ, Phường An Nhơn, TP. Hồ Chí Minh 3… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0341 | khi được cấp tài khoản edu của trường thì tài khoản và mật khẩu là gì ạ? | ài khoản và mật khẩu đăng nhập được nhà trường cấp riêng cho từng sinh viên sau khi hoàn tất các bước theo quy định. Nếu chưa nhận được hoặc quên thông tin đăng nhập, bạn nên liên hệ bộ phận hỗ trợ sinh viên của trường … | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0342 | thực tập thì trường sẽ giơi thiệu cho hay là sinh viên phải tự đi kiếm doanh nghiệp? | Trường có hỗ trợ kết nối sinh viên với doanh nghiệp để kiến tập, thực hành và thực tập, chứ không phải hoàn toàn để sinh viên tự tìm. Tài liệu của trường nêu các hoạt động hợp tác doanh nghiệp nhằm tạo cơ hội thực tập v… | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0343 | trường DHV có làm đồ án và bảo vệ đồ án như các trường khác hay không? | Có. Trường Đại học Hùng Vương TP. Hồ Chí Minh có tổ chức làm và bảo vệ đồ án/khóa luận tốt nghiệp, nhưng hình thức sẽ tùy từng ngành và chương trình đào tạo. Chẳng hạn, năm 2026 sinh viên ngành Công nghệ thông tin – chu… | Mình có dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nhưng không có dữ liệu đã xác minh của trường còn lại để thực hiện so sánh đầy đủ. | WRONG_ENTITY | HIGH |
| UQ0344 | trường có quy định khi đi học có bắt buộc phải mặc đồng phục không ạ? | Trường chưa công bố quy định chung bắt buộc tất cả sinh viên phải mặc đồng phục trong mọi buổi học. Tuy nhiên, một số khoa hoặc một số hoạt động có thể có quy định trang phục riêng, vì vậy sinh viên cần thực hiện theo t… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0345 | bãi đỗ xe có tính phí không? | không, trường sẽ hỗ trợ cho sinh viên nhưng số lượng có hạn. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0346 | nếu phải mua riêng đồng phục thì giá sẽ là bao nhiêu ạ? | một số khoa hoặc hoạt động có thể yêu cầu trang phục riêng. Mức đồng phục được thông báo gồm áo trắng 190.000 đồng, bộ đồ thể dục màu đỏ 250.000 đồng, hoặc mua 1 combo gồm cả hai với giá 440.000 đồng | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0347 | trường có tổ chức lễ khai giảng cho sinh viên không ạ? | Có. Trường Đại học Hùng Vương TP. Hồ Chí Minh có tổ chức lễ khai giảng và chào đón tân sinh viên. Ví dụ, ngày 05/09/2025, trường đã tổ chức Lễ Khai giảng năm học 2025–2026 và đón tân sinh viên niên khóa 2025–2029 tại cơ… | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0349 | trường có phòng cho sinh viên nghỉ ngơi sau mỗi tiết học không ạ? | có, trường có chỗ cho sinh viên để có thể nghỉ ngơi có, Sảnh G để ngơi: Cơ sở 194 Lê Đức Thọ P.An Nhơn, TP.HCM, 736 Nguyễn Trãi P. Chợ Lớn TP.HCM, Căn tin để ngơi: 37 Kinh Dương Vương P. Phú Lâm TP.HCM | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | MEDIUM |
| UQ0363 | Một hướng việc làm sau ngành Quản trị kinh doanh có phải là chuyên viên nhân sự không? | Cử nhân Quản trị kinh doanh có thể làm việc tại bộ phận quản lý nhân sự của doanh nghiệp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0367 | Sau khi ra trường, cử nhân Quản trị kinh doanh có thể hướng đến nghề vị trí quản lý doanh nghiệp không? | Sau quá trình tích lũy kinh nghiệm, cử nhân Quản trị kinh doanh có thể phát triển lên các vị trí quản lý và điều hành. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0372 | Học ngành Quản trị kinh doanh có giúp sinh viên rèn khả năng thích ứng trong môi trường đa văn hóa không? | Sinh viên được chuẩn bị khả năng thích ứng với môi trường đa văn hóa thông qua kiến thức về thay đổi và quản trị rủi ro. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0378 | Chương trình Marketing trang bị kiến thức về nghiên cứu thị trường như thế nào? | Sinh viên Marketing được học cách nghiên cứu thị trường để nhận diện nhu cầu, xu hướng và cơ hội kinh doanh. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0389 | Một hướng việc làm sau ngành Marketing có phải là nhân viên phát triển thị trường không? | Cử nhân Marketing có thể tham gia các hoạt động mở rộng thị trường và phát triển nhóm khách hàng. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0393 | Sau khi ra trường, cử nhân Marketing có thể hướng đến nghề trưởng phòng marketing không? | Ngành Marketing mở ra lộ trình phát triển lên các vị trí quản lý như trưởng phòng marketing. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0409 | Ngành Thương mại điện tử có đào tạo phần kiến thức hoạt động và môi trường doanh nghiệp không? | Nội dung đào tạo bao gồm kiến thức về hoạt động doanh nghiệp và môi trường kinh doanh. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0415 | Một hướng việc làm sau ngành Thương mại điện tử có phải là tư vấn giải pháp công nghệ không? | Cử nhân có thể làm công việc tư vấn các giải pháp công nghệ phục vụ hoạt động kinh doanh. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0419 | Sau khi ra trường, cử nhân Thương mại điện tử có thể hướng đến nghề nhân sự tại doanh nghiệp cung cấp dịch vụ e-marketing không? | Các doanh nghiệp cung cấp dịch vụ e-marketing là một môi trường nghề nghiệp được trang chương trình đề cập. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0441 | Một hướng việc làm sau ngành Kinh tế quốc tế có phải là chuyên viên xuất nhập khẩu không? | Xuất nhập khẩu là một hướng nghề nghiệp phù hợp với kiến thức thương mại quốc tế được đào tạo. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0442 | Sinh viên tốt nghiệp Kinh tế quốc tế có thể phát triển nghề nghiệp theo hướng chuyên viên phát triển thị trường quốc tế không? | Cử nhân có thể tham gia nghiên cứu và mở rộng thị trường ở nước ngoài. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0445 | Sau khi ra trường, cử nhân Kinh tế quốc tế có thể hướng đến nghề chuyên viên thu mua quốc tế không? | Nền tảng về mua hàng toàn cầu giúp người học hướng tới các vị trí thu mua và tìm nguồn cung quốc tế. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0453 | Sinh viên ngành Kinh tế quốc tế có được rèn luyện kỹ năng thích ứng với môi trường đa văn hóa không? | Người học được rèn khả năng làm việc trong môi trường đa văn hóa và thích ứng với khác biệt giữa các thị trường. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0455 | Ba phòng thí nghiệm công nghệ trọng điểm được DHV đưa vào vận hành năm 2026 gồm những phòng nào? | Ba phòng gồm AI & Big Data Lab, Smart Factory Lab và Aero Space Lab. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0456 | Trong quá trình học ngành Kinh tế quốc tế, sinh viên có cơ hội học theo định hướng gắn với môi trường làm việc không? | Chương trình định hướng ứng dụng để sinh viên sớm hình dung và thích ứng với môi trường kinh doanh thực tế. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0467 | Một hướng việc làm sau ngành Tài chính - Ngân hàng có phải là giao dịch viên ngân hàng không? | Cử nhân Tài chính - Ngân hàng có thể làm giao dịch viên tại ngân hàng hoặc tổ chức tài chính. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trườ… | WRONG_SCOPE | HIGH |
| UQ0471 | Sau khi ra trường, cử nhân Tài chính - Ngân hàng có thể hướng đến nghề chuyên viên tín dụng không? | Cử nhân có thể làm việc tại bộ phận tín dụng, từ tiếp nhận hồ sơ đến thẩm định và theo dõi khoản vay. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |
| UQ0497 | Sau khi ra trường, cử nhân Kế toán có thể hướng đến nghề kế toán thuế không? | Cử nhân có thể đảm nhiệm công việc kế toán thuế, theo dõi và xử lý các nghĩa vụ thuế của đơn vị. | Mình hiện chỉ sử dụng dữ liệu chính thức của Trường Đại học Hùng Vương TP.HCM, nên không thể xác nhận thông tin tuyển sinh của trường khác. Mình có thể hỗ trợ bạn về điểm chuẩn, h… | WRONG_ENTITY | HIGH |

The 380 BLOCKED question IDs are retained in the failure JSONL with `result=BLOCKED`, `failure_code=ENVIRONMENT_ERROR`; they are not counted as PASS.

## 23. Failure Clusters

| Cluster | Count | Affected IDs (complete) |
|---|---:|---|
| WRONG_ENTITY | 45 | UQ0003, UQ0004, UQ0010, UQ0016, UQ0032, UQ0057, UQ0064, UQ0068, UQ0074, UQ0076, UQ0083, UQ0086, UQ0087, UQ0089, UQ0091, UQ0092, UQ0093, UQ0095, UQ0097, UQ0106, UQ0108, UQ0133, UQ0138, UQ0150, UQ0160, UQ0228, UQ0256, UQ0262, UQ0338, UQ0339, UQ0341, UQ0342, UQ0343, UQ0367, UQ0372, UQ0378, UQ0393, UQ0409, UQ0419, UQ0442, UQ0445, UQ0453, UQ0456, UQ0471, UQ0497 |
| WRONG_SCOPE | 68 | UQ0001, UQ0009, UQ0013, UQ0017, UQ0024, UQ0025, UQ0040, UQ0041, UQ0042, UQ0061, UQ0078, UQ0085, UQ0096, UQ0098, UQ0099, UQ0107, UQ0189, UQ0202, UQ0209, UQ0222, UQ0224, UQ0231, UQ0236, UQ0245, UQ0246, UQ0248, UQ0249, UQ0252, UQ0254, UQ0258, UQ0261, UQ0264, UQ0265, UQ0267, UQ0268, UQ0269, UQ0271, UQ0272, UQ0274, UQ0275, UQ0280, UQ0281, UQ0282, UQ0284, UQ0292, UQ0297, UQ0300, UQ0302, UQ0305, UQ0327, UQ0329, UQ0330, UQ0331, UQ0332, UQ0333, UQ0336, UQ0340, UQ0344, UQ0345, UQ0346, UQ0347, UQ0349, UQ0363, UQ0389, UQ0415, UQ0441, UQ0455, UQ0467 |
| WRONG_INTENT | 6 | UQ0011, UQ0026, UQ0103, UQ0179, UQ0250, UQ0296 |
| WRONG_YEAR | 1 | UQ0007 |
| ENVIRONMENT_ERROR / BLOCKED | 380 | All blocked IDs are in the JSONL checkpoint; not enumerated as functional FAILs |

Priority clusters:

- P0/P1: false external/mixed school detection and full DHV-name ambiguity; these suppress valid retrieval and can recreate wrong-domain behavior.
- P1: scope/intent contract rejects substantive canonical DHV school, admissions, career, and event questions.
- P1: historical qualification-year parsing causes false no-data.
- P2: missing school artifact/test filename mismatch and threshold answer/test wording mismatch.
- Environment blocker: Ollama availability prevents end-to-end factual adjudication.

## 24. New Bugs

1. `SWEEP-SCOPE-001` — HIGH — generic `trường ...` and comparative `các trường khác` patterns are treated as named external schools, causing false OTHER_SCHOOL/MIXED boundaries for 32 canonical DHV questions.
2. `SWEEP-SCOPE-002` — HIGH — full DHV legal-name variants containing `TP. Hồ Chí Minh` resolve to AMBIGUOUS instead of DHV, causing 13 canonical questions to stop before retrieval.
3. `SWEEP-INTENT-001` — HIGH — explicit admissions/school-information questions are classified as OUT_OF_SCOPE or receive a wrong score clarification; this affects the 68 WRONG_SCOPE records and 6 WRONG_INTENT records.
4. `SWEEP-YEAR-001` — HIGH — historical-year phrase in UQ0007 is interpreted as the requested data year, yielding false no-data.
5. `SWEEP-DATA-001` — HIGH — active canonical dataset contains school-information/event/career questions with substantive expected answers, while runtime scope contract refuses many of them; this is a dataset/runtime contract mismatch.
6. `SWEEP-DATA-002` — HIGH — `tests/test_task_09.py` expects a missing raw school PDF filename and therefore cannot validate the current manifested school source.
7. `SWEEP-TEST-001` — MEDIUM — `tests/test_task_c.py` has a wording assertion requiring `từ 15 điểm`; current deterministic output preserves numeric values but omits that literal phrase.

| ID | Severity | Example input | Expected | Actual | Root cause | Affected file(s) | Owner |
|---|---|---|---|---|---|---|---|
| `SWEEP-SCOPE-001` | HIGH | `Khi đến trường làm thủ tục nhập học, tôi cần mang những giấy tờ chính nào?` | DHV in-scope retrieval with verified enrollment evidence | `OTHER_SCHOOL`, retrieval=0, evidence=0 | Generic word after `trường` is treated as a named institution | `src/chatbot/scope_guard.py`, `src/chatbot/query_analysis.py` | `LEAD_CODER` |
| `SWEEP-SCOPE-002` | HIGH | `Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh đào tạo bao nhiêu ngành?` | `target_school=DHV` | `target_school=AMBIGUOUS`, clarification, retrieval=0 | Legal-name normalization/alias coverage misses the `TP. Hồ Chí Minh` form | `src/chatbot/scope_guard.py` | `LEAD_CODER` |
| `SWEEP-INTENT-001` | HIGH | `DHV năm 2026 có những cách xét tuyển nào vậy ạ?` | Admission-method list | `OUT_OF_SCOPE` refusal, retrieval=0 | Rule/classifier routing gives an in-scope admission question `OUT_OF_SCOPE`; related score/event turns ask wrong clarification | `src/chatbot/query_analysis.py`, intent/router tests | `LEAD_CODER` |
| `SWEEP-YEAR-001` | HIGH | `... bằng tốt nghiệp THPT từ năm 2025 trở về trước ... xét tuyển năm 2026?` | Eligibility rule for 2026 | `year=2025`, `no_data` | Historical qualification year is confused with requested target year | `src/chatbot/query_analysis.py`, year tests | `LEAD_CODER` |
| `SWEEP-DATA-001` | HIGH | `Giới thiệu về trường` / school events and career questions | Verified school-information answer from active 500-Q&A contract | Scope refusal or wrong domain | Runtime scope contract and active canonical domain are inconsistent | scope contract, data manifest, retrieval categories | `LEAD_CODER`, `DATA_REVIEW` |
| `SWEEP-DATA-002` | HIGH | Task 09 school source smoke test | Current manifest/file pair loads and preserves school metadata | Expected `thong_tin_truong_dhv_2026.pdf` is absent; 3 Task 09 tests fail | Test expects stale filename instead of current manifest files | `tests/test_task_09.py`, `data/raw/manifest.json` | `DATA_REVIEW` |
| `SWEEP-TEST-001` | MEDIUM | `Điểm sàn CNTT 2026?` fixture | Output includes required threshold wording | Output has correct `15/18/600` facts but omits literal `từ 15 điểm` | Deterministic answer wording and test contract differ | `src/chatbot/rag_chain.py`, `tests/test_task_c.py` | `LEAD_CODER` |

## 25. Priority Handoff

# HANDOFF TO LEAD CODER

### Priority 1 — Scope and entity safety

- Bug IDs: `SWEEP-SCOPE-001`, `SWEEP-SCOPE-002`.
- Affected question IDs: `UQ0003, UQ0004, UQ0010, UQ0016, UQ0032, UQ0057, UQ0064, UQ0068, UQ0074, UQ0076, UQ0083, UQ0086, UQ0087, UQ0089, UQ0091, UQ0092, UQ0093, UQ0095, UQ0097, UQ0106, UQ0108, UQ0133, UQ0138, UQ0150, UQ0160, UQ0228, UQ0256, UQ0262, UQ0338, UQ0339, UQ0341, UQ0342, UQ0343, UQ0367, UQ0372, UQ0378, UQ0393, UQ0409, UQ0419, UQ0442, UQ0445, UQ0453, UQ0456, UQ0471, UQ0497`.
- Affected files: `src/chatbot/scope_guard.py`, `src/chatbot/query_analysis.py`, and corresponding scope tests.
- Reproduce: call the production entry point sequentially for each affected ID; inspect `target_school`, `retrieval_calls`, and `evidence_count`.
- Trace: false positives stop in `_school_scope_boundary_result` with `OTHER_SCHOOL`/`MIXED` or `AMBIGUOUS`, before retriever invocation.
- Expected behavior: generic DHV references remain `UNSPECIFIED`/DHV-default; explicit full DHV legal names resolve DHV; only genuine external/mixed/ambiguous school queries stop before retrieval.
- Actual behavior: 45 canonical rows are classified as `WRONG_ENTITY`; all have retrieval=0/evidence=0 despite substantive expected answers.
- Acceptance criteria: rerun all affected IDs, external matrix, non-accent variants, comparative wording, and assert retrieval/evidence zero only for true external/mixed/ambiguous cases.
- QA rerun: full sweep plus external-school matrix.

### Priority 1 — Query analysis and routing

- Bug IDs: `SWEEP-INTENT-001`, `SWEEP-YEAR-001`.
- Affected question IDs: `UQ0001, UQ0009, UQ0013, UQ0017, UQ0024, UQ0025, UQ0040, UQ0041, UQ0042, UQ0061, UQ0078, UQ0085, UQ0096, UQ0098, UQ0099, UQ0107, UQ0189, UQ0202, UQ0209, UQ0222, UQ0224, UQ0231, UQ0236, UQ0245, UQ0246, UQ0248, UQ0249, UQ0252, UQ0254, UQ0258, UQ0261, UQ0264, UQ0265, UQ0267, UQ0268, UQ0269, UQ0271, UQ0272, UQ0274, UQ0275, UQ0280, UQ0281, UQ0282, UQ0284, UQ0292, UQ0297, UQ0300, UQ0302, UQ0305, UQ0327, UQ0329, UQ0330, UQ0331, UQ0332, UQ0333, UQ0336, UQ0340, UQ0344, UQ0345, UQ0346, UQ0347, UQ0349, UQ0363, UQ0389, UQ0415, UQ0441, UQ0455, UQ0467`; plus `UQ0007, UQ0011, UQ0026, UQ0103, UQ0179, UQ0250, UQ0296`.
- Affected files: `src/chatbot/query_analysis.py`, router/intent tests, and year extraction tests.
- Example trace: `UQ0013` has explicit `DHV` and admission-method wording but returns `intent=OUT_OF_SCOPE`, `retrieval_calls=0`; `UQ0007` extracts `year=2025` and returns `no_data`.
- Expected behavior: explicit method/score/school/event questions route to their factual intent; historical qualification years do not override requested target year.
- Actual behavior: 68 rows are scope-refused, 6 rows receive unrelated clarification, and UQ0007 is false no-data.
- Acceptance criteria: six clarification failures answer or retrieve the intended category; UQ0007 returns the eligibility rule; no regression in COUNT/LIST modes.
- QA rerun: affected IDs, all 500 canonical questions, wrong-year matrix.

### Priority 2 — Active domain contract and data/test alignment

- Bug IDs: `SWEEP-DATA-001`, `SWEEP-DATA-002`, `SWEEP-TEST-001`.
- Affected files: scope contract/data manifest/test fixture naming and deterministic answer contract.
- Example inputs: `Giới thiệu về trường`; `tests/test_task_09.py::test_school_pdf_is_manifested_and_processed_by_pipeline`; `Điểm sàn CNTT 2026?`.
- Actual trace: canonical school-information rows return scope refusal with retrieval=0; Task 09 fails on the absent raw filename; Task C returns correct numeric mappings but fails the literal wording assertion.
- Expected behavior: either support the active 500-question school-information domain with verified evidence, or formally revise the canonical dataset contract before claiming full sweep PASS; restore/align the manifested school PDF test fixture; align threshold wording contract.
- Acceptance criteria: school-info/event/career rows no longer receive unsupported scope refusal, Task 09 passes against the current manifest, and threshold tests pass without weakening factual validation.
- QA rerun: full canonical sweep, Task 09, Task C, evidence checks.

## 26. Acceptance Criteria

| Criterion | Status | Evidence |
|---|---|---|
| Entire canonical set executed | PASS | 500/500 sequential records in checkpoint |
| No question skipped | PASS | Every canonical row has a JSONL record |
| No HIGH/CRITICAL functional issue | FAIL | 45 WRONG_ENTITY, 68 WRONG_SCOPE, 6 WRONG_INTENT, 1 WRONG_YEAR |
| COUNT/LIST exact accuracy | BLOCKED | 78 factual enumeration paths depend on unavailable Ollama/retrieval |
| Factual answers evidence-grounded | BLOCKED | 380 factual paths stopped at Ollama dependency |
| No wrong-school leakage | PASS for boundary probe; BLOCKED for full factual path | External matrix had retrieval=0/evidence=0; positive path unavailable |
| No wrong-year leakage | FAIL | UQ0007 false no-data due year extraction |
| Multi-turn regression | BLOCKED/PARTIAL | Boundary/state probes ran; factual turns could not complete with Ollama offline |
| Full regression suites | FAIL | Writable-temp rerun: 189 passed, 4 failed, 4 skipped |
| Security blocker absent | PASS (within static checks) | No tracked `.env`/live secret found; no destructive/security exploit observed |

## 27. Final Verdict

**FULL_QUESTION_SWEEP_FAIL**

Reason: 500/500 rows were executed, but 120 have confirmed functional failures and 380 are environment-blocked. The project cannot claim full-question correctness, count/list correctness, factual grounding, or full runtime PASS until the scope/entity/intent/year clusters are fixed and Ollama-backed regression is rerun.

## Report / Code Mismatches

- `QA_RUNTIME_NODATA_RETEST_REPORT.md` reports Chroma count 258 and real Ollama PASS; current read-only collection count is 262 and current Ollama endpoint is unavailable.
- `reports/SEC_002_FIX_REPORT.md` reports 173 passed/12 failed/4 skipped; current full test run is 179 passed/14 failed/4 skipped under default temp and 189 passed/4 failed/4 skipped with writable temp.
- `reports/FULL_PDF_STRUCTURED_JSON_REPORT.md` and `PDF_CONTENT_COMPLETENESS_AUDIT.md` describe a school-information pipeline, but current `tests/test_task_09.py` points to a missing raw filename and fails against the current manifest/files.
- The original sweep harness marked 114 records PASS without factual expected-answer comparison; this report corrects that and does not rely on the old PASS labels.

## Regression Suites

| Suite | Passed | Failed | Skipped | Blocked | Classification |
|---|---:|---:|---:|---:|---|
| `tests/test_priority_1_2_fix.py` | 19 | 0 | 0 | 0 | PASS; 26 subtests |
| Intent/runtime/UI targeted group | 78 | 0 | 0 | 0 | PASS; 142 subtests |
| Full pytest, default sandbox temp | 179 | 14 | 4 | 0 | Mixed: temp ACL plus reproducible failures |
| Full pytest, writable project temp | 189 | 4 | 4 | 0 | FAIL; 3 Task 09 data/file failures + 1 Task C assertion |
| `compileall` | 1 check | 0 | 0 | 0 | PASS |
| `pip check` | PASS | 0 | 0 | 0 | PASS |
| Real Ollama production-like path | 0 | 0 | 0 | 500 | BLOCKED_BY_ENVIRONMENT |

## Security / Repo Hygiene Notes

- `.env` and `.streamlit/secrets.toml` are ignored; only `.env.example` is tracked.
- Static secret-pattern scan found configuration names and report/test references, but no high-confidence live secret was identified. Values were not printed.
- Streamlit output uses `unsafe_allow_html=False` at rendered markdown call sites observed; no `eval`, `exec`, `shell=True`, or unsafe pickle path was observed in the scanned source.
- `pip-audit` and `safety` are not installed in the environment, so third-party CVE status is unverified.
- Generated sweep artifacts are intentionally untracked QA outputs; no deployment was performed.
