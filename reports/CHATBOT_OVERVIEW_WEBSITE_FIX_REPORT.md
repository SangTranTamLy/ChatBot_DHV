# CHATBOT OVERVIEW + WEBSITE COUNT FIX REPORT

## 1. Scope

Đã xử lý hai lỗi runtime được nêu trong trao đổi:

- Câu hỏi tổng quan `thông tin trường DHV` có thể lấy nội dung học phí/học bổng không liên quan hoặc trả `no_data` dù corpus có đoạn giới thiệu.
- Câu hỏi đếm website của DHV bị nhận diện như yêu cầu website đơn, nên chỉ trả một địa chỉ.

Không sửa prompt, dataset, RAW PDF, embedding, model hay Chroma; không deploy. Bước LLM tiền xử lý/tách câu hỏi nhiều ý trong kế hoạch tổng thể chưa nằm trong phần sửa này.

## 2. Root Cause Verification

### Tổng quan trường

Runtime thật truy xuất 25 tài liệu và chọn 25 evidence. Tuy nhiên, context có giới hạn ký tự; các chunk thông tin chi tiết dài (ví dụ học bổng) đứng trước đoạn `TỔNG QUAN VỀ TRƯỜNG`, khiến đoạn giới thiệu bị cắt khỏi context. Nhánh tổng quan khi đó không có đúng evidence để trả lời, hoặc câu trả lời tổng hợp rộng có nguy cơ lạc chủ đề.

Processed corpus và Chroma đang hoạt động có đoạn giới thiệu trường đã verified. Root cause là thứ tự đưa evidence vào context, không phải thiếu dữ liệu hay prompt cũ.

### Đếm website

Nhận diện website trước đây phụ thuộc marker chuỗi có khoảng trắng; dấu câu ngay sau `website` có thể khiến marker không khớp. Query analysis cũng chưa phân biệt rõ câu hỏi đếm website với câu hỏi xin một địa chỉ. Nhánh trả lời website vì vậy có thể chỉ chọn website trường chính.

## 3. Implementation

- Nhận diện `website`, `web`, `trang web` theo ranh giới từ, không phụ thuộc khoảng trắng trước dấu câu.
- Nhận diện semantic yêu cầu đếm (`bao nhiêu`, `mấy`, `số lượng`) cho website/cổng thông tin; đặt `query_mode=COUNT` và `requested_information=official_website_count`.
- Với câu tổng quan trường, ưu tiên chunk giới thiệu trước khi dựng context, nhưng chỉ khi metadata khớp category `thong_tin_truong`, `school_code=DHV`, trạng thái `verified` và năm mục tiêu.
- Trả lời tổng quan bằng đoạn evidence giới thiệu đã xác minh và giới hạn nguồn trích dẫn về đúng nguồn của đoạn đó. Nếu không có đoạn giới thiệu phù hợp, dừng ở `no_data`, không gọi LLM để lấp chỗ trống bằng evidence học bổng/học phí.
- Đếm website từ URL của các tài liệu đã qua selection/evidence gate; chỉ nhận HTTPS thuộc `dhv.edu.vn` hoặc subdomain của nó, khử trùng theo hostname và ưu tiên URL gốc. Không tạo URL mới.

## 4. Files Changed

| File | Khu vực | Lý do |
|---|---|---|
| `src/chatbot/query_analysis.py` | Website request/count detection, query mode | Bắt dấu câu và phân biệt đếm website với hỏi một website cụ thể. |
| `src/chatbot/scope_guard.py` | Phân loại school subject/object | Phân biệt trường ngoài được hỏi như entity ngang hàng với trường ngoài chỉ là object của quan hệ DHV. |
| `src/chatbot/rag_chain.py` | Verified website aggregation; overview evidence ordering/answer boundary | Đếm trên nguồn đã xác minh; tránh context clipping làm mất đoạn tổng quan và tránh trả lời lệch chủ đề. |
| `src/chatbot/output_validator.py` | Evidence year contract | Kiểm tra năm theo cấu hình runtime thay vì cố định 2026; caller không truyền năm vẫn dùng mặc định cấu hình. |
| `tests/test_task_09.py` | Website count và school overview regression | Bao gồm punctuation, URL dedup, nguồn đúng và chunk không liên quan đủ dài để lấp context. |
| `tests/test_priority_1_2_fix.py` | Mixed school và subject/object scope regression | Chứng minh câu hỏi fact hai trường bị chặn, nhưng object quan hệ DHV không bị chặn nhầm. |
| `reports/CHATBOT_OVERVIEW_WEBSITE_FIX_REPORT.md` | Báo cáo/handoff | Lưu kết quả triển khai và các giới hạn còn lại. |

