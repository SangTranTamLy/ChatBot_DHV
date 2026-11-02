"""Common, source-backed facts and bounded conversation resolution contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


FACT_STATUSES = frozenset({"VERIFIED", "PARTIAL", "MISSING", "CONFLICT"})
CONTEXT_STATUSES = frozenset({"RESOLVED", "AMBIGUOUS", "UNRESOLVED"})

_SUBJECT_FIELDS = (
    "major_name",
    "major_code",
    "parent_major",
    "parent_major_code",
    "program_name",
    "scholarship_name",
    "method",
    "method_number",
    "semester",
    "unit_name",
    "unit_type",
)
_PROVENANCE_FIELDS = frozenset(
    {
        "document_id",
        "structured_document_id",
        "structured_record_id",
        "chunk_id",
        "page",
        "year",
        "title",
        "source_sha256",
        "source_date",
        "collected_at",
        "status",
        "verification_status",
        "source_file",
        "source_url",
        "source_urls",
        "raw_file",
    }
)


def _safe_scalar_or_json(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_safe_scalar_or_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _safe_scalar_or_json(item) for key, item in value.items()}
    return str(value)


@dataclass(frozen=True)
class FactProvenance:
    """Private trace back to the exact indexed source; never includes local paths."""

    source_id: str
    document_id: str
    record_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    source_sha256: str | None = None
    title: str = ""
    public_url: str | None = None

    def to_dict(self, *, for_prompt: bool = False) -> dict[str, object]:
        if for_prompt:
            # Provenance is for backend audits only. The model gets the verified
            # values, not internal record IDs, storage names or URLs.
            return {}
        value: dict[str, object] = {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "record_id": self.record_id,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "title": self.title,
        }
        value["source_sha256"] = self.source_sha256
        value["public_url"] = self.public_url
        return {key: item for key, item in value.items() if item not in (None, "")}


@dataclass(frozen=True)
class VerifiedFact:
    """A fact or evidence excerpt with an explicit status and source provenance."""

    fact_id: str
    fact_type: str
    value: object
    subject: Mapping[str, object] = field(default_factory=dict)
    unit: str | None = None
    academic_year: int | None = None
    status: str = "VERIFIED"
    attributes: Mapping[str, object] = field(default_factory=dict)
    provenance: FactProvenance | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in FACT_STATUSES:
            raise ValueError(f"Unsupported fact status: {self.status}")
        if not self.fact_id.strip() or not self.fact_type.strip():
            raise ValueError("fact_id and fact_type must not be empty")

    def to_dict(self, *, for_prompt: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "fact_id": self.fact_id,
            "fact_type": self.fact_type,
            "subject": _safe_scalar_or_json(self.subject),
            "value": _safe_scalar_or_json(self.value),
            "unit": self.unit,
            "academic_year": self.academic_year,
            "status": self.status,
            "attributes": _safe_scalar_or_json(self.attributes),
            "reason": self.reason,
        }
        if self.provenance:
            result["provenance"] = self.provenance.to_dict(for_prompt=for_prompt)
        return {key: value for key, value in result.items() if value not in (None, "", {})}


@dataclass(frozen=True)
class ResolvedContext:
    """Resolved query and bounded state; conversation state is not source evidence."""

    original_question: str
    resolved_question: str
    status: str = "RESOLVED"
    method: str = "independent_question"
    entities: Mapping[str, object] = field(default_factory=dict)
    clarification: str = ""

    def __post_init__(self) -> None:
        if self.status not in CONTEXT_STATUSES:
            raise ValueError(f"Unsupported context status: {self.status}")

    def to_dict(self, *, for_prompt: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "original_question": self.original_question,
            "resolved_question": self.resolved_question,
            "status": self.status,
            "method": self.method,
            "entities": _safe_scalar_or_json(self.entities),
        }
        if self.clarification:
            result["clarification"] = self.clarification
        return result


def facts_from_chunks(chunks: Sequence[Any]) -> tuple[VerifiedFact, ...]:
    """Normalize selected evidence chunks into source-backed prompt facts.

    Every item is tied to a verified chunk. Structured scalar metadata remains
    available as attributes, while the readable chunk text preserves prose and
    table context for fields that have no dedicated parser yet.
    """

    facts: list[VerifiedFact] = []
    seen: set[str] = set()
    for chunk in chunks:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        if str(metadata.get("status") or "").casefold() != "verified":
            continue
        text = str(getattr(chunk, "text", "") or "").strip()
        if not text:
            continue

        document_id = str(metadata.get("document_id") or metadata.get("structured_document_id") or "")
        record_id = str(metadata.get("structured_record_id") or "") or None
        chunk_id = str(metadata.get("chunk_id") or "") or None
        identity = "|".join((document_id, record_id or "", chunk_id or "", text[:160]))
        fact_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        if fact_id in seen:
            continue
        seen.add(fact_id)

        subject = {
            key: metadata[key]
            for key in _SUBJECT_FIELDS
            if metadata.get(key) not in (None, "", "-")
        }
        attributes = {
            str(key): _safe_scalar_or_json(value)
            for key, value in metadata.items()
            if key not in _PROVENANCE_FIELDS
            and key not in _SUBJECT_FIELDS
            and not any(
                marker in str(key).casefold()
                for marker in ("path", "file", "url", "sha256", "document", "chunk", "record", "page")
            )
            and value not in (None, "", [])
            and (isinstance(value, (str, int, float, bool)) or isinstance(value, (list, tuple, dict)))
        }
        try:
            year = int(metadata.get("year")) if metadata.get("year") is not None else None
        except (TypeError, ValueError, OverflowError):
            year = None
        page_value = metadata.get("page")
        try:
            page = int(page_value) if page_value is not None else None
        except (TypeError, ValueError, OverflowError):
            page = None

        source_id = document_id or str(metadata.get("source_sha256") or fact_id)
        provenance = FactProvenance(
            source_id=source_id,
            document_id=document_id or source_id,
            record_id=record_id,
            page=page,
            chunk_id=chunk_id,
            source_sha256=str(metadata.get("source_sha256") or "") or None,
            title=str(metadata.get("title") or "DHV"),
            public_url=str(metadata.get("source_url") or "") or None,
        )
        fact_type = ".".join(
            str(value)
            for value in (
                metadata.get("fact_category") or metadata.get("category") or "source",
                metadata.get("record_type") or "excerpt",
            )
            if value
        )
        facts.append(
            VerifiedFact(
                fact_id=fact_id,
                fact_type=fact_type,
                # Keep one bounded excerpt per retrieved record. Full source
                # text remains available in CONTEXT; copying entire pages here
                # would drown useful facts in duplicated prompt content.
                value=text[:1200],
                subject=subject,
                unit=(str(metadata.get("unit_name") or metadata.get("unit_type") or "") or None),
                academic_year=year,
                status="VERIFIED",
                attributes=attributes,
                provenance=provenance,
            )
        )

        # Materialize major → program links as their own atomic facts too.
        raw_programs = metadata.get("program_names")
        try:
            programs = json.loads(raw_programs) if isinstance(raw_programs, str) else raw_programs
        except (TypeError, json.JSONDecodeError):
            programs = ()
        if isinstance(programs, Sequence) and not isinstance(programs, (str, bytes)):
            for program in programs:
                program_name = str(program or "").strip()
                parent_major = str(metadata.get("major_name") or "").strip()
                if not program_name or not parent_major:
                    continue
                relation_id = hashlib.sha256(
                    f"{fact_id}|{parent_major}|{program_name}".encode("utf-8")
                ).hexdigest()[:20]
                facts.append(
                    VerifiedFact(
                        fact_id=relation_id,
                        fact_type="nganh_dao_tao.program_relation",
                        subject={"parent_major": parent_major},
                        value=program_name,
                        academic_year=year,
                        status="VERIFIED",
                        provenance=provenance,
                    )
                )

    return tuple(facts)


def facts_from_score_facts(score_facts: Sequence[Mapping[str, object]]) -> tuple[VerifiedFact, ...]:
    """Normalize deterministic admission score records into the shared schema."""

    facts: list[VerifiedFact] = []
    for index, row in enumerate(score_facts):
        if str(row.get("source_status") or row.get("status") or "").casefold() != "verified":
            continue
        raw_value = row.get("raw_value", row.get("value"))
        missing = raw_value in (None, "", "-")
        year_value = row.get("year")
        try:
            year = int(year_value) if year_value is not None else None
        except (TypeError, ValueError, OverflowError):
            year = None
        document_id = str(row.get("document_id") or row.get("structured_document_id") or "")
        chunk_id = str(row.get("chunk_id") or "") or None
        source_id = document_id or chunk_id or f"score-{index}"
        provenance = FactProvenance(
            source_id=source_id,
            document_id=document_id or source_id,
            record_id=str(row.get("structured_record_id") or "") or None,
            page=int(row["page"]) if str(row.get("page") or "").isdigit() else None,
            chunk_id=chunk_id,
            source_sha256=str(row.get("source_sha256") or "") or None,
            title=str(row.get("title") or "DHV"),
            public_url=str(row.get("source_url") or "") or None,
        )
        subject = {
            key: row[key]
            for key in ("major_name", "major_code", "method", "score_type", "category")
            if row.get(key) not in (None, "", "-")
        }
        facts.append(
            VerifiedFact(
                fact_id=f"score-{index}-{source_id}",
                fact_type=str(row.get("score_type") or "admission_score"),
                subject=subject,
                value=None if missing else raw_value,
                unit="điểm",
                academic_year=year,
                status="MISSING" if missing else "VERIFIED",
                attributes={
                    key: _safe_scalar_or_json(row[key])
                    for key in ("method_number", "threshold_type", "special_rule")
                    if row.get(key) not in (None, "", [])
                },
                provenance=provenance,
                reason="Nguồn đã xác minh không công bố giá trị cho phương thức này." if missing else None,
            )
        )
    groups: dict[tuple[object, ...], list[int]] = defaultdict(list)
    for index, fact in enumerate(facts):
        subject = fact.subject
        key = (
            fact.fact_type,
            fact.academic_year,
            subject.get("major_name"),
            subject.get("major_code"),
            subject.get("method"),
            subject.get("category"),
        )
        groups[key].append(index)
    for indexes in groups.values():
        values = {str(facts[index].value) for index in indexes}
        if len(values) > 1:
            for index in indexes:
                facts[index] = replace(
                    facts[index],
                    status="CONFLICT",
                    reason="Nguồn đã xác minh có các giá trị khác nhau cho cùng dữ kiện.",
                )
    return tuple(facts)


def prompt_facts(facts: Sequence[VerifiedFact], *, limit: int = 24) -> list[dict[str, object]]:
    """Return bounded facts with no local path or direct file URL."""

    return [fact.to_dict(for_prompt=True) for fact in facts[:limit]]


__all__ = [
    "CONTEXT_STATUSES",
    "FACT_STATUSES",
    "FactProvenance",
    "ResolvedContext",
    "VerifiedFact",
    "facts_from_chunks",
    "facts_from_score_facts",
    "prompt_facts",
]
