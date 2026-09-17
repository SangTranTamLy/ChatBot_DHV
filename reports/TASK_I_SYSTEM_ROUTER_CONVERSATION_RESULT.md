# TASK I — System Router + Conversation Result

Ngày: 2026-09-15  
Repository: `ChatBot_DHV`  
Kết luận: **PASS**

## 1. Task

Hoàn thiện `GREETING`, `SYSTEM_IDENTITY`, `SYSTEM_SCOPE`, `SCHOOL_INFO`,
`MULTI_ISSUE`; giữ conversation state bounded/session-only; bảo đảm follow-up
giữ hoặc chuyển major/program/method/score/interest hợp lý; không gọi RAG cho
greeting/identity/scope; không tự nhận là kênh chính thức DHV.

Các case bắt buộc: `hello`; `Bạn tên gì?`; `Bạn có phải chatbot chính thức
không?`; `Bạn có phải toàn bộ thông tin trường không?`; `DHV là trường gì?`;
follow-up `CNTT`;
`Đổi sang Kỹ thuật máy tính`; và `Thời tiết hôm nay?`.

## 2. Baseline và reproduce

Trước khi sửa, router không có intent hệ thống; `Xin chào` và `Bạn là ai?`
bị xử lý như `OUT_OF_SCOPE`. Câu nhiều chủ đề chỉ giữ một intent/category;
không có subplan độc lập. Khi đổi major, state có thể giữ program/candidate
của major cũ.

Baseline full suite bằng sandbox mặc định:

```text
\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
Ran 74 tests in 3.725s
FAILED (errors=5, skipped=1)
```

5 lỗi là lỗi môi trường Windows sandbox khi tạo/dọn `TemporaryDirectory` và
Chroma handle; không phải assertion của router. Các test chức năng còn lại
đều pass.

## 3. Root cause

1. `query_analysis.py` chỉ có vocabulary intent tuyển sinh/RAG; không có nhánh
   deterministic cho greeting, identity và scope.
2. `rag_chain.py` sau khi route luôn đi qua scope/retrieval, nên không có trust
   boundary response trước RAG.
3. `QueryPlan` biểu diễn một issue duy nhất, không có decomposition/subplans.
4. `update_conversation_state` luôn fallback về major/program cũ và không nhận
   biết explicit context switch.
5. Scope predicate chưa nhận diện câu hỏi SCHOOL_INFO khái quát.

## 4. Current → expected → result

| Case | Current trước sửa | Expected | Result sau sửa |
|---|---|---|---|
| `hello` | `OUT_OF_SCOPE` | `GREETING`, deterministic, không RAG | PASS |
| `Bạn tên gì?` | `OUT_OF_SCOPE` | `SYSTEM_IDENTITY`, nói rõ trợ lý AI trong đồ án | PASS |
| chatbot chính thức? | Không có identity branch | Không tự nhận official; khẳng định không phải kênh chính thức | PASS |
| toàn bộ thông tin trường? | Bị scope gate | `SYSTEM_SCOPE`, nêu phạm vi tuyển sinh 2026, không phải toàn bộ DHV | PASS |
| `CNTT` → follow-up | State chưa có switch contract | Giữ current major bounded | PASS |
| đổi sang Kỹ thuật máy tính | Có thể còn program/candidates cũ | current major mới, clear program/list cũ, giữ score/interest hợp lý | PASS |
| thời tiết | Out-of-scope nhưng chưa có system routing separation | `OUT_OF_SCOPE`, không retrieval/LLM | PASS |
| học phí + học bổng + chương trình | Một intent/category | `MULTI_ISSUE`, 3 subplans độc lập | PASS |

## 5. Files changed cho TASK I

- `src/chatbot/query_analysis.py`: system-router vocabulary/predicates; thêm
  `SCHOOL_INFO`, `MULTI_ISSUE`, `QueryPlan.subplans`; bounded state aliases và
  explicit major switch.
- `src/chatbot/rag_chain.py`: deterministic response trước scope/retrieval;
  retrieve từng multi-issue subplan, lọc category trước evidence, ghép kết quả.
- `src/chatbot/scope_guard.py`: nhận diện SCHOOL_INFO trong scope predicate.
- `tests/test_task_i.py`: 6 regression tests cho system router, official wording,
  out-of-scope, context switch và multi-issue decomposition.
- `reports/TASK_I_SYSTEM_ROUTER_CONVERSATION_RESULT.md`: report này.

Các thay đổi khác đã có sẵn trong working tree trước task này được giữ nguyên;
không reset/xóa hoặc sửa để che lỗi.

## 6. Architecture decisions

- Giữ ownership hiện hữu trong `query_analysis.py` và `rag_chain.py`; không tạo
  router/service trùng chức năng và giữ API `ChatService`/Streamlit tương thích.
- `GREETING`, `SYSTEM_IDENTITY`, `SYSTEM_SCOPE` là router-only deterministic
  intents. Chúng bỏ qua trained classifier, có `intent_source=
  deterministic_router`, category rỗng và trả lời trước retrieval/LLM.
- `SCHOOL_INFO` là intent retrieval riêng với category `thong_tin_truong`; nó
  không kế thừa current major/program của conversation.
- `MULTI_ISSUE` tạo subplan theo từng topic. Mỗi subplan có intent/category/
  metadata filter riêng; adapter trả kết quả rộng hơn filter vẫn bị lọc lại
  trước `build_evidence`. Catalog vẫn do Python format.
