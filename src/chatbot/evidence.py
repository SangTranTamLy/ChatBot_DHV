"""Evidence and backend-owned source construction for RAG."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from langchain_core.documents import Document

from src.config.settings import Settings, settings


_URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>]+", re.IGNORECASE)
_SOURCE_LINE_RE = re.compile(
    r"^\s*(?:nguồn(?: chính thức| cập nhật)?|ngày cập nhật nguồn|ngày kiểm tra)\s*:",
    re.IGNORECASE,
)
_CODE_LINE_RE = re.compile(r"^\s*(\d{7})\s*$")
_NUMBER_LINE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")
_THRESHOLD_FACT_PATTERNS = (
    ("thpt", re.compile(r"thi\s+tốt\s+nghiệp\s+THPT[^\d-]{0,80}?(?:từ\s*)?(\d+(?:[.,]\d+)?|-)", re.IGNORECASE)),
    ("hoc_ba", re.compile(r"học\s+bạ[^\d-]{0,80}?(?:từ\s*)?(\d+(?:[.,]\d+)?|-)", re.IGNORECASE)),
    ("dgnl", re.compile(r"đánh\s+giá\s+năng\s+lực[^\d-]{0,100}?(?:từ\s*)?(\d+(?:[.,]\d+)?|-)", re.IGNORECASE)),
)
_ADMISSION_FACT_RE = re.compile(
    r"(?:^|[•\n])\s*(?P<major>[^:\n]+?)\s*:\s*(?P<value>\d+(?:[.,]\d+)?)\s*điểm",
    re.IGNORECASE,
)
_SUPPLEMENTARY_FACT_RE = re.compile(
    r"(?:thi\s+tốt\s+nghiệp\s+THPT|học\s+bạ\s+THPT)[^\n]*?(?:từ\s*)(\d+(?:[.,]\d+)?)\s*điểm",
    re.IGNORECASE,
)
_SUPPLEMENTARY_DATE_FACT_RE = re.compile(
    r"(?:đến\s+hết\s+ngày|đến\s+ngày)\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceChunk:
    """A retrieved chunk with only backend-provided metadata."""

    text: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class EvidenceBundle:
    """Deduplicated context plus the exact retrieved source metadata."""

    chunks: tuple[EvidenceChunk, ...]
    context: str
    sources: tuple[dict[str, str], ...]
    score_facts: tuple[dict[str, object], ...] = ()
    entity_relations: tuple[dict[str, str], ...] = ()

    @property
    def is_usable(self) -> bool:
        return bool(self.chunks and self.context.strip() and self.sources)


def build_evidence(
    documents: Iterable[Document],
    *,
    settings_obj: Settings = settings,
    max_chars: int | None = None,
) -> EvidenceBundle:
    """Deduplicate chunks, cap the prompt context and preserve source metadata."""

    limit = settings_obj.rag_max_context_chars if max_chars is None else max_chars
    if limit < 100:
        raise ValueError("max_chars must be at least 100")

    chunks: list[EvidenceChunk] = []
    context_parts: list[str] = []
    seen_chunks: set[str] = set()
    remaining = limit
    for document in documents:
        text = _clean_context_text(document.page_content or "")
        metadata = dict(document.metadata or {})
        if metadata.get("status") != "verified":
            continue
        if not text:
            continue
        identity = str(metadata.get("chunk_id") or "")
        if not identity:
            identity = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if identity in seen_chunks:
            continue
        url = _valid_http_url(metadata.get("source_url"))
        if not url:
            continue
        separator = "\n\n" if context_parts else ""
        static_context = "\n".join(
            [
                f"[Evidence {len(context_parts) + 1}]",
                f"Tiêu đề: {metadata.get('title', '')}",
                f"Nhóm: {metadata.get('category', '')}",
                f"Năm: {metadata.get('year', '')}",
                f"Mục: {metadata.get('heading_path', '')}",
                "Nội dung: ",
            ]
        )
        available = remaining - len(separator) - len(static_context)
        if available <= 0:
            break
        clipped = text[:available]
        if not clipped.strip():
            break
        seen_chunks.add(identity)
        chunks.append(EvidenceChunk(text=clipped, metadata=metadata))
        context_parts.append(static_context + clipped)
        remaining -= len(separator) + len(static_context) + len(clipped)

    score_facts, entity_relations = _extract_structured_facts(chunks)
    return EvidenceBundle(
        chunks=tuple(chunks),
        context="\n\n".join(context_parts),
        sources=_backend_sources(chunks),
        score_facts=score_facts,
        entity_relations=entity_relations,
    )


def select_candidate_documents(
    documents: Iterable[Document],
    candidates: Iterable[str] | None = None,
) -> list[Document]:
    """Keep only retrieved chunks that explicitly mention a requested candidate.

    Advisory retrieval can return unrelated rows from a broad category table.
    Candidate filtering happens after retrieval, never by manufacturing a
    document, so the remaining context and structured facts stay grounded in
    the verified chunks that name the user's choices.
    """

    candidate_values = tuple(
        _fold_text(candidate)
        for candidate in candidates or ()
        if str(candidate).strip()
    )
    materialized = list(documents)
    if not candidate_values:
        return materialized
    selected: list[Document] = []
    for document in materialized:
        if (document.metadata or {}).get("status") != "verified":
            continue
        text = _fold_text(document.page_content or "")
        if any(candidate in text for candidate in candidate_values):
            selected.append(document)
    return selected


def select_program_relations(
    relations: Iterable[dict[str, str]],
    *,
    parent_major: str | None = None,
) -> tuple[dict[str, str], ...]:
    """Select verified program-parent rows with canonicalized matching.

    Catalog answers must operate on relations extracted from evidence rather
    than on model text.  The optional parent filter is intentionally generic:
    it works for any major present in the corpus and does not encode a named
    major in business logic.
    """

    requested_parent = _fold_text(parent_major) if parent_major else ""
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for relation in relations or ():
        program = str(relation.get("program_name") or "").strip()
        parent = str(relation.get("parent_major") or "").strip()
        if not program or not parent:
            continue
        if requested_parent and _fold_text(parent) != requested_parent:
            continue
        identity = (_fold_text(parent), _fold_text(program))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append({"program_name": program, "parent_major": parent})
    return tuple(selected)


def _extract_structured_facts(
    chunks: Iterable[EvidenceChunk],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, str], ...]]:
    """Keep score mappings and major/program relations separate from prose."""

    facts: list[dict[str, object]] = []
    relations: list[dict[str, str]] = []
    seen_facts: set[tuple[object, ...]] = set()
    seen_relations: set[tuple[str, str]] = set()
    for chunk in chunks:
        category = str(chunk.metadata.get("category") or "")
        text = chunk.text
        if category in {"nganh_dao_tao", "nguong_dau_vao"}:
            row_facts, row_relations = _parse_threshold_table(text, category)
            facts.extend(
                fact
                for fact in row_facts
                if _remember_fact(seen_facts, fact)
            )
            for relation in row_relations:
                identity = (relation["parent_major"], relation["program_name"])
                if identity not in seen_relations:
                    seen_relations.add(identity)
                    relations.append(relation)
            if category == "nguong_dau_vao":
                for method, pattern in _THRESHOLD_FACT_PATTERNS:
                    for match in pattern.finditer(text):
                        raw_value = match.group(1)
                        fact = {
                            "major_name": None,
                            "major_code": None,
                            "score_type": "application_threshold",
                            "method": method,
                            "raw_value": raw_value,
                            "value": _numeric_or_none(raw_value),
                            "category": category,
                        }
                        if _remember_fact(seen_facts, fact):
                            facts.append(fact)
        elif category == "diem_trung_tuyen":
            for match in _ADMISSION_FACT_RE.finditer(text):
                fact = {
                    "major_name": match.group("major").strip(" •*-").strip(),
                    "major_code": None,
                    "score_type": "admission_score",
                    "method": "thpt",
                    "raw_value": match.group("value"),
                    "value": _numeric_or_none(match.group("value")),
                    "category": category,
                }
                if _remember_fact(seen_facts, fact):
                    facts.append(fact)
        elif category == "xet_tuyen_bo_sung":
            for match in _SUPPLEMENTARY_FACT_RE.finditer(text):
                method = "hoc_ba" if "học bạ" in match.group(0).lower() else "thpt"
                fact = {
                    "major_name": None,
                    "major_code": None,
                    "score_type": "supplementary_threshold",
                    "method": method,
                    "raw_value": match.group(1),
                    "value": _numeric_or_none(match.group(1)),
                    "category": category,
                }
                if _remember_fact(seen_facts, fact):
                    facts.append(fact)
            for match in _SUPPLEMENTARY_DATE_FACT_RE.finditer(text):
                fact = {
                    "major_name": None,
                    "major_code": None,
                    "score_type": "supplementary_threshold",
                    "method": "deadline",
                    "raw_value": match.group(1),
                    "value": None,
                    "category": category,
                }
                if _remember_fact(seen_facts, fact):
                    facts.append(fact)
    return tuple(facts), tuple(relations)


def _remember_fact(seen: set[tuple[object, ...]], fact: dict[str, object]) -> bool:
    identity = (
        fact.get("major_name"),
        fact.get("major_code"),
        fact.get("score_type"),
        fact.get("method"),
        fact.get("raw_value"),
        fact.get("category"),
    )
    if identity in seen:
        return False
    seen.add(identity)
    return True


def _numeric_or_none(value: str) -> int | float | None:
    if value.strip() == "-":
        return None
    try:
        parsed = float(value.replace(",", "."))
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _parse_threshold_table(
    text: str,
    category: str,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    facts: list[dict[str, object]] = []
    relations: list[dict[str, str]] = []
    for index, line in enumerate(lines[:-1]):
        code_match = _CODE_LINE_RE.match(line)
        if not code_match or index == 0:
            continue
        major_name = lines[index - 1]
        if major_name.upper() in {"MÃ NGÀNH", "MA NGANH"}:
            continue
        end = next(
            (position for position in range(index + 1, len(lines)) if _CODE_LINE_RE.match(lines[position])),
            len(lines),
        )
        body_lines = lines[index + 1 : end]
        value_positions = [
            position for position, value in enumerate(body_lines)
            if _NUMBER_LINE_RE.match(value) or value == "-"
        ]
        values = [body_lines[position] for position in value_positions[:3]]
        if len(values) == 3:
            for method, raw_value in zip(("thpt", "hoc_ba", "dgnl"), values):
                facts.append(
                    {
                        "major_name": major_name,
                        "major_code": code_match.group(1),
                        "score_type": "application_threshold",
                        "method": method,
                        "raw_value": raw_value,
                        "value": _numeric_or_none(raw_value),
                        "category": category,
                    }
                )
        if category == "nganh_dao_tao":
            program_text = " ".join(body_lines[: value_positions[0] if value_positions else len(body_lines)])
            for program in re.split(r";", program_text):
                program = program.strip(" •-.")
                # The source table owns the semantic distinction between the
                # major column and the program column.  A program can legally
                # have the same display name as its parent; preserve that
                # explicit relation instead of treating it as a duplicate.
                if program:
                    relations.append({"parent_major": major_name, "program_name": program})
    return facts, relations


def _backend_sources(chunks: Iterable[EvidenceChunk]) -> tuple[dict[str, str], ...]:
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for chunk in chunks:
        metadata = chunk.metadata
        url = _valid_http_url(metadata.get("source_url"))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(metadata.get("title") or metadata.get("source_name") or "DHV")
        sources.append({"title": title, "url": url})
    return tuple(sources)


def _valid_http_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _clean_context_text(text: str) -> str:
    lines = []
    for line in _URL_RE.sub("", text).splitlines():
        if _SOURCE_LINE_RE.match(line):
            continue
        if line.strip():
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _fold_text(value: object) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", folded.lower().replace("đ", "d")).strip()


__all__ = [
    "EvidenceBundle",
    "EvidenceChunk",
    "build_evidence",
    "select_candidate_documents",
    "select_program_relations",
]