## 5. Runtime Traces

Chạy runtime local thật với Ollama và Chroma đang cấu hình; không dùng fake retriever cho hai trace dưới đây.

| Câu hỏi | Intent | Retrieval | Retrieved docs | Evidence | Status | Kết quả |
|---|---|---:|---:|---:|---|---|
| `Thông tin trường DHV` | `SCHOOL_INFO` | 1 | 25 | 25 | `ok` | Nhánh `verified_school_overview`, trace xác nhận overview evidence được ưu tiên; trả 3 ý giới thiệu từ nguồn `https://dhv.edu.vn/`, không đưa học bổng/học phí vào câu trả lời. Validator `ok`. |
| `Trường DHV có bao nhiêu website?` | `HOI_CO_SO_LIEN_HE` | 1 | 25 | 25 | `ok` | Trả 2 hostname khác nhau, liệt kê `https://dhv.edu.vn/` và `https://tuyensinh.dhv.edu.vn/`; cả hai được đính kèm làm nguồn. |

Chroma không được rebuild trong task này.

## 6. Tests

| Suite | Kết quả |
|---|---|
| Suite targeted mới nhất: Task 09, Priority 1+2, intent classifier, full-sweep P1, Task K/L | PASS — 141 tests, 129 subtests |
| Full `pytest -q` với `TEMP`/`TMP` trỏ vào `.test_tmp` trong workspace | 275 passed, 4 skipped, 288 subtests passed, 3 failed |

Ba lỗi full-suite còn lại:

1. `tests/test_ingestion.py::IngestionTests::test_build_persists_chroma_and_smoke_query_keeps_source_metadata` — Chroma từ chối ID trùng trong test ingestion.
2. `tests/test_task_m.py::TaskMRawDataTests::test_raw_pdfs_have_official_urls_and_no_form_submission_data` — predicate URL official không chấp nhận một URL trích từ PDF RAW.
3. `tests/test_task_processed_md_to_json_migration.py::ProcessedJSONMigrationTests::test_loader_reads_canonical_json_only` — kỳ vọng `skipped_unverified=2`, kết quả thực tế là `1`.

Ba lỗi trên không thuộc các file được sửa trong task này; không chỉnh ingestion, RAW PDF, migration hay test expectation để che lỗi.

## 7. Acceptance Criteria

- [x] Website có dấu câu vẫn được nhận diện.
- [x] Câu hỏi “bao nhiêu website” thành COUNT riêng.
- [x] Câu hỏi tổng quan ưu tiên đúng đoạn DHV verified trước khi giới hạn context.
- [x] Chunk học bổng dài không thể che đoạn giới thiệu trong test tái hiện.
- [x] Câu trả lời tổng quan không trích nguồn của chunk học bổng.
- [x] Runtime thật trả lời tổng quan với nguồn official.
- [x] Runtime thật đếm và liệt kê hai website từ nguồn verified.
- [x] Không hard-code câu hỏi hay câu trả lời thực tế.
- [x] Không rebuild Chroma, không deploy.
- [ ] QA độc lập xác nhận câu trả lời và các nguồn trên snapshot hiện tại.
- [ ] Ba lỗi full-suite ngoài phạm vi được xử lý trong task riêng phù hợp.

## 8. Remaining Risks

- Bộ đếm website chỉ phản ánh các hostname DHV HTTPS có trong những tài liệu verified được query chọn; đây là “trong các nguồn DHV đã xác minh”, không khẳng định là kiểm kê internet đầy đủ.
- Các lỗi ingestion/RAW/migration liệt kê ở trên vẫn tồn tại.
- Kế hoạch lớn hơn về LLM bóc tách nhiều ý trước RAG chưa được triển khai trong task sửa hai lỗi này; cần theo dõi như hạng mục riêng, có safety gates và QA riêng.

## 9. Handoff to QA & Security

Xin QA chạy độc lập trên working tree/collection hiện tại:

