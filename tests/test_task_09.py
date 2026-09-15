"""Regression contract for TASK 09 school-information integration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader

from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from src.ingestion.loader import load_verified_documents
from src.retrieval.retriever import topic_category


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_SCHOOL_PDF = (
    PROJECT_ROOT / "data" / "raw" / "thong_tin_truong" / "thong_tin_truong_dhv_2026.pdf"
)
PROCESSED_SCHOOL_MD = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "thong_tin_truong"
    / "thong_tin_truong_dhv_2026.md"
)
MANIFEST = PROJECT_ROOT / "data" / "raw" / "manifest.json"


class Task09DataTests(unittest.TestCase):
    def test_school_pdf_is_manifested_and_processed_by_pipeline(self) -> None:
        self.assertTrue(RAW_SCHOOL_PDF.exists())
        self.assertEqual(RAW_SCHOOL_PDF.suffix.lower(), ".pdf")
        self.assertTrue(PROCESSED_SCHOOL_MD.exists())

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entry = next(
            item
            for item in manifest["documents"]
            if item["raw_file"] == "data/raw/thong_tin_truong/thong_tin_truong_dhv_2026.pdf"
        )
        self.assertEqual(entry["category"], "thong_tin_truong")
        self.assertEqual(entry["year"], 2026)
        self.assertEqual(entry["verification_status"], "verified")
        self.assertGreaterEqual(len(entry["source_urls"]), 1)
        self.assertIn('category: "thong_tin_truong"', PROCESSED_SCHOOL_MD.read_text(encoding="utf-8"))

    def test_loader_keeps_school_metadata(self) -> None:
        result = load_verified_documents(PROJECT_ROOT / "data" / "processed")
        school_documents = [
            document
            for document in result.documents
            if document.metadata.get("category") == "thong_tin_truong"
        ]

        self.assertEqual(len(school_documents), 1)
        metadata = school_documents[0].metadata
        self.assertEqual(metadata["year"], 2026)
        self.assertEqual(metadata["status"], "verified")
        self.assertEqual(metadata["verification_status"], "verified")
        self.assertTrue(metadata["source_url"])
        self.assertIn("https://", str(metadata["source_urls"]))

    def test_school_raw_contains_verified_official_website_directory(self) -> None:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(RAW_SCHOOL_PDF)).pages)
        expected_urls = (
            "https://dhv.edu.vn/",
            "https://tuyensinh.dhv.edu.vn/",
            "https://ipic.dhv.edu.vn/",
            "https://epdl.dhv.edu.vn/",
            "https://heal.dhv.edu.vn/",
            "https://tec.dhv.edu.vn/",
            "https://fba.dhv.edu.vn/",
            "https://bam.dhv.edu.vn/",
            "https://lan.dhv.edu.vn/",
            "https://host.dhv.edu.vn/",
            "https://online.dhv.edu.vn/",
        )
        self.assertIn("HỆ SINH THÁI WEBSITE CHÍNH THỨC CỦA DHV", text)
        for url in expected_urls:
            with self.subTest(url=url):
                self.assertIn(url, text)


class Task09RoutingTests(unittest.TestCase):
    def test_required_school_questions_have_safe_routes(self) -> None:
        school_info_cases = (
            "DHV là trường gì?",
            "Trường thành lập khi nào?",
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


if __name__ == "__main__":
    unittest.main()
