# PHASE 1.5 – PRODUCTION PIPELINE COMPLETION REPORT

Date: 2026-09-23  
Project: `ChatBot_DHV`  
Target year: `2026`

## 1. Environment

| Component | Result |
|---|---|
| Python | `.venv` Python 3.12.14 |
| PyMuPDF | PASS — 1.28.2 |
| pytesseract | PASS — 0.3.13 |
| ChromaDB | PASS — 1.5.9 |
| LangChain | PASS — 0.3.30; langchain-chroma 0.2.6 |
| Ollama CLI | PASS — 0.34.2 |
| Ollama Python client | PASS — 0.6.2 |
| Tesseract binary | **NOT AVAILABLE** — `tesseract` is not on PATH |
| nomic-embed-text | PASS — `nomic-embed-text:latest` is installed |
| qwen2.5:3b | PASS — model is installed |
| pytest | PASS — 9.1.1 |

The declared Python OCR dependencies and pytest were installed into the existing `.venv`. No alternate embedding model was installed or used.

## 2. OCR Runtime

| Check | Result |
|---|---|
| Native extraction | PASS — 44 pages inspected; 44 native pages, 0 OCR pages |
| OCR trigger | PASS — page 8 of `DIEM_TRUNG_TUYEN_VA_NHAP_HOC_DHV_2026.pdf` was judged unusable and called `_ocr_page()` |
| OCR execution | **BLOCKED** — pytesseract reached the real engine boundary, but Tesseract executable was missing |
| OCR output used | FAIL — no OCR text was returned; native empty text was retained with warnings |
| Result | **BLOCKED** |

The real runtime warning is `tesseract is not installed or it's not in your PATH`. The mocked OCR call-path regression test passes, but it is not counted as runtime OCR PASS.

## 3. Ollama Embedding

| Check | Result |
|---|---|
| Ollama service | PASS — CLI available and real HTTP `/api/embed` request returned `200 OK` |
| Model | PASS — `nomic-embed-text` |
| Project abstraction | PASS — `create_embeddings(backend="ollama")` returned `OllamaEmbeddings` |
| Embedding vector | PASS — `embed_query("test")` returned 768 numeric values |
| Result | **PASS** |

## 4. Production Chroma

The processed corpus was rebuilt from the current RAW PDFs, then the production Chroma directory was reset and rebuilt using the Ollama embedding backend.

| Metric | Result |
|---|---:|
| Processed JSON documents | 7 |
| Schema-valid JSON documents | 7/7 |
| Eligible verified 2026 documents | 5 |
| Unverified documents skipped | 2 |
| Structured records | 41 |
| Production chunks | 71 |
| Embedded chunks | 71 |
| Collection | `dhv_admissions_2026` |
| Collection count | **71** |

Production build evidence: `embedding_backend=ollama`, `embedding_model=nomic-embed-text`, `collection_count=71`. No offline/fake/hash/Sentence Transformers embeddings were used for this build.

## 5. Year Isolation

| Check | Result |
|---|---:|
| Production records with `year=2026` | 71 |
| Production records with `year=2024` | **0** |
| Chroma filter `where={"year": 2024}` | **0 records** |
| Metadata sample | contains `document_id`, `category`, `year`, `status`, `source_file`, `source_url`, `page`, `chunk_id`, `record_type` |
| Result | **PASS** |

`Hoc_Phi_DHV_2024.pdf` remains `year=2024`, `status=missing_source_url`, `verified=false` in processed data and is not eligible for the 2026 production collection.

## 6. Dense Retrieval

The tests below used the real `dhv_admissions_2026` collection and the real Ollama embedding function. Results shown are after the production category/entity filter.

| Query | Results | Year | Result |
|---|---:|---:|---|
| Trường có xét học bạ không? | 4 | 2026 | PASS — production candidates |
| Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu? | 1 | 2026 | PASS — production candidate |
| Hồ sơ nhập học cần những giấy tờ gì? | 4 | 2026 | PASS — production candidates |
| DHV có xét tuyển bổ sung năm 2026 không? | 1 | 2026 | PASS — production candidate |
| Ngành Công nghệ thông tin có những chương trình nào? | 0 | — | Expected `NO_DATA` — no verified `nganh_dao_tao` source in current corpus |
| 1 tín chỉ năm 2026 bao nhiêu tiền? | 0 | — | Expected `NO_DATA` — no verified 2026 tuition source |

No production query raised `vector_db_error`.

## 7. BM25 Retrieval

Production lexical test: `7480201`.

