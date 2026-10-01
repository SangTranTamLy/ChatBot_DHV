"""Regression tests for the trained intent model and the scope boundary."""

from __future__ import annotations

import unittest

from langchain_core.documents import Document

from src.chatbot.intent_classifier import (
    DEFAULT_MODEL_PATH,
    DEFAULT_TEST_PATH,
    DEFAULT_TRAIN_PATH,
    load_model,
    load_records,
)
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import INTENTS, analyze_question
from src.chatbot.scope_guard import is_in_scope, is_personal_life_advice
from src.chatbot.evidence import build_evidence
from src.chatbot.output_validator import (
    EXTERNAL_SCHOOL_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    validate_model_answer,
)
from src.models.local_llm import OllamaError


class NeverCalledRetriever:
    def __init__(self) -> None:
        self.called = False

    def retrieve(self, question: str) -> list[Document]:
        self.called = True
        raise AssertionError("out-of-scope questions must not retrieve documents")


class NeverCalledLLM:
    def __init__(self) -> None:
        self.called = False

    def generate(self, prompt: str) -> str:
        self.called = True
        raise AssertionError("out-of-scope questions must not call the LLM")


class OneDocumentRetriever:
    def retrieve(self, question: str) -> list[Document]:
        return [
            Document(
                page_content="Học phí: 12.500.000 đồng/học kỳ.",
                metadata={
                    "category": "hoc_phi",
                    "year": 2026,
                    "school_code": "DHV",
                    "source_url": "https://dhv.edu.vn/verified",
                    "status": "verified",
                    "chunk_id": "empty-answer-1",
                },
            )
        ]


class AdvisoryRetriever:
    def __init__(self) -> None:
        self.called = False

    def retrieve(self, question: str) -> list[Document]:
        self.called = True
        return [
            Document(
                page_content=(
                    "Công nghệ thông tin\n"
                    "7480201\n"
                    "Truyền thông đa phương tiện; Công nghệ phần mềm\n"
                    "15\n15\n600\n"
                    "Ngôn ngữ Trung Quốc\n"
                    "7220204\n"
                    "Tiếng Trung thương mại\n"
                    "15\n15\n600"
                ),
                metadata={
                    "category": "nganh_dao_tao",
                    "year": 2026,
                    "school_code": "DHV",
                    "source_url": "https://dhv.edu.vn/verified-major-catalog",
                    "status": "verified",
                    "chunk_id": "advisory-major-catalog-1",
                },
            )
        ]


class AdvisoryLLM:
    def __init__(self) -> None:
        self.called = False

    def generate(self, prompt: str) -> str:
        self.called = True
        return (
            "Bạn đang cân nhắc hai hướng. Truyền thông đa phương tiện là chương trình "
            "thuộc ngành Công nghệ thông tin. Ngôn ngữ Trung Quốc là một ngành khác "
            "trong dữ liệu DHV. Nếu bạn thích chỉnh sửa video, mình nghiêng về "
            "Truyền thông đa phương tiện hơn; bạn muốn so sánh sâu hơn không?"
        )


class WebsiteRetriever:
    def __init__(self) -> None:
        self.called = False

    def retrieve(self, question: str) -> list[Document]:
        self.called = True
        return [
            Document(
                page_content="Nguồn chính thức DHV và tổng đài tư vấn tuyển sinh.",
                metadata={
                    "title": "Cơ sở và liên hệ tuyển sinh DHV",
                    "category": "co_so_lien_he",
                    "year": 2026,
                    "school_code": "DHV",
                    "source_url": "https://dhv.edu.vn/tuyen-sinh",
                    "status": "verified",
                    "chunk_id": "website-link-1",
                },
            )
        ]


class EmptyAnswerLLM:
    def generate(self, prompt: str) -> str:
        raise OllamaError("Ollama returned an empty response")


class IntentDatasetTests(unittest.TestCase):
    def test_model_is_trained_from_a_reproducible_80_20_split(self) -> None:
        train = load_records(DEFAULT_TRAIN_PATH)
        test = load_records(DEFAULT_TEST_PATH)
        train_ids = {row["id"] for row in train}
        test_ids = {row["id"] for row in test}

        self.assertTrue(DEFAULT_MODEL_PATH.exists())
        self.assertEqual(len(train), 144)
        self.assertEqual(len(test), 36)
        self.assertEqual(len(train) / (len(train) + len(test)), 0.8)
        self.assertEqual(train_ids & test_ids, set())
        self.assertEqual({row["intent"] for row in train} | {row["intent"] for row in test}, set(INTENTS))

    def test_holdout_accuracy_is_at_least_80_percent(self) -> None:
        model = load_model()
        test = load_records(DEFAULT_TEST_PATH)
        correct = sum(
            model.predict(row["text"]) is not None
            and model.predict(row["text"]).intent == row["intent"]
            for row in test
        )

        self.assertGreaterEqual(correct / len(test), 0.80)

    def test_query_analysis_exposes_the_trained_model_source(self) -> None:
        analysis = analyze_question("Thời tiết hôm nay thế nào?")

        self.assertEqual(analysis.intent, "OUT_OF_SCOPE")
        self.assertIn("trained", analysis.intent_source)
        self.assertIsNotNone(analysis.intent_confidence)


