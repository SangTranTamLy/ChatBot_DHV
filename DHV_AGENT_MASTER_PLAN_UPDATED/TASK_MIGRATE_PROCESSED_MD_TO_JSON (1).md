# TASK: MIGRATE PROCESSED DATA TỪ MARKDOWN CŨ SANG JSON MỚI SAU OCR

## MỤC TIÊU

Sau khi pipeline mới của project chuyển sang:

```text
RAW PDF
↓
OCR
↓
Structured JSON
↓
Validation
↓
Chunk
↓
Embedding
↓
ChromaDB
```

cần xử lý dứt điểm thư mục `data/processed/` cũ đang chứa Markdown generated.

Task này KHÔNG được xóa dữ liệu cũ ngay từ đầu.

Phải thực hiện migration an toàn theo thứ tự:

```text
audit dependency
↓
migrate code
↓
generate JSON mới
↓
build ChromaDB từ JSON
↓
run regression
↓
xác nhận không còn code dùng Markdown cũ
↓
mới xóa processed Markdown cũ
```

---

## 1. AUDIT TOÀN BỘ DEPENDENCY CỦA `data/processed`

Trước khi xóa bất kỳ file nào, search toàn project các từ:

```text
data/processed
processed/
*.md
glob("*.md")
glob("**/*.md")
read_text
markdown
yaml
frontmatter
prepare_processed_from_raw
load_processed
```

Kiểm tra tối thiểu:

```text
src/ingestion/prepare_processed_from_raw.py
src/ingestion/loader.py
src/ingestion/build_vector_db.py
src/ingestion/splitter.py
src/ingestion/rebuild_smoke_test.py
src/ingestion/smoke_test_vector_db.py
src/retrieval/retriever.py
src/config/settings.py
tests/
README.md
.gitignore
```

Phải xác định:

1. File nào đang đọc Markdown.
2. File nào đang ghi Markdown.
3. Build Vector DB hiện đang đọc từ đâu.
4. Test nào đang assert `.md`.
5. README nào đang hướng dẫn dùng Markdown.
6. `.gitignore` đang xử lý processed data thế nào.
7. Có script/debug tool nào vẫn phụ thuộc Markdown không.

Tạo:

```text
reports/PROCESSED_MIGRATION_AUDIT.md
```

---

## 2. CẤU TRÚC THƯ MỤC MỚI

Ưu tiên cấu trúc:

```text
data/
├── raw/
│   └── *.pdf
│
└── processed/
    └── *.json
```

Tức là giữ tên thư mục:

```text
data/processed/
```

nhưng thay nội dung generated từ:

```text
*.md
```

sang:

```text
*.json
```

Ví dụ:

```text
data/processed/
├── hoc_phi/
│   └── hoc_phi_hoc_ky_1_2026.json
├── hoc_bong/
│   └── hoc_bong_2026.json
├── nganh_dao_tao/
│   └── danh_muc_nganh_chuong_trinh_2026.json
└── thong_tin_truong/
    └── thong_tin_truong_dhv_2026.json
```

Nếu code hiện tại hoặc task trước đã tạo `data/processed_json/`, Agent phải audit rồi chọn một convention duy nhất.

---

## 3. KHÔNG XÓA MARKDOWN CŨ NGAY

Trong giai đoạn migration:

```text
data/processed/
```

cũ phải được giữ hoặc backup tạm.

Có thể dùng:

```text
data/processed_legacy/
```

hoặc temp backup ngoài Git.

Mục tiêu:

```text
nếu pipeline JSON lỗi
→ vẫn có thể so sánh với output cũ
```

Không commit backup legacy nếu không cần.

---

## 4. MIGRATE `prepare_processed_from_raw.py`

Script này phải chuyển từ:

```text
RAW PDF
↓
extract text
↓
Markdown
```

sang:

```text
RAW PDF
↓
OCR
↓
normalize
↓
structured parser
↓
JSON
```

Output phải là:

```text
data/processed/**/*.json
```

Không còn tạo `.md` mới sau khi migration hoàn tất.

