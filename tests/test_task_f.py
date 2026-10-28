"""Task F tests: analysis, retrieval audit, generation guards and conversation."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.chatbot.evidence import build_evidence
from src.chatbot.chat_service import ChatService
from src.chatbot.output_validator import FALLBACK_ANSWER
from src.chatbot.rag_chain import _has_verified_advisory_fit_evidence, ask_chatbot
from src.chatbot.query_analysis import (
    ConversationState,
    analyze_question,
    enrich_analysis_from_evidence,
    normalize_question,
    route_question,
)
from src.config.settings import settings
from src.ingestion.loader import load_verified_documents
from src.ingestion.splitter import split_documents
from src.retrieval.retriever import DHVRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_golden_questions.json"
GOLDEN_CASES = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
DHV_MAJORS_2026 = (
    ("Quản trị kinh doanh", "7340101"),
    ("Kinh tế quốc tế", "7310106"),
    ("Marketing", "7340115"),
    ("Thương mại điện tử", "7340122"),
    ("Tài chính ngân hàng", "7340201"),
    ("Kế toán", "7340301"),
    ("Công nghệ tài chính", "7340205"),
    ("Kỹ thuật máy tính", "7480106"),
    ("Công nghệ thông tin", "7480201"),
    ("Trí tuệ nhân tạo", "7480107"),
    ("Ngôn ngữ Anh", "7220201"),
    ("Ngôn ngữ Nhật", "7220209"),
    ("Ngôn ngữ Trung Quốc", "7220204"),
    ("Ngôn ngữ Hàn Quốc", "7220210"),
    ("Quản trị Khách sạn", "7810201"),
    ("Quản trị Dịch vụ Du lịch & Lữ hành", "7810103"),
    ("Luật", "7380101"),
    ("Luật Kinh tế", "7380107"),
    ("Quản lý bệnh viện", "7720802"),
    ("Tâm lý học", "7310401"),
)
DHV_PROGRAM_PARENTS_2026 = (
    ("Quản trị Kinh doanh tổng hợp", "Quản trị kinh doanh"),
    ("Quản trị Nhân lực", "Quản trị kinh doanh"),
    ("Quản trị Logistics", "Quản trị kinh doanh"),
    ("Khởi nghiệp và Phát triển bền vững", "Quản trị kinh doanh"),
    ("Quản trị công nghệ và Đổi mới sáng tạo", "Quản trị kinh doanh"),
    ("Quản trị Marketing", "Marketing"),
    ("Digital Marketing", "Marketing"),
    ("Truyền thông và quan hệ công chúng", "Marketing"),
    ("Truyền thông số", "Marketing"),
    ("Quản trị thương mại điện tử", "Thương mại điện tử"),
    ("Kinh doanh số", "Thương mại điện tử"),
    ("Phân tích dữ liệu kinh doanh", "Thương mại điện tử"),
    ("Ngân hàng số", "Tài chính ngân hàng"),
    ("Tài chính doanh nghiệp", "Tài chính ngân hàng"),
    ("Kế toán doanh nghiệp", "Kế toán"),
    ("Kế toán số", "Kế toán"),
    ("Công nghệ tài chính", "Công nghệ tài chính"),
    ("Khai phá dữ liệu tài chính", "Công nghệ tài chính"),
    ("Hệ thống nhúng thông minh", "Kỹ thuật máy tính"),
    ("AI và IoT ứng dụng", "Kỹ thuật máy tính"),
    ("Công nghệ phần mềm", "Công nghệ thông tin"),
    ("Lập trình AI", "Công nghệ thông tin"),
    ("An ninh mạng và hệ thống", "Công nghệ thông tin"),
    ("Truyền thông đa phương tiện", "Công nghệ thông tin"),
    ("Phân tích dữ liệu lớn", "Công nghệ thông tin"),
    ("Giảng dạy Tiếng Anh", "Ngôn ngữ Anh"),
    ("Tiếng Anh thương mại", "Ngôn ngữ Anh"),
    ("Tiếng Nhật thương mại", "Ngôn ngữ Nhật"),
    ("Ngôn ngữ", "Ngôn ngữ Nhật"),
    ("Văn hóa Nhật Bản", "Ngôn ngữ Nhật"),
    ("Tiếng Trung thương mại", "Ngôn ngữ Trung Quốc"),
    ("Tiếng Trung hành chính văn phòng", "Ngôn ngữ Trung Quốc"),
    ("Giảng dạy Tiếng Trung", "Ngôn ngữ Trung Quốc"),
    ("Tiếng Trung văn hóa", "Ngôn ngữ Trung Quốc"),
    ("Du lịch", "Ngôn ngữ Trung Quốc"),
    ("Giảng dạy Tiếng Hàn", "Ngôn ngữ Hàn Quốc"),
    ("Tiếng Hàn thương mại", "Ngôn ngữ Hàn Quốc"),
    ("Quản trị khách sạn", "Quản trị Khách sạn"),
    ("Quản trị nhà hàng và dịch vụ ẩm thực", "Quản trị Khách sạn"),
    ("Quản trị lữ hành", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("Quản lý giải trí", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("Quản trị sự kiện", "Quản trị Dịch vụ Du lịch & Lữ hành"),
    ("Quản lý chất lượng bệnh viện", "Quản lý bệnh viện"),
    ("Quản lý tài chính bệnh viện", "Quản lý bệnh viện"),
    ("Quản lý trang thiết bị y tế", "Quản lý bệnh viện"),
    ("Tâm lý học đường", "Tâm lý học"),
    ("Tâm lý lâm sàng", "Tâm lý học"),
    ("Tâm lý tổ chức", "Tâm lý học"),
    ("Nhân sự", "Tâm lý học"),
    ("Ứng dụng AI trong tâm lý", "Tâm lý học"),
)


def _path_value(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _fixture_chunks() -> list[Document]:
    documents = load_verified_documents(PROJECT_ROOT / "data" / "processed").documents
    return split_documents(documents)


def _where_matches(metadata: dict[str, object], where: dict[str, object]) -> bool:
    if "year" in where:
        return metadata.get("year") == where["year"]
    if "$and" in where:
        return all(_where_matches(metadata, item) for item in where["$and"])
    if "$or" in where:
        return any(_where_matches(metadata, item) for item in where["$or"])
    if "category" in where:
        return metadata.get("category") == where["category"]
    if "data_role" in where:
        return metadata.get("data_role") == where["data_role"]
    return True


class CorpusStore:
    """Chroma-shaped read-only store backed by the current processed corpus."""

    chunks = _fixture_chunks()

    class Collection:
        def count(self) -> int:
            return len(CorpusStore.chunks)

    _collection = Collection()

    def __init__(self, **_: object) -> None:
        pass

    def _filtered(self, where: dict[str, object]) -> list[Document]:
        return [
            document
            for document in self.chunks
            if _where_matches(document.metadata, where)
        ]

    def similarity_search(self, query: str, *, k: int, filter: dict[str, object]) -> list[Document]:
        documents = self._filtered(filter)
        # Deliberately make vector-only retrieval miss the exact code chunk in
        # one regression case; the keyword pass must recover it from get().
        if "7480201" in query:
            documents = [document for document in documents if "7480201" not in document.page_content]
        return documents[:k]

    def get(self, *, where: dict[str, object], include: list[str]) -> dict[str, object]:
        documents = self._filtered(where)
        return {
            "documents": [document.page_content for document in documents],
            "metadatas": [document.metadata for document in documents],
        }


class EchoEvidenceLLM:
    """Generation double that emits only structured prompt evidence."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        entities_match = re.search(r"<ENTITIES>\n(.*?)\n</ENTITIES>", prompt, re.DOTALL)
        if entities_match:
            try:
                entities = json.loads(entities_match.group(1))
            except json.JSONDecodeError:
                entities = {}
            program = entities.get("program_name")
            parent = entities.get("parent_major")
            if program and parent:
                return f"{program} là chương trình thuộc ngành {parent}."
        facts_match = re.search(
            r"<STRUCTURED_SCORE_FACTS>\n(.*?)\n</STRUCTURED_SCORE_FACTS>",
            prompt,
            re.DOTALL,
        )
        if facts_match:
            try:
                facts = json.loads(facts_match.group(1))
            except json.JSONDecodeError:
                facts = []
            if facts:
                lines: list[str] = []
                labels = {
                    "thpt": "Thi tốt nghiệp THPT",
                    "hoc_ba": "Học bạ",
                    "dgnl": "ĐGNL",
                    "deadline": "Hạn xét tuyển bổ sung",
                }
                seen: set[tuple[str, str, str]] = set()
                for fact in facts:
                    method = str(fact.get("method", ""))
                    value = str(fact.get("raw_value", ""))
                    score_type = str(fact.get("score_type", ""))
                    key = (score_type, method, value)
                    if method not in labels or key in seen:
                        continue
                    seen.add(key)
                    lines.append(f"{labels[method]}: {value}")
                if lines:
                    return "Dữ liệu tuyển sinh: " + "; ".join(lines) + "."
        match = re.search(r"<CONTEXT>\n(.*?)\n</CONTEXT>", prompt, re.DOTALL)
        return match.group(1).strip() if match else ""


