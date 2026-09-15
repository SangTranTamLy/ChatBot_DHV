"""Offline regression contract for the candidate-source audit."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.ingestion.raw_manifest import is_official_dhv_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_FILE = PROJECT_ROOT / "DHV_AGENT_MASTER_PLAN_UPDATED" / "08_CANDIDATE_DHV_SOURCES.md"
REPORT_FILE = PROJECT_ROOT / "reports" / "TASK_08_CANDIDATE_DHV_SOURCES_RESULT.md"

EXPECTED_URLS = (
    "https://tuyensinh.dhv.edu.vn/",
    "https://tuyensinh.dhv.edu.vn/dangky",
    "https://tec.dhv.edu.vn/",
    "https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc",
    "https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm",
    "https://law.dhv.edu.vn/",
    "https://bam.dhv.edu.vn/contact",
)


class Task08CandidateSourceTests(unittest.TestCase):
    def test_candidate_registry_has_only_expected_official_urls(self) -> None:
        text = CANDIDATE_FILE.read_text(encoding="utf-8")
        urls = tuple(dict.fromkeys(re.findall(r"https://[^\s`|)]+", text)))

        self.assertEqual(set(urls), set(EXPECTED_URLS))
        self.assertTrue(all(is_official_dhv_url(url) for url in urls))

    def test_audit_records_decisions_and_data_boundaries(self) -> None:
        candidate = CANDIDATE_FILE.read_text(encoding="utf-8")
        report = REPORT_FILE.read_text(encoding="utf-8")

        for text in (candidate, report):
            self.assertIn("15/09/2026", text)
            self.assertIn("ACCEPT", text)
            self.assertIn("LIMITED", text)
            self.assertIn("PII", text)
            self.assertIn("2023/2024", text)

        self.assertIn("DATA_CONFLICTS_2026.md", candidate)
        self.assertIn("Không lưu bất kỳ giá trị", report)
        self.assertIn("Không có data mới", report)


if __name__ == "__main__":
    unittest.main()
