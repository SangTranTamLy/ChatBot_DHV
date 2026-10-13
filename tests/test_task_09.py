"""Regression contract for TASK 09 school-information integration."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader

from src.chatbot.query_analysis import ConversationState, analyze_question, route_question
from src.chatbot.rag_chain import _ask_multi_issue, ask_chatbot
from src.config.settings import settings
from src.ingestion.loader import load_verified_documents
from src.retrieval.retriever import topic_category


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "data" / "raw" / "manifest.json"


def _verified_school_manifest_entry() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidates = [
        item
        for item in manifest["documents"]
        if item.get("category") == "thong_tin_truong"
        and item.get("year") == 2026
        and item.get("verified") is True
        and item.get("verification_status") == "verified"
        and item.get("source_url")
    ]
    if not candidates:
        raise AssertionError("No verified 2026 school-information PDF is listed in the RAW manifest")
    return sorted(candidates, key=lambda item: str(item.get("document_id")))[0]


SCHOOL_SOURCE = _verified_school_manifest_entry()
RAW_SCHOOL_PDF = PROJECT_ROOT / str(SCHOOL_SOURCE["raw_file"])
SCHOOL_RAW_RELATIVE = Path(str(SCHOOL_SOURCE["raw_file"])).relative_to("data/raw")
PROCESSED_SCHOOL_JSON = PROJECT_ROOT / "data" / "processed" / SCHOOL_RAW_RELATIVE.with_suffix(".json")


class Task09DataTests(unittest.TestCase):
    def test_school_pdf_is_manifested_and_processed_by_pipeline(self) -> None:
        self.assertTrue(RAW_SCHOOL_PDF.exists())
        self.assertEqual(RAW_SCHOOL_PDF.suffix.lower(), ".pdf")
        self.assertTrue(PROCESSED_SCHOOL_JSON.exists())

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entry = next(item for item in manifest["documents"] if item["document_id"] == SCHOOL_SOURCE["document_id"])
        self.assertEqual(entry["category"], "thong_tin_truong")
        self.assertEqual(entry["year"], 2026)
        self.assertEqual(entry["verification_status"], "verified")
        self.assertGreaterEqual(len(entry["source_urls"]), 1)
        document = json.loads(PROCESSED_SCHOOL_JSON.read_text(encoding="utf-8"))
        self.assertEqual(document["category"], "thong_tin_truong")
        self.assertEqual(document["year"], 2026)
        self.assertEqual(document["source"]["verification_status"], "verified")
        self.assertTrue(document["pages"])

    def test_loader_keeps_school_metadata(self) -> None:
        result = load_verified_documents(PROJECT_ROOT / "data" / "processed")
        school_documents = [
            document
            for document in result.documents
            if document.metadata.get("category") == "thong_tin_truong"
        ]

        self.assertGreaterEqual(len(school_documents), 1)
        metadata = school_documents[0].metadata
        self.assertEqual(metadata["year"], 2026)
        self.assertEqual(metadata["status"], "verified")
        self.assertEqual(metadata["verification_status"], "verified")
        self.assertTrue(metadata["source_url"])
        self.assertIn("https://", str(metadata["source_urls"]))

    def test_manifested_verified_school_pdf_matches_processed_page_coverage(self) -> None:
        raw_pages = PdfReader(str(RAW_SCHOOL_PDF)).pages
        document = json.loads(PROCESSED_SCHOOL_JSON.read_text(encoding="utf-8"))
        self.assertEqual(len(raw_pages), len(document["pages"]))
        processed_text = "\n".join(page.get("text", "") for page in document["pages"])
        self.assertIn("1995", processed_text)
        self.assertIn("HỢP TÁC", processed_text)
        self.assertEqual(document["document_id"], SCHOOL_SOURCE["document_id"])
        self.assertEqual(document["source"]["source_url"], SCHOOL_SOURCE["source_url"])


class Task09RoutingTests(unittest.TestCase):
    def test_required_school_questions_have_safe_routes(self) -> None:
        school_info_cases = (
            "DHV là trường gì?",
            "Trường thành lập khi nào?",
            "Lịch sử của trường",
            "Triết lý giáo dục của trường là gì?",
        )
        for question in school_info_cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "SCHOOL_INFO")
                self.assertEqual(plan.categories, ("thong_tin_truong",))
                self.assertEqual(topic_category(question), "thong_tin_truong")

    def test_website_questions_can_use_school_provenance_without_breaking_contact_route(self) -> None:
        for question in ("Website của trường là gì?", "Web tuyển sinh DHV?"):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_CO_SO_LIEN_HE")
                self.assertTrue(analysis.entities["website_request"])
                self.assertIn("thong_tin_truong", plan.categories)
                self.assertIn("co_so_lien_he", plan.categories)
                self.assertEqual(topic_category(question), "thong_tin_truong")

    def test_specific_school_unit_website_is_not_misrouted_as_school_overview(self) -> None:
        questions = (
            "website Viện Đào tạo Sau đại học?",
            "website Vien Dao tao Sau dai hoc?",
            "website Khoa Kỹ thuật Công nghệ là gì?",
            "website Khoa Ky thuat Cong nghe la gi?",
        )
        for question in questions:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_CO_SO_LIEN_HE")
                self.assertTrue(analysis.entities["website_request"])
                self.assertFalse(plan.subplans)
                self.assertNotIn("SCHOOL_INFO", analysis.entities.get("issue_intents", []))

        compound = analyze_question(
            "Thông tin trường DHV và website Viện Đào tạo Sau đại học"
        )
        compound_plan = route_question(compound)
        self.assertEqual(compound.intent, "MULTI_ISSUE")
        self.assertEqual(
            {subplan.intent for subplan in compound_plan.subplans},
            {"SCHOOL_INFO", "HOI_CO_SO_LIEN_HE"},
        )

    def test_website_count_is_a_distinct_count_request(self) -> None:
        for question in (
            "Trường DHV có bao nhiêu website?",
            "DHV có mấy trang web?",
            "truong DHV co bao nhieu website?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertTrue(analysis.entities["website_request"])
                self.assertTrue(analysis.entities["website_count_request"])
                self.assertEqual(analysis.entities["query_mode"], "COUNT")
                self.assertEqual(
                    analysis.entities["requested_information"],
                    ["official_website_count"],
                )

    def test_campuses_remain_in_contact_category_and_scope_question_is_system(self) -> None:
        analysis = analyze_question("DHV có những cơ sở nào?")
        plan = route_question(analysis)
        self.assertEqual(analysis.intent, "HOI_CO_SO_LIEN_HE")
        self.assertEqual(plan.categories, ("co_so_lien_he",))

        scope = analyze_question("Đây có phải toàn bộ thông tin về trường không?")
        scope_plan = route_question(scope)
        self.assertEqual(scope.intent, "SYSTEM_SCOPE")
        self.assertEqual(scope_plan.categories, ())

    def test_system_scope_does_not_retrieve(self) -> None:
        class NeverCalled:
            def retrieve(self, *_: object, **__: object) -> list[object]:
                raise AssertionError("scope question must not retrieve")

            def retrieve_with_audit(self, *_: object, **__: object) -> object:
                raise AssertionError("scope question must not retrieve")

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("scope question must not call LLM")

        result = ask_chatbot(
            "Đây có phải toàn bộ thông tin về trường không?",
            retriever=NeverCalled(),
            llm=NeverCalledLLM(),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"], [])
        self.assertIn("không phải toàn bộ", str(result["answer"]).casefold())

    def test_website_answers_select_the_requested_verified_portal(self) -> None:
        class SchoolInfoRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content="Website trường và cổng tuyển sinh đã được kiểm chứng.",
                        metadata={
                            "title": "Thông tin trường phục vụ tư vấn",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "source_url": "https://tuyensinh.dhv.edu.vn/",
                            "source_urls": json.dumps(
                                ["https://tuyensinh.dhv.edu.vn/", "https://dhv.edu.vn/"]
                            ),
                            "status": "verified",
                            "chunk_id": "task-09-website",
                        },
                    )
                ]

        school_site = ask_chatbot(
            "Website của trường là gì?",
            retriever=SchoolInfoRetriever(),
        )
        self.assertEqual(school_site["status"], "ok")
        self.assertIn("https://dhv.edu.vn/", school_site["answer"])
        self.assertNotIn("https://tuyensinh.dhv.edu.vn/", school_site["answer"])

        admissions_site = ask_chatbot(
            "Web tuyển sinh DHV?",
            retriever=SchoolInfoRetriever(),
        )
        self.assertEqual(admissions_site["status"], "ok")
        self.assertIn("https://tuyensinh.dhv.edu.vn/", admissions_site["answer"])
        self.assertNotIn("https://dhv.edu.vn/", admissions_site["answer"])

    def test_website_answers_select_requested_school_unit_from_verified_directory(self) -> None:
        directory = (
            ("Website chính Trường Đại học Hùng Vương TP.HCM", "Kênh thông tin chung của trường.", "https://dhv.edu.vn/"),
            ("Cổng tuyển sinh DHV", "Kênh thông tin tuyển sinh.", "https://tuyensinh.dhv.edu.vn/"),
            ("Viện Đào tạo Sau đại học", "Trang thông tin của viện.", "https://ipic.dhv.edu.vn/"),
            ("Viện Liên kết Giáo dục và Đào tạo từ xa", "Trang thông tin của viện.", "https://epdl.dhv.edu.vn/"),
            ("Khoa Khoa học Sức khỏe", "Trang thông tin của khoa.", "https://heal.dhv.edu.vn/"),
            ("Khoa Kỹ thuật Công nghệ", "Trang thông tin của khoa.", "https://tec.dhv.edu.vn/"),
            ("Khoa Tài chính - Ngân hàng - Kế toán", "Trang thông tin của khoa.", "https://fba.dhv.edu.vn/"),
            ("Khoa Quản trị Kinh doanh - Marketing", "Trang thông tin của khoa.", "https://bam.dhv.edu.vn/"),
            ("Khoa Ngôn ngữ", "Trang thông tin của khoa.", "https://lan.dhv.edu.vn/"),
            ("Khoa Du lịch - Nhà hàng - Khách sạn", "Trang thông tin của khoa.", "https://host.dhv.edu.vn/"),
            ("Cổng thông tin đào tạo dành cho sinh viên/giảng viên", "Cổng thông tin đào tạo.", "https://online.dhv.edu.vn/"),
        )
        directory_text = "\n".join(
            f"{name}\nLoại: Đơn vị DHV\nMục đích: {purpose}\nWebsite: {url}"
            for name, purpose, url in directory
        )
        urls = [url for _, _, url in directory]

        class DirectoryRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content=directory_text,
                        metadata={
                            "title": "Thông tin trường phục vụ tư vấn",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "source_url": urls[0],
                            "source_urls": json.dumps(urls),
                            "status": "verified",
                            "verification_status": "verified",
                            "chunk_id": "task-09-directory",
                        },
                    )
                ]

        cases = (
            ("website chính của DHV là gì?", "https://dhv.edu.vn/"),
            ("web tuyển sinh DHV là gì?", "https://tuyensinh.dhv.edu.vn/"),
            ("website Khoa Kỹ thuật Công nghệ là gì?", "https://tec.dhv.edu.vn/"),
            ("web Khoa Ngôn ngữ?", "https://lan.dhv.edu.vn/"),
            ("Khoa Khoa học Sức khỏe có website không?", "https://heal.dhv.edu.vn/"),
            ("website Viện Đào tạo Sau đại học?", "https://ipic.dhv.edu.vn/"),
            ("cổng thông tin đào tạo của DHV là gì?", "https://online.dhv.edu.vn/"),
        )
        for question, expected_url in cases:
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=DirectoryRetriever())
                self.assertEqual(result["status"], "ok")
                self.assertIn(expected_url, str(result["answer"]))
                other_urls = [url for url in urls if url != expected_url]
                self.assertFalse(any(url in str(result["answer"]) for url in other_urls))

        existence_cases = (
            ("DHV có Viện Đào tạo Sau đại học không?", "Viện Đào tạo Sau đại học"),
            ("DHV có đào tạo từ xa không?", "Viện Liên kết Giáo dục và Đào tạo từ xa"),
        )
        for question, expected_name in existence_cases:
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=DirectoryRetriever())
                self.assertEqual(result["status"], "ok")
                self.assertIn(expected_name, str(result["answer"]))
                self.assertNotIn("https://", str(result["answer"]))

    def test_website_count_lists_all_unique_verified_domains(self) -> None:
        class WebsiteDirectoryRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content="Website trường và cổng tuyển sinh DHV.",
                        metadata={
                            "title": "Danh mục website DHV",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "source_url": "https://dhv.edu.vn/",
                            "source_urls": json.dumps(
                                ["https://dhv.edu.vn/", "https://tuyensinh.dhv.edu.vn/"]
                            ),
                            "status": "verified",
                            "verification_status": "verified",
                            "chunk_id": "task-09-website-count",
                        },
                    )
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("verified website count should be deterministic")

        result = ask_chatbot(
            "Trường DHV có bao nhiêu website?",
            retriever=WebsiteDirectoryRetriever(),
            llm=NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("2 website", str(result["answer"]).casefold())
        self.assertIn("https://dhv.edu.vn/", str(result["answer"]))
        self.assertIn("https://tuyensinh.dhv.edu.vn/", str(result["answer"]))
        self.assertEqual(
            {source["url"] for source in result["sources"]},
            {"https://dhv.edu.vn/", "https://tuyensinh.dhv.edu.vn/"},
        )

    def test_specific_website_request_does_not_fall_back_to_another_site(self) -> None:
        class MainSiteOnlyRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content="Website chính thức của DHV.",
                        metadata={
                            "title": "Thông tin trường DHV",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/",
                            "chunk_id": "task-09-main-site-only",
                        },
                    )
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("missing requested portal must not use another URL or LLM")

        result = ask_chatbot(
            "Web tuyển sinh DHV?",
            retriever=MainSiteOnlyRetriever(),
            llm=NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertNotIn("https://dhv.edu.vn/", str(result["answer"]))
        self.assertEqual(
            result["trace"].get("evidence_boundary"),
            "requested_website_not_in_verified_evidence",
        )

    def test_missing_school_unit_website_does_not_return_unrelated_overview(self) -> None:
        class OverviewOnlyRetriever:
            def __init__(self) -> None:
                self.calls = 0

            def retrieve_with_audit(self, *_: object, **__: object) -> dict[str, object]:
                self.calls += 1
                return {
                    "documents": [
                        Document(
                            page_content=(
                                "TỔNG QUAN VỀ TRƯỜNG\n"
                                "DHV là cơ sở giáo dục đại học, đào tạo và phát triển nguồn nhân lực."
                            ),
                            metadata={
                                "title": "Tổng quan DHV",
                                "category": "thong_tin_truong",
                                "year": 2026,
                                "school_code": "DHV",
                                "status": "verified",
                                "verification_status": "verified",
                                "source_url": "https://dhv.edu.vn/",
                                "chunk_id": "task-09-unit-website-overview-only",
                            },
                        )
                    ]
                }

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("missing unit website must not fall back to overview generation")

        retriever = OverviewOnlyRetriever()
        result = ask_chatbot(
            "website Viện Đào tạo Sau đại học?",
            retriever=retriever,
            llm=NeverCalledLLM(),
        )

        self.assertEqual(retriever.calls, 1)
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertNotIn("Tổng quan", str(result["answer"]))
        self.assertNotIn("cơ sở giáo dục đại học", str(result["answer"]))
        self.assertEqual(result["trace"]["intent"], "HOI_CO_SO_LIEN_HE")
        self.assertEqual(result["trace"]["retrieval_calls"], 1)
        self.assertEqual(
            result["trace"].get("evidence_boundary"),
            "requested_website_not_in_verified_evidence",
        )

    def test_website_count_uses_runtime_target_year_not_global_default(self) -> None:
        class FutureYearWebsiteRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content="DHV có website trường và cổng tuyển sinh.",
                        metadata={
                            "title": "Danh mục website DHV",
                            "category": "thong_tin_truong",
                            "year": 2030,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/",
                            "source_urls": json.dumps(
                                ["https://dhv.edu.vn/", "https://tuyensinh.dhv.edu.vn/"]
                            ),
                            "chunk_id": "task-09-target-year-websites",
                        },
                    )
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("website count should be evidence-only")

        result = ask_chatbot(
            "DHV có bao nhiêu website?",
            retriever=FutureYearWebsiteRetriever(),
            llm=NeverCalledLLM(),
            settings_obj=replace(settings, target_year=2030),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("2 website", str(result["answer"]).casefold())
        self.assertIn("Cổng tuyển sinh 2030", str(result["answer"]))
        self.assertIn("https://tuyensinh.dhv.edu.vn/", str(result["answer"]))

    def test_generic_school_overview_uses_intro_not_unrelated_scholarship_evidence(self) -> None:
        class SchoolOverviewRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                common = {
                    "year": 2026,
                    "school_code": "DHV",
                    "status": "verified",
                    "verification_status": "verified",
                }
                return [
                    Document(
                        page_content=(
                            "Học bổng: 70% học phí chuẩn HK1 khi đạt điều kiện điểm.\n"
                            * 1800
                        ),
                        metadata={
                            **common,
                            "title": "Tổng quan tuyển sinh DHV 2026",
                            "category": "thong_tin_truong",
                            "source_url": "https://tuyensinh.dhv.edu.vn/",
                            "chunk_id": "task-09-unrelated-scholarship",
                        },
                    ),
                    Document(
                        page_content=(
                            "1.1. TỔNG QUAN VỀ TRƯỜNG\n"
                            "Trường Đại học Hùng Vương Thành phố Hồ Chí Minh là một cơ sở giáo dục đại học.\n"
                            "Với sứ mệnh đào tạo và phát triển nguồn nhân lực cho xã hội.\n"
                            "DHV đào tạo các thế hệ sinh viên có trách nhiệm với cộng đồng.\n"
                            "1.1. Triết lý giáo dục"
                        ),
                        metadata={
                            **common,
                            "title": "Tổng quan về trường DHV",
                            "category": "thong_tin_truong",
                            "source_url": "https://dhv.edu.vn/",
                            "chunk_id": "task-09-overview",
                        },
                    ),
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("generic overview must not use unrelated broad context")

        result = ask_chatbot(
            "Thông tin trường DHV",
            retriever=SchoolOverviewRetriever(),
            llm=NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["trace"]["school_overview_evidence_prioritized"])
        self.assertIn("là một cơ sở giáo dục đại học", str(result["answer"]))
        self.assertIn("phát triển nguồn nhân lực", str(result["answer"]))
        self.assertNotIn("học bổng", str(result["answer"]).casefold())
        self.assertEqual(
            {source["url"] for source in result["sources"]},
            {"https://dhv.edu.vn/"},
        )

    def test_generic_school_overview_without_intro_evidence_returns_no_data(self) -> None:
        class ScholarshipOnlyRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content="Học bổng 70% học phí chuẩn HK1 theo điều kiện điểm.",
                        metadata={
                            "title": "Tổng quan tuyển sinh DHV 2026",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "source_url": "https://tuyensinh.dhv.edu.vn/",
                            "status": "verified",
                            "verification_status": "verified",
                            "chunk_id": "task-09-scholarship-only",
                        },
                    )
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("unsupported overview must stop before generation")

        result = ask_chatbot(
            "Thông tin trường DHV",
            retriever=ScholarshipOnlyRetriever(),
            llm=NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["trace"]["retrieval_calls"], 1)
        self.assertEqual(result["trace"]["evidence_count"], 1)
        self.assertEqual(
            result["trace"].get("evidence_boundary"),
            "school_overview_missing_matching_evidence",
        )

    def test_school_overview_uses_runtime_target_year_not_global_default(self) -> None:
        class FutureYearOverviewRetriever:
            def retrieve(self, *_: object, **__: object) -> list[Document]:
                return [
                    Document(
                        page_content=(
                            "TỔNG QUAN VỀ TRƯỜNG\n"
                            "Trường Đại học Hùng Vương TP.HCM là cơ sở giáo dục đại học.\n"
                            "Trường đào tạo và phát triển nguồn nhân lực cho xã hội."
                        ),
                        metadata={
                            "title": "Tổng quan DHV",
                            "category": "thong_tin_truong",
                            "year": 2030,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/",
                            "chunk_id": "task-09-overview-runtime-year",
                        },
                    )
                ]

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("verified overview should stay deterministic")

        result = ask_chatbot(
            "Thông tin trường DHV",
            retriever=FutureYearOverviewRetriever(),
            llm=NeverCalledLLM(),
            settings_obj=replace(settings, target_year=2030),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("cơ sở giáo dục đại học", str(result["answer"]))
        self.assertEqual(
            result["sources"],
            [{"title": "Tổng quan DHV", "url": "https://dhv.edu.vn/"}],
        )

    def test_natural_overview_compounds_create_independent_subplans(self) -> None:
        cases = (
            (
                "Thông tin trường DHV và học bổng DHV",
                {"SCHOOL_INFO", "HOI_HOC_BONG"},
            ),
            (
                "Thông tin trường DHV và website trường?",
                {"SCHOOL_INFO", "HOI_CO_SO_LIEN_HE"},
            ),
            (
                "Giới thiệu về trường DHV và cổng tuyển sinh?",
                {"SCHOOL_INFO", "HOI_CO_SO_LIEN_HE"},
            ),
        )
        for question, expected_intents in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                actual_intents = {subplan.intent for subplan in plan.subplans}
                self.assertEqual(analysis.intent, "MULTI_ISSUE")
                self.assertTrue(expected_intents.issubset(actual_intents))

        ordered = route_question(
            analyze_question("Thông tin trường DHV và học bổng DHV")
        )
        self.assertEqual(
            [subplan.intent for subplan in ordered.subplans],
            ["SCHOOL_INFO", "HOI_HOC_BONG"],
        )

    def test_natural_overview_compounds_answer_each_verified_issue(self) -> None:
        class MultiTopicRetriever:
            def retrieve_with_audit(
                self,
                question: str,
                *,
                categories: tuple[str, ...],
                retrieval_query: str,
                **_: object,
            ) -> dict[str, object]:
                del question, retrieval_query
                if "hoc_bong" in categories:
                    document = Document(
                        page_content=(
                            "Học bổng DHV 2026\n"
                            "HỌC BỔNG - HỌC PHÍ\n"
                            "• Chính sách học bổng: DHV có học bổng tuyển sinh theo điều kiện công bố."
                        ),
                        metadata={
                            "title": "Học bổng DHV",
                            "category": "hoc_bong",
                            "year": 2026,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/hoc-bong",
                            "chunk_id": "task-09-multi-scholarship-positive",
                        },
                    )
                elif "co_so_lien_he" in categories:
                    document = Document(
                        page_content="Website trường và cổng tuyển sinh DHV.",
                        metadata={
                            "title": "Danh mục website DHV",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/",
                            "source_urls": json.dumps(
                                ["https://dhv.edu.vn/", "https://tuyensinh.dhv.edu.vn/"]
                            ),
                            "chunk_id": "task-09-multi-websites-positive",
                        },
                    )
                else:
                    document = Document(
                        page_content=(
                            "TỔNG QUAN VỀ TRƯỜNG\n"
                            "DHV là cơ sở giáo dục đại học, đào tạo và phát triển nguồn nhân lực."
                        ),
                        metadata={
                            "title": "Tổng quan DHV",
                            "category": "thong_tin_truong",
                            "year": 2026,
                            "school_code": "DHV",
                            "status": "verified",
                            "verification_status": "verified",
                            "source_url": "https://dhv.edu.vn/",
                            "chunk_id": "task-09-multi-overview-positive",
                        },
                    )
                return {"documents": [document]}

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError(
                    "verified scholarship facts should use the deterministic evidence answer"
                )

        scholarship_result = ask_chatbot(
            "Thông tin trường DHV và học bổng DHV",
            retriever=MultiTopicRetriever(),
            llm=NeverCalledLLM(),
        )
        self.assertEqual(scholarship_result["status"], "ok")
        self.assertIn("### Thông tin trường", scholarship_result["answer"])
        self.assertIn("### Học bổng", scholarship_result["answer"])
        self.assertIn("đào tạo và phát triển nguồn nhân lực", scholarship_result["answer"])
        self.assertIn("học bổng tuyển sinh", scholarship_result["answer"])
        self.assertNotIn("học phí", str(scholarship_result["answer"]).casefold())
        self.assertNotIn("HỌC BỔNG - HỌC PHÍ", scholarship_result["answer"])
        self.assertNotIn("Học bổng DHV 2026", scholarship_result["answer"])
        self.assertNotIn("(#)", scholarship_result["answer"])

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("verified overview and website are deterministic")

        for question, expected_url in (
            (
                "Thông tin trường DHV và website trường?",
                "https://dhv.edu.vn/",
            ),
            (
                "Giới thiệu về trường DHV và cổng tuyển sinh?",
                "https://tuyensinh.dhv.edu.vn/",
            ),
        ):
            with self.subTest(question=question):
                result = ask_chatbot(
                    question,
                    retriever=MultiTopicRetriever(),
                    llm=NeverCalledLLM(),
                )
                self.assertEqual(result["status"], "ok")
                self.assertIn("### Thông tin trường", result["answer"])
                self.assertIn("### Cơ sở và liên hệ", result["answer"])
                self.assertIn(expected_url, result["answer"])

    def test_scholarship_answer_omits_numbered_heading_but_keeps_verified_values(self) -> None:
        class ScholarshipRetriever:
            def retrieve_with_audit(
                self,
                *_: object,
                **__: object,
            ) -> dict[str, object]:
                return {
                    "documents": [
                        Document(
                            page_content=(
                                "Học bổng DHV 2026\n"
                                "• Chính sách học bổng: Mức học bổng lên đến 50% học phí học kỳ 2.\n"
                                "1.16. Học bổng Cam kết hoàn học phí\n"
                                "• Quỹ học bổng lên đến 75 tỷ đồng dành cho sinh viên nhập học năm 2026."
                            ),
                            metadata={
                                "title": "Học bổng DHV 2026",
                                "category": "hoc_bong",
                                "year": 2026,
                                "school_code": "DHV",
                                "status": "verified",
                                "verification_status": "verified",
                                "source_url": "https://tuyensinh.dhv.edu.vn/",
                                "chunk_id": "task-09-numbered-scholarship-heading",
                            },
                        )
                    ]
                }

        class NeverCalledLLM:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("verified scholarship formatting must be deterministic")

        result = ask_chatbot(
            "DHV có học bổng nào?",
            retriever=ScholarshipRetriever(),
            llm=NeverCalledLLM(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("50%", result["answer"])
        self.assertIn("75 tỷ đồng", result["answer"])
        self.assertIn("Quỹ học bổng", result["answer"])
        self.assertNotIn("1.16.", result["answer"])
        self.assertEqual(result["sources"][0]["url"], "https://tuyensinh.dhv.edu.vn/")

    def test_multi_issue_school_overview_fails_closed_without_intro_evidence(self) -> None:
        class MultiIssueRetriever:
            def retrieve_with_audit(
                self,
                question: str,
                *,
                categories: tuple[str, ...],
                retrieval_query: str,
                **_: object,
            ) -> dict[str, object]:
                del question, retrieval_query
                if "hoc_bong" in categories:
                    content = "DHV có chính sách học bổng tuyển sinh theo điều kiện."
                    category = "hoc_bong"
                    chunk_id = "task-09-multi-scholarship"
                else:
                    # Same broad topic, but deliberately no introduction heading.
                    content = "Học bổng tuyển sinh DHV có các điều kiện áp dụng."
                    category = "thong_tin_truong"
                    chunk_id = "task-09-multi-school-details-only"
                return {
                    "documents": [
                        Document(
                            page_content=content,
                            metadata={
                                "title": "Thông tin DHV 2026",
                                "category": category,
                                "year": 2026,
                                "school_code": "DHV",
                                "status": "verified",
                                "verification_status": "verified",
                                "source_url": "https://dhv.edu.vn/",
                                "chunk_id": chunk_id,
                            },
                        )
                    ]
                }

        class RecordingLLM:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "DHV có chính sách học bổng tuyển sinh theo điều kiện."

        llm = RecordingLLM()
        for question in (
            "Thông tin trường DHV và sự kiện, website, học bổng",
            "Thong tin truong DHV va su kien, website, hoc bong",
        ):
            with self.subTest(question=question):
                result = ask_chatbot(
                    question,
                    retriever=MultiIssueRetriever(),
                    llm=llm,
                )

                multi_issue = result["trace"]["multi_issue"]
                intents = [subplan["intent"] for subplan in multi_issue["subplans"]]
                self.assertEqual(len(multi_issue["subplans"]), 4)
                # Scholarship now has a deterministic evidence-backed route too; the
                # overview without matching intro evidence must not trigger generation.
                self.assertEqual(len(llm.prompts), 0)
                scholarship_index = intents.index("HOI_HOC_BONG")
                self.assertEqual(multi_issue["statuses"][scholarship_index], "ok")
                self.assertIn("học bổng", result["answer"].casefold())
                event_index = intents.index("OUT_OF_SCOPE")
                self.assertEqual(multi_issue["statuses"][event_index], "out_of_scope")
                self.assertEqual(
                    multi_issue["evidence_boundaries"][event_index],
                    "unsupported_event_topic_outside_approved_scope",
                )
                self.assertIn("### Sự kiện và hoạt động trường", result["answer"])
                self.assertIn("chưa có nguồn đã xác minh", result["answer"])
                self.assertIsNone(multi_issue["retrieval_audits"][event_index])
                self.assertEqual(multi_issue["retrieved_docs_counts"][event_index], 0)
                self.assertEqual(multi_issue["evidence_counts"][event_index], 0)
                overview_index = intents.index("SCHOOL_INFO")
                self.assertEqual(multi_issue["statuses"][overview_index], "no_data")
                self.assertEqual(
                    multi_issue["evidence_boundaries"][overview_index],
                    "school_overview_missing_matching_evidence",
                )
                self.assertEqual(
                    multi_issue["school_overview_evidence_prioritized"][overview_index],
                    False,
                )
                self.assertEqual(result["trace"]["retrieval_calls"], len(intents) - 1)
                self.assertEqual(
                    result["trace"]["retrieved_docs_count"],
                    sum(multi_issue["retrieved_docs_counts"]),
                )
                self.assertEqual(
                    result["trace"]["evidence_count"],
                    sum(multi_issue["evidence_counts"]),
                )

    def test_overview_gate_survives_detail_markers_in_school_info_subplan(self) -> None:
        question = "Thông tin trường DHV và sự kiện, website, học bổng"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        self.assertIn("SCHOOL_INFO", [subplan.intent for subplan in plan.subplans])

        class DetailsWithoutIntroRetriever:
            def retrieve_with_audit(
                self,
                *_: object,
                categories: tuple[str, ...],
                **__: object,
            ) -> dict[str, object]:
                if categories == ("hoc_bong",):
                    page_content = "DHV có học bổng tuyển sinh theo điều kiện công bố."
                    category = "hoc_bong"
                    chunk_id = "task-09-security-scholarship"
                else:
                    # Deliberately usable detail evidence, but no approved intro heading.
                    page_content = "Thông tin trường DHV: sự kiện và website được công bố riêng."
                    category = "thong_tin_truong"
                    chunk_id = "task-09-security-details-only"
                return {
                    "documents": [
                        Document(
                            page_content=page_content,
                            metadata={
                                "title": "Thông tin DHV",
                                "category": category,
                                "year": 2026,
                                "school_code": "DHV",
                                "status": "verified",
                                "verification_status": "verified",
                                "source_url": "https://dhv.edu.vn/",
                                "chunk_id": chunk_id,
                            },
                        )
                    ]
                }

        class RecordingLLM:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "DHV có các hoạt động và website liên quan."

        for school_subquery in (
            "Thông tin trường DHV và sự kiện, website",
            "website của đơn vị DHV",
        ):
            with self.subTest(school_subquery=school_subquery):
                subplans = tuple(
                    replace(subplan, retrieval_query=school_subquery)
                    if subplan.intent == "SCHOOL_INFO"
                    else subplan
                    for subplan in plan.subplans
                )
                llm = RecordingLLM()
                result = _ask_multi_issue(
                    query=question,
                    analysis=analysis,
                    plan=replace(plan, subplans=subplans),
                    state=ConversationState(),
                    retriever=DetailsWithoutIntroRetriever(),
                    llm=llm,
                    settings_obj=settings,
                )

                multi_issue = result["trace"]["multi_issue"]
                intents = [subplan["intent"] for subplan in multi_issue["subplans"]]
                overview_index = intents.index("SCHOOL_INFO")
                self.assertEqual(llm.prompts, [])
                self.assertEqual(multi_issue["statuses"][overview_index], "no_data")
                self.assertEqual(
                    multi_issue["evidence_boundaries"][overview_index],
                    "school_overview_missing_matching_evidence",
                )
                self.assertEqual(result["trace"]["retrieval_calls"], len(intents) - 1)
                self.assertEqual(
                    result["trace"]["retrieved_docs_count"],
                    sum(multi_issue["retrieved_docs_counts"]),
                )
                self.assertEqual(
                    result["trace"]["evidence_count"],
                    sum(multi_issue["evidence_counts"]),
                )


if __name__ == "__main__":
    unittest.main()
