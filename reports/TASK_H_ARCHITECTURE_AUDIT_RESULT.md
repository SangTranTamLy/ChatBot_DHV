# TASK H — Architecture Audit Result

Ngày audit: 2026-09-15  
Repository: `ChatBot_DHV`  
Phạm vi: chỉ audit kiến trúc và reproduce theo `01_TASK_H_AUDIT_ARCHITECTURE.md`; không sửa RAW, processed hoặc Chroma.

## 1. Kết luận

Kiến trúc hiện tại đã có các mảnh nền tảng đúng hướng: phân tích câu hỏi, router metadata, state giới hạn, truy xuất Chroma, evidence bundle, deterministic catalog/score helpers, validator và ChatService tương thích. Tuy nhiên pipeline chưa đạt target trong master plan.

**Kết quả TASK H: FAIL ở mức Definition of Done.** Đây là kết luận audit, không phải kết luận rằng regression hiện tại hỏng. Targeted tests và full regression đều pass, nhưng các invariant kiến trúc vẫn còn vi phạm:

- greeting/identity/scope chưa là các nhánh deterministic riêng; greeting và identity bị phân loại thành `OUT_OF_SCOPE`;
- câu “điểm xét tuyển học bạ ngành Luật bao nhiêu?” bị route sang `cach_tinh_diem`, thiếu `score_type`, và một câu trả lời số sai vẫn lọt validator trong probe;
- Evidence Selection chưa phải một stage độc lập theo intent/entity/score type; context đưa cho LLM còn rộng;
- chưa có decomposition/subplans cho multi-issue;
- loader/evidence/retriever chưa enforce allowlist host `dhv.edu.vn`/subdomain;
- UI vẫn render source URL/card, trái với target master plan.

## 2. Phương pháp và phạm vi đã kiểm tra

Đã đọc:

- `DHV_AGENT_MASTER_PLAN_UPDATED/00_MASTER_PLAN.md`;
- `DHV_AGENT_MASTER_PLAN_UPDATED/01_TASK_H_AUDIT_ARCHITECTURE.md`;
- `DHV_AGENT_MASTER_PLAN_UPDATED/reference_images/README.md`;
- README, requirements, `.env.example`, app và toàn bộ `src/` liên quan;
- toàn bộ tests hiện có và golden questions;
- toàn bộ 62 trang `Tong_quan_xay_dung_chatbot_AI.pdf`.

Các phần phương pháp trong PDF được dùng để đối chiếu: layered architecture, RAG metadata/chunking, router và trust boundary, Evidence Selection, output validation, evaluation tách retrieval/generation, allowlist nguồn chính thức, PII/safety, versioning và regression.

**Không có file RAW, processed, Chroma hoặc dữ liệu nào được tạo/sửa trong task này.** Worktree đã dirty từ trước; các thay đổi có sẵn của người dùng được giữ nguyên.

## 3. Kiến trúc hiện tại

```text
Streamlit app.py
  -> src.chatbot.chat_service.ask_chatbot
       -> src.chatbot.rag_chain.ask_chatbot
            -> query_analysis.analyze_question / route_question
            -> scope_guard.is_in_scope
            -> retriever.retrieve_with_audit hoặc adapter.retrieve
            -> select_candidate_documents
            -> evidence.build_evidence
            -> enrich_analysis_from_evidence
            -> deterministic_score_comparisons
            -> catalog/website deterministic answers hoặc rag_prompt
            -> local_llm.OllamaLLM
            -> output_validator.validate_model_answer
```

Luồng dữ liệu hiện tại:

```text
PDF RAW -> prepare_processed_from_raw -> loader -> splitter
        -> embeddings -> Chroma collection dhv_admissions_2026
```

