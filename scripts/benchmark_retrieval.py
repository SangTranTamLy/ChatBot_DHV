"""Paired two/three-stream ablation on the existing Chroma corpus; no generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain_chroma import Chroma
from src.chatbot.query_analysis import analyze_question, normalize_question, route_question
from src.config.settings import settings
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.embeddings import create_embeddings
from src.retrieval import retriever as retrieval


def fingerprint(documents):
    rows = sorted((d.metadata["chunk_id"], d.page_content, d.metadata) for d in documents)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_corpus():
    store = Chroma(collection_name=settings.chroma_collection,
                   persist_directory=str(settings.chroma_persist_dir), embedding_function=create_embeddings())
    try:
        data = store.get(include=["documents", "metadatas"])
        return [retrieval.Document(page_content=text, metadata=metadata)
                for text, metadata in zip(data["documents"], data["metadatas"])]
    finally:
        close_chroma_store(store)


def record_cases(documents):
    """Strict record targets, declared from source metadata before either ranking."""
    groups = {}
    for doc in documents:
        m = doc.metadata
        if retrieval._filter_reason(doc, settings.target_year, ()) is not None:
            continue
        kind, name, method = m.get("record_type"), m.get("major_name"), m.get("method")
        question = None
        if kind == "major" and name:
            question = f"Mã ngành {name} là gì?"
        elif kind == "admission_score" and name and method in {"thpt", "hoc_ba", "dgnl"}:
            label = {"thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ", "dgnl": "ĐGNL"}[method]
            question = f"Điểm trúng tuyển ngành {name} theo {label} năm 2026 là bao nhiêu?"
        elif kind == "application_threshold" and name:
            question = f"Điểm sàn ngành {name} năm 2026 là bao nhiêu?"
        elif kind == "tuition":
            question = "Học phí học kỳ I DHV năm 2026 là bao nhiêu?"
        elif kind == "enrollment_document":
            question = "Hồ sơ nhập học cần những giấy tờ gì?"
        elif kind == "admission_method" and m.get("method_number"):
            question = f"Phương thức xét tuyển {m['method_number']} của DHV là gì?"
        if question:
            item = groups.setdefault(question, {"question": question, "group": kind, "relevant_ids": []})
            item["relevant_ids"].append(m["chunk_id"])
    return [{"id": f"record_{i:03d}", **item} for i, item in enumerate(groups.values(), 1)]


def coverage(reference, documents):
    stop = {"la", "va", "cua", "cho", "co", "cac", "duoc", "trong", "theo", "nam", "dhv", "2026"}
    tokens = set(retrieval._normalise_token_list(reference)) - stop
    found = set(retrieval._normalise_token_list(" ".join(d.page_content for d in documents)))
    return len(tokens & found) / len(tokens) if tokens else None


def has_fact(text, fact):
    if fact.isdigit():
        return fact in {re.sub(r"[.,]", "", number) for number in re.findall(r"\d+(?:[.,]\d+)*", text)}
    return normalize_question(fact) in normalize_question(text)


def critical_cases(documents):
    cases = [
        ("Hồ sơ cần những giấy tờ gì?", ["Học bạ THPT", "Căn cước", "Giấy chứng nhận kết quả thi"]),
        ("Nộp hồ sơ nhập học ở cơ sở nào?", ["194 Lê Đức Thọ", "37 Kinh Dương Vương"]),
        ("Trường có những cơ sở nào?", ["194 Lê Đức Thọ", "736 Nguyễn Trãi", "37 Kinh Dương Vương", "Công viên Phần mềm Quang Trung"]),
        ("Email liên hệ của DHV là gì?", ["info@dhv.edu.vn", "media@dhv.edu.vn"]),
        ("Số điện thoại tuyển sinh DHV là gì?", ["0287 1000 888"]),
        ("Học phí mỗi tín chỉ bao nhiêu?", ["1250000"]),
        ("Hồ sơ cần gì, nộp ở đâu và học phí bao nhiêu?", ["Học bạ THPT", "Căn cước", "194 Lê Đức Thọ", "37 Kinh Dương Vương", "12500000"]),
        ("Hồ sơ cần gì, nộp ở đâu?", ["Học bạ THPT", "Căn cước", "194 Lê Đức Thọ", "37 Kinh Dương Vương"]),
    ]
    valid = [d for d in documents if retrieval._filter_reason(d, settings.target_year, ()) is None]
    result = []
    for index, (question, facts) in enumerate(cases, 1):
        sources = {fact: [d.metadata["chunk_id"] for d in valid if has_fact(d.page_content, fact)] for fact in facts}
        if not all(sources.values()):
            raise ValueError(f"Critical fact absent from verified corpus: {sources}")
        result.append({"id": f"critical_{index:02d}", "question": question, "required_facts": facts, "fact_sources": sources})
    return result


def summarize(rows):
    result = {}
    for mode in ("two", "three"):
        timings = [t for row in rows for t in row[mode]["ms"]]
        metrics = {}
        for key in ("hit1", "hit4", "recall4", "mrr4", "reference_coverage4", "fact_coverage4", "all_facts4"):
            values = [row[mode][key] for row in rows if row[mode].get(key) is not None]
            if values:
                metrics[key] = statistics.mean(values)
        ordered = sorted(timings)
        result[mode] = {"requests": len(timings), "mean_ms": statistics.mean(timings),
                        "p50_ms": statistics.median(timings),
                        "p95_ms": ordered[min(len(ordered)-1, int(.95 * len(ordered)))], **metrics} if timings else {}
    return result


def run(cases, engine, repeats):
    rows = []
    real_lookup = retrieval.lookup_structured_documents
    for index, case in enumerate(cases):
        analysis = analyze_question(case["question"])
        plan = route_question(analysis)
        plans = plan.subplans or (plan,)
        if plan.needs_clarification or not any(p.categories for p in plans):
            rows.append({**case, "skipped": "no_unambiguous_retrieval_plan"})
            continue
        row = {**case, "intent": analysis.intent, "two": {"ms": []}, "three": {"ms": []}}
        for repeat in range(repeats):
            for mode in (("two", "three") if (index + repeat) % 2 == 0 else ("three", "two")):
                outputs, active, docs = [], False, []
                lookup = real_lookup if mode == "three" else lambda *a, **k: []
                with patch.object(retrieval, "lookup_structured_documents", lookup):
                    start = time.perf_counter()
                    for child in plans:
                        if not child.categories:
                            continue
                        output = engine.retrieve_with_audit(
                            child.issue_question or case["question"], categories=child.categories,
                            retrieval_query=child.retrieval_query, entity_filters=child.entity_filters, top_k=4)
                        outputs.append(output)
                    elapsed = (time.perf_counter() - start) * 1000
                row[mode]["ms"].append(elapsed)
                for output in outputs:
                    docs.extend(output.documents[:4])
                    active |= output.audit.fusion_method == "bm25+dense+structured+rrf"
                ids = list(dict.fromkeys(d.metadata["chunk_id"] for d in docs))
                if repeat and ids != row[mode]["ids"]:
                    raise RuntimeError(f"Non-deterministic retrieval: {case['id']} {mode}")
                relevant = set(case.get("relevant_ids", []))
                first = next((i for i, identity in enumerate(ids, 1) if identity in relevant), None)
                row[mode].update(ids=ids, structured_active=active,
                                 hit1=float(bool(ids and ids[0] in relevant)) if relevant else None,
                                 hit4=float(first is not None) if relevant else None,
                                 recall4=len(relevant & set(ids)) / len(relevant) if relevant else None,
                                 mrr4=1 / first if first else (0.0 if relevant else None),
                                 reference_coverage4=coverage(case["reference_answer"], docs)
                                 if case.get("reference_answer") else None)
                if case.get("required_facts"):
                    text = "\n".join(d.page_content for d in docs)
                    found = [fact for fact in case["required_facts"] if has_fact(text, fact)]
                    row[mode].update(found_facts=found, fact_coverage4=len(found)/len(case["required_facts"]),
                                     all_facts4=float(len(found) == len(case["required_facts"])))
        rows.append(row)
        if (index + 1) % 25 == 0:
            print(f"Measured {index+1}/{len(cases)}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--canonical-repeats", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/retrieval_benchmark")
    args = parser.parse_args()
    if min(args.repeats, args.canonical_repeats) < 1:
        parser.error("repeat counts must be positive")
    documents = load_corpus()
    gold = record_cases(documents)
    critical = critical_cases(documents)
    master = ROOT / "data/evaluation/qa_master_500.jsonl"
    canonical = [json.loads(line) for line in master.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        gold, canonical = gold[:args.limit], canonical[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "record_cases.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "critical_cases.json").write_text(json.dumps(critical, ensure_ascii=False, indent=2), encoding="utf-8")
    engine = retrieval.DHVRetriever()
    start = time.perf_counter()
    engine.retrieve_with_audit("Học phí DHV năm 2026 là bao nhiêu?")
    cold_ms = (time.perf_counter() - start) * 1000
    print(f"Corpus={len(documents)} record_cases={len(gold)} canonical={len(canonical)} cold_ms={cold_ms:.1f}", flush=True)
    report = {"created": datetime.now().astimezone().isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "corpus_count": len(documents), "corpus_sha256": fingerprint(documents),
              "master_sha256": hashlib.sha256(master.read_bytes()).hexdigest(), "repeats": args.repeats,
              "canonical_repeats": args.canonical_repeats,
              "embedding": settings.embedding_model, "top_k_per_issue": 4, "cold_first_retrieval_ms": cold_ms,
              "baseline": "Current production retriever with structured lookup disabled in this process only",
              "timing": "Sequential paired live retrieval including embeddings, Chroma open/read/close and ranking; alternating order; initial warmup excluded"}
    for name, cases in (("critical", critical), ("records", gold), ("canonical", canonical)):
        rows = run(cases, engine, args.canonical_repeats if name == "canonical" else args.repeats)
        evaluated = [r for r in rows if "skipped" not in r]
        report[name] = {"total": len(rows), "evaluated": len(evaluated), "skipped": len(rows)-len(evaluated),
                        "summary": summarize(evaluated), "groups": {group: summarize([r for r in evaluated if r.get("group") == group])
                         for group in sorted({r["group"] for r in evaluated if "group" in r})}, "rows": rows}
        (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if fingerprint(load_corpus()) != report["corpus_sha256"]:
        raise RuntimeError("Corpus changed during benchmark")
    print(json.dumps({k: report[k]["summary"] for k in ("critical", "records", "canonical")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
