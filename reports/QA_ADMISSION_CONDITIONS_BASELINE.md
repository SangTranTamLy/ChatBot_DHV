# QA Admission Conditions Baseline (Pre-fix)

**Verdict: FAIL — baseline only; not post-fix QA.**

This read-only audit checked the seven current processed JSON files against their same-name RAW PDFs, with focused page-level review of 2026 admission-condition facts and read-only routing probes. It did not edit code/data, run pytest, query or rebuild Chroma, or test live Ollama. The findings below are not a final assessment of the full corpus or of post-fix behavior.

## 1. Scope and files inspected

Read `reports/TONG_QUAN_AGENT` in UTF-8 and followed QA & Security’s read-only constraints. Inspected all 7 JSON/PDF pairs:

| Processed JSON | Corresponding RAW PDF | PDF pages | JSON pages | JSON category / year | Records | Top-level warnings |
|---|---|---:|---:|---|---:|---:|
| `data/processed/diem_trung_tuyen/V1_DIEM_TRUNG_TUYEN_DHV_2026.json` | `data/raw/diem_trung_tuyen/V1_DIEM_TRUNG_TUYEN_DHV_2026.pdf` | 2 | 2 | `diem_trung_tuyen` / 2026 | 69 | 0 |
| `data/processed/ho_so/V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.json` | `data/raw/ho_so/V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026.pdf` | 7 | 7 | `ho_so` / 2026 | 10 | 0 |
| `data/processed/hoc_phi/V1_HOC_PHI_DHV_2024.json` | `data/raw/hoc_phi/V1_HOC_PHI_DHV_2024.pdf` | 1 | 1 | `hoc_phi` / 2024 | 1 | 0 |
| `data/processed/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.json` | `data/raw/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` | 8 | 8 | `phuong_thuc_xet_tuyen` / 2026 | 94 | 0 |
| `data/processed/thong_tin_truong/V1_THONG_TIN_TRUONG_DHV.json` | `data/raw/thong_tin_truong/V1_THONG_TIN_TRUONG_DHV.pdf` | 7 | 7 | `thong_tin_truong` / 2026 | 1 | 0 |
| `data/processed/thong_tin_truong/V1_TONG_QUAN_TUYEN_SINH_DHV_2026.json` | `data/raw/phuong_thuc_xet_tuyen/V1_TONG_QUAN_TUYEN_SINH_DHV_2026.pdf` | 7 | 7 | `thong_tin_truong` / 2026 | 32 | 0 |
| `data/processed/xet_tuyen_bo_sung/V1_XET_TUYEN_BO_SUNG_DHV_2026.json` | `data/raw/xet_tuyen_bo_sung/V1_XET_TUYEN_BO_SUNG_DHV_2026.pdf` | 2 | 2 | `xet_tuyen_bo_sung` / 2026 | 24 | 0 |

**Page-count check: 7/7 pairs match; 34 PDF pages and 34 JSON pages total.** Each JSON page has `page_number`, `native_text`, `ocr_text`, `elements`, `tables`, `lists`, and `warnings`. All seven declare native extraction; OCR count is 0. The full-document extraction totals are taken from each JSON’s `content_audit`, not an independent semantic audit: combined `final_chars=52,140`, `ocr_chars=0`, declared warnings=0.

## 2. Admission-condition fact audit

Primary source: `V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` and its JSON. I opened and compared PDF pages 3–4 against the matching JSON page text; the key statements below are present in both. The separate `V1_TONG_QUAN_TUYEN_SINH_DHV_2026` JSON also repeats method/formula/threshold information on page 5.

