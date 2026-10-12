# QA & SECURITY – FULL SWEEP P1 RETEST REPORT

## 1. Scope

Independent retest of the 120 questions that failed in the original full sweep after Lead Coder P1 changes. The retest used the production-like `ask_chatbot` path with local Ollama and the existing Chroma collection. QA did not modify source code, datasets, expected answers, Chroma, or model configuration.

Lead claims reviewed: `FULL_SWEEP_P1_FIX_REPORT.md`, including claims for `SWEEP-SCOPE-001`, `SWEEP-SCOPE-002`, `SWEEP-INTENT-001`, and `SWEEP-YEAR-001`.

## 2. Runtime Environment

| Component | Observed |
|---|---|
| Runtime | Real sequential `src.chatbot.rag_chain.ask_chatbot` |
| LLM | Ollama `qwen2.5:3b` available |
| Embedding | Ollama `nomic-embed-text` available |
| Chroma | `dhv_admissions_2026`, 270 records, read-only inspection |
| Checkpoint | `QA_FULL_SWEEP_P1_RETEST_RESULTS.jsonl`, 120/120 records |

## 3. Overall Results

- Runtime execution: **120/120 completed**; no environment-blocked question.
- Runtime statuses: `ok=37`, `no_data=15`, `out_of_scope=68`.
- QA verdicts: **PASS=16, FAIL=40, CONTRACT_BLOCKED=64**.
- Factual QA pass rate over all 120: **13.33%**. Contract-blocked rows are not counted as PASS.
- Severity distribution: `{'MEDIUM': 83, 'HIGH': 21}`.

The retest does **not** support a full-sweep pass. There are confirmed HIGH factual/routing failures and unresolved contract rows.

## 4. Runtime Architecture / Trace Coverage

Every retested row contains the captured question, expected answer, analysis entities, intent, query mode, school/scope, year, retrieval count, document/evidence count, status, answer, sources, and latency in `QA_FULL_SWEEP_P1_RETEST_RESULTS_ENRICHED.jsonl`. The following representative traces were independently inspected:

| ID | Trace result | Retrieval | Evidence | QA interpretation |
|---|---|---:|---:|---|
| UQ0010 | ok / HOI_HOC_BONG | 1 / 4 docs | 4 | basic admission eligibility routed to scholarship intent and returned scholarship facts |
| UQ0007 | no_data / HOI_DANG_KY_XET_TUYEN | 1 / 4 docs | 4 | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0085 | out_of_scope / HOI_LICH_TUYEN_SINH | 0 / 0 docs | 0 | in-scope admissions schedule question was rejected before retrieval |
| UQ0107 | out_of_scope / OUT_OF_SCOPE | 0 / 0 docs | 0 | verified school overview fact was rejected by an overly narrow scope policy |
| UQ0224 | no_data / HOI_CHUONG_TRINH | 1 / 2 docs | 2 | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0342 | ok / SCHOOL_INFO | 1 / 8 docs | 8 | QA confirmed factual answer against expected answer and relevant evidence. |

## 5. Regression Suites

| Suite | Passed | Failed | Skipped | Classification |
|---|---:|---:|---:|---|
| Focused P1 + Task 09 + Task C + UI | 82 | 3 | 0 reported | PRODUCT_FAILURE: `tests/test_task_c.py` category over-selection |
| Full pytest | 215 | 5 | 4 | 3 Task C subtest failures + 2 existing data/manifest failures |
| Original FAIL-ID runtime retest | 120 | 0 blocked | 0 | Completed; QA answer evaluation still found failures |
| `python -m compileall src app.py` | PASS | 0 | 0 | Static syntax check passed |

Full-suite mismatch with Lead report: Lead reported 215 passed / 2 failed / 4 skipped; independent run returned 215 passed / 5 failed / 4 skipped. This is `REPORT_CODE_MISMATCH`.

## 6. Results by Intent

| Intent | PASS | FAIL | Contract blocked |
|---|---:|---:|---:|
| DANH_SACH_CHUONG_TRINH | 0 | 0 | 1 |
| DANH_SACH_NGANH | 0 | 1 | 0 |
| HOI_CACH_TINH_DIEM | 0 | 6 | 0 |
| HOI_CHUONG_TRINH | 0 | 2 | 0 |
| HOI_CO_SO_LIEN_HE | 0 | 1 | 0 |
| HOI_DANG_KY_XET_TUYEN | 0 | 4 | 0 |
| HOI_DIEM_TRUNG_TUYEN | 0 | 1 | 0 |
| HOI_HOC_BONG | 0 | 1 | 0 |
| HOI_HOC_PHI | 2 | 1 | 0 |
| HOI_HO_SO | 1 | 4 | 0 |
| HOI_LICH_TUYEN_SINH | 0 | 2 | 0 |
| HOI_NGANH | 0 | 1 | 0 |
| HOI_NGUONG_DAU_VAO | 2 | 2 | 0 |
| HOI_NHAP_HOC | 1 | 2 | 0 |
| HOI_PHUONG_THUC_XET_TUYEN | 1 | 2 | 0 |
| OUT_OF_SCOPE | 0 | 3 | 63 |
| SCHOOL_INFO | 9 | 7 | 0 |

## 7. Results by Query Mode

| Query mode | PASS | FAIL | Contract blocked |
|---|---:|---:|---:|
| COUNT | 2 | 7 | 4 |
| LIST | 0 | 5 | 2 |
| SINGLE_FACT | 14 | 28 | 58 |

## 8. Performance

- All 120 runtime calls: average `1517.90 ms`, median `10.79 ms`, p95 `5900.44 ms`, max `7084.96 ms`.

| Query mode | Count | Average ms | Median ms | P95 ms | Max ms |
|---|---:|---:|---:|---:|---:|
| COUNT | 13 | 2550.22 | 2196.67 | 5416.80 | 5479.51 |
| LIST | 7 | 2234.88 | 2203.22 | 5392.44 | 6691.64 |
| SINGLE_FACT | 100 | 1333.51 | 10.64 | 5900.44 | 7084.96 |

## 9. Complete Confirmed Failure List