- State chỉ chứa bounded slots; không lưu raw history, PII, hay ghi state/score
  vào Chroma. Tương thích ngược được giữ qua cả tên `student_scores`/`user_scores`
  và `interest`/`interests`.
- Explicit đổi major clear `current_program`, candidate choices và list context
  cũ; method/score/interest của thí sinh được giữ lại vì vẫn có thể áp dụng cho
  major mới.
- Không sửa RAW, processed Markdown/YAML, Chroma, prompt nguồn, reference
  images hoặc UI source-card trong task này.

## 7. Tests và kết quả

Targeted TASK I:

```powershell
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m unittest tests.test_task_i -v
```

Kết quả: **6 tests, OK**.

Regression liên quan router/conversation/catalog/classifier:

```powershell
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m unittest tests.test_task_c tests.test_task_f tests.test_task_g tests.test_intent_classifier -q
```

Kết quả assertion: **0 failure**; sandbox mặc định vẫn báo 2 lỗi teardown
`TemporaryDirectory` trong hai test Chroma.

Compile:

```powershell
\.venv\Scripts\python.exe -m compileall -q src tests
```

Kết quả: **PASS**.

Full regression cuối, chạy ngoài sandbox do lỗi quyền teardown ở baseline:

```powershell
New-Item -ItemType Directory -Force -Path .\tmp\task-i-test-temp-escalated | Out-Null
$env:TEMP=(Join-Path (Get-Location) 'tmp\task-i-test-temp-escalated')
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả: **Ran 80 tests in 5.728s — OK (skipped=1)**. Test skip là real Qwen
integration vì chưa bật `RUN_REAL_QWEN_TESTS=1`.

## 8. Targeted routing probe và metrics

Probe multi-issue:

```text
Query: CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?
Intent: MULTI_ISSUE
Subplans:
  HOI_HOC_PHI -> ('hoc_phi',)
  HOI_HOC_BONG -> ('hoc_bong',)
  DANH_SACH_CHUONG_TRINH -> ('nganh_dao_tao',)
Union categories: ('hoc_phi', 'hoc_bong', 'nganh_dao_tao')
Retrieval calls: 3
```

System probe xác nhận 5/5 case system/out-of-scope không gọi retriever hoặc
LLM. Catalog subplan vẫn trả danh sách chương trình bằng Python; không nhờ LLM
đếm hoặc chọn parent.

Smoke retrieval/router với corpus fixture (không ghi index):

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from tests.test_task_f import _fixture_chunks, RecordingRetriever, EchoEvidenceLLM
from src.chatbot.rag_chain import ask_chatbot
q = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
retriever = RecordingRetriever(_fixture_chunks())
result = ask_chatbot(q, retriever=retriever, llm=EchoEvidenceLLM())
print(result["status"])
print([call["categories"] for call in retriever.calls])
'@ | \.venv\Scripts\python.exe -
```

Kết quả: `ok`; 3 calls lần lượt `('hoc_phi',)`, `('hoc_bong',)`,
`('nganh_dao_tao',)`. Rebuild Chroma **không chạy** vì TASK I không thay đổi
RAW/processed/index.

## 9. Sources/data mới, conflicts và unverified

- Không có source/data mới trong TASK I.
- Không ingest `data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf` và
  không rebuild Chroma; đây là chủ ý vì task này chỉ sửa router/conversation.
- Không có conflict dữ liệu mới được phát hiện.
- `SCHOOL_INFO` đã có route/category, nhưng runtime chỉ trả nội dung khi nguồn
  trường đã được prepare/index ở task data phù hợp; không bịa fact thay thế.
- Reference images không được đưa vào RAG KB và không được dùng làm logo,
  avatar, background, CSS, layout, prompt, câu chữ hay dữ liệu.

## 10. Limitations

- Full suite cần quyền môi trường phù hợp trên Windows vì Chroma có thể giữ
  file handle khi test teardown; lần chạy escalated đã pass.
- Real Qwen generation chưa chạy; test integration vẫn skip theo cờ môi trường.
- UI vẫn còn các quyết định source rendering từ task trước; TASK I không mở
  rộng sang UI/source-card vì user yêu cầu không nhảy task.
- `SCHOOL_INFO` cần pipeline data/rebuild riêng để có evidence runtime; router
  không tự coi PDF RAW chưa index là dữ liệu trả lời.

## 11. Exact reproduce commands

Từ repository root:

```powershell
Set-Location C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m unittest tests.test_task_i -v
\.venv\Scripts\python.exe -m unittest tests.test_task_c tests.test_task_f tests.test_task_g tests.test_intent_classifier -q
\.venv\Scripts\python.exe -m compileall -q src tests
```

Probe trực tiếp intent/plan:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from src.chatbot.query_analysis import analyze_question, route_question
q = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
a = analyze_question(q)
r = route_question(a)
print(a.intent, a.entities)
print([p.to_dict() for p in r.subplans])
'@ | \.venv\Scripts\python.exe -
```

Full regression với temp path writable:

```powershell
New-Item -ItemType Directory -Force -Path .\tmp\task-i-test-temp-escalated | Out-Null
$env:TEMP=(Join-Path (Get-Location) 'tmp\task-i-test-temp-escalated')
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

## PASS/FAIL

**PASS** — targeted TASK I pass; full regression pass; compile pass; system
invariants (deterministic/no RAG, non-official identity wording, bounded
session state, explicit context switch, independent multi-issue categories)
remain đúng.
