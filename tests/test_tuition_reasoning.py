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

    def test_explicit_year_and_semester_override_only_the_matching_history_slots(self) -> None:
        history = (
            {"role": "user", "content": "Tổng các khoản thu học kỳ I năm 2026 của DHV là bao nhiêu?"},
            {"role": "assistant", "content": "Tổng các khoản thu học kỳ I năm 2026 là 12.500.000 đồng."},
        )
        cases = (
            ("Vậy tổng học kỳ II năm 2027 là bao nhiêu?", "học kỳ II", "2027"),
            ("Vậy tổng năm 2027 là bao nhiêu?", "học kỳ I", "2027"),
            ("Vậy tổng học kỳ II là bao nhiêu?", "học kỳ II", "2026"),
            ("Vậy tổng là bao nhiêu?", "học kỳ I", "2026"),
            ("Nếu không kiểm tra tiếng Anh thì sao?", "học kỳ I", "2026"),
        )

        for question, expected_semester, expected_year in cases:
            with self.subTest(question=question):
                result = resolve_history_question(question, history, settings_obj=settings)
                self.assertEqual(result.method, "fee_history_resolution")
                self.assertIn(expected_semester, result.question)
                self.assertIn(expected_year, result.question)
                if "không kiểm tra" in question:
                    self.assertIn("không gồm phí kiểm tra năng lực tiếng Anh", result.question)

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

    def test_not_subject_to_test_followup_preserves_explicit_exclusion(self) -> None:
        history = (
            {"role": "user", "content": "Tổng chi phí học kỳ I năm 2026 bao nhiêu?"},
            {
                "role": "assistant",
                "content": (
                    "Tổng các khoản cơ bản học kỳ I năm 2026 là 14.250.000 đồng. "
                    "Nếu thuộc diện kiểm tra năng lực Tiếng Anh, thành tối đa 14.500.000 đồng."
                ),
            },
        )
        result = resolve_history_question(
            "Nếu không thuộc diện kiểm tra tiếng Anh thì tổng là bao nhiêu?",
            history,
            settings_obj=settings,
        )

        self.assertEqual(result.method, "fee_history_resolution")
        self.assertIn("học kỳ I", result.question)
        self.assertIn("2026", result.question)
        self.assertIn("không gồm phí kiểm tra năng lực tiếng Anh", result.question)

    def test_new_topic_does_not_inherit_tuition_history(self) -> None:
        result = resolve_history_question("Vậy học bổng đầu vào thế nào?", self.history, settings_obj=settings)
        self.assertEqual(result.method, "independent_question")
        self.assertEqual(result.question, "Vậy học bổng đầu vào thế nào?")


