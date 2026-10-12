# Audit migration `data/processed` từ Markdown sang Structured JSON

Ngày audit: 2026-09-17  
Task: `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_MIGRATE_PROCESSED_MD_TO_JSON (1).md`

## Phạm vi và tài liệu đã đọc

- `00_MASTER_PLAN.md`.
- Task migration này và task OCR liên quan để kiểm tra dependency/prerequisite.
- Các module ingestion, retrieval, evidence, RAG, config và tests liên quan.
- `Tong_quan_xay_dung_chatbot_AI.pdf` để đối chiếu nguyên tắc tách extraction, structured knowledge, chunking, retrieval và evidence. PDF phương pháp không được đưa vào DHV RAG KB.

Audit chỉ xem xét generated processed data. `README.md`, task files, documentation và reports dạng Markdown không phải generated input của RAG nên không bị xóa.

## Baseline trước migration

Trước khi xóa bất kỳ dữ liệu nào, inventory cho thấy:

- `data/raw/`: 15 PDF nguồn.
- `data/processed/`: 15 Markdown generated có YAML frontmatter, chưa có JSON canonical.
- `data/processed_json/`: 15 JSON stale từ convention của task trước.
- Pipeline runtime/build còn không thống nhất: một số code/test dùng `data/processed`, trong khi build mặc định từng trỏ sang `data/processed_json` và loader còn có nhánh đọc Markdown.

Baseline logic:

```text
RAW PDF -> pypdf text -> data/processed/*.md + YAML frontmatter
         -> Markdown loader -> splitter -> LangChain Document -> ChromaDB
```

Trước khi sửa, 15 file Markdown ở `data/processed/` được backup tạm vào `data/processed_legacy/`. Backup chỉ phục vụ so sánh trong migration, không được dùng làm nguồn build và không commit.

## Audit dependency

| Thành phần | Dependency cũ | Kết quả migration |
|---|---|---|
| `src/ingestion/prepare_processed_from_raw.py` | Ghi Markdown/YAML; có output JSON ở convention khác | Ghi trực tiếp `data/processed/<category>/*.json`; không còn writer Markdown |
| `src/ingestion/loader.py` | Scan `.md`, parse frontmatter/YAML và body | Chỉ scan `.json`, bỏ `manifest.json`, parse/validate schema và tạo LangChain Documents từ records |
| `src/ingestion/build_vector_db.py` | Default path có thể lệch khỏi canonical processed | Nhận Structured JSON ở `data/processed/`; xác thực verified/year/source trước khi index |
| `src/ingestion/splitter.py` | Mô tả/suy nghĩ theo document Markdown | Chunk từ semantic records; recursive splitter chỉ là fallback trong record dài |
| `src/ingestion/rebuild_smoke_test.py` | Assert bảng Markdown cũ cho ngành/Luật | Assert record JSON, metadata và invariants semantic |
| `src/ingestion/smoke_test_vector_db.py` | Smoke trên Chroma | Không có dependency generated Markdown; giữ nguyên vai trò |
| `src/retrieval/retriever.py` | Một số truy vấn phụ thuộc text shape cũ | Dùng entity annotations và catalog JSON; list/count/filter deterministic khi có thể |
| `src/chatbot/evidence.py` | Regex/fact extraction từ chunks text | Ưu tiên metadata record JSON, giữ Evidence Selection và typed facts |
| `src/chatbot/rag_chain.py` | Retrieval top-k nhỏ có thể làm thiếu directory/overview | School info structured records được lấy đủ trong scope intent; không hard-code dữ liệu trường |
| `src/config/settings.py`, `.env.example` | `PROCESSED_JSON_DIR` song song canonical path | Chỉ còn `PROCESSED_DATA_DIR`, mặc định `data/processed` |
| `.gitignore`, `README.md` | Nhắc/cho phép convention processed cũ | Chỉ mô tả generated JSON tại `data/processed/`, vẫn giữ Markdown docs/report |
| `tests/` | Fixture/assert generated Markdown và frontmatter | Chuyển sang JSON schema, record metadata và file-count invariant; thêm migration test |

