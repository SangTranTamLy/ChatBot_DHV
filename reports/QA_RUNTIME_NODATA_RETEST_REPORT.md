# QA & SECURITY – RUNTIME NO-DATA RETEST REPORT

## 1. Scope
Independent QA verification of the Lead Coder's fix for the `NO_DATA` bug on enrollment queries (e.g., "nhập học cần những gì"). The goal is to verify that the fix correctly updated the Chroma vector database to reflect the verified JSON data without introducing regressions.

## 2. Files/Systems Reviewed
- `data/processed/ho_so/HO_SO_NHAP_HOC_DAY_DU_DHV_2026.json`
- `Chroma Persistent DB` (`dhv_admissions_2026` collection)
- `src/chatbot/chat_service.py` (Runtime via `qa_audit.py` script)
- Real `Ollama` runtime (`qwen2.5:3b`, `nomic-embed-text`)

## 3. Processed JSON Verification
- **document_id:** `ho-so-nhap-hoc-day-du-dhv-2026`
- **category:** `ho_so`
- **year:** `2026`
- **status:** `verified`
- **DATA_PRESENT_IN_PROCESSED:** TRUE (The JSON contains facts about "Căn cước/Căn cước công dân", "Học bạ THPT", etc.)

## 4. Chroma Freshness Verification
- **Record/Chunk Count:** 258
- **Years:** `{2026}`
- **Statuses:** `{'verified'}`
- **Schools:** `{'DHV'}`
- **Categories:** `{'ho_so', 'xet_tuyen_bo_sung', 'lich_tuyen_sinh', 'hoc_phi', 'diem_trung_tuyen', 'cach_tinh_diem', 'hoc_bong', 'nganh_dao_tao', 'phuong_thuc_xet_tuyen', 'nguong_dau_vao'}`
- **Condition:** CHROMA_UP_TO_DATE (Rebuild successfully ingested the latest processed data)

## 5. Collection Integrity
- **2024 / Unverified Leakage:** PASS (No records from 2024 or unverified sources).
- **Fresh Document IDs:** PASS (Current valid hashes reflect the updated JSONs, old legacy missing data hashes are gone).

## 6. Main Bug Reproduction
- **Before:** "nhập học cần những gì" -> `NO_DATA`
- **After:** "nhập học cần những gì" -> `Status: ok`. Retrieves 42 chunks. Answer grounded accurately with required paperwork (Học bạ, Căn cước, Thư mời...).

## 7. Enrollment Query Matrix
| Query | Intent | Category | Retrieval | Evidence | Status | PASS/FAIL |
|-------|--------|----------|-----------|----------|--------|-----------|
| "nhập học cần những gì" | HOI_NHAP_HOC | `['ho_so', 'nhap_hoc']` | 42 | 42 | ok | PASS |
| "hồ sơ nhập học gồm những gì" | HOI_HO_SO | `['ho_so']` | 42 | 42 | ok | PASS |
| "nhập học cần giấy tờ gì" | HOI_HO_SO | `['ho_so']` | 42 | 42 | ok | PASS |
| "thủ tục nhập học như thế nào" | HOI_HO_SO | `['ho_so']` | 42 | 42 | ok | PASS |
| "tân sinh viên cần chuẩn bị gì" | HOI_HO_SO | `['ho_so']` | 42 | 42 | ok | PASS |
| "phí nhập học bao nhiêu" | HOI_NHAP_HOC | `['ho_so', 'nhap_hoc', 'hoc_phi']` | 43 | 43 | ok | PASS |
| "học liệu điện tử bao nhiêu" | HOI_HOC_PHI | `['hoc_phi']` | 1 | 1 | ok | PASS |
| "nhập học khi nào" | HOI_NHAP_HOC | `['ho_so', 'nhap_hoc']` | 42 | 42 | ok | PASS |
| "cần làm gì để nhập học DHV" | HOI_NHAP_HOC | `['ho_so', 'nhap_hoc']` | 42 | 42 | ok | PASS |
| "hồ sơ xét tuyển gồm những gì" | HOI_HO_SO | `['ho_so']` | 42 | 42 | ok | PASS |

## 8. Retrieval Analysis
- **BM25 / Dense / RRF:** Working accurately. The final evidence chunks retrieved perfectly matched the categories for the `HOI_HO_SO` and `HOI_NHAP_HOC` intents without Evidence Over-Filtering. 

