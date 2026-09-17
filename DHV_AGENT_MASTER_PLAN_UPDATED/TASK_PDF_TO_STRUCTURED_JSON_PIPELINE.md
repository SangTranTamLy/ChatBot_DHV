# TASK: REFACTOR PIPELINE PDF → STRUCTURED JSON → CHUNK → EMBEDDING → CHROMADB

## MỤC TIÊU

Refactor pipeline ingestion của project Chatbot tuyển sinh Trường Đại học Hùng Vương TP. Hồ Chí Minh để tạo một lớp dữ liệu JSON có cấu trúc giữa RAW PDF và Vector Database.

Mục tiêu chính:

```text
RAW PDF
↓
PDF extraction / OCR theo pipeline hiện tại
↓
Structured JSON
↓
Validation
↓
Chunk Builder
↓
Embedding
↓
ChromaDB
↓
Retriever
↓
RAG
```

JSON KHÔNG phải dữ liệu gốc.

Nguồn gốc dữ liệu vẫn là:

```text
data/raw/**/*.pdf
```

JSON là dữ liệu generated/processed để:

- giữ cấu trúc rõ hơn Markdown thuần
- lưu page / section / record / metadata
- xử lý bảng tốt hơn
- giữ quan hệ parent-child
- lọc dữ liệu deterministic dễ hơn
- kiểm tra số liệu dễ hơn
- tạo chunk chính xác hơn
- giảm việc phải parse lại text tự do ở runtime
- hỗ trợ debug và regression test

Không được hiểu:

```text
PDF → JSON
```

là chỉ biến toàn bộ PDF thành:

```json
{
  "text": "toàn bộ nội dung..."
}
```

Cách đó gần như không mang lại lợi ích cấu trúc.

Phải tạo **Structured JSON**.

---

# 1. NGUYÊN TẮC KIẾN TRÚC

Kiến trúc đích:

```text
Official PDF
↓
Extractor / OCR
↓
Normalized Page Text
↓
Document Parser
↓
Structured JSON
↓
Schema Validation
↓
Record / Section Chunking
↓
Embedding
↓
ChromaDB
```

Runtime chatbot:

```text
User Question
↓
Intent + Entity
↓
Retriever
↓
ChromaDB
↓
Evidence
↓
Answer Planner
↓
LLM
```

KHÔNG parse PDF hoặc JSON lớn ở runtime.

---

# 2. AUDIT PIPELINE HIỆN TẠI TRƯỚC KHI SỬA

Đọc toàn bộ các file ingestion liên quan, tối thiểu:

```text
src/ingestion/loader.py
src/ingestion/prepare_processed_from_raw.py
src/ingestion/build_vector_db.py
src/ingestion/splitter.py
src/ingestion/embeddings.py
src/ingestion/chroma_lifecycle.py
src/ingestion/rebuild_smoke_test.py
src/ingestion/smoke_test_vector_db.py
src/retrieval/retriever.py
src/config/settings.py
requirements.txt
```

Nếu đã có OCR implementation thì đọc toàn bộ OCR modules.

Search toàn project các keyword:

```text
extract_text
pypdf
fitz
PyMuPDF
OCR
json
markdown
yaml
Document(
metadata
page
category
source_url
```

Phải xác định:

1. PDF hiện được extract ở đâu.
2. OCR hiện có hay chưa.
3. Text normalize ở đâu.
4. Processed Markdown hiện được tạo ở đâu.
5. Metadata hiện được lưu ở đâu.
6. Chunk hiện được tạo từ Markdown hay trực tiếp từ PDF.
7. Chroma metadata hiện có field nào.
8. Có logic catalog/score nào parse Markdown bằng regex không.
9. Có code nào phụ thuộc path `data/processed/**/*.md` hay không.

Tạo:

```text
reports/JSON_PIPELINE_AUDIT.md
```

Report phải mô tả:

- pipeline hiện tại
- file/function chịu trách nhiệm
- dependency của Markdown hiện tại
- điểm cần refactor
- điểm có thể giữ nguyên
- backward compatibility cần thiết

---

# 3. KHÔNG XÓA RAW PDF

RAW PDF tiếp tục là source of truth:

```text
data/raw/
```

