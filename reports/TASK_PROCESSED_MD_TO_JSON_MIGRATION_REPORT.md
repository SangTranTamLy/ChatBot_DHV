# TASK_MIGRATE_PROCESSED_MD_TO_JSON — Final report

## 1. Kết luận

**FAIL ở acceptance toàn task; PASS ở phần migration Markdown → Structured JSON.**

Lý do duy nhất khiến task tổng thể chưa PASS là acceptance bắt buộc **OCR pipeline hoạt động**, trong khi repository hiện vẫn trích xuất text layer bằng `pypdf_text`. OCR là task riêng đã được nhận diện nhưng chưa triển khai; không thực hiện lấn sang task đó và không ghi nhận `pypdf_text` như OCR.

Các gate còn lại của migration đã đạt: toàn bộ RAW được xử lý, JSON hợp lệ, Chroma rebuild từ JSON, retrieval regression pass, full regression pass, và không còn runtime dependency vào generated Markdown.

## 2. Task và phạm vi

- Task: `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_MIGRATE_PROCESSED_MD_TO_JSON (1).md`.
- Đã đọc master plan, task file, code/tests liên quan và `Tong_quan_xay_dung_chatbot_AI.pdf` để đối chiếu phương pháp pipeline. PDF phương pháp không được ingest vào RAG KB.
- Chỉ xử lý migration processed data và các consumer trực tiếp; không tự nhảy sang triển khai OCR task riêng.

## 3. Baseline / root cause

Baseline trước sửa:

```text
RAW PDF -> pypdf extract_text() -> data/processed/*.md + YAML frontmatter
         -> Markdown loader -> splitter -> ChromaDB
```

Đồng thời tồn tại 15 JSON stale ở `data/processed_json/`, tạo ra hai convention output. Root cause là intermediate representation và consumer không có một contract duy nhất: producer ghi Markdown ở canonical path, loader còn parse Markdown/YAML, build default lệch path, còn tests/smoke giữ giả định bảng Markdown.

## 4. Current → expected

| Hạng mục | Current trước task | Kết quả sau migration |
|---|---|---|
| Canonical processed path | `data/processed/` chứa Markdown; `data/processed_json/` chứa JSON stale | Chỉ `data/processed/**/*.json` |
| Loader | Scan `.md`, parse YAML/frontmatter | Scan JSON, validate schema, tạo record documents |
| Chunking | Split document Markdown | Chunk theo record/section/major/program/rule; splitter chỉ fallback trong record dài |
| Metadata | Frontmatter và text shape cũ | Metadata scalar từ JSON, page traceability, typed record facts |
| Retrieval/evidence | Có assumptions theo Markdown/table | Evidence Selection và deterministic list/count/filter/score vẫn giữ; dùng metadata JSON |
| OCR | Chưa có | **Chưa đạt**; hiện artifact ghi rõ `pypdf_text` |

## 5. Files/functions đã migrate

- `src/ingestion/prepare_processed_from_raw.py`: output JSON canonical; bỏ writer/converter Markdown và legacy `processed_json` output; giữ compatibility argument `markdown_root` nhưng từ chối path khác `None`.
- `src/ingestion/loader.py`: bỏ Markdown/YAML loader; chỉ load verified Structured JSON.
- `src/ingestion/structured_json.py`: record-level semantic chunk text, scalar metadata, program parent relation, major catalog summary atomic, scholarship summary và typed score/threshold/tuition records.
- `src/ingestion/build_vector_db.py`: build từ JSON canonical, validation trước index.
- `src/ingestion/splitter.py`: cập nhật contract cho semantic records.
- `src/ingestion/rebuild_smoke_test.py`: chuyển predicate regression từ Markdown table sang JSON records.
- `src/retrieval/retriever.py`: entity annotations và catalog/list retrieval phù hợp structured records; hybrid fallback có audit.
- `src/chatbot/evidence.py`: extract facts từ JSON metadata, giữ Evidence Selection và cap context an toàn.
- `src/chatbot/rag_chain.py`: school-info structured retrieval đủ records; không hard-code fact DHV.
- `src/config/settings.py`, `.env.example`, `.gitignore`, `README.md`: một convention `data/processed/` và generated JSON.
- `tests/test_ingestion.py`, `tests/test_task_09.py`, `tests/test_task_m.py`, `tests/test_task_pdf_to_structured_json.py`: chuyển fixture/assert sang JSON.
- `tests/test_task_processed_md_to_json_migration.py`: test mới cho RAW count → JSON count, schema, UTF-8, official source/year và không generated Markdown.

Dead code đã loại bỏ: Markdown writer/converter, Markdown processed loader, frontmatter/YAML parser chỉ dành cho generated processed docs, `processed_json` config/default, và các cờ CLI Markdown. Compatibility guard không tạo dependency runtime và fail-loud nếu caller cố yêu cầu output Markdown.

## 6. Directory structure mới

```text
data/
├── raw/**/*.pdf
└── processed/
    ├── cach_tinh_diem/*.json
    ├── co_so_lien_he/*.json
    ├── hoc_bong/*.json
    ├── hoc_phi/*.json
    ├── nganh_dao_tao/*.json
    ├── thong_tin_truong/*.json
    └── ...
```

