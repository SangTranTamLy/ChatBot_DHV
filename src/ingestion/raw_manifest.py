"""Tạo manifest có provenance và policy cho RAW PDF của DHV."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.config.settings import PROJECT_ROOT, settings

from .prepare_processed_from_raw import (
    _collected_at_from_text,
    _data_role_from_path,
    _extract_pdf_text,
    _source_date_from_text,
    _source_urls_from_text,
    _title_from_text,
)


DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_MANIFEST = DEFAULT_RAW_DIR / "manifest.json"


def is_official_dhv_url(value: object) -> bool:
    """Chỉ chấp nhận HTTPS đến domain DHV hoặc subdomain của DHV."""

    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme.lower() == "https"
        and not parsed.username
        and not parsed.password
        and (host == "dhv.edu.vn" or host.endswith(".dhv.edu.vn"))
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _raw_entry(path: Path, *, raw_root: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"RAW file is not PDF: {path}")
    relative_category = path.parent.relative_to(raw_root).as_posix()
    if not relative_category or "/" in relative_category:
        raise ValueError(f"RAW PDF must be directly below one category directory: {path}")

    text = _extract_pdf_text(path)
    source_urls = _source_urls_from_text(text)
    if not source_urls:
        raise ValueError(f"RAW PDF has no source URL: {path}")
    if not all(is_official_dhv_url(url) for url in source_urls):
        raise ValueError(f"RAW PDF contains a non-official source URL: {path}")

    source_date = _source_date_from_text(text)
    collected_at = _collected_at_from_text(text)
    return {
        "raw_file": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": _sha256(path),
        "title": _title_from_text(text),
        "year": settings.target_year,
        "date": source_date,
        "source_date": source_date,
        "collected_at": collected_at,
        "category": relative_category,
        "data_role": _data_role_from_path(path, relative_category),
        "source_url": source_urls[0],
        "source_urls": list(source_urls),
        "verification_status": "verified",
        "status": "verified",
        "source_type": "official_website",
        "document_type": "pdf",
        "contains_unnecessary_pii": False,
    }


def build_raw_manifest(
    *,
    raw_directory: str | Path = DEFAULT_RAW_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    audited_at: str | None = None,
) -> dict[str, Any]:
    raw_root = Path(raw_directory).resolve()
    output_path = Path(manifest_path).resolve()
    if not raw_root.exists() or not raw_root.is_dir():
        raise FileNotFoundError(f"RAW directory does not exist: {raw_root}")
    if output_path == raw_root or output_path == Path(output_path.anchor):
        raise ValueError("refusing to use RAW directory or a filesystem root as manifest")

    raw_files = sorted(
        path for path in raw_root.rglob("*.pdf") if path.is_file()
    )
    if not raw_files:
        raise RuntimeError(f"no RAW PDF files found in {raw_root}")

    documents = [_raw_entry(path, raw_root=raw_root) for path in raw_files]
    manifest = {
        "manifest_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audited_at": audited_at or datetime.now().date().isoformat(),
        "target_year": settings.target_year,
        "raw_format": "pdf",
        "official_source_policy": {
            "allowed_host": "dhv.edu.vn",
            "allowed_subdomains": True,
            "require_https": True,
        },
        "privacy_policy": "Do not ingest unnecessary personal data from forms or lookup tools.",
        "documents": documents,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--audited-at", default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    manifest = build_raw_manifest(
        raw_directory=args.raw_dir,
        manifest_path=args.manifest,
        audited_at=args.audited_at,
    )
    print(
        {
            "raw_pdfs": len(manifest["documents"]),
            "manifest": str(Path(args.manifest).resolve()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_raw_manifest", "is_official_dhv_url", "main"]
