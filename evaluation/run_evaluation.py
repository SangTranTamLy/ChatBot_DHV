"""Command-line runner for the fixed offline DHV evaluation set."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Mapping

from langchain_core.documents import Document

from src.chatbot.evidence import _clean_context_text
from src.chatbot.multi_issue import _retrieval_subplan_for_issue
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import ConversationState, analyze_question, route_question
from src.config.settings import Settings, settings
from src.ingestion.embeddings import resolve_embedding_config
from src.ingestion.loader import load_verified_documents
from src.ingestion.splitter import split_documents
from src.retrieval.retriever import DHVRetriever

from .evaluator import (
    EvaluationCase,
    evaluate_answers,
    evaluate_intents,
    evaluate_retrieval,
    load_cases,
    validate_dataset,
)


_TOKEN_RE = re.compile(r"\d[\d.,]*|[A-Za-zÀ-ỹĐđ]+", re.UNICODE)


def _fold(value: object) -> str:
    return " ".join(_TOKEN_RE.findall(str(value or "").casefold()))


def _where_matches(metadata: Mapping[str, object], where: Mapping[str, object]) -> bool:
    if "year" in where:
        return metadata.get("year") == where["year"]
    if "$and" in where:
        return all(_where_matches(metadata, item) for item in where["$and"] if isinstance(item, Mapping))
    if "$or" in where:
        return any(_where_matches(metadata, item) for item in where["$or"] if isinstance(item, Mapping))
    if "category" in where:
        return metadata.get("category") == where["category"]
    if "data_role" in where:
        return metadata.get("data_role") == where["data_role"]
    return not where


class OfflineCorpusStore:
    """Chroma-shaped read-only adapter for reproducible offline evaluation.

    The production retriever still owns filtering, BM25, dense-rank fusion and
    audit creation. This adapter only supplies the verified processed corpus and
    avoids requiring Ollama during a deterministic evaluation run.
    """

    chunks: tuple[Document, ...] = ()
    embedding_config = resolve_embedding_config(settings_obj=settings)

    class Collection:
        def count(self) -> int:
            return len(OfflineCorpusStore.chunks)

    _collection = Collection()
    _collection.metadata = {
        "embedding_backend": embedding_config.backend,
        "embedding_model": embedding_config.model,
        "embedding_dimension": 3,
    }

    def __init__(self, **_: object) -> None:
        pass

    def _filtered(self, where: Mapping[str, object]) -> list[Document]:
        return [document for document in self.chunks if _where_matches(document.metadata, where)]

    def similarity_search(self, query: str, *, k: int, filter: Mapping[str, object]) -> list[Document]:
        query_terms = set(_fold(query).split())
        documents = self._filtered(filter)
        ranked = sorted(
            documents,
            key=lambda document: (
                -len(query_terms & set(_fold(document.page_content).split())),
                str(document.metadata.get("chunk_id") or ""),
            ),
        )
        return ranked[:k]

    def get(self, *, where: Mapping[str, object], include: list[str]) -> dict[str, object]:
        documents = self._filtered(where)
        return {
            "documents": [document.page_content for document in documents],
            "metadatas": [document.metadata for document in documents],
        }


class EvidenceEchoLLM:
    """Offline generation double that returns prompt evidence, never new facts."""

    def generate(self, prompt: str) -> str:
        context_match = re.search(r"<CONTEXT>\n(.*?)\n</CONTEXT>", prompt, re.DOTALL)
        context = context_match.group(1) if context_match else ""
        entities_match = re.search(r"<ENTITIES>\n(.*?)\n</ENTITIES>", prompt, re.DOTALL)
        entities: object = {}
        if entities_match:
            try:
                entities = json.loads(entities_match.group(1))
            except json.JSONDecodeError:
                entities = {}
        if isinstance(entities, Mapping):
            program = str(entities.get("program_name") or "")
            parent = str(entities.get("parent_major") or "")
            if program and parent:
                return f"{program} là chương trình thuộc ngành {parent}."
        intent_match = re.search(r"<INTENT>\n(.*?)\n</INTENT>", prompt, re.DOTALL)
        intent = intent_match.group(1).strip() if intent_match else ""
        if intent == "TU_VAN_CHON_NGANH":
            interest = str(entities.get("interest") or "").strip() if isinstance(entities, Mapping) else ""
            title_candidates = []
            for title in re.findall(r"Tiêu đề:\s*([^\n]+)", context):
                match = re.search(r"(?:Mô tả ngành|ngành)\s+(.+?)(?:\s+và\s+|\s+-\s+|$)", title, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip(" .")
                    if candidate and candidate not in title_candidates:
                        title_candidates.append(candidate)
            if interest and title_candidates:
                return (
                    f"Với sở thích {interest}, mình nghiêng về {title_candidates[0]} hơn trong "
                    "các hướng theo dữ liệu DHV đã được kiểm chứng. Gợi ý này chỉ để bạn "
                    "cân nhắc thêm."
                )
        facts_match = re.search(
            r"<STRUCTURED_SCORE_FACTS>\n(.*?)\n</STRUCTURED_SCORE_FACTS>",
            prompt,
            re.DOTALL,
        )
        if facts_match and intent in {
            "HOI_NGUONG_DAU_VAO",
            "HOI_DIEM_TRUNG_TUYEN",
            "HOI_XET_TUYEN_BO_SUNG",
        }:
            try:
                facts = json.loads(facts_match.group(1))
            except json.JSONDecodeError:
                facts = []
            labels = {
                "thpt": "Thi tốt nghiệp THPT",
                "hoc_ba": "Học bạ",
                "dgnl": "ĐGNL",
                "deadline": "Hạn xét tuyển bổ sung",
            }
            lines = []
            for fact in facts if isinstance(facts, list) else []:
                method = str(fact.get("method") or "") if isinstance(fact, Mapping) else ""
                value = str(fact.get("raw_value") or "") if isinstance(fact, Mapping) else ""
                if method in labels:
                    lines.append(f"{labels[method]}: {value}")
            if lines:
                major = str(entities.get("major_name") or "") if isinstance(entities, Mapping) else ""
                prefix = f"{major}: " if major else "Dữ liệu tuyển sinh: "
                return prefix + "; ".join(dict.fromkeys(lines)) + "."
        return _clean_context_text(context) if context else ""


def _retriever(*, settings_obj: Settings = settings) -> DHVRetriever:
    processed = Path(settings_obj.processed_data_dir)
    OfflineCorpusStore.chunks = tuple(split_documents(load_verified_documents(processed).documents))
    embedding_config = resolve_embedding_config(settings_obj=settings_obj)
    OfflineCorpusStore._collection.metadata = {
        "embedding_backend": embedding_config.backend,
        "embedding_model": embedding_config.model,
        "embedding_dimension": 3,
    }

    class OfflineEmbeddings:
        @staticmethod
        def embed_query(_: str) -> list[float]:
            return [0.0, 0.0, 0.0]

    return DHVRetriever(
        settings_obj=settings_obj,
        store_factory=OfflineCorpusStore,
        embedding_factory=lambda **_: OfflineEmbeddings(),
    )


def _retrieve_for_case(
    retriever: DHVRetriever,
    case: EvaluationCase,
    *,
    top_k: int | None = None,
    settings_obj: Settings = settings,
) -> object:
    state = ConversationState.from_value(case.state, default_year=settings_obj.target_year)
    analysis = analyze_question(case.question, state, default_year=settings_obj.target_year)
    plan = route_question(analysis, state, target_year=settings_obj.target_year)
    if not plan.categories or plan.needs_clarification:
        return ()
    if analysis.intent == "MULTI_ISSUE" and plan.subplans:
        groups: list[list[Document]] = []
        retrieval_top_k = max(1, int(top_k or settings_obj.retriever_top_k))
        for subplan in plan.subplans:
            subquery = subplan.issue_question or subplan.retrieval_query
            if not subquery or not subplan.categories or subplan.needs_clarification:
                continue
            retrieval_subplan = _retrieval_subplan_for_issue(subplan)
            result = retriever.retrieve_with_audit(
                subquery,
                categories=subplan.categories,
                retrieval_query=subplan.retrieval_query,
                entity_filters=retrieval_subplan.entity_filters,
                data_roles=subplan.data_roles,
                top_k=retrieval_top_k,
            )
            groups.append(list(getattr(result, "documents", result) or ()))

        # Production retrieves each issue independently. Interleave their ranks
        # so a compound question's global top-k metric gives every issue a turn.
        merged: list[Document] = []
        seen_ids: set[str] = set()
        while len(merged) < retrieval_top_k:
            added = False
            for group in groups:
                if len(merged) >= retrieval_top_k:
                    break
                while group:
                    document = group.pop(0)
                    chunk_id = str(document.metadata.get("chunk_id") or "")
                    identity = chunk_id or f"{document.metadata!r}:{document.page_content}"
                    if identity in seen_ids:
                        continue
                    seen_ids.add(identity)
                    merged.append(document)
                    added = True
                    break
            if not added:
                break
        return merged
    return retriever.retrieve_with_audit(
        case.question,
        categories=plan.categories,
        retrieval_query=plan.retrieval_query,
        entity_filters=plan.entity_filters,
        data_roles=plan.data_roles,
        top_k=top_k,
    )


def run_evaluation(
    split: str = "all",
    *,
    top_k: int = 5,
    settings_obj: Settings = settings,
) -> dict[str, object]:
    """Run intent, retrieval and answer contract metrics for one fixed split."""

    dataset_report = validate_dataset()
    cases = load_cases(split)
    effective_top_k = max(1, int(top_k))
    retriever = _retriever(settings_obj=settings_obj)
    intent_report = evaluate_intents(
        cases,
        lambda case: analyze_question(
            case.question,
            ConversationState.from_value(case.state, default_year=settings_obj.target_year),
            default_year=settings_obj.target_year,
        ).intent,
    )
    retrieval_report = evaluate_retrieval(
        cases,
        lambda case: _retrieve_for_case(
            retriever,
            case,
            top_k=effective_top_k,
            settings_obj=settings_obj,
        ),
        top_k=effective_top_k,
    )

    llm = EvidenceEchoLLM()

    def answer_case(case: EvaluationCase) -> object:
        return ask_chatbot(
            case.question,
            retriever=retriever,
            llm=llm,
            conversation_state=case.state,
            settings_obj=settings_obj,
        )

    answer_report = evaluate_answers(cases, answer_case)
    return {
        "dataset": dataset_report,
        "split": split,
        "intent": intent_report,
        "retrieval": retrieval_report,
        "answer": answer_report,
        "generation_backend": "deterministic_evidence_echo_for_offline_contract_only",
        "holdout_policy": "report_only_not_used_for_tuning",
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="all")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = run_evaluation(args.split, top_k=args.top_k)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    print(f"Evaluation split: {args.split}")
    print(json.dumps({key: report[key] for key in ("dataset", "intent", "retrieval", "answer")}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
