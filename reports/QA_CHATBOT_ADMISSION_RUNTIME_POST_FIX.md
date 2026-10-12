# QA & Security Post-Fix Review — Admission Runtime

## Verdict: BLOCKED — live runtime QA is Lead-running; static/data review completed

This is a read-only QA handoff record. Static/source and PDF/JSON checks plus local regression tests are complete. The live Ollama/Chroma matrix is assigned to Lead and remains **BLOCKED-not-run by QA**. This is **not** a full-project QA pass and does not certify live post-fix behavior.

## Initial subagent execution blocker (superseded by follow-up below)

The workspace command launcher could not create a Windows process during this review. PowerShell, CMD, and the Node workspace runtime all failed before executing with:

```text
MXC launcher: failed to create the process security environment:
CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)
```

Consequently, this review could not inspect the current working tree, rerun pytest, query live Ollama/Chroma, or independently verify the current collection count. No source, test, processed data, PDF, or Chroma files were changed by this review. No deployment was performed.

## Baseline context (not independently revalidated in this review)

The earlier baseline report records seven processed JSON/PDF pairs and 34 total pages. The environment report available in prior task context reported active collection `dhv_admissions_2026` with 281 records. Earlier runtime notes in the task history also mentioned 310 records. This is an unresolved count discrepancy; the active collection must be queried directly before QA can state the authoritative count.

## Required query-by-query trace

All cases below are **BLOCKED — NOT RUN in this review**. Therefore the fields requested by QA (intent, target school/scope, categories, retrieval counts, evidence count, validator/final status, answer excerpt and source URL) are unavailable and must not be inferred from earlier Lead-Coder traces.

| # | Exact question | Required result to verify | Post-fix QA result |
|---|---|---|---|
| 1 | `Xét bằng điểm thi tốt nghiệp thì ba môn chọn như thế nào?` | Both documented subject-combination rules | BLOCKED — no fresh trace |
| 2 | `ĐGNL cần bao nhiêu điểm để đăng ký?` | Verified threshold “từ 600”; not generic no-data | BLOCKED — no fresh trace |
| 3 | H-SCA numeric-threshold query | Must not reuse the ĐGNL 600 threshold; safe no-data if no numeric source | BLOCKED — exact query/trace unavailable |
| 4 | `Học lực lớp 12 Khá, 20 điểm thì đủ xét ngành Luật không?` | Explain the evidenced grade condition without unsupported inference or unnecessary clarification | BLOCKED — no fresh trace |
| 5 | `Đợt xét tuyển bổ sung nhận hồ sơ đến ngày nào?` | 21/8/2026, supported by source | BLOCKED — no fresh trace |
| 6 | General eligibility paraphrase | Source-grounded eligibility conditions | BLOCKED — no fresh trace |
| 7 | Transcript three-year formula | Preserve both formulas/conditions from the verified source | BLOCKED — no fresh trace |
| 8 | CNTT transcript threshold | Correct DHV evidence and threshold | BLOCKED — no fresh trace |
| 9 | Enrollment documents | Complete relevant verified checklist | BLOCKED — no fresh trace |
| 10 | Scholarship list | No missing or duplicated policy headings | BLOCKED — no fresh trace |
| 11 | `Điểm chuẩn Văn Hiến?` | External school boundary; retrieval/evidence = 0 | BLOCKED — no fresh trace |
| 12 | Website-count question | Correct verified website count and URLs | BLOCKED — runtime availability unverified |

## Initial subagent test status (superseded by follow-up below)

No tests ran in this review because the process launcher failed before a command could start. The intended focused command was:

```powershell
$env:TEMP = (Resolve-Path .test_tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\pytest.exe -p no:cacheprovider tests/test_admission_conditions.py tests/test_intent_classifier.py tests/test_priority_1_2_fix.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_query_decomposer.py tests/test_full_sweep_p1.py
```

Result: **BLOCKED — command did not execute**. No pass/fail count is claimed.

## Initial subagent PDF audit status (superseded by follow-up below)

Per request, extraction was not repeated. The earlier baseline states seven pairs / 34 pages, but the files and page counts could not be re-opened or compared in this review. Pair integrity is therefore **NOT REVALIDATED** here.

## Initial handoff note (updated by follow-up below)

After the workspace process launcher is available, QA must:

1. Inspect `git status` and the current diff read-only; confirm no unrelated or disallowed changes were introduced.
2. Run the focused pytest command above and record exact counts.
3. Confirm Ollama availability and directly inspect the active Chroma collection count, metadata distribution (year/status/school/source), and collection name.
4. Run every exact query in the table through the live production runtime and record all requested trace fields, including answer excerpts and source URLs.
5. Reconcile the reported 281-versus-310 collection count before issuing a QA verdict.
6. Keep any unavailable live-runtime case marked BLOCKED, not PASS.

This report is an execution-blocker record only. It does not accept or reject the implementation itself.

## Independent follow-up completed (2026-10-12)

Scope was updated by the user: Lead runs the live Ollama/Chroma query matrix; QA does not duplicate it. Thus the live matrix remains **Lead-running / BLOCKED-not-run by QA**. No live answer, source, trace, or collection count is certified here.

### Diff/source and local test review

