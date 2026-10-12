# FULL SWEEP P1 FIX REPORT

## 1. Scope

- Xử lý các lỗi deterministic thuộc `SWEEP-SCOPE-001`, `SWEEP-SCOPE-002`, `SWEEP-INTENT-001`, `SWEEP-YEAR-001`.
- Rà soát `WRONG_ENTITY` / `WRONG_SCOPE` còn lại để phân biệt code defect với câu hỏi ngoài contract hoặc thiếu verified evidence.
- Không sửa dataset 500 Q&A, RAW PDF, model/embedding; không deploy; không làm Priority 3.
- Chạy lại đúng 120 dòng `result=FAIL` qua runtime Ollama + Chroma thật; 380 dòng `BLOCKED` được loại trừ. Runtime status không đồng nghĩa QA factual pass.
- Freshness audit ban đầu xác nhận active Chroma cũ có 270 records trong khi processed JSON canonical tạo 310 chunks. Theo điều kiện cho phép của task, build canonical từ `data/processed` vào candidate rồi thay active local collection; bản cũ được giữ recoverable tại `chroma_backup_20261009`.
- Real runtime rerun cuối dùng active `chroma_db/dhv_admissions_2026` 310 records; không build từ raw PDF, không sửa Chroma ngoài local/dev, không deploy.

## 2. QA Bugs Addressed

| Bug | Kết quả xử lý |
|---|---|
| `SWEEP-SCOPE-001` – “trường” chung bị hiểu thành trường ngoài | Generic school noun không tự tạo school target; “trường khác” và tên trường ngoài vẫn bị chặn. |
| `SWEEP-SCOPE-002` – tên pháp lý DHV bị AMBIGUOUS | Chuẩn hóa biến thể tên DHV có/không dấu, dấu câu, viết hoa và khoảng trắng; bare “Hùng Vương” vẫn ambiguous. |
| `SWEEP-INTENT-001` – câu tuyển sinh bị OUT_OF_SCOPE/clarification | Tăng ưu tiên tín hiệu tuyển sinh/phương thức/cộng điểm/điểm thi tường minh; tách ngày sự kiện khỏi lịch tuyển sinh. |
| `SWEEP-YEAR-001` – lấy nhầm năm tốt nghiệp | Ưu tiên năm gắn với “xét tuyển/tuyển sinh/đợt”; UQ0007 lấy 2026 và real runtime trả lời `ok`. |
| UQ0085 – so sánh mốc 13/8 và 21/8 | Root cause là date evidence viết `21 tháng 8 năm 2026` không được ưu tiên trước context budget; sau fix real runtime phân biệt được chính sách ưu đãi và hạn xác nhận trên hệ thống Bộ. |
| `SWEEP-DATA-001` | Chỉ mở hẹp thông tin trường có verified source/category; không tự mở event, nghề nghiệp, lab hay student-life. |
| `SWEEP-DATA-002` | Task 09 fixture dựa vào document identity trong manifest hiện hành, không filename cũ. |
| `SWEEP-TEST-001` | Task C kiểm tra numeric semantics của 15 điểm, không đòi wording literal “từ 15 điểm”. |

## 3. Root Cause – WRONG_ENTITY

- Resolver chưa nhận diện đủ legal-name variants của DHV nên một số câu tên đầy đủ chuyển sang `AMBIGUOUS`.
- Marker tổng quát “trường + từ kế tiếp” có thể nhầm danh từ chỉ địa điểm/đối tượng (“đến trường”, “trường lấy…”, “nhà trường…”) thành external school.
- Sửa theo semantic entity/school matching và vai trò subject/object; không thêm rule theo question ID.
- Kiểm tra: legal-name variants → `DHV`; “Điểm chuẩn Hùng Vương?” vẫn `AMBIGUOUS`; external school vẫn không retrieval.

## 4. Root Cause – WRONG_SCOPE

- Scope guard coi một số cụm trường chung hoặc câu thông tin có verified school corpus là ngoài phạm vi.
- Generic school noun được giữ `UNSPECIFIED` để áp dụng DHV default; thêm allowlist hẹp cho topic school-info có verified evidence.
- Không mở các câu event-specific, company-specific, viện/lab chưa index, career theo ngành hoặc student-life không có nguồn phù hợp.
- Trong 68 dòng QA ban đầu thuộc `WRONG_SCOPE`, lượt cuối: 21 `ok`, 2 `no_data`, 45 `out_of_scope`. Cần QA xét từng câu `no_data`/`out_of_scope`; không tuyên bố các câu `ok` đã factual-pass.
- UQ0085 là admissions question đã approved; trước fix bị `no_data` do chunk deadline dùng dạng chữ `21 tháng 8 năm 2026` nên priority chỉ nhận dạng ngày dạng `dd/mm`. Cập nhật date-semantic evidence priority để nhận cả hai biểu diễn, giữ hai fact cần thiết trong bounded evidence và chỉ trả lời khi có cả ý nghĩa của hai mốc.

