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
from .embeddings import create_embeddings


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
    return "công nghệ thông tin" in text and all(value in text for value in ("15", "18", "600"))


def _check_law_threshold(documents: list[Any], text: str) -> bool:
    # Structured JSON keeps one major per semantic record; do not require the
    # two Law rows to share a legacy Markdown table/chunk.
    law_rows = {
        str(document.metadata.get("major_name") or "").strip(): document.page_content
        for document in documents
        if str(document.metadata.get("record_type") or "") == "major"
        and str(document.metadata.get("major_name") or "").strip()
        in {"Luật", "Luật Kinh tế"}
    }
    if set(law_rows) != {"Luật", "Luật Kinh tế"}:
        return False
    for row in law_rows.values():
        normalized = _SPACE_RE.sub(" ", row).lower()
        if normalized.count(": -") < 3:
            return False
        if any(f": {value}" in normalized for value in ("15", "18", "600")):
            return False
    return True


def _check_admission_score(documents: list[Any], text: str) -> bool:
    return bool(_category_documents(documents, "diem_trung_tuyen")) and "luật: 20,0" in text


def _check_psychology_threshold(documents: list[Any], text: str) -> bool:
    return "tâm lý học" in text and all(value in text for value in ("15", "18", "600"))


def _check_psychology_admission(documents: list[Any], text: str) -> bool:
    return bool(_category_documents(documents, "diem_trung_tuyen")) and "tâm lý học: 20,0" in text


def _check_tuition(documents: list[Any], text: str) -> bool:
    tuition = _category_documents(documents, "hoc_phi")
    return bool(tuition) and "12.500.000" in text and "14.500.000" in text


def _check_supplementary_deadline(documents: list[Any], text: str) -> bool:
    supplementary = _category_documents(documents, "xet_tuyen_bo_sung")
    return bool(supplementary) and "21/08/2026" in text


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
    ("Điểm sàn CNTT?", _check_cntt_threshold, "must retrieve 15/18/600"),
    ("Điểm sàn Luật ngày 04/07/2026?", _check_law_threshold, "must preserve '-' for both Law rows"),
    ("Điểm trúng tuyển Luật 2026?", _check_admission_score, "must retrieve 20,0 from admission-score source"),
    ("Tâm lý học điểm sàn?", _check_psychology_threshold, "must retrieve 15/18/600"),
    ("Tâm lý học điểm trúng tuyển?", _check_psychology_admission, "must retrieve 20,0 from admission-score source"),
    ("Học phí HKI?", _check_tuition, "must retrieve 12.500.000 and total 14.500.000"),
    ("Hạn xét tuyển bổ sung?", _check_supplementary_deadline, "must retrieve 21/08/2026"),
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
    embedding_model: str,
    ollama_base_url: str,
    persist_directory: str,
    collection_name: str,
    top_k: int = 25,
) -> list[dict[str, object]]:
    embedding_function = create_embeddings(
        backend=backend,
        ollama_model=embedding_model,
        ollama_base_url=ollama_base_url,
    )
    vector_store = Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=embedding_function,
    )
    try:
        if vector_store._collection.count() <= 0:
            raise RuntimeError("ChromaDB collection is empty")

        results: list[dict[str, object]] = []
        for query, predicate, detail in REGRESSION_CASES:
            documents = vector_store.similarity_search(query, k=top_k)
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
    parser.add_argument("--embedding-model", default=settings.embedding_model)
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--persist-dir", default=str(settings.chroma_persist_dir))
    parser.add_argument("--collection", default=settings.chroma_collection)
    parser.add_argument("--top-k", type=int, default=25)
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
