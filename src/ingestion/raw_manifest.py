"""Tạo manifest có provenance và policy cho RAW PDF của DHV."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from src.config.settings import PROJECT_ROOT, settings

from .prepare_processed_from_raw import (
    _collected_at_from_text,
    _data_role_from_path,
    _extract_pdf_text,
    _source_date_from_text,
    _source_urls_from_text,
    _title_from_text,
)
from .structured_json import is_official_dhv_url


DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_MANIFEST = DEFAULT_RAW_DIR / "manifest.json"


def load_raw_manifest(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Load the provenance manifest without inspecting PDF text."""

    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError(f"invalid RAW manifest: {manifest_path}")
    return payload


def _entry_raw_path(entry: Mapping[str, Any]) -> str:
    value = str(entry.get("raw_file") or entry.get("file") or "").replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    if value.startswith("data/raw/"):
        value = value[len("data/raw/") :]
    return value


def find_manifest_entry(
    manifest: Mapping[str, Any],
    *,
    raw_path: str | Path,
    raw_root: str | Path,
) -> dict[str, Any]:
    """Find exactly one metadata entry for a RAW PDF."""

    relative = Path(raw_path).resolve().relative_to(Path(raw_root).resolve()).as_posix()
    matches = [
        dict(entry)
        for entry in manifest.get("documents", [])
        if isinstance(entry, Mapping) and _entry_raw_path(entry) == relative
    ]
    if len(matches) != 1:
        raise ValueError(f"manifest must contain exactly one entry for {relative}; found {len(matches)}")
    return matches[0]


def validate_manifest_sync(
    manifest: Mapping[str, Any],
    *,
    raw_root: str | Path,
) -> list[str]:
    """Return actionable errors for RAW/manifest coverage and metadata."""

    root = Path(raw_root).resolve()
    raw_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.pdf")
        if path.is_file()
    }
    entries = [entry for entry in manifest.get("documents", []) if isinstance(entry, Mapping)]
    entry_paths = [_entry_raw_path(entry) for entry in entries]
    errors: list[str] = []
    if len(entry_paths) != len(set(entry_paths)):
        errors.append("manifest contains duplicate raw_file entries")
    document_ids = [str(entry.get("document_id", "")).strip() for entry in entries]
    if any(not value for value in document_ids) or len(document_ids) != len(set(document_ids)):
        errors.append("manifest document_id values must be non-empty and unique")
    for path in sorted(raw_files - set(entry_paths)):
        errors.append(f"RAW PDF missing from manifest: {path}")
    for path in sorted(set(entry_paths) - raw_files):
        errors.append(f"manifest references missing RAW PDF: {path}")
    for entry in entries:
        entry_path = _entry_raw_path(entry)
        year = entry.get("year")
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
            errors.append(f"{entry_path}: manifest year must be an integer between 2000 and 2100")
        source_urls = list(entry.get("source_urls") or [])
        source_url = entry.get("source_url")
        if source_url and source_url not in source_urls:
            source_urls.insert(0, source_url)
        if not all(is_official_dhv_url(url) for url in source_urls):
            errors.append(f"{entry_path}: source URLs must be official HTTPS DHV URLs")
        status = str(entry.get("status") or entry.get("verification_status") or "").strip().lower()
        if status == "verified" and (entry.get("verified") is False or not source_url):
            errors.append(f"{entry_path}: verified entries require source_url and verified=true")
    return errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _raw_entry(
    path: Path,
    *,
    raw_root: Path,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"RAW file is not PDF: {path}")
    relative_category = path.parent.relative_to(raw_root).as_posix()
    if not relative_category or "/" in relative_category:
        raise ValueError(f"RAW PDF must be directly below one category directory: {path}")

    text = _extract_pdf_text(path)
    existing = dict(existing or {})
    source_urls = list(existing.get("source_urls") or [])
    extracted_links = list(_source_urls_from_text(text))
    source_url = existing.get("source_url")
    year = existing.get("year")
    if not isinstance(year, int):
        years = sorted({int(value) for value in re.findall(r"\b(20\d{2})\b", text)})
        year = years[-1] if len(years) == 1 else None
    source_date = str(existing.get("source_date") or existing.get("date") or "")
    if not source_date:
        try:
            source_date = _source_date_from_text(text)
        except ValueError:
            source_date = ""
    collected_at = str(existing.get("collected_at") or "")
    if not collected_at:
        try:
            collected_at = _collected_at_from_text(text)
        except ValueError:
            collected_at = ""
    if source_url and not source_urls:
        source_urls = [str(source_url)]
    status = str(existing.get("status") or existing.get("verification_status") or "").strip().lower()
    if not status:
        status = "verified" if isinstance(year, int) and source_url else (
            "missing_year" if not isinstance(year, int) else "missing_source_url"
        )
    verified = status == "verified" and bool(source_url)
    entry = {
        "document_id": str(existing.get("document_id") or path.stem),
        "raw_file": path.relative_to(PROJECT_ROOT).as_posix()
        if path.is_relative_to(PROJECT_ROOT)
        else path.relative_to(raw_root).as_posix(),
        "sha256": _sha256(path),
        "title": str(existing.get("title") or _title_from_text(text)),
        "year": year,
        "date": source_date,
        "source_date": source_date,
        "collected_at": collected_at,
        "category": str(existing.get("category") or relative_category),
        "data_role": str(existing.get("data_role") or _data_role_from_path(path, relative_category)),
        "source_url": source_url,
        "source_urls": source_urls,
        "extracted_links": extracted_links,
        "verification_status": status,
        "status": status,
        "verified": verified,
        "source_type": existing.get("source_type") or ("official_website" if source_url else "unknown"),
        "document_type": "pdf",
        "contains_unnecessary_pii": False,
    }
    return entry


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

    existing_by_path: dict[str, Mapping[str, Any]] = {}
    if output_path.exists():
        try:
            existing_manifest = load_raw_manifest(output_path)
        except (OSError, ValueError, json.JSONDecodeError):
            existing_manifest = {}
        existing_by_path = {
            _entry_raw_path(entry): entry
            for entry in existing_manifest.get("documents", [])
            if isinstance(entry, Mapping)
        }
    documents = [
        _raw_entry(
            path,
            raw_root=raw_root,
            existing=existing_by_path.get(path.relative_to(raw_root).as_posix())
            or existing_by_path.get(path.relative_to(PROJECT_ROOT).as_posix()),
        )
        for path in raw_files
    ]
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


__all__ = [
    "build_raw_manifest",
    "find_manifest_entry",
    "is_official_dhv_url",
    "load_raw_manifest",
    "main",
    "validate_manifest_sync",
]