1. `Thông tin trường DHV` — xác nhận chỉ dùng đoạn tổng quan, không lẫn số học phí/học bổng và nguồn là trang official tương ứng.
2. `Trường DHV có bao nhiêu website?` — xác nhận count, danh sách và provenance cho từng URL.
3. Biến thể dấu câu/không dấu: `DHV có mấy trang web?`, `truong DHV co bao nhieu website?`.
4. Hồi quy hỏi website cụ thể: website trường, cổng tuyển sinh và website của khoa/viện; xác nhận không trả nhầm URL.
5. Kiểm tra lại câu tổng quan khi intro evidence thiếu, sai năm, sai trường hoặc chưa verified; kết quả phải là `no_data`, không fallback sang chunk chi tiết.
6. Xác nhận ba lỗi full-suite còn lại được phân loại ngoài phạm vi task, không tính là lỗi do thay đổi này.

Verdict của Lead Coder: `READY_FOR_QA`. Đây không phải kết luận QA cuối cùng.

## 10. Security Review Follow-up

Security review phát hiện thêm bốn điểm cần khóa trước handoff. Đã kiểm tra code và thêm regression; các thay đổi này không sửa dữ liệu, không rebuild Chroma và không deploy.

| Phát hiện | Root cause xác nhận | Sửa đổi |
|---|---|---|
| Overview trong câu hỏi nhiều ý có thể đi qua nhánh sinh câu trả lời rộng | Guard intro-only/fail-closed mới áp dụng đầy đủ ở route đơn; subplan `SCHOOL_INFO` chưa dùng cùng evidence boundary | Multi-issue route chỉ chấp nhận câu trả lời overview từ intro evidence đúng DHV/năm/trạng thái; nếu thiếu thì issue đó là `no_data`, không nhờ LLM điền từ chunk chi tiết. |
| Website cụ thể thiếu evidence có thể nhận URL DHV bất kỳ | Nhánh website từng có fallback từ URL được yêu cầu sang mọi nguồn official đã chọn | Fallback tổng quát bị bỏ; khi URL yêu cầu không có trong verified evidence, trả `no_data`, không nguồn. Riêng cổng tuyển sinh chỉ chấp nhận host cổng hoặc landing path tuyển sinh đã xác định trên host chính. |
| Câu hỏi fact ngang hàng về DHV và trường khác có thể bị coi là DHV | School detection trước đó không phân biệt entity đồng cấp với trường ngoài là object trong câu quan hệ của DHV | Hai trường cùng là subject của câu fact/comparison được phân loại `MIXED`; trường ngoài trong quan hệ hợp tác/kết nối của DHV không tự biến thành `MIXED`. |
| Một số overview/website/validator dùng năm toàn cục | Target year của runtime chưa được truyền xuyên đến các nhánh trả lời và validator | Truyền `settings_obj.target_year` đến website label, overview, generation validation và các nhánh deterministic; validator giữ mặc định cấu hình cho caller cũ. |

### Runtime trace cập nhật

Chạy với Ollama local (`qwen2.5:3b`, `nomic-embed-text`) và collection active `chroma_db/dhv_admissions_2026`.

| Câu hỏi | Target/scope | Retrieval | Docs | Evidence | Status |
|---|---|---:|---:|---:|---|
| `Thông tin trường DHV` | `DHV` / `in_scope_dhv` | 1 | 25 | 25 | `ok`; deterministic overview, validator `ok`, nguồn `https://dhv.edu.vn/`. |
| `Trường DHV có bao nhiêu website?` | `DHV` / `in_scope_dhv` | 1 | 25 | 25 | `ok`; liệt kê 2 host và source đã xác minh, nhãn cổng tuyển sinh dùng năm runtime 2026. |
| `DHV và Đại học FPT có bao nhiêu website?` | `MIXED` / `mixed_school` | 0 | 0 | 0 | `out_of_scope`; không gọi retriever. |

Một truy vấn thử “Thông tin trường DHV và học bổng DHV” được classifier giữ thành một intent `SCHOOL_INFO`, không kích hoạt multi-issue plan; không tính nó là trace xác nhận nhánh nhiều ý. Nhánh nhiều ý được kiểm bằng regression test chuyên biệt về thiếu intro evidence.

### Collection audit

Không rebuild. Collection đang cấu hình là `dhv_admissions_2026`, có 310 records; cả 310 đều `year=2026`, `status=verified`, `school_code=DHV` và có `source_url`. Categories hiện có: `diem_trung_tuyen`, `hoc_bong`, `ho_so`, `hoc_phi`, `lich_tuyen_sinh`, `phuong_thuc_xet_tuyen`, `nganh_dao_tao`, `nguong_dau_vao`, `thong_tin_truong`, `cach_tinh_diem`, `xet_tuyen_bo_sung`.