| Thành phần | Hiện trạng | Đối chiếu target |
|---|---|---|
| Normalizer/state | Có trong `query_analysis.py`; state có year/major/program/method/score/interest và turn count | Đạt một phần; chưa có audience/question type/subplans |
| Intent/router | Rule + trained classifier; `QueryPlan` chỉ có một intent/category/filter | Thiếu system intents và multi-issue decomposition |
| Scope | `scope_guard.py` và guard trong `rag_chain.py` | Có chặn out-of-scope, nhưng duplicate logic và không có response branch cho greeting/identity/scope |
| Retrieval | Chroma vector search, sau đó rank keyword/vector trong memory | Chưa là BM25+dense+RRF; candidate scan O(N); chưa có version manifest |
| Evidence | `EvidenceBundle`, structured score facts và relations | Có bundle nhưng chưa có Evidence Selection độc lập, chưa enforce official host |
| Deterministic logic | List/count catalog và score comparison đã có trong `rag_chain.py`/`query_analysis.py` | Đạt ở các path đang test; chưa bao phủ multi-issue và score-type inference |
| LLM | Một prompt RAG, Ollama `qwen2.5:3b`, temperature 0 | Chưa có Answer Planner/schema; context còn rộng |
| Validation | Grounding/relevance/entity/score/date/admission checks | Coverage còn phụ thuộc entity extraction; numeric overlap quá yếu |
| UI | `app.py` render title + URL dưới câu trả lời | Vi phạm invariant UI không source cards/URLs |
| Service boundary | `ChatService` là wrapper mỏng quanh `rag_chain.ask_chatbot`; app import function trực tiếp | Tương thích runtime, nhưng ownership orchestration chưa rõ |

## 4. Reproduce các case bắt buộc

| Case | Current | Expected | Kết quả |
|---|---|---|---|
| `CNTT có những chương trình gì?` | `DANH_SACH_CHUONG_TRINH`, category `nganh_dao_tao`; deterministic list 5 chương trình; 0 LLM call | List đủ, count/list bằng Python, không hard-code riêng CNTT | PASS |
| `CNTT có bao nhiêu chương trình?` | Trả count 5 bằng deterministic path; 0 LLM call | Count từ evidence/catalog, không để LLM đếm | PASS |
| `điểm xét tuyển học bạ ngành Luật bao nhiêu?` | `HOI_CACH_TINH_DIEM`; route `cach_tinh_diem`; `score_type=None`; không lấy được Law threshold/admission evidence | Phân biệt đúng application/admission score, method `hoc_ba`, major/entity và chỉ trả khi evidence đúng | FAIL |
| Law probe với LLM trả `...ngành Luật có ngưỡng 18 điểm` | `status=ok`, câu trả lời số sai được chấp nhận trong test double probe | Phải abstain/fallback khi không có mapping score type + major phù hợp | FAIL |
| `Tôi 19 điểm thích edit video nên chọn ngành nào?` | `TU_VAN_CHON_NGANH`; lấy 3 chunk `nganh_dao_tao` + 1 chunk `nguong_dau_vao`; không có candidate-specific score comparison; context còn broad | Tách điểm/sở thích, chọn evidence ứng viên phù hợp, score logic deterministic, LLM chỉ diễn đạt bounded recommendation | FAIL một phần |
| `Xin chào` | `OUT_OF_SCOPE`, không retrieval/LLM | Greeting deterministic, không RAG | FAIL về intent/response contract |
| `Bạn là ai?` | `OUT_OF_SCOPE`, không retrieval/LLM | Identity deterministic, không RAG, không tự nhận official DHV chatbot | FAIL về intent/response contract |
| `Bạn hỗ trợ được gì?` | Trained classifier ra `HOI_HO_SO` rồi bị scope gate chặn thành `out_of_scope` | Scope deterministic, trả capability contract rõ ràng, không RAG | FAIL |
| `Thời tiết hôm nay?` | `OUT_OF_SCOPE`, không retrieval/LLM | Out-of-scope deterministic | PASS về chặn, thiếu kiến trúc branch riêng |
| `CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?` | Chỉ nhận `DANH_SACH_CHUONG_TRINH`, chỉ category `nganh_dao_tao`, không tạo subplans | `MULTI_ISSUE` + các sub-question độc lập, evidence/answer theo từng issue | FAIL |

## 5. Audit quan hệ ngành chính → chương trình

Audit trên corpus hiện tại cho thấy **20 mã ngành chính** và **47 quan hệ duy nhất**, không sửa data để ép số. Có 16 ngành có danh sách chương trình con:

| Ngành chính | Số CT | Chương trình con theo dữ liệu hiện tại |
|---|---:|---|
| Quản trị Kinh doanh tổng hợp (`QTKD`) | 5 | Quản trị Nguồn nhân lực; Quản trị Logistics; Khởi nghiệp và Phát triển bền vững; Quản trị công nghệ và Đổi mới sáng tạo; Quản trị Kinh doanh tổng hợp |
| Marketing | 4 | Quản trị Marketing; Digital Marketing; Truyền thông và quan hệ công chúng; Truyền thông số |
| Thương mại điện tử | 3 | Quản trị thương mại điện tử; Kinh doanh số; Phân tích dữ liệu kinh doanh |
| Tài chính ngân hàng | 2 | Ngân hàng số; Tài chính doanh nghiệp |
| Kế toán | 2 | Kế toán doanh nghiệp; Kế toán số |
| Công nghệ tài chính | 2 | Công nghệ tài chính; Khai phá dữ liệu tài chính |
| Kỹ thuật máy tính | 2 | Hệ thống nhúng thông minh; AI và IoT ứng dụng |
| Công nghệ thông tin | 5 | Công nghệ phần mềm; Lập trình AI; An ninh mạng và hệ thống; Truyền thông đa phương tiện; Phân tích dữ liệu lớn |
| Ngôn ngữ Anh | 2 | Giảng dạy Tiếng Anh; Tiếng Anh Thương mại |
| Ngôn ngữ Nhật | 2 | Tiếng Nhật thương mại; Ngôn ngữ - Văn hóa Nhật Bản |
| Ngôn ngữ Trung Quốc | 4 | Tiếng Trung thương mại; Tiếng Trung hành chính văn phòng; Giảng dạy Tiếng Trung; Tiếng Trung Văn hóa - Du lịch |
| Ngôn ngữ Hàn Quốc | 2 | Giảng dạy Tiếng Hàn; Tiếng Hàn thương mại |
| Quản trị Khách sạn | 2 | Quản trị khách sạn; Quản trị nhà hàng và dịch vụ ẩm thực |
| Quản trị Dịch vụ Du lịch & Lữ hành | 3 | Quản trị lữ hành; Quản lý giải trí; Quản trị sự kiện |
| Quản lý bệnh viện | 3 | Quản lý chất lượng bệnh viện; Quản lý tài chính bệnh viện; Quản lý trang thiết bị y tế |
| Tâm lý học | 4 | Tâm lý học đường; Tâm lý lâm sàng; Tâm lý tổ chức - Nhân sự; Ứng dụng AI trong tâm lý |

Hai quan hệ dễ bị mất do chuẩn hóa tên vẫn đang đúng trong corpus: `Công nghệ tài chính` → `Công nghệ tài chính` và `Quản trị khách sạn` → `Quản trị Khách sạn`. Tests hiện có xác nhận count/order này. Các ngành chính còn lại trong inventory không có chương trình con được parse từ các chunk hiện tại; không suy diễn thêm.

## 6. Gap matrix và root cause

| ID | Mức | Root cause | Current → expected |
|---|---|---|---|
| H-01 | P0 | `INTENTS` và `_classify_intent_rules` không có `GREETING`, `SYSTEM_IDENTITY`, `SYSTEM_SCOPE`; `rag_chain` chỉ có out-of-scope gate | `Xin chào`/`Bạn là ai?` → out-of-scope; cần nhánh deterministic, không RAG |
| H-02 | P0 | Rule `diem xet tuyen` tại `query_analysis.py` ưu tiên `HOI_CACH_TINH_DIEM`; entity extractor không gán `score_type`; validator chỉ kích hoạt score mapping khi có score type/marker hẹp | Law score query → formula + answer số có thể lọt; cần type/method/major mapping bắt buộc và abstain |
| H-03 | P0 | `_valid_http_url`, loader và `_is_verified_dhv_document` chỉ kiểm tra HTTP/status/year/school code, không kiểm tra hostname allowlist | URL HTTP bất kỳ có thể qua; cần chỉ `dhv.edu.vn` và subdomain |
| H-04 | P0 | `QueryAnalysis`/`QueryPlan` chỉ biểu diễn một intent và một retrieval query | Multi-issue → một category; cần `MULTI_ISSUE` và subplans/evidence độc lập |
| H-05 | P1 | `select_candidate_documents` chỉ lọc substring candidate; `build_evidence` gom các chunk hợp lệ; không có stage Evidence Selection theo intent/entity/score type | Broad context → LLM tự chọn; cần selected evidence contract trước planner/LLM |
| H-06 | P1 | `_rank_hybrid_candidates` là token overlap + vector rank; không phải BM25+dense+RRF; collection scan trong memory | “Hybrid” hiện tại → ranking có heuristic/O(N); cần retrieval contract/versioned strategy |
| H-07 | P1 | `rag_prompt.py` tạo một prompt tổng quát; chưa có Answer Planner/mode/schema | Mọi câu non-deterministic → cùng prompt; cần planner chọn DIRECT/OVERVIEW/TABLE/RECOMMENDATION/NO_DATA... |
| H-08 | P1 | `query_analysis.topic/category`, `route_question`, `scope_guard` và guard trong `rag_chain` cùng chứa keyword/scope logic; Law còn có special-case named major | Nhiều nguồn sự thật → drift và hard-code; cần một owner cho intent/route/scope, không special-case ngành |
| H-09 | P1 | `app.py:_render_sources` render `source_url`; README cũng mô tả URL UI | Backend provenance → UI source cards/URLs; cần giữ provenance backend nhưng ẩn khỏi UI |
| H-10 | P1 | `RetrievalAudit` chỉ giữ query/filter/hits; chưa có code/model/prompt/embedding/index/version hash; không có RAG eval harness tách retrieval/generation | Khó trace/regression theo version; cần manifest + eval metrics Hit@k/precision/recall/grounding/abstention |
| H-11 | P2 | `ChatService` wrapper mỏng, app gọi function; orchestration dồn vào `rag_chain.ask_chatbot` | Boundary vẫn chạy → ownership mờ; cần refactor tối thiểu, giữ API tương thích |
| H-12 | P1 | RAW `thong_tin_truong_dhv_2026.pdf` có trong worktree nhưng chưa có processed/index tương ứng | School info/contact có nguồn RAW chính thức → runtime chưa coverage; chỉ ingest sau verification/rebuild task riêng |