These 40 rows are confirmed QA FAIL. The full unabridged trace for every row is in `QA_FULL_SWEEP_P1_RETEST_FAILURES.jsonl`.

| ID | Question | Expected | Actual | Failure code | Severity | Probable root cause |
|---|---|---|---|---|---|---|
| UQ0001 | Giới thiệu về trường | Trường Đại học Hùng Vương TP. Hồ Chí Minh được thành lập năm 1995. Trường định hướng phát triển theo mô hình đại học ứng dụng, chú trọng thực học – thực hành, gắn đào tạo với thực tiễn, doanh nghiệp và tinh thần khởi nghiệp. Trong tuyển sinh năm 2026, trường sử dụng thông điệp “Giá trị thật – Tương lai thật” và hướng đến việc giúp sinh viên tăng khả năng thích ứng với môi trường làm việc sau khi tốt nghiệp. | Theo tài liệu đã xác minh của DHV: Với sứ mệnh đào tạo và phát triển nguồn nhân lực cho xã hội. | LLM_PARTIAL_ANSWER | MEDIUM | retrieval/evidence exists but overview generation omitted required school facts |
| UQ0003 | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh đào tạo bao nhiêu ngành đại học chính quy? | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh triển khai 20 ngành đại học chính quy với hơn 50 chương trình đào tạo. | DHV hiện có 20 ngành chính năm 2026. | LLM_PARTIAL_ANSWER | MEDIUM | answer gave the major count but omitted the required program-count fact |
| UQ0004 | Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì? | Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là DHV. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0007 | Nếu thí sinh có bằng tốt nghiệp THPT từ năm 2025 trở về trước, có được tham gia xét tuyển năm 2026 không? | Thí sinh đã được công nhận tốt nghiệp THPT của Việt Nam (hoặc tương đương) đều đủ điều kiện dự tuyển. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0009 | Đối với thí sinh khuyết tật, Trường có những chính sách hỗ trợ nào? | Hiệu trưởng sẽ thực hiện các biện pháp can thiệp (thông qua kiểm tra hồ sơ y tế) và tạo điều kiện tốt nhất để thí sinh được đăng ký dự tuyển và theo học các ngành phù hợp. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0010 | Muốn xét tuyển vào trường đại học Hùng Vương Tp.Hồ Chí Minh thì điều kiện cơ bản là gì? | Thí sinh đã tốt nghiệp THPT hoặc có trình độ tương đương theo quy định của Bộ Giáo dục và Đào tạo được đăng ký xét tuyển vào Trường đại học Hùng Vương Tp.Hồ Chí Minh. | Mình tóm tắt các chính sách và điều kiện học bổng đang có trong dữ liệu DHV 2026: - Chính sách học bổng: 100% học phí toàn khóa; Học bổng Hào khí Hùng Vương hỗ trợ đến 80% học phí học - Điều kiện nhận học bổng tuyển sinh DHV 2026: - hoàn tất hồ sơ sớm để được tư vấn về ngành học, phương thức xét tuyển, học phí, học bổng - HỌC BỔNG LÊN ĐẾN 100% VÀ NHIỀU CHÍNH SÁCH ĐỒNG HÀNH - Song song với đợt xét tuyển bổ sung, DHV tiếp tục triển khai Quỹ học bổng 75 tỷ - đồng dành cho tân sinh viên năm 2026. Trong đó, Học bổng Tà… | WRONG_INTENT | HIGH | basic admission eligibility routed to scholarship intent and returned scholarship facts |
| UQ0013 | DHV năm 2026 có những cách xét tuyển nào vậy ạ? | Trong mùa tuyển sinh năm 2026, DHV mở rộng cơ hội trúng tuyển cho thí sinh với 5 phương thức xét tuyển đa dạng: Xét điểm thi tốt nghiệp THPT 2026 Xét kết quả học bạ THPT Xét điểm thi Đánh giá năng lực ĐHQG-HCM Xét điểm kỳ thi chuyên biệt H-SCA kết hợp học bạ THPT Xét tuyển dành riêng cho thí sinh tốt nghiệp hệ trung cấp Bạn hoàn toàn có thể đăng ký nhiều phương thức cùng lúc để tăng tối đa cơ hội trúng tuyển vào ngành mình yêu thích nhé! | Mình liệt kê các phương thức xét tuyển được ghi nhận trong dữ liệu DHV: 1. Xét kết quả kỳ thi tốt nghiệp THPT năm 2026 2. 1.4. Xét tuyển kết quả học tập THPT (học bạ) 3. 1.5. Xét kết quả kỳ thi Đánh giá năng lực 4. 1.6. Xét kết quả bài thi Đánh giá năng lực chuyên biệt (H-SCA) 5. 1.7. Xét tuyển đối với thí sinh tốt nghiệp trung cấp | LLM_PARTIAL_ANSWER | MEDIUM | method enumeration was incomplete/garbled despite relevant evidence |
| UQ0016 | Nếu xét bằng điểm thi tốt nghiệp thì trường lấy mấy môn ạ? | Khi xét tuyển theo phương thức điểm thi tốt nghiệp THPT vào Trường Đại học Hùng Vương Tp.Hồ Chí Minh, điểm xét tuyển là tổng điểm 3 môn thuộc tổ hợp môn xét tuyển tương ứng của từng ngành, cộng với điểm ưu tiên (theo khu vực, đối tượng) theo quy định của Bộ GD&ĐT và Nhà trường nhé! | Ngưỡng nhận hồ sơ được công bố: thi tốt nghiệp THPT: 15,00 điểm. | WRONG_QUERY_MODE | HIGH | question asks subject-count semantics but answer returned an admission threshold |
| UQ0017 | Em mạnh Toán thì DHV có cách lấy Toán cộng hai môn điểm cao nhất không ạ? | Có bạn nhé! Nhà trường có áp dụng cấu trúc tổ hợp linh hoạt gồm môn Toán cộng với 2 môn có điểm cao nhất trong danh sách các môn: Ngữ văn, Ngoại ngữ, Vật lí, Hóa học, Sinh học, Lịch sử, Địa lí, Tin học, Giáo dục kinh tế và pháp luật, Công nghệ công nghiệp để tối ưu điểm xét tuyển cho bạn. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0024 | Cho em hỏi trường mình có chính sách cộng điểm khuyến khích cho thí sinh có chứng chỉ MOS không? | Theo quy định tuyển sinh của Trường Đại học Hùng Vương Tp.Hồ Chí Minh, thí sinh sở hữu chứng chỉ tin học quốc tế (như MOS, ICDL, IC3) hoặc chứng chỉ ngoại ngữ đạt trình độ từ B1 trở lên (theo khung tham chiếu CEFR hoặc tương đương) sẽ được cộng 1,50 điểm ưu tiên tính trên thang điểm 30 khi xét tuyển. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0025 | Giải Nhì học sinh giỏi cấp Tỉnh/Thành phố được cộng bao nhiêu điểm khi xét tuyển vào trường? | Nhà trường áp dụng chính sách cộng điểm ưu tiên thành tích đối với thí sinh đạt giải trong các kỳ thi, cuộc thi (trong 03 năm gần nhất) theo các mức cụ thể như sau: Cộng 1,50 điểm: Đạt giải Khuyến khích cấp Quốc gia trở lên; hoặc đạt giải Nhất, Nhì cấp Tỉnh / Thành phố trực thuộc Trung ương. Cộng 1,00 điểm: Đạt giải Ba hoặc giải Khuyến khích cấp Tỉnh / Thành phố. Cộng 0,50 điểm: Đạt giải Nhất, Nhì hoặc Ba trong các kỳ thi, cuộc thi cấp Trường. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0026 | Em được 18,5 điểm ba môn nhưng học lực lớp 12 không Giỏi thì có xét Luật được không ạ? | Riêng đối với các ngành Luật và Luật Kinh tế, thí sinh cần đáp ứng đồng thời các điều kiện sau: Về học lực: Học lực cả năm lớp 12 xếp loại Giỏi (hoặc Tốt) trở lên, điểm trung bình chung cả năm lớp 12 đạt từ 8,0 trở lên. Về điểm thi THPT: Tổng điểm 3 môn thi tốt nghiệp THPT theo tổ hợp xét tuyển đạt từ 18,00 điểm trở lên (thang điểm 30). Về môn điều kiện: Điểm thi tốt nghiệp THPT môn Toán hoặc môn Ngữ văn phải đạt từ 6,0 điểm trở lên. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0032 | Xét bổ sung em phải đến trường nộp hay đăng ký online được ạ? | Thí sinh có thể lựa chọn 1 trong 2 hình thức nộp hồ sơ xét tuyển bổ sung: Hình thức trực tuyến: Đăng ký trực tiếp tại cổng thông tin tuyển sinh của trường: tuyensinh.dhv.edu.vn. Hình thức trực tiếp: Nộp hồ sơ tại Ban Tư vấn Tuyển sinh thuộc một trong hai cơ sở đào tạo của Nhà trường: Cơ sở 1: Số 194 Lê Đức Thọ, Phường An Nhơn, TP.HCM. Cơ sở 2: Số 37 Kinh Dương Vương, Phường Phú Lâm, TP.HCM. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0042 | Nếu có kiểm tra năng lực tiếng Anh thì số tiền học kỳ I theo bảng sẽ thành bao nhiêu? | Nếu cộng thêm 250.000 đồng phí kiểm tra năng lực tiếng Anh vào ba khoản còn lại, tổng chi phí theo bảng là 14.500.000 đồng. | Học phí học kỳ I của DHV 2026 là 12.500.000 đồng, không tính thêm kiểm tra năng lực tiếng Anh. Nếu thêm kiểm tra năng lực tiếng Anh, tổng chi phí học kỳ I sẽ là 14.250.000 đồng. | WRONG_NUMERIC_FACT | HIGH | returned 14,250,000 instead of canonical 14,500,000 |
| UQ0057 | Khi đến trường làm thủ tục nhập học, tôi cần mang những giấy tờ chính nào? | Tân sinh viên cần mang thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học, học bạ trung học phổ thông, căn cước và giấy chứng nhận kết quả thi tốt nghiệp trung học phổ thông năm 2026. | Hồ sơ nhập học DHV 2026 cần chuẩn bị: - Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026. - Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. - Căn cước/Căn cước công dân. Lưu ý: mang bản gốc để đối chiếu, không cần công chứng. | LIST_INCOMPLETE | MEDIUM | method list omitted the expected học bạ item |
| UQ0064 | Nếu ở xa, tôi có thể nhập học mà chưa đến trường ngay không? | Về vấn đề này, Trường Đại học Hùng Vương TP. Hồ Chí Minh có hỗ trợ hình thức nhập học trực tuyến cho tân sinh viên ở xa: Hình thức nhập học: Bạn có thể lựa chọn nhập học trực tiếp tại trường hoặc nhập học trực tuyến. Nếu chưa thể đến trường ngay: Bạn có thể hoàn tất thủ tục và thanh toán học phí trên hệ thống UniZone bằng tài khoản do trường cấp. Sau khi hoàn tất hồ sơ và học phí theo yêu cầu, trường sẽ xác nhận nhập học. Nếu cần hỗ trợ thêm: Trường hợp bạn chưa nhận được tài khoản UniZone hoặc chưa rõ cách nộp hồ… | Hồ sơ nhập học DHV 2026 cần chuẩn bị: - Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. - Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026. - Học bạ THPT. Lưu ý: mang bản gốc để đối chiếu, không cần công chứng. | WRONG_INTENT | MEDIUM | remote-student online enrollment question got a generic document list |
| UQ0068 | Trường bắt đầu tiếp nhận tân sinh viên từ ngày nào? | Theo lịch trình tuyển sinh đại học chính quy tuyển mới năm 2026, thời gian nhập học cho thí sinh trúng tuyển là từ ngày 11/08/2026. | Trường bắt đầu tiếp nhận hồ sơ nhập học từ ngày 13/8/2026. | WRONG_DATE | HIGH | returned 13/8 and 8/8 where canonical deadline is 11/8 |
| UQ0074 | Ngoài thủ tục của trường, thí sinh trúng tuyển có phải xác nhận trên hệ thống của Bộ không? | Có. Thí sinh trúng tuyển phải xác nhận nhập học trên hệ thống hỗ trợ xét tuyển chung của Bộ Giáo dục và Đào tạo, sau đó tiếp tục hoàn tất thủ tục theo hướng dẫn của trường. | Hồ sơ nhập học DHV 2026 cần chuẩn bị: - Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026. - Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. Lưu ý: mang bản gốc để đối chiếu, không cần công chứng. | WRONG_INTENT | MEDIUM | question asks where to verify documents; answer listed documents instead |
| UQ0076 | Tôi đã trúng tuyển nhưng chưa xác nhận trên hệ thống của Bộ thì chỉ đến trường làm hồ sơ có đủ không? | Được, đến hết thời hạn xác nhận nhập học, nếu thí sinh không hoàn tất các thủ tục cần thiết, bao gồm xác nhận trên hệ thống của Bộ Giáo dục và Đào tạo và hoàn thiện hồ sơ nhập học, thí sinh có thể được xem là từ chối nhập học. Nếu bạn chưa xác nhận hoặc đã quá thời hạn xác nhận trên hệ thống, bạn nên liên hệ ngay tư vấn viên tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh để được kiểm tra trường hợp cụ thể và hướng dẫn cách xử lý. | Hồ sơ nhập học DHV 2026 cần chuẩn bị: - Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026. - Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. Lưu ý: mang bản gốc để đối chiếu, không cần công chứng. | WRONG_INTENT | MEDIUM | question asks confirmation/completion workflow; answer returned generic documents |
| UQ0083 | Thông tin chi tiết về hồ sơ và các bước nhập học được trường công bố ở đâu? | Tài liệu điểm trúng tuyển cho biết các hướng dẫn về hồ sơ, thời gian, địa điểm và quy trình nhập học được đăng trên website tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh. | Hồ sơ nhập học DHV 2026 cần chuẩn bị: - Thư mời nhập học bản chính hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học. - Căn cước/Căn cước công dân. - Giấy chứng nhận kết quả thi tốt nghiệp THPT năm 2026. Lưu ý: mang bản gốc để đối chiếu, không cần công chứng. | WRONG_INTENT | MEDIUM | question asks where the published enrollment guidance is located; answer returned a generic document checklist |
| UQ0085 | Mốc 13/8 và mốc 21/8 trong hướng dẫn có phải cùng một ý nghĩa không? | Mốc 13/08/2026 và mốc 21/08/2026 là hai mốc khác nhau và có ý nghĩa khác nhau trong quá trình nhập học tại Trường Đại học Hùng Vương TP. Hồ Chí Minh. Mốc 13/08/2026: Liên quan đến quyền lợi và chính sách hỗ trợ của trường. Tân sinh viên hoàn tất xác nhận trước ngày 13/08/2026 sẽ được hưởng mức ưu đãi cao nhất của chương trình hỗ trợ UniBridge, trong đó có hỗ trợ học phí học kỳ I và các quyền lợi tương ứng theo mức học bổng. Mốc 21/08/2026: Là thời hạn xác nhận nhập học trên Hệ thống hỗ trợ tuyển sinh chung của Bộ … | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trường. | WRONG_SCOPE | HIGH | in-scope admissions schedule question was rejected before retrieval |
| UQ0086 | Thông điệp tuyển sinh năm 2026 của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì? | Thông điệp được sử dụng trong cổng tuyển sinh năm 2026 là “Giá trị thật - Tương lai thật”, gắn với định hướng thực học, thực hành và khả năng thích ứng với môi trường làm việc. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trường. | WRONG_SCOPE | MEDIUM | verified school slogan question was rejected before retrieval |
| UQ0089 | Tổ hợp môn xét tuyển của trường gồm những môn nào? | Năm 2026, khi xét tuyển bằng kết quả kỳ thi tốt nghiệp trung học phổ thông, Trường Đại học Hùng Vương TP. Hồ Chí Minh xây dựng tổ hợp xét tuyển theo 2 cấu trúc chính, thay vì cố định một số tổ hợp truyền thống. Tổ hợp 1: Toán + 2 môn có điểm cao nhất Trong cấu trúc này, Toán là môn bắt buộc, sau đó trường chọn thêm 2 môn có điểm cao nhất của thí sinh trong các môn: Ngữ văn, Ngoại ngữ, Vật lý, Hóa học, Sinh học, Lịch sử, Địa lý, Tin học Giáo dục kinh tế và pháp luật Công nghệ công nghiệp. Ví dụ, nếu bạn có điểm Toá… | Mình liệt kê các phương thức xét tuyển được ghi nhận trong dữ liệu DHV: 1. Xét kết quả kỳ thi tốt nghiệp THPT năm 2026 2. 1.4. Xét tuyển kết quả học tập THPT (học bạ) 3. 1.5. Xét kết quả kỳ thi Đánh giá năng lực 4. 1.6. Xét kết quả bài thi Đánh giá năng lực chuyên biệt (H-SCA) 5. 1.7. Xét tuyển đối với thí sinh tốt nghiệp trung cấp | WRONG_INTENT | HIGH | subject-combination question returned admission methods |
| UQ0096 | Đạt giải Khuyến khích cấp quốc gia thì được cộng bao nhiêu điểm? | Thí sinh có giải từ Khuyến khích cấp quốc gia được cộng 1,50 điểm theo chính sách cộng điểm khuyến khích. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0098 | Giải Ba cấp tỉnh hoặc thành phố được cộng mấy điểm? | Giải Ba hoặc Khuyến khích cấp tỉnh, thành phố được cộng 1,00 điểm. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0099 | Giải cấp trường có được tính điểm khuyến khích không? | Có. Giải Nhất, Nhì hoặc Ba cấp trường trong phạm vi được quy định sẽ được cộng 0,50 điểm. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0106 | Cơ cấu tổ chức của Trường Đại học Hùng Vương TP. Hồ Chí Minh gồm những nhóm đơn vị chính nào? | Cơ cấu của trường gồm Hội đồng trường, Hội đồng Khoa học và Đào tạo, Ban Giám hiệu, các khoa và viện đào tạo, cùng các phòng ban và đơn vị trực thuộc. | Theo thông tin cung cấp trong tài liệu, cơ cấu tổ chức của Trường Đại học Hùng Vương TP. Hồ Chí Minh bao gồm các nhóm đơn vị chính như sau: 1. Ban giám hiệu: Quản lý toàn diện hoạt động của trường. 2. Các khoa: Đào tạo các chuyên ngành cụ thể. 3. Hội đồng sáng lập: Đặt tên và ban hành các quyết định quan trọng cho trường. Tuy nhiên, tài liệu không cung cấp chi tiết về các đơn vị tổ chức cụ thể trong các khoa hoặc các chức vụ cụ thể trong Ban giám hiệu. Để có thông tin chi tiết hơn về cơ cấu tổ chức cụ thể, cần xem… | LIST_INCOMPLETE | MEDIUM | school-governance list omitted required councils/faculties |
| UQ0107 | Quỹ Vườn ươm Khởi nghiệp của trường được giới thiệu với quy mô ban đầu bao nhiêu? | Tài liệu tổng quan tuyển sinh giới thiệu Quỹ Vườn ươm Khởi nghiệp với giá trị ban đầu 1 triệu USD để đồng hành cùng các ý tưởng sáng tạo và khởi nghiệp của sinh viên. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trường. | WRONG_SCOPE | MEDIUM | verified school overview fact was rejected by an overly narrow scope policy |
| UQ0133 | Sinh viên Trường Đại học Hùng Vương TP. Hồ Chí Minh có được tiếp cận môi trường doanh nghiệp từ sớm không? | Có. Tài liệu tuyển sinh năm 2026 cho biết trường phát triển mô hình học tập gắn với thực hành và doanh nghiệp để sinh viên sớm tiếp cận môi trường nghề nghiệp. | Tôi không thể trả lời câu hỏi này vì nội dung không nằm trong phạm vi tuyển sinh của Trường Đại học Hùng Vương TP.HCM. Tôi chỉ hỗ trợ các câu hỏi liên quan đến tuyển sinh của trường. | WRONG_SCOPE | MEDIUM | verified early-enterprise-access fact was rejected despite explicit DHV target |
| UQ0138 | Năm 2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh có ký hợp tác với Đại học Chosun của Hàn Quốc không? | Có. Ngày 28/01/2026, Trường Đại học Hùng Vương TP. Hồ Chí Minh và Đại học Chosun ký biên bản ghi nhớ nhằm thúc đẩy hợp tác trong đào tạo và nghiên cứu khoa học. | Theo tài liệu đã xác minh của DHV: Trường Đại học Chosun – Hàn Quốc: ký Biên bản Ghi nhớ hợp tác (MOU) với DHV vào tháng 01/2026. | LLM_PARTIAL_ANSWER | MEDIUM | partnership answer omitted the exact 28/01/2026 date and requested benefits |
| UQ0160 | Viện Công nghệ Tiên tiến và Trí tuệ Nhân tạo có đào tạo trình độ đại học về Trí tuệ nhân tạo không? | Có. Trang chính thức của Viện IATAI liệt kê Trí tuệ nhân tạo trong nhóm chương trình đào tạo bậc đại học. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0179 | Điểm trúng tuyển ngành Tâm lý học DHV 2026 cao hơn các ngành khác vì sao? | Điểm trúng tuyển ngành Tâm lý học đợt 1 là 20,0 điểm (cùng với Luật và Luật Kinh tế), trong khi các ngành còn lại là 15,0 điểm. | Điểm trúng tuyển được công bố: học bạ: 22.5 điểm; ĐGNL: 762 điểm; thi tốt nghiệp THPT: 20 điểm. | LLM_PARTIAL_ANSWER | MEDIUM | returned score values but did not answer why the major is higher |
| UQ0202 | Khoa Ngôn ngữ hợp tác với doanh nghiệp nhằm hỗ trợ sinh viên trong những hoạt động học tập nào? | Các quan hệ hợp tác được xây dựng để đưa sinh viên đi trải nghiệm thực tế, nâng cao kỹ năng ngôn ngữ và kỹ năng mềm, đồng thời tạo cơ sở cho hoạt động thực tập tốt nghiệp. | Có. Dữ liệu DHV 2026 ghi nhận Khoa Ngôn ngữ trong hệ sinh thái đơn vị chính thức của trường. Tài liệu này chỉ xác nhận đơn vị và thông tin chung; chưa kết luận về chương trình, điều kiện hoặc thủ tục cụ thể. | LLM_PARTIAL_ANSWER | MEDIUM | returned generic Khoa existence instead of requested cooperation benefits |
| UQ0224 | DHV có đào tạo Logistics không? | Có, DHV có chuyên ngành Quản trị Logistics thuộc ngành Quản trị kinh doanh (mã 7340101). Đây cũng là một trong 12 chương trình có chỉ tiêu xét tuyển bổ sung 2026. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0236 | DHV hợp tác với đơn vị nào để mở rộng cơ hội thực tập tại Hoa Kỳ cho sinh viên? | Nhà trường ký biên bản ghi nhớ hợp tác với Công ty Cổ phần Học viện Hạnh phúc Việt Nam trong chương trình được công bố ngày 19/06/2026. | Theo tài liệu đã xác minh của DHV: HỢP TÁC – ĐỐI TÁC Trường Đại học Hùng Vương TP. Hồ Chí Minh đẩy mạnh hợp tác với các trường đại học, tổ chức giáo dục, doanh nghiệp và đơn vị nghề nghiệp trong và ngoài nước. | LLM_PARTIAL_ANSWER | MEDIUM | returned generic partnerships instead of the named Học viện relationship |
| UQ0252 | Mạng lưới đối tác của Khoa Ngôn ngữ trải rộng ở những nhóm lĩnh vực nào? | Khoa có các đối tác hoạt động trong nhiều lĩnh vực như thương mại, xuất nhập khẩu, tài chính và giáo dục – đào tạo. | Có. Dữ liệu DHV 2026 ghi nhận Khoa Ngôn ngữ trong hệ sinh thái đơn vị chính thức của trường. Tài liệu này chỉ xác nhận đơn vị và thông tin chung; chưa kết luận về chương trình, điều kiện hoặc thủ tục cụ thể. | LLM_PARTIAL_ANSWER | MEDIUM | returned generic Khoa text instead of requested partner fields |
| UQ0327 | Lễ ký kết với 6 doanh nghiệp ngày 26/06/2026 mang lại những cơ hội nào cho sinh viên? | Hoạt động ký kết với 6 doanh nghiệp hướng tới xây dựng học kỳ doanh nghiệp, mời chuyên gia chia sẻ thực tiễn và kết nối thực tập, hướng nghiệp, tuyển dụng cho sinh viên. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0339 | khi trúng tuyển thì trường sẽ thông báo vào đâu ạ? | Khi trúng tuyển, bạn nên kiểm tra kết quả trên hệ thống hỗ trợ tuyển sinh chung của Bộ Giáo dục và Đào tạo và theo dõi website tuyển sinh chính thức của Trường Đại học Hùng Vương TP. Hồ Chí Minh để xem hướng dẫn nhập học. Ngoài ra, tài liệu nhập học của trường có nhắc đến thư mời nhập học hoặc tin nhắn Zalo xác nhận đủ điều kiện nhập học, bạn cũng nên theo dõi Zalo/số điện thoại đã đăng ký với trường. | Tôi chưa biết câu trả lời này vì hiện chưa tìm thấy thông tin trong dữ liệu tuyển sinh DHV đã được kiểm chứng. Bạn vui lòng tham khảo thông tin chính thức từ Trường Đại học Hùng Vương TP.HCM. | FALSE_NO_DATA | HIGH | canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient |
| UQ0340 | đóng tiền mặt thì đóng ở đâu ạ vào thời gian nào ạ? | Theo thông tin nhập học năm 2026, trường chưa nêu rõ riêng quầy hoặc địa điểm thu học phí bằng tiền mặt. Trường chỉ công bố hai địa điểm tiếp nhận nhập học trực tiếp là: 194 Lê Đức Thọ, Phường An Nhơn, TP. Hồ Chí Minh 37 Kinh Dương Vương, Phường Phú Lâm, TP. Hồ Chí Minh Thời gian tiếp nhận là 06:00–18:00, từ 11/08/2026 đến 10/09/2026, kể cả thứ Bảy, Chủ nhật và ngày lễ. Tại đây, tư vấn viên sẽ hướng dẫn sinh viên về việc thanh toán học phí. | Các mốc nhập học có trong dữ liệu DHV 2026: - Chính sách hỗ trợ sau ngày 13/8/2026 - Khuyến khích: Thí sinh nên hoàn tất xác nhận trước ngày 13/8/2026 để được ghi - Đặc biệt, tân sinh viên hoàn tất xác nhận trước ngày 13/8/2026 sẽ được hưởng mức - Dhv tiếp nhận nhập học 06:00 – 18:00 Từ 11/08/2026 đến 10/09/2026 - (Xuyên suốt Thứ 7, Chủ Nhật & Ngày Lễ) - Hoàn tất xác nhận trước ngày 13/8/2026, tân sinh viên sẽ được hưởng mức ưu đãi - 1. Hoàn tất xác nhận trước ngày 13/8/2026 để được hưởng mức ưu đãi cao nhất | LLM_PARTIAL_ANSWER | MEDIUM | did not answer the cash-payment location/absence-of-counter details |
| UQ0378 | Chương trình Marketing trang bị kiến thức về nghiên cứu thị trường như thế nào? | Sinh viên Marketing được học cách nghiên cứu thị trường để nhận diện nhu cầu, xu hướng và cơ hội kinh doanh. | Chương trình Marketing tại Trường Đại học Hùng Vương TP.HCM (DHV) năm 2026 trang bị kiến thức về nghiên cứu thị trường thông qua các chương trình như Quản trị Marketin, Digital Marketing, Truyền thông và quan hệ công chúng, Truyền thông số. Bạn có quan tâm đến chương trình nào cụ thể không? | LLM_PARTIAL_ANSWER | MEDIUM | listed programs but did not answer how market knowledge is taught |

