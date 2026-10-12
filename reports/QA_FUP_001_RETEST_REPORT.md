# QA-FUP-001 Independent Retest Report

## Verdict

**BLOCKED — independent verification was not performed.** No PASS/FAIL conclusion about the product fix is justified by this run.

## Scope and restrictions

Requested audit: independently determine whether QA-FUP-001 is fixed for standalone accented/unaccented institute/faculty website questions, missing verified unit URLs, and explicit compound overview + unit website questions. QA/Security-only restrictions were followed: no source, tests, data, prompts, settings, or Chroma were intentionally modified; no Chroma write/rebuild and no deployment were performed.

## Required materials and snapshot inspection

Could not read or inspect:

- `reports/TONG_QUAN_AGENT`
- `reports/QA_CHATBOT_PLAN_FOLLOWUP_RETEST_REPORT.md`
- `reports/CHATBOT_QA_FUP_001_LEAD_REVALIDATION_REPORT.md`
- Relevant current source/tests or working-tree status

The first attempt to read the required reports and the second attempt using an explicit PowerShell executable both failed before the process started:

```text
MXC launcher: failed to create the process security environment:
CreateProcessSecurityEnvironment failed (HRESULT = 0x80070020)
```

This is an environment/process-launch blocker, not evidence of a product failure or pass. The current snapshot, report contents, and Lead revalidation accuracy therefore remain unverified.

## Required behavior and verification status

| Scenario | Expected | Actual in this QA run | Result |
|---|---|---|---|
| Standalone accented institute website query | Only `HOI_CO_SO_LIEN_HE`; if no verified unit URL, `no_data`, no sources, no unrelated overview | Not executed; source and runtime unavailable | BLOCKED |
| Standalone unaccented institute website query | Same as above | Not executed | BLOCKED |
| Standalone accented faculty website query | Only `HOI_CO_SO_LIEN_HE`; if no verified unit URL, `no_data`, no sources, no unrelated overview | Not executed | BLOCKED |
| Standalone unaccented faculty website query | Same as above | Not executed | BLOCKED |
| Explicit compound overview + unit website | Both issues retained; missing unit URL must not be replaced by unrelated overview or another URL | Not executed | BLOCKED |

No question trace was produced; consequently `target_school`, `scope_reason`, `intent`, retrieval calls, retrieved document count, evidence count, status, and sources are **unknown**, not zero.

## Tests and runtime

- Read-only inspection command: attempted `Get-Content -Raw` for the three required reports; **process launch failed**, no files were read.
- Alternate process-launch attempt: `Get-Location` via explicit `powershell.exe`; **same launcher error**.
- Focused tests: **not run**.
- Relevant targeted suites: **not run**.
- Live default runtime: **not attempted**, because the workspace process launcher failed before inspection or test setup. This is an environment blocker, not a chatbot runtime result.
- Test counts: **unavailable**; no Lead-reported counts are represented as QA results.

## Findings and severity

1. **QA execution blocked — severity: blocker.** The Windows process security environment could not be created (`0x80070020`), preventing the required independent source review and test execution.
2. **QA-FUP-001 product status — undetermined.** No evidence was available in this run to confirm or refute the Lead revalidation.

## Mutations

No source code, tests, data, prompts, settings, or Chroma were changed. No Chroma write/rebuild and no deployment occurred. This required QA report is the only intended artifact written by this run.

## Required next step

Rerun this independent audit after the workspace process-launch issue is cleared. Read the three required reports and relevant current source/tests, execute the exact standalone accented/unaccented institute/faculty queries and compound overview + unit website cases, run focused and relevant targeted suites, and attempt the live default runtime if available. Record each trace and final evidence/source boundary before assigning PASS or FAIL.
