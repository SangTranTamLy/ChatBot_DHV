# DEVOPS / SRE REPORT — Admission Conditions Runtime Audit

## 1. Deployment Target

- Target inspected: local development environment on Windows.
- Deployment performed: no.
- This task was limited to a read-only runtime/environment audit. No chatbot questions were submitted.

## 2. Pre-deployment Checks

- QA status: not assessed by this environment-only task; no deployment requested or performed.
- Runtime configuration: loaded through the project's `src.config.settings.settings` object. Only non-secret effective values are recorded below; no secret values were printed.
- Relevant services: Ollama HTTP health and model listing checked; active Chroma SQLite database inspected using SQLite URI `mode=ro`.
- Ports: configured Ollama endpoint `http://localhost:11434` responded successfully.

## 3. Environment

- Python: `3.12.14` (`.venv`).
- OS: `Windows-11-10.0.26300-SP0`.
- Deployment platform: local development; no deployment.
- Ollama executable: `C:\Users\Sang\AppData\Local\Programs\Ollama\ollama.exe`, process present during inspection.
- Ollama endpoint: `http://localhost:11434`.
- Chat model configured: `qwen2.5:3b`.
- Embedding backend/model configured: `ollama` / `nomic-embed-text`.
- Ollama timeout: `90.0` seconds.
- Chroma active persistence path: `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db`.
- Chroma active collection: `dhv_admissions_2026`.
- Configured processed-data path: `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\data\processed`.
- Configured target year: `2026`.
- Configured retriever top-k: `4`.
- RAG maximum context size: `12000` characters.
- Installed relevant package versions: `chromadb 1.5.9`, `ollama 0.6.2`, `langchain-chroma 0.2.6`, `langchain-ollama 0.3.10`, `python-dotenv 1.2.3`.

## 4. Deployment Steps

None. No deployment or service restart was performed.

## 5. Health Checks

### Ollama

- `GET http://localhost:11434/` via Python `urllib`: **HTTP 200**, body `Ollama is running`.
- `GET http://localhost:11434/api/tags` via Python `urllib`: **HTTP 200**.
- `ollama list`: succeeded and listed:
  - `nomic-embed-text:latest` (274 MB; embedding length reported by tags API: 768).
  - `qwen2.5:3b` (1.9 GB).
- `GET http://127.0.0.1:11434/api/tags` via PowerShell `Invoke-RestMethod`: succeeded and returned the same two models.

### Chroma (read-only inspection)

- The configured database file `chroma_db/chroma.sqlite3` exists (4,141,056 bytes at inspection time).
- SQLite was opened with `mode=ro`; no Chroma client, ingestion, or write operation was used.
- Configured collection `dhv_admissions_2026` exists; collection dimension is `768`.
- Active collection record count: **281**.
- Metadata coverage across all 281 records:
  - `year=2026`: 281.
  - `status=verified`: 281.
  - `school_code=DHV`: 281.
  - Source hosts: `dhv.edu.vn` 134 records; `tuyensinh.dhv.edu.vn` 147 records.
  - Categories: `diem_trung_tuyen` 71; `nganh_dao_tao` 42; `nguong_dau_vao` 40; `hoc_bong` 37; `thong_tin_truong` 27; `xet_tuyen_bo_sung` 27; `phuong_thuc_xet_tuyen` 21; `ho_so` 12; `cach_tinh_diem` 2; `hoc_phi` 1; `lich_tuyen_sinh` 1.
- This verifies configured collection metadata and counts only. It does not verify factual completeness, retrieval relevance, or answer quality.

## 6. Smoke Tests

- No chatbot/runtime question was submitted, by instruction.
- No embedding request or generation request was sent. Ollama checks were health/model-list calls only.

## 7. Logs / Errors

- PowerShell `Invoke-WebRequest http://localhost:11434/` returned a client-side `Object reference not set to an instance of an object` error. This was not reproduced using Python `urllib`; the same endpoint returned HTTP 200 and `Ollama is running`. `/api/tags` also returned HTTP 200. The evidence indicates a PowerShell wrapper/client error rather than an Ollama health failure.
- No Ollama process, port, or SQLite read error was observed.
- The active Chroma collection contains **281**, not 310, records. This is a count discrepancy versus earlier project/QA notes; this audit does not determine when or why the active collection changed. It is reported for Lead/QA awareness, not classified as an environment outage.

## 8. Security / Secret Checks

- Effective settings were obtained from the project's settings loader.
- No `.env` secret values, credentials, or tokens were emitted in command output or this report.
- Chroma was inspected read-only. No user question or sensitive query was submitted.

## 9. Rollback Status

- Not applicable: no changes, database mutation, model changes, service restart, or deployment occurred.

## 10. Final Verdict (Environment Only)

**ENVIRONMENT_HEALTHY_WITH_CHROMA_COUNT_DISCREPANCY**

Ollama is reachable and both configured models are available. The configured Chroma collection exists and its records consistently carry the expected year, verification status, school code, and official DHV source hosts. However, its active count is 281; reconcile this with the 310-record figure in prior notes before relying on those earlier counts. This verdict is not a QA/product correctness verdict and does not certify answer completeness.

Explicitly: **no deploy, no Chroma/DB mutation or rebuild, no source/business-logic changes.**
