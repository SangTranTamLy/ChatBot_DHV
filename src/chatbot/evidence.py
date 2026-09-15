"""Xây dựng bằng chứng và nguồn (source) do backend quản lý cho RAG."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
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
    """Một chunk được truy xuất chỉ có metadata do backend cung cấp."""

    text: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class EvidenceBundle:
    """Ngữ cảnh đã khử trùng lặp cộng với metadata nguồn gốc được truy xuất chính xác."""

    chunks: tuple[EvidenceChunk, ...]
    context: str
    sources: tuple[dict[str, str], ...]
    score_facts: tuple[dict[str, object], ...] = ()
    entity_relations: tuple[dict[str, str], ...] = ()

    @property
    def is_usable(self) -> bool:
        return bool(self.chunks and self.context.strip() and self.sources)


@dataclass(frozen=True)
class EvidenceSelection:
    """Kết quả chọn evidence sau retrieval, kèm lý do giữ/loại từng candidate."""

    documents: tuple[Document, ...]
    candidates: tuple[dict[str, object], ...]
    filtered: tuple[dict[str, object], ...]

    @property
    def selected_evidence(self) -> tuple[dict[str, object], ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.get("selected") is True
        )

    def to_dict(self) -> dict[str, object]:
        selected = [dict(candidate) for candidate in self.selected_evidence]
        filtered = [dict(candidate) for candidate in self.filtered]
        return {
            "candidate_count": len(self.candidates) + len(self.filtered),
            "selected_count": len(selected),
            "selected": selected,
            "filtered": filtered,
            "filter_reasons": [
                {
                    "chunk_id": item.get("chunk_id"),
                    "reason": item.get("filter_reason"),
                }
                for item in filtered
            ],
        }


def build_evidence(
    documents: Iterable[Document],
    *,
    settings_obj: Settings = settings,
    max_chars: int | None = None,
) -> EvidenceBundle:
    """Khử trùng lặp các chunk, giới hạn ngữ cảnh cho prompt và giữ nguyên metadata của nguồn."""

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


def merge_evidence_bundles(
    bundles: Iterable[EvidenceBundle],
    *,
    settings_obj: Settings = settings,
    max_chars: int | None = None,
) -> EvidenceBundle:
    """Gộp evidence của các sub-issue theo thứ tự, khử trùng lặp chunk."""

    documents: list[Document] = []
    seen: set[str] = set()
    for bundle in bundles:
        for chunk in bundle.chunks:
            identity = str(chunk.metadata.get("chunk_id") or "")
            if not identity:
                identity = hashlib.sha1(chunk.text.encode("utf-8")).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            documents.append(
                Document(page_content=chunk.text, metadata=dict(chunk.metadata))
            )
    return build_evidence(documents, settings_obj=settings_obj, max_chars=max_chars)


def _selection_entity_values(
    entities: Mapping[str, object] | None,
    candidates: Iterable[str] | None,
) -> tuple[str, ...]:
    values: list[str] = []
    for value in candidates or ():
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    for key in (
        "major_name",
        "major_code",
        "program_name",
        "parent_major",
        "candidate_majors",
        "candidate_programs",
    ):
        value = (entities or {}).get(key)
        items = value if isinstance(value, (list, tuple, set)) else (value,)
        for item in items:
            text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
    return tuple(values)


def _selection_filter_reason(
    document: Document,
    *,
    categories: tuple[str, ...],
    target_year: int,
) -> str | None:
    metadata = document.metadata or {}
    if metadata.get("status") != "verified":
        return "status_not_verified"
    try:
        if int(metadata.get("year")) != target_year:
            return "year_mismatch"
    except (TypeError, ValueError):
        return "year_mismatch"
    if str(metadata.get("school_code") or "").upper() != "DHV":
        return "target_institution_mismatch"
    if categories and str(metadata.get("category") or "") not in categories:
        return "category_not_requested"
    if not _valid_http_url(metadata.get("source_url")):
        return "source_url_invalid"
    if not (document.page_content or "").strip():
        return "empty_content"
    return None


def _entity_row_subset(text: str, entity_values: tuple[str, ...]) -> str:
    """Lấy nguyên row ngành/chương trình thay vì nguyên bảng rộng vào prompt."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    code_positions = [
        index for index, line in enumerate(lines) if _CODE_LINE_RE.fullmatch(line)
    ]
    if not code_positions:
        folded = _fold_text(text)
        return text if any(_fold_text(value) in folded for value in entity_values) else ""
    folded_values = tuple(
        _fold_text(value) for value in entity_values if _fold_text(value)
    )
    selected_rows: list[str] = []
    for position, code_position in enumerate(code_positions):
        start = max(0, code_position - 1)
        next_code = (
            code_positions[position + 1]
            if position + 1 < len(code_positions)
            else len(lines)
        )
        # The line immediately before the next code is that next row's major
        # label. Exclude it so a row at a chunk boundary cannot inherit the
        # following major as if it were its own program/entity.
        end = max(start + 1, next_code - 1) if next_code != len(lines) else next_code
        row = "\n".join(lines[start:end])
        folded_row = _fold_text(row)
        if any(value in folded_row for value in folded_values):
            selected_rows.append(row)
    return "\n\n".join(selected_rows)


