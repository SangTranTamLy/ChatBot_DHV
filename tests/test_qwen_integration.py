"""Opt-in integration checks against the configured local Ollama Qwen model.

These tests are intentionally separate from the offline suite because Ollama
and the model are external local runtime dependencies.
"""

from __future__ import annotations

import os
import unittest

from langchain_core.documents import Document

from src.chatbot.rag_chain import ask_chatbot
from src.models.local_llm import LocalLLM
from src.config.settings import settings


RUN_REAL_QWEN_TESTS = os.getenv("RUN_REAL_QWEN_TESTS") == "1"


class StaticRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: tuple[str, ...],
        retrieval_query: str,
        **_: object,
    ) -> dict[str, object]:
        return {"documents": self.documents}


def _tuition_document() -> Document:
    return Document(
        page_content=(
            "Học phí theo tín chỉ năm 2026 là 1.250.000 đồng/tín chỉ. "
            "Tổng học phí phụ thuộc vào số tín chỉ thực tế đăng ký."
        ),
        metadata={
            "record_type": "page_text",
            "title": "Học phí DHV 2026",
            "category": "hoc_phi",
            "year": 2026,
            "school_code": "DHV",
            "source_url": "https://dhv.edu.vn/",
            "status": "verified",
            "source_file": "08_HOC_PHI_VA_KHOAN_THU_NHAP_HOC_DHV_2026.pdf",
            "document_id": "qwen-tuition-fixture",
            "chunk_id": "qwen-tuition-1",
        },
    )


class QwenFixtureRoutingTests(unittest.TestCase):
    def test_verified_tuition_fixture_reaches_the_common_composer(self) -> None:
        class ComposerProbe:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return (
                    "Học phí DHV năm 2026 được tính theo tín chỉ, "
                    "ở mức 1.250.000 đồng/tín chỉ. Tổng tiền tùy số tín chỉ đăng ký."
                )

        llm = ComposerProbe()
        result = ask_chatbot(
            "Học phí DHV 2026 theo tín chỉ là bao nhiêu?",
            retriever=StaticRetriever([_tuition_document()]),
            llm=llm,
            settings_obj=settings,
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(llm.prompts)
        self.assertIn("1.250.000", str(result["answer"]))


@unittest.skipUnless(
    RUN_REAL_QWEN_TESTS,
    "set RUN_REAL_QWEN_TESTS=1 to run against the configured Ollama Qwen model",
)
class RealQwenTests(unittest.TestCase):
    def test_real_qwen_produces_a_grounded_answer(self) -> None:
        result = ask_chatbot(
            "Học phí DHV 2026 theo tín chỉ là bao nhiêu?",
            retriever=StaticRetriever([_tuition_document()]),
            llm=LocalLLM(settings_obj=settings),
            settings_obj=settings,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("1.250.000", str(result["answer"]))
        self.assertIn("học phí", str(result["answer"]).casefold())


if __name__ == "__main__":
    unittest.main()