## 10. Contract-Blocked Rows (Not PASS)

The following 64 rows were safely refused as `out_of_scope` with zero retrieval/evidence. They are not counted as functional PASS because their canonical expected answers require a product scope/evidence contract decision. This is a DATA_REVIEW handoff, not evidence that the chatbot may invent answers.

| ID | Question | Runtime scope | Retrieval | Evidence | Decision needed |
|---|---|---|---:|---:|---|
| UQ0108 | Viện IATAI của trường phụ trách những lĩnh vực đào tạo và nghiên cứu nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0150 | Việc hợp tác giữa trường và Công ty Công nghệ PREP năm 2026 hướng tới những lợi ích nào cho sinh viên? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0189 | Các phòng lab công nghệ của DHV chỉ dùng cho giờ thực hành trên lớp hay còn có mô hình hoạt động khác? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0209 | DHV có trung tâm Công nghệ riêng không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0231 | Aero Space Lab tại DHV phục vụ nghiên cứu những công nghệ nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0245 | UniHackfest Unitour × DHV giúp sinh viên tiếp cận những xu hướng công nghệ nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0246 | Tại UniHackfest Unitour × DHV, sinh viên được nghe chia sẻ gì về hệ sinh thái Solana? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0248 | DHV ký biên bản ghi nhớ với SCTV vào thời điểm nào trong năm 2026? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0249 | UniHackfest Unitour × DHV có đề cập đến cơ hội nghề nghiệp trong các lĩnh vực công nghệ mới không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0250 | Khoa Quản trị Kinh doanh – Marketing tổ chức tọa đàm về mô hình CO-OP vào thời điểm nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0254 | Workshop “La bàn nghề nghiệp” của Khoa BAM hỗ trợ sinh viên về nội dung gì? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0256 | Sinh viên Khoa Kỹ thuật Công nghệ đã báo cáo bao nhiêu đề tài nghiên cứu khoa học cấp trường trong đợt công bố tháng 7/2026? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0258 | Đề tài SV-19-24 của sinh viên Khoa Kỹ thuật Công nghệ hướng đến nhu cầu nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0261 | Sinh viên Khoa Kỹ thuật Công nghệ có nghiên cứu phần mềm phục vụ các cuộc thi không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0262 | Hoạt động nghiên cứu khoa học cấp trường giúp sinh viên Khoa Kỹ thuật Công nghệ rèn những kỹ năng gì? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0264 | Lễ ra quân Chiến dịch Mùa Hè Xanh 2026 của DHV được tổ chức vào ngày nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0265 | Sinh viên Khoa Kỹ thuật Công nghệ tham gia Mùa Hè Xanh 2026 tại địa bàn nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0267 | Chiến dịch Mùa Hè Xanh 2026 tạo cơ hội gì cho sinh viên DHV ngoài hoạt động học tập? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0268 | Food & Hospitality Vietnam 2026 tạo môi trường quốc tế cho sinh viên DHV ở quy mô ra sao? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0269 | Trong Học kỳ Doanh nghiệp năm 2026, sinh viên lớp TN07 đã được đưa đến thực tập ở đâu? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0271 | Sinh viên DHV đạt những hạng giải nào tại Talent Administrator 2026? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0272 | Talent Administrator 2026 là sân chơi học thuật gắn với nhóm kiến thức nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0274 | SCFF26 đề cập đến những lĩnh vực công nghệ nổi bật nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0275 | Giảng viên Khoa Kỹ thuật Công nghệ tham dự IAAA 2026 vào thời gian và địa điểm nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0280 | Workshop “Chiến lược bán lẻ đa kênh toàn diện” của Khoa BAM được tổ chức khi nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0281 | DHV thành lập những câu lạc bộ công nghệ nào cùng với hệ thống phòng lab năm 2026? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0282 | Workshop về bán lẻ đa kênh mang đến cho sinh viên những nội dung thực tiễn nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0284 | Sinh viên có thể học được những nội dung chuyên môn nào trong Học kỳ Doanh nghiệp của FBA? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0292 | Sinh viên tìm hiểu công nghệ nhân sự nào trong chuyến tham quan JobTest? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0296 | Chương trình “Khởi nghiệp cùng Sinh viên DHV 2026” của Khoa BAM diễn ra vào thời điểm nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0297 | Sinh viên Khoa BAM tham gia Company Tour 2026 tại Kim Oanh Group vào ngày nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0300 | Chuyến tham quan Kim Oanh Group mang lại giá trị gì cho sinh viên Khoa BAM? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0302 | Sinh viên FBA tham gia sân chơi “Nhà đầu tư tương lai 2026” do đơn vị nào tổ chức? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0305 | Đội sinh viên FBA đạt kết quả gì tại cuộc thi “Nhà đầu tư tương lai 2026”? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0329 | Công việc của một AI Researcher được Viện IATAI mô tả gồm những nhiệm vụ nào? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0330 | AI Developer thường đảm nhiệm những công việc gì theo thông tin của Viện IATAI? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0331 | Mạng lưới đối tác của Viện IATAI có hoạt động trong lĩnh vực học máy không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0332 | Mạng lưới đối tác công nghệ của Viện IATAI có bao gồm lĩnh vực điện toán đám mây không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0333 | Viện IATAI có kết nối đối tác trong lĩnh vực an toàn thông tin không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0336 | khi là sinh viên của trường DHV thì sẽ được những quyền lợi gì ạ? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0341 | khi được cấp tài khoản edu của trường thì tài khoản và mật khẩu là gì ạ? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0343 | trường DHV có làm đồ án và bảo vệ đồ án như các trường khác hay không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0344 | trường có quy định khi đi học có bắt buộc phải mặc đồng phục không ạ? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0345 | bãi đỗ xe có tính phí không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0346 | nếu phải mua riêng đồng phục thì giá sẽ là bao nhiêu ạ? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0347 | trường có tổ chức lễ khai giảng cho sinh viên không ạ? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0349 | trường có phòng cho sinh viên nghỉ ngơi sau mỗi tiết học không ạ? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0363 | Một hướng việc làm sau ngành Quản trị kinh doanh có phải là chuyên viên nhân sự không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0367 | Sau khi ra trường, cử nhân Quản trị kinh doanh có thể hướng đến nghề vị trí quản lý doanh nghiệp không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0372 | Học ngành Quản trị kinh doanh có giúp sinh viên rèn khả năng thích ứng trong môi trường đa văn hóa không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0389 | Một hướng việc làm sau ngành Marketing có phải là nhân viên phát triển thị trường không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0393 | Sau khi ra trường, cử nhân Marketing có thể hướng đến nghề trưởng phòng marketing không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0409 | Ngành Thương mại điện tử có đào tạo phần kiến thức hoạt động và môi trường doanh nghiệp không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0415 | Một hướng việc làm sau ngành Thương mại điện tử có phải là tư vấn giải pháp công nghệ không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0419 | Sau khi ra trường, cử nhân Thương mại điện tử có thể hướng đến nghề nhân sự tại doanh nghiệp cung cấp dịch vụ e-marketing không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0441 | Một hướng việc làm sau ngành Kinh tế quốc tế có phải là chuyên viên xuất nhập khẩu không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0442 | Sinh viên tốt nghiệp Kinh tế quốc tế có thể phát triển nghề nghiệp theo hướng chuyên viên phát triển thị trường quốc tế không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0445 | Sau khi ra trường, cử nhân Kinh tế quốc tế có thể hướng đến nghề chuyên viên thu mua quốc tế không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0453 | Sinh viên ngành Kinh tế quốc tế có được rèn luyện kỹ năng thích ứng với môi trường đa văn hóa không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0455 | Ba phòng thí nghiệm công nghệ trọng điểm được DHV đưa vào vận hành năm 2026 gồm những phòng nào? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0456 | Trong quá trình học ngành Kinh tế quốc tế, sinh viên có cơ hội học theo định hướng gắn với môi trường làm việc không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0467 | Một hướng việc làm sau ngành Tài chính - Ngân hàng có phải là giao dịch viên ngân hàng không? | in_scope_dhv | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0471 | Sau khi ra trường, cử nhân Tài chính - Ngân hàng có thể hướng đến nghề chuyên viên tín dụng không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |
| UQ0497 | Sau khi ra trường, cử nhân Kế toán có thể hướng đến nghề kế toán thuế không? | general_out_of_scope | 0 | 0 | Approve corpus/scope or keep refusal |