---

## 5. MIGRATE `build_vector_db.py`

Build Vector DB phải đổi từ:

```text
load Markdown
↓
split text
```

sang:

```text
load Structured JSON
↓
build semantic chunks từ records/sections
↓
LangChain Document
↓
embedding
↓
ChromaDB
```

Không dùng:

```python
json.dumps(whole_document)
```

làm một chunk lớn.

Phải chunk theo nghĩa dữ liệu.

---

## 6. MIGRATE LOADER

Nếu `loader.py` đang có logic:

```text
load .md
parse YAML frontmatter
read Markdown body
```

thì phải thay bằng:

```text
load .json
validate schema
return structured document
```

Có thể giữ loader cũ tạm thời trong migration nhưng sau khi regression pass phải loại bỏ nếu không còn dùng.

---

## 7. MIGRATE SPLITTER / CHUNK BUILDER

Không split JSON bằng character splitter một cách mù quáng.

Ưu tiên:

```text
record
→ chunk

section
→ chunk

major
→ chunk

scholarship rule
→ chunk

tuition record
→ chunk
```

Nếu text dài:
- mới dùng recursive splitter bên trong record/section.

---

## 8. MIGRATE TESTS

Search tất cả test đang phụ thuộc:

```text
.md
Markdown
YAML frontmatter
processed file count
```

Sửa sang JSON.

Test tối thiểu:

```text
RAW PDF count
→ processed JSON count
```

```text
JSON parse thành công
```

```text
required metadata có mặt
```

```text
build_vector_db đọc JSON thật
```

```text
không còn test nào yêu cầu generated Markdown
```

---

## 9. MIGRATE README

README phải mô tả pipeline mới:

```text
RAW PDF
↓
OCR
↓
Structured JSON
↓
Validation
↓
Chunk
↓
Embedding
↓
ChromaDB
```

Không còn mô tả:

```text
RAW PDF → Markdown → ChromaDB
```

nếu Markdown đã bị loại bỏ.

---

## 10. MIGRATE `.gitignore`

Nếu processed là generated data và không commit:

```gitignore
data/processed/**
!data/processed/.gitkeep
```

Giữ:

```text
data/processed/.gitkeep
```

nếu cần giữ thư mục rỗng trong Git.

Nếu project quyết định commit JSON:
- phải report lý do.
- không tự thay policy Git mà không ghi rõ.

---

## 11. BUILD JSON TỪ TOÀN BỘ RAW

Sau khi migration code xong:

```text
clear/regenerate processed JSON
↓
scan ALL RAW PDF
↓
OCR ALL PDF
↓
generate ALL JSON
```

Không test chỉ 1–2 file rồi xóa dữ liệu cũ.

Phải process toàn bộ RAW hiện tại.

---

## 12. VALIDATE JSON

Mỗi JSON phải kiểm tra:

```text
valid UTF-8
json.load() thành công
document_id
category
source
pages
records/sections nếu applicable
```

Các field quan trọng phải được audit:

```text
major_code
program names
scores
thresholds
tuition
scholarship
deadline
website
hotline
address
```

---

## 13. BUILD CHROMADB TỪ JSON

Sau khi JSON valid:

```text
JSON
↓
Chunk Builder
↓
Embedding
↓
ChromaDB rebuild
```

Phải chứng minh bằng log/report rằng:

```text
ChromaDB source = JSON mới
```

không phải Markdown cũ.

---

## 14. RETRIEVAL REGRESSION

Chạy lại tối thiểu:

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

Không được giảm chất lượng retrieval nghiêm trọng.

---

## 15. DETECT MARKDOWN DEPENDENCY SAU MIGRATION

Sau khi tất cả test pass:

Search lại toàn project:

```text
data/processed
*.md
frontmatter
markdown loader
```

Mục tiêu:

```text
không còn runtime/ingestion dependency
vào generated Markdown cũ
```

README `.md` và report `.md` vẫn được giữ.

Chỉ cần loại dependency với:

```text
data/processed/**/*.md
```

---