Inspected read-only diffs in `src/chatbot/query_analysis.py`, `src/chatbot/rag_chain.py`, `tests/test_admission_conditions.py`, and `tests/test_full_sweep_p1.py`. Changes match the described scope: three-subject combination parsing; method-specific threshold routing; evidence-backed threshold and Law eligibility helpers; deadline paraphrase recognition; scholarship top-k 96; regression tests. No evaluation dataset edits were present in this inspected diff. `git diff --check` passed (Git printed only LF/CRLF normalization warnings).

Independent targeted regression run:

```powershell
$env:TEMP=(Resolve-Path '.test_tmp').Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m pytest tests/test_admission_conditions.py tests/test_intent_classifier.py tests/test_priority_1_2_fix.py tests/test_phase2_runtime.py tests/test_phase4_answer_behavior.py tests/test_query_decomposer.py tests/test_full_sweep_p1.py tests/test_runtime_enrollment.py tests/test_task_j.py tests/test_task_l.py tests/test_task_c.py -q -p no:cacheprovider
```

**204 passed, 161 subtests passed, 0 failed** in 27.87 seconds. This is local regression evidence only, not live RAG/LLM acceptance.

Review gaps: live outputs still need to verify personal 720-point questions are not turned into admission decisions; H-SCA does not borrow the ĐGNL threshold; complete scholarship list survives top-k 96; deadline and conditions are retrieved from the expected verified sources. The code's DGNL threshold helper requires a verified official DHV source chunk plus one verified `nguong_dau_vao` fact, and has no numeric H-SCA fallback. Production behavior remains unverified until Lead returns traces.

### PDF/processed JSON pair audit

Read-only audit found seven exact filename pairs and **34/34 matching pages**. Every page had non-empty JSON `pages[].text`; normalized text-layer tokens from `pypdf` were all present in corresponding JSON page text (token coverage 1.000 on each page). JSON extraction metadata reports native text for all pages, zero OCR pages, and no warnings. This validates text presence/page coverage, not visual reading order or factual/table semantics.

| Document | Pages | Records | Structured tables | Structured lists | Provenance |
|---|---:|---:|---|---|---|
| V1_DIEM_TRUNG_TUYEN_DHV_2026 | 2 | 69 | 2 / 23 rows / 138 cells | 0 | Verified; official DHV URL |
| V1_HO_SO_VA_THU_TUC_NHAP_HOC_DHV_2026 | 7 | 10 | 5 / 56 rows / 124 cells | 8 / 25 items | Verified; official DHV URL |
| V1_HOC_PHI_DHV_2024 | 1 | 1 | 0 | 2 / 2 items | **missing_source_url; verified=false** |
| V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026 | 8 | 94 | 3 / 20 rows / 60 cells | 15 / 33 items | Verified; official tuyển sinh URL |
| V1_THONG_TIN_TRUONG_DHV | 7 | 1 | 0 | 20 / 50 items | Verified URL; `source_type=unknown` |
| V1_TONG_QUAN_TUYEN_SINH_DHV_2026 | 7 | 32 | 3 / 20 rows / 60 cells | 9 / 25 items | Verified; official tuyển sinh URL |
| V1_XET_TUYEN_BO_SUNG_DHV_2026 | 2 | 24 | 2 / 12 rows / 72 cells | 1 / 2 items | Verified; official DHV URL |
| **Total** | **34** | **231** | **15 / 131 rows / 454 cells** | **55 / 137 items** | 6 verified; 1 unverified |

The JSONs preserve source metadata at document level: raw filename/path, SHA-256, source URL(s), organization, school code, verification state, and collection date. Record rows do not repeat those fields. The 2024 tuition file remains ineligible as verified evidence until provenance is resolved; no change to the file or manifest was made. `V1_THONG_TIN_TRUONG_DHV` has `source_type=unknown` despite a DHV URL and verified flag; clarify this classification with the data owner.

### Live cases: Lead-running / BLOCKED-not-run by QA

| Case | QA status |
|---|---|
| Three-subject formula question | Lead-running / BLOCKED-not-run |
| “ĐGNL cần bao nhiêu điểm để đăng ký?” | Lead-running / BLOCKED-not-run |
| H-SCA numeric threshold / no borrowing 600 | Lead-running / BLOCKED-not-run |
| Personal 720 ĐGNL question | Lead-running / BLOCKED-not-run |
| Law: grade 12 Khá and 20 points | Lead-running / BLOCKED-not-run |
| Supplementary deadline 21/8/2026 | Lead-running / BLOCKED-not-run |
| External school retrieval=0 | Lead-running / BLOCKED-not-run |
| Enrollment, scholarship, cutoff, and general eligibility | Lead-running / BLOCKED-not-run |

Earlier notes cite active collection counts of both **281** and **310**. Since the user assigned live Ollama/Chroma matrix to Lead, QA did not query the collection; the discrepancy is still an acceptance gap and needs Lead's direct audit.

### Handoff / acceptance gaps

Lead should append exact per-query `intent`, school/scope, categories, retrieval calls/docs, evidence count, validator/final status, answer excerpt, and source URL; directly inspect active collection count and its year/status/school/source metadata; and keep any unavailable live case marked BLOCKED. QA must then independently judge factual correctness. This follow-up does not issue a QA PASS or project-wide pass.