### Regression và giới hạn

- Các targeted suite liên quan: `141 passed`, `129 subtests passed`.
- Full suite sau khi chuyển temp path vào workspace: `275 passed`, `4 skipped`, `288 subtests passed`, `3 failed`.
- Ba failure còn lại không thuộc thay đổi này: Chroma ingestion test tạo duplicate IDs; predicate official URL của test RAW PDF; migration test kỳ vọng `skipped_unverified=2` nhưng loader trả `1`. Không sửa chúng trong follow-up này.
- Lần full-suite chạy đầu với Windows temp mặc định gặp thêm lỗi ACL; khi chuyển `TEMP`/`TMP` vào workspace thì các lỗi ACL đó biến mất. Kết quả ba failure trên là lần rerun dùng làm kết quả cuối.
- Không sửa prompt để thay cho scope/evidence guard. Thiết kế tổng thể “LLM phân tích/tách mọi câu hỏi trước RAG” vẫn là hạng mục riêng, chưa được triển khai ở follow-up này.

### QA/Security cần rerun

1. Câu nhiều ý có SCHOOL_INFO: một case có intro evidence và một case chỉ có học phí/học bổng/event detail; xác nhận overview issue không lấy nhầm chunk hoặc dùng LLM bù.
2. Website cụ thể có evidence chính xác, chỉ có URL khác, và không có URL yêu cầu; URL khác không được dùng thay thế.
3. `DHV và Đại học FPT có bao nhiêu website?` phải `MIXED`, retrieval/docs/evidence đều bằng 0.
4. `DHV có hợp tác với Đại học FPT không?` và `DHV có kết nối/giao lưu với các trường khác không?` không bị chặn sai chỉ vì trường ngoài là object quan hệ.
5. Năm cấu hình khác 2026 trong website count/overview/validator phải nhất quán; production evidence vẫn phải tuân theo target year cấu hình.
6. Chạy lại external-school, website count, overview và regression suite trên snapshot Chroma hiện tại.

Verdict sau follow-up của Lead Coder: `READY_FOR_QA`; chờ QA/Security độc lập xác nhận. Không phải kết luận QA cuối cùng.

## 11. Security Re-review F-01–F-03 (2026-10-09)

Đã xử lý ba finding mới trong báo cáo Security. Chỉ sửa routing multi-intent, fail-closed overview, validator nhận diện tổ chức không dấu và trace tổng hợp. Không sửa dataset, không rebuild Chroma, không deploy.

### Root cause và thay đổi

| Finding | Root cause xác nhận | Thay đổi |
|---|---|---|
| F-01 — multi-intent overview | Nhận diện `SCHOOL_INFO` đơn có thể kết thúc phân loại trước khi gom các ý khác; overview subplan dùng câu gốc chứa detail markers nên ranh giới overview bị bỏ qua. | Phân loại nhiều ý trước khi trả `SCHOOL_INFO`; website/cổng tuyển sinh được tạo thành ý riêng. Overview subplan kiểm tra evidence bằng câu con đã cô lập; thiếu intro evidence thì trả `no_data` và không gọi LLM cho ý overview. |
| F-02 — bypass tên trường không dấu | Regex chỉ nhận dạng cụm có dấu; kiểm tra tên trường trên câu trả lời gốc nên `Dai hoc FPT` không bị ranh giới tổ chức bắt đúng. Token overlap cũng không đủ làm bằng chứng cho tên đối tác. | Chuẩn hóa dấu trước khi nhận diện tổ chức; so tên tổ chức đã chuẩn hóa như một cụm đầy đủ với evidence. Regression xác nhận cả `Đại học FPT` và `Dai hoc FPT` đều bị từ chối khi evidence chỉ nói chung về hợp tác, không nêu FPT. |
| F-03 — trace đếm thiếu | Trace gốc của multi-intent không cộng bộ đếm retrieval/docs/evidence từ từng subplan. | Root trace cộng các số liệu từng subplan; trace `multi_issue` lưu cả bộ đếm riêng từng subplan để đối chiếu. |

### Runtime traces và kiểm thử

Chạy runtime thật với Ollama (`qwen2.5:3b`, `nomic-embed-text`) và Chroma active `dhv_admissions_2026`; collection không rebuild.

