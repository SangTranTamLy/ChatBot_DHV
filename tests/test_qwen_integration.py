"""Opt-in integration checks against the real local qwen2.5:3b model.

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
    ) -> dict[str, object]:
        return {"documents": self.documents}


def _tuition_document() -> Document:
    return Document(
        page_content=(
            "## Học phí học kỳ I năm 2026\n"
            "Học phí: 12.500.000 đồng/học kỳ đối với chương trình chuẩn.\n"
            "Học phí học kỳ II: 14.500.000 đồng/học kỳ."
        ),
        metadata={
            "title": "Học phí DHV 2026",
            "category": "hoc_phi",
            "year": 2026,
            "school_code": "DHV",
            "source_url": "https://dhv.edu.vn/verified-tuition",
            "status": "verified",
            "chunk_id": "qwen-tuition-1",
        },
    )


@unittest.skipUnless(
    RUN_REAL_QWEN_TESTS,
    "set RUN_REAL_QWEN_TESTS=1 to run against Ollama and qwen2.5:3b",
)
class RealQwenTests(unittest.TestCase):
    def test_real_qwen_produces_a_grounded_answer(self) -> None:
        result = ask_chatbot(
            "Học phí DHV 2026 là bao nhiêu?",
            retriever=StaticRetriever([_tuition_document()]),
            llm=LocalLLM(settings_obj=settings),
            settings_obj=settings,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("12.500.000", str(result["answer"]))
        self.assertIn("học phí", str(result["answer"]).casefold())


if __name__ == "__main__":
    unittest.main()