def _selection_preview(document: Document, *, text: str | None = None) -> str:
    value = text if text is not None else document.page_content
    return value[:220].replace("\n", " | ")


def select_evidence_documents(
    documents: Iterable[Document],
    *,
    categories: Iterable[str] | None = None,
    entities: Mapping[str, object] | None = None,
    candidates: Iterable[str] | None = None,
    target_year: int = settings.target_year,
    intent: str | None = None,
) -> EvidenceSelection:
    """Chọn evidence sau retrieval theo metadata, category và entity đã phân tích.

    Với bảng danh mục, selection cắt theo row có thật trong document và giữ nguyên
    provenance; không tạo fact mới. Đây là ranh giới cuối trước khi build prompt.
    """

    del intent  # Reserved for future intent-specific policies; categories are authoritative.
    materialized = list(documents)
    category_values = tuple(
        str(category) for category in categories or () if str(category)
    )
    entity_values = _selection_entity_values(entities, candidates)
    selected: list[Document] = []
    candidate_audits: list[dict[str, object]] = []
    filtered_audits: list[dict[str, object]] = []
    row_selected_by_category: set[str] = set()

    for rank, document in enumerate(materialized, start=1):
        metadata = dict(document.metadata or {})
        reason = _selection_filter_reason(
            document,
            categories=category_values,
            target_year=target_year,
        )
        base = {
            "rank": rank,
            "chunk_id": metadata.get("chunk_id"),
            "category": metadata.get("category"),
            "year": metadata.get("year"),
            "status": metadata.get("status"),
            "title": metadata.get("title"),
            "selected": False,
            "filter_reason": reason,
            "matched_entities": [],
            "content_preview": _selection_preview(document),
        }
        if reason is not None:
            filtered_audits.append(base)
            continue

        category = str(metadata.get("category") or "")
        data_role = str(metadata.get("data_role") or "").strip().casefold()
        selected_document = document
        matched_entities = [
            value
            for value in entity_values
            if _fold_text(value) and _fold_text(value) in _fold_text(document.page_content)
        ]
        selection_reason = "metadata_and_category_match"
        if entity_values and category == "nganh_dao_tao" and data_role != "description":
            subset = _entity_row_subset(document.page_content, entity_values)
            if not subset.strip():
                base["filter_reason"] = "entity_not_in_document"
                filtered_audits.append(base)
                continue
            selected_document = Document(page_content=subset, metadata=metadata)
            matched_entities = [
                value
                for value in entity_values
                if _fold_text(value) and _fold_text(value) in _fold_text(subset)
            ]
            selection_reason = "entity_row_match"
            row_selected_by_category.add(category)
        elif entity_values and category in {"diem_trung_tuyen", "xet_tuyen_bo_sung"}:
            folded_text = _fold_text(document.page_content)
            if not matched_entities and not any(
                marker in folded_text for marker in ("phan lon", "toan bo", "chung")
            ):
                base["filter_reason"] = "entity_not_in_document"
                filtered_audits.append(base)
                continue
        elif entity_values and category == "nguong_dau_vao":
            # A generic threshold note contains an unrelated Luật caveat. Keep
            # it only when no entity-specific catalogue row is available.
            selection_reason = "generic_rule_match"

        base.update(
            {
                "selected": True,
                "selection_reason": selection_reason,
                "matched_entities": matched_entities,
                "content_preview": _selection_preview(
                    selected_document, text=selected_document.page_content
                ),
            }
        )
        selected.append(selected_document)
        candidate_audits.append(base)

    if entity_values and "nganh_dao_tao" in row_selected_by_category:
        # Remove generic threshold chunks only when selected catalogue rows
        # already carry the method/value mapping.
        kept: list[Document] = []
        removed: list[dict[str, object]] = []
        for document, audit in zip(selected, candidate_audits):
            if str((document.metadata or {}).get("category") or "") == "nguong_dau_vao":
                audit["selected"] = False
                audit["filter_reason"] = "generic_rule_shadowed_by_entity_row"
                removed.append(audit)
                continue
            kept.append(document)
        selected = kept
        candidate_audits = [audit for audit in candidate_audits if audit not in removed]
        filtered_audits.extend(removed)

    return EvidenceSelection(
        documents=tuple(selected),
        candidates=tuple(candidate_audits),
        filtered=tuple(filtered_audits),
    )


