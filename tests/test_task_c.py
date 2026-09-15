"""Offline regression tests for the Task C service boundary and guards."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.scope_guard import is_in_scope
from src.config.settings import settings
from src.models.local_llm import LocalLLM
from src.prompts.rag_prompt import build_rag_prompt
from src.retrieval.retriever import DHVRetriever, topic_category


SOURCE_URL = "https://dhv.edu.vn/verified-source"
def _document(text: str, *, url: str = SOURCE_URL, chunk_id: str = "chunk-1") -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": "Học phí DHV 2026",
            "category": "hoc_phi",
            "year": 2026,
            "school_code": "DHV",
            "source_url": url,
            "status": "verified",
            "chunk_id": chunk_id,
            "heading_path": "Học phí > Mức học phí",
        },
    )


class RecordingRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.called = False

    def retrieve(self, question: str) -> list[Document]:
        self.called = True
        return self.documents


class CategoryRecordingRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.categories: tuple[str, ...] = ()
        self.question = ""
        self.retrieval_query = ""

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: tuple[str, ...],
        retrieval_query: str,
    ) -> dict[str, object]:
        self.question = question
        self.categories = tuple(categories)
        self.retrieval_query = retrieval_query
        return {"documents": self.documents}


class RecordingLLM:
    def __init__(self, answer: str) -> None:
        self.answers = list(answer) if isinstance(answer, list) else [answer]
        self.prompt = ""
        self.prompts: list[str] = []
        self.called = False

    def generate(self, prompt: str) -> str:
        self.called = True
        self.prompt = prompt
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""


class FailingClient:
    def chat(self, **kwargs: object) -> object:
        raise ConnectionError("offline")


class RecordingClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def chat(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"message": {"content": "Học phí là 1.250.000 đồng/tín chỉ."}}


def _category_document(category: str, text: str, *, url: str = SOURCE_URL) -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": f"{category} DHV 2026",
            "category": category,
            "year": 2026,
            "school_code": "DHV",
            "source_url": url,
            "status": "verified",
            "chunk_id": f"{category}-chunk",
            "heading_path": category,
        },
    )


TOPIC_CASES = (
    (
        "Phương thức xét tuyển DHV 2026 gồm những gì?",
        "HOI_PHUONG_THUC_XET_TUYEN",
        "phuong_thuc_xet_tuyen",
    ),
    (
        "phuong thuc xet tuyen va to hop mon nao?",
        "HOI_PHUONG_THUC_XET_TUYEN",
        "phuong_thuc_xet_tuyen",
    ),
    (
        "Công thức điểm xét tuyển học bạ tính thế nào?",
        "HOI_CACH_TINH_DIEM",
        "cach_tinh_diem",
    ),
    (
        "quy doi diem xet tuyen ra sao?",
        "HOI_CACH_TINH_DIEM",
        "cach_tinh_diem",
    ),
    (
        "Cổng đăng ký xét tuyển DHV ở đâu?",
        "HOI_DANG_KY_XET_TUYEN",
        "dang_ky_xet_tuyen",
    ),
    (
        "nop nguyen vong tren cong nao?",
        "HOI_DANG_KY_XET_TUYEN",
        "dang_ky_xet_tuyen",
    ),
    (
        "Cơ sở và hotline tư vấn tuyển sinh DHV?",
        "HOI_CO_SO_LIEN_HE",
        "co_so_lien_he",
    ),
    (
        "dia chi va so dien thoai lien he DHV la gi?",
        "HOI_CO_SO_LIEN_HE",
        "co_so_lien_he",
    ),
)


class TaskCTests(unittest.TestCase):
    def test_scope_guard_allows_admissions_and_rejects_unrelated(self) -> None:
        self.assertTrue(is_in_scope("Học phí DHV 2026 là bao nhiêu?"))
        self.assertTrue(is_in_scope("Hồ sơ/thủ tục nhập học cần gì?"))
        self.assertTrue(is_in_scope("Điểm sàn CNTT?"))
        self.assertTrue(is_in_scope("Điểm trúng tuyển Luật 2026?"))
        self.assertFalse(is_in_scope("Thời tiết hôm nay thế nào?"))

    def test_new_admissions_topics_have_dedicated_intent_and_category(self) -> None:
        for question, expected_intent, expected_category in TOPIC_CASES:
            with self.subTest(question=question):
                analysis = analyze_question(question)
                plan = route_question(analysis, target_year=2026)
                self.assertEqual(analysis.intent, expected_intent)
                self.assertEqual(plan.intent, expected_intent)
                self.assertEqual(plan.categories, (expected_category,))
                self.assertEqual(
                    plan.metadata_filter,
                    {"year": 2026, "categories": [expected_category]},
                )
                self.assertEqual(topic_category(question), expected_category)
                self.assertTrue(is_in_scope(question))

    def test_registration_does_not_capture_enrollment_or_enrollment_documents(self) -> None:
        enrollment = analyze_question("Đăng ký nhập học DHV ở đâu?")
        documents = analyze_question("Thủ tục đăng ký nhập học cần gì?")
        self.assertEqual(enrollment.intent, "HOI_NHAP_HOC")
        self.assertEqual(route_question(enrollment).categories, ("nhap_hoc",))
        self.assertEqual(documents.intent, "HOI_HO_SO")
        self.assertEqual(route_question(documents).categories, ("ho_so",))

    def test_new_admissions_topics_use_only_their_verified_category_end_to_end(self) -> None:
        cases = (
            (
                TOPIC_CASES[0][0],
                "phuong_thuc_xet_tuyen",
                "Phương thức 1: Xét kết quả kỳ thi tốt nghiệp THPT 2026.",
            ),
            (
                TOPIC_CASES[2][0],
                "cach_tinh_diem",
                "Điểm xét tuyển = Toán hoặc Ngữ văn + (Trung bình cả năm THPT × 2).",
            ),
            (
                TOPIC_CASES[4][0],
                "dang_ky_xet_tuyen",
                "Form có Ngành đăng ký NV1, NV2, NV3 và Phương thức xét tuyển. https://fake.invalid/form",
            ),
            (
                TOPIC_CASES[6][0],
                "co_so_lien_he",
                "Trụ sở chính: 194 Lê Đức Thọ. Tổng đài tư vấn tuyển sinh: 0287 1000 888.",
            ),
        )
        for question, category, answer in cases:
            with self.subTest(category=category):
                retriever = CategoryRecordingRetriever(
                    [_category_document(category, answer.replace(" https://fake.invalid/form", ""))]
                )
                llm = RecordingLLM(answer)
                result = ask_chatbot(question, retriever=retriever, llm=llm)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(retriever.categories, (category,))
                self.assertEqual(result["sources"], [{"title": f"{category} DHV 2026", "url": SOURCE_URL}])
                self.assertNotIn("fake.invalid", result["answer"])

    def test_contact_validator_rejects_unverified_phone_and_retries_from_evidence(self) -> None:
        category = "co_so_lien_he"
        document = _category_document(
            category,
            "Tổng đài tư vấn tuyển sinh: 0287 1000 888.",
        )
        llm = RecordingLLM(
            [
                "Hotline tư vấn: 0909 999 999.",
                "Tổng đài tư vấn tuyển sinh: 0287 1000 888.",
            ]
        )
        result = ask_chatbot(
            "Hotline tư vấn tuyển sinh DHV là số nào?",
            retriever=CategoryRecordingRetriever([document]),
            llm=llm,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("0287 1000 888", result["answer"])
        self.assertNotIn("0909 999 999", result["answer"])
        self.assertEqual(len(llm.prompts), 2)

    def test_fact_only_validator_rejects_unverified_date_and_retries(self) -> None:
        category = "dang_ky_xet_tuyen"
        document = _category_document(
            category,
            "Cổng đăng ký xét tuyển DHV đang công khai trong năm 2026.",
        )
        llm = RecordingLLM(
            [
                "Cổng đăng ký xét tuyển: 01/01/2099.",
                "Cổng đăng ký xét tuyển DHV đang công khai trong năm 2026.",
            ]
        )
        result = ask_chatbot(
            "Cổng đăng ký xét tuyển DHV ở đâu?",
            retriever=CategoryRecordingRetriever([document]),
            llm=llm,
        )
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("01/01/2099", result["answer"])
        self.assertEqual(len(llm.prompts), 2)

    def test_success_uses_retrieved_metadata_and_removes_phantom_url(self) -> None:
        retriever = RecordingRetriever(
            [_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")]
        )
        llm = RecordingLLM(
            "Học phí là 1.250.000 đồng/tín chỉ. https://fake.invalid/not-retrieved"
        )

        result = ask_chatbot("Học phí DHV 2026", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"], [{"title": "Học phí DHV 2026", "url": SOURCE_URL}])
        self.assertNotIn("fake.invalid", result["answer"])
        self.assertTrue(llm.called)
        self.assertNotIn(SOURCE_URL, llm.prompt)

    def test_tuition_validator_does_not_relabel_total_cost_as_tuition(self) -> None:
        documents = [
            _document(
                "Học phí HKI (10 tín chỉ): 12.500.000 đồng. "
                "Tổng chi phí học kỳ I: 14.500.000 đồng.",
            )
        ]
        llm = RecordingLLM("Học phí học kỳ I là 14.500.000 đồng.")

        result = ask_chatbot("Học phí DHV 2026", retriever=RecordingRetriever(documents), llm=llm)

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(llm.prompts), 2)

    def test_threshold_validator_repairs_model_omission_from_evidence(self) -> None:
        threshold_document = Document(
            page_content=(
                "Ngưỡng đảm bảo chất lượng đầu vào (điểm sàn) năm 2026:\n"
                "Xét kết quả kỳ thi tốt nghiệp THPT: từ 15 điểm.\n"
                "Xét kết quả học tập THPT (học bạ): từ 18 điểm.\n"
                "Xét kết quả kỳ thi đánh giá năng lực: từ 600 điểm."
            ),
            metadata={
                "title": "Ngưỡng đảm bảo chất lượng đầu vào DHV 2026",
                "category": "nguong_dau_vao",
                "year": 2026,
                "school_code": "DHV",
                "source_url": SOURCE_URL,
                "status": "verified",
                "chunk_id": "threshold-1",
                "heading_path": "Ngưỡng đầu vào",
            },
        )
        llm = RecordingLLM(
            [
                "Ngưỡng điểm sàn năm 2026 là từ 15 điểm, xét theo kết quả kỳ thi tốt nghiệp THPT.",
                threshold_document.page_content,
            ]
        )

        result = ask_chatbot(
            "Điểm sàn CNTT 2026?",
            retriever=RecordingRetriever([threshold_document]),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("từ 15 điểm", result["answer"])
        self.assertIn("từ 18 điểm", result["answer"])
        self.assertIn("từ 600 điểm", result["answer"])
        self.assertEqual(len(llm.prompts), 2)

    def test_evidence_deduplicates_chunks_and_sources_and_caps_context(self) -> None:
        docs = [
            _document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.", chunk_id="same"),
            _document("Nội dung trùng không được thêm lần nữa.", chunk_id="same"),
            _document("Học kỳ I gồm 10 tín chỉ.", chunk_id="other"),
        ]

        evidence = build_evidence(docs, max_chars=600)

        self.assertEqual(len(evidence.chunks), 2)
        self.assertEqual(len(evidence.sources), 1)
        self.assertLessEqual(len(evidence.context), 600)
        self.assertEqual(evidence.sources[0]["url"], SOURCE_URL)
        self.assertNotIn("https://", evidence.context)

    def test_explicit_unsupported_year_is_no_data_without_model_call(self) -> None:
        retriever = RecordingRetriever([_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")])
        llm = RecordingLLM("Không nên được gọi.")

        result = ask_chatbot("Học phí DHV 2027", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertFalse(retriever.called)
        self.assertFalse(llm.called)

    def test_out_of_scope_is_rejected_without_retrieval_or_model_call(self) -> None:
        retriever = RecordingRetriever([_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")])
        llm = RecordingLLM("Không nên được gọi.")

        result = ask_chatbot("Thời tiết hôm nay?", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "out_of_scope")
        self.assertFalse(retriever.called)
        self.assertFalse(llm.called)

    def test_missing_evidence_falls_back(self) -> None:
        result = ask_chatbot("Học bổng DHV 2026", retriever=RecordingRetriever([]), llm=RecordingLLM("x"))

        self.assertEqual(result["status"], "no_data")
        self.assertIn("chưa tìm thấy", result["answer"])
        self.assertEqual(result["sources"], [])

    def test_ollama_offline_is_classified_without_traceback(self) -> None:
        retriever = RecordingRetriever([_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")])
        llm = LocalLLM(client=FailingClient())

        result = ask_chatbot("Học phí DHV 2026", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "ollama_offline")
        self.assertEqual(result["sources"], [])
        self.assertNotIn("Traceback", result["answer"])

    def test_missing_chroma_is_classified_as_vector_db_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_settings = replace(
                settings,
                chroma_persist_dir=Path(temp_dir) / "missing-chroma",
            )
            retriever = DHVRetriever(settings_obj=missing_settings)
            result = ask_chatbot("Học phí DHV 2026", retriever=retriever)

        self.assertEqual(result["status"], "vector_db_error")
        self.assertEqual(result["sources"], [])

    def test_retriever_passes_task_b_embedding_contract_and_top_k(self) -> None:
        calls: dict[str, object] = {}

        def embedding_factory(**kwargs: object) -> object:
            calls["embedding"] = kwargs
            return object()

        class Collection:
            def count(self) -> int:
                return 1

        class Store:
            _collection = Collection()

            def similarity_search(self, question: str, *, k: int, filter: dict[str, int]) -> list[Document]:
                calls["search"] = {"question": question, "k": k, "filter": filter}
                return [_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")]

        def store_factory(**kwargs: object) -> Store:
            calls["store"] = kwargs
            return Store()

        with tempfile.TemporaryDirectory() as temp_dir:
            configured = replace(settings, chroma_persist_dir=Path(temp_dir))
            retriever = DHVRetriever(
                settings_obj=configured,
                store_factory=store_factory,
                embedding_factory=embedding_factory,
            )
            documents = retriever.retrieve("Học phí DHV 2026")

        self.assertEqual(len(documents), 1)
        self.assertEqual(calls["embedding"]["backend"], "ollama")
        self.assertEqual(calls["embedding"]["ollama_model"], "nomic-embed-text")
        self.assertEqual(calls["embedding"]["ollama_base_url"], "http://localhost:11434")
        self.assertEqual(calls["store"]["collection_name"], "dhv_admissions_2026")
        self.assertEqual(calls["search"]["k"], 4)
        self.assertEqual(
            calls["search"]["filter"],
            {"$and": [{"year": 2026}, {"category": "hoc_phi"}]},
        )

    def test_topic_category_prioritizes_the_specific_admissions_group(self) -> None:
        self.assertEqual(topic_category("Học phí DHV 2026"), "hoc_phi")
        self.assertEqual(topic_category("Hồ sơ/thủ tục nhập học"), "ho_so")
        self.assertEqual(topic_category("Nhập học trực tuyến ở đâu?"), "nhap_hoc")
        self.assertEqual(topic_category("Hạn xét tuyển bổ sung"), "xet_tuyen_bo_sung")
        self.assertEqual(topic_category("Lịch tuyển sinh DHV 2026"), "lich_tuyen_sinh")
        self.assertEqual(topic_category("Điểm sàn CNTT?"), "nguong_dau_vao")
        self.assertEqual(topic_category("Điểm sàn chung?"), "nguong_dau_vao")
        self.assertEqual(topic_category("Điểm trúng tuyển Luật 2026?"), "diem_trung_tuyen")
        self.assertEqual(topic_category("Ngành đào tạo DHV 2026?"), "nganh_dao_tao")

    def test_local_llm_calls_configured_qwen_model(self) -> None:
        client = RecordingClient()
        llm = LocalLLM(client=client)

        answer = llm.generate("prompt")

        self.assertIn("1.250.000", answer)
        self.assertEqual(client.kwargs["model"], "qwen2.5:3b")
        self.assertEqual(client.kwargs["options"], {"temperature": 0})

    def test_prompt_requires_context_only_and_no_urls(self) -> None:
        prompt = build_rag_prompt("Học phí DHV 2026", "Học phí là 1.250.000 đồng/tín chỉ.")

        self.assertIn("CHỈ DÙNG CONTEXT", prompt)
        self.assertIn("Không tạo, đoán hoặc chép URL", prompt)
        self.assertIn("điểm sàn", prompt)
        self.assertIn("Học phí là 1.250.000", prompt)


if __name__ == "__main__":
    unittest.main()