## 7. Quyết định kiến trúc và thứ tự refactor tối thiểu

1. Giữ `ChatService`, `rag_chain` và Streamlit API hiện tại; không tạo router/retriever/evidence module thứ hai.
2. Chuẩn hóa contract trong `query_analysis.py`: thêm system intents, audience/question type, score type, và multi-issue subplans; giữ rule/classifier ở một nơi.
3. Đưa greeting/identity/scope vào deterministic response layer trước retrieval; `scope_guard` chỉ làm policy predicate hoặc được gộp vào owner duy nhất, không nhân bản keyword list.
4. Sửa score semantics trước khi mở rộng LLM: phân biệt `application_threshold` và `admission_score`, bắt buộc method/year/major mapping; Python quyết định list/count/score/comparison, LLM không tính và không kết luận đậu-rớt.
5. Tạo Evidence Selection stage trong `evidence.py` hoặc `rag_chain.py` (chọn một owner hiện hữu), đầu ra là selected structured facts + selected chunks; không truyền toàn bộ candidate context vào prompt.
6. Nâng retrieval trong `retriever.py` theo từng bước có thể đo: metadata allowlist → sparse+dense → RRF → selection; thêm retrieval/index/data contract version vào audit.
7. Thêm Answer Planner riêng chỉ khi chưa có owner tương đương; planner trả mode/schema cho prompt và validator. Không để prompt tự quyết định routing hay authorization.
8. Ẩn sources khỏi UI tại `app.py`, nhưng vẫn giữ provenance trong backend/trace.
9. Sau mỗi bước chạy targeted → full regression; sau thay đổi data/retrieval mới rebuild và smoke. Không ingest RAW school-info trong TASK H.

## 8. Files dự kiến cho các task sửa tiếp theo

**Files đã thay đổi trong TASK H:** chỉ có file báo cáo này.

**Files dự kiến cần xem/sửa theo thứ tự:**

- `src/chatbot/query_analysis.py`
- `src/chatbot/scope_guard.py`
- `src/chatbot/rag_chain.py`
- `src/chatbot/evidence.py`
- `src/chatbot/output_validator.py`
- `src/retrieval/retriever.py`
- `src/prompts/rag_prompt.py`
- `app.py`
- tests tương ứng; có thể thêm một `answer_planner.py` duy nhất nếu chưa có module ownership phù hợp.

Không dự kiến sửa trong audit này: `data/raw/`, `data/processed/`, `chroma_db/`.

## 9. Tests, smoke và metrics

