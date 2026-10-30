"""Offline regression tests for the Task C service boundary and guards."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence, select_evidence_documents
from src.chatbot.rag_chain import ask_chatbot
from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.scope_guard import is_in_scope
from src.config.settings import settings
from src.models.local_llm import LocalLLM
from src.prompts.rag_prompt import build_rag_prompt
from src.retrieval.retriever import DHVRetriever, topic_category


SOURCE_URL = "https://dhv.edu.vn/verified-source"
def _document(
    text: str,
    *,
    url: str = SOURCE_URL,
    chunk_id: str = "chunk-1",
    year: int = 2026,
) -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": f"Học phí DHV {year}",
            "category": "hoc_phi",
            "year": year,
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
        "phuong_thuc_xet_tuyen",
    ),
    (
        "quy doi diem xet tuyen ra sao?",
        "HOI_CACH_TINH_DIEM",
        "phuong_thuc_xet_tuyen",
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
                expected_categories = (
                    ("dang_ky_xet_tuyen", "phuong_thuc_xet_tuyen")
                    if expected_intent == "HOI_DANG_KY_XET_TUYEN"
                    else ("thong_tin_truong", "co_so_lien_he")
                    if expected_intent == "HOI_CO_SO_LIEN_HE"
                    else (expected_category,)
                )
                self.assertEqual(plan.categories, expected_categories)
                expected_filter = {
                    "year": 2026,
                    "categories": list(expected_categories),
                }
                if plan.data_roles:
                    expected_filter["data_roles"] = list(plan.data_roles)
                self.assertEqual(
                    plan.metadata_filter,
                    expected_filter,
                )
                self.assertEqual(topic_category(question), expected_category)
                self.assertTrue(is_in_scope(question))

    def test_registration_does_not_capture_enrollment_or_enrollment_documents(self) -> None:
        enrollment = analyze_question("Đăng ký nhập học DHV ở đâu?")
        documents = analyze_question("Thủ tục đăng ký nhập học cần gì?")
        self.assertEqual(enrollment.intent, "HOI_NHAP_HOC")
        self.assertEqual(route_question(enrollment).categories, ("ho_so", "nhap_hoc"))
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
                "phuong_thuc_xet_tuyen",
                "Điểm xét tuyển = Toán hoặc Ngữ văn + (Trung bình cả năm THPT × 2).",
            ),
            (
                TOPIC_CASES[4][0],
                ("dang_ky_xet_tuyen", "phuong_thuc_xet_tuyen"),
                "Form có Ngành đăng ký NV1, NV2, NV3 và Phương thức xét tuyển. https://fake.invalid/form",
            ),
            (
                TOPIC_CASES[6][0],
                ("thong_tin_truong", "co_so_lien_he"),
                "Trụ sở chính: 194 Lê Đức Thọ. Tổng đài tư vấn tuyển sinh: 0287 1000 888.",
            ),
        )
        for question, category_value, answer in cases:
            categories = (
                category_value
                if isinstance(category_value, tuple)
                else (category_value,)
            )
            category = categories[0]
            with self.subTest(category=categories):
                retriever = CategoryRecordingRetriever(
                    [_category_document(category, answer.replace(" https://fake.invalid/form", ""))]
                )
                llm = RecordingLLM(answer)
                result = ask_chatbot(question, retriever=retriever, llm=llm)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(retriever.categories, categories)
                self.assertEqual(result["sources"], [{"title": f"{category} DHV 2026", "url": SOURCE_URL}])
                self.assertNotIn("fake.invalid", result["answer"])

    def test_registration_intent_drops_unrelated_chunks_from_shared_method_category(self) -> None:
        registration = _category_document(
            "phuong_thuc_xet_tuyen",
            "Nguyên tắc chung: Thí sinh chỉ cần đăng ký vào DHV và ngành học mong muốn. "
            "Thời gian đăng ký xét tuyển đến hết ngày 13/08/2026.",
        )
        registration.metadata["chunk_id"] = "registration-rule"
        scholarship = _category_document(
            "phuong_thuc_xet_tuyen",
            "Chính sách học bổng: Thí sinh đăng ký học bổng theo điểm học tập và được "
            "hỗ trợ học phí học kỳ I.",
        )
        scholarship.metadata["chunk_id"] = "scholarship-policy"

        selection = select_evidence_documents(
            [scholarship, registration],
            categories=("phuong_thuc_xet_tuyen",),
            target_year=2026,
            intent="HOI_DANG_KY_XET_TUYEN",
        )

        self.assertEqual(
            [document.metadata["chunk_id"] for document in selection.documents],
            ["registration-rule"],
        )
        self.assertEqual(
            [item["filter_reason"] for item in selection.filtered],
            ["intent_content_mismatch"],
        )

    def test_general_registration_rule_is_extracted_from_verified_evidence(self) -> None:
        document = _category_document(
            "phuong_thuc_xet_tuyen",
            "Nguyên tắc chung: Thí sinh chỉ cần đăng ký vào DHV và ngành học mong muốn; "
            "hệ thống tuyển sinh của Nhà trường sẽ tự động chọn phương thức có điểm cao "
            "nhất để xét trúng tuyển.\nThời gian đăng ký xét tuyển: Đến hết ngày 13/08/2026",
        )
        llm = RecordingLLM("Không được dùng câu trả lời này.")
        result = ask_chatbot(
            "Cách đăng ký tuyển sinh DHV năm 2026 như thế nào?",
            retriever=CategoryRecordingRetriever([document]),
            llm=llm,
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("đăng ký vào DHV và ngành học mong muốn", result["answer"])
        self.assertIn("13/08/2026", result["answer"])
        self.assertNotIn("các bước", result["answer"].casefold())
        self.assertFalse(llm.called)

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
        self.assertEqual(llm.prompts, [])

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
        self.assertIn("1.250.000 đồng/tín chỉ", result["answer"])
        self.assertFalse(llm.called)

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
        self.assertFalse(llm.prompts)

    def test_threshold_answer_preserves_numeric_semantics_from_evidence(self) -> None:
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
        self.assertRegex(result["answer"], r"(?<!\d)15(?:[.,]00)?\s*điểm")
        self.assertRegex(result["answer"], r"(?<!\d)18(?:[.,]00)?\s*điểm")
        self.assertRegex(result["answer"], r"(?<!\d)600(?:[.,]00)?\s*điểm")
        # The public contract is the evidence-grounded values, not whether
        # the response was supplied by the deterministic score branch or LLM.

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

    def test_explicit_other_year_uses_only_matching_year_evidence(self) -> None:
        retriever_2024 = RecordingRetriever(
            [
                _document("Học phí DHV năm 2024 là 1.100.000 VNĐ/tín chỉ.", year=2024),
                _document(
                    "Học phí DHV năm 2026 là 1.250.000 đồng/tín chỉ.",
                    year=2026,
                    chunk_id="2026",
                ),
            ]
        )
        llm_2024 = RecordingLLM("Học phí DHV năm 2024 là 1.100.000 VNĐ/tín chỉ.")

        result_2024 = ask_chatbot(
            "Học phí DHV năm 2024 bao nhiêu?",
            retriever=retriever_2024,
            llm=llm_2024,
        )

        self.assertEqual(result_2024["status"], "ok")
        self.assertEqual(result_2024["trace"]["entities"]["year"], 2024)
        self.assertEqual(result_2024["trace"]["evidence_count"], 1)
        self.assertIn("1.100.000", result_2024["answer"])
        self.assertNotIn("1.250.000", result_2024["answer"])
        self.assertFalse(llm_2024.called)

        retriever_2026 = RecordingRetriever(
            [
                _document("Học phí DHV năm 2024 là 1.100.000 VNĐ/tín chỉ.", year=2024),
                _document(
                    "Học phí DHV năm 2026 là 1.250.000 đồng/tín chỉ.",
                    year=2026,
                    chunk_id="2026",
                ),
            ]
        )
        result_2026 = ask_chatbot(
            "Học phí DHV năm 2026 bao nhiêu?",
            retriever=retriever_2026,
            llm=RecordingLLM("Học phí DHV năm 2026 là 1.250.000 đồng/tín chỉ."),
        )
        self.assertEqual(result_2026["status"], "ok")
        self.assertEqual(result_2026["trace"]["entities"]["year"], 2026)
        self.assertEqual(result_2026["trace"]["evidence_count"], 1)
        self.assertIn("1.250.000", result_2026["answer"])
        self.assertNotIn("1.100.000", result_2026["answer"])

    def test_explicit_unsupported_year_is_no_data_without_model_call(self) -> None:
        retriever = RecordingRetriever([_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")])
        llm = RecordingLLM("Không nên được gọi.")

        result = ask_chatbot("Học phí DHV 2027", retriever=retriever, llm=llm)

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["sources"], [])
        self.assertTrue(retriever.called)
        self.assertEqual(result["trace"]["entities"]["year"], 2027)
        self.assertEqual(result["trace"]["evidence_count"], 0)
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
        self.assertIn("chưa có thông tin chính xác", result["answer"])
        self.assertEqual(result["sources"], [])

    def test_ollama_offline_is_classified_without_traceback(self) -> None:
        retriever = RecordingRetriever([_document("Học phí DHV 2026 là 1.250.000 đồng/tín chỉ.")])
        llm = LocalLLM(client=FailingClient())

        result = ask_chatbot("Học phí DHV 2026", retriever=retriever, llm=llm)

        # A complete answer from verified evidence does not depend on Ollama.
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"], [{"title": "Học phí DHV 2026", "url": SOURCE_URL}])
        self.assertIn("1.250.000 đồng/tín chỉ", result["answer"])
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
            configured = replace(
                settings,
                chroma_persist_dir=Path(temp_dir),
                embedding_backend="ollama",
                embedding_model="nomic-embed-text",
            )
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
        configured = replace(settings, ollama_model="qwen2.5:3b")
        llm = LocalLLM(settings_obj=configured, client=client)

        answer = llm.generate("prompt")

        self.assertIn("1.250.000", answer)
        self.assertEqual(client.kwargs["model"], "qwen2.5:3b")
        self.assertEqual(client.kwargs["options"]["temperature"], 0)
        self.assertGreaterEqual(client.kwargs["options"]["num_ctx"], 8192)

    def test_prompt_requires_context_only_and_no_urls(self) -> None:
        prompt = build_rag_prompt("Học phí DHV 2026", "Học phí là 1.250.000 đồng/tín chỉ.")

        self.assertIn("CHỈ DÙNG CONTEXT", prompt)
        self.assertIn("Không tạo, đoán hoặc chép URL", prompt)
        self.assertIn("điểm sàn", prompt)
        self.assertIn("Học phí là 1.250.000", prompt)


if __name__ == "__main__":
    unittest.main()