## 16. CHỈ SAU ĐÓ MỚI XÓA MARKDOWN CŨ

Điều kiện để xóa:

```text
JSON generation PASS
+
JSON validation PASS
+
Chroma rebuild PASS
+
retrieval regression PASS
+
full test PASS
+
search dependency = không còn dùng Markdown processed
```

Sau đó:

```text
delete old generated .md files
```

Nếu có:

```text
data/processed_legacy/
```

thì cũng xóa sau khi xác nhận migration hoàn tất.

---

## 17. KHÔNG XÓA RAW PDF

TUYỆT ĐỐI không xóa:

```text
data/raw/**/*.pdf
```

RAW PDF vẫn là source of truth.

---

## 18. KHÔNG XÓA REPORT / README

Không hiểu nhầm `.md` là xóa tất cả Markdown trong project.

Được giữ:

```text
README.md
reports/*.md
task files
documentation
```

Chỉ loại:

```text
generated processed Markdown
```

nếu đã được JSON thay thế.

---

## 19. CLEAN DEAD CODE

Sau migration thành công:

Xóa code chết như:

```text
Markdown processed loader
YAML frontmatter parser chỉ dành cho generated processed docs
Markdown writer
legacy processed converter
```

nhưng chỉ khi chắc chắn không còn dependency.

---

## 20. FULL REGRESSION

Chạy:

```text
targeted ingestion tests
↓
JSON tests
↓
Chroma tests
↓
retrieval tests
↓
chatbot tests
↓
full regression
```

Không báo PASS nếu chỉ build JSON thành công.

---

## 21. FINAL DIRECTORY EXPECTED

Sau migration hoàn tất, cấu trúc mong muốn:

```text
data/
├── raw/
│   ├── hoc_phi/
│   │   └── *.pdf
│   ├── hoc_bong/
│   │   └── *.pdf
│   ├── nganh_dao_tao/
│   │   └── *.pdf
│   └── ...
│
└── processed/
    ├── hoc_phi/
    │   └── *.json
    ├── hoc_bong/
    │   └── *.json
    ├── nganh_dao_tao/
    │   └── *.json
    └── ...
```

Không còn:

```text
data/processed/**/*.md
```

nếu migration đã hoàn tất.

---

## 22. KIẾN TRÚC CUỐI

```text
RAW PDF
↓
OCR
↓
Normalized text
↓
Structured JSON
↓
Validation
↓
Semantic Chunk Builder
↓
Embedding
↓
ChromaDB
↓
Retriever
↓
Evidence
↓
RAG
↓
ChatService
↓
UI
```

---

## 23. ACCEPTANCE CRITERIA

Task chỉ PASS khi:

- RAW PDF còn nguyên.
- OCR pipeline hoạt động.
- JSON mới được sinh cho toàn bộ RAW.
- Không còn generated Markdown mới.
- Build Vector DB đọc JSON.
- ChromaDB rebuild thành công.
- Retrieval regression pass.
- Chatbot regression pass.
- Không còn code runtime phụ thuộc `data/processed/**/*.md`.
- Markdown processed cũ đã được xóa an toàn.
- README mô tả pipeline mới.
- `.gitignore` phù hợp với processed generated data.
- Không xóa README/report Markdown.
- Không phá ChatService/RAG/UI.

---

## 24. FINAL REPORT

Tạo:

```text
reports/TASK_PROCESSED_MD_TO_JSON_MIGRATION_REPORT.md
```

Report phải gồm:

1. Processed architecture cũ.
2. Dependency Markdown cũ.
3. Files/functions migrated.
4. Directory structure mới.
5. JSON generation result.
6. JSON validation result.
7. Chroma rebuild result.
8. Retrieval regression result.
9. Full regression result.
10. Search dependency sau migration.
11. Danh sách Markdown processed đã xóa.
12. Dead code đã xóa.
13. Remaining limitations.

Cuối report:

```text
STATUS: PASS
```

hoặc:

```text
STATUS: FAIL
```

Không ghi PASS nếu code vẫn còn đọc generated Markdown cũ.