## 5. Root Cause – WRONG_INTENT

- Rule rộng về scope/động từ chỉ thời điểm có thể chạy trước hoặc ghi đè intent tuyển sinh cụ thể.
- Ưu tiên rule admission khi có tín hiệu rõ; nhận diện phương thức, cộng điểm, eligibility và điểm thi tường minh.
- Ngày tọa đàm/chương trình sự kiện không bị map thành `HOI_LICH_TUYEN_SINH` chỉ vì có “thời điểm”. Event-specific cases vẫn ngoài phạm vi nếu thiếu contract/evidence.
- UQ0013 được phân loại `HOI_PHUONG_THUC_XET_TUYEN`, `LIST`, không còn `OUT_OF_SCOPE`.

## 6. Root Cause – WRONG_YEAR

- Trích năm theo thứ tự xuất hiện có thể chọn năm tốt nghiệp/lịch sử trước năm admission.
- Bổ sung parser semantic cho admission year; cụm “xét tuyển năm 2026”, “tuyển sinh 2026”, “đợt 2026” được ưu tiên.
- UQ0007 và biến thể nhiều năm trích target year 2026. Trace real runtime cuối: `year=2026`, retrieval 1, 4 docs/evidence, status `ok`; câu trả lời dựa trên điều kiện tốt nghiệp THPT trong nguồn tuyển sinh 2026. QA vẫn cần xác nhận câu trả lời đáp đủ “có được tham gia không”.

## 7. Scope Guard Changes

- Phân biệt explicit DHV, named external school, ambiguous, mixed comparison và câu không nêu trường.
- “trường”/“nhà trường” chung không thành external entity.
- “trường khác”, “đại học khác”, “trường đại học khác” vẫn là external boundary.
- DHV là subject với object “các trường khác” (hợp tác/giao lưu) không thành `MIXED`; so sánh DHV với Văn Hiến vẫn `MIXED`.
- Với `OTHER_SCHOOL`, `MIXED`, `AMBIGUOUS`, boundary dừng trước retrieval; tests kiểm `retrieval_calls=0`, docs/evidence bằng 0.

## 8. DHV Alias / Legal Name Changes

- Nhận diện biến thể có/không dấu, case-insensitive, dấu câu và khoảng trắng dư: `Trường Đại học Hùng Vương TP. Hồ Chí Minh`, `Trường Đại học Hùng Vương TP.HCM`, `Đại học Hùng Vương TP. Hồ Chí Minh`, `Đại học Hùng Vương TP.HCM`, `TP HCM`, `TP.HCM`, `DHV`.
- Không biến mọi câu có “Hùng Vương” thành DHV: tên rút gọn “Hùng Vương” vẫn `AMBIGUOUS`, không retrieval.

## 9. Intent / Router Changes

- “DHV năm 2026 có những cách xét tuyển nào vậy ạ?” → `HOI_PHUONG_THUC_XET_TUYEN`, `LIST`, category `phuong_thuc_xet_tuyen`.
- Bonus/MOS/giải thưởng và câu hỏi có ngữ cảnh điểm thi được giữ trong intent admission tương ứng, không bị đẩy sang `OUT_OF_SCOPE`.
- Câu ghi rõ “3 môn thi tốt nghiệp” không hỏi clarification lại phương thức.
- Câu eligibility có major Luật nhận `major_name=Luật`, intent `HOI_NGUONG_DAU_VAO`.
- Giữ các query mode `COUNT`, `LIST`, `LIST_AND_COUNT`, `SINGLE_FACT` và deterministic count/list route.

## 10. Year Semantic Parsing Changes

- Parser chọn năm admission gắn với ngữ cảnh xét tuyển/tuyển sinh/đợt, không chọn năm đầu tiên.
- Tests gồm tốt nghiệp 2024/2025 + admission 2026, điểm thi 2025 dùng cho 2026, và tốt nghiệp trước 2026.
- UQ0007 `entities.year=2026`; trace cuối retrieval theo năm 2026, có 4 documents/evidence và status `ok`. QA cần xác minh câu trả lời nêu điều kiện đủ rõ, không chỉ dựa vào runtime status.

## 11. Dataset Contract Analysis

Inventory này phân loại các câu `WRONG_SCOPE` trong 120 dòng QA gốc theo phạm vi và evidence đang có; không khẳng định `status=ok` đồng nghĩa factual PASS.

### Supported

