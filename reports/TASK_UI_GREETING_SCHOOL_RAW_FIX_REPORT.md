# Báo cáo TASK_FIX_UI_GREETING_AND_EXPAND_SCHOOL_RAW

## 1. Task và kết luận

- Task: `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_FIX_UI_GREETING_AND_EXPAND_SCHOOL_RAW.md`
- Ngày kiểm tra: 2026-09-16
- Kết luận: **PASS**

Đã xử lý đúng phạm vi: làm phẳng message UI, thay greeting mặc định, mở rộng RAW trường bằng directory website chính thức đã audit, rebuild pipeline và kiểm tra retrieval/UI.

## 2. Baseline / reproduce và root cause

Baseline hiện có đạt 23/23, nhưng acceptance checks mới tái hiện: selector CSS của user còn tạo bubble; greeting là bản cũ; RAW trường chưa có directory; website query có thể trả nhiều URL hoặc bị `out_of_scope`. Với RAW mới, directory chunks cũng có thể nằm ngoài `top_k=4`, làm câu hỏi IPIC/đào tạo từ xa rơi về overview chung.

Root cause:

1. `app.py` có CSS riêng cho user với border, radius và nền màu.
2. Greeting hard-code chưa theo exact contract của task.
3. Website fallback chưa chọn deterministic theo đơn vị/cổng được hỏi; “cổng thông tin đào tạo” chưa được nhận diện là website request.
4. RAW chưa có hệ sinh thái website và retrieval chưa có top-k override có điều kiện cho directory.

## 3. Current → expected

| Hạng mục | Trước | Sau |
|---|---|---|
| User/assistant | Có nền/border/radius dạng bubble | Nền trong suốt, không border/card/bubble; avatar vẫn giữ |
| Greeting | Văn bản cũ | Đúng nguyên văn và 3 bullet yêu cầu |
| Suggestions | Backend `related_questions` còn tồn tại | Không render pill/chip/suggestion; giữ field để tương thích |
| Website answer | Có thể trả nhiều URL/URL sai mục tiêu | Chỉ URL verified đúng request; chỉ direct website query được hiển thị URL |
| School RAW | Chưa có directory | Có section `HỆ SINH THÁI WEBSITE CHÍNH THỨC CỦA DHV` |
| Directory retrieval | Có thể thiếu chunk directory trong top-k | Override top-k chỉ cho school-directory, vẫn qua Evidence Selection |

## 4. Files changed / artifacts

- `app.py`: flat message CSS, exact greeting, conditional verified-URL rendering.
- `README.md`: ghi rõ không có source card/URL tự động; direct website query có thể hiện URL verified.
- `src/chatbot/query_analysis.py`: website directory, IPIC và đào tạo từ xa.
- `src/chatbot/scope_guard.py`: allowlist câu hỏi directory trong phạm vi DHV.
- `src/chatbot/rag_chain.py`: deterministic directory mapping, existence answer có evidence, chọn URL đúng đơn vị.
- `src/retrieval/retriever.py`: optional `top_k` override, giữ contract cũ.
- `tests/test_app.py`, `tests/test_task_09.py`: acceptance tests cho greeting/CSS/RAW/routing/URL boundary.
- `data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf`: PDF RAW mới.
- `data/raw/manifest.json`, processed Markdown và `chroma_db`: sinh lại từ pipeline.
- `reports/screenshots/ui_final/`: năm ảnh smoke UI.

## 5. Architecture decisions và invariants

- Greeting/identity/scope deterministic, không RAG/LLM.
- Website target và URL được chọn bằng Python từ directory verified; LLM không tạo URL, tính điểm hay tạo fact.
- URL chỉ được giữ trong answer khi trace xác nhận direct website request; existence question về IPIC/đào tạo từ xa không tự lộ URL.
- Directory query vẫn qua Evidence Selection; top-k mở rộng chỉ áp dụng cho school-directory, không đổi retrieval thường.
- Không ingest form field/PII không cần thiết; không dùng `reference_images/` làm data/prompt/CSS/layout/RAG.
- Không trộn formula/threshold/admission/supplementary/scholarship; conflict cũ tiếp tục ở `reports/DATA_CONFLICTS_2026.md`.

## 6. Official source audit / data mới

