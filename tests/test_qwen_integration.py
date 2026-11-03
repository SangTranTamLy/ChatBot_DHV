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

    def test_unsupported_school_shortening_retries_with_canonical_name_rule(self) -> None:
        class CorrectingComposer:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                if len(self.prompts) == 1:
                    return (
                        "Học phí theo tín chỉ năm 2026 của Trường Đại học Hùng Vương "
                        "là 1.250.000 đồng/tín chỉ."
                    )
                return "Học phí DHV năm 2026 là 1.250.000 đồng/tín chỉ."

        llm = CorrectingComposer()
        result = ask_chatbot(
            "Học phí DHV 2026 theo tín chỉ là bao nhiêu?",
            retriever=StaticRetriever([_tuition_document()]),
            llm=llm,
            settings_obj=settings,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("không rút gọn thành", llm.prompts[1])
        self.assertEqual(result["trace"]["response_composer"]["status"], "composed")
        self.assertIn("1.250.000 đồng/tín chỉ", result["answer"])

    def test_composer_cannot_replace_requested_unit_price_with_semester_price(self) -> None:
        class MisleadingComposer:
            def generate(self, prompt: str) -> str:
                # Both facts appear in the verified fixture, but only the
                # per-credit rate answers the question.
                return "Học phí HKI (10 tín chỉ): 12.500.000 đồng"

        document = Document(
            page_content=(
                "Học phí HKI (10 tín chỉ): 12.500.000 đồng\n"
                "Học phí theo tín chỉ: 1.250.000 đồng/tín chỉ."
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
                "document_id": "qwen-tuition-scope-fixture",
                "chunk_id": "qwen-tuition-scope-1",
            },
        )
        result = ask_chatbot(
            "Học phí DHV 2026 tính theo tín chỉ là bao nhiêu?",
            retriever=StaticRetriever([document]),
            llm=MisleadingComposer(),
            settings_obj=settings,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("1.250.000 đồng/tín chỉ", str(result["answer"]))
        self.assertNotIn("12.500.000 đồng", str(result["answer"]))


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
        self.assertEqual(
            (result.get("trace") or {}).get("response_composer", {}).get("status"),
            "composed",
            "a safe deterministic fallback is not evidence that Qwen ran",
        )


if __name__ == "__main__":
    unittest.main()
