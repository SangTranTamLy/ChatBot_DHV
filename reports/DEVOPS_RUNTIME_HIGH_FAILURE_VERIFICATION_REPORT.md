# DEVOPS Runtime High-Failure Verification Report

## 1. Scope and verdict

Independent, read-only verification of the local runtime described in `reports/CHATBOT_RUNTIME_HIGH_FAILURE_FIX_REPORT.md`.

**Local runtime readiness: READY.** Ollama, both configured models, the configured Chroma collection, and one default `ask_chatbot` smoke call were available during this check. This is an environment/runtime finding only; it does **not** adjudicate the answer's factual correctness, provide QA sign-off, or declare chatbot answers passed.

No code, configuration, source data, processed data, or Chroma records were intentionally changed. No service was stopped/restarted; no install, model change, rebuild, reset, upsert, or deployment was performed. The only intended workspace addition is this requested report.

## 2. OS and Python/dependency versions

Read-only commands:

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
& .\.venv\Scripts\python.exe -c "import sys, importlib.metadata as m; print('Python:',sys.version.replace(chr(10),' ')); pkgs=['chromadb','langchain','langchain-community','fastapi','streamlit','pydantic','httpx','ollama']; [print(p+': '+(m.version(p) if any(d.metadata['Name'].lower()==p.lower() for d in m.distributions()) else 'not-installed')) for p in pkgs]"
```

Observed:

| Component | Observed version |
|---|---|
| OS | Microsoft Windows 11 Pro, 64-bit; version 10.0.26300, build 26300 |
| Python | 3.12.14 (64-bit, MSC v.1944) |
| chromadb | 1.5.9 |
| langchain | 0.3.30 |
| langchain-community | 0.3.31 |
| streamlit | 1.63.0 |
| pydantic | 2.13.5 |
| httpx | 0.28.1 |
| ollama Python package | 0.6.2 |
| fastapi | not installed in this virtual environment |

These are the selected runtime/retrieval dependencies needed to reproduce the checks, not a full lockfile inventory.

## 3. Ollama health and models

Command/check:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
```

Result: request succeeded. The returned model names included both required models:

- `qwen2.5:3b`
- `nomic-embed-text:latest`

The loaded application settings point to Ollama at `http://localhost:11434`, use `qwen2.5:3b` for generation, and use `nomic-embed-text` for embeddings.

An additional combined request for `/`, `/api/version`, report existence, and `git status --short` did not return output before its shell operation was interrupted. No conclusion is recorded for those auxiliary checks. The required `/api/tags` endpoint succeeded independently and confirmed the available models.

## 4. Active Chroma configuration and read-only audit

The active settings were loaded from `src.config.settings`; the collection was opened with `chromadb.PersistentClient` and queried only with `get_collection`, `count`, and `get(include=['metadatas'])`.

Observed configuration and inventory:

| Field | Observed |
|---|---|
| Persist directory | `C:\Users\Sang\OneDrive\Desktop\ChatBot_DHV\chroma_db` |
| Collection | `dhv_admissions_2026` |
| `count()` | 310 |
| Metadata rows returned | 310 |
| Year | 310 records are `2026`; other years: 0 |
| Status | 310 records are `verified`; other statuses: 0 |
| School | 310 records are `DHV`; other schools: 0 |
| Missing year/status/school/source URL | 0 for each field |
| Source URL scheme | 310 HTTPS; non-HTTPS or missing-host records: 0 |
| Source hosts | `dhv.edu.vn`: 181; `tuyensinh.dhv.edu.vn`: 129 |

Category counts observed: `diem_trung_tuyen` 75; `hoc_bong` 37; `ho_so` 42; `hoc_phi` 1; `lich_tuyen_sinh` 2; `phuong_thuc_xet_tuyen` 15; `nganh_dao_tao` 42; `nguong_dau_vao` 40; `thong_tin_truong` 25; `cach_tinh_diem` 3; `xet_tuyen_bo_sung` 28.

Gate violations observed: year other than 2026 = 0; status other than verified = 0; school other than DHV = 0. This was a metadata/readiness audit, not a factual-content review.

The exact read-only inspection was run from the project's `.venv` with this script body:

```python
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
import json
from src.config.settings import settings
import chromadb
path = Path(settings.chroma_persist_dir).resolve()
name = settings.chroma_collection
client = chromadb.PersistentClient(path=str(path))
col = client.get_collection(name)
rows = col.get(include=['metadatas'])
metas = rows.get('metadatas') or []
keys = ['year', 'status', 'school_code', 'category']
out = {
  'persist_path': str(path), 'collection': name,
  'count_api': col.count(), 'records_returned': len(metas),
  'metadata_values': {key: dict(Counter(str(m.get(key)) for m in metas)) for key in keys},
  'missing_metadata': {key: sum(1 for m in metas if not m.get(key)) for key in ['year','status','school_code','source_url']},
  'source_schemes': dict(Counter((urlparse(str(m.get('source_url') or '')).scheme or 'missing') for m in metas)),
  'source_hosts': dict(Counter((urlparse(str(m.get('source_url') or '')).hostname or 'missing').lower() for m in metas)),
  'non_https_source_records': sum(1 for m in metas if urlparse(str(m.get('source_url') or '')).scheme.lower() != 'https' or not urlparse(str(m.get('source_url') or '')).hostname),
  'gate_violations': {
    'year_not_2026': sum(1 for m in metas if str(m.get('year')) != '2026'),
    'status_not_verified': sum(1 for m in metas if str(m.get('status','')).lower() != 'verified'),
    'school_not_DHV': sum(1 for m in metas if str(m.get('school_code','')).upper() != 'DHV')
  }
}
print(json.dumps(out, ensure_ascii=False, indent=2))
```

## 5. `ask_chatbot` smoke check

The entrypoint signature was inspected without changing it:

```powershell
& .\.venv\Scripts\python.exe -c "import inspect; from src.chatbot.rag_chain import ask_chatbot; print(inspect.signature(ask_chatbot))"
```

It exposes `ask_chatbot(question, *, retriever=None, llm=None, ..., settings_obj=...)`; loaded settings pointed at the active Chroma path/collection and local Ollama models above.

Smoke call used the default path (no fake retriever or fake LLM):

```powershell
$env:PYTHONIOENCODING = 'utf-8'; & .\.venv\Scripts\python.exe -c "from src.chatbot.rag_chain import ask_chatbot; r=ask_chatbot('DHV có những phương thức xét tuyển nào?'); t=r['trace']; print('status:',r.get('status')); print('intent:',t.get('intent')); print('target_school:',r.get('target_school')); print('scope_reason:',r.get('scope_reason')); print('retrieval_calls:',t.get('retrieval_calls')); print('retrieved_docs_count:',t.get('retrieved_docs_count')); print('evidence_count:',t.get('evidence_count')); print('final_status:',t.get('final_status')); print('sources:',r.get('sources'))"
```

Observed trace summary:

```yaml
status: ok
intent: HOI_PHUONG_THUC_XET_TUYEN
target_school: DHV
scope_reason: in_scope_dhv
retrieval_calls: 1
retrieved_docs_count: 15
evidence_count: 15
trace.final_status: ok
source_host: tuyensinh.dhv.edu.vn
```

The runtime returned an answer and source URL. This confirms the local request path completed; it is **not** an assessment that the listed methods, wording, evidence sufficiency, or URL attribution are factually correct. Those remain QA responsibilities.

The first smoke invocation completed the chatbot call but failed while writing Vietnamese output to the Windows `cp1252` console (`UnicodeEncodeError`). It was rerun with `PYTHONIOENCODING=utf-8` and produced the trace above. This is a console encoding issue, not an Ollama/Chroma availability failure.

## 6. Configuration discovery and command notes

The source/config discovery command was:

```powershell
rg -n --glob "*.py" --glob "*.toml" --glob "*.yaml" --glob "*.yml" --glob "*.json" "dhv_admissions_2026|CHROMA.*(PATH|DIR|COLLECTION)|persist_directory|PersistentClient|collection_name" src config .
```

It located configuration in `src/config/settings.py` and the active connection in `src/retrieval/retriever.py`; `rg` also emitted a non-fatal error because the optional path `config` does not exist. Runtime values were confirmed from the loaded settings object and active collection, not inferred from the scan.

An initial shell launch was blocked by `CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)`. The read-only checks later ran successfully in an approved local shell. This launcher issue did not indicate an Ollama outage.

## 7. Change and side-effect statement

- No code, config, model, corpus, or expected-result file was edited.
- No Chroma rebuild, reset, upsert, or deletion command was run.
- No Ollama process/service was started, stopped, or restarted; requests were sent to the already-running local endpoint.
- No package was installed or upgraded; no deployment was performed.
- This verification report is the only intended file addition for this task. A combined `git status --short` check did not complete, so unrelated pre-existing worktree dirtiness was not adjudicated.

## 8. DevOps/SRE conclusion

**LOCAL_RUNTIME_READY at the time of verification.** Ollama's model-list endpoint responded, both required models were present, the configured 310-record Chroma collection opened with all inspected metadata gates satisfied, and a real default `ask_chatbot` smoke call completed with status `ok`.

This is strictly a local runtime/environment conclusion. It is **not** a QA verdict, does not certify answer correctness or grounding, and does not claim a full sweep or production readiness.
