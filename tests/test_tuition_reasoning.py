from __future__ import annotations

import unittest

from evaluation.run_evaluation import _retriever
from src.chatbot.chat_service import ChatService
from src.chatbot.evidence import EvidenceBundle, EvidenceChunk
from src.chatbot.history_context import resolve_history_question
from src.chatbot.query_analysis import analyze_question
from src.chatbot.query_semantics import analyze_fee_request
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.tuition_formatters import answer_fee_request
from src.config.settings import settings


class FeeRequestAnalysisTests(unittest.TestCase):
    def test_scope_and_topics_are_parsed_without_calculating_amounts(self) -> None:
        cases = (
            ("Học phí ngành CNTT bao nhiêu?", "per_credit", {"tuition"}),
            ("Học phí học kỳ I là bao nhiêu và tương ứng bao nhiêu tín chỉ?", "semester", {"tuition"}),
            ("Ngoài học phí còn khoản nào?", "semester", {"other_fees"}),
            ("Học phí trung bình theo năm?", "annual", {"tuition"}),
            ("Học phí HKI bao nhiêu, ngoài ra có những khoản thu nào và tổng cộng bao nhiêu?", "semester",
             {"tuition", "other_fees", "total"}),
        )
        for question, expected_scope, expected_topics in cases:
            with self.subTest(question=question):
                request = analyze_fee_request(question)
                self.assertTrue(request.is_fee_request)
                self.assertEqual(request.scope, expected_scope)
                self.assertTrue(expected_topics.issubset(request.topics))

        analysis = analyze_question("Học phí 10 tín chỉ bao nhiêu?")
        self.assertEqual(analysis.primary_intent, "HOI_HOC_PHI")
        self.assertEqual(analysis.requested_scope, "per_credit")
        self.assertEqual(analysis.requested_detail["credits"], 10)
        self.assertFalse(analysis.is_follow_up)

    def test_conditional_english_and_credit_count_are_explicit(self) -> None:
        without_test = analyze_fee_request("Tổng học phí HKI nếu không kiểm tra tiếng Anh")
        with_test = analyze_fee_request("Nếu có kiểm tra tiếng Anh thì tổng các khoản là bao nhiêu?")
        credits = analyze_fee_request("10 tín chỉ thì học phí bao nhiêu?")
        self.assertEqual(without_test.optional_english, "exclude")
        self.assertEqual(with_test.optional_english, "include")
        self.assertEqual(credits.scope, "per_credit")
        self.assertEqual(credits.credits, 10)

    def test_independent_school_term_question_is_not_a_fee_request(self) -> None:
        self.assertFalse(analyze_fee_request("Học kỳ I có bao nhiêu học phần?").is_fee_request)

    def test_generic_scholarship_request_is_marked_ambiguous(self) -> None:
        request = analyze_fee_request("Học phí CNTT bao nhiêu, có học bổng không?")
        self.assertIn("scholarship", request.topics)
        self.assertIn("scholarship", request.ambiguous_topics)

    def test_partial_fee_answer_names_the_missing_table_row(self) -> None:
        question = "Phí nhập học và phí kiểm tra năng lực tiếng Anh bao nhiêu?"
        metadata = {
            "record_type": "page_text", "category": "hoc_phi", "status": "verified",
            "school_code": "DHV", "year": 2026, "source_url": "https://dhv.edu.vn/",
        }
        evidence = EvidenceBundle(
            chunks=(EvidenceChunk(
                text="Kiểm tra năng lực Tiếng Anh (nếu có)\n250.000 đồng",
                metadata=metadata,
            ),),
            context="Kiểm tra năng lực Tiếng Anh (nếu có)\n250.000 đồng",
            sources=({"url": "https://dhv.edu.vn/"},),
        )
        result = answer_fee_request(
            analyze_question(question), evidence, analyze_fee_request(question)
        )
        self.assertIsNotNone(result)
        self.assertIn("250.000 đồng", result["answer"])
        self.assertIn("chưa có số tiền cho Phí nhập học", result["answer"])
        self.assertIn("enrollment_fee", result["missing_topics"])


class FeeHistoryResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.history = (
            {"role": "user", "content": "Học phí ngành CNTT bao nhiêu?"},
            {"role": "assistant", "content": "Học phí theo tín chỉ: 1.250.000 đồng/tín chỉ."},
        )

    def test_total_followup_inherits_fee_topic_and_semester(self) -> None:
        result = resolve_history_question("Vậy tổng là bao nhiêu?", self.history, settings_obj=settings)
        self.assertEqual(result.method, "fee_history_resolution")
        self.assertIn("Tổng các khoản thu học kỳ", result.question)

    def test_other_fees_followup_keeps_the_fee_topic(self) -> None:
        result = resolve_history_question("Nếu thêm các khoản khác thì sao?", self.history, settings_obj=settings)
        self.assertEqual(result.method, "fee_history_resolution")
        self.assertIn("Ngoài học phí", result.question)
        self.assertIn("khoản thu nào", result.question)

    def test_conditional_test_followup_preserves_negation(self) -> None:
        result = resolve_history_question("Nếu không kiểm tra tiếng Anh thì sao?", self.history,
                                          settings_obj=settings)
        self.assertEqual(result.method, "fee_history_resolution")
        self.assertIn("không gồm phí kiểm tra năng lực tiếng Anh", result.question)

    def test_new_topic_does_not_inherit_tuition_history(self) -> None:
        result = resolve_history_question("Vậy học bổng đầu vào thế nào?", self.history, settings_obj=settings)
        self.assertEqual(result.method, "independent_question")
        self.assertEqual(result.question, "Vậy học bổng đầu vào thế nào?")


