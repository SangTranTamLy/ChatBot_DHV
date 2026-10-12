# Security Review — Remaining Runtime Fix

## Verdict: BLOCKED

Read-only review of the current dirty diff and active local runtime. No source, data, Chroma, or deployment changes were made. The current indexed corpus and tested requests showed no 2024/2026 mixing or external-school retrieval. However, runtime provenance checks are weaker than the canonical ingestion gate, so the review cannot confirm the stronger invariant that inconsistent/unverified evidence can never pass downstream.

## Findings

### F-01 — Runtime accepts inconsistent verification metadata and HTTP provenance

**Severity: MEDIUM (defense-in-depth; not reproduced in the active collection).**

- `src/ingestion/loader.py:101-115` correctly admits only `status == "verified"` and `verified is True`, then invokes full structured-document validation.
- `src/ingestion/structured_json.py:1821-1835` requires `verification_status == "verified"` and `verified is True` for verified records, and `is_official_dhv_url()` requires HTTPS.
- After indexing, `src/retrieval/retriever.py:320-343`, `src/chatbot/evidence.py:260-282`, and `src/chatbot/output_validator.py:254-276` check `status`, year, school code and source host, but do not re-check `verification_status` (or the source `verified` boolean). Their official-URL helpers accept both `http` and `https` (`retriever.py:306-317`, `output_validator.py:241-252`; evidence uses `_valid_http_url`).
- Therefore a stale/manually altered Chroma record with `status="verified"` but `verification_status="unverified"`, or with an HTTP DHV URL, could pass these runtime filters if it bypassed canonical ingestion. This metadata combination was **not present** in the active collection; all current chunks had both verification fields set to verified and HTTPS official DHV source URLs.

**Required before claiming the invariant:** align retriever, evidence selection and output validation with the ingestion provenance contract (consistent verification fields and HTTPS-only official source URLs), with regression tests using synthetic inconsistent metadata. No fix was applied in this review.

## Verified Invariants / Trace Results

### Year isolation

- `src/chatbot/rag_chain.py:5844-5870` resolves the explicit requested year, inherits state year only for a relevant follow-up, otherwise uses configured year, and creates request-specific settings before routing/retrieval.
- `src/retrieval/retriever.py:293-304, 320-343` applies an exact year metadata filter and independently rejects year mismatches. `src/chatbot/evidence.py:260-282` and `src/chatbot/output_validator.py:254-276` repeat the exact-year check.
- The configured vector collection is named `dhv_admissions_2026`, but its current 282 chunks comprise 281 for 2026 and 1 for 2024. The name is potentially misleading; the per-request metadata filter is what isolates years.
- Read-only audit found 282/282 chunks marked verified, verification_status verified, school_code DHV, and with an official source URL. All seven processed-document hashes matched their active Chroma source hashes; each processed source hash also matched its current raw PDF hash.
- Live Ollama + Chroma trace for “Học phí DHV năm 2024 bao nhiêu?”: status `ok`, exact year/category filter `{year: 2024, category: hoc_phi}`, 1 retrieved document, 1 evidence item, selected year only `2024`; answer cited 1.100.000 VNĐ/tín chỉ.
- Live Ollama + Chroma trace for “Học phí DHV năm 2026 bao nhiêu?”: status `ok`, exact year/category filter `{year: 2026, category: hoc_phi}`, 1 retrieved document, 1 evidence item, selected year only `2026`; answer cited the 2026 HKI 10-credit amount.
- “Điểm chuẩn DHV năm 2027?” returned `no_data`, zero retrieved documents/evidence, with no fallback to 2026.

### School boundary

- `src/chatbot/rag_chain.py:5872-5892` returns the external/mixed/ambiguous school boundary result before constructing or calling the retriever.
- A local runtime trace for “Điểm chuẩn Văn Hiến năm 2026?” returned `target_school=OTHER_SCHOOL`, `scope_reason=external_school`, `status=out_of_scope`, retrieval calls 0, retrieved documents 0, evidence 0. The boundary path did not invoke embedding or answer generation.
- Targeted external/mixed/ambiguous regression tests passed; no external-school evidence was observed.

### Index construction

- `src/ingestion/build_vector_db.py:255-269` defaults to the configured target year, permits an explicit `--year`, or permits `--all-years`; ingestion still goes through `load_verified_documents`.
- `src/ingestion/loader.py:101-115` applies the year gate and verification gate before loading records. `src/ingestion/structured_json.py:1788-1835` validates source URLs and verification consistency.
- This review did not rebuild or write to Chroma.

## Tests Actually Run

| Run | Result |
|---|---|
| Focused year/scope/ingestion/security regression selection | **49 passed; 50 subtests passed** |
| Broader targeted invocation including temp-file cases | **63 passed; 42 subtests passed; 5 failed** — all five failures were Windows `WinError 5` temp-directory create/cleanup ACL errors, not assertion failures |
| Retry with temp variables pointed at project `.test_tmp` | Same 5 Windows ACL failures; no assertion failures |
| Full pytest | **Not run** |
| Live local Ollama + active Chroma | 2024 and 2026 tuition queries succeeded with year-isolated evidence; external-school and unsupported-year checks produced zero evidence as expected |

## Handoff

QA/Security should rerun the 49 focused tests and add synthetic Chroma/evidence cases where `status` conflicts with `verification_status`/`verified`, and where the source is `http://dhv.edu.vn/...`. Re-review the runtime gates after that hardening. The current active corpus is clean, but this review is **BLOCKED** on the downstream provenance-contract gap above. No deployment was performed.