| Fact | Source PDF / JSON page | Present in page text? | Structured `records[]` coverage / issue |
|---|---:|---|---|
| General eligibility: completed high school or equivalent | Main document p.3; summary document p.5 | Yes | Not represented as a complete eligibility record. |
| General 2026 threshold: 3 exam subjects in the admission combination, minimum 15.00/30, for candidates taking the THPT graduation exam from 2026 onward | Main p.3; summary p.5 | Yes | A threshold record exists (`application_threshold_thpt_001`, value 15.0), but its `page` is **1**, not PDF/JSON page 3. It does not encode the candidate-year condition or full 3-subject/30-point wording. |
| Law and Law Economics exception: grade-12 academic result Giỏi or above and grade-12 subject average ≥8.0 | Main p.3 | Yes | The two threshold records represent the 18-point exam total only; the grade/average condition is not separately represented in records. |
| Law and Law Economics exception: 3-subject THPT exam total ≥18, with Math or Literature ≥6 | Main p.3 | Yes | Records `application_threshold_thpt_002/003` contain value 18 and major labels; missing the Math/Literature ≥6 condition. Both also point to page 1 instead of page 3. |
| THPT exam method: two flexible subject-combination constructions, including the “Math or Literature + two highest-scoring eligible subjects” rules | Main pp.3–4 | Yes | Admission-method record identifies method 1, but the complete combination rules are page text/list content rather than complete structured records. |
| Transcript method: evaluate grade 10, 11, 12; either total of the three admission subjects, or Math/Literature + 2× overall average across grades 10–12 | Main p.4; summary p.5 | Yes | Method 2 record exists. Both formulas are not encoded as dedicated structured formula/eligibility records. |
| National University HCMC aptitude exam: 2026 exam, threshold ≥600 | Main p.4; summary p.5 | Yes | Threshold record value 600 exists and points to p.4; details about exam/year/institution remain in page text. The general threshold record may also be expanded per major, but the page provenance is not the issue for this fact. |
| H-SCA: 2026 H-SCA exam from HCMC University of Education, combined with THPT academic results | Main p.4; summary p.5 | Yes | Method 4 record contains only a shortened method name; no full structured condition/year/provider record. The PDF does not state a numeric H-SCA threshold. |
| Vocational entry: graduated vocational intermediate in the same field group as intended university field, and completed the THPT cultural program per regulations | Main p.4 | Yes | Method 5 record names the method, but does not encode the two eligibility conditions as structured records. |

The 2026 method document has 5 `admission_method` records and 40 `application_threshold` records (many are per-major expansions). The page text preserves more precise conditions than those records. Thus “fact present in JSON” is true for these items at the page-text layer, but **not** equivalent to “all conditions are represented in semantic records or discoverable by every route.”

### Page-level comparison limitation

A PyMuPDF text-layer comparison found every distinct normalized PDF token also in the corresponding JSON page text on 33/34 pages (token-set overlap 1.000); the remaining page (`V1_THONG_TIN_TRUONG_DHV.pdf`, p.3) was 0.993. This is only a text-layer/token-presence screen. It does **not** prove exact reading order, visual/table fidelity, correct OCR of image-only content, or completeness of every fact. No pages were visually rendered in this baseline. The method PDF is native-text extracted (`pypdf`, 8/8 native pages, 0 OCR pages); its page-level text includes the listed target facts, and its JSON warnings are empty.

## 3. Warnings and data-quality findings

1. **HIGH — structured condition records are incomplete relative to source text.** The 15-point and Law/Law Economics records omit important qualifications and point at page 1 although the source condition is on page 3. A consumer relying on those records alone may state the wrong eligibility rule or lose provenance precision.
2. **HIGH — current intent/category routing misses several supported variants.** Read-only probes against `analyze_question()` and `route_question()` found the misroutes below (details next section). This directly matches the observed “no information” behavior despite the condition text being present.
3. **MEDIUM — conditions are mostly preserved as prose/list text, not typed semantic facts.** Transcript formulas, the Law grade-12 requirement, Math/Literature subminimum, H-SCA combination requirement, and vocational eligibility are not complete structured records. Their retrievability depends on page-text chunking and category routing.
4. **No JSON-declared warnings** for the seven files. `ocr_chars=0` across these native-extracted PDFs is not by itself an error; this audit did not verify whether any meaningful content exists only inside raster images.

## 4. Routing clues observed (source inspection + local analysis only)

Eight non-mutating `analyze_question()` + `route_question()` probes were run with target year 2026. These do not call Chroma, Ollama, generation, or validate final answers.

