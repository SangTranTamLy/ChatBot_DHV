"""Run the Task B 2026 regression queries against the rebuilt ChromaDB."""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Callable

from langchain_chroma import Chroma

from src.config.settings import settings

from .chroma_lifecycle import close_chroma_store
from .embeddings import (
    create_embeddings,
    resolve_embedding_config,
    validate_embedding_metadata,
)


LOGGER = logging.getLogger(__name__)
_SPACE_RE = re.compile(r"\s+")
_CODE_RE = re.compile(r"\b\d{7}\b")


def _compact(documents: list[Any]) -> str:
    return _SPACE_RE.sub(
        " ",
        " ".join(document.page_content for document in documents),
    ).strip().lower()


def _category_documents(documents: list[Any], category: str) -> list[Any]:
    return [document for document in documents if document.metadata.get("category") == category]


def _record_values(
    documents: list[Any],
    *,
    category: str,
    record_type: str,
    major_name: str | None = None,
    generic_only: bool = False,
) -> dict[str, str]:
    normalized_major = major_name.casefold() if major_name else None
    return {
        str(document.metadata.get("method") or ""): str(
            document.metadata.get("raw_value") or document.metadata.get("value") or ""
        )
        for document in documents
        if document.metadata.get("category") == category
        and document.metadata.get("record_type") == record_type
        and (
            normalized_major is None
            or str(document.metadata.get("major_name") or "").strip().casefold()
            == normalized_major
        )
        and (
            not generic_only
            or not str(document.metadata.get("major_name") or "").strip()
        )
    }


def _require(query: str, documents: list[Any], predicate: Callable[[list[Any], str], bool], detail: str) -> None:
    if not documents:
        raise AssertionError(f"no result for query: {query}")
    text = _compact(documents)
    if not predicate(documents, text):
        raise AssertionError(f"{query}: {detail}")


def _check_industry_count(documents: list[Any], text: str) -> bool:
    codes = set(_CODE_RE.findall(" ".join(document.page_content for document in documents)))
    return len(codes) == 20


def _check_cntt_code(documents: list[Any], text: str) -> bool:
    return "7480201" in text and "công nghệ thông tin" in text


def _check_cntt_programs(documents: list[Any], text: str) -> bool:
    programs = (
        "công nghệ phần mềm",
        "lập trình ai",
        "an ninh mạng và hệ thống",
        "truyền thông đa phương tiện",
        "phân tích dữ liệu lớn",
    )
    return all(program in text for program in programs)


def _check_ai_code(documents: list[Any], text: str) -> bool:
    return "7480107" in text and "trí tuệ nhân tạo" in text


def _check_cntt_threshold(documents: list[Any], text: str) -> bool:
    values = _record_values(
        documents,
        category="nguong_dau_vao",
        record_type="application_threshold",
        generic_only=True,
    )
    return values.get("thpt") in {"15", "15.0", "15,00"} and values.get("dgnl") == "600"


def _check_law_threshold(documents: list[Any], text: str) -> bool:
    # Structured JSON keeps the method-specific 18-point Law thresholds as
    # semantic records; do not inspect the old Markdown table formatting.
    law_rows = {
        str(document.metadata.get("major_name") or "").strip().casefold(): document
        for document in documents
        if str(document.metadata.get("record_type") or "") == "application_threshold"
        and str(document.metadata.get("method") or "") == "thpt"
        and str(document.metadata.get("major_name") or "").strip().casefold()
        in {"luật", "luật kinh tế"}
    }
    if set(law_rows) != {"luật", "luật kinh tế"}:
        return False
    for document in law_rows.values():
        metadata = document.metadata
        if str(metadata.get("raw_value") or metadata.get("value") or "") != "18":
            return False
    return True


def _check_admission_score(documents: list[Any], text: str) -> bool:
    values = _record_values(
        documents,
        category="diem_trung_tuyen",
        record_type="admission_score",
        major_name="Luật",
    )
    return values == {"thpt": "20", "hoc_ba": "20(*)", "dgnl": "762"}


def _check_psychology_threshold(documents: list[Any], text: str) -> bool:
    values = _record_values(
        documents,
        category="nguong_dau_vao",
        record_type="application_threshold",
        generic_only=True,
    )
    return values.get("thpt") in {"15", "15.0", "15,00"}


def _check_psychology_admission(documents: list[Any], text: str) -> bool:
    score_documents = _category_documents(documents, "diem_trung_tuyen")
    return any(
        re.search(
            r"7310401\s+Tâm lý học\s+20\s+22,5\s+762",
            document.page_content,
            flags=re.IGNORECASE,
        )
        for document in score_documents
    )


def _check_tuition(documents: list[Any], text: str) -> bool:
    tuition = _category_documents(documents, "hoc_phi")
    return any(
        all(marker in document.page_content for marker in ("12.500.000", "14.250.000", "250.000"))
        and "nếu có" in document.page_content.casefold()
        for document in tuition
    )


