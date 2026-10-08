# TASK L — Answer Planner + Natural Response

Ngày: 2026-09-15  
Repository: `ChatBot_DHV`  
Kết luận: **PASS**

## 1. Task

Thêm Answer Planner đứng sau intent/router và Evidence Selection, để câu trả lời
được trình bày theo đúng loại câu hỏi thay vì dùng một template RAG cho mọi lượt:

- `DIRECT_SHORT`, `EXPLANATION`, `OVERVIEW`, `COMPARISON`, `TABLE`,
  `STEP_BY_STEP`, `RECOMMENDATION`, `CLARIFICATION`, `NO_DATA`,
  `OUT_OF_SCOPE`.
- LLM chỉ nhận instruction về hình thức từ planner và facts/evidence đã được
  chọn; planner không truy xuất và không tạo fact.
- Backend giữ provenance để audit; UI không render source cards/URL.
- Có tối đa 3 related questions do Python tạo theo intent/entity, không gọi LLM
  và không chứa URL.

Manual cases bắt buộc đã được probe: `hello`; tên chatbot; scope; overview CNTT;
đếm chương trình; so sánh CNTT/Kỹ thuật máy tính; học phí + học bổng; tư vấn theo
sở thích.

## 2. Baseline và reproduce

Baseline trước TASK L: hệ thống đã có routing, Evidence Selection và validator,
nhưng chưa có contract answer plan. Các intent RAG đều dựng cùng một prompt; model
hoặc test double có thể trả văn bản context thô. Trace không ghi mode diễn đạt và
UI còn hiển thị provenance backend.

Baseline probe cho thấy:

| Case | Current trước sửa | Expected |
|---|---|---|
| Overview CNTT | Trả các dòng score theo prompt chung | Tóm tắt overview có các ý chính |
| So sánh hai ngành | Không có mode so sánh | `COMPARISON`, nêu từng lựa chọn theo cùng tiêu chí |
| Tư vấn sở thích | Không có planner contract | `RECOMMENDATION`, lời khuyên có điều kiện |
| Multi-issue | Ghép các output nhưng không có outer/sub answer plan | Có plan riêng cho từng issue và plan ghép |
| UI provenance | Render source title + URL | Giữ ở backend, không render trong UI |

Lệnh baseline:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả baseline có các assertion cũ của source UI và lỗi quyền
`TemporaryDirectory`/Chroma trên Windows sandbox; các regression logic trước
TASK L không có failure assertion.

## 3. Root cause

1. `rag_chain.py` có intent/evidence/validator nhưng chưa có owner cho quyết định
   về hình thức câu trả lời.
2. `rag_prompt.py` có grounding rules chung, chưa nhận biết overview, comparison,
   step-by-step hay recommendation.
3. Multi-issue mới có subplan retrieval nhưng chưa ghi contract realization cho
   từng subplan.
4. UI copy toàn bộ `sources` từ backend và render URL dưới câu trả lời, trái với
   invariant của master plan.

## 4. Current → expected → result

| Hạng mục | Expected | Kết quả |
|---|---|---|
| Planner modes | Đủ 10 mode, chọn theo intent + shape + status | PASS; `ANSWER_MODES` và `AnswerPlan` có contract serializable |
| Overview | Có mode riêng, có section key points/next question | PASS; overview CNTT → `OVERVIEW` |
| Comparison | Không trộn hai candidate, cùng basis | PASS; CNTT vs Kỹ thuật máy tính → `COMPARISON` |
| Count/catalog | Không dùng LLM để đếm | PASS; CNTT → 5 chương trình, LLM không bị gọi |
| Recommendation | Suy luận có điều kiện từ sở thích/evidence, không quyết định đậu/rớt | PASS; mode `RECOMMENDATION`, score engine/validator giữ nguyên |
| Clarification/no-data/out-of-scope | Boundary deterministic | PASS; không gọi RAG/LLM cho system; no-data có `NO_DATA` |
| Multi-issue | Outer plan + subplan plan, section theo issue | PASS; 3 subplan được trace riêng |
| Related questions | 0–3, deterministic, không URL | PASS; manual successful cases tối đa 3 gợi ý |
| UI sources | Backend giữ provenance, UI không source cards/URL | PASS; app sanitizer + regression UI mới |

## 5. Files changed

- `src/chatbot/answer_planner.py`: owner mới duy nhất cho mode, response format,
  sections, required content và related questions; có `AnswerPlan`,
  `AnswerPlanner`, function aliases và 10 mode constants.
- `src/chatbot/rag_chain.py`: gọi planner ở boundary/system, sau evidence và
  sau generation; ghi `answer_plan` vào API/trace; planner cho từng multi-issue
  subplan; giữ catalog/score deterministic; UI-facing website answer vẫn giữ
  provenance ở backend.
- `src/prompts/rag_prompt.py`: nhận `answer_plan`, thêm `<ANSWER_PLAN>` và
  instruction riêng cho từng mode; plan chỉ điều khiển hình thức, không là nguồn
  fact.
- `src/chatbot/__init__.py`: export `AnswerPlan`, `AnswerPlanner`, `plan_answer`.
- `app.py`: không copy/render `sources`; sanitize URL trong text trước hiển thị;
  hiển thị related questions dạng gợi ý văn bản an toàn.
- `README.md`: đồng bộ tài liệu rằng provenance ở backend, UI không hiển thị URL.
- `tests/test_task_l.py`: 7 regression tests cho modes, prompt contract, trace,
  multi-issue và comparison.
- `tests/test_app.py`: cập nhật test history để kiểm tra invariant mới là ẩn
  backend sources/URL, không xóa test coverage status/history.
- `reports/TASK_L_ANSWER_PLANNER_RESULT.md`: report này.

