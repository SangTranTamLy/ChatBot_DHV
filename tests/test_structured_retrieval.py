"""Regression coverage for the structured third retrieval stream."""

import json
import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from langchain_core.documents import Document

from src.config.settings import settings
from src.retrieval.retriever import DHVRetriever, _rank_hybrid_candidates_with_audit
from src.retrieval.structured_lookup import lookup_structured_documents


def record(identity, kind, text, **metadata):
    return Document(page_content=text, metadata={
        "chunk_id": identity, "record_type": kind, "category": "diem_trung_tuyen",
        "year": 2026, "status": "verified", "school_code": "DHV",
        "source_url": "https://dhv.edu.vn/test-structured", "page": 1,
        "source_file": "data/raw/test.pdf", **metadata,
    })


class StructuredLookupTests(unittest.TestCase):
    def test_exact_code_and_method_win_over_repeated_keywords(self):
        wanted = record("wanted", "admission_score", "Ngành 7480201: kết quả theo phương thức công bố.",
                        major_code="7480201", major_name="Công nghệ thông tin", method="thpt", value=15)
        unrelated = record("prose", "page_text", "Điểm chuẩn 7480201 THPT " * 20)
        wrong_method = record("wrong-method", "admission_score", "Điểm chuẩn học bạ 7480201.",
                              major_code="7480201", method="hoc_ba", value=18)
        ranked, audit = _rank_hybrid_candidates_with_audit(
            "Điểm chuẩn 7480201 THPT", [unrelated, wrong_method, wanted], [unrelated], {},
            2026, 1, categories=("diem_trung_tuyen",), entity_filters={"admission_method": "thpt"},
        )
        self.assertEqual(ranked, [wanted])
        self.assertEqual(audit["wanted"]["structured_rank"], 1)
        self.assertIsNone(audit["wrong-method"]["structured_rank"])
        self.assertIsNone(audit["prose"]["structured_rank"])
        self.assertEqual(ranked[0].metadata["source_file"], "data/raw/test.pdf")

    def test_program_is_matched_against_json_array_not_prose(self):
        wanted = record("wanted", "major", "Danh mục ngành.", major_code="7480201",
                        program_names=json.dumps(["An ninh mạng và hệ thống"], ensure_ascii=False))
        prose = record("prose", "major", "An ninh mạng và hệ thống", major_code="7340101")
        result = lookup_structured_documents("Mã ngành của chương trình?", [prose, wanted],
                                             {"program_name": "An ninh mạng và hệ thống"})
        self.assertEqual(result, [wanted])

    def test_explicit_method_in_question_is_respected_without_router_annotation(self):
        records = [record(method, "admission_score", "Điểm chuẩn 7480201.",
                          major_code="7480201", method=method) for method in ("hoc_ba", "thpt", "dgnl")]
        self.assertEqual(lookup_structured_documents("Điểm chuẩn 7480201 theo THPT?", records), [records[1]])
        self.assertEqual(lookup_structured_documents("Điểm chuẩn 7480201 theo học bạ THPT?", records), [records[0]])
        # Merely mentioning high school is not a request for the exam method.
        self.assertEqual(len(lookup_structured_documents("Điểm chuẩn cho học sinh THPT?", records)), 3)

    def test_enrollment_location_is_distinct_from_all_campuses_and_history(self):
        intake = record("intake", "page_text", "Địa điểm nhập học:\nCơ sở 1: Địa chỉ A\nCơ sở 2: Địa chỉ B",
                        category="ho_so")
        campuses = record("campuses", "page_text", "Các cơ sở của trường:\nCơ sở 1: Địa chỉ A\nCơ sở 2: Địa chỉ C",
                          category="thong_tin_truong")
        history = record("history", "page_text", "Ngày truyền thống tại cơ sở chính Địa chỉ C.",
                         category="thong_tin_truong")
        documents = [campuses, history, intake]
        self.assertEqual(lookup_structured_documents("Nộp hồ sơ nhập học ở cơ sở nào?", documents), [intake])
        self.assertEqual(lookup_structured_documents("Trường có những cơ sở nào?", documents), [campuses])

    def test_unsupported_queries_and_missing_metadata_keep_two_stream_behavior(self):
        prose = record("prose", "page_text", "Học phí theo thông báo.", category="hoc_phi")
        self.assertEqual(lookup_structured_documents("Học phí bao nhiêu?", [prose]), [])
        self.assertEqual(lookup_structured_documents("Giá trị cốt lõi của trường?", [prose]), [])
        ranked, audit = _rank_hybrid_candidates_with_audit(
            "Học phí", [prose], [prose], {}, 2026, 4, categories=("hoc_phi",),
        )
        self.assertEqual(ranked, [prose])
        self.assertAlmostEqual(audit["prose"]["rrf_score"], 2 / 61)

    def test_year_category_verification_and_entity_boundaries_are_preserved(self):
        wanted = record("wanted", "admission_score", "Điểm chuẩn CNTT 7480201.", major_code="7480201")
        invalid = [
            record("old", "admission_score", "Điểm chuẩn CNTT 7480201.", year=2024, major_code="7480201"),
            record("unverified", "admission_score", "Điểm chuẩn CNTT 7480201.", status="draft", major_code="7480201"),
            record("other-school", "admission_score", "Điểm chuẩn CNTT 7480201.", school_code="OTHER", major_code="7480201"),
            record("other-category", "admission_score", "Điểm chuẩn CNTT 7480201.", category="ho_so", major_code="7480201"),
            record("unofficial", "admission_score", "Điểm chuẩn CNTT 7480201.", source_url="https://example.com", major_code="7480201"),
            record("other-major", "admission_score", "Điểm chuẩn ngành khác.", major_code="7340101"),
        ]
        ranked, audit = _rank_hybrid_candidates_with_audit(
            "Điểm chuẩn 7480201", invalid + [wanted], invalid, {}, 2026, 4,
            categories=("diem_trung_tuyen",), entity_filters={"major_code": "7480201"},
        )
        self.assertEqual(ranked, [wanted])
        self.assertEqual(set(audit), {"wanted"})

    def test_sql_values_are_parameters_and_malformed_programs_are_ignored(self):
        document = record("record", "major", "Danh mục ngành.", major_code="7480201", program_names="not-json")
        self.assertEqual(lookup_structured_documents("Mã ngành?", [document],
                                                    {"major_code": "' OR 1=1 --"}), [])
        self.assertEqual(lookup_structured_documents("Mã ngành?", [document],
                                                    {"program_name": "An ninh mạng"}), [])

    def test_multiple_candidate_entities_return_each_matching_record_once(self):
        records = [record(str(i), "major", "Danh mục ngành.", major_name=name)
                   for i, name in enumerate(["Luật", "Marketing", "Kế toán"])]
        self.assertEqual(lookup_structured_documents("Mã ngành?", records,
                                                    {"candidate_majors": ["Luật", "Kế toán"]}),
                         [records[0], records[2]])

    def test_existing_tuition_document_and_deadline_records_are_supported(self):
        for query, kind in (("Học phí HKI?", "tuition"), ("Hồ sơ cần giấy tờ gì?", "enrollment_document"),
                            ("Hạn nộp hồ sơ?", "deadline")):
            with self.subTest(query=query):
                document = record("record", kind, "Thông tin đã xác minh.")
                self.assertEqual(lookup_structured_documents(query, [document]), [document])


