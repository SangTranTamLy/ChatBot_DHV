# TASK K — Retrieval, Evidence Selection và Query Decomposition

Ngày: 2026-09-15  
Repository: `ChatBot_DHV`  
Kết luận: **PASS**

## 1. Task

Hoàn thiện retrieval/evidence boundary cho chatbot DHV:

- Hybrid retrieval có BM25 + dense retrieval + Reciprocal Rank Fusion (RRF).
- Evidence Selection là gate bắt buộc sau retrieval, có metadata/status/source/category
  filtering và entity binding.
- Multi-issue được tách thành các subquery độc lập, retrieval riêng, sau đó merge
  evidence có deduplication.
- Không trộn công thức, ngưỡng, điểm trúng tuyển và xét tuyển bổ sung; không dùng
  LLM để tính điểm hay tự tạo fact.

Đã đối chiếu `DHV_AGENT_MASTER_PLAN_UPDATED/00_MASTER_PLAN.md`,
`DHV_AGENT_MASTER_PLAN_UPDATED/04_TASK_K_RETRIEVAL_EVIDENCE_DECOMPOSITION.md`,
code/tests liên quan và tài liệu phương pháp `Tong_quan_xay_dung_chatbot_AI.pdf`.

## 2. Baseline và reproduce

Baseline trước TASK K:

| Khu vực | Current | Expected |
|---|---|---|
| Hybrid ranking | Có ưu tiên keyword/vector nhưng chưa phải rank fusion thực sự | BM25 và dense có rank riêng, fusion RRF deterministic |
| Retrieval audit | Chủ yếu ghi hits sau cùng | Ghi candidate pool, filtered candidates/reasons và fusion scores |
| Evidence selection | Lọc candidate tương đối rộng; bảng ngành có thể kéo theo row ngành khác | Lọc verified/year/DHV/official source/category rồi bind theo entity/row |
| Multi-issue | Có route nhiều intent nhưng subquery còn mang ngữ cảnh issue khác | Mỗi issue có query/topic riêng, retrieval riêng, merge evidence dedup |
| Provenance | Chưa có boundary nhất quán cho source/domain và entity row | Chỉ chấp nhận nguồn DHV chính thức, năm đích, trường đích và evidence phù hợp |

Reproduce baseline full suite:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả baseline: **84 tests**, 1 skip và 5 lỗi hạ tầng
`TemporaryDirectory`/Chroma do quyền ghi/xóa temp trên Windows sandbox; các
assertion tests còn lại pass, không có assertion failure logic được quy cho TASK K.

## 3. Root cause

1. Retrieval chưa thực hiện BM25+dense RRF; thứ tự phụ thuộc keyword-priority và
   vector score nên audit không giải thích được đóng góp từng tín hiệu.
2. Evidence boundary chưa là một selector độc lập sau retrieval; candidate rộng có
   thể đưa bảng/row ngoài entity hoặc nguồn ngoài phạm vi vào context.
3. Multi-issue chưa tạo retrieval query thực sự độc lập và chưa có merged evidence
   trace để kiểm chứng deduplication.
4. Metadata filtering trước đó chưa đủ chặt cho status, year, institution và
   official DHV source domain.

## 4. Current → expected → result

| Case | Expected | Result |
|---|---|---|
| Hybrid retrieval | BM25 + dense + RRF, deterministic, audit được | PASS; `fusion_method=bm25+dense+rrf`, `rrf_k=60`, audit có rank/score từng hit |
| Evidence metadata | Chỉ nhận verified, năm 2026, `school_code=DHV`, category được route và URL official DHV | PASS; candidate sai bị loại với reason cụ thể |
| Entity table | CNTT/Kỹ thuật máy tính chỉ lấy row tương ứng, không kéo Tài chính/Kế toán/Luật | PASS; row boundary được cắt trước row ngành kế tiếp |
| Multi-issue | Học phí/học bổng/chương trình có 3 subquery riêng và evidence merge không trùng chunk | PASS; 3 retrieval calls, 3 query khác nhau, merged chunk IDs unique |
| ĐGNL ĐHQG-HCM | `score_source` là ĐHQG-HCM nhưng target institution vẫn là DHV | PASS; retrieval/evidence chỉ giữ tài liệu DHV |
| Tư vấn chọn ngành | Context chỉ gồm các ngành ứng viên, không lấy row unrelated | PASS; logic deterministic trước generation |

## 5. Files changed

- `src/retrieval/retriever.py`: BM25 scoring, dense rank, RRF fusion, official-DHV
  source validation và retrieval audit candidate/filter/fusion fields; giữ tương
  thích API cũ.
- `src/chatbot/evidence.py`: `EvidenceSelection`, metadata/entity/category gate,
  table-row selection, official URL validation và `merge_evidence_bundles` dedup.
- `src/chatbot/query_analysis.py`: `QueryPlan.entity_filters`, entity score source,
  và scoped subquery cho từng multi-issue.
- `src/chatbot/rag_chain.py`: gọi Evidence Selection sau retrieval, trace selection,
  retrieval audits, subqueries và merged evidence; generation nhận context đã chọn.
