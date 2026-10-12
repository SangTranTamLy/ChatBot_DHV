# TASK J — Score Intent + Deterministic Logic

Ngày: 2026-09-15  
Repository: `ChatBot_DHV`  
Kết luận: **PASS**

## 1. Task

Phân biệt bốn loại yêu cầu liên quan đến điểm:

- Công thức/cách tính điểm.
- Ngưỡng đảm bảo chất lượng đầu vào/điểm nhận hồ sơ, theo phương thức.
- Điểm trúng tuyển/điểm chuẩn.
- Ngưỡng hoặc điều kiện của đợt xét tuyển bổ sung.

Các câu hồi quy bắt buộc:

1. `Cách tính điểm xét tuyển học bạ ngành Luật?`
2. `Điểm xét tuyển học bạ ngành Luật bao nhiêu?`
3. `Ngành Luật xét học bạ bao nhiêu điểm?`
4. `Luật học bạ lấy bao nhiêu?`
5. `Điểm chuẩn ngành Luật năm 2026 bao nhiêu?`
6. `Ngành Luật xét bổ sung bao nhiêu điểm?`

## 2. Baseline và reproduce

Baseline intent probe trước khi sửa:

| Câu hỏi | Baseline |
|---|---|
| Cách tính điểm xét tuyển học bạ ngành Luật? | `HOI_CACH_TINH_DIEM` |
| Điểm xét tuyển học bạ ngành Luật bao nhiêu? | Bị gán nhầm `HOI_CACH_TINH_DIEM` |
| Ngành Luật xét học bạ bao nhiêu điểm? | `HOI_NGUONG_DAU_VAO`, nhưng score type chưa được gắn rõ |
| Luật học bạ lấy bao nhiêu? | Bị rơi về `HOI_NGANH` |
| Điểm chuẩn ngành Luật năm 2026 bao nhiêu? | `HOI_DIEM_TRUNG_TUYEN` |
| Ngành Luật xét bổ sung bao nhiêu điểm? | Bị rơi về `HOI_NGUONG_DAU_VAO` |

Full suite baseline chạy trong sandbox mặc định có 80 tests, 5 lỗi teardown/quyền
Windows ở `TemporaryDirectory`/Chroma; không có assertion failure của Task J vì
chưa có test Task J riêng.

## 3. Root cause

1. Rule `diem xet tuyen` được coi trực tiếp là câu hỏi công thức, dù có thể là
   yêu cầu một ngưỡng theo phương thức học bạ.
2. `score_type` được suy ra chưa đủ từ các mẫu tự nhiên như `học bạ lấy bao nhiêu`
   và `xét bổ sung`.
3. Nhánh entity ngành chạy trước score-type fallback, nên câu hỏi có tên Luật
   nhưng không có cụm `bao nhiêu điểm` bị phân loại thành `HOI_NGANH`.
4. Structured score facts chưa mang provenance `verified` rõ ràng; Score Engine chỉ
   so sánh số đầu tiên tìm được.
5. Entity-specific facts có thể bị trộn với rule chung hoặc với điểm trúng tuyển/
   bổ sung khi adapter trả về context rộng hơn category filter.

## 4. Current → expected → result

| Case | Expected | Result |
|---|---|---|
| Câu 1 | `HOI_CACH_TINH_DIEM`, category `cach_tinh_diem`, method `hoc_ba` | PASS |
| Câu 2 | `HOI_NGUONG_DAU_VAO`, `application_threshold`, method `hoc_ba`, category `nganh_dao_tao` | PASS; thiếu rule Luật → `no_data` |
| Câu 3 | Như câu 2 | PASS; không lấy ngưỡng chung 18 |
| Câu 4 | Như câu 2 | PASS; không còn `HOI_NGANH` |
| Câu 5 | `HOI_DIEM_TRUNG_TUYEN`, `admission_score`, category `diem_trung_tuyen` | PASS; lấy 20,0 đúng nguồn |
| Câu 6 | `HOI_XET_TUYEN_BO_SUNG`, `supplementary_threshold`, category `xet_tuyen_bo_sung` | PASS; không dùng dữ liệu initial |

Với các câu hỏi giá trị điểm, Score Engine chỉ cho phép rule có `status=verified`
và value số. Rule thiếu value, dấu `-`, hoặc không có entity/method mapping trả
trạng thái `insufficient-data`. Kết quả so sánh chỉ diễn đạt đạt/vượt ngưỡng nhận
hồ sơ; không kết luận đậu/trượt.

## 5. Files changed

- `src/chatbot/query_analysis.py`: thêm nhận diện formula/value request, marker bổ
  sung, score type theo method; thêm `deterministic_score_evaluation`; chỉ dùng
  specific row khi đã có row của entity, nếu không mới fallback rule chung.
- `src/chatbot/evidence.py`: gắn `status/source_status/year` vào structured facts;
  parse rule bổ sung theo method và giữ riêng ngoại lệ Luật.
- `src/chatbot/rag_chain.py`: lọc category sau single-plan retrieval; short-circuit
  `insufficient-data`; ghi `score_engine` vào trace.
- `src/chatbot/output_validator.py`: score mapping/date chỉ xét facts verified.
- `src/retrieval/retriever.py`: đồng bộ marker `xét bổ sung` và phân biệt category
  formula/threshold.
- `src/prompts/rag_prompt.py`: cấm lấy rule chung, điểm trúng tuyển hoặc điểm bổ
  sung để điền vào rule entity-specific thiếu dữ liệu.