Audit ngày 2026-09-16 chỉ dùng [website chính thức DHV](https://dhv.edu.vn/) và [cổng tuyển sinh DHV](https://tuyensinh.dhv.edu.vn/). Các URL đơn vị dưới đây là link trực tiếp đã thấy trên official pages; không đoán URL cho đơn vị không có link trực tiếp.

Directory bắt buộc trong PDF:

- `https://dhv.edu.vn/`
- `https://tuyensinh.dhv.edu.vn/`
- `https://ipic.dhv.edu.vn/`
- `https://epdl.dhv.edu.vn/`
- `https://heal.dhv.edu.vn/`
- `https://tec.dhv.edu.vn/`
- `https://fba.dhv.edu.vn/`
- `https://bam.dhv.edu.vn/`
- `https://lan.dhv.edu.vn/`
- `https://host.dhv.edu.vn/`
- `https://online.dhv.edu.vn/`

URL bổ sung do official audit trực tiếp xác nhận:

- `https://law.dhv.edu.vn/`, `https://iatai.dhv.edu.vn/`, `https://core.dhv.edu.vn/`
- `https://tek.dhv.edu.vn/`, `https://thuvien.dhv.edu.vn/`, `https://tapchikhoahoc.dhv.edu.vn/`

Kết quả pipeline: 15/15 raw PDF verified; `raw_pdfs=15 processed_documents=15`; Chroma `files_seen=15 verified_documents=15 metadata_errors=0 chunks_indexed=29`. Dữ liệu “đào tạo từ xa” chỉ xác nhận directory EPDL, không suy diễn chương trình/điều kiện/thủ tục.

## 7. Tests và metrics

Targeted suite:

```text
Ran 74 tests in 5.465s
OK
```

Full regression:

```text
Ran 133 tests in 9.300s
OK (skipped=1)
```

Skip duy nhất là Qwen integration cần `RUN_REAL_QWEN_TESTS=1`; không phải failure.

Kiểm tra bổ sung:

- `smoke_test_vector_db --top-k 4`: `SMOKE_PASS`.
- `rebuild_smoke_test --top-k 29`: `REGRESSION_PASS (13 cases)`.
- Website smoke: 9/9 câu hỏi bắt buộc `status=ok`; 7 URL direct chọn đúng duy nhất; 2 existence query không lộ URL.
- `python -m compileall -q src tests`: pass; `git diff --check`: pass.

Ảnh đã render và visual-QA:

- [greeting.png](<C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/screenshots/ui_final/greeting.png>)
- [normal_user_assistant.png](<C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/screenshots/ui_final/normal_user_assistant.png>)
- [list.png](<C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/screenshots/ui_final/list.png>)
- [table.png](<C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/screenshots/ui_final/table.png>)
- [website.png](<C:/Users/Sang/OneDrive/Desktop/ChatBot_DHV/reports/screenshots/ui_final/website.png>)

Visual check xác nhận greeting đúng; user/assistant không có background/border/card; list là list; table là vùng duy nhất có border; website answer hiển thị URL verified, không có source card tự động.

## 8. Exact reproduce commands

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.venv\Scripts\python.exe -m src.ingestion.raw_manifest --audited-at 2026-09-16
.venv\Scripts\python.exe -m src.ingestion.prepare_processed_from_raw
.venv\Scripts\python.exe -m src.ingestion.build_vector_db --embedding-backend ollama --embedding-model nomic-embed-text --reset
.venv\Scripts\python.exe -m src.ingestion.smoke_test_vector_db --top-k 4
.venv\Scripts\python.exe -m src.ingestion.rebuild_smoke_test --top-k 29
.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

```powershell
$taskTemp = Join-Path (Get-Location) 'tmp\test_temp_final'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
.venv\Scripts\python.exe -m unittest tests.test_app tests.test_task_09 tests.test_task_c tests.test_task_f tests.test_task_i tests.test_task_l tests.test_task_m -v
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

## 9. Conflicts, unverified items và limitations

- Không có URL ngoài policy official hoặc PII không cần thiết được ingest.
- Không có URL guessed cho unit không có direct link trong audit.
- Không có conflict mới; conflict cũ được ghi ở `reports/DATA_CONFLICTS_2026.md`.
- Website có thể thay đổi sau ngày audit; directory phải re-verify khi cập nhật source.
- Entry directory chỉ là name/type/URL/purpose tổng quát; không suy diễn ngành, điều kiện hoặc thủ tục.

## 10. Final status

**PASS** — targeted tests, full regression, rebuild/smoke và UI visual-QA đều pass; invariants của task còn đúng.
