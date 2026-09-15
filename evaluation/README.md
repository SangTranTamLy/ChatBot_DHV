# DHV evaluation set

This directory contains the fixed offline evaluation contract for TASK N.

- `dev.jsonl`: 16 cases used for development/regression checks.
- `holdout.jsonl`: 4 cases reserved for final reporting. It is never used to tune
  routing, retrieval, prompts, or thresholds.

The split is a deterministic 80/20 split by file membership, with disjoint case
IDs. Retrieval gold is expressed as official corpus categories plus required
evidence phrases (or explicit chunk IDs when a future benchmark needs that
granularity). Answer gold checks only the declared contract: expected status,
required markers, forbidden claims, and validator faithfulness when evidence is
available. It does not treat lexical similarity as factual correctness.

Run the offline report from the repository root:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --split all
```

The dataset contains no reference images, source cards, URLs, personal data, or
unverified facts. Its factual phrases are derived from the verified DHV 2026
corpus already used by the project.
