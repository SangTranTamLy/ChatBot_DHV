from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.build_vector_db import _reset_persist_directory, build_vector_db
from src.ingestion.path_safety import validate_generated_directory
from src.ingestion.prepare_processed_from_raw import _safe_reset_generated_directory


class IngestionPathSafetyTests(unittest.TestCase):
    def _fixture(self, temp_dir: str) -> tuple[Path, Path, Path]:
        root = Path(temp_dir) / "project"
        raw = root / "data" / "raw"
        raw.mkdir(parents=True)
        sentinel = raw / "keep.txt"
        sentinel.write_text("RAW-SENTINEL", encoding="utf-8")
        return root, raw, sentinel

    def test_processed_reset_rejects_raw_project_and_ancestor_paths_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, raw, sentinel = self._fixture(temp_dir)
            targets = (root / "data", raw, raw / "nested", root, root.parent)

            for target in targets:
                with self.subTest(target=target), patch(
                    "src.ingestion.prepare_processed_from_raw.shutil.rmtree"
                ) as remove:
                    with self.assertRaises(ValueError):
                        _safe_reset_generated_directory(
                            target, raw_root=raw, project_root=root
                        )
                    remove.assert_not_called()
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "RAW-SENTINEL")

    def test_vector_reset_rejects_raw_project_and_processed_overlap_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, raw, sentinel = self._fixture(temp_dir)
            processed = root / "data" / "processed"
            targets = (root / "data", raw, root, root.parent, processed)

            for target in targets:
                with self.subTest(target=target), patch(
                    "src.ingestion.build_vector_db.shutil.rmtree"
                ) as remove:
                    with self.assertRaises(ValueError):
                        _reset_persist_directory(
                            target,
                            data_directory=processed,
                            raw_directory=raw,
                            project_root=root,
                        )
                    remove.assert_not_called()
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "RAW-SENTINEL")

    def test_vector_output_is_validated_even_without_reset_before_loading_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, raw, _ = self._fixture(temp_dir)
            data_dir = root / "data" / "processed"

            with patch("src.ingestion.build_vector_db.load_verified_documents") as load:
                with self.assertRaises(ValueError):
                    build_vector_db(
                        data_directory=data_dir,
                        persist_directory=data_dir,
                        reset=False,
                    )
                load.assert_not_called()

    def test_symlink_alias_to_raw_is_rejected_after_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, raw, sentinel = self._fixture(temp_dir)
            alias = root / "raw-alias"
            try:
                alias.symlink_to(raw, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            with patch("src.ingestion.prepare_processed_from_raw.shutil.rmtree") as remove:
                with self.assertRaises(ValueError):
                    _safe_reset_generated_directory(alias, raw_root=raw, project_root=root)
                remove.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "RAW-SENTINEL")

    def test_separate_custom_generated_directory_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, raw, _ = self._fixture(temp_dir)
            processed = root / "data" / "processed"
            chroma = root / "data" / "chroma_db"

            resolved = validate_generated_directory(
                processed,
                protected_paths=(raw, chroma),
                project_root=root,
            )

            self.assertEqual(resolved, processed.resolve())


if __name__ == "__main__":
    unittest.main()