| question_id | domain | current_scope | data_available? | verified_source? | recommended_action |
|---|---|---|---|---|---|
| UQ0009, UQ0013, UQ0017, UQ0024, UQ0025, UQ0040–UQ0042, UQ0061, UQ0078, UQ0085, UQ0096, UQ0098, UQ0099, UQ0222, UQ0224, UQ0340 | Tuyển sinh, tính điểm, hồ sơ, học phí, lịch | Approved admissions | Có tài liệu/record tuyển sinh liên quan trong 2026 corpus; một vài câu hỏi cần xác minh chi tiết đúng theo intent và record | Có nguồn DHV chính thức cho tài liệu tuyển sinh 2026; QA cần kiểm từng fact/citation | Giữ trong scope; QA đối chiếu answer với evidence, đặc biệt điểm cộng, phép tính, khoản tiền và logistics. |
| UQ0001 | Thông tin tổng quan trường | Hỗ trợ hẹp khi có verified evidence | Có các đoạn tổng quan trong processed/Chroma | Có source DHV chính thức | Hỗ trợ phần được trích dẫn; không lấy canonical `source="Tự làm"` làm evidence. |
| UQ0202, UQ0252 | Hoạt động/đối tác Khoa Ngôn ngữ | Chỉ trả facts hiện diện trong verified school corpus | Có evidence cho hoạt động hợp tác chung và các nhóm lĩnh vực; UQ0202 chỉ được hỗ trợ ở mức thông tin tập thể, không khẳng định riêng vượt nguồn | Có đoạn nguồn DHV đã kiểm chứng | QA xác nhận answer không biến thông tin chung thành hoạt động riêng của khoa; không thêm lĩnh vực ngoài evidence. |

### Outside Current Contract

| question_id | domain | current_scope | data_available? | verified_source? | recommended_action |
|---|---|---|---|---|---|
| UQ0189, UQ0231, UQ0258, UQ0261, UQ0281, UQ0455 | Lab, nghiên cứu, câu lạc bộ công nghệ | Ngoài admissions contract hiện tại | Chưa có corpus/evidence đã duyệt đủ chi tiết trong runtime | Chưa xác minh được nguồn phù hợp trong active verified RAG evidence | Giữ `OUT_OF_SCOPE`; chỉ mở sau khi duyệt domain và ingest nguồn verified. |
| UQ0245, UQ0246, UQ0248, UQ0249, UQ0254, UQ0264, UQ0265, UQ0267, UQ0268, UQ0271, UQ0272, UQ0274, UQ0275, UQ0280, UQ0282, UQ0297, UQ0302, UQ0305 | Sự kiện, workshop, cuộc thi, hội nghị | Ngoài admissions contract hiện tại | Nội dung event-specific không được chứng minh bởi dữ liệu tuyển sinh chung | Nguồn cụ thể chưa được xác minh trong active corpus | Không map từ “thời điểm” sang lịch tuyển sinh; cần scope/data approval riêng. |
| UQ0236, UQ0269, UQ0284, UQ0292, UQ0300, UQ0329, UQ0330, UQ0331–UQ0333, UQ0363, UQ0389, UQ0415, UQ0441, UQ0467 | Nghề nghiệp, học kỳ doanh nghiệp, đối tác thực tập | Ngoài admissions contract hiện tại | Chưa có profile nghề nghiệp/chi tiết đối tác đầy đủ trong active Chroma | Chưa xác minh đủ bằng chứng cụ thể; không dùng `source="Tự làm"` | Không đưa khuyến nghị nghề nghiệp hay quan hệ đối tác chưa grounded; cần contract/data approval. |
| UQ0336, UQ0344–UQ0347, UQ0349 | Quyền lợi sinh viên, đồng phục, bãi xe, khai giảng, tiện ích | Ngoài admissions contract hiện tại | Corpus verified hiện tại không xác nhận đầy đủ các yêu cầu | Một số expected answer chỉ là evaluation reference, không phải provenance | Giữ ngoài scope; cần duyệt phạm vi và nguồn trước khi hỗ trợ. |
| UQ0107, UQ0209 | Quỹ/đơn vị và thông tin trường chi tiết | School-info chưa được mở tổng quát | Có thông tin liên quan trong processed overview ở một số chủ đề, nhưng category/index chưa nhất quán hoặc chưa chứng minh đúng câu hỏi | Processed overview có nguồn verified; coverage trong Chroma/category cần QA kiểm lại | Contract/taxonomy decision; không mở rộng retrieval chỉ để tăng sweep score. |

### Missing Verified Data