## 11. Failure Clusters

| Cluster | Count | Priority | Owner |
|---|---:|---|---|
| CONTRACT_SCOPE_UNRESOLVED | 64 | P2 | DATA_REVIEW |
| FALSE_NO_DATA | 15 | P1 | LEAD_CODER |
| LLM_PARTIAL_ANSWER | 10 | P2 | LEAD_CODER |
| WRONG_INTENT | 6 | P1 | LEAD_CODER |
| WRONG_SCOPE | 4 | P1 | LEAD_CODER |
| LIST_INCOMPLETE | 2 | P2 | LEAD_CODER |
| WRONG_QUERY_MODE | 1 | P1 | LEAD_CODER |
| WRONG_NUMERIC_FACT | 1 | P1 | LEAD_CODER |
| WRONG_DATE | 1 | P1 | LEAD_CODER |

## 12. Security / Regression Review

- No new QA-side source changes were made.
- External/scope-safe refusals showed zero retrieval/evidence in the retest; no new DHV factual leakage was observed in those rows.
- The retest did expose a false-negative scope regression for verified DHV facts (`UQ0085`, `UQ0086`, `UQ0107`, `UQ0133`).
- The deterministic routing regression over-selects `phuong_thuc_xet_tuyen` and `ho_so` for `dang_ky_xet_tuyen`; this can broaden retrieval and contaminate evidence selection.
- No unbounded concurrency was used; calls were sequential to avoid Ollama contention.

