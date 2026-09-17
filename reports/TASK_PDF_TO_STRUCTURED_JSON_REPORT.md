# TASK_PDF_TO_STRUCTURED_JSON_PIPELINE — report

## Kết luận

**PASS** — targeted tests, full regression, build Chroma và retrieval smoke/regression đều đạt; các invariant nguồn DHV, năm 2026, page traceability và semantic score còn đúng.

## Task và phạm vi

- Task: `DHV_AGENT_MASTER_PLAN_UPDATED/TASK_PDF_TO_STRUCTURED_JSON_PIPELINE.md`.
- Đã đọc: `DHV_AGENT_MASTER_PLAN_UPDATED/00_MASTER_PLAN.md`, task file, code/tests ingestion liên quan và `Tong_quan_xay_dung_chatbot_AI.pdf`.
- `Tong_quan_xay_dung_chatbot_AI.pdf` chỉ dùng để đối chiếu phương pháp RAG (metadata nguồn/trang, chunk theo cấu trúc, tách indexing khỏi retrieval); không được ingest vào DHV KB.
- Chỉ dùng corpus RAW hiện có trong `data/raw/`; không sửa PDF, `manifest.json`, dữ liệu intent hay dữ liệu cũ để che bug.

## Baseline / reproduce

Baseline trước thay đổi là:

```text
RAW PDF → pypdf extract_text() → data/processed/*.md + YAML
→ Markdown loader → splitter → Chroma
```

Baseline không có lớp object JSON, không giữ page boundary ở artifact trung gian và không có record-level chunk builder. Runtime vẫn tiêu thụ LangChain `Document`, vì vậy `ChatService`, retriever và UI không cần đổi contract.

## Root cause và current → expected

| Hạng mục | Current trước task | Expected sau task |
|---|---|---|
| Intermediate representation | Markdown phẳng | Structured JSON có schema/domain validation |
| Traceability | metadata YAML, page boundary bị flatten | `pages`, `sections`, `records` đều có `page` |
| Domain semantics | text chung | parser deterministic theo category; score/threshold/formula tách nghĩa |
| Ngành–chương trình | chưa có quan hệ parent-child | `programs[].parent_major` và `parent_major_code` |
| Indexing | chunk Markdown | record text tự nhiên + scalar metadata phẳng từ JSON |
| Tính tương thích | consumer cũ dùng Markdown | JSON là input chính; Markdown vẫn được xuất để giữ consumer cũ |

## Thay đổi chính

- `src/ingestion/structured_json.py`: owner duy nhất của structured document, parser theo category, validation và record-to-text chunk builder.
- `src/ingestion/prepare_processed_from_raw.py`: extract theo từng trang, tạo JSON trực tiếp từ RAW; Markdown chỉ là compatibility export từ cùng pages, không phải input tạo JSON.
- `src/ingestion/loader.py`: ưu tiên đọc JSON đã verified đúng năm; vẫn giữ Markdown loader/API cũ.
- `src/ingestion/build_vector_db.py`: mặc định build từ `data/processed_json`; legacy Markdown vẫn hỗ trợ khi truyền `--data-dir`.
- `src/config/settings.py`, `.env.example`, `.gitignore`, `README.md`: thêm `PROCESSED_JSON_DIR` và cập nhật hướng dẫn/pipeline.
- `src/ingestion/raw_manifest.py`: dùng chung validator official URL, tránh duplicate logic.
- `tests/test_task_pdf_to_structured_json.py`: test schema/page traceability, parser semantic, loader/index path và validation rejection.
- `reports/JSON_PIPELINE_AUDIT.md`: ghi audit baseline, ownership và boundary của extraction.

## JSON contract và validation

Mỗi file có các nhóm chính:

```text
document_id, title, category, year, data_role
source: file_name, raw_file, source_url(s), org, verified,
        verification_status/status, source_date, collected_at, school_code
extraction: method, text_source, page_count
pages[], sections[], records[], warnings[]
```

Ví dụ record ngành sau khi parse từ catalog RAW:

```json
{
  "record_type": "major",
  "major_name": "Công nghệ thông tin",
  "major_code": "7480201",
  "programs": [
    {"program_name": "Công nghệ phần mềm", "parent_major_code": "7480201"},
    {"program_name": "Lập trình AI", "parent_major_code": "7480201"}
  ],
  "threshold_type": "application_threshold",
  "thresholds": {"thpt": 15, "hoc_ba": 18, "dgnl": 600},
  "page": 1
}
```

Ví dụ tuition record giữ numeric fields riêng, không gộp vào score:

```json
{
  "record_type": "tuition",
  "semester": "Học kỳ 1",
  "credits": 10,
  "tuition_amount_vnd": 12500000,
  "admission_fee_vnd": 1500000,
  "elearning_fee_vnd": 250000,
  "english_test_fee_vnd": 250000,
  "page": 1
}
```

Validation deterministic kiểm tra: top-level bắt buộc; `year=2026`; source phải `verified=true`, status `verified`, URL HTTPS thuộc `dhv.edu.vn` hoặc subdomain; page index/page count; record page traceability; major code 7 chữ số; parent-child; numeric non-negative hoặc giữ raw `-`; URL trong record; và không cho trường score mơ hồ trộn giữa threshold, admission score, supplementary threshold, formula.