def _check_supplementary_deadline(documents: list[Any], text: str) -> bool:
    supplementary = _category_documents(documents, "xet_tuyen_bo_sung")
    return any(
        document.metadata.get("record_type") == "deadline"
        and re.search(r"\b21/0?8/2026\b", document.page_content)
        for document in supplementary
    )


def _check_recommendation(documents: list[Any], text: str) -> bool:
    targets = ("công nghệ thông tin", "truyền thông đa phương tiện", "marketing")
    return bool(documents) and any(target in text for target in targets)


def _check_school_info(documents: list[Any], text: str) -> bool:
    school = _category_documents(documents, "thong_tin_truong")
    return bool(school) and "thành lập" in text and "1995" in text


REGRESSION_CASES: tuple[tuple[str, Callable[[list[Any], str], bool], str], ...] = (
    ("DHV năm 2026 có bao nhiêu ngành?", _check_industry_count, "must retrieve 20 distinct program codes"),
    ("CNTT mã ngành bao nhiêu?", _check_cntt_code, "must retrieve code 7480201"),
    ("CNTT có chương trình gì?", _check_cntt_programs, "must retrieve all five CNTT programs"),
    ("Trí tuệ nhân tạo mã ngành?", _check_ai_code, "must retrieve code 7480107"),
    (
        "Điểm sàn CNTT?",
        _check_cntt_threshold,
        "must retrieve the general THPT 15 and ĐGNL 600 threshold records",
    ),
    (
        "Điểm sàn Luật ngày 04/07/2026?",
        _check_law_threshold,
        "must retrieve both Law-specific 18-point THPT thresholds",
    ),
    (
        "Điểm trúng tuyển Luật 2026?",
        _check_admission_score,
        "must retrieve THPT 20, Học bạ 20(*), and ĐGNL 762",
    ),
    (
        "Tâm lý học điểm sàn?",
        _check_psychology_threshold,
        "must retrieve the general 15-point THPT floor without borrowing Law's 18",
    ),
    (
        "Tâm lý học điểm trúng tuyển?",
        _check_psychology_admission,
        "must retrieve the Psychology row 20/22.5/762 from the score table",
    ),
    (
        "Học phí HKI?",
        _check_tuition,
        "must retrieve tuition, the 14.25M base total, and the optional 250K fee",
    ),
    (
        "Hạn xét tuyển bổ sung?",
        _check_supplementary_deadline,
        "must retrieve the verified 21/8/2026 deadline",
    ),
    (
        "Tôi 19 điểm, thích edit video, nên chọn ngành nào DHV 2026?",
        _check_recommendation,
        "must retrieve an official CNTT/media/marketing result",
    ),
    ("Trường thành lập khi nào?", _check_school_info, "must retrieve verified school-information evidence"),
)


def run_regression_tests(
    *,
    backend: str,
    embedding_model: str | None,
    ollama_base_url: str,
    persist_directory: str,
    collection_name: str,
    top_k: int = 96,
) -> list[dict[str, object]]:
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    embedding_config = resolve_embedding_config(
        backend=backend,
        model=embedding_model,
        ollama_base_url=ollama_base_url,
    )
    embedding_function = create_embeddings(
        backend=embedding_config.backend,
        model=embedding_config.model,
        ollama_base_url=embedding_config.base_url,
    )
    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=embedding_function,
    )
    try:
        if vector_store._collection.count() <= 0:
            raise RuntimeError("ChromaDB collection is empty")
        validate_embedding_metadata(vector_store._collection.metadata, embedding_config)
        query_vector = embedding_function.embed_query(REGRESSION_CASES[0][0])
        validate_embedding_metadata(
            vector_store._collection.metadata,
            embedding_config,
            query_dimension=len(query_vector),
        )

        results: list[dict[str, object]] = []
        for query, predicate, detail in REGRESSION_CASES:
            query_vector = embedding_function.embed_query(query)
            documents = vector_store.similarity_search_by_vector(query_vector, k=top_k)
            _require(query, documents, predicate, detail)
            results.append(
                {
                    "query": query,
                    "result_count": len(documents),
                    "categories": sorted({document.metadata.get("category") for document in documents}),
                }
            )
            print(json.dumps(results[-1], ensure_ascii=False))
        print(f"REGRESSION_PASS ({len(results)} cases)")
        return results
    finally:
        close_chroma_store(vector_store)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-backend", default=settings.embedding_backend)
    parser.add_argument("--embedding-model", default=None)
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--persist-dir", default=str(settings.chroma_persist_dir))
    parser.add_argument("--collection", default=settings.chroma_collection)
    parser.add_argument("--top-k", type=int, default=96)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        run_regression_tests(
            backend=args.embedding_backend,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_base_url,
            persist_directory=args.persist_dir,
            collection_name=args.collection,
            top_k=args.top_k,
        )
    except Exception as exc:
        LOGGER.error("rebuild regression failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["REGRESSION_CASES", "main", "run_regression_tests"]