Không thay RAW bằng JSON.

Không commit việc sửa tay JSON rồi coi JSON là nguồn chính.

Luồng đúng:

```text
RAW PDF
↓
generate JSON
```

Nếu JSON sai:

```text
fix extractor/parser
↓
regenerate JSON
```

---

# 4. THƯ MỤC JSON MỚI

Tạo hoặc chuẩn hóa:

```text
data/processed_json/
```

Ví dụ:

```text
data/
├── raw/
│   ├── hoc_phi/
│   │   └── hoc_phi_hoc_ky_1_2026.pdf
│   ├── hoc_bong/
│   │   └── hoc_bong_2026.pdf
│   └── thong_tin_truong/
│       └── thong_tin_truong_dhv_2026.pdf
│
└── processed_json/
    ├── hoc_phi/
    │   └── hoc_phi_hoc_ky_1_2026.json
    ├── hoc_bong/
    │   └── hoc_bong_2026.json
    └── thong_tin_truong/
        └── thong_tin_truong_dhv_2026.json
```

Nếu project hiện đã dùng:

```text
data/processed/
```

thì Agent phải audit trước khi quyết định:

```text
data/processed_json/
```

hay:

```text
data/processed/
```

Không được đổi path làm vỡ project mà không update tất cả dependency.

---

# 5. JSON SCHEMA CHUNG

Mỗi PDF sinh một JSON document.

Schema nền tảng đề xuất:

```json
{
  "document_id": "hoc_phi_hoc_ky_1_2026",
  "title": "Học phí học kỳ 1 năm 2026",
  "category": "hoc_phi",
  "year": 2026,
  "source": {
    "file_name": "hoc_phi_hoc_ky_1_2026.pdf",
    "source_url": "...",
    "organization": "Trường Đại học Hùng Vương TP. Hồ Chí Minh",
    "verified": true
  },
  "extraction": {
    "method": "ocr",
    "page_count": 1
  },
  "pages": [
    {
      "page": 1,
      "text": "..."
    }
  ],
  "sections": [],
  "records": [],
  "warnings": []
}
```

Tên field có thể điều chỉnh để phù hợp code hiện tại.

Nhưng phải giữ được tối thiểu:

```text
document_id
title
category
year
source
pages
sections hoặc records
warnings
```

---

# 6. PAGE-LEVEL DATA

Không làm mất page boundary.

Ví dụ:

```json
"pages": [
  {
    "page": 1,
    "text": "..."
  },
  {
    "page": 2,
    "text": "..."
  }
]
```

Mục đích:

- audit
- debug
- citation/provenance backend
- OCR quality review
- biết record đến từ trang nào

---

# 7. SECTION-LEVEL DATA

Nếu tài liệu có heading/section rõ ràng, parse thành:

```json
"sections": [
  {
    "section_id": "sec_001",
    "heading": "Học phí học kỳ 1",
    "page_start": 1,
    "page_end": 1,
    "text": "..."
  }
]
```

Không cần ép mọi document phải có section nếu tài liệu không có cấu trúc rõ.

---

# 8. RECORD-LEVEL DATA — PHẦN QUAN TRỌNG NHẤT

Đối với dữ liệu có cấu trúc như:

- ngành
- chương trình
- điểm sàn
- điểm chuẩn
- học phí
- học bổng
- website
- cơ sở
- deadline

phải parse thành `records`.

Ví dụ ngành:

```json
{
  "record_type": "major",
  "major_name": "Công nghệ thông tin",
  "major_code": "7480201",
  "programs": [
    "Công nghệ phần mềm",
    "Lập trình AI",
    "An ninh mạng và hệ thống",
    "Truyền thông đa phương tiện",
    "Phân tích dữ liệu lớn"
  ],
  "thresholds": {
    "thpt": 15,
    "hoc_ba": 18,
    "dgnl": 600
  },
  "page": 1
}
```

Ví dụ website:

```json
{
  "record_type": "official_website",
  "unit_name": "Khoa Kỹ thuật Công nghệ",
  "unit_type": "faculty",
  "url": "https://tec.dhv.edu.vn/",
  "page": 1
}
```

Ví dụ học phí:

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

Không bắt buộc mọi category dùng cùng field.