| Kiểm tra | Kết quả |
|---|---|
| Compile `src` + `tests` | PASS |
| Targeted `tests.test_task_c tests.test_task_f tests.test_task_g` | **57 tests, OK** |
| Full `unittest discover` | **74 tests, OK, 1 skipped**; test skipped là real Qwen integration do chưa bật `RUN_REAL_QWEN_TESTS=1` |
| Vector DB smoke với Ollama embeddings | **SMOKE_PASS**, 3 queries |
| Rebuild-style retrieval regression không ghi dữ liệu | **REGRESSION_PASS**, 12 cases |
| Intent holdout | 144 train / 36 test; 30 đúng; accuracy **83.33%**; macro-F1 **80.74%** |
| Intent confusions | `HOI_DIEM_TRUNG_TUYEN → HOI_NGUONG_DAU_VAO` 2 lần; thêm 4 confusion đơn lẻ ở chương trình/list/người dùng ngoài scope |
| Program-parent corpus audit | 20 major codes; 47 unique relations; 18 Chroma chunks |

Lần chạy trong sandbox gặp 5 lỗi quyền tạo/xóa `TemporaryDirectory` trên Windows; chạy lại cùng suite với quyền môi trường phù hợp cho kết quả full regression nêu trên. Đây là giới hạn môi trường, không phải assertion failure của product.

## 10. Sources, data mới, conflicts và unverified

- Audit không thêm nguồn/data mới.
- 13 processed documents hiện tại đều `year=2026`, `status=verified`, `school_code=DHV`; Chroma có 18 chunks. Domain hiện thấy là `dhv.edu.vn` và `tuyensinh.dhv.edu.vn`.
- Worktree có 14 PDF RAW; `data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf` là RAW chính thức bổ sung nhưng chưa được prepare/index. Không tự import trong TASK H.
- Loader/evidence vẫn chưa enforce allowlist host. Một số fixture test dùng URL `example.test`, vì vậy policy official-domain hiện chưa được test đầy đủ.
- Không phát hiện conflict dữ liệu nào được phép tự giải quyết trong audit. Việc xác minh nội dung 2026 và ingest PDF bổ sung cần task data/rebuild riêng.
- Reference images không được đọc vào KB, không được dùng làm asset/style/source/prompt/data.

## 11. Limitations

- Real Qwen generation chưa chạy; các probe LLM dùng test double để chứng minh validator/routing behavior.
- `rebuild_smoke_test` hiện gọi trực tiếp similarity search và chưa kiểm tra toàn bộ router → Evidence Selection → validator; vì vậy PASS của smoke không chứng minh evidence isolation.
- Chưa có benchmark RAG độc lập cho Hit@k, context precision/recall, grounding và abstention; đây là gap cần đo sau khi contract được chốt.

## 12. Exact reproduce commands

Chạy từ repository root:

```powershell
Set-Location C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV
\.venv\Scripts\python.exe -m compileall -q src tests
\.venv\Scripts\python.exe -m unittest tests.test_task_c tests.test_task_f tests.test_task_g -v
\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text --top-k 4
\.venv\Scripts\python.exe -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text --top-k 18
```

Reproduce intent/route của multi-issue:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from src.chatbot.query_analysis import analyze_question, route_question
q = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
a = analyze_question(q)
r = route_question(a)
print(a.to_dict())
print(r.to_dict())
'@ | .\.venv\Scripts\python.exe -
```

Reproduce trained intent holdout:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from src.chatbot.intent_classifier import DEFAULT_TEST_PATH, DEFAULT_TRAIN_PATH, load_model, load_records
train = load_records(DEFAULT_TRAIN_PATH)
test = load_records(DEFAULT_TEST_PATH)
model = load_model()
pred = [model.predict(row["text"]).intent for row in test]
print(len(train), len(test), sum(row["intent"] == p for row, p in zip(test, pred)))
'@ | .\.venv\Scripts\python.exe -
```

Các câu hỏi bắt buộc còn lại được reproduce bằng cùng harness với corpus-backed retriever và test-double LLM: `CNTT có những chương trình gì?`, `CNTT có bao nhiêu chương trình?`, `điểm xét tuyển học bạ ngành Luật bao nhiêu?`, `Tôi 19 điểm thích edit video nên chọn ngành nào?`, `Xin chào`, `Bạn là ai?`, `Bạn hỗ trợ được gì?`, `Thời tiết hôm nay?`.

## PASS/FAIL

**FAIL.** Regression hiện tại pass, nhưng audit xác nhận các invariant target chưa đúng; cần thực hiện các task sửa kiến trúc theo thứ tự ở mục 7 trước khi có thể tuyên bố PASS.
