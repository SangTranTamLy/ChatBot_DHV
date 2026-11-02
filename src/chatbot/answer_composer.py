"""Shared Qwen response composer for source-backed answers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import json
from typing import Any

from src.config.settings import Settings, settings
from src.prompts.rag_prompt import build_rag_prompt

from .facts import FACT_STATUSES, VerifiedFact, facts_from_score_facts, prompt_facts
from .evidence import EvidenceChunk
from .generation_guards import _validated_generation


def _evidence_with_derived_facts(evidence: Any, facts: Sequence[VerifiedFact]) -> Any:
    """Let deterministic, source-linked calculations participate in grounding.

    A computed tuition total may not occur verbatim in the PDF. It is still
    verifiable when a backend calculator produced it from a selected official
    row, so expose only such VERIFIED facts to the validator as derived chunks.
    Their metadata inherits the original official source contract and the
    public source list stays unchanged.
    """

    original_chunks = tuple(getattr(evidence, "chunks", ()) or ())
    derived_chunks: list[EvidenceChunk] = []
    for fact in facts:
        if fact.status != "VERIFIED" or fact.provenance is None:
            continue
        source_chunk = next(
            (
                chunk
                for chunk in original_chunks
                if (
                    fact.provenance.chunk_id
                    and str(chunk.metadata.get("chunk_id") or "") == fact.provenance.chunk_id
                )
                or (
                    fact.provenance.document_id
                    and str(
                        chunk.metadata.get("document_id")
                        or chunk.metadata.get("structured_document_id")
                        or ""
                    ) == fact.provenance.document_id
                )
            ),
            None,
        )
        if source_chunk is None:
            continue
        value = fact.value
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        detail = [str(value)]
        if fact.unit:
            detail.append(f"Đơn vị: {fact.unit}")
        if fact.academic_year:
            detail.append(f"Năm áp dụng: {fact.academic_year}")
        detail.extend(
            f"{key}: {item}"
            for key, item in fact.attributes.items()
            if item not in (None, "", [], {})
        )
        metadata = dict(source_chunk.metadata)
        metadata["record_type"] = "derived_verified_fact"
        derived_chunks.append(EvidenceChunk(text="\n".join(detail), metadata=metadata))
    if not derived_chunks:
        return evidence
    return replace(evidence, chunks=original_chunks + tuple(derived_chunks))


def compose_verified_response(
    *,
    active_llm: Any,
    question: str,
    original_question: str | None,
    resolved_context: Mapping[str, object] | None,
    analysis: Any,
    evidence: Any,
    conversation_state: Mapping[str, object] | None,
    answer_plan: Any,
    score_facts: Sequence[Mapping[str, object]] = (),
    score_comparisons: Sequence[Mapping[str, object]] = (),
    entity_relations: Sequence[Mapping[str, str]] = (),
    additional_facts: Sequence[VerifiedFact | Mapping[str, object]] = (),
    required_phrases: Sequence[str] = (),
    settings_obj: Settings = settings,
) -> dict[str, object]:
    """Generate once from normalized facts, then run the existing grounding checks."""

    facts = prompt_facts(tuple(getattr(evidence, "facts", ()) or ()))
    facts.extend(
        prompt_facts(facts_from_score_facts(score_facts))
    )
    normalized_additional_facts: list[VerifiedFact] = []
    for fact in additional_facts:
        if isinstance(fact, VerifiedFact):
            normalized_additional_facts.append(fact)
            facts.append(fact.to_dict(for_prompt=True))
        elif isinstance(fact, Mapping):
            status = str(fact.get("status") or "VERIFIED").upper()
            if status in FACT_STATUSES:
                facts.append(dict(fact))

    prompt = build_rag_prompt(
        question,
        str(getattr(evidence, "context", "") or ""),
        original_question=original_question,
        resolved_context=resolved_context,
        intent=getattr(analysis, "intent", None),
        entities=getattr(analysis, "entities", {}),
        conversation_state=conversation_state,
        answer_plan=answer_plan,
        score_facts=list(score_facts),
        score_comparisons=list(score_comparisons),
        entity_relations=list(entity_relations),
        verified_facts=facts,
    )
    validation_evidence = _evidence_with_derived_facts(
        evidence, normalized_additional_facts
    )
    return _validated_generation(
        active_llm=active_llm,
        prompt=prompt,
        evidence=validation_evidence,
        question=question,
        analysis=analysis,
        score_facts=score_facts,
        answer_plan=answer_plan,
        score_comparisons=score_comparisons,
        required_phrases=required_phrases,
        target_year=settings_obj.target_year,
    )


__all__ = ["compose_verified_response"]
