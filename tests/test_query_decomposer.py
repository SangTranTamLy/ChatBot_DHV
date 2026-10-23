"""Safety and routing tests for the optional pre-RAG query decomposer."""

from __future__ import annotations

import json
import unittest

from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.query_decomposer import (
    build_query_decomposition_prompt,
    decompose_question,
    should_attempt_decomposition,
)
from src.chatbot.rag_chain import ask_chatbot
from src.prompts.rag_prompt import build_rag_prompt


COMPOUND_QUESTION = "Em muốn biết cách đăng ký tuyển sinh DHV và học phí năm 2026."
VERBATIM_PARTS = (
    "Em muốn biết cách đăng ký tuyển sinh DHV",
    "học phí năm 2026",
)


class _PlannerLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class QueryDecomposerTests(unittest.TestCase):
    def test_parser_accepts_ordered_verbatim_spans_and_rejects_rewrites(self) -> None:
        valid = _PlannerLLM(json.dumps({"parts": VERBATIM_PARTS}, ensure_ascii=False))
        result = decompose_question(COMPOUND_QUESTION, valid)
        self.assertTrue(result.accepted)
        self.assertEqual(result.parts, VERBATIM_PARTS)

        rewritten = _PlannerLLM(
            json.dumps(
                {"parts": ["thủ tục đăng ký tuyển sinh DHV", "học phí năm 2026"]},
                ensure_ascii=False,
            )
        )
        self.assertEqual(
            decompose_question(COMPOUND_QUESTION, rewritten).reason,
            "part_not_verbatim",
        )

    def test_parser_rejects_omitted_content_reordered_parts_and_single_issue(self) -> None:
        omitted = _PlannerLLM(
            json.dumps({"parts": ["Em muốn biết", "học phí năm 2026"]}, ensure_ascii=False)
        )
        self.assertEqual(
            decompose_question(COMPOUND_QUESTION, omitted).reason,
            "question_content_omitted",
        )

        reordered = _PlannerLLM(
            json.dumps({"parts": list(reversed(VERBATIM_PARTS))}, ensure_ascii=False)
        )
        self.assertEqual(
            decompose_question(COMPOUND_QUESTION, reordered).reason,
            "order_changed",
        )

        single = _PlannerLLM('{"parts": []}')
        self.assertEqual(decompose_question(COMPOUND_QUESTION, single).reason, "not_compound")

    def test_decomposition_is_only_eligible_for_unplanned_complex_in_scope_queries(self) -> None:
        compound = analyze_question(COMPOUND_QUESTION)
        compound_plan = route_question(compound)
        self.assertEqual(compound.intent, "HOI_DANG_KY_XET_TUYEN")
        self.assertFalse(compound_plan.subplans)
        self.assertTrue(should_attempt_decomposition(compound, compound_plan))

        simple = analyze_question("Điểm chuẩn CNTT?")
        self.assertFalse(should_attempt_decomposition(simple, route_question(simple)))

        advisory = analyze_question("Học lực của em không giỏi, nên chọn ngành nào?")
        self.assertFalse(should_attempt_decomposition(advisory, route_question(advisory)))

    def test_natural_admission_method_phrasings_are_in_scope_and_listable(self) -> None:
        for question in (
            "Trường mình có những hình thức tuyển sinh nào?",
            "DHV có những cách tuyển sinh nào?",
        ):
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis)
                self.assertEqual(analysis.intent, "HOI_PHUONG_THUC_XET_TUYEN")
                self.assertEqual(plan.categories, ("phuong_thuc_xet_tuyen",))
                self.assertEqual(plan.query_mode, "LIST")

    def test_method_and_tuition_question_keeps_both_issues_in_order(self) -> None:
        analysis = analyze_question("DHV tuyển sinh như thế nào, học phí có cao không?")
        plan = route_question(analysis)

        self.assertEqual(analysis.intent, "MULTI_ISSUE")
        self.assertEqual(
            [subplan.intent for subplan in plan.subplans],
            ["HOI_PHUONG_THUC_XET_TUYEN", "HOI_HOC_PHI"],
        )

    def test_comma_separated_natural_compound_reaches_pre_rag_llm(self) -> None:
        question = "Em quan tâm ngành Luật, mức học phí mỗi tín chỉ ra sao?"
        parts = (
            "Em quan tâm ngành Luật",
            "mức học phí mỗi tín chỉ ra sao",
        )
        analysis = analyze_question(question)
        plan = route_question(analysis)

        self.assertFalse(plan.subplans)
        self.assertTrue(should_attempt_decomposition(analysis, plan))
        self.assertIn("chỉ ngăn bằng dấu phẩy", build_query_decomposition_prompt(question))
        planner = _PlannerLLM(json.dumps({"parts": parts}, ensure_ascii=False))

        class EmptyRetriever:
            def __init__(self) -> None:
                self.calls: list[tuple[str, ...]] = []

            def retrieve_with_audit(
                self,
                question: str,
                *,
                categories: tuple[str, ...],
                **_: object,
            ) -> dict[str, object]:
                self.calls.append(categories)
                return {"documents": []}

        retriever = EmptyRetriever()
        result = ask_chatbot(question, retriever=retriever, query_planner=planner)

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(len(planner.prompts), 1)
        self.assertEqual(len(retriever.calls), 2)
        self.assertEqual(
            [subplan["intent"] for subplan in result["trace"]["multi_issue"]["subplans"]],
            ["HOI_NGANH", "HOI_HOC_PHI"],
        )

    def test_runtime_decomposes_before_two_independent_retrievals_and_traces_them(self) -> None:
        class EmptyRetriever:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def retrieve_with_audit(
                self,
                question: str,
                *,
                categories: tuple[str, ...],
                retrieval_query: str,
                **_: object,
            ) -> dict[str, object]:
                self.calls.append(
                    {"question": question, "categories": categories, "query": retrieval_query}
                )
                return {"documents": []}

        llm = _PlannerLLM(json.dumps({"parts": VERBATIM_PARTS}, ensure_ascii=False))
        retriever = EmptyRetriever()
        result = ask_chatbot(COMPOUND_QUESTION, retriever=retriever, query_planner=llm)

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(len(llm.prompts), 1, "empty evidence must not trigger answer generation")
        self.assertIn("chỉ phân đoạn câu hỏi", llm.prompts[0].casefold())
        self.assertEqual(len(retriever.calls), 2)
        self.assertEqual(
            [call["categories"] for call in retriever.calls],
            [
                ("dang_ky_xet_tuyen", "phuong_thuc_xet_tuyen"),
                ("hoc_phi",),
            ],
        )
        trace = result["trace"]
        self.assertEqual(trace["intent"], "MULTI_ISSUE")
        self.assertEqual(trace["retrieval_calls"], 2)
        self.assertEqual(trace["evidence_count"], 0)
        self.assertEqual(
            trace["pre_rag_decomposition"]["status"],
            "accepted",
        )
        self.assertEqual(
            trace["multi_issue"]["subplans"][0]["intent"],
            "HOI_DANG_KY_XET_TUYEN",
        )
        self.assertEqual(
            trace["multi_issue"]["subplans"][1]["intent"],
            "HOI_HOC_PHI",
        )

    def test_security_boundary_and_simple_question_never_call_pre_rag_model(self) -> None:
        class NeverCalled:
            def generate(self, *_: object, **__: object) -> str:
                raise AssertionError("blocked/simple input must not invoke the planner")

        class CountingRetriever:
            def __init__(self) -> None:
                self.calls = 0

            def retrieve_with_audit(self, *_: object, **__: object) -> dict[str, object]:
                self.calls += 1
                return {"documents": []}

        external_retriever = CountingRetriever()
        external = ask_chatbot(
            "Điểm chuẩn Văn Hiến?",
            retriever=external_retriever,
            llm=NeverCalled(),
        )
        self.assertEqual(external["status"], "out_of_scope")
        self.assertEqual(external_retriever.calls, 0)

        simple_retriever = CountingRetriever()
        simple = ask_chatbot(
            "Điểm chuẩn CNTT?",
            retriever=simple_retriever,
            llm=NeverCalled(),
        )
        self.assertEqual(simple["status"], "no_data")
        self.assertEqual(simple_retriever.calls, 1)

    def test_answer_prompt_requires_complete_evidence_bounded_multi_issue_response(self) -> None:
        prompt = build_rag_prompt(
            "Học phí và học bổng DHV là gì?",
            "Evidence chỉ có học phí DHV 2026.",
            intent="MULTI_ISSUE",
        )
        self.assertIn("không bỏ sót ý độc lập nào", prompt)
        self.assertIn("không dùng evidence của một ý để suy ra ý khác", prompt)
        self.assertIn("nói rõ phần còn thiếu bằng lời tự nhiên", prompt)
        self.assertIn("Không tạo, đoán hoặc chép URL/markdown link", prompt)
        self.assertIn("Không thêm thông tin quảng bá", prompt)


if __name__ == "__main__":
    unittest.main()