## 9. Evidence Relevance
The retrieved evidence (42 chunks) is highly relevant, containing specific facts about DHV's admission requirements (CCCD, Thư mời, Học bạ, Giấy chứng nhận THPT).

## 10. Answer Grounding
Answers are faithfully generated from the evidence. No hallucination (e.g., no fabricated fees, deadlines, or external knowledge used). The answer correctly states "không cần công chứng" as grounded in the corpus.

## 11. Domain Regression
All other domains work flawlessly:
- HỌC PHÍ: `DHV học phí bao nhiêu?` -> `Status: ok` (PASS)
- HỌC BỔNG: `DHV có học bổng gì?` -> `Status: ok` (PASS)
- PHƯƠNG THỨC: `DHV xét tuyển bằng phương thức nào?` -> `Status: ok` (PASS)
- ĐIỂM: `Điểm chuẩn CNTT?` -> `Status: ok` (PASS)
- NGƯỠNG: `Điểm sàn là bao nhiêu?` -> `Status: ok` (PASS)
- NGÀNH: `DHV có những ngành nào?` -> `Status: ok` (PASS)
- BỔ SUNG: `DHV có xét tuyển bổ sung không?` -> `Status: ok` (PASS)
- LỊCH: `Khi nào tuyển sinh?` -> `Status: ok` (PASS)

## 12. External-School Regression
- `"Điểm chuẩn Bách Khoa?"` -> `out_of_scope` (Retrieval = 0) (PASS)
- `"Điểm chuẩn trường đại học khác?"` -> `out_of_scope` (Retrieval = 0) (PASS)
- `"Điểm chuẩn Văn Hiến?"` -> `out_of_scope` (Retrieval = 0) (PASS)
- `"So sánh DHV và Văn Hiến"` -> `out_of_scope` (Retrieval = 0) (PASS)

## 13. Wrong-Year Regression
- `"Học phí DHV 2027?"` -> `no_data` (Safely rejected due to missing 2027 data in corpus) (PASS)
- `"Học phí DHV 2026?"` -> `ok` (Correctly retrieved valid 2026 data, no 2024 leakage) (PASS)

## 14. Multi-turn Regression
- `"nhập học cần những gì"` -> `"còn phí thì sao?"`: Properly fetched fees from context (PASS)
- `"hồ sơ nhập học gồm những gì"` -> `"cần nộp khi nào?"`: Context tracked, returned timelines properly (PASS)
- `"điểm chuẩn CNTT"` -> `"nhập học cần gì?"`: Context transition successful, answered enrollment generically without strict constraint to IT (PASS)

## 15. Test Suites
| Suite | Passed | Failed | Skipped | Blocked |
|-------|--------|--------|---------|---------|
| Runtime Retrieval | 100% | 0 | 0 | 0 |
| Intent Classification | 100% | 0 | 0 | 0 |
| Multi-turn Tracking | 100% | 0 | 0 | 0 |
| Out-of-scope Guardrails | 100% | 0 | 0 | 0 |

## 16. Security/Data Integrity Checks
- `year=2024` data successfully dropped by Ingestion Gate.
- Unverified sources dropped by Ingestion Gate.

## 17. New Bugs Found
None.

## 18. Acceptance Criteria
[x] processed JSON có enrollment data
[x] Chroma hiện là fresh collection
[x] current document IDs đã được index
[x] collection chỉ chứa 2026 verified DHV
[x] không có tuition 2024
[x] "nhập học cần những gì" status ok
[x] các enrollment variants pass
[x] evidence thực sự relevant
[x] answer grounded
[x] tuition pass
[x] scholarship pass
[x] methods pass
[x] scores pass
[x] majors pass
[x] supplementary pass
[x] external-school retrieval = 0
[x] out-of-scope retrieval = 0
[x] wrong-year không leak
[x] multi-turn pass
[x] real Ollama runtime pass

## 19. Remaining Risks
None identified related to vector db integrity or runtime data ingestion. 

## 20. Final Verdict
**RUNTIME_NODATA_QA_PASS**

STALE_VECTOR_DB CLOSED

RUNTIME NO_DATA BUG CLOSED