- `tests/test_task_j.py`: 4 regression tests cho sáu câu bắt buộc, thiếu ngưỡng
  học bạ Luật, verified-only comparison và rule bổ sung riêng.
- `reports/TASK_J_SCORE_INTENT_RESULT.md`: report này.

Không sửa RAW/processed data, không import dữ liệu cũ, không đưa reference image
vào KB và không rebuild Chroma vì Task J chỉ thay đổi logic/provenance/retrieval
boundary, không thay đổi nguồn dữ liệu.

## 6. Architecture decisions

- Giữ ownership score logic trong `query_analysis.py`, không tạo module trùng chức
  năng và giữ tương thích API `ChatService`/Streamlit.
- `deterministic_score_evaluation` là lớp kiểm tra rule trước generation; LLM không
  tính điểm và không quyết định đậu/trượt.
- Formula chỉ được nhận diện bởi marker tính/quy đổi/công thức. Cụm hỏi một con số
  theo `học bạ` được route thành application threshold.
- Khi có row specific của ngành, kể cả row chứa `-`, không được fallback sang rule
  chung. Đây là điều kiện ngăn trả 18 cho học bạ Luật.
- Category filter được áp dụng sau adapter cho cả single-plan và multi-issue; vì vậy
  context formula không nhìn thấy admission score, và initial không nhìn thấy
  supplementary nếu adapter trả rộng hơn filter.
- Facts vẫn giữ provenance tối thiểu cần cho kiểm tra verified; không đưa URL vào
  structured score facts/prompt.

## 7. Tests và kết quả

Targeted Task J:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest tests.test_task_j -v
```

Kết quả: **4 tests, OK**.

Related regression sau sửa:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest tests.test_task_j tests.test_task_c tests.test_task_f tests.test_task_g tests.test_task_i tests.test_intent_classifier -q
```

Kết quả assertion: pass; sandbox mặc định vẫn có 2 lỗi teardown quyền Windows ở
nhóm Chroma/TemporaryDirectory.

Compile và whitespace:

```powershell
git diff --check
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Kết quả: **PASS**.

Full regression cuối với temp writable trong workspace:

```powershell
New-Item -ItemType Directory -Force -Path .\tmp\task-j-test-temp-final | Out-Null
$env:TEMP=(Join-Path (Get-Location) 'tmp\task-j-test-temp-final')
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

Kết quả: **Ran 84 tests in 4.663s — OK (skipped=1)**. Test skip là real Qwen
integration vì chưa bật `RUN_REAL_QWEN_TESTS=1`.

## 8. Smoke và metrics

Smoke với corpus processed hiện tại, dùng retriever double trả context rộng, xác
nhận:

- 6/6 câu bắt buộc được route đúng intent/category.
- Công thức chỉ nhận category `cach_tinh_diem`.
- Ba câu học bạ Luật trả `no_data`, không gọi LLM và không xuất 18/20 từ nguồn
  khác.
- Điểm chuẩn Luật trả 20,0 từ category `diem_trung_tuyen`.
- Rule bổ sung THPT Luật được parse là 20; học bạ Luật được giữ là `điều kiện
  riêng` không có value số, nên câu hỏi tổng quát thiếu mapping trả `no_data`.
- Verified-only score comparison: 1 comparison hợp lệ, không nhận rule từ document
  `unverified`.

Không có thay đổi data nên không rebuild index; full suite đã chạy smoke trên
processed corpus trong các test ingestion/retrieval hiện có.

## 9. Sources/data mới, conflicts và unverified

- Không có source/data mới trong Task J.
- `data/processed/nganh_dao_tao/...`: dòng Luật và Luật Kinh tế đang giữ `-` cho
  các ngưỡng initial; không suy ra 18 từ rule chung.
- `data/processed/nguong_dau_vao/diem_san_2026.md`: ngưỡng chung học bạ 18 chỉ áp
  dụng khi evidence không có row specific phủ định/thiếu giá trị của ngành.
- `data/processed/diem_trung_tuyen/...`: Luật 20,0 là admission score, không thay
  cho application threshold.
- `data/processed/xet_tuyen_bo_sung/...`: Luật/Luật Kinh tế THPT bổ sung từ 20;
  học bạ có điều kiện riêng chưa có giá trị số. Không dùng hai rule này cho initial.
- Tất cả facts được Score Engine chấp nhận phải có provenance verified; facts thiếu
  verified hoặc thiếu value không được so sánh.

## 10. Limitations

- Câu hỏi bổ sung tổng quát về Luật hiện trả `no_data` nếu cần đồng thời một rule
  học bạ nhưng nguồn chỉ ghi “điều kiện riêng” chưa có số; đây là chủ ý an toàn.
- Chưa chạy real Qwen/Ollama vì integration test đang skip theo cấu hình môi trường.
- Full regression cần temp path writable trên Windows để tránh lỗi teardown quyền đã
  có từ baseline.
- Root không có file `00_MASTER_PLAN.md`; task được đối chiếu với bản trong
  `DHV_AGENT_MASTER_PLAN_UPDATED/00_MASTER_PLAN.md`.

## 11. PASS/FAIL

**PASS** — targeted Task J pass; full regression pass; compile và diff check pass;
score intent đúng; formula/threshold/admission/supplementary không trộn; verified
only; thiếu rule trả `insufficient-data`; Score Engine không kết luận đậu/trượt;
không thay đổi data/KB hoặc reference images.
