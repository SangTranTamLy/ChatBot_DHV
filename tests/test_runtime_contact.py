"""Contact answers must reach verified facts stored outside the legacy category."""

import json
from pathlib import Path
import unittest

from langchain_core.documents import Document

from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot


ROOT = Path(__file__).resolve().parents[1]


class ContactRetriever:
    def __init__(self):
        self.documents = []
        for category in ("thong_tin_truong", "ho_so", "co_so_lien_he"):
            for path in (ROOT / "data/processed" / category).glob("*.json"):
                data = json.loads(path.read_text(encoding="utf-8"))
                for page in data["pages"]:
                    if category == "co_so_lien_he":
                        allowed_pages = {1}
                    else:
                        allowed_pages = {7} if category == "thong_tin_truong" else {2, 3}
                    if page["page"] not in allowed_pages:
                        continue
                    self.documents.append(Document(page_content=page["text"], metadata={
                        "category": category, "year": data["year"],
                        "school_code": "DHV", "status": data["source"]["status"],
                        "source_url": data["source"]["source_url"],
                        "title": data["title"], "page": page["page"],
                        "chunk_id": f"{path.stem}-{page['page']}",
                    }))

    def retrieve_with_audit(self, question, *, categories, **kwargs):
        return {"documents": [d for d in self.documents if d.metadata["category"] in categories]}


class AnswerLLM:
    def __init__(self, answer):
        self.answer = answer

    def generate(self, prompt):
        return self.answer


