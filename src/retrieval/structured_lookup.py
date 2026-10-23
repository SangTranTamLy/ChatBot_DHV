"""Exact field lookup over JSON-record metadata already stored in Chroma.

The caller supplies verified, year/category-filtered documents. SQLite is an
ephemeral index only: no source file, persistent database or embedding is changed.
Returned documents retain their original text, chunk identity and provenance.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from typing import Iterable, Mapping

from langchain_core.documents import Document


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().replace("đ", "d").replace("&", " va "))
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def _requested_kinds(query: str) -> tuple[str, ...]:
    from src.chatbot.query_semantics import enrollment_request

    # Ignore router annotations: an intent label is not a user request.
    query = _fold(query.partition("intent:")[0])
    request = enrollment_request(query)
    if request in {"reception_hours", "reception_dates", "submission_mode"}:
        return (request,)
    location = any(x in query for x in ("co so", "dia diem", "dia chi", "o dau", "noi nao"))
    if location and any(x in query for x in ("nop ho so", "nhap hoc")):
        return ("enrollment_location",)
    if "email" in query:
        return ("email",)
    if any(x in query for x in ("hotline", "dien thoai", "so zalo")):
        return ("phone",)
    if location:
        return ("campus",)
    if "thong tin lien he" in query:
        return ("email", "phone", "campus")
    if any(x in query for x in ("hoc phi", "tin chi", "phi nhap hoc", "hoc lieu")):
        return ("tuition",)
    if any(x in query for x in ("diem chuan", "diem trung tuyen")):
        return ("admission_score",)
    if any(x in query for x in ("diem san", "nguong", "diem dau vao", "diem nhan ho so")):
        return ("admission_threshold",)
    if any(x in query for x in ("han nop", "han nhan", "han xet tuyen", "khi nao", "ngay nao")):
        return ("deadline",)
    if "ho so" in query or "giay to" in query:
        return ("enrollment_document",)
    if "phuong thuc" in query:
        return ("admission_method",)
    if "ma nganh" in query or re.search(r"\b\d{7}\b", query):
        return ("major",)
    return ()


def _document_kinds(document: Document) -> set[str]:
    metadata = document.metadata
    kind = str(metadata.get("record_type") or "")
    kinds = {kind} if kind else set()
    if kind == "application_threshold":
        kinds.add("admission_threshold")
    # Campus/contact facts are not yet separate JSON records. Index only
    # explicit labelled source lines, never infer an address from a mention
    # in a historical paragraph. Keep the full original document as evidence.
    text = _fold(document.page_content)
    if metadata.get("category") in {"ho_so", "nhap_hoc"}:
        if "tiep nhan nhap hoc" in text and re.search(r"\b\d{1,2}:\d{2}\b", text):
            kinds.update(("reception_hours", "reception_dates"))
        if any(x in text for x in ("nhap hoc truc tuyen", "he thong unizone")):
            kinds.add("submission_mode")
    if re.search(r"\bco so\s*\d+\s*[:–-]", text):
        if metadata.get("category") in {"ho_so", "nhap_hoc", "xet_tuyen_bo_sung"} and any(
            x in text for x in ("tiep nhan ho so", "nop ho so", "dia diem nhap hoc", "nhap hoc truc tiep")
        ):
            kinds.add("enrollment_location")
        if metadata.get("category") in {"thong_tin_truong", "co_so_lien_he"}:
            kinds.add("campus")
    if re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text):
        kinds.add("email")
    if re.search(r"(?:hotline|tong dai|dien thoai|sdt)[^\n]{0,50}\b0\d[\d .()-]{7,}", text):
        kinds.add("phone")
    if metadata.get("category") == "nguong_dau_vao" and any(
        key.startswith("application_threshold_") for key in metadata
    ):
        kinds.add("admission_threshold")
    return kinds


def lookup_structured_documents(
    query: str,
    documents: Iterable[Document],
    entity_filters: Mapping[str, object] | None = None,
) -> list[Document]:
    """Query typed records and exact entities; no lexical or vector scoring.

    An unsupported lookup simply contributes no third-stream vote. All SQL
    values, including user-derived entities, are bound parameters.
    """
    kinds = _requested_kinds(query)
    if not kinds:
        return []
    filters = entity_filters or {}
    body = _fold(query.partition("intent:")[0])
    has_entity = any(filters.get(k) for k in (
        "major_name", "major_code", "parent_major", "program_name", "candidate_majors", "candidate_programs"
    )) or bool(re.search(r"\b\d{7}\b", body))
    if set(kinds) & {"admission_score", "admission_threshold"} and not has_entity:
        return []
    method_number = re.search(r"\bphuong thuc(?: xet tuyen)?(?: thu)?\s*(\d+)\b", body)
    if kinds == ("admission_method",) and not method_number and not any(
        x in body for x in ("hoc ba", "thpt", "dgnl", "danh gia nang luc", "h-sca", "trung cap")
    ):
        return []
    documents = list(documents)
    rows: list[tuple[int, str, str, str]] = []
    for index, document in enumerate(documents):
        metadata = document.metadata
        for kind in _document_kinds(document):
            rows.append((index, "kind", kind, str(metadata.get("chunk_id") or index)))
        for key in ("major_name", "major_code", "parent_major", "parent_major_code", "program_name", "method", "method_number"):
            if metadata.get(key) is not None:
                rows.append((index, key, _fold(metadata[key]), ""))
        try:
            programs = json.loads(str(metadata.get("program_names") or "[]"))
        except (ValueError, TypeError):
            programs = []
        if isinstance(programs, list):
            rows.extend((index, "program_name", _fold(name), "") for name in programs if isinstance(name, str))

    methods = filters.get("admission_method") or filters.get("candidate_methods")
    if not methods and set(kinds) & {"admission_score", "admission_threshold", "admission_method"}:
        body = _fold(query.partition("intent:")[0])
        methods = [method for method, pattern in (
            ("thpt", r"\b(?:theo|thi|phuong thuc)\s+(?:ket qua\s+)?(?:tot nghiep\s+)?thpt\b"),
            ("hoc_ba", r"\bhoc ba\b"),
            ("dgnl", r"\bdgnl\b|\bdanh gia nang luc(?! chuyen biet)\b"),
            ("h_sca", r"\bh[- ]?sca\b|\bdanh gia nang luc chuyen biet\b"),
        ) if re.search(pattern, body)]
    # A code in a direct retriever query is also an exact entity constraint.
    codes = re.findall(r"\b\d{7}\b", query.partition("intent:")[0])
    clauses = ["f.field = 'kind'", "f.value IN (" + ",".join("?" for _ in kinds) + ")"]
    params: list[object] = list(kinds)
    groups = (
        (("major_code", "parent_major_code"), filters.get("major_code") or codes),
        (("major_name", "parent_major"), filters.get("major_name") or filters.get("parent_major") or filters.get("candidate_majors")),
        (("program_name",), filters.get("program_name") or filters.get("candidate_programs")),
        (("method",), methods),
        (("method_number",), [method_number.group(1)] if method_number and kinds == ("admission_method",) else None),
    )
    for fields, values in groups:
        if not values:
            continue
        values = values if isinstance(values, (list, tuple, set)) else [values]
        normalized = [_fold(value) for value in values if value]
        if not normalized:
            continue
        clauses.append(
            "EXISTS (SELECT 1 FROM facts e WHERE e.doc = f.doc AND e.field IN ("
            + ",".join("?" for _ in fields) + ") AND e.value IN ("
            + ",".join("?" for _ in normalized) + "))"
        )
        params.extend(fields)
        params.extend(normalized)
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE facts (doc INTEGER, field TEXT, value TEXT, identity TEXT)")
        connection.executemany("INSERT INTO facts VALUES (?, ?, ?, ?)", rows)
        connection.execute("CREATE INDEX fact_fields ON facts(field, value, doc)")
        matches = connection.execute(
            "SELECT DISTINCT f.doc, f.identity FROM facts f WHERE " + " AND ".join(clauses)
            + " ORDER BY f.identity, f.doc", params,
        ).fetchall()
        return [documents[index] for index, _ in matches]
    finally:
        connection.close()