## 13. Lead Claims Verified

| Claim | Verified? | Evidence |
|---|---|---|
| 120 original FAIL IDs were rerun with real runtime | YES | Independent checkpoint contains 120/120 rows; Ollama and Chroma were available |
| Lead runtime status split was 38 ok / 14 no_data / 68 out_of_scope | NO | Independent split is 37 ok / 15 no_data / 68 out_of_scope; this is `REPORT_CODE_MISMATCH` |
| External/scope fixes avoid unsupported retrieval | PARTIAL | External refusals had retrieval=0/evidence=0, but four verified in-scope DHV questions were also refused |
| Year semantics fixed | PARTIAL | UQ0007 extracts year 2026 but still returns NO_DATA with evidence present |
| Full regression is 215 passed / 2 failed / 4 skipped | NO | Independent run: 215 passed / 5 failed / 4 skipped |
| Task C category routing is aligned | NO | 3 subtests fail because plan categories are `dang_ky_xet_tuyen`, `phuong_thuc_xet_tuyen`, `ho_so` instead of only `dang_ky_xet_tuyen` |

## 14. Acceptance Criteria

| Criterion | Result |
|---|---|
| All original 120 rows executed | PASS |
| No environment block in this retest | PASS |
| No external-school DHV factual leak observed in refused rows | PASS for tested external/scope-safe rows |
| No wrong-year data claim in the retested answers | BLOCKED/FAIL: UQ0007 remains NO_DATA despite year=2026 evidence |
| Factual answers grounded and complete | FAIL: 39 confirmed FAIL rows |
| No wrong intent/query mode | FAIL: UQ0010, UQ0016, UQ0089 and others |
| COUNT/LIST and numeric facts remain correct | FAIL: UQ0003, UQ0013, UQ0016, UQ0042, UQ0057 |
| Regression suites clean | FAIL: 5 full-suite failures, 3 focused Task C subtests |
| All canonical questions resolved or contract-approved | BLOCKED: 64 contract-scope decisions pending |

