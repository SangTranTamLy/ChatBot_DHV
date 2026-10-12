# QA-FUP-001 Lead Revalidation Report

## 1. Scope

Revalidated the QA finding that a specific faculty/institute website request could add an unrelated DHV overview section. This is a Lead Coder verification report, not an independent QA verdict.

## 2. Finding and Current Code

QA-FUP-001 reported that `website Viện Đào tạo Sau đại học?` was routed as `MULTI_ISSUE` with `HOI_CO_SO_LIEN_HE` and `SCHOOL_INFO`, causing a generic overview to appear despite the requested institute URL being absent from verified evidence.

The current working tree contains a specific-unit website detector in `src/chatbot/query_analysis.py`. It distinguishes a request for a named faculty/institute website from a generic school overview, while preserving an overview subplan when the user explicitly asks for both. Regression tests in `tests/test_task_09.py` cover institute and faculty names with and without diacritics, plus the explicit overview + unit website compound.

## 3. Verification

### Focused tests

Command:

```powershell
$env:TEMP=(Resolve-Path .test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest -q tests/test_task_09.py -k "specific_school_unit_website or missing_school_unit_website"
```

Result: **2 passed, 21 deselected, 4 subtests passed**.

### Default chatbot runtime traces

The exact QA query and two controls were run through the current `ask_chatbot` default path:

| Query | Intent | Status | Retrieval / docs / evidence | Sources | Unrelated overview |
|---|---|---|---:|---|---|
| `website Viện Đào tạo Sau đại học?` | `HOI_CO_SO_LIEN_HE` | `no_data` | 1 / 25 / 25 | Empty | No |
| `website Vien Dao tao Sau dai hoc?` | `HOI_CO_SO_LIEN_HE` | `no_data` | 1 / 25 / 25 | Empty | No |
| `website Khoa Kỹ thuật Công nghệ là gì?` | `HOI_CO_SO_LIEN_HE` | `no_data` | 1 / 25 / 25 | Empty | No |

Each response used the boundary `requested_website_not_in_verified_evidence`. No institute/faculty URL was fabricated or replaced with the general DHV URL. The current verified corpus does not support these specific unit websites, so `no_data` with no source is the expected fail-closed result.

### Full regression

Command: `.venv\\Scripts\\python.exe -m pytest -q`, with `TEMP` and `TMP` directed to the existing workspace `.test_tmp` because of Windows temporary-directory ACL behavior.

Result: **295 passed, 4 skipped, 0 failed; 303 subtests passed**.

## 4. Changes Made in This Revalidation

No source, test, data, prompt, or Chroma changes were needed: the current working tree already contains the QA-FUP-001 routing guard and regression tests. This report records their verification against the QA repro. No Chroma rebuild or deployment was performed.

## 5. Remaining Risks and Handoff

- The exact QA-FUP-001 behavior passes in the current checkout, but QA/Security must independently inspect the current diff and rerun the regression before the project can be considered complete.
- The official website of the requested institute/faculty is absent from verified evidence. The chatbot correctly returns `no_data`; adding that URL requires an independently verified source and is outside this fix.
- This report does not claim a full Ollama planner/generation E2E or a 500-question QA sweep.

## 6. Lead Verdict

**READY_FOR_QA** — the current code passes the targeted repro and full local regression. This is not QA PASS and does not authorize deployment.
