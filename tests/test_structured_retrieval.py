"""Regression coverage for the structured third retrieval stream."""

import json
import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from langchain_core.documents import Document

from src.config.settings import settings
from src.retrieval.retriever import DHVRetriever, _metadata_filter, _rank_hybrid_candidates_with_audit
from src.retrieval.structured_lookup import lookup_structured_documents


def record(identity, kind, text, **metadata):
    return Document(page_content=text, metadata={
        "chunk_id": identity, "record_type": kind, "category": "diem_trung_tuyen",
        "year": 2026, "status": "verified", "school_code": "DHV",
        "source_url": "https://dhv.edu.vn/test-structured", "page": 1,
        "source_file": "data/raw/test.pdf", **metadata,
    })


class StructuredLookupTests(unittest.TestCase):
    def test_document_role_filter_excludes_nearby_topics_in_same_category_pool(self):
        contact = record(
            "contact", "page_text", "Email và tổng đài liên hệ DHV.",
            category="co_so_lien_he", data_role="co_so_va_kenh_lien_he",
        )
        enrollment = record(
            "enrollment", "page_text", "Tư vấn viên và thủ tục nhập học DHV.",
            category="ho_so", data_role="thu_tuc_va_quyen_loi_nhap_hoc",
        )

        ranked, _ = _rank_hybrid_candidates_with_audit(
            "Thông tin liên hệ của DHV", [contact, enrollment], [contact, enrollment], {},
            2026, 4, categories=("co_so_lien_he", "ho_so"),
            data_roles=("co_so_va_kenh_lien_he",),
        )

        self.assertEqual(ranked, [contact])
        self.assertEqual(
            _metadata_filter(2026, ("co_so_lien_he", "ho_so"), ("co_so_va_kenh_lien_he",)),
            {"$and": [{"year": 2026}, {"data_role": "co_so_va_kenh_lien_he"}]},
        )

    def test_document_role_keeps_fact_chunks_with_a_different_category(self):
        unibridge_tuition_fact = record(
            "unibridge-tuition", "tuition", "Hỗ trợ UniBridge học phí HKI.",
            category="hoc_phi", data_role="unibridge_ho_tro_tai_chinh",
        )
        ranked, _ = _rank_hybrid_candidates_with_audit(
            "UniBridge hỗ trợ học phí", [unibridge_tuition_fact], [unibridge_tuition_fact], {},
            2026, 4, categories=("hoc_bong",),
            data_roles=("unibridge_ho_tro_tai_chinh",),
        )
        self.assertEqual(ranked, [unibridge_tuition_fact])

    def test_all_major_score_followup_expands_past_semantic_top_k(self):
        majors = [f"Ngành {index:02d}" for index in range(1, 21)]
        documents = [
            record(
                f"major-{index:02d}",
                "admission_score",
                f"Điểm trúng tuyển {major}: 15 điểm.",
                major_name=major,
                major_code=f"{index:07d}",
                method="thpt",
            )
            for index, major in enumerate(majors, start=1)
        ]
        query = (
            "Điểm sàn của tất cả các ngành intent:HOI_DIEM_TRUNG_TUYEN "
            "score_type:admission_score "
            + " ".join(f"candidate_majors:{major}" for major in majors)
        )

        ranked, _ = _rank_hybrid_candidates_with_audit(
            query,
            documents,
            documents[:3],
            {},
            2026,
            4,
            categories=("diem_trung_tuyen",),
            entity_filters={"candidate_majors": majors},
        )

        self.assertEqual(len(ranked), 20)
        self.assertEqual(
            {document.metadata["major_name"] for document in ranked},
            set(majors),
        )

    def test_equivalent_ampersand_and_vietnamese_entity_names_match(self):
        wanted = record("tourism", "admission_score", "Điểm trúng tuyển Quản trị Dịch vụ Du lịch và Lữ hành: 18.",
                        major_name="Quản trị Dịch vụ Du lịch và Lữ hành", method="hoc_ba")
        ranked, _ = _rank_hybrid_candidates_with_audit(
            "Điểm chuẩn ngành Du lịch theo học bạ?", [wanted], [wanted], {}, 2026, 4,
            categories=("diem_trung_tuyen",), entity_filters={"major_name": "Quản trị Dịch vụ Du lịch & Lữ hành"},
        )
        self.assertEqual(ranked, [wanted])

    def test_reception_hours_do_not_select_paperwork(self):
        hours = record("hours", "page_text", "DHV tiếp nhận nhập học 06:00 – 18:00", category="ho_so")
        paper = record("paper", "enrollment_document", "Hồ sơ nhập học: Học bạ THPT.", category="ho_so")
        self.assertEqual(lookup_structured_documents("Nhận hồ sơ nhập học vào khung giờ nào?", [paper, hours]), [hours])

    def test_general_method_query_abstains_but_explicit_number_matches(self):
        first = record("first", "admission_method", "Phương thức 1", method_number=1)
        third = record("third", "admission_method", "Phương thức 3", method_number=3)
        self.assertEqual(lookup_structured_documents("Phương thức xét tuyển", [first, third]), [])
        self.assertEqual(lookup_structured_documents("Phương thức xét tuyển 3 là gì?", [first, third]), [third])

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
        # A broad question with no named major must keep BM25/vector overview evidence.
        self.assertEqual(lookup_structured_documents("Điểm chuẩn cho học sinh THPT?", records), [])

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
