# TASK N — Kết quả Validator, Evaluation và UI

Ngày thực hiện: 15/09/2026  
Phạm vi: DHV_AGENT_MASTER_PLAN_UPDATED/07_TASK_N_VALIDATOR_EVALUATION_UI.md

## Kết luận

**PASS.** Targeted tests, full regression và evaluation đều pass. Không có critical factual hallucination trong bộ đánh giá cố định. Holdout được giữ độc lập và chỉ dùng để báo cáo.

## Baseline và root cause

Baseline trước TASK N: full suite có 101 tests, 1 skipped; các assertion nghiệp vụ đã pass nhưng 5 test ingestion/retrieval lỗi Access denied khi Windows sandbox tạo/dọn TemporaryDirectory cho Chroma. Đây là lỗi môi trường quyền thư mục tạm, không phải lỗi assertion của sản phẩm.

Root cause của phần còn thiếu trong TASK N:

- Validator đã có grounding, catalog và một số ràng buộc điểm, nhưng chưa có một boundary contract rõ ràng cho năm, trường mục tiêu, official-status wording và semantic score/method.
- Chưa có evaluation harness cố định để tách intent, retrieval và answer; chưa có dev/holdout policy có thể kiểm tra bằng test.
- UI trước TASK N đã có Markdown/chat message và URL sanitizer, nhưng chưa có evaluation chứng minh answer contract và holdout regression.

## Current → expected → result

| Khu vực | Current trước TASK N | Expected | Result |
|---|---|---|---|
| Evidence metadata | Một số kiểm tra rải rác | Chỉ nhận verified, năm 2026, school code DHV, URL official DHV/subdomain | Đã thêm evidence contract; reject rõ reason |
| Answer contract | Chưa bao phủ đầy đủ boundary wording/entity/year/institution | Chặn hallucination factual trước khi hiển thị | Đã thêm year_mismatch, institution_mismatch, official_status_claim, entity_mismatch và retry/fallback mapping |
| Score semantics | Có mapping điểm nhưng chưa đủ phân biệt score type/method ở boundary | Không trộn điểm sàn, điểm trúng tuyển, bổ sung hoặc phương thức | Đã thêm kiểm tra score_type_mismatch, method_mismatch; Python tiếp tục giữ vai trò tính/đối chiếu |
| Parent/program | Có logic relation nhưng cần regression contract | Không biến chương trình thành ngành độc lập, giữ đúng parent | Giữ Evidence Selection và relation validator; có test regression |
| Evaluation set | Chưa có bộ cố định | Dev 80%, holdout 20%, ID disjoint, holdout không tune | 16 dev + 4 holdout, kiểm tra tự động |
| UI | Markdown/chat rendering; backend còn provenance | Markdown/table tự nhiên, không source cards/URLs; related questions không bắt buộc là button | AppTest pass; UI không render URL/source cards, related questions hiển thị dạng gợi ý text an toàn |

## Files changed cho TASK N

- src/chatbot/output_validator.py: evidence contract; entity/year/institution/official-status/score semantic checks.
- src/chatbot/rag_chain.py: retryable validation reasons và advisory fallback an toàn, giữ tương thích ask_chatbot/ChatService.
- evaluation/__init__.py, evaluation/evaluator.py: loader, split validation, retrieval metrics, answer contract metrics và critical hallucination flag.
- evaluation/run_evaluation.py: runner offline tái sử dụng routing/retrieval/evidence/validator; generation double deterministic chỉ để đánh giá contract, không tạo fact mới.
- evaluation/dev.jsonl: 16 fixed development cases.
- evaluation/holdout.jsonl: 4 fixed holdout cases.
- evaluation/README.md: policy, metric definitions và reproduce command.
- tests/test_task_n.py: 6 tests cho split, metrics và validator boundary.
- reports/TASK_N_FINAL_EVALUATION_RESULT.md: báo cáo này.

app.py không cần sửa thêm trong TASK N: implementation hiện tại đã dùng native st.chat_message/st.markdown, unsafe_allow_html=False, lọc URL hiển thị và không render source cards. Việc không sửa UI thêm là quyết định refactor tối thiểu.

## Architecture decisions

- Validator vẫn là boundary cuối trước UI; không chuyển grounding, score calculation hay admission decision sang LLM.
- Giữ ChatService/ask_chatbot và flow Evidence Selection; chỉ bổ sung contract checks và reason mapping.
- Evaluator nằm ngoài runtime chatbot. OfflineCorpusStore chỉ là adapter đọc processed corpus đã verified để chạy reproducible, không thay đổi production retriever.
- Retrieval metrics và answer metrics được tính riêng. Answer scorer là deterministic contract scorer: status, required markers, forbidden claims, faithfulness contract khi có evidence; không dùng LLM judge để làm nguồn sự thật.
- Holdout không được đưa vào tuning; command loader kiểm tra disjoint IDs và policy report-only.
- Không dùng reference_images/, không đưa ảnh vào RAG KB, không thêm RAW/PII và không sửa data để che bug.