`data/processed/` vẫn được dùng và là canonical input cho loader/build. Chỉ generated Markdown cũ không còn dùng. `data/processed_legacy/` và `data/processed_json/` đã được xóa sau khi kiểm tra; RAW PDF không bị xóa.

## 7. JSON generation và validation

Kết quả generate từ toàn bộ RAW:

```text
raw_pdfs=15
success=15
failed=0
records=97
warnings=0
processed_json=15
processed_md=0
```

Validation read-only sau build:

```text
valid_utf8_and_json=15/15
required_fields_errors=0
years={2026}
extraction_methods={pypdf_text}
```

Invariants domain còn đúng: source URLs chính thức DHV/subdomain, status verified, page traceability, record metadata tách khỏi formula/threshold/admission/supplementary/scholarship, major/program parent relation và không ingest reference images/PII không cần thiết.

## 8. Chroma rebuild

Chroma đã rebuild từ JSON mới, không đọc Markdown:

```text
files_seen=15
verified_documents=15
metadata_errors=0
chunks_indexed=99
collection=dhv_admissions_2026
```

Semantic chunks được tạo từ records, không dùng `json.dumps(whole_document)` làm một chunk lớn.

## 9. Retrieval regression

Regression 13 case đạt `REGRESSION_PASS (13 cases)`, gồm các nhóm:

- count/list ngành;
- chương trình thuộc ngành và số lượng chương trình;
- học phí;
- điều kiện học bổng;
- điểm sàn và điểm chuẩn;
- website tuyển sinh;
- thông tin trường.

Vector smoke đạt `SMOKE_PASS`.

## 10. Tests

Targeted command:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_task_processed_md_to_json_migration tests.test_task_pdf_to_structured_json tests.test_ingestion tests.test_task_f tests.test_task_g tests.test_task_k tests.test_task_response_ui
```

Kết quả: `Ran 67 tests ... OK`.

Full regression command:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Kết quả cuối: `Ran 140 tests ... OK (skipped=1)`.

Các test cần thư mục tạm được chạy trong môi trường được phê duyệt vì Windows ACL của sandbox chặn một số `TemporaryDirectory`; đây là giới hạn môi trường chạy, không phải test failure.

## 11. Dependency search sau migration

Đã chạy:

```powershell
rg -n "processed_json|PROCESSED_JSON_DIR|processed_json_dir|load_markdown_file|frontmatter|yaml\.safe_load|markdown_directory|--markdown-dir|--no-markdown|processed_json_output" src tests README.md .env.example .gitignore
```

Kết quả: không có match. Các `.md` còn lại trong repository chỉ là README, task/documentation, reports hoặc test audit; không có runtime/ingestion dependency tới `data/processed/**/*.md`.

## 12. Sources, data mới, conflicts và unverified items

- Không thêm nguồn web/PDF ngoài corpus hiện có trong `data/raw/`.
- Không dùng `reference_images/` làm dữ liệu, source hoặc RAG KB.
- Không import 15 JSON stale từ `data/processed_json/`; JSON canonical được generate lại từ RAW.
- Không xóa RAW PDF.
- Các conflict đã có trong `reports/DATA_CONFLICTS_2026.md` không được tự giải quyết trong task này.
- Unverified/limitation chính: OCR chưa active; mọi JSON hiện ghi `extraction.method=pypdf_text`, nên PDF scan/image-only có thể chưa được trích xuất đầy đủ.

## 13. Exact reproduce commands

```powershell
.venv\Scripts\python.exe -m src.ingestion.prepare_processed_from_raw --log-level INFO
.venv\Scripts\python.exe -m src.ingestion.build_vector_db --data-dir data/processed --persist-dir chroma_db --collection dhv_admissions_2026 --embedding-backend ollama --embedding-model nomic-embed-text --ollama-base-url http://localhost:11434 --reset --log-level INFO
.venv\Scripts\python.exe -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text --ollama-base-url http://localhost:11434 --persist-dir chroma_db --collection dhv_admissions_2026 --top-k 25
.venv\Scripts\python.exe -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text --ollama-base-url http://localhost:11434 --persist-dir chroma_db --collection dhv_admissions_2026 --top-k 25
.venv\Scripts\python.exe -m unittest tests.test_task_processed_md_to_json_migration tests.test_task_pdf_to_structured_json tests.test_ingestion tests.test_task_f tests.test_task_g tests.test_task_k tests.test_task_response_ui
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

## 14. Limitations

1. OCR mandatory criterion remains unimplemented and must be handled by the separate OCR task before this migration can be promoted from conditional FAIL to full PASS.
2. `markdown_root` remains in the public function signature only as a fail-loud compatibility boundary; it cannot write Markdown.
3. One existing full-regression test is skipped; no test was deleted or weakened to obtain the result.

## 15. Status

Migration JSON-only: PASS.  
Task acceptance including OCR: FAIL.

STATUS: FAIL
