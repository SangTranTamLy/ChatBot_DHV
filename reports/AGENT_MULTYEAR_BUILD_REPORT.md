# Multi-year Build CLI Implementation Report

## Rationale

Added an explicit opt-in CLI mode for indexing verified processed documents across years. The CLI remains backward-compatible: omitting a year still selects the configured `settings.target_year`, and `--year N` still selects only that year. `--all-years` maps to `target_year=None`, which the existing builder forwards to `load_verified_documents`.

The year selector is mutually exclusive: `--year N --all-years` is rejected by argparse rather than silently choosing one interpretation. The all-years help text explicitly says that verification, official-source, and DHV gates remain in force. No loader, validator, model, embedding, dataset, or runtime configuration code was changed.

## Files Changed

| File | Change |
| --- | --- |
| `src/ingestion/build_vector_db.py` | Added mutually exclusive `--all-years`; retained configured-year default and explicit `--year`; made CLI help description ASCII-safe for Windows CP1252 terminals. |
| `tests/test_ingestion.py` | Added coverage for configured-year default, all-years selection, explicit `--year`, selector conflict, all-years verified-year selection, and Windows-console-safe help. |

## Behavior

- `python -m src.ingestion.build_vector_db` -> uses configured `settings.target_year`.
- `python -m src.ingestion.build_vector_db --year 2024` -> indexes that year only.
- `python -m src.ingestion.build_vector_db --all-years` -> passes `target_year=None` to the existing build function; the existing build function passes it to the existing loader.
- `--year` and `--all-years` together -> rejected as conflicting options.

`load_verified_documents` still requires the source envelope to be explicitly verified before parsing. Structured JSON validation still enforces official DHV HTTPS provenance for verified sources; the all-years option only disables the year predicate. No active Chroma collection was built, reset, or modified.

## Exact Validation Commands and Results

1. Focused new/changed behavior:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_ingestion.py -q -p no:cacheprovider -k "build_cli or loader_all_years"
   ```

   Result: **6 passed, 5 deselected**.

2. Full ingestion suite (run with permission to create/clean temporary Windows fixtures):

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_ingestion.py -q -p no:cacheprovider
   ```

   Result: **11 passed**.

3. CLI help smoke check:

   ```powershell
   .\.venv\Scripts\python.exe -m src.ingestion.build_vector_db --help
   ```

   Result: **exit 0**; help displays `--year YEAR | --all-years` and the configured default year.

4. Diff whitespace check:

   ```powershell
   git diff --check
   ```

   Result: **passed** (Git emitted line-ending conversion notices only).

An initial non-elevated full-suite attempt encountered Windows `WinError 5` while creating/cleaning `TemporaryDirectory` fixtures. Rerunning the same ingestion suite with the required temporary-directory access completed successfully; this was an environment ACL issue, not a test assertion failure.

## Risks / Limitations

- This change is only a build CLI option. It does not change retrieval's configured-year filtering or make the chatbot query multiple years automatically.
- Using `--all-years` against a collection consumed by a single-year runtime may place several verified years in that collection; coordinate a separate retrieval/year-filter review before using it for a live chatbot corpus.
- Current tests verify the CLI-to-builder selector, loader inclusion of multiple verified years, and rejection of an unverified fixture. They do not rebuild or inspect any Chroma collection.

## QA Handoff

QA should review the diff and independently verify:

1. No argument selects the configured year.
2. `--year 2024` remains year-specific.
3. `--all-years` passes `None` through the builder to the existing loader.
4. Mixed selector arguments are rejected.
5. The existing verified/source/DHV validation path remains unchanged.
6. No database was rebuilt or active collection modified.

This is an implementation handoff only; it is **not** a QA pass. No deployment was performed.