class FeeConversationRegressionTests(unittest.TestCase):
    class MisleadingFeeComposer:
        def generate(self, prompt: str) -> str:
            # All listed rows are sourced, but 14.250.000 is a subtotal that
            # excludes the conditional English test fee.
            return (
                "Học phí HKI (10 tín chỉ): 12.500.000 đồng; "
                "phí nhập học: 1.500.000 đồng; học liệu: 250.000 đồng; "
                "kiểm tra năng lực Tiếng Anh (nếu có): 250.000 đồng. "
                "Tổng cộng, bạn cần đóng 14.250.000 đồng."
            )

    def test_generic_hki_tuition_question_does_not_gain_an_unrequested_total(self) -> None:
        result = ChatService(
            retriever=_retriever(), llm=self.MisleadingFeeComposer()
        ).ask("Học phí học kỳ I đóng bao nhiêu?")

        self.assertEqual(result["status"], "ok")
        self.assertIn("12.500.000", result["answer"])
        self.assertNotIn("Tổng cộng", result["answer"])
        self.assertNotIn("14.250.000", result["answer"])

    def test_hki_followup_keeps_conditional_english_fee_out_of_tuition_total(self) -> None:
        service = ChatService(
            retriever=_retriever(), llm=self.MisleadingFeeComposer()
        )
        first_question = "Học phí ngành Công nghệ thông tin năm 2026 bao nhiêu?"
        first = service.ask(first_question)
        history = [
            {"role": "user", "content": first_question},
            {"role": "assistant", "content": str(first["answer"])},
        ]

        followup = service.ask(
            "Còn học phí học kỳ I thì sao?",
            conversation_state=first.get("state"),
            conversation_history=history,
        )

        self.assertEqual(followup["status"], "ok")
        self.assertEqual(
            followup["trace"]["history_resolution"]["method"],
            "fee_history_resolution",
        )
        self.assertIn("12.500.000", followup["answer"])
        self.assertNotIn("Tổng cộng", followup["answer"])
        self.assertNotIn("14.250.000", followup["answer"])

    def test_history_exclusion_overrides_unknown_optional_english_status(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("verified fee-table answers should not need generation")

        service = ChatService(retriever=_retriever(), llm=NeverGenerate())
        first_question = "Tổng chi phí học kỳ I năm 2026 bao nhiêu?"
        first = service.ask(first_question)
        history = [
            {"role": "user", "content": first_question},
            {"role": "assistant", "content": str(first["answer"])},
        ]
        followup = service.ask(
            "Nếu không thuộc diện kiểm tra tiếng Anh thì tổng là bao nhiêu?",
            conversation_state=first.get("state"),
            conversation_history=history,
        )

        self.assertEqual(followup["status"], "ok")
        resolution = followup["trace"]["history_resolution"]["resolved_question"]
        self.assertIn("không gồm phí kiểm tra năng lực tiếng Anh", resolution)
        self.assertEqual(followup["trace"]["fee_request"]["optional_english"], "exclude")
        self.assertIn("14.250.000", followup["answer"])
        self.assertNotIn("14.500.000", followup["answer"])

    def test_composer_cannot_add_excluded_optional_fee_after_correct_subtotal(self) -> None:
        class IncorrectlyAddsExcludedFee:
            def generate(self, prompt: str) -> str:
                return (
                    "Tổng các khoản thu học kỳ I năm 2026, không gồm phí kiểm tra tiếng Anh, "
                    "là 14.250.000 đồng + 250.000 đồng = 14.500.000 đồng."
                )

        service = ChatService(retriever=_retriever(), llm=IncorrectlyAddsExcludedFee())
        first_question = "Tổng chi phí học kỳ I năm 2026 bao nhiêu?"
        first = service.ask(first_question)
        history = [
            {"role": "user", "content": first_question},
            {"role": "assistant", "content": str(first["answer"])},
        ]
        followup = service.ask(
            "Nếu không thuộc diện kiểm tra tiếng Anh thì tổng là bao nhiêu?",
            conversation_state=first.get("state"),
            conversation_history=history,
        )

        self.assertEqual(followup["status"], "ok")
        self.assertIn("14.250.000", followup["answer"])
        self.assertNotIn("14.500.000", followup["answer"])
        self.assertEqual(followup["trace"]["response_composer"]["status"], "safe_fallback")
        self.assertEqual(
            followup["trace"]["response_composer"]["reason"],
            "optional_fee_total_mismatch",
        )

    def test_unqualified_total_keeps_base_and_conditional_fee_distinct(self) -> None:
        result = ChatService(
            retriever=_retriever(), llm=self.MisleadingFeeComposer()
        ).ask("Tổng các khoản phải đóng học kỳ I năm 2026 là bao nhiêu?")

        self.assertEqual(result["status"], "ok")
        answer = str(result["answer"])
        self.assertIn("Tổng các khoản cơ bản", answer)
        self.assertIn("14.250.000 đồng", answer)
        self.assertIn("nếu thuộc diện kiểm tra", answer.casefold())
        self.assertIn("tối đa 14.500.000 đồng", answer.casefold())

    def test_retry_instruction_echo_falls_back_without_showing_internal_prompt(self) -> None:
        class RetryInstructionEcho:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                if len(self.prompts) == 1:
                    return "Tổng cộng, bạn cần đóng 14.250.000 đồng."
                return (
                    "Bản đáp án mới: "
                    "Tổng các khoản cơ bản học kỳ I năm 2026 là 14.250.000 đồng; "
                    "Nếu thuộc diện kiểm tra năng lực Tiếng Anh, cộng thêm 250.000 đồng, "
                    "thành tối đa 14.500.000 đồng."
                )

        llm = RetryInstructionEcho()
        result = ChatService(retriever=_retriever(), llm=llm).ask(
            "Tổng chi phí học kỳ I năm 2026 bao nhiêu?"
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("BẢN ĐÁP ÁN TRƯỚC", llm.prompts[1])
        self.assertIn("CÂU TRẢ LỜI MỚI:", llm.prompts[1])
        self.assertNotIn("Bản đáp án mới:", result["answer"])
        self.assertIn("Tổng các khoản cơ bản", result["answer"])
        self.assertIn("tối đa 14.500.000 đồng", result["answer"])
        self.assertEqual(result["trace"]["response_composer"]["status"], "safe_fallback")
        self.assertEqual(result["trace"]["response_composer"]["reason"], "prompt_leak")

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

    def test_chat_service_keeps_new_semester_and_year_through_the_final_answer(self) -> None:
        class NeverGenerate:
            def generate(self, prompt: str) -> str:
                raise AssertionError("the unavailable HKII 2027 total must not be generated")

        history = (
            {"role": "user", "content": "Tổng các khoản thu học kỳ I năm 2026 của DHV là bao nhiêu?"},
            {"role": "assistant", "content": "Tổng các khoản thu học kỳ I năm 2026 là 12.500.000 đồng."},
        )
        result = ChatService(retriever=_retriever(), llm=NeverGenerate()).ask(
            "Vậy tổng học kỳ II năm 2027 là bao nhiêu?",
            conversation_history=history,
        )

        resolution = result["trace"]["history_resolution"]
        self.assertIn("học kỳ II", resolution["resolved_question"])
        self.assertIn("2027", resolution["resolved_question"])
        self.assertEqual(result["status"], "no_data")
        self.assertNotIn("12.500.000", result["answer"])
        self.assertNotIn("học kỳ I", result["answer"])
        self.assertNotIn("2026", result["answer"])

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
