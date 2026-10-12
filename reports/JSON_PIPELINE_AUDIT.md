# JSON pipeline audit

## Scope and baseline

Audit date: 2026-09-16. The RAW corpus contains 15 PDF files under
`data/raw/<category>/`; `data/raw/manifest.json` records their official source
URLs, SHA-256, verification state and target year.

The supplied project overview PDF was used only to confirm the intended RAG
method: keep source/page metadata, separate indexing from runtime retrieval,
chunk by meaningful structure, and evaluate retrieval separately from answer
generation. It is not a DHV knowledge-base source.

## Current pipeline before this task

```text
data/raw/**/*.pdf
  -> src/ingestion/prepare_processed_from_raw.py
  -> pypdf PdfReader.page.extract_text(), text normalisation
  -> data/processed/**/*.md with YAML front matter
  -> src/ingestion/loader.py (verified/year filtering)
  -> src/ingestion/splitter.py (Markdown headers + recursive splitter)
  -> src/ingestion/build_vector_db.py
  -> ChromaDB
  -> src/retrieval/retriever.py
```

Responsibilities found during audit:

| Area | Owner | Baseline finding |
|---|---|---|
| PDF extraction and Markdown generation | `prepare_processed_from_raw.py` | pypdf text extraction; page boundaries were flattened before Markdown output |
| Metadata/provenance | `prepare_processed_from_raw.py`, `raw_manifest.py` | YAML and manifest metadata; no structured JSON object |
| Processed loading | `loader.py` | Markdown-only; verifies status and target year |
| Chunking | `splitter.py` | Markdown heading-aware; no record-level builder |
| Embedding/indexing | `build_vector_db.py`, `embeddings.py` | Chroma receives split Markdown documents |
| Retrieval | `retriever.py` | hybrid/vector and keyword candidate handling; public API must remain stable |
| Runtime chatbot | `chatbot/*`, `app.py` | consumes LangChain Documents and provenance metadata, not processed paths directly |

## Dependencies and compatibility

Existing tests and the runtime used `data/processed/**/*.md`; `tests/test_task_f.py`
also builds a deterministic corpus from that directory. Therefore the migration
keeps Markdown loading and the old conversion functions. A new generated path,
`data/processed_json/`, is the primary input for the vector builder, while the
prepare command exports a compatibility Markdown view from the same extraction.
No ChatService, RAG, retriever public API, UI schema, RAW PDF or Chroma runtime
contract is changed.

## Refactor decisions

1. Add `src/ingestion/structured_json.py` as the single owner of the structured
   representation, category parser mapping, validation and record-to-text chunk
   conversion.
2. Preserve page boundaries in JSON as `pages[].page` and `pages[].text`.
3. Use deterministic parsers for major catalog, application threshold,
   admission score, supplementary threshold, tuition, scholarship, official
   websites, admission methods, formulas, contacts, enrollment and deadlines.
4. Keep score semantics explicit (`application_threshold`, `admission_score`,
   `supplementary_threshold`, `score_formula`) and retain `-` for unverified
   catalog values rather than replacing them.
5. Flatten only scalar record fields into Chroma metadata; embedding input is
   natural-language record text, never a whole JSON dump.
6. Keep `PROCESSED_DATA_DIR` for legacy Markdown and add
   `PROCESSED_JSON_DIR` for the new generated layer.

## Known boundary

The repository currently has no OCR implementation. The separate mandatory-OCR
task explicitly requires replacing the current extraction boundary with OCR;
this task does not silently implement or claim that change. JSON records use
`extraction.method = "pypdf_text"` and preserve the current extraction behavior
until that task is completed.