| question_id | domain | current_scope | data_available? | verified_source? | recommended_action |
|---|---|---|---|---|---|
| UQ0160 | Quan hệ giữa viện IATAI và chương trình/ngành | School-unit detail chưa được duyệt | Có chunks tổng quát/ngành nhưng không có evidence xác nhận đúng quan hệ; lượt cuối no-data | Không có câu nguồn phù hợp trong selected verified evidence | Giữ no-data/clarification; cần nguồn xác nhận relation cụ thể. |
| UQ0236 | Đối tác đưa sinh viên đi thực tập tại Hoa Kỳ | Ngoài admissions hiện tại | Không thấy fact về Hoa Kỳ/đơn vị cụ thể trong active verified corpus | Chưa xác nhận | Không suy diễn từ đoạn hợp tác chung; cần nguồn official cụ thể. |
| UQ0327 | Sự kiện ký kết với sáu doanh nghiệp và quyền lợi | Ngoài admissions hiện tại | Evidence tổng quan không chứng minh sự kiện/ngày/số doanh nghiệp cụ thể; lượt cuối no-data | Chưa xác nhận | Không khẳng định từ partnership paragraph chung; cần event source đã duyệt. |
| UQ0378 | Nội dung dạy kiến thức thị trường trong chương trình Marketing | Chi tiết chương trình chưa có trong active evidence | Có danh sách chương trình nhưng thiếu nội dung giảng dạy được hỏi; lượt cuối no-data | Chưa xác nhận | Không tự suy ra nội dung học; cần curriculum source hoặc giữ no-data. |

### Contract Decision Required

- Các nhóm event/workshop/lab/research, career, student-life ở trên chỉ được mở rộng sau khi owner sản phẩm xác nhận scope và QA xác minh corpus có provenance.
- Các `out_of_scope` còn lại ở rerun 120, được giữ an toàn chờ quyết định contract (chi tiết từng câu trong rerun V2): `UQ0108, UQ0150, UQ0189, UQ0209, UQ0231, UQ0245, UQ0246, UQ0248, UQ0249, UQ0250, UQ0254, UQ0256, UQ0258, UQ0261, UQ0262, UQ0264, UQ0265, UQ0267, UQ0268, UQ0269, UQ0271, UQ0272, UQ0274, UQ0275, UQ0280, UQ0281, UQ0282, UQ0284, UQ0292, UQ0296, UQ0297, UQ0300, UQ0302, UQ0305, UQ0329–UQ0333, UQ0336, UQ0341, UQ0343–UQ0347, UQ0349, UQ0363, UQ0367, UQ0372, UQ0389, UQ0393, UQ0415, UQ0419, UQ0441, UQ0442, UQ0445, UQ0453, UQ0455, UQ0456, UQ0467, UQ0471, UQ0497`.
- Các chủ đề cần quyết định bao gồm: IATAI/đơn vị và cơ sở vật chất; đối tác/doanh nghiệp; sự kiện/workshop/cuộc thi; nghiên cứu; nghề nghiệp/đầu ra; đời sống và tiện ích sinh viên. Không đổi chúng thành DHV admission facts chỉ để giảm metric.
- Câu canonical mang `source="Tự làm"` là expected-answer reference, không phải official verified evidence; không huấn luyện, index hoặc trích làm production fact trong task này.
- Freshness đã đối chiếu bằng loader/build audit: processed JSON canonical cung cấp 298 loader documents từ 6 verified JSON documents; splitter/build tạo 310 chunks. Active collection mới có đúng 310 rows và sáu document identities. Không có build hash byte-level trong metadata; nội dung/identity và canonical audit đã xác nhận dùng cùng nguồn processed hiện tại.

## 12. Task 09 Alignment

- Test lấy tài liệu `thong_tin_truong` theo identity từ manifest hiện hành, kiểm processed JSON, verified metadata, page coverage và nội dung; không dựa filename cũ.
- `tests/test_task_09.py` nằm trong targeted suite đã chạy và pass.
- Không thay RAW PDF hoặc manifest trong task này.

## 13. Task C Alignment

- Numeric threshold assertions kiểm tra đúng ngưỡng 15/18/600 và ý nghĩa số học thay vì bắt buộc chuỗi chữ “từ 15 điểm”.
- `tests/test_task_c.py` nằm trong targeted suite và full suite; không đổi canonical Q&A.

## 14. Files Changed