Các parser hiện có gồm: catalog ngành, ngưỡng đầu vào, điểm trúng tuyển, học phí, học bổng, website chính thức, công thức điểm, phương thức xét tuyển, đăng ký, liên hệ, hồ sơ nhập học, hình thức nhập học, lịch tuyển sinh và xét tuyển bổ sung. Parser không gọi LLM và không tự tạo fact.

## Artifact và invariant sau build

Đã regenerate từ 15 RAW PDF:

- 15 JSON document, 18 pages, 96 records, 0 warnings.
- Catalog có 20 major records và một summary record được suy ra từ chính 20 dòng ngành để hỗ trợ query count deterministic; không hard-code ngành riêng.
- Quan hệ CNTT (mã `7480201`) giữ đủ 5 chương trình con và parent code/name.
- Threshold CNTT giữ các giá trị `15`, `18`, `600` với `score_type=application_threshold`.
- Admission score dùng `score_type=admission_score`, giữ `20,0` thành numeric `20.0` và raw value; không trộn với threshold.
- Tuition giữ numeric VND: `12.500.000`, phí xét tuyển `1.500.000`, tổng `14.500.000` theo RAW; scholarship và supplementary là category/record riêng.
- Tất cả source hosts được kiểm tra đều là `dhv.edu.vn` hoặc subdomain; không có source ngoài domain official.
- Chroma rebuild từ JSON: 99 indexed chunks, collection `dhv_admissions_2026`, embedding `ollama/nomic-embed-text`.
- JSON không được đưa nguyên khối vào embedding; chunk content là natural-language record text, metadata Chroma chỉ flatten scalar fields.

## Tests và kết quả

Targeted:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_task_pdf_to_structured_json tests.test_ingestion tests.test_task_m tests.test_task_09
```

Kết quả: **Ran 21 tests in 1.889s — OK**.

Full regression:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py'
```

Kết quả: **Ran 137 tests in 10.485s — OK (skipped=1)**.

Data/retrieval rebuild và smoke:

```powershell
.\.venv\Scripts\python.exe -m src.ingestion.prepare_processed_from_raw
.\.venv\Scripts\python.exe -m src.ingestion.build_vector_db --reset
.\.venv\Scripts\python.exe -m src.ingestion.smoke_test_vector_db --embedding-backend ollama --embedding-model nomic-embed-text --top-k 4
.\.venv\Scripts\python.exe -m src.ingestion.rebuild_smoke_test --embedding-backend ollama --embedding-model nomic-embed-text --top-k 25
```

Kết quả: **SMOKE_PASS** và **REGRESSION_PASS (13 cases)**. Các nhóm đã smoke gồm học phí, học bổng, nhập học và thông tin trường; regression bao gồm count ngành, mã/ngành/chương trình CNTT, threshold/admission score của Luật và Tâm lý học, học phí, hạn bổ sung và câu hỏi tư vấn ngành.

## Metrics

Đo trên máy hiện tại, corpus 15 PDF và Ollama local:

| Stage | Thời gian |
|---|---:|
| RAW → Structured JSON + compatibility Markdown | 0.496 s |
| JSON → Chroma rebuild (`--reset`) | 14.443 s |
| Retrieval smoke 4 query | 10.287 s |
| Retrieval regression 13 query | 10.135 s |

Thời gian embedding phụ thuộc Ollama/model/local hardware; đây không phải SLA cố định.

## Sources, data mới, conflicts / unverified

- Nguồn factual duy nhất của generated artifact là 15 PDF trong `data/raw/`, có provenance từ `data/raw/manifest.json`; các URL đều official DHV.
- Không thêm source web mới, không import dữ liệu cũ vào 2026, không ingest PII không cần thiết.
- `Tong_quan_xay_dung_chatbot_AI.pdf` không phải nguồn DHV và không được đưa vào JSON/Chroma.
- Các giá trị RAW hiển thị là `-` vẫn được giữ raw, không suy diễn thành số 0 hoặc ngưỡng mặc định. Những field thiếu/không xác minh tiếp tục nằm trong giới hạn của RAW và được audit bằng validation.

## Limitations

- Extraction hiện tại là `pypdf_text` từ text layer. OCR và fallback cho scanned/image-only PDF thuộc task OCR riêng, chưa được giả nhận là đã hoàn tất; PDF không extract được text sẽ fail rõ ràng thay vì sinh JSON rỗng.
- Parser deterministic được mở rộng cho các category đang có trong corpus; category văn bản chưa có bảng/domain record vẫn giữ một `document_text` record có page traceability, không bịa cấu trúc.
- `.venv` hiện không có `pytest`; regression canonical của repository là `unittest`, đã chạy full và targeted thành công.

## Final status

**PASS** — targeted 21/21, full regression 137/137 (1 skipped), JSON rebuild 15/15, Chroma rebuild thành công, smoke PASS, retrieval regression 13/13; invariants bắt buộc còn đúng.

STATUS: PASS