Các file khác đang modified/untracked trong working tree thuộc các task trước
hoặc dữ liệu/plan đã có; không reset, xóa hay sửa chúng để phục vụ TASK L.

## 6. Architecture decisions

- Giữ refactor tối thiểu: planner là module duy nhất, không tạo router/retriever
  mới; `ChatService`/`ask_chatbot` vẫn tương thích.
- Thứ tự runtime là `analysis → router → retrieval → Evidence Selection →
  structured evidence → Answer Planner → LLM realization → validator`.
- System intent, clarification, no-data và out-of-scope không gọi LLM để quyết
  định hình thức hay tạo câu trả lời. Catalog/count và score vẫn do Python sở hữu.
- Plan được truyền vào prompt như metadata hình thức; structured score facts,
  score comparisons, entity relations và context vẫn là các block evidence riêng.
- Related questions được sinh từ intent/entity canonical đã có, giới hạn 3 và
  không chứa URL. Gợi ý không được dùng làm facts.
- Backend vẫn trả `sources` để giữ provenance và các regression backend hiện hữu;
  app bỏ field này khỏi payload render và lọc URL khỏi nội dung hiển thị.
- Không dùng ảnh tham khảo làm asset, wording, prompt, brand hay dữ liệu; không
  ingest `reference_images/` vào KB.

## 7. Tests và kết quả

Targeted TASK L:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_l -q
```

Kết quả: **Ran 7 tests — OK**.

Related regression:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_l tests.test_task_i tests.test_task_j tests.test_task_k -q
```

Kết quả: **Ran 23 tests — OK**.

Full regression, với temp writable để Chroma/TemporaryDirectory hoạt động đúng:

```powershell
$tempPath = Join-Path (Get-Location) 'tmp\task-l-test-temp-final'
New-Item -ItemType Directory -Force -Path $tempPath | Out-Null
$env:TEMP=$tempPath
$env:TMP=$tempPath
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả: **Ran 97 tests — OK (skipped=1)**. Test skip là real Qwen integration,
chỉ chạy khi bật `RUN_REAL_QWEN_TESTS=1` và Ollama/model tương ứng sẵn sàng.

Kiểm tra bổ sung:

```powershell
& '.venv\Scripts\python.exe' -m compileall -q src tests
git diff --check
```

Kết quả: **PASS**.

## 8. Manual cases và metrics

Probe dùng retriever fixture và LLM double để không phụ thuộc Ollama:

| Metric | Kết quả |
|---|---:|
| Manual cases đạt mode + status | 8/8 |
| Mode contract trong targeted tests | 7/7 tests |
| Related questions mỗi case thành công | 2–3, không URL |
| Multi-issue subplan answer plans | 3/3 |
| Full regression | 97 tests, 1 skip |

Mapping manual:

```text
hello                                      → DIRECT_SHORT
Bạn tên gì?                                → DIRECT_SHORT
Bạn có phải toàn bộ thông tin trường không?→ EXPLANATION
Tổng quan về ngành Công nghệ thông tin?   → OVERVIEW
CNTT có bao nhiêu chương trình đào tạo?   → DIRECT_SHORT (deterministic)
So sánh CNTT với Kỹ thuật máy tính       → COMPARISON
CNTT học phí + học bổng                  → EXPLANATION
Tôi thích edit video nên chọn ngành nào?  → RECOMMENDATION
```

Chưa có gold benchmark để gán điểm chất lượng diễn đạt; đây là metric contract và
regression offline, không phải đánh giá chất lượng real Qwen.

## 9. Sources/data mới, conflicts và unverified

- Không có source/data mới trong TASK L; không sửa RAW, processed Markdown/YAML
  hoặc Chroma và không rebuild index.
- Không đưa ảnh tham khảo vào RAG KB.
- Evidence/score provenance vẫn theo verified-only boundary từ TASK K/J; planner
  không nới điều kiện verified và không fallback sang dữ liệu unverified.
- Không phát hiện conflict dữ liệu mới.
- Một test UI trước đây yêu cầu hiển thị URL, mâu thuẫn với invariant TASK L; test
  được chuyển thành assertion ẩn URL nhưng vẫn giữ nguyên coverage lịch sử/status.

## 10. Limitations

- Chưa chạy real Qwen/Ollama; integration vẫn skip theo cấu hình môi trường.
- Planner kiểm soát cấu trúc qua prompt, còn độ tự nhiên cuối cùng phụ thuộc model
  cục bộ và validator. LLM double `EchoEvidenceLLM` trong regression chủ ý echo
  evidence để kiểm thử grounding, không đại diện style real model.
- UI related questions hiện là gợi ý văn bản, chưa phải nút gửi lại câu hỏi; việc
  làm thành interactive buttons thuộc phạm vi UI/evaluation tiếp theo.
- Chưa tạo evaluation dev/holdout hay metrics answer quality; đó là TASK N.

## 11. Exact reproduce commands

Từ repository root:

```powershell
Set-Location 'C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV'
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_l -q
& '.venv\Scripts\python.exe' -m unittest tests.test_task_l tests.test_task_i tests.test_task_j tests.test_task_k -q
& '.venv\Scripts\python.exe' -m compileall -q src tests
& 'git' diff --check
```

Full suite cần temp path writable như lệnh ở mục 7 khi môi trường Windows sandbox
chặn cleanup temporary files.

## 12. PASS/FAIL

**PASS** — targeted TASK L pass; related regression pass; full regression 97 tests
pass với 1 skip đã biết; compile/diff-check pass; 8/8 manual cases đạt mode;
planner không tạo fact, không phá deterministic catalog/score, multi-issue có
subplans và trace, backend giữ provenance nhưng UI không hiển thị source cards/URL.