class SequenceLLM:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


class RecordingRetriever:
    """Deterministic retriever double that still exposes the real corpus chunks."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.calls: list[dict[str, object]] = []

    def retrieve_with_audit(
        self,
        question: str,
        *,
        categories: tuple[str, ...],
        retrieval_query: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "question": question,
                "categories": tuple(categories),
                "retrieval_query": retrieval_query,
            }
        )
        return {"documents": list(self.documents)}


class RecordingLLM:
    """Ollama-like generation double used to prove catalog output is evidence-owned."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def _retriever() -> DHVRetriever:
    return DHVRetriever(
        settings_obj=settings,
        store_factory=CorpusStore,
        embedding_factory=lambda **_: object(),
    )


class TaskFAnalysisTests(unittest.TestCase):
    def test_all_20_major_names_and_codes_resolve_to_canonical_entities(self) -> None:
        for major, code in DHV_MAJORS_2026:
            with self.subTest(major=major):
                for question in (
                    f"{major} là ngành gì?",
                    f"{normalize_question(major)} la nganh gi?",
                    f"Mã ngành {code} là ngành gì?",
                ):
                    result = ask_chatbot(
                        question,
                        retriever=_retriever(),
                        llm=EchoEvidenceLLM(),
                    )
                    entities = result["trace"]["entities"]
                    self.assertEqual(entities["major_name"], major)
                    self.assertEqual(entities["major_code"], code)
                    self.assertEqual(entities["entity_type"], "major")
                    self.assertEqual(result["trace"]["router"]["categories"], ["nganh_dao_tao"])

    def test_declared_programs_resolve_and_keep_evidence_parent(self) -> None:
        evidence = build_evidence(_fixture_chunks())
        relation_by_program = {
            relation["program_name"]: relation["parent_major"]
            for relation in evidence.entity_relations
        }
        relation_by_normalized_program = {
            normalize_question(relation["program_name"]): relation["parent_major"]
            for relation in evidence.entity_relations
        }
        for program, parent_major in DHV_PROGRAM_PARENTS_2026:
            with self.subTest(program=program):
                analysis = analyze_question(f"{program} thuộc ngành nào?")
                self.assertEqual(analysis.entities["program_name"], program)
                self.assertEqual(analysis.entities["entity_type"], "program")
                enriched = enrich_analysis_from_evidence(analysis, evidence)
                self.assertEqual(enriched.entities["parent_major"], parent_major)
                self.assertEqual(
                    relation_by_program.get(program)
                    or relation_by_normalized_program.get(normalize_question(program)),
                    parent_major,
                )

    def test_golden_intent_and_entity_extraction(self) -> None:
        for case in GOLDEN_CASES:
            with self.subTest(case=case["id"]):
                state = ConversationState.from_value(case.get("state"), default_year=2026)
                analysis = analyze_question(case["question"], state)
                self.assertEqual(analysis.intent, case["expected_intent"])
                for path, expected in case.get("expected_entities", {}).items():
                    self.assertEqual(_path_value(analysis.entities, path), expected)

    def test_router_clarifies_ambiguous_score_without_retrieval(self) -> None:
        analysis = analyze_question("Công nghệ thông tin lấy bao nhiêu điểm?")
        plan = route_question(analysis, target_year=2026)
        self.assertEqual(analysis.intent, "HOI_NGUONG_DAU_VAO")
        self.assertTrue(plan.needs_clarification)
        self.assertEqual(plan.categories, ("nganh_dao_tao", "nguong_dau_vao"))

    def test_catalog_list_intents_distinguish_majors_and_programs(self) -> None:
        major_analysis = analyze_question("bạn có thể liệt kê những ngành đó ra không")
        self.assertEqual(major_analysis.intent, "DANH_SACH_NGANH")
        self.assertEqual(
            route_question(major_analysis).categories,
            ("nganh_dao_tao",),
        )

        program_analysis = analyze_question("liệt kê các chương trình đào tạo")
        self.assertEqual(program_analysis.intent, "DANH_SACH_CHUONG_TRINH")
        self.assertEqual(
            route_question(program_analysis).categories,
            ("nganh_dao_tao",),
        )


