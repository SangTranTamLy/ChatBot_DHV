# REMAINING RUNTIME FIX REPORT

## 1. Scope

Addressed the remaining confirmed runtime/data regressions in the current working tree:

- allow an explicitly requested year to retrieve only verified evidence for that year;
- preserve the configured year for new, unspecified questions and inherit a prior year only for a relevant follow-up;
- normalize structured table headers consistently and retain continued-table headers only when source/layout evidence supports it;
- align the program catalog aliases with source spellings and keep adjacent table lines as separate entries unless the PDF marks them as one title.

No deployment, dataset evaluation edits, Chroma rebuild, or RAW PDF edits were performed.

## 2. Confirmed Root Causes

1. `ask_chatbot()` previously returned `no_data` immediately whenever an explicit year differed from `settings.target_year`. This made verified historical-year data unreachable even when the matching data was present in the active collection.
2. Structured table-header parsing normalized actual newline characters but not literal escaped `\\n`/`\\r` sequences, allowing table headers, cell labels, and row keys to diverge.
3. A table continuation guard treated an explicitly inspected empty native-block list as unknown content and rejected otherwise well-aligned continuation tables.
4. Catalog regression expectations had truncated spellings and combined three adjacent PDF lines into compound names without a visible joining mark.

## 3. Implementation

- Resolve the requested year before routing. An explicit year is used for that request; a prior year is inherited only when `should_inherit_context()` approves the follow-up; otherwise the configured default year is retained.
- Bind the selected year into the request settings, analysis entities, conversation state, routing and retrieval filters. The existing verified/source/school gates remain in force.
- Add 2024/2026 isolation tests and ensure unsupported 2027 does not call the answer LLM when there is no matching evidence.
- Normalize escaped table-header line breaks while keeping page text and cell values intact; synchronize table headers, row-data keys, cell headers and table element labels.
- Permit continued-header inheritance for an explicitly empty inspected block list only when the existing layout/adjacency/column checks support continuation. Tests now distinguish detected source headers from genuinely inherited headers.
- Correct the source-backed table-page assertion: the two enrollment support tables are on PDF pages 5 and 6, one on each page.
- Align program aliases with full canonical names and update the visible table audit to 50 separate entries. This does not settle the PDF prose claim “more than 50”; see Remaining Risks.

## 4. Files Changed / Integrated

| File | Change area | Attribution / reason |
|---|---|---|
| `src/chatbot/rag_chain.py` | Per-request target year selection | Lead change in this continuation; removes the blanket explicit-year mismatch rejection and applies exact request-year routing. |
| `tests/test_task_c.py` | Multi-year runtime tests | Lead change; proves 2024 and 2026 evidence do not cross and 2027 does not reach answer generation without evidence. |
| `tests/test_data_pipeline_recovery.py` | 2024 provenance/loader assertions | Lead change; aligns regression assertions with the current verified 2024 manifest entry and loader year filter. |
| `tests/test_task_m.py` | Manifest-year acceptance | Lead change; allows the single verified 2024 tuition document only with the expected document ID/category and official source. |
| `tests/test_task_processed_md_to_json_migration.py` | Loader statistics | Lead change; distinguishes verified documents for the configured year from verified documents skipped for another year. |
| `tests/test_task_pdf_to_structured_json.py` | Source/page assertions | Lead correction; checks one table on each of PDF pages 5 and 6. Other table-normalization and continuation changes in this file were already present in the working tree. |
| `tests/test_task_g.py` | Catalog count assertion | Lead correction; updates the stale visible-table count assertion from 47 to 50. Other catalog alias changes were already present in the working tree. |
| `src/chatbot/query_analysis.py` | Catalog aliases | Existing in-tree change reviewed/integrated; maps truncated user aliases to canonical source names and keeps ambiguous adjacent lines separate. |
| `src/ingestion/structured_json.py` | Table header normalization | Existing in-tree change reviewed/integrated; normalizes literal escaped line breaks consistently across structured fields. |
| `src/ingestion/prepare_processed_from_raw.py` | Continued table headers | Existing in-tree change reviewed/integrated; uses explicit empty-block and layout evidence for safe inheritance. |
| `src/ingestion/build_vector_db.py`, `tests/test_ingestion.py` | Multi-year build CLI | Existing in-tree change reviewed/integrated; adds opt-in `--all-years` while retaining verified/source gates. It was not used to rebuild the active collection. |