## Tests và evaluation

### Targeted

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_task_n -q
# Ran 6 tests ... OK

.\.venv\Scripts\python.exe -m unittest tests.test_task_n tests.test_task_f tests.test_task_g tests.test_task_i tests.test_task_j tests.test_task_k tests.test_task_l -q
# Ran 67 tests ... OK

.\.venv\Scripts\python.exe -m unittest tests.test_app -q
# Ran 3 tests ... OK

.\.venv\Scripts\python.exe -m compileall -q src evaluation tests
git diff --check
~~~

### Full regression

~~~powershell
$env:PYTHONIOENCODING = 'utf-8'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
~~~

Kết quả cuối chạy ngoài sandbox để loại bỏ giới hạn quyền thư mục tạm:

~~~text
Ran 107 tests in 5.891s
OK (skipped=1)
~~~

metadata error in broken.md: missing YAML front matter là warning từ fixture cố ý hỏng trong test ingestion; test vẫn pass.

### Evaluation command

~~~powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --split all
~~~

Kết quả all với top_k=5:

| Metric | Result |
|---|---:|
| Dataset | 20 cases; 16 dev / 4 holdout; disjoint = true |
| Intent accuracy | 1.0000 (20/20) |
| Retrieval eligible cases | 15 |
| Hit@5 | 1.0000 |
| Precision@5 | 0.2933 |
| Recall@5 | 0.9556 |
| MRR | 0.9333 |
| Answer correctness | 1.0000 (20/20) |
| Relevance | 1.0000 |
| Faithfulness contract | 1.0000 |
| Abstention accuracy | 1.0000 |
| Hallucination rate | 0.0000 |
| Critical factual hallucinations | **0** |

Phân tách split:

- Dev: 16/16 intent và answer pass; Hit@5 1.0000, Precision@5 0.3273, Recall@5 0.9394, MRR 0.9091.
- Holdout: 4/4 intent và answer pass; Hit@5 1.0000, Precision@5 0.2000, Recall@5 1.0000, MRR 1.0000.

## Sources, data và conflicts

- Không có source/data mới được ingest trong TASK N. Evaluation dùng các processed Markdown DHV 2026 đã verified từ official dhv.edu.vn/subdomain.
- Phương pháp metric được đối chiếu trong Tong_quan_xay_dung_chatbot_AI.pdf, phần evaluation khoảng trang 41–47: tách retrieval/generation, Hit@k/Recall@k/MRR, correctness/faithfulness/citation/abstention và dùng human calibration khi cần.
- Không dùng URL/source card trong UI; URL chỉ còn ở backend provenance/evidence metadata theo kiến trúc.
- Không phát hiện conflict mới. Ghi chú dữ liệu cũ 2023/2024 trong tài liệu mô tả CNTT vẫn được coi là boundary cảnh báo và không dùng để thay thế fact tuyển sinh 2026.

## Limitations

- Generation backend của evaluation là deterministic evidence echo/double offline, không phải phép đo chất lượng văn phong Qwen/Ollama thực tế; vì vậy answer metrics chứng minh contract/grounding boundary chứ không thay thế human review về độ tự nhiên.
- Faithfulness metric trong harness là contract-level và không phải LLM-as-judge; các benchmark ngưỡng minh họa trong PDF không được tự coi là project acceptance threshold.
- Validator hiện khóa target year 2026 theo phạm vi TASK N/master plan; khi mở sang năm khác cần chuyển expected year sang cấu hình hoặc request-scoped policy.
- Không đo P95 latency trong TASK N vì không thay đổi runtime performance path và offline evaluator không khởi chạy Ollama.

## Exact reproduce và verdict

Từ repository root:

~~~powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m unittest tests.test_task_n -q
.\.venv\Scripts\python.exe -m unittest tests.test_task_n tests.test_task_f tests.test_task_g tests.test_task_i tests.test_task_j tests.test_task_k tests.test_task_l -q
.\.venv\Scripts\python.exe -m unittest tests.test_app -q
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --split dev
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --split holdout
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --split all
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
~~~

**PASS** — targeted tests pass, full regression pass, evaluation dev/holdout pass, critical factual hallucination bằng 0, UI invariants còn đúng.