def select_evidence(
    documents: Iterable[Document],
    **kwargs: Any,
) -> EvidenceSelection:
    """Tên gọi ngắn tương thích cho lớp Evidence Selection sau retrieval."""

    return select_evidence_documents(documents, **kwargs)


def select_candidate_documents(
    documents: Iterable[Document],
    candidates: Iterable[str] | None = None,
) -> list[Document]:
    """Chỉ giữ lại các chunk truy xuất có nhắc đến ứng viên được yêu cầu một cách rõ ràng.

    Quá trình truy xuất tư vấn có thể trả về các dòng không liên quan từ một bảng danh mục rộng.
    Việc lọc ứng viên diễn ra sau khi truy xuất; row view (nếu cần) chỉ là lát cắt
    của chunk đã xác thực, không tạo fact mới hay thay thế provenance nguồn.
    """

    candidate_values = tuple(
        str(candidate).strip()
        for candidate in candidates or ()
        if str(candidate).strip()
    )
    materialized = list(documents)
    if not candidate_values:
        return materialized
    return list(
        select_evidence_documents(
            materialized,
            candidates=candidate_values,
            target_year=settings.target_year,
        ).documents
    )


def select_program_relations(
    relations: Iterable[dict[str, str]],
    *,
    parent_major: str | None = None,
) -> tuple[dict[str, str], ...]:
    """Chọn các dòng chương trình-ngành cha đã xác thực bằng so khớp chuẩn hóa (canonicalized matching).

    Các câu trả lời danh mục phải hoạt động dựa trên các mối quan hệ được trích xuất từ bằng chứng
    thay vì từ văn bản của model. Bộ lọc ngành cha tùy chọn được thiết kế chung:
    nó hoạt động cho mọi ngành có mặt trong corpus và không mã hóa cứng một ngành cụ thể
    vào logic nghiệp vụ.
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
    """Tách biệt các ánh xạ điểm số và quan hệ ngành/chương trình khỏi văn xuôi (prose)."""

    facts: list[dict[str, object]] = []
    relations: list[dict[str, str]] = []
    seen_facts: set[tuple[object, ...]] = set()
    seen_relations: set[tuple[str, str]] = set()
    for chunk in chunks:
        category = str(chunk.metadata.get("category") or "")
        data_role = str(chunk.metadata.get("data_role") or "").strip().casefold()
        text = chunk.text
        parses_catalog_table = category == "nguong_dau_vao" or (
            category == "nganh_dao_tao" and data_role != "description"
        )
        if parses_catalog_table:
            row_facts, row_relations = _parse_threshold_table(text, category)
            row_facts = [{**fact, **_fact_provenance(chunk)} for fact in row_facts]
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
                            **_fact_provenance(chunk),
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
                    **_fact_provenance(chunk),
                }
                if _remember_fact(seen_facts, fact):
                    facts.append(fact)
        elif category == "xet_tuyen_bo_sung":
            for fact in _parse_supplementary_facts(text, chunk):
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
                    **_fact_provenance(chunk),
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


def _fact_provenance(chunk: EvidenceChunk) -> dict[str, object]:
    """Gắn provenance tối thiểu để score engine không dùng fact thiếu verified."""

    metadata = chunk.metadata
    return {
        "status": metadata.get("status"),
        "source_status": metadata.get("status"),
        "year": metadata.get("year"),
    }


def _parse_supplementary_facts(
    text: str,
    chunk: EvidenceChunk,
) -> list[dict[str, object]]:
    """Tách rule bổ sung theo method và giữ ngoại lệ Luật ở đúng entity."""

    facts: list[dict[str, object]] = []
    matched_method_line = False
    for line in text.splitlines():
        folded = _fold_text(line)
        if "hoc ba" in folded:
            method = "hoc_ba"
        elif "thi tot nghiep thpt" in folded or "thi thpt" in folded:
            method = "thpt"
        else:
            continue
        matched_method_line = True
        parts = [part.strip(" •-") for part in line.split(";") if part.strip(" •-")]
        for part in parts:
            part_folded = _fold_text(part)
            value_match = re.search(
                r"\btu\s+(\d+(?:[.,]\d+)?)\s*diem\b",
                part_folded,
                re.IGNORECASE,
            )
            raw_value = value_match.group(1) if value_match else None
            major_names = _supplementary_major_names(part, part_folded)
            if raw_value is None and not major_names[0]:
                continue
            if raw_value is None and "dieu kien rieng" not in part_folded:
                continue
            for major_name in major_names:
                raw = raw_value or "điều kiện riêng"
                facts.append(
                    {
                        "major_name": major_name,
                        "major_code": None,
                        "score_type": "supplementary_threshold",
                        "method": method,
                        "raw_value": raw,
                        "value": _numeric_or_none(raw) if raw_value else None,
                        "category": "xet_tuyen_bo_sung",
                        **_fact_provenance(chunk),
                    }
                )
    if matched_method_line:
        return facts

    # Keep compatibility with compact fixtures that put the method and value
    # in one prose sentence instead of the source's semicolon-separated lines.
    for match in _SUPPLEMENTARY_FACT_RE.finditer(text):
        method = "hoc_ba" if "học bạ" in match.group(0).lower() else "thpt"
        facts.append(
            {
                "major_name": None,
                "major_code": None,
                "score_type": "supplementary_threshold",
                "method": method,
                "raw_value": match.group(1),
                "value": _numeric_or_none(match.group(1)),
                "category": "xet_tuyen_bo_sung",
                **_fact_provenance(chunk),
            }
        )
    return facts


def _supplementary_major_names(part: str, folded_part: str) -> tuple[str | None, ...]:
    """Lấy tên entity từ câu nguồn, không gắn logic với một ngành cụ thể."""

    if "phan lon chuong trinh" in folded_part:
        return (None,)
    prefix = re.split(r"\b(?:từ|tu)\b|\bcó\s+điều\s+kiện\s+riêng\b|\bco\s+dieu\s+kien\s+rieng\b", part, maxsplit=1, flags=re.IGNORECASE)[0]
    prefix = re.sub(
        r"^.*?(?:học\s+bạ(?:\s+THPT)?|hoc\s+ba(?:\s+THPT)?|thi\s+tốt\s+nghiệp\s+THPT(?:\s+20\d{2})?|thi\s+thpt(?:\s+20\d{2})?)\s*:?\s*",
        "",
        prefix,
        flags=re.IGNORECASE,
    )
    prefix = prefix.strip(" •-:.")
    if not prefix or "phan lon" in _fold_text(prefix):
        return (None,)
    names = tuple(
        name.strip(" •-:.")
        for name in re.split(r"\s+(?:và|va)\s+", prefix, flags=re.IGNORECASE)
        if name.strip(" •-:.")
    )
    return names or (None,)


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
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or not (
            hostname == "dhv.edu.vn"
            or hostname == "www.dhv.edu.vn"
            or hostname.endswith(".dhv.edu.vn")
        )
    ):
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
    "EvidenceSelection",
    "build_evidence",
    "select_candidate_documents",
    "select_evidence",
    "select_evidence_documents",
    "merge_evidence_bundles",
    "select_program_relations",
]
