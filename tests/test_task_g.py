"""Task G regressions for program-catalog intent, scope and deterministic counts."""

from __future__ import annotations

import unittest
from collections import Counter

from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import validate_model_answer
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import analyze_question

from tests.test_task_f import (
    DHV_PROGRAM_PARENTS_2026,
    EchoEvidenceLLM,
    RecordingLLM,
    _fixture_chunks,
    _retriever,
)


class TaskGIntentTests(unittest.TestCase):
    def test_natural_language_specialization_aliases_resolve_to_program_catalog(self) -> None:
        cases = (
            (
                "Bạn có thể liệt kê những chuyên ngành của ngành công nghệ thông tin không?",
                "LIST",
            ),
            ("Công nghệ thông tin có mấy chuyên ngành?", "COUNT"),
            ("CNTT có bao nhiêu chuyên ngành?", "COUNT"),
            ("CNTT gồm những chuyên ngành nào?", "LIST"),
            (
                "CNTT có bao nhiêu chuyên ngành, gồm những gì?",
                "LIST_AND_COUNT",
            ),
            ("Liệt kê chương trình đào tạo của CNTT", "LIST"),
        )
        for question, operation in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.intent, "DANH_SACH_CHUONG_TRINH")
                self.assertEqual(analysis.entities["major_name"], "Công nghệ thông tin")
                self.assertEqual(analysis.entities["entity_type"], "major")
                self.assertEqual(analysis.entities["catalog_operation"], operation)

    def test_major_catalog_language_stays_a_major_catalog(self) -> None:
        analysis = analyze_question("Liệt kê tất cả các ngành của trường")
        self.assertEqual(analysis.intent, "DANH_SACH_NGANH")
        self.assertIsNone(analysis.entities["catalog_operation"])

    def test_same_name_major_and_program_keep_their_semantics(self) -> None:
        for major, program in (
            ("Công nghệ tài chính", "Công nghệ tài chính"),
            ("Quản trị Khách sạn", "Quản trị khách sạn"),
        ):
            with self.subTest(major=major):
                catalog = analyze_question(f"{major} có mấy chuyên ngành?")
                self.assertEqual(catalog.intent, "DANH_SACH_CHUONG_TRINH")
                self.assertEqual(catalog.entities["major_name"], major)
                self.assertEqual(catalog.entities["entity_type"], "major")
                self.assertIsNone(catalog.entities["program_name"])

                relation = analyze_question(f"{program} thuộc ngành nào?")
                self.assertEqual(relation.intent, "HOI_CHUONG_TRINH")
                self.assertEqual(relation.entities["entity_type"], "program")
                self.assertEqual(relation.entities["program_name"], program)

    def test_followup_resolves_current_major_without_raw_history(self) -> None:
        first = analyze_question("Tôi đang tìm hiểu Công nghệ thông tin")
        self.assertEqual(first.intent, "HOI_NGANH")
        self.assertEqual(first.entities["major_name"], "Công nghệ thông tin")

        second = analyze_question(
            "vậy có mấy chuyên ngành",
            {"current_major": "Công nghệ thông tin", "previous_intent": first.intent},
        )
        self.assertEqual(second.intent, "DANH_SACH_CHUONG_TRINH")
        self.assertEqual(second.entities["major_name"], "Công nghệ thông tin")
        self.assertEqual(second.entities["catalog_operation"], "COUNT")


