"""Regressions found by a first-time candidate session (follow-ups, teencode, formatting)."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from evaluation.run_evaluation import _retriever
from src.chatbot.query_analysis import ConversationState, analyze_question
from src.chatbot import rag_chain
from src.chatbot.catalog_formatters import _catalog_existence_answer
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.supplement_faq import _entries, lookup_supplement
from src.config.settings import settings


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("these answers must come from verified evidence")


class MajorSwitchFollowUpTests(unittest.TestCase):
    def test_short_major_switch_keeps_previous_topic(self) -> None:
        for previous_intent in ("HOI_DIEM_TRUNG_TUYEN", "HOI_HOC_PHI"):
            state = ConversationState(
                current_major="Công nghệ thông tin",
                candidate_majors=("Công nghệ thông tin",),
                previous_intent=previous_intent,
                turn_count=1,
            )
            for question in ("thế còn ngành Luật?", "còn ngành Luật thì sao", "ngành Luật thì sao?"):
                with self.subTest(previous_intent=previous_intent, question=question):
                    analysis = analyze_question(question, state)
                    self.assertEqual(analysis.intent, previous_intent)
                    self.assertEqual(analysis.entities.get("major_name"), "Luật")

    def test_major_question_with_its_own_ask_is_not_rewritten(self) -> None:
        state = ConversationState(previous_intent="HOI_HOC_PHI", current_major="Công nghệ thông tin")
        self.assertEqual(analyze_question("còn ngành Luật học gì?", state).intent, "HOI_NGANH")


class TeencodeTests(unittest.TestCase):
    def test_d_abbreviation_is_a_score_but_money_is_not(self) -> None:
        self.assertEqual(
            analyze_question("e đc 22đ thi thpt có đỗ cntt ko").entities.get("student_scores"), {"thpt": 22}
        )
        self.assertEqual(analyze_question("học phí 12.500.000đ đúng không").entities.get("student_scores"), {})

    def test_hp_and_misspelled_tuition_are_tuition_questions(self) -> None:
        for question in ("hp?", "hp bn", "hok phí ngàng marketting bn v ạ"):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).intent, "HOI_HOC_PHI")

    def test_where_is_the_school_is_in_scope(self) -> None:
        for question in ("trường ở đâu", "truong nam o dau vay"):
            with self.subTest(question=question):
                self.assertEqual(analyze_question(question).entities.get("scope_reason"), "in_scope_dhv")


class VerifiedAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = _retriever()

    def _ask(self, question: str, state: object = None) -> dict[str, object]:
        result = ask_chatbot(question, retriever=self.retriever, llm=_NeverCalledLLM(), conversation_state=state)
        self.assertEqual(result["status"], "ok", msg=result.get("answer"))
        return result

    def test_fee_follow_up_for_another_major_uses_fee_table(self) -> None:
        first = self._ask("Học phí ngành Công nghệ thông tin năm 2026 bao nhiêu?")
        follow_up = self._ask("thế còn ngành Luật?", first["state"])
        self.assertIn("1.250.000", str(follow_up["answer"]))

    def test_score_follow_up_for_another_major(self) -> None:
        first = self._ask("điểm chuẩn ngành CNTT năm 2026")
        follow_up = self._ask("thế còn ngành Luật?", first["state"])
        self.assertIn("762", str(follow_up["answer"]))

    def test_broad_scholarship_question_gets_summary_not_page_fragments(self) -> None:
        for question in ("dhv co hoc bong ko ad", "học bổng ngành AI"):
            with self.subTest(question=question):
                answer = str(self._ask(question)["answer"])
                self.assertIn("(tóm tắt)", answer)
                self.assertNotIn("1.9 Điều kiện", answer)

    def test_base_total_breakdown_excludes_optional_english_test(self) -> None:
        answer = str(self._ask("tổng chi phí học kỳ 1")["answer"])
        base_sentence = answer.split(". Nếu")[0]
        self.assertIn("14.250.000", base_sentence)
        self.assertNotIn("Tiếng Anh", base_sentence)
        self.assertIn("14.500.000", answer)



class CatalogExistenceTests(unittest.TestCase):
    def test_unknown_major_does_not_match_a_shorter_catalog_name(self) -> None:
        for question in (
            "DHV có ngành Ngôn ngữ Đức không?",
            "DHV có ngành Luật hình sự không?",
            "DHV có ngành Công nghệ thông tin y tế không?",
            "có ngành y đa khoa không",
        ):
            with self.subTest(question=question):
                self.assertIsNone(_catalog_existence_answer(analyze_question(question)))

    def test_known_major_still_matches(self) -> None:
        for question in ("DHV có ngành Luật kinh tế không?", "có ngành luật kinh tế ở dhv không", "có ngành luật kinh tế tại trường không"):
            with self.subTest(question=question):
                answer = _catalog_existence_answer(analyze_question(question))
                self.assertIn("7380107", str(answer and answer["answer"]))


class SupplementGuardTests(unittest.TestCase):
    def test_different_major_in_same_template_is_rejected(self) -> None:
        for question in (
            "Ngành Luật kinh tế tại DHV có những chuyên ngành nào?",
            "Điểm trúng tuyển ngành Luật DHV 2026 cao hơn các ngành khác vì sao?",
        ):
            with self.subTest(question=question):
                self.assertIsNone(lookup_supplement(question))

    def test_unsourced_entries_with_figures_are_not_served(self) -> None:
        import re

        from src.ingestion.structured_json import is_official_dhv_url

        entries, _, year = _entries()
        self.assertEqual(year, 2026)
        for _, entry in entries:
            self.assertTrue(
                is_official_dhv_url(str(entry.get("source_url") or "")) or not re.search(r"\d", str(entry["answer"])),
                entry["id"],
            )

    def _wrapped(self, question: str, core: dict[str, object]) -> dict[str, object]:
        fake = {"answer": "x", "sources": [], "status": "ok", "supplement": {"id": "T", "score": 1.0, "year": 2026}}
        target = replace(settings, target_year=2026)
        with patch.object(rag_chain, "_ask_chatbot_core", return_value=core), \
                patch.object(rag_chain, "lookup_supplement", return_value=dict(fake)):
            return ask_chatbot(question, settings_obj=target)

    def test_supplement_keeps_refusals_and_year_boundaries(self) -> None:
        def core(status: str, school: str = "UNSPECIFIED", year: int = 2026) -> dict[str, object]:
            return {"answer": "no", "status": status, "target_school": school,
                    "state": {"current_year": year}, "trace": {"validator": {"status": "rejected", "reason": "r"}}}

        self.assertEqual(self._wrapped("Điểm sàn tại DHV và UEH?", core("out_of_scope", "MIXED"))["status"],
                         "out_of_scope")
        self.assertEqual(self._wrapped("Hạn chót năm ngoái là khi nào?", core("no_data"))["status"], "no_data")
        self.assertEqual(self._wrapped("Hạn chót năm 2025?", core("no_data", year=2025))["status"], "no_data")
        replaced = self._wrapped("bãi đỗ xe có tính phí không?", core("no_data"))
        self.assertEqual(replaced["status"], "ok")
        self.assertEqual(replaced["trace"]["validator"]["status"], "rejected")


class EmbeddingModelTests(unittest.TestCase):
    def test_embedding_model_is_not_used_as_hf_id_under_ollama_backend(self) -> None:
        from src.ingestion import embeddings

        ollama = replace(settings, embedding_backend="ollama", embedding_model="org/ollama-model")
        with patch.object(embeddings, "settings", ollama), patch.dict(os.environ, {"SENTENCE_TRANSFORMER_MODEL": ""}):
            self.assertEqual(
                embeddings.resolve_sentence_transformer_model(), embeddings.DEFAULT_SENTENCE_TRANSFORMER_MODEL
            )


if __name__ == "__main__":
    unittest.main()
