"""Trình truy xuất (retriever) Chroma dành cho cơ sở tri thức tuyển sinh DHV đã xác thực."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from math import log
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config.settings import Settings, settings
from src.ingestion.chroma_lifecycle import close_chroma_store
from src.ingestion.embeddings import create_embeddings


class RetrieverError(RuntimeError):
    """Lỗi cơ sở khi quá trình truy xuất từ vector-store thất bại."""


class VectorDatabaseError(RetrieverError):
    """Cơ sở dữ liệu hoặc collection Chroma đã cấu hình không thể đọc được."""


class RetrieverEmbeddingError(RetrieverError):
    """Service embedding đã cấu hình bị lỗi khi mã hóa một truy vấn."""


_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MAJOR_CODE_RE = re.compile(r"\b\d{7}\b")
_TOKEN_RE = re.compile(r"\d{7}|[a-zA-ZÀ-ỹĐđ]+", re.UNICODE)
_RETRIEVAL_STOPWORDS = frozenset(
    {"va", "la", "cua", "cho", "toi", "ban", "dhv", "nam", "co", "ve", "diem"}
)
_RRF_K = 60


@dataclass(frozen=True)
class RetrievalAudit:
    """Thông tin kiểm toán (audit) có thể tuần tự hóa dùng để đánh giá độc lập phần truy xuất."""

    query: str
    normalized_query: str
    metadata_filter: dict[str, object]
    top_k: int
    hits: tuple[dict[str, object], ...]
    candidates: tuple[dict[str, object], ...] = ()
    filtered_candidates: tuple[dict[str, object], ...] = ()
    fusion_method: str = "bm25+dense+rrf"
    rrf_k: int = _RRF_K

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "metadata_filter": self.metadata_filter,
            "top_k": self.top_k,
            "hits": [dict(hit) for hit in self.hits],
            "candidates": [dict(candidate) for candidate in self.candidates],
            "filtered_candidates": [
                dict(candidate) for candidate in self.filtered_candidates
            ],
            "fusion_method": self.fusion_method,
            "rrf_k": self.rrf_k,
        }


@dataclass(frozen=True)
class RetrievalResult:
    """Các tài liệu kèm theo dấu vết kiểm toán (audit trace); chức năng sinh văn bản cố tình bị loại bỏ."""

    documents: tuple[Document, ...]
    audit: RetrievalAudit


def _normalise_tokens(value: str) -> set[str]:
    folded = _normalize(value)
    return {
        token
        for token in _TOKEN_RE.findall(folded)
        if token not in _RETRIEVAL_STOPWORDS and (len(token) >= 3 or token.isdigit())
    }


def _normalise_token_list(value: str) -> list[str]:
    folded = _normalize(value)
    return [
        token
        for token in _TOKEN_RE.findall(folded)
        if token not in _RETRIEVAL_STOPWORDS and (len(token) >= 3 or token.isdigit())
    ]


def _document_identity(document: Document) -> str:
    metadata = document.metadata or {}
    return str(metadata.get("chunk_id") or metadata.get("source_file") or id(document))


def _keyword_score(query: str, document: Document) -> float:
    query_tokens = _normalise_tokens(query)
    content = _normalize(document.page_content)
    content_tokens = _normalise_tokens(document.page_content)
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & content_tokens)
    score = float(overlap)
    if _normalize(query).strip() and _normalize(query).strip() in content:
        score += 5.0
    for token in query_tokens:
        if len(token) >= 7 and token in content:
            score += 1.5
    return score


def _bm25_scores(query: str, documents: Iterable[Document]) -> dict[str, float]:
    """Tính BM25 trên candidate pool hiện có, không ghi thêm dữ liệu vào Chroma."""

    materialized = list(documents)
    if not materialized:
        return {}
    query_terms = set(_normalise_token_list(query))
    if not query_terms:
        return {_document_identity(document): 0.0 for document in materialized}

    tokenized = {
        _document_identity(document): _normalise_token_list(document.page_content)
        for document in materialized
    }
    document_count = len(materialized)
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized.values():
        document_frequency.update(set(tokens))
    average_length = sum(len(tokens) for tokens in tokenized.values()) / document_count
    average_length = max(average_length, 1.0)
    k1 = 1.2
    b = 0.75
    scores: dict[str, float] = {}
    for document in materialized:
        identity = _document_identity(document)
        tokens = tokenized[identity]
        term_frequency = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query_terms:
            frequency = term_frequency.get(term, 0)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse_frequency = log(
                1.0 + (document_count - df + 0.5) / (df + 0.5)
            )
            normalization = k1 * (1.0 - b + b * length / average_length)
            score += inverse_frequency * (
                frequency * (k1 + 1.0) / (frequency + normalization)
            )
        # Keep exact identifiers and phrases useful even when the term IDF is
        # small in a compact corpus.
        normalized_query = _normalize(query).strip()
        if normalized_query and normalized_query in _normalize(document.page_content):
            score += 1.0
        scores[identity] = score
    return scores


def requested_year(question: str) -> int | None:
    """Trả về số năm gồm 4 chữ số được nhắc đến rõ ràng, nếu có."""

    match = _YEAR_RE.search(question or "")
    return int(match.group(1)) if match else None


def topic_category(question: str) -> str | None:
    """Suy luận danh mục corpus bao quát từ các từ khóa chủ đề, không sử dụng dữ kiện thực tế."""

    normalized = _normalize(question)
    if (
        "thong tin truong" in normalized
        or "thong tin ve truong" in normalized
        or "thong tin ve dhv" in normalized
        or "gioi thieu truong" in normalized
        or "gioi thieu ve dhv" in normalized
        or "dhv la truong" in normalized
        or "truong dhv la" in normalized
        or "truong dai hoc hung vuong la" in normalized
        or "truong thanh lap" in normalized
        or "thanh lap khi nao" in normalized
        or "thanh lap nam" in normalized
    ):
        return "thong_tin_truong"
    if (
        ("website" in normalized or "trang web" in normalized or re.search(r"\bweb\b", normalized))
        and ("dhv" in normalized or "truong" in normalized or "tuyen sinh" in normalized)
    ):
        return "thong_tin_truong"
    if "xac nhan nhap hoc" in normalized:
        return "lich_tuyen_sinh"
    if "hoc phi" in normalized:
        return "hoc_phi"
    if "hoc bong" in normalized:
        return "hoc_bong"
    if (
        "xet tuyen bo sung" in normalized
        or "tuyen sinh bo sung" in normalized
        or "xet bo sung" in normalized
    ):
        return "xet_tuyen_bo_sung"
    if "ho so" in normalized or "giay to" in normalized:
        return "ho_so"
    if "thu tuc nhap hoc" in normalized:
        return "ho_so"
    if "nhap hoc" in normalized:
        return "nhap_hoc"
    if "lich tuyen sinh" in normalized or "lich xet tuyen" in normalized or "han xet tuyen" in normalized:
        return "lich_tuyen_sinh"
    if "diem trung tuyen" in normalized or "diem chuan" in normalized:
        return "diem_trung_tuyen"
    if (
        "diem san" in normalized
        or "nguong dau vao" in normalized
        or "nguong dam bao chat luong" in normalized
    ):
        return "nguong_dau_vao"
    # Các dấu hiệu chủ đề cụ thể phải được ưu tiên hơn cách nhắc chung chung về "ngành" hoặc
    # "chương trình", nếu không thì ví dụ như "phương thức xét tuyển của ngành CNTT"
    # sẽ bị gửi vào danh mục chương trình.
    if (
        "phuong thuc" in normalized
        or "hinh thuc xet tuyen" in normalized
        or "to hop xet tuyen" in normalized
        or "to hop mon" in normalized
        or "to hop" in normalized
    ):
        return "phuong_thuc_xet_tuyen"
    if (
        "cach tinh diem" in normalized
        or "cong thuc diem" in normalized
        or "quy doi diem" in normalized
        or "tinh diem the nao" in normalized
        or "tinh diem ra sao" in normalized
        or "tinh nhu the nao" in normalized
    ):
        return "cach_tinh_diem"
    if (
        ("hoc ba" in normalized and re.search(r"\b(?:bao nhieu|may|lay)\b", normalized))
        or "diem nhan ho so" in normalized
        or "diem dau vao" in normalized
    ):
        return "nguong_dau_vao"
    if (
        ("dang ky" in normalized or "cong dang ky" in normalized or "cong thong tin xet tuyen" in normalized or "nop nguyen vong" in normalized or "nguyen vong" in normalized)
        and "nhap hoc" not in normalized
        and "lich " not in normalized
        and "han xet tuyen" not in normalized
    ):
        return "dang_ky_xet_tuyen"
    if (
        "co so" in normalized
        or "hotline" in normalized
        or "lien he" in normalized
        or "dia chi" in normalized
        or "so dien thoai" in normalized
        or "dien thoai" in normalized
        or "email" in normalized
    ):
        return "co_so_lien_he"
    if "nganh" in normalized or "chuong trinh" in normalized:
        return "nganh_dao_tao"
    return None


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return folded.lower().replace("đ", "d")


def _categories_from_question(question: str) -> tuple[str, ...]:
    category = topic_category(question)
    return (category,) if category else ()


def _metadata_filter(target_year: int, categories: tuple[str, ...]) -> dict[str, object]:
    if not categories:
        return {"year": target_year}
    if len(categories) == 1:
        return {"$and": [{"year": target_year}, {"category": categories[0]}]}
    return {
        "$and": [
            {"year": target_year},
            {"$or": [{"category": category} for category in categories]},
        ]
    }


def _official_dhv_url(value: object) -> bool:
    url = str(value or "").strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return bool(
        parsed.scheme in {"http", "https"}
        and not parsed.username
        and (
            hostname in {"dhv.edu.vn", "www.dhv.edu.vn"}
            or hostname.endswith(".dhv.edu.vn")
        )
    )


def _filter_reason(
    document: Document,
    target_year: int,
    categories: tuple[str, ...],
) -> str | None:
    metadata = document.metadata or {}
    if metadata.get("status") != "verified":
        return "status_not_verified"
    try:
        year_matches = int(metadata.get("year")) == target_year
    except (TypeError, ValueError):
        year_matches = False
    if not year_matches:
        return "year_mismatch"
    if str(metadata.get("school_code") or "").upper() != "DHV":
        return "target_institution_mismatch"
    if not _official_dhv_url(metadata.get("source_url")):
        return "source_not_official_dhv"
    if categories and str(metadata.get("category") or "") not in categories:
        return "category_not_requested"
    if not str(document.page_content or "").strip():
        return "empty_content"
    return None


def _entity_terms(entity_filters: Mapping[str, object] | None) -> tuple[str, ...]:
    if not entity_filters:
        return ()
    values: list[str] = []
    for key in (
        "major_name",
        "major_code",
        "program_name",
        "parent_major",
        "candidate_majors",
        "candidate_programs",
    ):
        value = entity_filters.get(key)
        items = value if isinstance(value, (list, tuple, set)) else (value,)
        for item in items:
            folded = _normalize(str(item or "")).strip()
            if folded and folded not in values:
                values.append(folded)
    return tuple(values)


def _entity_matches(document: Document, entity_filters: Mapping[str, object] | None) -> bool:
    terms = _entity_terms(entity_filters)
    if not terms:
        return True
    content = _normalize(document.page_content)
    return any(term in content for term in terms)


def _inferred_entity_filters(query: str) -> dict[str, str]:
    """Giữ truy vấn mã ngành trực tiếp khỏi bị prose mô tả che khuất.

    Adapter cũ có thể không truyền ``entity_filters``. Trong trường hợp đó,
    chỉ suy ra mã ngành có định dạng cố định; không suy đoán tên ngành hay
    tạo fact từ ngôn ngữ tự nhiên.
    """

    match = _MAJOR_CODE_RE.search(query or "")
    return {"major_code": match.group(0)} if match else {}


def _catalog_list_query(query: str, categories: tuple[str, ...], entity_filters: Mapping[str, object]) -> bool:
    """Nhận diện truy vấn liệt kê để ưu tiên nguồn catalog có cấu trúc.

    Đây là một policy về dạng truy vấn, không phụ thuộc tên ngành. Tài liệu
    ``description`` vẫn được truy xuất cho câu hỏi mô tả/tư vấn; chỉ các yêu
    cầu liệt kê thuần catalog mới bỏ prose khỏi candidate pool.
    """

    if categories != ("nganh_dao_tao",) or entity_filters:
        return False
    normalized = _normalize(query)
    return any(
        marker in normalized
        for marker in (
            "danh sach",
            "liet ke",
            "bao nhieu nganh",
            "tat ca cac nganh",
            "co nhung nganh",
            "chuong trinh nao",
            "co may chuong trinh",
        )
    )


def _rank_hybrid_candidates(
    query: str,
    candidates: Iterable[Document],
    vector_documents: list[Document],
    vector_scores: dict[str, float],
    target_year: int,
    top_k: int,
    categories: Iterable[str] = (),
    entity_filters: Mapping[str, object] | None = None,
) -> list[Document]:
    ranked, _ = _rank_hybrid_candidates_with_audit(
        query,
        candidates,
        vector_documents,
        vector_scores,
        target_year,
        top_k,
        categories=categories,
        entity_filters=entity_filters,
    )
    return ranked


def _rank_hybrid_candidates_with_audit(
    query: str,
    candidates: Iterable[Document],
    vector_documents: list[Document],
    vector_scores: dict[str, float],
    target_year: int,
    top_k: int,
    *,
    categories: Iterable[str] = (),
    entity_filters: Mapping[str, object] | None = None,
) -> tuple[list[Document], dict[str, dict[str, object]]]:
    category_values = tuple(str(category) for category in categories if str(category))
    unique: dict[str, Document] = {}
    for document in candidates:
        if _filter_reason(document, target_year, category_values) is not None:
            continue
        if not _entity_matches(document, entity_filters):
            continue
        unique.setdefault(_document_identity(document), document)

    dense_rank = {
        _document_identity(document): rank
        for rank, document in enumerate(vector_documents, start=1)
        if _document_identity(document) in unique
    }
    bm25_scores = _bm25_scores(query, unique.values())
    bm25_ranked = [
        identity
        for identity in sorted(
            unique,
            key=lambda identity: (-bm25_scores.get(identity, 0.0), identity),
        )
        if bm25_scores.get(identity, 0.0) > 0.0
    ]
    bm25_rank = {identity: rank for rank, identity in enumerate(bm25_ranked, start=1)}
    rrf_scores: dict[str, float] = {identity: 0.0 for identity in unique}
    for rank, identity in enumerate(bm25_ranked, start=1):
        rrf_scores[identity] += 1.0 / (_RRF_K + rank)
    for rank, document in enumerate(vector_documents, start=1):
        identity = _document_identity(document)
        if identity in rrf_scores:
            rrf_scores[identity] += 1.0 / (_RRF_K + rank)

    ranking = sorted(
        unique,
        key=lambda identity: (
            -rrf_scores[identity],
            bm25_rank.get(identity, 10**6),
            dense_rank.get(identity, 10**6),
            vector_scores.get(identity, 10**6),
            identity,
        ),
    )
    fusion = {
        identity: {
            "bm25_rank": bm25_rank.get(identity),
            "bm25_score": bm25_scores.get(identity, 0.0),
            "dense_rank": dense_rank.get(identity),
            "dense_score": vector_scores.get(identity),
            "rrf_score": rrf_scores[identity],
        }
        for identity in unique
    }
    return [unique[identity] for identity in ranking[:top_k]], fusion


def _audit_hit(
    document: Document,
    rank: int,
    query: str,
    vector_documents: list[Document],
    fusion: Mapping[str, object] | None = None,
) -> dict[str, object]:
    metadata = document.metadata or {}
    vector_rank = next(
        (
            position
            for position, candidate in enumerate(vector_documents, start=1)
            if _document_identity(candidate) == _document_identity(document)
        ),
        None,
    )
    return {
        "rank": rank,
        "score": _keyword_score(query, document),
        "keyword_score": _keyword_score(query, document),
        "vector_rank": vector_rank,
        **dict(fusion or {}),
        "category": metadata.get("category"),
        "year": metadata.get("year"),
        "status": metadata.get("status"),
        "title": metadata.get("title"),
        "source_file": metadata.get("source_file"),
        "chunk_id": metadata.get("chunk_id"),
        "content_preview": document.page_content[:220].replace("\n", " | "),
    }


class DHVRetriever:
    """Trình truy xuất Chroma kết hợp (hybrid) tải trễ, sử dụng hợp đồng embedding của Task B.

    Chroma vẫn là nguồn dữ liệu gốc (source of truth). Một bước duyệt từ khóa nhỏ trong quá trình
    chạy (runtime) trên cùng collection chỉ được dùng để cải thiện việc khớp chính xác thực thể/mã số;
    nó không ghi vào collection hay làm thay đổi embedding.
    """

    def __init__(
        self,
        *,
        settings_obj: Settings = settings,
        store_factory: Callable[..., Any] = Chroma,
        embedding_factory: Callable[..., Any] = create_embeddings,
    ) -> None:
        self.settings = settings_obj
        self._store_factory = store_factory
        self._embedding_factory = embedding_factory

    def retrieve(self, question: str) -> list[Document]:
        """Truy xuất các tài liệu đã xác thực cho năm cơ sở tri thức được cấu hình.

        Một yêu cầu rõ ràng về năm khác sẽ được coi là không có dữ liệu. Điều này rất
        quan trọng vì nếu không, truy xuất vector (dense retrieval) sẽ trả về các đoạn (chunks)
        năm 2026 gần đúng cho một câu hỏi về năm 2027.
        """

        return list(self.retrieve_with_audit(question).documents)

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: Iterable[str] | None = None,
        retrieval_query: str | None = None,
        entity_filters: Mapping[str, object] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Truy xuất top-k chunk đã xác thực và trả về bản kiểm toán không kèm phần sinh văn bản."""

        query = (retrieval_query or question or "").strip()
        original_query = (question or "").strip()
        effective_top_k = max(1, int(top_k or self.settings.retriever_top_k))
        effective_entity_filters = (
            dict(entity_filters)
            if entity_filters is not None
            else _inferred_entity_filters(query)
        )
        empty_audit = RetrievalAudit(
            query=original_query,
            normalized_query=_normalize(query),
            metadata_filter={"year": self.settings.target_year},
            top_k=effective_top_k,
            hits=(),
        )
        if not query:
            return RetrievalResult((), empty_audit)
        year = requested_year(original_query) or requested_year(query)
        if year is not None and year != self.settings.target_year:
            return RetrievalResult((), empty_audit)

        persist_directory = Path(self.settings.chroma_persist_dir)
        if not persist_directory.exists() or not persist_directory.is_dir():
            raise VectorDatabaseError(
                f"Chroma persist directory is missing: {persist_directory}"
            )

        try:
            embedding_function = self._embedding_factory(
                backend=self.settings.embedding_backend,
                ollama_model=self.settings.embedding_model,
                ollama_base_url=self.settings.ollama_base_url,
            )
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("query embedding backend could not be created") from exc

        try:
            vector_store = self._store_factory(
                collection_name=self.settings.chroma_collection,
                persist_directory=str(persist_directory),
                embedding_function=embedding_function,
            )
        except Exception as exc:
            raise VectorDatabaseError("ChromaDB could not be opened") from exc

        metadata_filter = _metadata_filter(
            self.settings.target_year,
            tuple(str(category) for category in categories if str(category))
            if categories is not None
            else _categories_from_question(original_query),
        )
        requested_categories = tuple(
            str(category)
            for category in (categories if categories is not None else _categories_from_question(original_query))
            if str(category)
        )
        candidates: list[Document] = []
        vector_documents: list[Document] = []
        vector_scores: dict[str, float] = {}
        fusion: dict[str, dict[str, object]] = {}
        try:
            count = vector_store._collection.count()
            if count <= 0:
                raise VectorDatabaseError("Chroma collection is empty")

            vector_documents, vector_scores = self._vector_search(
                vector_store,
                query,
                metadata_filter,
                effective_top_k,
            )
            candidates = self._collection_candidates(vector_store, metadata_filter)
            if not candidates:
                candidates = list(vector_documents)
            if _catalog_list_query(query, requested_categories, effective_entity_filters):
                candidates = [
                    candidate
                    for candidate in candidates
                    if str((candidate.metadata or {}).get("data_role") or "").strip().casefold()
                    != "description"
                ]
            documents, fusion = _rank_hybrid_candidates_with_audit(
                query,
                candidates,
                vector_documents,
                vector_scores,
                self.settings.target_year,
                effective_top_k,
                categories=requested_categories,
                entity_filters=effective_entity_filters,
            )
        except RetrieverEmbeddingError:
            raise
        except VectorDatabaseError:
            raise
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("Chroma similarity search failed") from exc
        finally:
            close_chroma_store(vector_store)

        candidate_audits: list[dict[str, object]] = []
        filtered_audits: list[dict[str, object]] = []
        selected_ids = {_document_identity(document) for document in documents}
        for position, candidate in enumerate(candidates, start=1):
            identity = _document_identity(candidate)
            reason = _filter_reason(candidate, self.settings.target_year, requested_categories)
            if reason is None and effective_entity_filters and not _entity_matches(candidate, effective_entity_filters):
                reason = "entity_not_in_document"
            item = {
                "candidate_rank": position,
                "chunk_id": (candidate.metadata or {}).get("chunk_id"),
                "category": (candidate.metadata or {}).get("category"),
                "year": (candidate.metadata or {}).get("year"),
                "status": (candidate.metadata or {}).get("status"),
                "selected": identity in selected_ids,
                "filter_reason": reason,
                "content_preview": candidate.page_content[:220].replace("\n", " | "),
            }
            if reason is None:
                item.update(fusion.get(identity, {}))
                candidate_audits.append(item)
            else:
                filtered_audits.append(item)
        hits = tuple(
            _audit_hit(document, rank, query, vector_documents, fusion.get(_document_identity(document)))
            for rank, document in enumerate(documents, start=1)
        )
        audit = RetrievalAudit(
            query=original_query,
            normalized_query=_normalize(query),
            metadata_filter=metadata_filter,
            top_k=effective_top_k,
            hits=hits,
            candidates=tuple(candidate_audits),
            filtered_candidates=tuple(filtered_audits),
        )
        return RetrievalResult(tuple(documents), audit)

    def _vector_search(
        self,
        vector_store: Any,
        query: str,
        metadata_filter: dict[str, object],
        top_k: int,
    ) -> tuple[list[Document], dict[str, float]]:
        try:
            if hasattr(vector_store, "similarity_search_with_score"):
                pairs = vector_store.similarity_search_with_score(
                    query,
                    k=top_k,
                    filter=metadata_filter,
                )
                documents = [pair[0] for pair in pairs]
                scores = {
                    _document_identity(document): float(pair[1])
                    for document, pair in zip(documents, pairs)
                }
                return documents, scores
            documents = vector_store.similarity_search(
                query,
                k=top_k,
                filter=metadata_filter,
            )
            return list(documents), {}
        except Exception as exc:
            if self.settings.embedding_backend == "ollama":
                raise RetrieverEmbeddingError("query embedding service failed") from exc
            raise VectorDatabaseError("Chroma similarity search failed") from exc

    @staticmethod
    def _collection_candidates(
        vector_store: Any,
        metadata_filter: dict[str, object],
    ) -> list[Document]:
        """Đọc collection hiện có để xếp hạng lại bằng từ khóa, tuyệt đối không thay đổi collection."""

        getter = getattr(vector_store, "get", None)
        if not callable(getter):
            return []
        try:
            payload = getter(
                where=metadata_filter,
                include=["documents", "metadatas"],
            )
        except Exception:
            return []
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        return [
            Document(page_content=str(content or ""), metadata=dict(metadata or {}))
            for content, metadata in zip(documents, metadatas)
            if content
        ]


def _is_verified_dhv_document(document: Document, target_year: int) -> bool:
    return _filter_reason(document, target_year, ()) is None


def retrieve_documents(question: str) -> list[Document]:
    """Hàm tiện ích cho các nơi gọi sử dụng cài đặt mặc định."""

    return DHVRetriever().retrieve(question)


__all__ = [
    "DHVRetriever",
    "RetrievalAudit",
    "RetrieverEmbeddingError",
    "RetrieverError",
    "RetrievalResult",
    "VectorDatabaseError",
    "requested_year",
    "topic_category",
    "retrieve_documents",
]