Có thể dùng schema theo category.

---

# 9. CATEGORY-SPECIFIC PARSERS

Không dùng một parser generic duy nhất để đoán tất cả.

Tạo parser theo category hoặc strategy tương đương.

Ví dụ:

```text
parse_school_info()
parse_major_catalog()
parse_admission_threshold()
parse_admission_score()
parse_tuition()
parse_scholarship()
parse_admission_method()
parse_enrollment()
parse_schedule()
```

Có thể tổ chức bằng mapping:

```python
PARSERS = {
    "nganh_dao_tao": parse_major_catalog,
    "hoc_phi": parse_tuition,
    "hoc_bong": parse_scholarship,
    ...
}
```

Mục tiêu:

```text
category
↓
đúng parser
↓
structured records
```

Không để LLM tự parse JSON trong ingestion nếu deterministic parser làm được.

---

# 10. KHÔNG TRỘN SCORE TYPES

JSON phải tách rõ:

```text
application_threshold
admission_score
supplementary_threshold
score_formula
```

Không dùng chung field kiểu:

```json
"score": 18
```

vì dễ nhầm nghĩa.

Ví dụ:

```json
{
  "record_type": "application_threshold",
  "major_name": "Công nghệ thông tin",
  "method": "hoc_ba",
  "value": 18
}
```

và:

```json
{
  "record_type": "admission_score",
  "major_name": "Luật",
  "method": "thpt",
  "value": 20
}
```

Phải tách riêng.

---

# 11. PARENT-CHILD RELATION

JSON phải giữ quan hệ ngành → chương trình.

Ví dụ:

```json
{
  "record_type": "major",
  "major_name": "Công nghệ thông tin",
  "major_code": "7480201",
  "programs": [
    {
      "program_name": "Công nghệ phần mềm"
    },
    {
      "program_name": "Lập trình AI"
    },
    {
      "program_name": "An ninh mạng và hệ thống"
    },
    {
      "program_name": "Truyền thông đa phương tiện"
    },
    {
      "program_name": "Phân tích dữ liệu lớn"
    }
  ]
}
```

Không flatten thành:

```text
Truyền thông đa phương tiện = major độc lập
```

Regression phải bảo vệ quan hệ này.

---

# 12. RAW TEXT VẪN PHẢI ĐƯỢC GIỮ

Structured JSON không được làm mất raw extracted text.

JSON phải có:

```json
"pages": [...]
```

hoặc field raw text tương đương.

Lý do:

- structured parser có thể bỏ sót
- cần audit
- cần fallback retrieval
- cần kiểm tra OCR/extraction

---

# 13. VALIDATION LAYER

Sau khi sinh JSON phải chạy validation.

Có thể dùng:

```text
Pydantic
dataclass + custom validator
JSON Schema
```

Ưu tiên Pydantic nếu phù hợp stack hiện tại.

Validation tối thiểu:

```text
category không rỗng
document_id không rỗng
page_count hợp lệ
page index hợp lệ
major_code đúng pattern nếu có
URL đúng format nếu có
year hợp lệ
numeric fields đúng type
```

---

# 14. DOMAIN VALIDATION

Ngoài schema validation, thêm rule nghiệp vụ.

Ví dụ:

```text
major_code
→ phải là chuỗi số đúng độ dài mong đợi

threshold
→ không âm

DGNĐL/DGNL
→ không được tự đổi 600 thành 60

URL
→ phải giữ domain chính thức

program
→ phải có parent_major nếu thuộc chương trình con
```

Không tự sửa factual field nếu validation fail.

Phải ghi warning/error.

---

# 15. WARNINGS

JSON có:

```json
"warnings": []
```

Ví dụ:

```json
"warnings": [
  {
    "type": "UNVERIFIED_VALUE",
    "page": 1,
    "field": "hoc_ba_threshold",
    "message": "Không xác minh được giá trị từ nguồn."
  }
]
```

Không đưa warning nội bộ lên UI user.

Warning dùng cho:

- audit
- tests
- data review

---

# 16. OCR / PDF EXTRACTION

Task JSON không được tự ý thay đổi policy extraction hiện tại nếu OCR vừa được implement.

Nếu project đang dùng OCR mandatory:

```text
PDF
↓
OCR
↓
text
↓
JSON
```

Nếu OCR chưa được merge:

Agent phải báo rõ trạng thái.

Không được âm thầm quay lại:

```python
page.extract_text()
```

nếu requirement hiện hành của project là OCR toàn bộ PDF.

---

# 17. KHÔNG DÙNG LLM ĐỂ TẠO FACTS TRONG JSON

LLM không được:

- đoán major code
- đoán score
- đoán program relation
- suy ra URL
- tự điền field bị thiếu

Nếu parser không xác định được:

```json
"value": null
```

hoặc không tạo record.

Kèm warning nếu cần.

---

# 18. JSON → CHUNK

Không embed nguyên một JSON document khổng lồ.

Phải build chunk từ từng unit có nghĩa.

Ví dụ:

```text
major record
→ 1 chunk hoặc một nhóm chunk

tuition record
→ 1 chunk

scholarship rule
→ 1 chunk

school-info section
→ 1 chunk

website record
→ 1 chunk
```

---

# 19. CHUNK TEXT

Embedding input phải là text tự nhiên, không phải JSON dump khó đọc.

Ví dụ từ:

```json
{
  "major_name": "Công nghệ thông tin",
  "major_code": "7480201",
  "programs": [...]
}
```

build text:

```text
Ngành: Công nghệ thông tin
Mã ngành: 7480201
Các chương trình:
- Công nghệ phần mềm
- Lập trình AI
- An ninh mạng và hệ thống
- Truyền thông đa phương tiện
- Phân tích dữ liệu lớn
```

Metadata giữ structured fields.

---

# 20. CHROMA METADATA

Chunk đưa vào Chroma nên có metadata tối thiểu:

```json
{
  "document_id": "...",
  "category": "nganh_dao_tao",
  "record_type": "major",
  "major_name": "Công nghệ thông tin",
  "major_code": "7480201",
  "year": 2026,
  "page": 1,
  "source_file": "...",
  "source_url": "..."
}
```

Không nhét nested dict/list phức tạp vào Chroma nếu backend metadata không hỗ trợ.

Flatten metadata cần thiết.

---

# 21. RETRIEVAL FILTER

Sau khi có structured metadata, tận dụng filter khi phù hợp.

Ví dụ:

```text
intent = TUITION
↓
ưu tiên category = hoc_phi
```

```text
intent = SCHOOL_INFO
↓
ưu tiên category = thong_tin_truong
```

```text
entity = Công nghệ thông tin
↓
ưu tiên major_name = Công nghệ thông tin
```

Không hard-filter quá mạnh đến mức mất recall.

Nếu hybrid retrieval hiện tại dùng BM25 + Dense + RRF:
- giữ nguyên
- JSON chỉ cải thiện corpus + metadata

---

# 22. MARKDOWN CŨ

Không xóa Markdown ngay nếu project còn phụ thuộc.

Thực hiện migration an toàn:

```text
Phase A:
PDF → JSON
JSON → existing chunk pipeline

Phase B:
remove Markdown dependency nếu không còn cần
```

Nếu Markdown chỉ phục vụ debug/documentation, có thể giữ generator:

```text
JSON
↓
optional Markdown export
```

Không để:

```text
PDF → Markdown → JSON
```

nếu JSON là processed representation chính mới.

Ưu tiên:

```text
PDF → JSON
```

---

# 23. CLI

Tạo/chuẩn hóa command:

```bash
python -m src.ingestion.prepare_processed_from_raw
```

hoặc command hiện tại tương đương.

Command phải:

```text
scan RAW PDFs
↓
extract/OCR
↓
parse
↓
write JSON
↓
validate
↓
summary
```

Ví dụ log:

```text
[1/14] hoc_phi_hoc_ky_1_2026.pdf
  extraction: OK
  category: hoc_phi
  records: 1
  validation: PASS
  output: data/processed_json/hoc_phi/hoc_phi_hoc_ky_1_2026.json
```

---

# 24. BUILD VECTOR DB

`build_vector_db.py` phải đọc JSON structured data thay vì phụ thuộc trực tiếp vào Markdown generated.

Luồng:

```text
processed_json
↓
load JSON
↓
chunk builder
↓
LangChain Document
↓
embedding
↓
ChromaDB
```

---

# 25. LANGCHAIN DOCUMENT

Ví dụ:

```python
Document(
    page_content=chunk_text,
    metadata={
        "category": "nganh_dao_tao",
        "record_type": "major",
        "major_name": "Công nghệ thông tin",
        "major_code": "7480201",
        "year": 2026,
        "page": 1,
    }
)
```

Không để:

```python
page_content=json.dumps(whole_document)
```

cho toàn bộ PDF.

---

# 26. TEST: JSON GENERATION

Thêm test:

```text
PDF
↓
JSON file được tạo
↓
valid UTF-8
↓
json.load() thành công
```

---

# 27. TEST: REQUIRED FIELDS

Test mỗi JSON phải có:

```text
document_id
title
category
source
pages
```

Nếu category có parser structured:
- kiểm tra `records`.

---

# 28. TEST: MAJOR CATALOG

Phải xác minh JSON cho ngành Công nghệ thông tin chứa:

```text
major_name = Công nghệ thông tin
major_code = 7480201
program count = 5
```

và có:

```text
Công nghệ phần mềm
Lập trình AI
An ninh mạng và hệ thống
Truyền thông đa phương tiện
Phân tích dữ liệu lớn
```

Không tạo `Truyền thông đa phương tiện` thành major độc lập.

---

# 29. TEST: SCORE SEMANTICS

Phải test:

```text
application_threshold
≠
admission_score
≠
score_formula
≠
supplementary_threshold
```

Không dùng cùng field.

---

# 30. TEST: NUMERIC INTEGRITY

Kiểm tra các giá trị quan trọng sau extraction:

```text
15
18
600
20
7480201
12.500.000
1.500.000
250.000
75 tỷ
```

Không được mất dấu số hoặc gán nhầm field.

---

# 31. TEST: WEBSITE DATA

JSON `thong_tin_truong` phải giữ được các URL verified hiện có như:

```text
https://dhv.edu.vn/
https://tuyensinh.dhv.edu.vn/
https://ipic.dhv.edu.vn/
https://epdl.dhv.edu.vn/
https://heal.dhv.edu.vn/
https://tec.dhv.edu.vn/
https://fba.dhv.edu.vn/
https://bam.dhv.edu.vn/
https://lan.dhv.edu.vn/
https://host.dhv.edu.vn/
https://online.dhv.edu.vn/
```

Không silently sửa URL.

---

# 32. TEST: PAGE TRACEABILITY

Với mỗi structured record quan trọng phải trace được về:

```text
source_file
page
```

Nếu record đến từ nhiều page:
- dùng page range hoặc source_pages.

---

# 33. TEST: JSON → CHROMA

Sau JSON generation:

```text
build ChromaDB
↓
count chunks
↓
smoke retrieval
```

Phải chứng minh Chroma đang build từ JSON mới.

---

# 34. RETRIEVAL REGRESSION

Chạy lại các query:

```text
Trường Đại học Hùng Vương TP. Hồ Chí Minh có bao nhiêu ngành?
Công nghệ thông tin có những chuyên ngành nào?
Công nghệ thông tin có mấy chuyên ngành?
Học phí học kỳ 1 bao nhiêu?
Điều kiện nhận học bổng?
Điểm sàn Công nghệ thông tin?
Điểm chuẩn ngành Luật?
Website tuyển sinh là gì?
Thông tin trường?
```

So sánh baseline trước/sau.

---

# 35. DETERMINISTIC QUERY SUPPORT

JSON structured data nên được tận dụng cho câu hỏi cần tính/list/filter.

Ví dụ:

```text
"CNTT có mấy chuyên ngành?"
↓
structured JSON
↓
programs.length
↓
5
```

Thay vì:

```text
LLM đọc paragraph rồi tự đếm
```

Tương tự:

```text
"liệt kê chương trình CNTT"
↓
programs[]
```

Điều này là một lợi ích chính của JSON.

---

# 36. KHÔNG ÉP TẤT CẢ CÂU HỎI ĐỌC JSON TRỰC TIẾP

JSON là processed data layer.

Runtime vẫn nên dùng:

```text
retrieval
+
structured/deterministic helper khi cần
```

Không làm:

```text
mỗi user query
↓
load tất cả JSON
↓
đưa hết vào LLM
```

---

# 37. PERFORMANCE

Report:

- số PDF
- thời gian PDF → JSON
- tổng JSON size
- số records
- số chunks
- Chroma build time
- retrieval test time

Mục tiêu là kiểm soát pipeline, không chỉ nói "JSON tối ưu hơn".

---

# 38. GIT

JSON generated nên được xem xét giống processed data hiện tại.

Nếu quyết định không commit generated JSON:

`.gitignore` có thể dùng:

```gitignore
data/processed_json/**
!data/processed_json/.gitkeep
```

Nhưng Agent phải kiểm tra workflow nhóm trước khi thay đổi Git.

Không tự đổi Git policy mà không report.

---

# 39. README

Cập nhật architecture:

```text
RAW PDF
↓
Extraction / OCR
↓
Structured JSON
↓
Schema Validation
↓
Chunk Builder
↓
Embedding
↓
ChromaDB
↓
Retriever
↓
RAG
```

Giải thích ngắn:

> JSON là lớp dữ liệu xử lý trung gian có cấu trúc, giúp giữ metadata, page traceability, bảng, quan hệ ngành–chương trình và các trường dữ liệu deterministic trước khi tạo chunk cho Vector Database.

---

# 40. BACKWARD COMPATIBILITY

Không được phá:

```text
ChatService
rag_chain
retriever public API
output validator
conversation state
Streamlit UI
```

Refactor ingestion không được buộc UI phải biết JSON.

UI vẫn chỉ nhận:

```python
{
    "answer": "...",
    "sources": [...],
    "status": "..."
}
```

hoặc schema backend hiện tại tương đương.

---

# 41. ACCEPTANCE CRITERIA

Task chỉ PASS khi:

- RAW PDF vẫn là source of truth.
- Mỗi RAW PDF generate được JSON.
- JSON UTF-8 hợp lệ.
- JSON có metadata nguồn.
- JSON giữ page boundary.
- Category quan trọng có structured records.
- Ngành/chương trình giữ đúng parent-child.
- Score types được tách semantic rõ.
- URL/số liệu quan trọng không bị sai.
- Build Vector DB đọc từ JSON.
- Chunk không phải whole-JSON dump.
- Chroma metadata được tạo từ structured fields.
- deterministic count/list có thể dùng JSON.
- retrieval regression pass.
- full test suite pass.
- ChatService/RAG/UI không bị phá.

---

# 42. FINAL REPORT

Tạo:

```text
reports/TASK_PDF_TO_STRUCTURED_JSON_REPORT.md
```

Report phải gồm:

1. Pipeline trước khi sửa.
2. Pipeline sau khi sửa.
3. Files changed.
4. JSON schema.
5. Category parsers.
6. Validation rules.
7. JSON examples.
8. Số PDF processed.
9. Số records generated.
10. Số warnings/errors.
11. Chunk strategy.
12. Chroma build result.
13. Retrieval regression.
14. Deterministic query tests.
15. Full test result.
16. Performance.
17. Remaining limitations.

Cuối report:

```text
STATUS: PASS
```

hoặc:

```text
STATUS: FAIL
```

---

# KIẾN TRÚC ĐÍCH CUỐI CÙNG

```text
Official PDF
↓
Extractor / OCR
↓
Normalized text by page
↓
Category-specific parser
↓
Structured JSON
├─ metadata
├─ pages
├─ sections
├─ records
└─ warnings
↓
Schema + domain validation
↓
Chunk Builder
↓
LangChain Documents
↓
Embedding
↓
ChromaDB
↓
Hybrid Retriever
↓
Evidence Selection
↓
Answer Planner / Deterministic Logic
↓
LLM
↓
ChatService
↓
UI
```

## NGUYÊN TẮC QUAN TRỌNG

```text
PDF = source of truth

JSON = structured processed representation

ChromaDB = retrieval index

LLM = natural-language generator
```

JSON giúp tối ưu cấu trúc và deterministic logic, nhưng không thay thế Vector Database và không được biến thành nơi LLM tự suy đoán dữ liệu.