| Query | Subplans / target | Retrieval | Docs | Evidence | Status / kết quả |
|---|---|---:|---:|---:|---|
| `Thông tin trường DHV và học bổng DHV` | `HOI_HOC_BONG`, `SCHOOL_INFO` / `DHV` | 2 | 29 | 14 | `ok`; trả cả hai phần. |
| `Thông tin trường DHV và website trường?` | `HOI_CO_SO_LIEN_HE`, `SCHOOL_INFO` / `DHV` | 2 | 50 | 18 | `ok`; trả cả website và overview, nguồn website `https://dhv.edu.vn/`. |
| `Giới thiệu về trường DHV và cổng tuyển sinh?` | `HOI_CO_SO_LIEN_HE`, `SCHOOL_INFO` / `DHV` | 2 | 50 | 18 | `ok`; trả cả overview và cổng `https://tuyensinh.dhv.edu.vn/`. |
| `DHV có hợp tác với Đại học FPT không?` | `SCHOOL_INFO` / `DHV` | 1 | 25 | 25 | `no_data`; validator/model fallback, `sources=[]`, không khẳng định quan hệ với FPT. |

Trace multi-intent hiện phản ánh đúng số retrieval ở root (2 thay vì 0) và cộng docs/evidence từ các subplan. Regression tổng hợp tái hiện đúng chuỗi Security `Thong tin truong DHV va su kien, website, hoc bong`; khi overview không có intro evidence phù hợp, issue overview fail-closed và không gọi LLM để bù. Validator có test synthetic riêng cho hai dạng tên đối tác có dấu/không dấu.

| Suite | Kết quả |
|---|---|
| Targeted: Task 09, Priority 1+2, intent, full-sweep P1, Task K/L | 144 passed, 136 subtests passed |
| Full pytest (`TEMP`/`TMP` dùng `.test_tmp`) | 278 passed, 4 skipped, 295 subtests passed, 3 failed |

Ba lỗi full-suite vẫn nằm ngoài phạm vi thay đổi Security này:

1. `tests/test_ingestion.py::IngestionTests::test_build_persists_chroma_and_smoke_query_keeps_source_metadata` — Chroma từ chối duplicate IDs do test ingestion.
2. `tests/test_task_m.py::TaskMRawDataTests::test_raw_pdfs_have_official_urls_and_no_form_submission_data` — predicate URL official không chấp nhận URL trích từ `Thong_Tin_Truong.pdf`.
3. `tests/test_task_processed_md_to_json_migration.py::ProcessedJSONMigrationTests::test_loader_reads_canonical_json_only` — test kỳ vọng `skipped_unverified=2`, thực tế `1`.

### Files thay đổi cho F-01–F-03

| File | Khu vực | Lý do |
|---|---|---|
| `src/chatbot/query_analysis.py` | Phân loại SCHOOL_INFO/multi-intent, nhận diện cổng tuyển sinh | Không để intent overview đơn nuốt các ý đồng thời; nhận dạng cụm cổng tuyển sinh có dấu câu. |
| `src/chatbot/rag_chain.py` | Multi-issue subplans, overview boundary, root trace aggregation | Tách câu con cho gate overview, fail-closed khi thiếu intro evidence, cộng số liệu subplan. |
| `src/chatbot/output_validator.py` | Nhận diện institution trong answer/evidence | Chặn bypass tổ chức không dấu và yêu cầu cụm tên có trong evidence. |
| `tests/test_task_09.py` | Regression multi-intent, missing overview evidence và trace | Bắt ba câu tự nhiên, đúng repro Security và invariant không gọi LLM khi thiếu evidence overview. |
| `tests/test_priority_1_2_fix.py` | Validator accented/unaccented partner | Bắt F-02 cho cả câu trả lời có dấu và không dấu. |

### Handoff / verdict

QA và Security cần rerun: (1) exact query multi-intent của F-01 có intro evidence và trường hợp thiếu intro evidence; xác nhận không LLM fallback cho overview; (2) ba biến thể overview + học bổng/website/cổng tuyển sinh, xác nhận đủ từng ý; (3) câu trả lời nêu `Đại học FPT` có dấu và `Dai hoc FPT` không dấu khi evidence không nêu quan hệ/đối tác; (4) root trace phải bằng tổng retrieval/docs/evidence của subplans; (5) external/mixed/ambiguous và website/year gates hồi quy.

Verdict của Lead Coder: `READY_FOR_QA`. Đây không phải kết luận QA/Security cuối. Ollama đã khả dụng trong lần runtime local này; QA cần xác nhận độc lập trên môi trường/snapshot của họ. Không deploy.