The 2024 source entry in `data/raw/manifest.json` was already modified in the working tree before this runtime-fix continuation. It now points to the official DHV tuition commitment page and marks the source verified. This task did not author or rewrite that manifest entry. The corresponding processed JSON and active Chroma record were also already present; no processed JSON or Chroma mutation was made here.

## 5. Chroma Freshness / Safety

Read-only audit of active collection `dhv_admissions_2026`:

| Check | Result |
|---|---:|
| Total chunks | 282 |
| Year 2026 | 281 |
| Year 2024 | 1 |
| Verified status | 282/282 |
| School code DHV | 282/282 |
| Distinct source hashes | 7 |

No 2024 document is used for a 2026 request because retrieval is filtered by the resolved target year. No collection rebuild/reset occurred.

## 6. Runtime Traces (Real Ollama + Active Chroma)

| Query | Intent / year | Retrieval / docs | Evidence | Result |
|---|---|---:|---:|---|
| `Học phí DHV năm 2024 bao nhiêu?` | `HOI_HOC_PHI`, 2024 | 1 / 1 | 1 | `ok`; answer gives 1,100,000 VNĐ/tín chỉ, official DHV source. |
| `Học phí DHV năm 2026 bao nhiêu?` | `HOI_HOC_PHI`, 2026 | 1 / 1 | 1 | `ok`; answer uses 2026 HKI 10-credit tuition evidence, no 2024 figure. |
| `Học phí DHV năm 2027 bao nhiêu?` | `HOI_HOC_PHI`, 2027 | 1 / 0 | 0 | `no_data`; no source and no answer LLM generation. |

Runtime used `qwen2.5:3b`, `nomic-embed-text`, and the active collection. No factual answer was hard-coded.

## 7. Tests

| Suite / command | Result |
|---|---|
| Focused seven-file regression set (`task_c`, recovery, task_m, migration, task_f, task_g, structured JSON) | 98 passed, 143 subtests passed. |
| `pytest tests -q -p no:cacheprovider` using the Windows system Temp directory | **359 passed, 4 skipped, 335 subtests passed** in 31.81s. |
| `git diff --check` | Passed; only line-ending conversion notices. |
| Initial full test discovery using project `.test_tmp` | Environment failure: pytest encountered an ACL-denied temporary directory before test collection; the run was repeated successfully with the Windows system Temp directory. |

## 8. Remaining Risks

- The source PDF's introduction says it offers “more than 50” programs, while the visible catalog table has 50 separate lines. Three pairs of adjacent lines have no printed hyphen. The implementation preserves the visible source entries and does not claim that 50 is the institution's definitive total; an authoritative catalog/source-owner clarification is still needed for the exact official count/names.
- This report covers the confirmed regressions above; it does not establish a QA factual pass for all 500 evaluation questions or implement the separate proposed LLM pre-RAG decomposition/menu work.
- External-school protections have regression coverage in the suite, but this task's live Ollama traces focused on year isolation. QA/Security should rerun the external/mixed/ambiguous boundary cases on the final diff.

## 9. Handoff to QA & Security

Please independently review the final diff and rerun:

1. 2024 tuition, 2026 tuition, and unsupported 2027 tuition; confirm year, retrieved documents, evidence, source and final status.
2. Generic DHV default-year behavior and a year-specific multi-turn follow-up.
3. External, mixed and ambiguous school cases; verify retrieval/evidence remain zero before generation.
4. The PDF table header normalization, continued-table positive/negative cases, source-page 5/6 table counts, and catalog aliases/count behavior.
5. Full `tests/` suite with a writable Windows temporary directory.

This is a Lead Coder implementation handoff only. It is not a final QA/security pass. No deployment was performed.

Independent QA and Security reviews were dispatched to the two available agents. No review report had been returned at the time this handoff report was finalized; their review is still pending and is not counted as completed.

## 10. Lead Coder Verdict

**READY_FOR_QA**
