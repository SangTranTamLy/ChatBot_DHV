"""Generate QA artifacts for the independent P1 full-sweep retest.

This is QA/reporting code only. It does not modify product code, datasets,
expected answers, Chroma, or model configuration.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "QA_FULL_SWEEP_P1_RETEST_RESULTS.jsonl"
OUTPUT = ROOT / "QA_FULL_SWEEP_P1_RETEST_RESULTS_ENRICHED.jsonl"
FAILURES = ROOT / "QA_FULL_SWEEP_P1_RETEST_FAILURES.jsonl"
REPORT = ROOT / "QA_FULL_SWEEP_P1_RETEST_REPORT.md"


# These are the rows whose answer was checked against the canonical expected
# answer and relevant evidence. A row is not a PASS merely because the runtime
# returned status=ok.
QA_PASS_IDS = {
    "UQ0011",
    "UQ0040",
    "UQ0041",
    "UQ0061",
    "UQ0078",
    "UQ0087",
    "UQ0091",
    "UQ0092",
    "UQ0093",
    "UQ0095",
    "UQ0097",
    "UQ0103",
    "UQ0222",
    "UQ0228",
    "UQ0338",
    "UQ0342",
    "UQ034?",  # removed below; keeps accidental typo impossible to hide
}
QA_PASS_IDS.discard("UQ034?")


FAIL_META = {
    "UQ0001": ("LLM_PARTIAL_ANSWER", "MEDIUM", "retrieval/evidence exists but overview generation omitted required school facts"),
    "UQ0003": ("LLM_PARTIAL_ANSWER", "MEDIUM", "answer gave the major count but omitted the required program-count fact"),
    "UQ0010": ("WRONG_INTENT", "HIGH", "basic admission eligibility routed to scholarship intent and returned scholarship facts"),
    "UQ0013": ("LLM_PARTIAL_ANSWER", "MEDIUM", "method enumeration was incomplete/garbled despite relevant evidence"),
    "UQ0016": ("WRONG_QUERY_MODE", "HIGH", "question asks subject-count semantics but answer returned an admission threshold"),
    "UQ0042": ("WRONG_NUMERIC_FACT", "HIGH", "returned 14,250,000 instead of canonical 14,500,000"),
    "UQ0057": ("LIST_INCOMPLETE", "MEDIUM", "method list omitted the expected học bạ item"),
    "UQ0064": ("WRONG_INTENT", "MEDIUM", "remote-student online enrollment question got a generic document list"),
    "UQ0068": ("WRONG_DATE", "HIGH", "returned 13/8 and 8/8 where canonical deadline is 11/8"),
    "UQ0074": ("WRONG_INTENT", "MEDIUM", "question asks where to verify documents; answer listed documents instead"),
    "UQ0076": ("WRONG_INTENT", "MEDIUM", "question asks confirmation/completion workflow; answer returned generic documents"),
    "UQ0089": ("WRONG_INTENT", "HIGH", "subject-combination question returned admission methods"),
    "UQ0083": ("WRONG_INTENT", "MEDIUM", "question asks where the published enrollment guidance is located; answer returned a generic document checklist"),
    "UQ0106": ("LIST_INCOMPLETE", "MEDIUM", "school-governance list omitted required councils/faculties"),
    "UQ0138": ("LLM_PARTIAL_ANSWER", "MEDIUM", "partnership answer omitted the exact 28/01/2026 date and requested benefits"),
    "UQ0179": ("LLM_PARTIAL_ANSWER", "MEDIUM", "returned score values but did not answer why the major is higher"),
    "UQ0202": ("LLM_PARTIAL_ANSWER", "MEDIUM", "returned generic Khoa existence instead of requested cooperation benefits"),
    "UQ0236": ("LLM_PARTIAL_ANSWER", "MEDIUM", "returned generic partnerships instead of the named Học viện relationship"),
    "UQ0252": ("LLM_PARTIAL_ANSWER", "MEDIUM", "returned generic Khoa text instead of requested partner fields"),
    "UQ0340": ("LLM_PARTIAL_ANSWER", "MEDIUM", "did not answer the cash-payment location/absence-of-counter details"),
    "UQ0378": ("LLM_PARTIAL_ANSWER", "MEDIUM", "listed programs but did not answer how market knowledge is taught"),
    "UQ0085": ("WRONG_SCOPE", "HIGH", "in-scope admissions schedule question was rejected before retrieval"),
    "UQ0086": ("WRONG_SCOPE", "MEDIUM", "verified school slogan question was rejected before retrieval"),
    "UQ0107": ("WRONG_SCOPE", "MEDIUM", "verified school overview fact was rejected by an overly narrow scope policy"),
    "UQ0133": ("WRONG_SCOPE", "MEDIUM", "verified early-enterprise-access fact was rejected despite explicit DHV target"),
}


def compact(value: object, limit: int = 900) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("|", "\\|").split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def md(value: object, limit: int = 900) -> str:
    return compact(value, limit).replace("`", "'" )


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * p
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def classify(row: dict) -> tuple[str, str | None, str | None, str, str]:
    qid = row["question_id"]
    if qid in QA_PASS_IDS:
        return "PASS", None, None, "QA confirmed factual answer against expected answer and relevant evidence.", "QA"
    if qid in FAIL_META:
        code, severity, reason = FAIL_META[qid]
        return "FAIL", code, severity, reason, "LEAD_CODER"
    if row.get("status") == "no_data":
        return (
            "FAIL",
            "FALSE_NO_DATA",
            "HIGH",
            "canonical expected answer exists, but the production-like path returned NO_DATA; evidence/filter/planner coverage is insufficient",
            "LEAD_CODER",
        )
    if row.get("status") == "out_of_scope":
        return (
            "CONTRACT_BLOCKED",
            "CONTRACT_SCOPE_UNRESOLVED",
            "MEDIUM",
            "safe refusal prevented unsupported claims, but the canonical expected answer is outside the currently approved production scope/evidence contract",
            "DATA_REVIEW",
        )
    return (
        "FAIL",
        "UNSUPPORTED_ANSWER",
        "HIGH",
        "runtime answer did not satisfy canonical expected-answer requirements",
        "LEAD_CODER",
    )


def load_rows() -> list[dict]:
    return [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    rows = load_rows()
    enriched: list[dict] = []
    for row in rows:
        verdict, code, severity, reason, owner = classify(row)
        item = dict(row)
        item.update(
            {
                "qa_verdict": verdict,
                "qa_failure_code": code,
                "qa_severity": severity,
                "qa_reason": reason,
                "qa_owner": owner,
            }
        )
        enriched.append(item)

    OUTPUT.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in enriched) + "\n", encoding="utf-8")
    failures = [item for item in enriched if item["qa_verdict"] == "FAIL"]
    FAILURES.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in failures) + "\n", encoding="utf-8")

    runtime_counts = Counter(row.get("status") for row in rows)
    qa_counts = Counter(row["qa_verdict"] for row in enriched)
    failure_codes = Counter(row["qa_failure_code"] for row in enriched if row["qa_failure_code"])
    severities = Counter(row["qa_severity"] for row in enriched if row["qa_severity"])
    intents = defaultdict(lambda: Counter())
    modes = defaultdict(lambda: Counter())
    for row in enriched:
        intents[row.get("intent") or "UNKNOWN"][row["qa_verdict"]] += 1
        modes[row.get("query_mode") or "UNKNOWN"][row["qa_verdict"]] += 1

    latencies = [float(row.get("latency_ms") or 0) for row in rows]
    by_mode_latency: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_mode_latency[row.get("query_mode") or "UNKNOWN"].append(float(row.get("latency_ms") or 0))

    lines: list[str] = []
    add = lines.append
    add("# QA & SECURITY – FULL SWEEP P1 RETEST REPORT")
    add("")
    add("## 1. Scope")
    add("")
    add("Independent retest of the 120 questions that failed in the original full sweep after Lead Coder P1 changes. The retest used the production-like `ask_chatbot` path with local Ollama and the existing Chroma collection. QA did not modify source code, datasets, expected answers, Chroma, or model configuration.")
    add("")
    add("Lead claims reviewed: `FULL_SWEEP_P1_FIX_REPORT.md`, including claims for `SWEEP-SCOPE-001`, `SWEEP-SCOPE-002`, `SWEEP-INTENT-001`, and `SWEEP-YEAR-001`.")
    add("")
    add("## 2. Runtime Environment")
    add("")
    add("| Component | Observed |")
    add("|---|---|")
    add("| Runtime | Real sequential `src.chatbot.rag_chain.ask_chatbot` |")
    add("| LLM | Ollama `qwen2.5:3b` available |")
    add("| Embedding | Ollama `nomic-embed-text` available |")
    add("| Chroma | `dhv_admissions_2026`, 270 records, read-only inspection |")
    add("| Checkpoint | `QA_FULL_SWEEP_P1_RETEST_RESULTS.jsonl`, 120/120 records |")
    add("")
    add("## 3. Overall Results")
    add("")
    add(f"- Runtime execution: **{len(rows)}/{len(rows)} completed**; no environment-blocked question.")
    add(f"- Runtime statuses: `ok={runtime_counts['ok']}`, `no_data={runtime_counts['no_data']}`, `out_of_scope={runtime_counts['out_of_scope']}`.")
    add(f"- QA verdicts: **PASS={qa_counts['PASS']}, FAIL={qa_counts['FAIL']}, CONTRACT_BLOCKED={qa_counts['CONTRACT_BLOCKED']}**.")
    add(f"- Factual QA pass rate over all 120: **{qa_counts['PASS'] / len(rows) * 100:.2f}%**. Contract-blocked rows are not counted as PASS.")
    add(f"- Severity distribution: `{dict(severities)}`.")
    add("")
    add("The retest does **not** support a full-sweep pass. There are confirmed HIGH factual/routing failures and unresolved contract rows.")
    add("")
    add("## 4. Runtime Architecture / Trace Coverage")
    add("")
    add("Every retested row contains the captured question, expected answer, analysis entities, intent, query mode, school/scope, year, retrieval count, document/evidence count, status, answer, sources, and latency in `QA_FULL_SWEEP_P1_RETEST_RESULTS_ENRICHED.jsonl`. The following representative traces were independently inspected:")
    add("")
    add("| ID | Trace result | Retrieval | Evidence | QA interpretation |")
    add("|---|---|---:|---:|---|")
    for qid in ("UQ0010", "UQ0007", "UQ0085", "UQ0107", "UQ0224", "UQ0342"):
        row = next(item for item in enriched if item["question_id"] == qid)
        add(f"| {qid} | {row.get('status')} / {row.get('intent')} | {row.get('retrieval_calls', 0)} / {row.get('retrieved_docs_count', 0)} docs | {row.get('evidence_count', 0)} | {md(row['qa_reason'], 220)} |")
    add("")
    add("## 5. Regression Suites")
    add("")
    add("| Suite | Passed | Failed | Skipped | Classification |")
    add("|---|---:|---:|---:|---|")
    add("| Focused P1 + Task 09 + Task C + UI | 82 | 3 | 0 reported | PRODUCT_FAILURE: `tests/test_task_c.py` category over-selection |")
    add("| Full pytest | 215 | 5 | 4 | 3 Task C subtest failures + 2 existing data/manifest failures |")
    add("| Original FAIL-ID runtime retest | 120 | 0 blocked | 0 | Completed; QA answer evaluation still found failures |")
    add("| `python -m compileall src app.py` | PASS | 0 | 0 | Static syntax check passed |")
    add("")
    add("Full-suite mismatch with Lead report: Lead reported 215 passed / 2 failed / 4 skipped; independent run returned 215 passed / 5 failed / 4 skipped. This is `REPORT_CODE_MISMATCH`.")
    add("")
    add("## 6. Results by Intent")
    add("")
    add("| Intent | PASS | FAIL | Contract blocked |")
    add("|---|---:|---:|---:|")
    for intent in sorted(intents):
        add(f"| {intent} | {intents[intent]['PASS']} | {intents[intent]['FAIL']} | {intents[intent]['CONTRACT_BLOCKED']} |")
    add("")
    add("## 7. Results by Query Mode")
    add("")
    add("| Query mode | PASS | FAIL | Contract blocked |")
    add("|---|---:|---:|---:|")
    for mode in sorted(modes):
        add(f"| {mode} | {modes[mode]['PASS']} | {modes[mode]['FAIL']} | {modes[mode]['CONTRACT_BLOCKED']} |")
    add("")
    add("## 8. Performance")
    add("")
    add(f"- All 120 runtime calls: average `{statistics.mean(latencies):.2f} ms`, median `{statistics.median(latencies):.2f} ms`, p95 `{percentile(latencies, .95):.2f} ms`, max `{max(latencies):.2f} ms`.")
    add("")
    add("| Query mode | Count | Average ms | Median ms | P95 ms | Max ms |")
    add("|---|---:|---:|---:|---:|---:|")
    for mode in sorted(by_mode_latency):
        values = by_mode_latency[mode]
        add(f"| {mode} | {len(values)} | {statistics.mean(values):.2f} | {statistics.median(values):.2f} | {percentile(values, .95):.2f} | {max(values):.2f} |")
    add("")
    add("## 9. Complete Confirmed Failure List")
    add("")
    add(f"These {qa_counts['FAIL']} rows are confirmed QA FAIL. The full unabridged trace for every row is in `QA_FULL_SWEEP_P1_RETEST_FAILURES.jsonl`.")
    add("")
    add("| ID | Question | Expected | Actual | Failure code | Severity | Probable root cause |")
    add("|---|---|---|---|---|---|---|")
    for row in enriched:
        if row["qa_verdict"] != "FAIL":
            continue
        add("| " + " | ".join(
            [
                row["question_id"],
                md(row.get("question"), 360),
                md(row.get("expected_answer"), 520),
                md(row.get("answer"), 520),
                row.get("qa_failure_code") or "",
                row.get("qa_severity") or "",
                md(row.get("qa_reason"), 360),
            ]
        ) + " |")
    add("")
    add("## 10. Contract-Blocked Rows (Not PASS)")
    add("")
    add("The following 64 rows were safely refused as `out_of_scope` with zero retrieval/evidence. They are not counted as functional PASS because their canonical expected answers require a product scope/evidence contract decision. This is a DATA_REVIEW handoff, not evidence that the chatbot may invent answers.")
    add("")
    add("| ID | Question | Runtime scope | Retrieval | Evidence | Decision needed |")
    add("|---|---|---|---:|---:|---|")
    for row in enriched:
        if row["qa_verdict"] != "CONTRACT_BLOCKED":
            continue
        add(f"| {row['question_id']} | {md(row.get('question'), 420)} | {md(row.get('scope_reason'), 180)} | {row.get('retrieval_calls', 0)} | {row.get('evidence_count', 0)} | Approve corpus/scope or keep refusal |")
    add("")
    add("## 11. Failure Clusters")
    add("")
    add("| Cluster | Count | Priority | Owner |")
    add("|---|---:|---|---|")
    for code, count in failure_codes.most_common():
        priority = "P1" if code in {"FALSE_NO_DATA", "WRONG_INTENT", "WRONG_QUERY_MODE", "WRONG_NUMERIC_FACT", "WRONG_DATE", "WRONG_SCOPE"} else "P2"
        owner = "LEAD_CODER" if code != "CONTRACT_SCOPE_UNRESOLVED" else "DATA_REVIEW"
        add(f"| {code} | {count} | {priority} | {owner} |")
    add("")
    add("## 12. Security / Regression Review")
    add("")
    add("- No new QA-side source changes were made.")
    add("- External/scope-safe refusals showed zero retrieval/evidence in the retest; no new DHV factual leakage was observed in those rows.")
    add("- The retest did expose a false-negative scope regression for verified DHV facts (`UQ0085`, `UQ0086`, `UQ0107`, `UQ0133`).")
    add("- The deterministic routing regression over-selects `phuong_thuc_xet_tuyen` and `ho_so` for `dang_ky_xet_tuyen`; this can broaden retrieval and contaminate evidence selection.")
    add("- No unbounded concurrency was used; calls were sequential to avoid Ollama contention.")
    add("")
    add("## 13. Lead Claims Verified")
    add("")
    add("| Claim | Verified? | Evidence |")
    add("|---|---|---|")
    add("| 120 original FAIL IDs were rerun with real runtime | YES | Independent checkpoint contains 120/120 rows; Ollama and Chroma were available |")
    add("| Lead runtime status split was 38 ok / 14 no_data / 68 out_of_scope | NO | Independent split is 37 ok / 15 no_data / 68 out_of_scope; this is `REPORT_CODE_MISMATCH` |")
    add("| External/scope fixes avoid unsupported retrieval | PARTIAL | External refusals had retrieval=0/evidence=0, but four verified in-scope DHV questions were also refused |")
    add("| Year semantics fixed | PARTIAL | UQ0007 extracts year 2026 but still returns NO_DATA with evidence present |")
    add("| Full regression is 215 passed / 2 failed / 4 skipped | NO | Independent run: 215 passed / 5 failed / 4 skipped |")
    add("| Task C category routing is aligned | NO | 3 subtests fail because plan categories are `dang_ky_xet_tuyen`, `phuong_thuc_xet_tuyen`, `ho_so` instead of only `dang_ky_xet_tuyen` |")
    add("")
    add("## 14. Acceptance Criteria")
    add("")
    add("| Criterion | Result |")
    add("|---|---|")
    add("| All original 120 rows executed | PASS |")
    add("| No environment block in this retest | PASS |")
    add("| No external-school DHV factual leak observed in refused rows | PASS for tested external/scope-safe rows |")
    add("| No wrong-year data claim in the retested answers | BLOCKED/FAIL: UQ0007 remains NO_DATA despite year=2026 evidence |")
    add("| Factual answers grounded and complete | FAIL: 39 confirmed FAIL rows |")
    add("| No wrong intent/query mode | FAIL: UQ0010, UQ0016, UQ0089 and others |")
    add("| COUNT/LIST and numeric facts remain correct | FAIL: UQ0003, UQ0013, UQ0016, UQ0042, UQ0057 |")
    add("| Regression suites clean | FAIL: 5 full-suite failures, 3 focused Task C subtests |")
    add("| All canonical questions resolved or contract-approved | BLOCKED: 64 contract-scope decisions pending |")
    add("")
    add("## 15. Handoff to Lead Coder")
    add("")
    add("### Priority 1")
    add("")
    add("1. Fix the 15 `FALSE_NO_DATA` rows as one coverage/filter/planner cluster. Preserve the no-hallucination boundary, but when verified evidence is present (`UQ0007`, `UQ0017`, `UQ0024`, `UQ0025`, `UQ0026`, `UQ0096`, `UQ0098`, `UQ0099`, `UQ0160`, `UQ0224`, `UQ0327`) the answer planner must not discard it. Acceptance: each canonical fact is answered from relevant year/school evidence, or the dataset contract is explicitly changed by DATA_REVIEW.")
    add("2. Fix wrong intent/query-mode routing for `UQ0010`, `UQ0016`, `UQ0089` and the related partial rows. Acceptance: expected requested information and query mode are preserved through route, retrieve, plan, validator, and final answer.")
    add("3. Fix numeric/date/list defects: `UQ0042`, `UQ0057`, `UQ0068`, plus incomplete enumeration rows. Acceptance: canonical numeric values, dates, and unique item sets match structured evidence.")
    add("")
    add("### Priority 2")
    add("")
    add("1. Narrow `dang_ky_xet_tuyen` category routing so it does not automatically add `phuong_thuc_xet_tuyen` and `ho_so` when the test contract requires a single category. Rerun the three failing Task C subtests.")
    add("2. Restore in-scope handling for verified DHV schedule/school facts (`UQ0085`, `UQ0086`, `UQ0107`, `UQ0133`) without weakening external-school guards.")
    add("3. Improve answer planning/completeness for overview, partnership, school governance, payment, and program-teaching questions listed in the confirmed failure table.")
    add("")
    add("### Priority 3 — DATA_REVIEW")
    add("")
    add("1. Decide whether the 64 contract-blocked questions are part of supported production scope. If yes, add/verify official evidence and explicit intents/categories; if no, remove them from the canonical production evaluation contract rather than silently counting safe refusal as PASS.")
    add("2. Resolve the two non-routing full-suite failures: raw PDF official-URL policy and the hard-coded skipped-unverified manifest expectation. Do not alter tests solely to make them green; align policy/manifest/test fixture intentionally.")
    add("")
    add("## 16. Final Verdict")
    add("")
    add("**FULL_SWEEP_P1_RETEST_FAIL**")
    add("")
    add(f"Reason: all 120 runtime calls completed, but only {qa_counts['PASS']}/120 were confirmed factual PASS, {qa_counts['FAIL']} were confirmed FAIL, and {qa_counts['CONTRACT_BLOCKED']} remain contract-blocked. The independent full suite also has 5 failures, including 3 Task C routing failures not reported by the Lead report. This is not `FULL_QUESTION_SWEEP_PASS` and not an environment block.")
    add("")
    add("QA stops here. No deployment and no product-code changes were made.")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": len(rows),
        "runtime": dict(runtime_counts),
        "qa": dict(qa_counts),
        "failures": str(FAILURES),
        "report": str(REPORT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
