"""Tên DHV bị ngắt dòng thành gạch đầu dòng không bị coi là trường khác."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from evaluation.run_evaluation import _retriever
from src.chatbot.output_validator import _has_unsupported_named_entity, _target_institution_failure
from src.chatbot.rag_chain import ask_chatbot


EVIDENCE = SimpleNamespace(chunks=[SimpleNamespace(
    text="Năm 2026, Trường Đại học\nHùng Vương TP. Hồ Chí Minh (DHV) triển khai quỹ học bổng."
)])


class _NeverCalledLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("the verified scholarship answer must not fall back to generation")


class InstitutionNameBulletTests(unittest.TestCase):
    def test_dhv_name_split_by_a_bullet_is_trusted(self) -> None:
        answer = "Năm 2026, Trường Đại học\n- Hùng Vương TP. Hồ Chí Minh (DHV) triển khai quỹ học bổng."
        self.assertEqual(_target_institution_failure(answer, EVIDENCE), "")

    def test_named_entity_guard_also_trusts_the_split_dhv_name(self) -> None:
        answer = "Năm 2026, Trường Đại học\n- Hùng Vương TP. Hồ Chí Minh (DHV) triển khai quỹ học bổng."
        self.assertFalse(_has_unsupported_named_entity(answer, EVIDENCE, None))
        self.assertTrue(_has_unsupported_named_entity("Trường Đại học\n- FPT có học bổng.", EVIDENCE, None))

    def test_other_school_is_still_rejected_with_or_without_a_bullet(self) -> None:
        for answer in (
            "Trường Đại học\n- FPT có học bổng 100% học phí.",
            "Trường Đại học FPT có học bổng 100% học phí.",
        ):
            with self.subTest(answer=answer):
                self.assertEqual(_target_institution_failure(answer, EVIDENCE), "institution_mismatch")

    def test_dhv_scholarship_question_keeps_the_verified_answer(self) -> None:
        result = ask_chatbot("DHV có học bổng không?", retriever=_retriever(), llm=_NeverCalledLLM())
        self.assertEqual(result["trace"]["evidence_direct_answer"]["status"], "ok")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Học bổng", str(result["answer"]))


if __name__ == "__main__":
    unittest.main()