| File | Function / area | Reason |
|---|---|---|
| `src/chatbot/scope_guard.py` | School target detection / scope decision | Semantic school boundary, generic “trường”, comparison subject/object, DHV aliases. |
| `src/chatbot/query_analysis.py` | Intent rules, verified school-info scope, year/entity analysis | Admissions routing và school-info allowlist hẹp; giữ event/unsupported scope an toàn. |
| `src/chatbot/year_semantics.py` | Admission-year semantic extraction | Phân biệt target admission year với graduation/history year. |
| `src/chatbot/rag_chain.py` | School-info/admission evidence answers, route integration | Trả lời chi tiết có điều kiện từ selected verified evidence; mở rộng lấy đủ top-k cho một số câu thủ tục; giữ deterministic routes. |
| `src/chatbot/rag_chain.py` | `_prioritize_admission_date_comparison_documents` | Đưa deadline có ngày viết dạng chữ vào bounded evidence đúng thứ tự để UQ0085 dùng đủ hai mốc. |
| `src/chatbot/rag_chain.py` | Verified tuition fallback | Chỉ dùng canonical `tuition` record có provenance DHV/2026/verified; ngăn nhầm học phí với tổng chi phí và giữ nguyên luồng generation cho metadata fixture chung. |
| `src/retrieval/retriever.py` | Requested year / retrieval candidate sizing | Dùng target year semantic và giữ đủ kết quả list. |
| `tests/test_full_sweep_p1.py` | Regression tests | Legal aliases, generic/external/mixed boundary, intents, year, event, score context, result-notification grounding, and written-month date priority. |
| `tests/test_task_09.py` | Manifest-driven source fixture | Không phụ thuộc stale raw filename. |
| `tests/test_task_c.py` | Numeric semantics assertion | Kiểm số theo contract, không literal wording. |
| `tests/test_task_response_ui.py` | Verified tuition/school-info regressions | Kiểm tuition line không bị trộn với tổng chi phí và câu trả lời structured có evidence/source hợp lệ. |
| `reports/FULL_SWEEP_P1_FIX_REPORT.md` | Handoff report | Tổng hợp thay đổi, rerun, residuals và yêu cầu QA. |

Các thay đổi working-tree khác (ví dụ `data/raw/manifest.json`, `src/chatbot/evidence.py`, `src/chatbot/output_validator.py`, ingestion files và report cũ) không được quy là do task này. Riêng active Chroma được cập nhật từ verified processed JSON vì freshness audit xác nhận stale; không sửa canonical 500 Q&A hay RAW PDF.

## 15. 120-Failure Rerun

Sau các sửa đổi cuối cùng, toàn bộ 120 dòng ban đầu `result=FAIL` đã được chạy lại qua `ask_chatbot` với Ollama và collection Chroma đang cấu hình thật (`chroma_db/dhv_admissions_2026`, 310 records). Artifact mới nhất là V6; mỗi dòng giữ question/reference, answer, intent/entity/year, retrieval/evidence, validator, sources và trace. Bảng dưới đây chỉ tóm tắt runtime status, không phải QA factual pass.

| Original failure group | Original | Runtime `ok` | Runtime `no_data` | Runtime `out_of_scope` | Runtime `ollama_offline` |
|---|---:|---:|---:|---:|---:|
| `WRONG_ENTITY` | 45 | 27 | 2 | 16 | 0 |
| `WRONG_SCOPE` | 68 | 21 | 2 | 45 | 0 |
| `WRONG_INTENT` | 6 | 4 | 0 | 2 | 0 |
| `WRONG_YEAR` | 1 | 1 | 0 | 0 | 0 |
| **Total** | **120** | **53** | **4** | **63** | **0** |

- Artifact cuối: `reports/FULL_SWEEP_P1_120_LEAD_RERUN_20261009_V6.jsonl`, 120/120, Chroma count=310; elapsed khoảng 137 giây. V1–V5 được giữ nguyên làm lịch sử, V6 là lượt sau cùng.
- `ok` không đồng nghĩa QA đã chấm câu trả lời đúng; cần đối chiếu expected answer và evidence. Không có `ollama_offline` trong lượt này.
- Bốn `no_data` được giữ an toàn vì corpus hiện tại không chứng minh đủ fact: UQ0160 (quan hệ IATAI–ngành), UQ0236 (đối tác thực tập tại Hoa Kỳ), UQ0327 (sự kiện sáu doanh nghiệp), UQ0378 (nội dung dạy cụ thể của Marketing). Không dùng expected answer `source="Tự làm"` làm evidence.
- Các `out_of_scope` còn lại chủ yếu là event, career, lab/research, student-life hoặc school-info chi tiết chưa thuộc contract tuyển sinh. Hai event-date cases UQ0250/UQ0296 cũng được giữ ngoài lịch tuyển sinh thay vì map nhầm intent.
- Các admissions case cần QA ưu tiên trong V6: UQ0007, UQ0010, UQ0013, UQ0017, UQ0078, UQ0085, UQ0134, UQ0179, UQ0205, UQ0321, UQ0328 và UQ0339. Runtime có answer/source; QA vẫn phải xác nhận tính đầy đủ và đúng nghĩa.

## 16. External-School Regression

Real pipeline checks:

