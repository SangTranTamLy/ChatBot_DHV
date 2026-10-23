"""Compound admissions questions retain their own wording and evidence."""

import unittest

from src.chatbot.query_analysis import analyze_question, route_question
from src.chatbot.rag_chain import ask_chatbot
from tests.test_runtime_contact import ContactRetriever
from tests.test_task_f import EchoEvidenceLLM, RecordingRetriever, _fixture_chunks


class MultiIssueContextTests(unittest.TestCase):
    def test_documents_destination_and_tuition_are_three_ordered_issues(self):
        plan = route_question(analyze_question("Hồ sơ cần gì, nộp ở đâu và học phí bao nhiêu?"))
        self.assertEqual([p.intent for p in plan.subplans],
                         ["HOI_HO_SO", "HOI_NHAP_HOC", "HOI_HOC_PHI"])
        self.assertIn("nộp ở đâu", plan.subplans[1].issue_question)
        self.assertNotIn("học phí", plan.subplans[1].retrieval_query)

    def test_submission_destination_does_not_create_general_campus_issue(self):
        plan = route_question(analyze_question("Hồ sơ nhập học cần gì và nộp ở cơ sở nào?"))
        self.assertEqual([p.intent for p in plan.subplans], ["HOI_HO_SO", "HOI_NHAP_HOC"])
        single = route_question(analyze_question("Nếu tôi nộp hồ sơ thì nộp ở cơ sở nào?"))
        self.assertEqual(single.intent, "HOI_NHAP_HOC")
        self.assertFalse(single.subplans)

    def test_submission_and_tuition_do_not_add_a_document_list(self):
        plan = route_question(analyze_question(
            "Nộp hồ sơ nhập học ở cơ sở nào và học phí bao nhiêu?"))
        self.assertEqual([p.intent for p in plan.subplans], ["HOI_NHAP_HOC", "HOI_HOC_PHI"])
        self.assertIn("ở cơ sở nào", plan.subplans[0].issue_question)

    def test_specific_tuition_wording_and_shared_major_are_retained(self):
        plan = route_question(analyze_question(
            "Năm 2026 ngành Luật có học bổng gì và học phí mỗi tín chỉ bao nhiêu?"))
        self.assertEqual([p.intent for p in plan.subplans], ["HOI_HOC_BONG", "HOI_HOC_PHI"])
        self.assertEqual(plan.subplans[1].issue_question, "học phí mỗi tín chỉ bao nhiêu")
        self.assertEqual(plan.subplans[1].entity_filters.get("major_name"), "Luật")
        self.assertIn("ho_so", plan.subplans[1].categories)

    def test_different_majors_do_not_leak_between_clauses(self):
        plan = route_question(analyze_question(
            "Học phí ngành Luật bao nhiêu và điểm chuẩn ngành Công nghệ thông tin thế nào?"))
        self.assertEqual([p.intent for p in plan.subplans], ["HOI_HOC_PHI", "HOI_DIEM_TRUNG_TUYEN"])
        self.assertEqual(plan.subplans[0].entity_filters.get("major_name"), "Luật")
        self.assertEqual(plan.subplans[1].entity_filters.get("major_name"), "Công nghệ thông tin")
        self.assertNotIn("Công nghệ thông tin", plan.subplans[0].retrieval_query)

    def test_each_issue_reports_only_its_own_evidence_and_status(self):
        result = ask_chatbot("CNTT học phí bao nhiêu, có học bổng gì và có những chương trình nào?",
                             retriever=RecordingRetriever(_fixture_chunks()), llm=EchoEvidenceLLM())
        trace = result["trace"]["multi_issue"]
        self.assertEqual(len(trace["issues"]), 3)
        for index, issue in enumerate(trace["issues"]):
            self.assertEqual(issue["issue_id"], f"issue_{index + 1}")
            self.assertEqual(issue["status"], trace["statuses"][index])
            self.assertEqual(issue["can_answer"], issue["status"] == "ok")
            self.assertEqual(len(issue["chunk_ids"]), trace["evidence_counts"][index])

    def test_contact_issue_does_not_inherit_unrelated_major_filter(self):
        plan = route_question(analyze_question(
            "Học phí ngành Luật bao nhiêu và trường có những cơ sở nào?"))
        contact = plan.subplans[1]
        self.assertEqual(contact.intent, "HOI_CO_SO_LIEN_HE")
        self.assertNotIn("major_name", contact.entity_filters)
        self.assertNotIn("Luật", contact.retrieval_query)

    def test_missing_tuition_does_not_hide_verified_campuses(self):
        class NeverCalled:
            def generate(self, prompt):
                raise AssertionError("Campus evidence must be formatted without generation")

        result = ask_chatbot("Trường có những cơ sở nào và học phí bao nhiêu?",
                             retriever=ContactRetriever(), llm=NeverCalled())
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["partial"])
        self.assertIn("736 Nguyễn Trãi", result["answer"])
        self.assertEqual(result["trace"]["multi_issue"]["statuses"], ["ok", "no_data"])
        issues = result["trace"]["multi_issue"]["issues"]
        self.assertTrue(issues[0]["can_answer"])
        self.assertFalse(issues[1]["can_answer"])
        self.assertEqual(issues[1]["chunk_ids"], [])
        self.assertEqual(issues[1]["sources"], [])


if __name__ == "__main__":
    unittest.main()