| Probe | Observed intent / route | Baseline assessment |
|---|---|---|
| “Điều kiện xét tuyển DHV năm 2026 là gì?” | `HOI_HOC_BONG`; categories include `hoc_bong`, `phuong_thuc_xet_tuyen`, `ho_so` | **Wrong intent**. The method/conditions source is included among categories, but intent can select unrelated scholarship behavior/evidence. |
| “Điều kiện xét tuyển theo học bạ năm 2026 gồm những gì?” | `HOI_PHUONG_THUC_XET_TUYEN`; category `phuong_thuc_xet_tuyen` | Route is plausibly aligned; actual retrieval/evidence not tested. |
| “Điều kiện xét tuyển ngành Luật năm 2026 là gì?” | `HOI_NGANH`, major `Luật`; category only `nganh_dao_tao` | **Wrong category for the requested fact**: the Law eligibility text is in the method/conditions source, category `phuong_thuc_xet_tuyen`. |
| “Điều kiện xét tuyển Luật Kinh tế là gì?” | `HOI_NGANH`, major `Luật Kinh tế`; category only `nganh_dao_tao` | Same category mismatch. |
| “Xét tuyển bằng đánh giá năng lực cần bao nhiêu điểm?” | `HOI_NGUONG_DAU_VAO`; categories `nganh_dao_tao`, `nguong_dau_vao` | **Category mismatch risk**: the 600-point fact is in the `phuong_thuc_xet_tuyen` source. |
| “H-SCA cần điều kiện gì?” | `HOI_HOC_BONG`; scope `general_out_of_scope`; route categories include `hoc_bong`, `phuong_thuc_xet_tuyen`, `ho_so` | **Wrong intent and scope risk** for a DHV admissions-method condition. |
| “Tốt nghiệp trung cấp có được xét tuyển không?” | `HOI_DANG_KY_XET_TUYEN`; category `phuong_thuc_xet_tuyen` | Route is plausibly aligned; actual retrieval/evidence not tested. |
| “Điểm sàn tuyển sinh DHV 2026 là bao nhiêu?” | `HOI_NGUONG_DAU_VAO`; categories `nganh_dao_tao`, `nguong_dau_vao` | **Category mismatch risk** with the source document’s canonical category. |

Relevant code areas observed: `src/chatbot/query_analysis.py` around routing for `HOI_NGUONG_DAU_VAO`, `HOI_PHUONG_THUC_XET_TUYEN`, and `HOI_DANG_KY_XET_TUYEN`; record-to-evidence handling in `src/chatbot/evidence.py`; method/threshold deterministic answer handling in `src/chatbot/rag_chain.py`. These are routing clues, not a complete execution trace or confirmed Chroma behavior.

## 5. Commands and checks run

- Read role guidance: `Get-Content -Raw -Encoding UTF8 reports/TONG_QUAN_AGENT` — completed.
- Enumerated `data/processed/**/*.json` and `data/raw/**/*.pdf` — 7 JSON, 7 PDFs.
- Read-only Python/PyMuPDF audit comparing matching PDF and JSON page counts, per-page text/token coverage, extraction/content-audit metadata, and target fact text — 7 pairs, 34 pages; all page counts matched.
- Read-only Python probe of `analyze_question()` and `route_question()` — 8 questions; results listed above.
- `rg` / source reads of query routing, evidence extraction and deterministic method answer paths — inspection only.
- **pytest/tests run: 0.** No test suite was run because this was a read-only pre-fix data/routing baseline; no code was changed.
- **Chroma/Ollama/live RAG: not run.** No vector store was read or rebuilt and no live generation was attempted.

## 6. Findings and verdict

| Finding | Severity | Status |
|---|---|---|
| Seven PDF/JSON page counts match; target admission-condition statements are present in method JSON page text at pages 3–4 (and some repeat in summary page 5). | PASS, limited to checked facts/page counts | Partial only; not a full visual or semantic completeness certification. |
| Structured records fully capture all conditions and accurate page provenance. | **FAIL** | Conditions are partial; 15/Law records point to page 1 instead of p.3 and omit qualifications. |
| Different natural phrasings route consistently to the correct condition source. | **FAIL** | Multiple confirmed intent/scope/category mismatches in 8 static probes. |
| Full extraction completeness for every content element in all 7 PDFs. | **BLOCKED / not established** | Token comparison is not visual/layout/OCR completeness audit; no page renders or full semantic audit were performed. |
| Post-fix behavior / final QA approval. | **BLOCKED / not tested** | This is explicitly a pre-fix baseline. |

**Overall baseline verdict: FAIL.** The core eligibility facts are present in page text, so the observed answer failures cannot be attributed simply to those facts being absent from the current JSON. The strongest confirmed causes in this baseline are incomplete/mis-paged structured condition records and question intent/category routing. Lead Coder should fix routing/record provenance upstream; then QA should rerun the natural-language variants against actual retrieval/evidence and inspect final claims against the source pages.

## 7. Handoff to Lead Coder / post-fix QA

After implementation, QA should rerun at minimum the eight routing variants in §4, plus paraphrases for each of: 15-point general eligibility; both transcript formulas; Law and Law Economics conjunctive exception; ≥600 aptitude threshold; H-SCA plus transcript; vocational same-group and cultural-program conditions. Record intent, scope, category filters, retrieval count/results, selected evidence/page provenance, validator status, and final answer. Confirm an answer does not turn the Law exception into a single 18-point condition or imply a numeric H-SCA threshold absent from the PDF. This report is not post-fix approval.