| Query | target/scope | Retrieval | Docs | Evidence | Status |
|---|---|---:|---:|---:|---|
| “Điểm chuẩn Bách Khoa?” / “diem chuan bach khoa?” | `OTHER_SCHOOL` / external | 0 | 0 | 0 | `out_of_scope` |
| “Điểm chuẩn Văn Hiến?”, “Học phí Hoa Sen?”, “Văn Lang có học bổng không?”, “Nguyễn Tất Thành có xét học bạ không?” | `OTHER_SCHOOL` / external | 0 | 0 | 0 | `out_of_scope` |
| “So sánh DHV và Văn Hiến” | `MIXED` | 0 | 0 | 0 | blocked safely |
| “Điểm chuẩn Hùng Vương?” | `AMBIGUOUS` | 0 | 0 | 0 | `clarification` |

## 17. Positive DHV Regression

| Query | target/scope | Intent/mode | Retrieval | Evidence | Outcome |
|---|---|---|---:|---:|---|
| “Điểm chuẩn DHV CNTT?” | `DHV` | score | 1 | 4 | `ok`; evidence-grounded values 15/18/600 |
| “Điểm chuẩn CNTT?” | `UNSPECIFIED` → DHV default | score | 1 | 4 | `ok`; default preserved |
| “Trường có những ngành nào?” | `UNSPECIFIED` → DHV default | list | 1 | 42 | `ok`; 20 majors |
| “Trường Đại học Hùng Vương TP. Hồ Chí Minh có bao nhiêu ngành?” | `DHV` | count | 1 | 67 | `ok`; count 20 |
| “DHV năm 2026 có những cách xét tuyển nào vậy ạ?” | DHV | `HOI_PHUONG_THUC_XET_TUYEN` / `LIST` | 1 | 15 | `ok`; list contains 5 methods |
| “Khi trúng tuyển thì trường sẽ thông báo vào đâu ạ?” (UQ0339) | `UNSPECIFIED` → DHV default | `HOI_DANG_KY_XET_TUYEN` | 1 | 117 | `ok`; answer cites invitation/Zalo, Ministry system, and DHV admissions website; QA checks completeness |
| “Tốt nghiệp THPT từ 2025 trở về trước có được xét tuyển năm 2026 không?” (UQ0007) | `UNSPECIFIED` → DHV default | `HOI_DANG_KY_XET_TUYEN`, year 2026 | 1 | 15 | `ok`; official source states THPT-graduation eligibility; QA confirms answer completeness |
| “Mốc 13/8 và mốc 21/8… có phải cùng một ý nghĩa không?” (UQ0085) | `UNSPECIFIED` → DHV default | `HOI_LICH_TUYEN_SINH`, year 2026 | 1 | 64 retrieved / evidence-prioritized | `ok`; 13/8 ưu đãi cao nhất; 21/8 hạn xác nhận hệ thống Bộ; both facts have DHV sources |
| “Giới thiệu về trường” | `UNSPECIFIED` → DHV default | `SCHOOL_INFO` | 1 | 8 | `ok`; verified source attached |
| “Điểm chuẩn Hùng Vương?” | ambiguous, not positive DHV | clarification | 0 | 0 | safe; not silently resolved |
| “Trường DHV có kết nối và giao lưu với các trường khác không ạ?” | `DHV` / `in_scope_dhv` | `SCHOOL_INFO` | 1 | 25 | `ok`; “các trường khác” là object, không thành `MIXED` |

## 18. COUNT/LIST Regression

- Deterministic count/list behavior and query modes were exercised in `tests/test_full_sweep_p1.py`, `tests/test_task_c.py`, and existing task/runtime suites.
- Live Chroma method-list check returned 5 methods; live major count returned 20; live major list returned 20 entries.
- Full pytest includes these regressions; no count/list-related failure was reported.

### Real multi-turn traces

| Turns | Outcome |
|---|---|
| `Điểm chuẩn CNTT?` → `Còn học phí?` | Turn 2 stays `HOI_HOC_PHI`, retrieves one canonical verified tuition record and answers `Học phí HKI (10 tín chỉ): 12.500.000 đồng`; no conflicting 14.25M total is emitted. |
| `Điểm chuẩn CNTT?` → `Học phí DHV hiện nay?` | Explicit DHV/generic-school request answers from tuition evidence without mentioning CNTT, despite prior major remaining in conversation state. |
| `Văn Hiến có xét học bạ không?` → `Còn DHV thì sao?` | Turn 1 `OTHER_SCHOOL`, retrieval/docs/evidence 0; turn 2 explicit DHV override, retrieval and verified DHV evidence allowed. |
| `Liệt kê các ngành DHV` → `Điểm sàn các ngành nêu trên?` | Turn 2 resolves `candidate_majors=20` and returns the verified threshold table for the prior list. |

## 19. Wrong-Year Regression