class ThreeStreamRuntimeTests(unittest.TestCase):
    def test_audit_exposes_actual_third_stream_and_no_duplicate_chunks(self):
        wanted = record("wanted", "admission_score", "Điểm chuẩn 7480201: 15.", major_code="7480201")
        prose = record("prose", "page_text", "Điểm chuẩn 7480201 " * 10)

        class Store:
            def __init__(self, **kwargs):
                self._collection = self

            def count(self):
                return 2

            def similarity_search(self, query, **kwargs):
                return [prose]

            def get(self, **kwargs):
                return {"documents": [prose.page_content, wanted.page_content],
                        "metadatas": [prose.metadata, wanted.metadata]}

        with TemporaryDirectory() as directory:
            retriever = DHVRetriever(settings_obj=replace(settings, chroma_persist_dir=directory),
                                     store_factory=Store, embedding_factory=lambda **kwargs: object())
            result = retriever.retrieve_with_audit("Điểm chuẩn 7480201", categories=("diem_trung_tuyen",))
        self.assertEqual(result.audit.fusion_method, "bm25+dense+structured+rrf")
        self.assertEqual(result.audit.hits[0]["chunk_id"], "wanted")
        self.assertEqual(result.audit.hits[0]["structured_rank"], 1)
        ids = [d.metadata["chunk_id"] for d in result.documents]
        self.assertEqual(len(ids), len(set(ids)))