class RuntimeContactTests(unittest.TestCase):
    def test_campus_and_hotline_question_returns_both_requested_details(self):
        class NeverCalledLLM:
            def generate(self, prompt):
                raise AssertionError("Requested campus and hotline facts must use verified contact evidence")

        result = ask_chatbot(
            "Cơ sở và hotline tư vấn tuyển sinh DHV là gì?",
            retriever=ContactRetriever(), llm=NeverCalledLLM(),
        )

        answer = str(result["answer"])
        self.assertEqual(result["status"], "ok")
        for expected in (
            "194 Lê Đức Thọ", "736 Nguyễn Trãi", "37 Kinh Dương Vương",
            "Công viên Phần mềm Quang Trung", "0287 1000 888",
        ):
            self.assertIn(expected, answer)
        for unrelated_detail in ("info@dhv.edu.vn", "Kênh theo dõi", "TikTok", "Facebook"):
            self.assertNotIn(unrelated_detail, answer)

    def test_broad_contact_answer_contains_only_phone_and_email(self):
        class NeverCalledLLM:
            def generate(self, prompt):
                raise AssertionError("A broad contact answer must use the verified contact record")

        result = ask_chatbot(
            "Thông tin liên hệ của trường là gì?",
            retriever=ContactRetriever(), llm=NeverCalledLLM(),
        )
        answer = result["answer"]
        self.assertEqual(result["status"], "ok")
        for expected in (
            "info@dhv.edu.vn", "media@dhv.edu.vn", "0287 1000 888",
        ):
            self.assertIn(expected, answer)
        for irrelevant_contact_detail in (
            "Cơ sở", "Kênh theo dõi", "TikTok", "Zalo", "YouTube", "Facebook",
            "194 Lê Đức Thọ", "736 Nguyễn Trãi", "37 Kinh Dương Vương",
            "https://www.tiktok.com/", "https://dhv.edu.vn/",
        ):
            self.assertNotIn(irrelevant_contact_detail, answer)

    def test_social_follow_question_returns_only_verified_social_channels(self):
        class NeverCalledLLM:
            def generate(self, prompt):
                raise AssertionError("Social channels must come from the verified contact record")

        for question in (
            "Tôi theo dõi ở đâu để biết thêm thông tin?",
            "Những kênh mạng xã hội của trường là gì?",
        ):
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=ContactRetriever(), llm=NeverCalledLLM())
                answer = result["answer"]
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["trace"]["intent"], "HOI_CO_SO_LIEN_HE")
                self.assertIn("Bạn có thể theo dõi thông tin chính thức của DHV", answer)
                self.assertIn("**Website DHV:** [dhv.edu.vn](https://dhv.edu.vn/)", answer)
                for channel, account, url in (
                    ("Facebook", "hungvuonguni", "https://www.facebook.com/hungvuonguni"),
                    ("TikTok", "@dhv.official", "https://www.tiktok.com/@dhv.official"),
                    ("YouTube", "@hungvuonguni", "https://www.youtube.com/@hungvuonguni"),
                    ("Zalo", "zalo.me/1822829687649866202", "https://zalo.me/1822829687649866202"),
                ):
                    self.assertIn(f"**{channel}:** [{account}]({url})", answer)
                for unrelated_detail in (
                    "info@dhv.edu.vn", "0287 1000 888", "Cơ sở 1", "194 Lê Đức Thọ",
                ):
                    self.assertNotIn(unrelated_detail, answer)

    def test_campus_question_after_enrollment_uses_campus_list_without_generation(self):
        class NeverCalledLLM:
            def generate(self, prompt):
                raise AssertionError("A verified campus list must not be replaced by model tuition prose")

        first = ask_chatbot("nộp hồ sơ nhập học ở cơ sở nào", retriever=ContactRetriever(), llm=NeverCalledLLM())
        self.assertEqual(first["status"], "ok")
        self.assertNotIn("736 Nguyễn Trãi", first["answer"])
        for state in (None, first["conversation_state"]):
            with self.subTest(followup=state is not None):
                result = ask_chatbot("Trường có những cơ sở nào?", retriever=ContactRetriever(),
                                     llm=NeverCalledLLM(), conversation_state=state)
                self.assertEqual(result["status"], "ok")
                answer = result["answer"]
                for address in ("194 Lê Đức Thọ", "736 Nguyễn Trãi", "37 Kinh Dương Vương",
                                "Công viên Phần mềm Quang Trung, Phường Trung Mỹ Tây"):
                    self.assertIn(address, answer)
                self.assertEqual(answer.count("- Cơ sở"), 4)
                self.assertNotIn("học phí", answer.casefold())
                self.assertNotIn("Tổng đài", answer)

    def test_verified_contact_facts_reach_answer_validation(self):
        cases = (
            ("Tôi có thể liên hệ tuyển sinh DHV qua số điện thoại nào?", "Tổng đài tư vấn tuyển sinh: 0287 1000 888."),
            ("Thông tin liên hệ của trường là gi?", "Email: info@dhv.edu.vn; media@dhv.edu.vn. Tổng đài: 0287 1000 888."),
            ("Địa chỉ email tư vấn tuyển sinh DHV là gì?", "Email liên hệ chung của DHV: info@dhv.edu.vn."),
            ("DHV có bao nhiêu cơ sở và địa chỉ của từng cơ sở là gì?", "DHV có 4 cơ sở: 194 Lê Đức Thọ; 736 Nguyễn Trãi; 37 Kinh Dương Vương; Công viên Phần mềm Quang Trung."),
            ("Nếu em cần hỗ trợ trước khi thành sinh viên chính thức thì có thể liên hệ tư vấn viên không?", "Có. Tư vấn viên giải đáp thắc mắc trước khi chính thức trở thành sinh viên DHV."),
            ("Số điện thoại tư vấn viên nhập học DHV là gì?", "Số điện thoại tư vấn viên: 0848189507."),
        )
        for question, answer in cases:
            with self.subTest(question=question):
                result = ask_chatbot(question, retriever=ContactRetriever(), llm=AnswerLLM(answer))
                self.assertEqual(result["status"], "ok")
                self.assertGreater(result["trace"]["evidence_count"], 0)
                self.assertTrue(result["sources"])
                if question.startswith("Số điện thoại tư vấn viên"):
                    self.assertIn("chưa nêu số điện thoại riêng", result["answer"])
                    self.assertIn("0287 1000 888", result["answer"])
                    self.assertNotIn("0848189507", result["answer"])

    def test_faculty_email_is_not_inferred_from_school_email(self):
        result = ask_chatbot(
            "Tôi muốn liên lạc với Khoa Kỹ thuật Công nghệ DHV thì email nào?",
            retriever=ContactRetriever(), llm=AnswerLLM("Email của khoa là tec@dhv.edu.vn."),
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("chưa có email riêng", result["answer"])
        self.assertIn("Email liên hệ chung", result["answer"])
        self.assertNotIn("tec@dhv.edu.vn", result["answer"])

    def test_website_and_school_code_routes_are_preserved(self):
        for question, category in (("Website DHV là gì?", "thong_tin_truong"), ("Mã trường dùng trong tuyển sinh của Trường Đại học Hùng Vương TP. Hồ Chí Minh là gì?", "diem_trung_tuyen")):
            self.assertIn(category, route_question(analyze_question(question)).categories)