class TaskFRetrievalTests(unittest.TestCase):
    def test_hybrid_retrieval_recovers_exact_code_and_audits_top_k(self) -> None:
        result = _retriever().retrieve_with_audit(
            "7480201 là ngành gì?",
            categories=("nganh_dao_tao",),
            retrieval_query="7480201 là ngành gì?",
        )
        self.assertTrue(result.documents)
        joined = " ".join(document.page_content for document in result.documents)
        self.assertIn("7480201", joined)
        self.assertIn("Công nghệ thông tin", joined)
        self.assertEqual(result.audit.hits[0]["category"], "nganh_dao_tao")
        self.assertEqual(result.audit.hits[0]["rank"], 1)
        self.assertIn("keyword_score", result.audit.hits[0])

    def test_golden_retrieval_has_expected_evidence_in_top_k(self) -> None:
        for case in GOLDEN_CASES:
            if case["expected_status"] != "ok":
                continue
            state = ConversationState.from_value(case.get("state"), default_year=2026)
            analysis = analyze_question(case["question"], state)
            plan = route_question(analysis, state, target_year=2026)
            result = _retriever().retrieve_with_audit(
                case["question"],
                categories=plan.categories,
                retrieval_query=plan.retrieval_query,
            )
            joined = " ".join(document.page_content for document in result.documents)
            expected = case["expected_evidence"]
            evidence_hit = expected["category"] in {
                document.metadata.get("category") for document in result.documents
            } and all(term in joined for term in expected["contains"])
            with self.subTest(case=case["id"]):
                self.assertTrue(evidence_hit, result.audit.to_dict())