| Rank | Document ID | Category | Year | BM25 score |
|---:|---|---|---:|---:|
| 1 | `33b75ba5ae96` | `diem_trung_tuyen` | 2026 | 1.149967 |
| 2 | `b2a1be05de48` | `thong_tin_truong` | 2026 | 1.128378 |
| 3 | `48385aee28bc` | `phuong_thuc_xet_tuyen` | 2026 | 1.124861 |

BM25 returned real candidates from the production collection. Result: **PASS**.

## 8. RRF

Call path observed in the production audit:

```text
Question
  ↓
Chroma dense search + production collection candidate read
  ↓
BM25 candidate scoring
  ↓
_rank_hybrid_candidates_with_audit()
  ↓
RRF score (bm25+dense+rrf, k=60)
  ↓
final ranked documents
  ↓
Evidence Selection
```

Production evidence:

- `điểm chuẩn CNTT 2026`: dense rank and BM25 rank were both present in the audit; final RRF results were passed to evidence selection.
- `7480201`: BM25 recovered exact-code candidates when the dense result did not retain an entity-matching rank; RRF still produced final production documents.
- `đăng ký xét tuyển bổ sung`: BM25 rank 1 and dense rank 1 both contributed to the final RRF result.

The audit exposed `bm25_rank`, `bm25_score`, `dense_rank`, `dense_score`, and `rrf_score`. Result: **PASS**.

## 9. Evidence

Real evidence selection smoke test:

| Field | Value |
|---|---|
| Question | Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu? |
| Evidence ID / chunk ID | `33b75ba5ae96-000-001-3aaf798f` |
| Document ID | `33b75ba5ae96` |
| Page | 1 |
| Category | `diem_trung_tuyen` |
| Year | 2026 |
| Source | Official DHV URL from Chroma metadata |
| Evidence context used | Yes |
| Evidence usable | Yes |

The selected evidence carried real text and provenance into `build_evidence()`. A separate runtime instrumentation of the hồ sơ query observed: `Qwen generate calls=1`, `Output Validator calls=1`, selected evidence=4, source count=1, final status=`ok`.

## 10. Runtime Chat

| Question | Retrieval | Evidence | LLM | Validator | Final |
|---|---|---|---|---|---|
| Trường có xét học bạ không? | 0; router boundary | 0 | Not called | Not called | `out_of_scope` fallback |
| Điểm chuẩn ngành Công nghệ thông tin năm 2026 là bao nhiêu? | 1 | 1 | Not called — score boundary | Not called — score boundary | `no_data` |
| Hồ sơ nhập học gồm những gì? | 4 | 4 | Qwen real call | Real validator call | `ok` |
| DHV có xét tuyển bổ sung không? | 1 | 1 | Qwen real call | Real validator call | `ok` |
| 1 tín chỉ năm 2026 bao nhiêu tiền? | 0; router boundary | 0 | Not called | Not called | `out_of_scope` fallback; no 2024 tuition used |

The exact standalone `học bạ` and tuition phrasings are currently classified by the existing scope/router logic as `out_of_scope`; changing that business logic is outside this phase. The production retrieval layer itself returned no `vector_db_error`, and no 2024 tuition content entered the answer path.

## 11. Tests

| Test suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| `tests/test_data_pipeline_recovery.py` | 5 | 0 | 0 | 0 |
| Full pytest run | 94 | 140 | 0 | 1 |

The full run also reported 73 passing subtests. The 140 failures are concentrated in legacy/stale or dataset-dependent expectations: removed RAW filenames, a former 15-document corpus, verified 2026 tuition, and the former 20-major/program catalogue. No stale test was modified blindly, and no production code was changed to satisfy those obsolete expectations.

## 12. Remaining Issues

1. **Blocking:** Tesseract OCR binary is not installed or discoverable. The scanned/empty page cannot produce OCR text, so OCR runtime cannot be marked PASS.
2. The current corpus has no verified 2026 tuition document and no verified `nganh_dao_tao` document. Tuition and programme-list queries therefore correctly return no data rather than importing 2024 data.
3. Existing scope/router logic does not recognize the exact standalone phrases `Trường có xét học bạ không?` and `1 tín chỉ năm 2026 bao nhiêu tiền?` as in-scope. This was not changed because Phase 1.5 explicitly excludes intent/business-logic changes.
4. Legacy tests remain stale/dataset-mismatched; they were reported, not hidden or rewritten.

## 13. Final Verdict

# BLOCKED

The production embedding, Chroma build, year isolation, dense retrieval, BM25, RRF, evidence selection, Qwen smoke, and validator runtime paths are operational. Phase 1.5 cannot be marked READY because the mandatory real OCR integration criterion is blocked by the missing Tesseract binary.