class FeeConversationRegressionTests(unittest.TestCase):
    def test_optional_english_total_is_in_scope_and_includes_the_conditional_fee(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("verified fee-table answers should not need generation")

        question = "Nếu có kiểm tra tiếng Anh thì tổng bao nhiêu?"
        result = ChatService(retriever=_retriever(), llm=NeverGenerate()).ask(question)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["trace"]["scope"]["in_scope"])
        self.assertIn("14.500.000", result["answer"])
        self.assertEqual(result["trace"]["fee_coverage"]["missing_topics"], [])

    def test_tuition_and_scholarship_conditions_remain_two_independent_issues(self) -> None:
        from src.chatbot.query_analysis import route_question

        question = "Học phí ngành CNTT bao nhiêu, có học bổng không và điều kiện là gì?"
        analysis = analyze_question(question)
        plan = route_question(analysis)

        self.assertEqual(analysis.intent, "MULTI_ISSUE")
        self.assertEqual(analysis.primary_intent, "MULTI_ISSUE")
        self.assertEqual(analysis.sub_intents, ("HOI_HOC_PHI", "HOI_HOC_BONG"))
        self.assertEqual(analysis.requested_scope, "per_credit")
        self.assertEqual(analysis.requested_detail["topics"], ["tuition", "scholarship"])
        self.assertEqual(
            [subplan.intent for subplan in plan.subplans],
            ["HOI_HOC_PHI", "HOI_HOC_BONG"],
        )

        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("deterministic evidence answers should not need generation")

        result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["trace"]["multi_issue"]["complete"])
        self.assertIn("1.250.000 đồng/tín chỉ", result["answer"])
        self.assertIn("điều kiện", result["answer"].casefold())
        tuition_issue = next(
            issue for issue in result["trace"]["multi_issue"]["issues"]
            if issue["intent"] == "HOI_HOC_PHI"
        )
        self.assertEqual(tuition_issue["fee_coverage"]["missing_topics"], [])

    def test_fee_separation_and_semester_total_are_both_answered(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("verified fee-table answers should not need generation")

        question = "Phí học liệu có thu riêng không, nếu có thì tổng học kỳ là bao nhiêu?"
        request = analyze_fee_request(question)
        self.assertEqual(request.relationship, "separate")
        self.assertIn("learning_materials", request.fee_items)
        result = ask_chatbot(question, retriever=_retriever(), llm=NeverGenerate())

        self.assertEqual(result["status"], "ok")
        self.assertRegex(result["answer"], r"(?i)Có.*khoản riêng ngoài học phí")
        self.assertIn("14.250.000", result["answer"])
        self.assertIn("14.500.000", result["answer"])

    def test_standalone_hki_amount_question_routes_to_fee_table(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("verified fee-table answers should not need generation")

        result = ChatService(retriever=_retriever(), llm=NeverGenerate()).ask("Học kỳ I đóng bao nhiêu?")
        self.assertEqual(result["status"], "ok")
        self.assertIn("12.500.000", result["answer"])
        self.assertEqual(result["trace"]["intent"], "HOI_HOC_PHI")
        self.assertTrue(any(hit.get("category") == "hoc_phi" for hit in result["trace"]["retrieval"]["hits"]))

    def test_tuition_conversation_keeps_hki_context_and_totals(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("verified fee-table answers should not need generation")

        service = ChatService(retriever=_retriever(), llm=NeverGenerate())
        state = None
        history: list[dict[str, str]] = []
        questions = (
            "Học phí ngành CNTT bao nhiêu?",
            "Vậy học kỳ I đóng bao nhiêu?",
            "Nếu thêm các khoản khác thì sao?",
            "Vậy tổng là bao nhiêu?",
            "Nếu không kiểm tra tiếng Anh thì sao?",
        )
        results = []
        for question in questions:
            result = service.ask(question, conversation_state=state, conversation_history=history)
            self.assertEqual(result["status"], "ok", msg=result.get("answer"))
            results.append(result)
            state = result.get("state", state)
            history.extend((
                {"role": "user", "content": question},
                {"role": "assistant", "content": str(result.get("answer", ""))},
            ))

        self.assertIn("1.250.000 đồng/tín chỉ", results[0]["answer"])
        self.assertIn("12.500.000", results[1]["answer"])
        self.assertIn("10 tín chỉ", results[1]["answer"])
        for amount in ("12.500.000", "1.500.000", "250.000"):
            self.assertIn(amount, results[2]["answer"])
        self.assertIn("14.250.000", results[3]["answer"])
        self.assertIn("14.500.000", results[3]["answer"])
        self.assertIn("14.250.000", results[4]["answer"])
        self.assertNotIn("14.500.000", results[4]["answer"])
        self.assertTrue(results[1]["trace"]["is_follow_up"])

        for result in results[1:]:
            self.assertEqual(result["trace"]["history_resolution"]["method"], "fee_history_resolution")
            self.assertEqual(result["trace"]["intent"], "HOI_HOC_PHI")
            self.assertTrue(any(hit.get("category") == "hoc_phi" for hit in result["trace"]["retrieval"]["hits"]))
            self.assertEqual(result["trace"]["fee_coverage"]["missing_topics"], [])

    def test_same_followup_phrase_after_document_exchange_remains_independent(self) -> None:
        history = (
            {"role": "user", "content": "Hồ sơ nhập học cần gì?"},
            {"role": "assistant", "content": "Cần học bạ và căn cước."},
        )
        result = resolve_history_question("Vậy tổng là bao nhiêu?", history, settings_obj=settings)
        self.assertEqual(result.method, "independent_question")


if __name__ == "__main__":
    unittest.main()