class ScopeRegressionTests(unittest.TestCase):
    def test_foreign_institution_questions_are_out_of_scope(self) -> None:
        for question in (
            "Điểm chuẩn Đại học Quốc gia Hà Nội năm 2026 là bao nhiêu?",
            "Học phí Đại học FPT bao nhiêu?",
            "Điểm chuẩn của trường đại học Sài Gòn?",
            "Điểm chuẩn ngành Công nghệ thông tin của trường đại học quốc gia TP.HCM?",
            "Điểm chuẩn trường Văn Hiến?",
            "Điểm chuẩn Văn Hiến?",
            "Điểm chuẩn ĐH Văn Hiến?",
            "Điểm trúng tuyển trường khác năm nay thế nào?",
        ):
            with self.subTest(question=question):
                self.assertFalse(is_in_scope(question))
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], "OTHER_SCHOOL")
                self.assertEqual(analysis.entities["scope_reason"], "external_school")
                self.assertNotEqual(analysis.intent, "OUT_OF_SCOPE")

    def test_foreign_institution_is_rejected_before_retrieval(self) -> None:
        for question in (
            "Điểm chuẩn của trường đại học Sài Gòn?",
            "Điểm chuẩn trường Văn Hiến?",
        ):
            with self.subTest(question=question):
                retriever = NeverCalledRetriever()
                llm = NeverCalledLLM()

                result = ask_chatbot(question, retriever=retriever, llm=llm)

                self.assertEqual(result["status"], "out_of_scope")
                self.assertEqual(result["answer"], EXTERNAL_SCHOOL_ANSWER)
                self.assertFalse(retriever.called)
                self.assertFalse(llm.called)

    def test_external_score_source_for_dhv_remains_in_scope(self) -> None:
        question = "ĐGNL ĐHQG-HCM của DHV cần bao nhiêu điểm?"

        self.assertTrue(is_in_scope(question))
        self.assertNotEqual(analyze_question(question).intent, "OUT_OF_SCOPE")

    def test_target_school_contract_distinguishes_dhv_unspecified_mixed_and_ambiguous(self) -> None:
        cases = (
            ("Điểm chuẩn DHV CNTT 2026 bao nhiêu?", "DHV", "in_scope_dhv"),
            ("Điểm chuẩn CNTT 2026 bao nhiêu?", "UNSPECIFIED", "in_scope_dhv"),
            ("So sánh điểm chuẩn DHV và Văn Hiến", "MIXED", "mixed_school"),
            ("Điểm chuẩn Đại học Hùng Vương bao nhiêu?", "AMBIGUOUS", "ambiguous_school"),
        )
        for question, target_school, reason in cases:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                self.assertEqual(analysis.entities["target_school"], target_school)
                self.assertEqual(analysis.entities["scope_reason"], reason)

    def test_external_school_followup_keeps_external_scope_without_retrieval(self) -> None:
        first_retriever = NeverCalledRetriever()
        first_llm = NeverCalledLLM()
        first = ask_chatbot(
            "Văn Hiến có xét học bạ không?",
            retriever=first_retriever,
            llm=first_llm,
        )
        self.assertEqual(first["trace"]["scope"]["target_school"], "OTHER_SCHOOL")
        self.assertEqual(first["conversation_state"]["current_school"], "OTHER_SCHOOL")

        second_retriever = NeverCalledRetriever()
        second_llm = NeverCalledLLM()
        second = ask_chatbot(
            "Còn điểm chuẩn?",
            retriever=second_retriever,
            llm=second_llm,
            conversation_state=first["conversation_state"],
        )

        self.assertEqual(second["status"], "out_of_scope")
        self.assertEqual(second["scope_reason"], "external_school")
        self.assertEqual(second["trace"]["retrieved_docs_count"], 0)
        self.assertFalse(second_retriever.called)
        self.assertFalse(second_llm.called)

    def test_explicit_dhv_switch_overrides_external_school_state(self) -> None:
        first = ask_chatbot(
            "Văn Hiến có xét học bạ không?",
            retriever=NeverCalledRetriever(),
            llm=NeverCalledLLM(),
        )
        dhv_retriever = AdvisoryRetriever()
        second = ask_chatbot(
            "Còn DHV thì sao?",
            retriever=dhv_retriever,
            llm=NeverCalledLLM(),
            conversation_state=first["conversation_state"],
        )

        self.assertEqual(second["trace"]["scope"]["target_school"], "DHV")
        self.assertTrue(dhv_retriever.called)

    def test_mixed_school_question_stops_before_retrieval(self) -> None:
        retriever = NeverCalledRetriever()
        llm = NeverCalledLLM()

        result = ask_chatbot(
            "So sánh điểm chuẩn DHV và Văn Hiến",
            retriever=retriever,
            llm=llm,
        )

        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["scope_reason"], "mixed_school")
        self.assertEqual(result["target_school"], "MIXED")
        self.assertEqual(result["trace"]["retrieved_docs_count"], 0)
        self.assertFalse(retriever.called)
        self.assertFalse(llm.called)

    def test_generic_school_reference_is_not_mistaken_for_another_school(self) -> None:
        for question in (
            "Trường có xét học bạ không?",
            "Điểm chuẩn trường nào năm 2026?",
        ):
            with self.subTest(question=question):
                self.assertTrue(is_in_scope(question))

        ambiguous = analyze_question("Điểm chuẩn trường Hùng Vương năm 2026?")
        self.assertEqual(ambiguous.entities["target_school"], "AMBIGUOUS")
        self.assertEqual(ambiguous.entities["scope_reason"], "ambiguous_school")

    def test_major_passion_dilemma_is_dynamic_admissions_advice(self) -> None:
        question = (
            "Tôi đang phân vân giữa Truyền thông đa phương tiện và Ngôn ngữ Trung "
            "nhưng tôi có chút đam mê chỉnh sửa video, tôi không biết nên đi theo "
            "đam mê hay theo ngành mình không đam mê, bạn có thể tư vấn tôi không?"
        )
        retriever = AdvisoryRetriever()
        llm = AdvisoryLLM()

        self.assertTrue(is_personal_life_advice(question))
        self.assertFalse(is_in_scope(question))
        self.assertTrue(is_in_scope(question, has_admissions_entity=True))
        analysis = analyze_question(question)
        self.assertEqual(analysis.intent, "TU_VAN_CHON_NGANH")
        self.assertEqual(analysis.entities["interest"], "chinh sua video")

        result = ask_chatbot(question, retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "ok")
        self.assertIn("Truyền thông đa phương tiện", result["answer"])
        self.assertIn("Ngôn ngữ Trung Quốc", result["answer"])
        self.assertTrue(retriever.called)
        self.assertTrue(llm.called)

    def test_website_request_returns_verified_url_without_fabricating_one(self) -> None:
        retriever = WebsiteRetriever()
        llm = NeverCalledLLM()

        analysis = analyze_question("web tuyển sinh DHV")
        self.assertEqual(analysis.intent, "HOI_CO_SO_LIEN_HE")
        self.assertEqual(analysis.entities["requested_information"], ["official_website"])

        result = ask_chatbot("web tuyển sinh DHV", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "ok")
        self.assertIn("https://dhv.edu.vn/tuyen-sinh", result["answer"])
        self.assertEqual(
            result["sources"],
            [{"title": "Cơ sở và liên hệ tuyển sinh DHV", "url": "https://dhv.edu.vn/tuyen-sinh"}],
        )
        self.assertTrue(retriever.called)
        self.assertFalse(llm.called)

    def test_simple_passion_based_major_advice_stays_in_scope(self) -> None:
        question = "Tôi đam mê công nghệ, không biết nên chọn ngành nào?"

        self.assertFalse(is_personal_life_advice(question))
        self.assertTrue(is_in_scope(question))
        self.assertEqual(analyze_question(question).intent, "TU_VAN_CHON_NGANH")

    def test_broad_admissions_words_cannot_reopen_an_out_of_scope_turn(self) -> None:
        question = "Thời tiết tuyển sinh ngành hôm nay thế nào?"
        retriever = NeverCalledRetriever()
        llm = NeverCalledLLM()

        # The legacy keyword guard sees both broad words, so this reproduces
        # the original failure mode directly.
        self.assertTrue(is_in_scope(question))
        result = ask_chatbot(question, retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["trace"]["intent"], "OUT_OF_SCOPE")
        self.assertFalse(retriever.called)
        self.assertFalse(llm.called)

    def test_model_saying_it_does_not_know_becomes_no_data(self) -> None:
        evidence = build_evidence(
            [
                Document(
                    page_content="Học phí: 12.500.000 đồng/học kỳ.",
                    metadata={
                        "category": "hoc_phi",
                        "year": 2026,
                        "school_code": "DHV",
                        "source_url": "https://dhv.edu.vn/verified",
                        "status": "verified",
                        "chunk_id": "fallback-1",
                    },
                )
            ]
        )

        result = validate_model_answer(
            "Tôi không biết thông tin học phí DHV.",
            evidence,
            question="Học phí DHV 2026?",
        )

        self.assertEqual(result["status"], "no_data")
        self.assertIn("chưa tìm thấy", result["answer"])

    def test_empty_local_model_response_becomes_no_data(self) -> None:
        result = ask_chatbot(
            "Học phí DHV 2026?",
            retriever=OneDocumentRetriever(),
            llm=EmptyAnswerLLM(),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertIn("chưa tìm thấy", result["answer"])


if __name__ == "__main__":
    unittest.main()