## 15. Handoff to Lead Coder

### Priority 1

1. Fix the 15 `FALSE_NO_DATA` rows as one coverage/filter/planner cluster. Preserve the no-hallucination boundary, but when verified evidence is present (`UQ0007`, `UQ0017`, `UQ0024`, `UQ0025`, `UQ0026`, `UQ0096`, `UQ0098`, `UQ0099`, `UQ0160`, `UQ0224`, `UQ0327`) the answer planner must not discard it. Acceptance: each canonical fact is answered from relevant year/school evidence, or the dataset contract is explicitly changed by DATA_REVIEW.
2. Fix wrong intent/query-mode routing for `UQ0010`, `UQ0016`, `UQ0089` and the related partial rows. Acceptance: expected requested information and query mode are preserved through route, retrieve, plan, validator, and final answer.
3. Fix numeric/date/list defects: `UQ0042`, `UQ0057`, `UQ0068`, plus incomplete enumeration rows. Acceptance: canonical numeric values, dates, and unique item sets match structured evidence.

### Priority 2

1. Narrow `dang_ky_xet_tuyen` category routing so it does not automatically add `phuong_thuc_xet_tuyen` and `ho_so` when the test contract requires a single category. Rerun the three failing Task C subtests.
2. Restore in-scope handling for verified DHV schedule/school facts (`UQ0085`, `UQ0086`, `UQ0107`, `UQ0133`) without weakening external-school guards.
3. Improve answer planning/completeness for overview, partnership, school governance, payment, and program-teaching questions listed in the confirmed failure table.

### Priority 3 — DATA_REVIEW

1. Decide whether the 64 contract-blocked questions are part of supported production scope. If yes, add/verify official evidence and explicit intents/categories; if no, remove them from the canonical production evaluation contract rather than silently counting safe refusal as PASS.
2. Resolve the two non-routing full-suite failures: raw PDF official-URL policy and the hard-coded skipped-unverified manifest expectation. Do not alter tests solely to make them green; align policy/manifest/test fixture intentionally.

## 16. Final Verdict

**FULL_SWEEP_P1_RETEST_FAIL**

Reason: all 120 runtime calls completed, but only 16/120 were confirmed factual PASS, 40 were confirmed FAIL, and 64 remain contract-blocked. The independent full suite also has 5 failures, including 3 Task C routing failures not reported by the Lead report. This is not `FULL_QUESTION_SWEEP_PASS` and not an environment block.

QA stops here. No deployment and no product-code changes were made.
