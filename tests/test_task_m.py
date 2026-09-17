"""Regression coverage for TASK M RAW expansion and provenance policy."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.ingestion.prepare_processed_from_raw import (
    _extract_pdf_text,
    _source_urls_from_text,
)
from src.ingestion.raw_manifest import is_official_dhv_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"


class TaskMRawDataTests(unittest.TestCase):
    def test_manifest_covers_only_official_pdf_sources(self) -> None:
        manifest_path = RAW_ROOT / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_files = sorted(RAW_ROOT.rglob("*.pdf"))
        documents = manifest["documents"]

        self.assertEqual(manifest["raw_format"], "pdf")
        self.assertEqual(len(documents), len(raw_files))
        self.assertEqual(manifest["target_year"], 2026)
        self.assertEqual(
            {entry["category"] for entry in documents}
            & {"thong_tin_truong", "nganh_dao_tao", "phuong_thuc_xet_tuyen", "dang_ky_xet_tuyen"},
            {"thong_tin_truong", "nganh_dao_tao", "phuong_thuc_xet_tuyen", "dang_ky_xet_tuyen"},
        )

        required = {
            "raw_file",
            "sha256",
            "title",
            "year",
            "date",
            "collected_at",
            "category",
            "source_url",
            "source_urls",
            "verification_status",
        }
        for entry in documents:
            self.assertTrue(required <= entry.keys(), entry)
            self.assertTrue(entry["raw_file"].endswith(".pdf"))
            self.assertEqual(entry["year"], 2026)
            self.assertEqual(entry["verification_status"], "verified")
            self.assertFalse(entry["contains_unnecessary_pii"])
            self.assertTrue(all(is_official_dhv_url(url) for url in entry["source_urls"]))
            self.assertTrue(is_official_dhv_url(entry["source_url"]))

    def test_raw_pdfs_have_official_urls_and_no_form_submission_data(self) -> None:
        for path in sorted(RAW_ROOT.rglob("*.pdf")):
            text = _extract_pdf_text(path)
            urls = _source_urls_from_text(text)
            self.assertTrue(urls, path)
            self.assertTrue(all(is_official_dhv_url(url) for url in urls), path)

        registration_text = _extract_pdf_text(
            RAW_ROOT / "dang_ky_xet_tuyen" / "dang_ky_xet_tuyen_2026.pdf"
        )
        self.assertIn("Không lưu bất kỳ dữ liệu cá nhân thực tế nào", registration_text)
        self.assertNotRegex(registration_text, r"\b\d{12}\b")

    def test_processed_metadata_and_new_career_evidence_are_present(self) -> None:
        school = json.loads(
            (
                PROJECT_ROOT
                / "data"
                / "processed"
                / "thong_tin_truong"
                / "thong_tin_truong_dhv_2026.json"
            ).read_text(encoding="utf-8")
        )
        career = json.loads(
            (
                PROJECT_ROOT
                / "data"
                / "processed"
                / "nganh_dao_tao"
                / "mo_ta_cntt_co_hoi_nghe_nghiep_2026.json"
            ).read_text(encoding="utf-8")
        )

        for document in (school, career):
            source = document["source"]
            self.assertEqual(source["verification_status"], "verified")
            self.assertEqual(source["collected_at"], "2026-09-15")
            self.assertTrue(source["source_date"])
            self.assertTrue(source["source_urls"])
            self.assertTrue(document["pages"])
        self.assertTrue(any("info@dhv.edu.vn" in page["text"] for page in school["pages"]))
        self.assertEqual(career["data_role"], "description")
        career_text = "\n".join(page["text"] for page in career["pages"])
        self.assertIn("Cơ hội nghề nghiệp", career_text)
        self.assertIn("Không suy diễn", career_text)

    def test_official_host_policy_rejects_non_dhv_and_lookalike_urls(self) -> None:
        self.assertTrue(is_official_dhv_url("https://dhv.edu.vn/"))
        self.assertTrue(is_official_dhv_url("https://tuyensinh.dhv.edu.vn/dangky"))
        self.assertFalse(is_official_dhv_url("http://dhv.edu.vn/"))
        self.assertFalse(is_official_dhv_url("https://dhv.edu.vn.evil.example/"))
        self.assertFalse(is_official_dhv_url("https://example.test/dhv"))
        self.assertFalse(is_official_dhv_url("https://user:pass@dhv.edu.vn/"))


if __name__ == "__main__":
    unittest.main()
