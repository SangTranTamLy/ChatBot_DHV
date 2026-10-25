"""Regression coverage for TASK M RAW expansion and provenance policy."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.ingestion.prepare_processed_from_raw import (
    _extract_pdf_text,
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
            {entry["category"] for entry in documents},
            {
                "co_so_lien_he",
                "diem_trung_tuyen",
                "ho_so",
                "hoc_bong",
                "hoc_phi",
                "lich_tuyen_sinh",
                "nganh_dao_tao",
                "phuong_thuc_xet_tuyen",
                "thong_tin_truong",
                "xet_tuyen_bo_sung",
            },
        )
        # Every document carries a unique reviewed retrieval role.
        roles = [entry["data_role"] for entry in documents]
        self.assertTrue(all(roles))
        self.assertEqual(len(roles), len(set(roles)))

        required = {
            "document_id",
            "raw_file",
            "title",
            "year",
            "category",
            "data_role",
            "source_url",
            "source_urls",
            "verified",
            "status",
            "source_type",
        }
        for entry in documents:
            self.assertTrue(required <= entry.keys(), entry)
            self.assertTrue(entry["raw_file"].endswith(".pdf"))
            self.assertTrue(all(is_official_dhv_url(url) for url in entry["source_urls"]))
            if entry["verified"] is True:
                self.assertEqual(entry["year"], 2026)
                self.assertEqual(entry["status"], "verified")
                self.assertTrue(is_official_dhv_url(entry["source_url"]))
            else:
                self.assertNotEqual(entry["status"], "verified")
                self.assertIsNone(entry["source_url"])

    def test_raw_pdfs_have_no_form_submission_data(self) -> None:
        manifest = json.loads((RAW_ROOT / "manifest.json").read_text(encoding="utf-8"))
        by_file = {entry["raw_file"].replace("/", "\\"): entry for entry in manifest["documents"]}
        for path in sorted(RAW_ROOT.rglob("*.pdf")):
            text = _extract_pdf_text(path)
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            entry = by_file[relative.replace("/", "\\")]
            if entry["verified"]:
                self.assertTrue(is_official_dhv_url(entry["source_url"]), path)
                self.assertTrue(
                    all(is_official_dhv_url(url) for url in entry["source_urls"]), path
                )
            self.assertNotRegex(text, r"\b\d{12}\b", path)

    def test_processed_metadata_and_new_career_evidence_are_present(self) -> None:
        processed = PROJECT_ROOT / "data" / "processed"

        def load(relative: str) -> dict:
            path = processed / relative
            if not path.exists():
                self.skipTest("data/processed is generated locally; run prepare_processed_from_raw first")
            return json.loads(path.read_text(encoding="utf-8"))

        career = load("thong_tin_truong/11_MOI_TRUONG_HOC_TAP_VA_CO_HOI_NGHE_NGHIEP_DHV_2026.json")
        catalog = load("nganh_dao_tao/02_NGANH_VA_CHUONG_TRINH_DAO_TAO_DHV_2026.json")
        methods = load("phuong_thuc_xet_tuyen/03_DIEU_KIEN_VA_PHUONG_THUC_XET_TUYEN_DHV_2026.json")

        for document in (career, catalog, methods):
            source = document["source"]
            self.assertEqual(source["verification_status"], "verified")
            self.assertTrue(source["source_urls"])
            self.assertTrue(all(is_official_dhv_url(url) for url in source["source_urls"]))
            self.assertTrue(document["data_role"])
            self.assertTrue(document["pages"])
        self.assertIn("nghề nghiệp", "\n".join(page["text"] for page in career["pages"]).casefold())
        self.assertEqual(
            sum(record.get("record_type") == "major" for record in catalog["records"]),
            20,
        )
        self.assertTrue(
            any(record.get("record_type") == "application_threshold" for record in methods["records"])
        )

    def test_official_host_policy_rejects_non_dhv_and_lookalike_urls(self) -> None:
        self.assertTrue(is_official_dhv_url("https://dhv.edu.vn/"))
        self.assertTrue(is_official_dhv_url("https://tuyensinh.dhv.edu.vn/dangky"))
        self.assertFalse(is_official_dhv_url("http://dhv.edu.vn/"))
        self.assertFalse(is_official_dhv_url("https://dhv.edu.vn.evil.example/"))
        self.assertFalse(is_official_dhv_url("https://example.test/dhv"))
        self.assertFalse(is_official_dhv_url("https://user:pass@dhv.edu.vn/"))


if __name__ == "__main__":
    unittest.main()