class TaskGCatalogTests(unittest.TestCase):
    def test_verified_corpus_has_complete_unique_program_parent_audit(self) -> None:
        evidence = build_evidence(_fixture_chunks())
        actual = tuple(
            (relation["program_name"], relation["parent_major"])
            for relation in evidence.entity_relations
        )
        expected_counts = {
            "Quản trị kinh doanh": 5,
            "Marketing": 4,
            "Thương mại điện tử": 3,
            "Tài chính ngân hàng": 2,
            "Kế toán": 2,
            "Công nghệ tài chính": 2,
            "Kỹ thuật máy tính": 2,
            "Công nghệ thông tin": 5,
            "Ngôn ngữ Anh": 2,
            "Ngôn ngữ Nhật": 2,
            "Ngôn ngữ Trung Quốc": 4,
            "Ngôn ngữ Hàn Quốc": 2,
            "Quản trị Khách sạn": 2,
            "Quản trị Dịch vụ Du lịch & Lữ hành": 3,
            "Quản lý bệnh viện": 3,
            "Tâm lý học": 4,
        }

        self.assertEqual(len(actual), 47)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(actual, DHV_PROGRAM_PARENTS_2026)
        self.assertEqual(Counter(parent for _, parent in actual), expected_counts)
        self.assertIn(("Công nghệ tài chính", "Công nghệ tài chính"), actual)
        self.assertIn(("Quản trị khách sạn", "Quản trị Khách sạn"), actual)

    def test_cntt_list_is_filtered_to_parent_relation_and_does_not_call_llm(self) -> None:
        llm = RecordingLLM("LLM must not format a deterministic catalog")
        result = ask_chatbot(
            "Bạn có thể liệt kê những chuyên ngành của ngành công nghệ thông tin không?",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(llm.prompts), 0)
        catalog = result["trace"]["catalog"]
        self.assertTrue(catalog["deterministic"])
        self.assertEqual(catalog["requested_major"], "Công nghệ thông tin")
        self.assertEqual(catalog["program_count"], 5)
        self.assertEqual(
            {row["program_name"] for row in catalog["program_rows"]},
            {
                "Công nghệ phần mềm",
                "Lập trình AI",
                "An ninh mạng và hệ thống",
                "Truyền thông đa phương tiện",
                "Phân tích dữ liệu lớn",
            },
        )
        self.assertNotIn("Quản trị Logistics", result["answer"])
        self.assertNotIn("Hệ thống nhúng thông minh", result["answer"])

    def test_cntt_count_is_deterministic_and_exact(self) -> None:
        llm = RecordingLLM("CNTT có 4 chuyên ngành.")
        result = ask_chatbot(
            "CNTT có bao nhiêu chuyên ngành?",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(llm.prompts), 0)
        self.assertEqual(result["trace"]["catalog"]["program_count"], 5)
        self.assertIn("có 5 chương trình đào tạo", result["answer"])
        self.assertNotIn("4", result["answer"])

    def test_all_program_catalog_keeps_parent_relations(self) -> None:
        result = ask_chatbot(
            "Liệt kê tất cả chương trình đào tạo",
            retriever=_retriever(),
            llm=RecordingLLM("unused"),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["catalog"]["program_count"], len(DHV_PROGRAM_PARENTS_2026))
        for program, parent in DHV_PROGRAM_PARENTS_2026:
            self.assertIn(program, result["answer"])
            self.assertIn(f"thuộc ngành {parent}", result["answer"])

    def test_global_program_catalog_does_not_inherit_current_major(self) -> None:
        result = ask_chatbot(
            "Liệt kê tất cả chương trình đào tạo",
            retriever=_retriever(),
            llm=RecordingLLM("unused"),
            conversation_state={
                "current_major": "Công nghệ thông tin",
                "previous_intent": "HOI_NGANH",
            },
        )

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["trace"]["entities"]["major_name"])
        self.assertIsNone(result["trace"]["catalog"]["requested_major"])
        self.assertEqual(result["trace"]["catalog"]["program_count"], 47)
        self.assertIn("Quản trị Logistics", result["answer"])
        self.assertIn("Công nghệ phần mềm", result["answer"])

    def test_twenty_major_catalog_regression_remains_intact(self) -> None:
        result = ask_chatbot(
            "Liệt kê tất cả các ngành của trường",
            retriever=_retriever(),
            llm=RecordingLLM("unused"),
        )
        rows = [line for line in result["answer"].splitlines() if line[:1].isdigit()]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(rows), 20)
        self.assertNotIn("thuộc ngành", result["answer"])

    def test_followup_uses_current_major_and_returns_only_its_programs(self) -> None:
        first = ask_chatbot(
            "Tôi đang tìm hiểu Công nghệ thông tin",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )
        second = ask_chatbot(
            "vậy có mấy chuyên ngành",
            retriever=_retriever(),
            llm=RecordingLLM("unused"),
            conversation_state=first["conversation_state"],
        )

        self.assertEqual(first["state"]["current_major"], "Công nghệ thông tin")
        self.assertEqual(second["trace"]["entities"]["major_name"], "Công nghệ thông tin")
        self.assertEqual(second["trace"]["catalog"]["program_count"], 5)
        self.assertNotIn("Quản trị Logistics", second["answer"])
        self.assertNotIn("Hệ thống nhúng thông minh", second["answer"])

    def test_followup_list_uses_current_major_and_returns_only_its_programs(self) -> None:
        first = ask_chatbot(
            "Tôi đang tìm hiểu Công nghệ thông tin",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )
        second = ask_chatbot(
            "gồm những chuyên ngành nào?",
            retriever=_retriever(),
            llm=RecordingLLM("unused"),
            conversation_state=first["conversation_state"],
        )

        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["trace"]["catalog"]["operation"], "LIST")
        self.assertEqual(second["trace"]["catalog"]["program_count"], 5)
        self.assertIn("Truyền thông đa phương tiện", second["answer"])
        self.assertNotIn("Quản trị Logistics", second["answer"])
        self.assertNotIn("Hệ thống nhúng thông minh", second["answer"])

    def test_program_relation_question_still_uses_evidence_parent(self) -> None:
        result = ask_chatbot(
            "Truyền thông đa phương tiện thuộc ngành nào?",
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("Truyền thông đa phương tiện", result["answer"])
        self.assertIn("Công nghệ thông tin", result["answer"])


class TaskGValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = build_evidence(_fixture_chunks())

    def test_validator_rejects_wrong_catalog_count(self) -> None:
        analysis = analyze_question("Công nghệ thông tin có mấy chuyên ngành?")
        result = validate_model_answer(
            "Công nghệ thông tin có 4 chương trình đào tạo.",
            self.evidence,
            question=analysis.question,
            analysis=analysis,
        )
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "program_catalog_count_mismatch")

    def test_validator_rejects_program_from_a_different_parent(self) -> None:
        analysis = analyze_question("CNTT gồm những chuyên ngành nào?")
        result = validate_model_answer(
            "Hệ thống nhúng thông minh — thuộc ngành Công nghệ thông tin.",
            self.evidence,
            question=analysis.question,
            analysis=analysis,
        )
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["_validation_reason"], "program_catalog_parent_mismatch")


if __name__ == "__main__":
    unittest.main()