class TaskFGenerationTests(unittest.TestCase):
    def test_method_count_followup_lists_all_five_verified_methods(self) -> None:
        llm = EchoEvidenceLLM()
        first = ask_chatbot(
            "Có bao nhiêu phương thức xét tuyển?",
            retriever=_retriever(),
            llm=llm,
        )
        second = ask_chatbot(
            "Nêu rõ những phương thức xét tuyển đó là gì?",
            retriever=_retriever(),
            llm=llm,
            conversation_state=first["state"],
        )

        self.assertEqual(first["status"], "ok")
        self.assertIn("5 phương thức", str(first["answer"]))
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["trace"]["router"]["query_mode"], "LIST")
        method_facts = [
            fact
            for fact in second["trace"]["score_facts"]
            if fact.get("score_type") == "admission_method"
        ]
        self.assertEqual(
            sorted(fact.get("method_number") for fact in method_facts),
            [1, 2, 3, 4, 5],
        )
        answer = str(second["answer"])
        for method in (
            "kỳ thi tốt nghiệp THPT",
            "học bạ",
            "Đánh giá năng lực",
            "H-SCA",
            "tốt nghiệp trung cấp",
        ):
            with self.subTest(method=method):
                self.assertIn(method.casefold(), answer.casefold())
        self.assertEqual(llm.prompts, [])

    def test_method_conditions_followup_answers_all_methods_without_treating_just_now_as_current(self) -> None:
        llm = EchoEvidenceLLM()
        first = ask_chatbot(
            "Có bao nhiêu phương thức xét tuyển?",
            retriever=_retriever(),
            llm=llm,
        )
        listed = ask_chatbot(
            "Nêu rõ những phương thức xét tuyển đó là gì?",
            retriever=_retriever(),
            llm=llm,
            conversation_state=first["state"],
        )
        conditions = ask_chatbot(
            "Vậy điều kiện của những phương thức đó là gì?",
            retriever=_retriever(),
            llm=llm,
            conversation_state=listed["state"],
        )
        explicit_conditions = ask_chatbot(
            "Điều kiện của 5 phương thức xét tuyển bạn vừa nêu lúc nãy",
            retriever=_retriever(),
            llm=llm,
            conversation_state=listed["state"],
        )

        self.assertEqual(listed["state"]["last_listed_methods"], [
            "thpt", "hoc_ba", "dgnl", "h_sca", "trung_cap",
        ])
        for result in (conditions, explicit_conditions):
            trace = result["trace"]
            self.assertEqual(result["status"], "ok", str({
                **{
                    key: trace.get(key)
                    for key in ("intent", "entities", "router", "evidence_count", "evidence_boundary")
                },
                "selected": [
                    item.get("content_preview")
                    for item in trace.get("evidence_selection", {}).get("selected", [])
                ],
            }))
            self.assertFalse(result["trace"].get("temporal_checked", False))
            self.assertNotIn("đã hết hạn", str(result["answer"]))
            for method in (
                "Thi tốt nghiệp THPT",
                "Học bạ THPT",
                "Đánh giá năng lực",
                "H-SCA",
                "Tốt nghiệp trung cấp",
            ):
                with self.subTest(method=method):
                    self.assertIn(method.casefold(), str(result["answer"]).casefold())

    def test_method_list_followup_returns_verified_thpt_score_formula(self) -> None:
        llm = EchoEvidenceLLM()
        state: dict[str, object] = {}
        first = ask_chatbot(
            "trường có bao nhiêu phương thức xét, và hãy liệt kê chi tiết về những phương thức xét tuyển đấy",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )
        state = dict(first["state"])
        second = ask_chatbot(
            "xét kết quả kỳ thi tốt nghiệp THPT thì xét điểm như nào",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )

        trace = second["trace"]
        self.assertEqual(first["status"], "ok")
        self.assertIn("có 5 phương thức", first["answer"])
        self.assertEqual(trace["intent"], "HOI_CACH_TINH_DIEM")
        self.assertEqual(trace["entities"]["admission_method"], "thpt")
        self.assertEqual(trace["router"]["categories"], ["phuong_thuc_xet_tuyen"])
        self.assertEqual(trace["retrieval_calls"], 1)
        self.assertGreater(trace["retrieved_docs_count"], 0)
        self.assertGreater(trace["evidence_count"], 0)
        self.assertEqual(trace["final_status"], "ok")
        self.assertEqual(trace["evidence_direct_answer"]["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertIn("tổng điểm 03 môn", second["answer"].casefold())
        self.assertIn("Toán + 02 môn có điểm cao nhất", second["answer"])
        self.assertIn("Ngữ văn + 02 môn có điểm cao nhất", second["answer"])
        self.assertEqual(llm.prompts, [])
        self.assertEqual(
            second["sources"],
            [{
                "title": "Điều kiện và phương thức xét tuyển DHV 2026",
                "url": "https://dhv.edu.vn/truong-dai-hoc-hung-vuong-tp-ho-chi-minh-cong-bo-diem-san-xet-tuyen-nam-2026-trien-khai-quy-hoc-bong-75-ty-dong/",
            }],
        )

    def test_multi_issue_scholarship_retrieves_verified_policy_and_marks_partial_result(self) -> None:
        question = "CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?"
        llm = EchoEvidenceLLM()
        result = ask_chatbot(
            question,
            retriever=_retriever(),
            llm=llm,
        )

        multi_issue = result["trace"]["multi_issue"]
        subplans = multi_issue["subplans"]
        scholarship_index = next(
            index
            for index, subplan in enumerate(subplans)
            if subplan["intent"] == "HOI_HOC_BONG"
        )
        scholarship_categories = subplans[scholarship_index]["categories"]
        self.assertIn("hoc_bong", scholarship_categories)
        self.assertEqual(scholarship_categories, ["hoc_bong"])
        self.assertNotIn("ho_so", scholarship_categories)
        self.assertGreater(multi_issue["retrieved_docs_counts"][scholarship_index], 0)
        self.assertGreater(multi_issue["evidence_counts"][scholarship_index], 0)
        self.assertEqual(multi_issue["statuses"][scholarship_index], "ok")
        scholarship_answer = result["answer"].split("### Học bổng\n", 1)[1].split("\n### ", 1)[0]
        self.assertIn("Học bổng tuyển sinh", scholarship_answer)
        self.assertIn("Học bổng Đôi bạn cùng tiến", scholarship_answer)
        self.assertNotIn("TÊN NGÀNH", scholarship_answer)
        self.assertNotIn("Công nghệ phần mềm", scholarship_answer)
        self.assertFalse(
            {"major_name", "major_code", "program_name", "parent_major", "candidate_majors", "candidate_programs"}
            & set(subplans[scholarship_index]["entity_filters"])
        )
        scholarship_selected = multi_issue["evidence_selections"][scholarship_index]["selected"]
        self.assertTrue(
            any(
                item.get("category") == "hoc_bong"
                and "học bổng" in str(item.get("content_preview") or "").casefold()
                for item in scholarship_selected
            )
        )
        self.assertEqual(llm.prompts, [])
        # A semester total is not a per-major tuition quote; show the verified
        # per-credit rate instead of implying 10 credits is universal.
        tuition_answer = result["answer"].split("### Học phí\n", 1)[1].split("\n### ", 1)[0]
        self.assertIn("1.250.000 đồng/tín chỉ", tuition_answer)
        self.assertNotIn("12.500.000", tuition_answer)
        self.assertFalse(result["partial"])
        self.assertFalse(multi_issue["partial"])
        self.assertTrue(multi_issue["complete"])
        self.assertEqual(multi_issue["statuses"], ["ok", "ok", "ok"])

    def test_single_issue_major_scholarship_question_uses_policy_not_program_table(self) -> None:
        question = "CNTT có học bổng gì?"
        analysis = analyze_question(question)
        plan = route_question(analysis)
        llm = EchoEvidenceLLM()

        result = ask_chatbot(question, retriever=_retriever(), llm=llm)

        self.assertEqual(analysis.intent, "HOI_HOC_BONG")
        self.assertEqual(analysis.entities["query_mode"], "LIST")
        self.assertEqual(plan.query_mode, "LIST")
        self.assertFalse(
            {"major_name", "major_code", "program_name", "parent_major", "candidate_majors", "candidate_programs"}
            & set(plan.entity_filters)
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("Học bổng tuyển sinh", result["answer"])
        self.assertIn("Học bổng Ngành Tiên phong", result["answer"])
        self.assertNotIn("TÊN NGÀNH", result["answer"])
        self.assertNotIn("Công nghệ phần mềm", result["answer"])
        selected = result["trace"]["evidence_selection"]["selected"]
        self.assertTrue(selected)
        self.assertFalse(
            any(
                all(
                    marker in normalize_question(str(item.get("content_preview") or ""))
                    for marker in ("ten nganh", "chuong trinh dao tao", "ma nganh")
                )
                for item in selected
            )
        )
        self.assertEqual(llm.prompts, [])

    def test_advisory_does_not_generate_personal_fit_without_verified_evidence(self) -> None:
        llm = SequenceLLM(
            [
                (
                    "Truyền thông đa phương tiện thuộc ngành Kỹ thuật máy tính, "
                    "nằm trong ngành cha Công nghệ thông tin."
                ),
                (
                    "Truyền thông đa phương tiện là chương trình thuộc ngành Công nghệ thông tin; "
                    "Kỹ thuật máy tính là ngành còn lại bạn đang cân nhắc."
                ),
            ]
        )

        result = ask_chatbot(
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "clarification")
        self.assertEqual(len(llm.prompts), 0)
        self.assertIn("thuộc ngành Công nghệ thông tin", result["answer"])
        self.assertNotIn("thuộc ngành Kỹ thuật máy tính", result["answer"])
        self.assertEqual(
            result["trace"]["advisory_boundary"],
            "personal_fit_not_in_verified_evidence",
        )

    def test_direct_fit_evidence_must_be_verified_dhv_and_current_year(self) -> None:
        analysis = analyze_question(
            "Tôi thích edit video, chương trình Truyền thông đa phương tiện có phù hợp không?"
        )
        state = ConversationState(current_year=2026)

        def evidence_for(
            *,
            status: str = "verified",
            year: int = 2026,
            school_code: str = "DHV",
            text: str = "Chương trình Truyền thông đa phương tiện phù hợp với người thích edit video.",
        ) -> Any:
            return build_evidence(
                [
                    Document(
                        page_content=text,
                        metadata={
                            "status": status,
                            "year": year,
                            "school_code": school_code,
                            "source_url": "https://tuyensinh.dhv.edu.vn/chuong-trinh",
                        },
                    )
                ]
            )

        self.assertTrue(
            _has_verified_advisory_fit_evidence(
                analysis, evidence_for(), state, target_year=2026
            )
        )
        self.assertFalse(
            _has_verified_advisory_fit_evidence(
                analysis, evidence_for(status="unverified"), state, target_year=2026
            )
        )
        self.assertFalse(
            _has_verified_advisory_fit_evidence(
                analysis, evidence_for(year=2025), state, target_year=2026
            )
        )
        self.assertFalse(
            _has_verified_advisory_fit_evidence(
                analysis,
                evidence_for(
                    text="Chương trình Truyền thông đa phương tiện không phù hợp với người thích edit video."
                ),
                state,
                target_year=2026,
            )
        )
        self.assertFalse(
            _has_verified_advisory_fit_evidence(
                analysis,
                evidence_for(school_code="OTHER"),
                state,
                target_year=2026,
            )
        )

    def test_advisory_rejects_named_major_and_organization_outside_evidence(self) -> None:
        class UnsafeLLM:
            called = False

            def generate(self, _: str) -> str:
                self.called = True
                return "Luật có ngưỡng ĐGNL 600 điểm; Đại học Quốc gia TP.HCM có thông tin liên quan."

        llm = UnsafeLLM()
        result = ask_chatbot(
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không",
            retriever=_retriever(),
            llm=llm,
        )

        self.assertEqual(result["status"], "clarification")
        self.assertTrue(result["sources"])
        self.assertEqual(result["trace"]["advisory_boundary"], "personal_fit_not_in_verified_evidence")
        self.assertFalse(llm.called)

    def test_generation_is_separate_and_echo_is_grounded(self) -> None:
        llm = EchoEvidenceLLM()
        for case in GOLDEN_CASES:
            if case["expected_status"] != "ok":
                continue
            with self.subTest(case=case["id"]):
                state = ConversationState.from_value(case.get("state"), default_year=2026)
                analysis = analyze_question(case["question"], state)
                result = ask_chatbot(
                    case["question"],
                    retriever=_retriever(),
                    llm=llm,
                    conversation_state=state,
                )
                if analysis.intent == "TU_VAN_CHON_NGANH":
                    self.assertEqual(result["status"], "clarification")
                    self.assertNotIn("mình nghiêng về", str(result["answer"]).casefold())
                    if analysis.entities.get("interest"):
                        self.assertIn("chưa nêu căn cứ để kết luận", str(result["answer"]))
                else:
                    self.assertEqual(result["status"], "ok")
                answer = str(result["answer"])
                for claim in case.get("forbidden_claims", []):
                    self.assertNotIn(claim, answer)
                self.assertTrue(result["sources"])

    def test_threshold_lookup_uses_verified_structured_answer(self) -> None:
        llm = SequenceLLM([])
        result = ask_chatbot(
            "Điểm sàn CNTT 2026",
            retriever=_retriever(),
            llm=llm,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(llm.prompts), 0)
        self.assertEqual(
            result["trace"]["deterministic_branch"],
            "application_threshold_lookup",
        )
        self.assertIn("15 điểm", result["answer"])

    def test_personal_admission_guarantee_is_rejected(self) -> None:
        class UnsafeLLM:
            called = False

            def generate(self, _: str) -> str:
                self.called = True
                return "Công nghệ thông tin và Truyền thông đa phương tiện, bạn chắc chắn đậu."

        llm = UnsafeLLM()
        result = ask_chatbot(
            "Tôi 19 điểm thích edit video nên chọn ngành nào?",
            retriever=_retriever(),
            llm=llm,
        )
        self.assertEqual(result["status"], "clarification")
        self.assertTrue(result["sources"])
        self.assertEqual(result["trace"]["advisory_boundary"], "personal_fit_not_in_verified_evidence")
        self.assertFalse(llm.called)

    def test_wrong_program_major_code_is_rejected(self) -> None:
        class WrongRelationLLM:
            def generate(self, _: str) -> str:
                return "Truyền thông đa phương tiện thuộc mã ngành 7340101, thuộc nhóm ngành Công nghệ thông tin."

        result = ask_chatbot(
            "truyền thông đa phương tiện thì sao?",
            retriever=_retriever(),
            llm=WrongRelationLLM(),
            conversation_state={"current_major": "Công nghệ thông tin", "current_year": 2026},
        )
        # The evidence path can safely replace the model's bad draft with the
        # verified program-to-major relation. The contract is to reject the
        # invented 7340101 claim, not to reject a correct grounded answer.
        self.assertEqual(result["status"], "ok")
        self.assertIn("Công nghệ thông tin", result["answer"])
        self.assertIn("7480201", result["answer"])
        self.assertNotIn("7340101", result["answer"])
        self.assertTrue(result["sources"])


class TaskFConversationTests(unittest.TestCase):
    def test_two_turn_screenshot_lists_verified_majors_and_corrects_count_followup(self) -> None:
        retriever = RecordingRetriever(_fixture_chunks())
        # This is intentionally a realistic bad draft: the returned answer
        # must be owned by structured evidence, not by this model output.
        llm = RecordingLLM(
            "1. Quản trị thương mại điện tử\n2. Quản trị Logistics\n"
            "3. Kỹ thuật máy tính"
        )
        first = ask_chatbot(
            "bạn có thể liệt kê những ngành đó ra không",
            retriever=retriever,
            llm=llm,
        )
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["trace"]["intent"], "DANH_SACH_NGANH")
        first_rows = re.findall(
            r"^\d+\. (.+?) — mã ngành (\d+)$",
            str(first["answer"]),
            re.MULTILINE,
        )
        self.assertEqual(first_rows, list(DHV_MAJORS_2026))
        self.assertEqual(first["state"]["last_list_count"], 20)
        self.assertEqual(first["state"]["last_listed_majors"], [major for major, _ in DHV_MAJORS_2026])
        self.assertNotIn("Quản trị Logistics", first["answer"])
        self.assertNotIn("Quản trị thương mại điện tử", first["answer"])
        self.assertEqual(first["state"], first["conversation_state"])

        second = ask_chatbot(
            "bạn nói có 12 ngành sao liệt kê có 10 ngành à",
            retriever=retriever,
            llm=llm,
            conversation_state=first["conversation_state"],
        )
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["trace"]["intent"], "DANH_SACH_NGANH")
        self.assertIn("Mình đính chính", second["answer"])
        self.assertIn("20 ngành chính", second["answer"])
        second_rows = re.findall(
            r"^\d+\. (.+?) — mã ngành (\d+)$",
            str(second["answer"]),
            re.MULTILINE,
        )
        self.assertEqual(second_rows, list(DHV_MAJORS_2026))
        self.assertEqual(second["state"]["last_list_count"], 20)
        self.assertEqual(second["state"], second["conversation_state"])
        self.assertEqual(
            [call["categories"] for call in retriever.calls],
            [("nganh_dao_tao",), ("nganh_dao_tao",)],
        )

    def test_program_catalog_lists_children_with_parent_major(self) -> None:
        result = ask_chatbot(
            "liệt kê các chương trình đào tạo",
            retriever=RecordingRetriever(_fixture_chunks()),
            llm=RecordingLLM("Quản trị Logistics là một ngành."),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["intent"], "DANH_SACH_CHUONG_TRINH")
        self.assertIn("Quản trị Logistics — thuộc ngành Quản trị kinh doanh", result["answer"])
        self.assertNotIn("Quản trị Logistics là một ngành", result["answer"])
        self.assertNotIn("mã ngành Quản trị Logistics", result["answer"])

    def test_list_followup_without_the_word_major_uses_previous_catalog_state(self) -> None:
        result = ask_chatbot(
            "danh sách trên chưa đủ",
            retriever=RecordingRetriever(_fixture_chunks()),
            llm=RecordingLLM("Không tìm thấy dữ liệu."),
            conversation_state={
                "previous_intent": "DANH_SACH_NGANH",
                "last_listed_majors": [major for major, _ in DHV_MAJORS_2026[:10]],
                "last_list_count": 10,
            },
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("Mình đính chính", result["answer"])
        self.assertIn("20 ngành chính", result["answer"])

    def test_advisory_keeps_two_non_program_candidates_without_parent_claim(self) -> None:
        question = "Tôi phân vân giữa Marketing và Tâm lý học, chưa biết chọn ngành nào"
        result = ask_chatbot(
            question,
            retriever=_retriever(),
            llm=EchoEvidenceLLM(),
        )

        self.assertEqual(result["status"], "clarification")
        self.assertEqual(result["trace"]["advisory_boundary"], "personal_fit_not_in_verified_evidence")
        self.assertEqual(
            result["state"]["candidate_majors"],
            ["Marketing", "Tâm lý học"],
        )
        self.assertIsNone(result["state"]["current_major"])
        self.assertIsNone(result["trace"]["entities"]["parent_major"])
        self.assertNotIn("thuộc ngành", result["answer"].casefold())

    def test_ollama_like_quoted_relation_and_grounded_major_list(self) -> None:
        state: dict[str, object] = {}
        llm = SequenceLLM(
            [
                (
                    '"Truyền thông đa phương tiện" thuộc ngành "Kỹ thuật máy tính", '
                    'nằm trong ngành cha "Công nghệ thông tin".'
                ),
                '"Truyền thông đa phương tiện" là chương trình thuộc ngành "Công nghệ thông tin".',
                (
                    "Các ngành phù hợp gồm: Kỹ thuật máy tính, Công nghệ thông tin, "
                    "Công nghệ tài chính, Kế toán, Tài chính ngân hàng. Với ĐGNL 720, "
                    "bạn có thể tham khảo ngưỡng 600 điểm."
                ),
            ]
        )
        first = ask_chatbot(
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )
        self.assertEqual(first["status"], "clarification")
        self.assertEqual(first["trace"]["advisory_boundary"], "personal_fit_not_in_verified_evidence")
        self.assertNotIn("thuộc ngành Kỹ thuật máy tính", first["answer"])
        self.assertNotIn("phù hợp", first["answer"].casefold())
        self.assertIn("Bạn thích sáng tạo nội dung số hay tìm hiểu AI/IoT", first["answer"])
        state = dict(first["state"])

        second = ask_chatbot(
            "Tôi thi tốt nghiệp xong điểm tôi đây: Toán: 8 Văn: 7 Anh: 7.5 ĐGNL: 720 Sở thích: edit video nhưng chưa biết chọn ngành nào",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )

        self.assertEqual(second["status"], "clarification")
        self.assertTrue(second["sources"])
        self.assertEqual(len(llm.prompts), 0)

    def test_advisory_fallback_keeps_verified_context_when_candidate_filter_is_empty(self) -> None:
        class CandidateMissRetriever:
            def retrieve_with_audit(self, *_: object, **__: object) -> dict[str, object]:
                return {
                    "documents": [
                        Document(
                            page_content="Kỹ thuật máy tính; Truyền thông đa phương tiện",
                            metadata={"status": "unverified", "source_url": "https://fake.invalid"},
                        ),
                        Document(
                            page_content=(
                                "Ngưỡng đảm bảo chất lượng đầu vào (điểm sàn) năm 2026:\n"
                                "Xét kết quả kỳ thi tốt nghiệp THPT: từ 15 điểm.\n"
                                "Xét kết quả học tập THPT (học bạ): từ 18 điểm.\n"
                                "Xét kết quả kỳ thi đánh giá năng lực: từ 600 điểm."
                            ),
                            metadata={
                                "title": "Ngưỡng đầu vào DHV 2026",
                                "category": "nguong_dau_vao",
                                "year": 2026,
                                "school_code": "DHV",
                                "source_url": "https://dhv.edu.vn/threshold",
                                "status": "verified",
                                "chunk_id": "generic-threshold",
                            },
                        ),
                    ]
                }

        llm = SequenceLLM([FALLBACK_ANSWER, "Bạn muốn biết điểm sàn, điểm trúng tuyển hay điểm xét tuyển bổ sung?"])
        result = ask_chatbot(
            "Tôi thi tốt nghiệp xong điểm tôi đây: Toán: 8 Văn: 7 Anh: 7.5 ĐGNL: 720 Sở thích: edit video nhưng chưa biết chọn ngành nào",
            retriever=CandidateMissRetriever(),
            llm=llm,
            conversation_state={
                "current_year": 2026,
                "candidate_majors": ["Kỹ thuật máy tính", "Công nghệ thông tin"],
                "candidate_programs": ["Truyền thông đa phương tiện"],
            },
        )

        self.assertEqual(result["status"], "clarification")
        self.assertTrue(result["sources"])
        self.assertEqual(len(llm.prompts), 0)

    def test_two_turn_multiple_choices_then_scores_keeps_candidates_and_grounding(self) -> None:
        state: dict[str, object] = {}
        llm = SequenceLLM(
            [
                (
                    "Bạn đang cân nhắc Kỹ thuật máy tính và Truyền thông đa phương tiện. "
                    "Truyền thông đa phương tiện là chương trình thuộc ngành Công nghệ thông tin."
                ),
                (
                    "Với sở thích edit video, Truyền thông đa phương tiện là chương trình "
                    "thuộc ngành Công nghệ thông tin; Kỹ thuật máy tính là ngành còn lại bạn "
                    "đang cân nhắc. Điểm ĐGNL của bạn là 720, so với ngưỡng nhận hồ sơ từ "
                    "600 điểm; đây không phải kết luận trúng tuyển."
                ),
            ]
        )
        turns = [
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không",
            "Tôi thi tốt nghiệp xong điểm tôi đây: Toán: 8 Văn: 7 Anh: 7.5 ĐGNL: 720 Sở thích: edit video nhưng chưa biết chọn ngành nào",
        ]

        first = ask_chatbot(
            turns[0],
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )
        self.assertEqual(first["status"], "clarification")
        state = dict(first["state"])
        self.assertIsNone(first["trace"]["entities"]["major_name"])
        self.assertIsNone(first["trace"]["entities"]["program_name"])
        self.assertIsNone(first["trace"]["entities"]["parent_major"])
        self.assertNotIn("thuộc ngành Kỹ thuật máy tính", first["answer"])
        self.assertIsNone(state["current_major"])
        self.assertIsNone(state["current_program"])
        self.assertEqual(
            state["candidate_majors"],
            ["Kỹ thuật máy tính", "Công nghệ thông tin"],
        )
        self.assertEqual(state["candidate_programs"], ["Truyền thông đa phương tiện"])

        second = ask_chatbot(
            turns[1],
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )

        self.assertEqual(second["status"], "clarification")
        self.assertTrue(second["sources"])
        self.assertIsNone(second["trace"]["entities"]["major_name"])
        self.assertIsNone(second["trace"]["entities"]["program_name"])
        self.assertEqual(
            second["state"]["candidate_programs"], ["Truyền thông đa phương tiện"]
        )
        self.assertIsNone(second["state"]["current_major"])
        self.assertIsNone(second["state"]["current_program"])
        self.assertEqual(second["state"]["interest"], "edit video")
        self.assertEqual(
            second["state"]["student_scores"],
            {"thpt_subjects": {"toan": 8, "van": 7, "anh": 7.5}, "dgnl": 720},
        )
        self.assertEqual(
            second["trace"]["score_comparisons"],
            [
                {
                    "method": "dgnl",
                    "student_value": 720,
                    "threshold_value": 600,
                    "operator": ">=",
                    "meets_threshold": True,
                }
            ],
        )
        self.assertEqual(second["trace"]["advisory_boundary"], "personal_fit_not_in_verified_evidence")
        self.assertEqual(llm.prompts, [])
        self.assertIn("Kỹ thuật máy tính", second["answer"])
        self.assertIn("Truyền thông đa phương tiện", second["answer"])
        self.assertNotIn("là ngành độc lập", second["answer"])
        self.assertNotIn("mình nghiêng về", second["answer"].casefold())
        self.assertIn("chưa nêu căn cứ để kết luận", second["answer"])

    def test_realistic_two_turn_rejected_drafts_fall_back_to_grounded_clarification(self) -> None:
        state: dict[str, object] = {}
        llm = SequenceLLM(
            [
                (
                    "Bạn có thể tham khảo chương trình Truyền thông đa phương tiện "
                    "thuộc ngành Kỹ thuật máy tính (7480106), còn Kỹ thuật máy tính "
                    "gồm Hệ thống nhúng thông minh và AI và IoT ứng dụng."
                ),
                (
                    "Bạn có thể tham khảo chương trình Truyền thông đa phương tiện "
                    "thuộc ngành Kỹ thuật máy tính (7480106), còn Kỹ thuật máy tính "
                    "gồm Hệ thống nhúng thông minh và AI và IoT ứng dụng."
                ),
                (
                    "Theo dữ liệu, bạn đã đủ điều kiện với ĐGNL 720 và nên chọn Luật; "
                    "Truyền thông đa phương tiện thuộc ngành Kỹ thuật máy tính."
                ),
                (
                    "Theo dữ liệu, bạn đã đủ điều kiện với ĐGNL 720 và nên chọn Luật; "
                    "Truyền thông đa phương tiện thuộc ngành Kỹ thuật máy tính."
                ),
            ]
        )
        first = ask_chatbot(
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )
        self.assertEqual(first["status"], "clarification")
        self.assertIn(
            "Truyền thông đa phương tiện là chương trình thuộc ngành Công nghệ thông tin",
            first["answer"],
        )
        self.assertNotIn("thuộc ngành Kỹ thuật máy tính", first["answer"])
        self.assertNotIn("chưa tự quyết định thay bạn", first["answer"])
        self.assertNotIn("hệ thống chưa", first["answer"].casefold())
        self.assertNotIn("Luật", first["answer"])
        self.assertNotIn("ĐHQG", first["answer"])
        self.assertIn("Bạn thích sáng tạo nội dung số hay tìm hiểu AI/IoT", first["answer"])
        state = dict(first["state"])

        second = ask_chatbot(
            "Tôi thi tốt nghiệp xong điểm tôi đây: Toán: 8 Văn: 7.5 Anh: 7.5 ĐGNL: 720 Sở thích: edit video nhưng chưa biết chọn ngành nào",
            retriever=_retriever(),
            llm=llm,
            conversation_state=state,
        )
        self.assertEqual(second["status"], "clarification")
        self.assertIn("ĐGNL", second["answer"])
        self.assertNotIn("Luật", second["answer"])
        self.assertNotIn("thuộc ngành Kỹ thuật máy tính", second["answer"])
        self.assertNotIn("chưa tự quyết định thay bạn", second["answer"])
        self.assertNotIn("hệ thống chưa", second["answer"].casefold())
        self.assertNotIn("ĐHQG", second["answer"])
        self.assertNotIn("mình nghiêng về", second["answer"].casefold())
        self.assertIn("chưa nêu căn cứ để kết luận", second["answer"])
        self.assertIn("Công nghệ thông tin (mã ngành 7480201)", second["answer"])
        self.assertIn("Kỹ thuật máy tính (mã ngành 7480106)", second["answer"])
        self.assertIn("Hệ thống nhúng thông minh", second["answer"])
        self.assertIn("AI và IoT ứng dụng", second["answer"])
        self.assertIn("Công nghệ thông tin", second["answer"])
        self.assertEqual(second["state"]["candidate_programs"], ["Truyền thông đa phương tiện"])
        self.assertEqual(second["state"]["student_scores"]["dgnl"], 720)

    def test_chat_service_passes_state_after_first_clarification(self) -> None:
        llm = SequenceLLM(
            [
                "Truyền thông đa phương tiện thuộc ngành Kỹ thuật máy tính (7480106).",
                "Truyền thông đa phương tiện thuộc ngành Kỹ thuật máy tính (7480106).",
                (
                    "Theo dữ liệu tuyển sinh năm 2026 của Trường Đại học Hùng Vương TP.HCM, "
                    "bạn đã vượt qua ngưỡng điểm sàn với ĐGNL 720 so với ngưỡng 600. "
                    "Với sở thích edit video, Truyền thông đa phương tiện là chương trình "
                    "thuộc ngành Công nghệ thông tin. Kỹ thuật máy tính mã "
                    "7480106 gồm Hệ thống nhúng thông minh và AI và IoT ứng dụng."
                ),
            ]
        )
        service = ChatService(retriever=_retriever(), llm=llm)
        first = service.ask_chatbot(
            "tôi đang phân vân giữa truyền thông đa phương tiện và kỹ thuật máy tính nhưng không biết theo ngành nào bạn có thể tư vấn cho tôi được không"
        )
        self.assertEqual(first["status"], "clarification")
        self.assertEqual(first["conversation_state"], first["state"])

        second = service.ask_chatbot(
            "Tôi thi tốt nghiệp xong điểm tôi đây: Toán: 8 Văn: 7.5 Anh: 7.5 ĐGNL: 720 Sở thích: edit video nhưng chưa biết chọn ngành nào",
            conversation_state=first["conversation_state"],
        )
        self.assertEqual(second["status"], "clarification")
        self.assertIn("Truyền thông đa phương tiện là chương trình thuộc ngành Công nghệ thông tin", second["answer"])
        self.assertNotIn("mình nghiêng về", second["answer"].casefold())
        self.assertIn("chưa nêu căn cứ để kết luận", second["answer"])
        self.assertNotIn("Luật", second["answer"])
        self.assertEqual(second["state"]["candidate_majors"], ["Kỹ thuật máy tính", "Công nghệ thông tin"])
        self.assertEqual(second["state"]["student_scores"]["dgnl"], 720)

    def test_three_turn_conversation_keeps_program_and_threshold_context(self) -> None:
        state: dict[str, object] = {}
        llm = EchoEvidenceLLM()
        turns = [
            "Tôi vừa thi xong, ĐGNL 720, thích edit video, chưa biết chọn ngành nào",
            "truyền thông đa phương tiện thì sao?",
            "điểm đầu vào bao nhiêu?",
        ]
        results = []
        for question in turns:
            result = ask_chatbot(
                question,
                retriever=_retriever(),
                llm=llm,
                conversation_state=state,
            )
            results.append(result)
            state = dict(result["state"])

        self.assertEqual(results[0]["status"], "clarification")
        self.assertEqual(
            results[0]["trace"]["score_comparisons"],
            [
                {
                    "method": "dgnl",
                    "student_value": 720,
                    "threshold_value": 600,
                    "operator": ">=",
                    "meets_threshold": True,
                }
            ],
        )
        self.assertEqual(results[1]["status"], "ok")
        self.assertEqual(results[2]["status"], "ok")
        self.assertEqual(results[1]["trace"]["entities"]["entity_type"], "program")
        self.assertEqual(results[1]["trace"]["entities"]["parent_major"], "Công nghệ thông tin")
        self.assertEqual(state["current_major"], "Công nghệ thông tin")
        self.assertEqual(state["current_program"], "Truyền thông đa phương tiện")
        self.assertEqual(state["student_scores"]["dgnl"], 720)
        turn3_text = results[2]["answer"]
        self.assertIn("15", turn3_text)
        self.assertIn("600", turn3_text)
        self.assertEqual(results[2]["trace"]["retrieval"]["top_k"], settings.retriever_top_k)


if __name__ == "__main__":
    unittest.main()