Các symbol/runtime pattern đã kiểm tra sau migration: `processed_json`, `PROCESSED_JSON_DIR`, `processed_json_dir`, `load_markdown_file`, `frontmatter`, `yaml.safe_load`, `markdown_directory`, `--markdown-dir`, `--no-markdown`, `processed_json_output`. Không còn match trong `src/`, `tests/`, `README.md`, `.env.example`, `.gitignore`.

`markdown_root` vẫn xuất hiện duy nhất như một compatibility boundary trong hàm public cũ: giá trị khác `None` bị từ chối bằng lỗi rõ ràng, không đọc/ghi Markdown. Các match `.md` còn lại thuộc task/report/test audit, không phải runtime dependency của `data/processed/**/*.md`.

## Quyết định convention và an toàn dữ liệu

Convention duy nhất sau migration:

```text
data/
├── raw/**/*.pdf
└── processed/<category>/*.json
```

Trình tự thực tế:

1. Audit dependency và kiểm tra inventory.
2. Backup tạm Markdown vào `data/processed_legacy/`.
3. Migrate loader, builder, config, retrieval/evidence assumptions và tests.
4. Generate JSON từ toàn bộ 15 RAW PDF.
5. Validate JSON.
6. Rebuild Chroma từ `data/processed/`.
7. Chạy smoke/regression và full tests.
8. Search lại dependency generated Markdown.
9. Chỉ sau đó xóa `data/processed_legacy/` và stale `data/processed_json/`.

Không xóa hoặc sửa `data/raw/**/*.pdf`; không ingest `reference_images/`; không import dữ liệu cũ vào JSON để che lỗi; không ingest PII không cần thiết.

## Kết quả sau migration

- `data/raw/`: 15 PDF, còn nguyên.
- `data/processed/`: 15 JSON, 0 `.md`.
- JSON parse: 15/15 thành công.
- Required top-level fields (`document_id`, `category`, `source`, `pages`, `records`): có mặt trên toàn bộ JSON.
- Năm dữ liệu: 2026 trên toàn bộ JSON.
- Extraction method hiện tại: `pypdf_text` trên toàn bộ JSON.
- Tổng semantic records: 97.
- Warnings khi generate: 0.
- `data/processed_legacy/`: đã xóa sau validation/regression.
- `data/processed_json/`: đã xóa sau khi xác nhận convention canonical.
- `README.md`, task files và reports Markdown: giữ nguyên.

## Chroma và runtime source

Chroma được reset/rebuild với `--data-dir data/processed`, collection `dhv_admissions_2026`, và log xác nhận:

```text
files_seen=15
verified_documents=15
metadata_errors=0
chunks_indexed=99
```

Chunk builder không embed `json.dumps(whole_document)`. Mỗi record/section domain là đơn vị semantic; major, program relation, threshold, tuition, scholarship và school directory giữ metadata riêng. Summary catalog được giữ atomic để count/list không mất dòng cuối khi split.

## OCR limitation

Task migration mô tả pipeline mục tiêu có bước OCR và acceptance yêu cầu OCR hoạt động. Repository hiện vẫn dùng `pypdf_text`; module `prepare_processed_from_raw.py` có boundary rõ để thay extractor về sau nhưng không giả nhận đây là OCR. Task OCR bắt buộc là phạm vi riêng và chưa được triển khai trong task này.

Vì vậy migration Markdown → JSON và các gate JSON/Chroma/retrieval/test đều đã hoàn thành, nhưng acceptance toàn task không thể đánh PASS khi OCR criterion còn thiếu.

## Exact audit command

```powershell
rg -n "processed_json|PROCESSED_JSON_DIR|processed_json_dir|load_markdown_file|frontmatter|yaml\.safe_load|markdown_directory|--markdown-dir|--no-markdown|processed_json_output" src tests README.md .env.example .gitignore
```

Kỳ vọng: không có output. Search `.md` toàn project vẫn có kết quả từ README, reports, task files và tests kiểm tra rằng generated Markdown không còn; đó không phải runtime dependency.