- `tests/test_task_k.py`: 6 regression tests cho RRF/audit, selector, provenance,
  entity row, multi-issue merge và score-source boundary.
- `reports/TASK_K_RETRIEVAL_EVIDENCE_RESULT.md`: report này.

Không sửa RAW/processed data, không import dữ liệu cũ, không đưa `reference_images/`
vào RAG KB và không thay đổi UI/source cards/URLs.

## 6. Architecture decisions

- Giữ refactor tối thiểu: `ChatService`/Streamlit API không đổi; không tạo module
  trùng chức năng.
- Retrieval trả về audit có candidate pool, filtered reasons và fusion metadata;
  Evidence Selection vẫn là boundary bắt buộc trước `build_evidence`/generation.
- RRF dùng hai ranking độc lập BM25 và dense với hằng số `k=60`; tie-break deterministic
  theo BM25 rank, dense rank, vector score và identity.
- Selector chỉ chấp nhận nguồn HTTP(S) có host `dhv.edu.vn`, `www.dhv.edu.vn` hoặc
  subdomain của `dhv.edu.vn`; reject credentials/non-official host.
- Entity-specific table được cắt từ chunk verified hiện có, giữ nguyên metadata và
  provenance; không tạo fact mới.
- Mỗi subquery multi-issue chỉ mang entity anchors + một topic label + target year.
  Evidence được merge bằng `chunk_id`/text fingerprint và trace đầy đủ từng selection.
- Greeting/identity/scope vẫn không qua RAG; list/count/filter/score vẫn deterministic;
  LLM không làm phép tính hoặc kết luận đậu/rớt.

## 7. Tests và kết quả

Targeted TASK K:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_k -q
```

Kết quả: **Ran 6 tests — OK**.

Related regression:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_k tests.test_task_c tests.test_task_f tests.test_task_g tests.test_task_i tests.test_task_j -q
```

Các assertion liên quan pass; lỗi chạy sandbox mặc định trước đó chỉ thuộc nhóm
temp/Chroma Windows. Full regression cuối được chạy trong môi trường temp writable:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả cuối: **Ran 90 tests in 3.334s — OK (skipped=1)**. Test skip là real Qwen
integration chưa bật `RUN_REAL_QWEN_TESTS=1`.

Kiểm tra bổ sung:

```powershell
& '.venv\Scripts\python.exe' -m compileall -q src tests
git diff --check
```

Kết quả: **compileall PASS**, **diff-check PASS**; cảnh báo còn lại chỉ là line
ending LF/CRLF của working copy.

## 8. Smoke và metrics

Smoke trên Chroma hiện tại:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m src.ingestion.smoke_test_vector_db --persist-dir .\chroma_db --collection dhv_admissions_2026 --embedding-backend ollama --embedding-model nomic-embed-text --top-k 4
& '.venv\Scripts\python.exe' -m src.ingestion.rebuild_smoke_test --persist-dir .\chroma_db --collection dhv_admissions_2026 --embedding-backend ollama --embedding-model nomic-embed-text --top-k 18
```

Kết quả: **SMOKE_PASS** cho 3 truy vấn; **REGRESSION_PASS (12 cases)**.
Audit probe cho truy vấn học phí 2026 có hit category `hoc_phi`, BM25 rank, dense
rank và RRF score dương.

Metrics kiểm thử hiện có: 6 test TASK K, 90 test full suite, 12 smoke cases, RRF
`k=60`. Chưa có gold set offline để đo Precision@k/Recall@k/MRR; vì vậy không
gán một con số retrieval-quality ngoài các regression/smoke deterministic này.

## 9. Sources/data mới, conflicts và unverified

- Không có source/data mới trong TASK K và không rebuild index vì không đổi corpus.
- Corpus hiện tại được smoke từ tài liệu 2026 có source URL thuộc DHV chính thức.
- Candidate `unverified`, sai năm, sai institution, sai category, rỗng hoặc source
  ngoài official DHV bị loại và được ghi reason trong audit/selection.
- Khi có entity-specific row, rule chung không được lấn vào context row-specific;
  đây là boundary chống trộn formula/threshold/admission/supplementary.
- Không phát hiện conflict mới cần resolve; các fact thiếu verification không được
  dùng làm evidence trả lời.

## 10. Limitations

- Chưa chạy real Qwen end-to-end; integration test vẫn skip theo cấu hình môi trường.
- Chưa tune trọng số/`k` RRF trên gold benchmark; hiện ưu tiên tính deterministic và
  auditability.
- Smoke dùng Chroma/index hiện có; không phải rebuild từ RAW vì TASK K không thay đổi
  data/ingestion.
- Các lỗi temp/Chroma xuất hiện trong sandbox mặc định là vấn đề quyền Windows đã có
  từ baseline; full regression cuối trong môi trường writable đã pass.

## 11. PASS/FAIL

**PASS** — targeted TASK K pass; full regression 90 tests pass với 1 skip đã biết;
compile/diff-check pass; smoke và 12-case retrieval regression pass; RRF/audit,
Evidence Selection, multi-issue decomposition/merge và DHV provenance invariants
được kiểm chứng; không thay đổi dữ liệu hoặc reference images.