- Graduation 2025/before + admission 2026 → extracted `entities.year=2026`, registration intent; final trace retrieved 4 docs/evidence and returned an answer sourced from official tuyển sinh 2026.
- Multi-year tests for graduation 2024/2025 and admission 2026 pass semantic extraction.
- UQ0007 runtime status is now `ok`; QA should check that its answer explicitly resolves eligibility and that no historical graduation year fact was treated as the requested admission-data year.
- Chroma audit found no 2024 records in active collection; the separate 2024 raw tuition entry is unverified and excluded.

## 20. Tests

| Suite | Result | Notes |
|---|---|---|
| Targeted P1/Phase 2+4/scope/intent/year/Task C/F/09/UI suite | **186 passed, 250 subtests passed** | Includes `test_priority_1_2_fix.py`, `test_full_sweep_p1.py`, Phase 2/4, intent, Task C/F/09 and UI contract. |
| Full pytest | **265 passed, 4 skipped, 3 failed, 283 subtests passed** | Completed in 77.62s. Three failures below remain; no P1/runtime targeted regression failed. |
| `tests/test_ingestion.py::...test_build_persists_chroma_and_smoke_query_keeps_source_metadata` | Failed | Chroma upsert received duplicate deterministic IDs for two temporary test documents; outside the changed runtime files, but a real ingestion-suite failure requiring follow-up. |
| `tests/test_task_m.py::TaskMRawDataTests::test_raw_pdfs_have_official_urls_and_no_form_submission_data` | Failed | A URL embedded in manifest-verified `Thong_Tin_Truong.pdf` fails the official-URL predicate; raw PDF/manifest left untouched. |
| `tests/test_task_processed_md_to_json_migration.py::ProcessedJSONMigrationTests::test_loader_reads_canonical_json_only` | Failed | Test hard-codes `skipped_unverified=2`; current manifest/loader produce 1. Manifest was not changed here. |
| `tests/test_task_response_ui.py` scholarship call-count test | **PASS** | The verified structured response contract passes in final targeted/full runs. |

## 21. Remaining Issues

1. Four `no_data` residuals: UQ0160, UQ0236, UQ0327, UQ0378; keep them unasserted until verified corpus data and scope support those facts.
2. Ollama was reachable throughout V6; QA must fact-check all 53 runtime `ok` outputs against their evidence, not accept status alone.
3. Sixty-three rows remain `out_of_scope`, mostly event/career/lab/research/student-life or detailed school-info outside current admissions contract. QA must confirm no approved admissions query was blocked.
4. The QA agent’s independent FAIL used a prior 270-record Chroma snapshot and preceded final V6. It remains valid for that snapshot; QA must rerun final code on the current 310-record active collection.
5. Full pytest retains three failures: duplicate deterministic IDs in ingestion test; official-URL predicate on untouched PDF; and stale skipped-unverified count expectation. They are disclosed and not suppressed. No 500-Q&A expectation was altered.

## 22. Ollama Status

- Ollama was available during the 120-row rerun; `qwen2.5:3b` and `nomic-embed-text` were present/loaded.
- Input JSONL contained 500 rows (`FAIL=120`, `BLOCKED=380`). The first exploratory process was stopped after 10 rows on detecting the mixed file; the completed rerun filtered `result=FAIL`, asserted exactly 120, and excluded all blocked rows.
- All 120 original FAIL rows were rerun with real `ask_chatbot`, active local Chroma retrieval, evidence selection and output validation; this was not replaced by fake-retriever E2E.
- Final V6 used the configured active collection at `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db`, collection `dhv_admissions_2026`, count=310. Independent QA observed 270 rows in an earlier snapshot; the mismatch is disclosed. V6 did not rebuild Chroma.
- The 380 previously BLOCKED rows were not rerun as a full 500-question QA sweep in this Lead Coder task. QA may rerun 500/500 now that Ollama is available. No `FULL_QUESTION_SWEEP_PASS` is claimed.

### Chroma freshness and post-build audit

- Before: active `chroma_db/dhv_admissions_2026` = **270 records**, 2026 verified DHV. This was stale relative to the freshly processed data.
- Build: canonical `data/processed` → verified/year=2026/DHV/source-url loader → splitter → Ollama embeddings (`nomic-embed-text`) → candidate Chroma. No raw-PDF ingestion. Candidate was audited, then activated locally; prior DB retained in `chroma_backup_20261009`.
- After: active collection = **310 records**; every row year `2026`, status and verification_status `verified`, school_code `DHV`, source_url non-empty and hosted on `dhv.edu.vn` / subdomain; zero invalid/missing-source rows. Six document identities. No 2024 or unverified record.
- Category counts: `cach_tinh_diem=3`, `diem_trung_tuyen=75`, `ho_so=42`, `hoc_bong=37`, `hoc_phi=1`, `lich_tuyen_sinh=2`, `nganh_dao_tao=42`, `nguong_dau_vao=40`, `phuong_thuc_xet_tuyen=15`, `thong_tin_truong=25`, `xet_tuyen_bo_sung=28`.
- Command shape used: `python -m src.ingestion.build_vector_db --data-dir data/processed --persist-dir <candidate> --collection dhv_admissions_2026 --year 2026 --embedding-backend ollama --embedding-model nomic-embed-text --ollama-base-url http://localhost:11434`.

## 23. Acceptance Criteria

| Criterion | Status |
|---|---|
| Full DHV legal-name variants resolve to DHV | PASS |
| Generic “trường/nhà trường” does not become external | PASS |
| DHV subject + “các trường khác” object is not falsely MIXED | PASS |
| True external schools retrieval/evidence = 0 | PASS |
| True DHV + external comparison remains blocked | PASS |
| Bare “Hùng Vương” remains ambiguous, retrieval = 0 | PASS |
| UQ0013 method question is not OUT_OF_SCOPE and routes LIST | PASS |
| Explicit score/method context avoids wrong clarification | PASS for targeted route assertions |
| UQ0085 two admission dates use the right semantics from real evidence | PASS; direct trace `ok`, official sources, evidence-prioritized |
| UQ0007 target admission year = 2026 and runtime no longer chooses graduation year | PASS runtime; QA to adjudicate factual completeness |
| All 45 WRONG_ENTITY rows rerun | PASS execution; 16 out-of-contract rows and missing-relation no-data rows documented for QA |
| All 6 WRONG_INTENT rows rerun | PASS execution; 4 admissions rows `ok`, 2 event-date rows remain safely out of scope |
| WRONG_YEAR row rerun | PASS execution; target year 2026, runtime status `ok`; QA to adjudicate answer |
| Admissions WRONG_SCOPE rows rerun | PASS; approved admissions cases now resolve, including UQ0085; broader domains stay outside pending contract |
| COUNT/LIST regressions | PASS |
| Real multi-turn tuition, school override and list coreference | PASS in live trace; QA to independently confirm answer/evidence |
| No-data, external-school and wrong-year safety regressions | PASS as safety; residual no-data listed above |
| No canonical 500 Q&A modified | PASS |
| No question-ID-specific answer/scope rule added | PASS |
| Full pytest result documented | PASS; final run 265 passed, 4 skipped, 3 failures, each named in this report |
| All deterministic P1 code defects in approved admissions scope addressed | PASS for targeted rerun; 4 no-data evidence/contract gaps and 63 out-of-scope rows are not declared resolved or in-scope |

## 24. Handoff To QA

QA & Security should:

1. Independently rerun the final 120-row artifact `reports/FULL_SWEEP_P1_120_LEAD_RERUN_20261009_V6.jsonl` on the current configured 310-record active collection; adjudicate answer/evidence pairs, not runtime `status=ok` alone.
2. Inspect no-data IDs `UQ0160, UQ0236, UQ0327, UQ0378`; decide whether each needs approved domain/evidence or correctly stays no-data.
3. Confirm all 63 remaining `out_of_scope` rows are outside current contract or raise a specific contract decision; prioritize school-info/partnership rows `UQ0108, UQ0150, UQ0209`, and verify no approved admissions question is blocked.
4. Rerun and fact-check UQ0007, UQ0010, UQ0013, UQ0017, UQ0078, UQ0085, UQ0134, UQ0179, UQ0205, UQ0321, UQ0328 and UQ0339, including numeric/date semantics and source provenance.
5. Re-run external/mixed/ambiguous school, generic-school false-positive, positive-DHV, count/list, Phase 2/4, multi-year, tuition-follow-up, explicit school override and unsupported-recommendation cases against the active 310-row collection.
6. Review the three full-pytest failures: duplicate deterministic Chroma IDs in ingestion; official-URL predicate for manifest-verified `Thong_Tin_Truong.pdf`; and stale `skipped_unverified` assertion. Scholarship call-count test passes final runs.
7. Ollama and `qwen2.5:3b` / `nomic-embed-text` were available for this run. QA should still perform its independent 500/500 canonical sweep and factual grounding review before any project-level pass claim.

**Verdict: READY_FOR_QA** — deterministic P1 changes, targeted regression suite, final 120-row real-runtime rerun, and external-school/multi-turn checks are ready for independent QA/Security review. This is not `FULL_QUESTION_SWEEP_PASS`; four no-data evidence gaps, 63 out-of-contract/out-of-scope rows, three full-suite failures and the earlier 270-vs-310 QA snapshot mismatch are disclosed. QA must rerun final code on the active collection. No deployment was performed.
