"""Path validation helpers for generated ingestion outputs."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from collections.abc import Iterable

from src.config.settings import PROJECT_ROOT


DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
LOGGER = logging.getLogger(__name__)


def paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either resolved path contains the other."""

    left = Path(first).expanduser().resolve()
    right = Path(second).expanduser().resolve()
    return left == right or left in right.parents or right in left.parents


def validate_generated_directory(
    path: str | Path,
    *,
    protected_paths: Iterable[str | Path] = (),
    project_root: str | Path = PROJECT_ROOT,
    forbid_current_directory: bool = False,
) -> Path:
    """Resolve a generated directory and reject roots or protected overlaps.

    Generated outputs may live inside the project, but cannot be the project
    root, an ancestor of it, or overlap any protected source/output directory.
    Resolving first also checks existing symlinks and Windows junctions.
    """

    destination = Path(path).expanduser().resolve()
    project = Path(project_root).expanduser().resolve()
    filesystem_root = Path(destination.anchor).resolve()
    if destination == filesystem_root:
        raise ValueError(f"refusing to use a filesystem root as generated output: {destination}")
    if destination == project or destination in project.parents:
        raise ValueError(f"refusing to use the project root or its parent as generated output: {destination}")
    if forbid_current_directory and destination == Path.cwd().resolve():
        raise ValueError(f"refusing to use the current working directory as generated output: {destination}")

    for protected in protected_paths:
        protected_path = Path(protected).expanduser().resolve()
        if paths_overlap(destination, protected_path):
            raise ValueError(
                f"generated output overlaps protected path {protected_path}: {destination}"
            )
    return destination


def validate_distinct_generated_directories(*paths: str | Path) -> tuple[Path, ...]:
    """Resolve output directories and reject parent/child overlap between them."""

    resolved = tuple(Path(path).expanduser().resolve() for path in paths)
    for index, path in enumerate(resolved):
        for other in resolved[index + 1 :]:
            if paths_overlap(path, other):
                raise ValueError(f"generated output directories overlap: {path} and {other}")
    return resolved


def unique_generated_sibling(destination: str | Path, *, purpose: str) -> Path:
    """Return a unique staging/backup path beside a generated directory."""

    target = Path(destination).expanduser().resolve()
    token = uuid.uuid4().hex
    return target.with_name(f".{target.name}.{purpose}-{token}")


def publish_staged_directory(
    staging: str | Path,
    destination: str | Path,
    *,
    protected_paths: Iterable[str | Path] = (),
    project_root: str | Path = PROJECT_ROOT,
    forbid_current_directory: bool = False,
) -> Path:
    """Publish a complete sibling directory while retaining rollback data."""

    target = validate_generated_directory(
        destination,
        protected_paths=protected_paths,
        project_root=project_root,
        forbid_current_directory=forbid_current_directory,
    )
    candidate = validate_generated_directory(
        staging,
        protected_paths=(*protected_paths, target),
        project_root=project_root,
        forbid_current_directory=forbid_current_directory,
    )
    if candidate.parent != target.parent:
        raise ValueError("staging directory must be a sibling of its publish destination")
    if not candidate.is_dir():
        raise FileNotFoundError(f"staging directory does not exist: {candidate}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"publish destination is not a directory: {target}")

    backup = unique_generated_sibling(target, purpose="backup")
    backup = validate_generated_directory(
        backup,
        protected_paths=(*protected_paths, target, candidate),
        project_root=project_root,
        forbid_current_directory=forbid_current_directory,
    )

    moved_old = False
    if target.exists():
        # Re-resolve immediately before the rename so changed junction targets
        # cannot redirect the operation after validation.
        target = validate_generated_directory(
            target,
            protected_paths=protected_paths,
            project_root=project_root,
            forbid_current_directory=forbid_current_directory,
        )
        os.replace(target, backup)
        moved_old = True
    try:
        candidate = validate_generated_directory(
            candidate,
            protected_paths=(*protected_paths, target),
            project_root=project_root,
            forbid_current_directory=forbid_current_directory,
        )
        target = validate_generated_directory(
            target,
            protected_paths=protected_paths,
            project_root=project_root,
            forbid_current_directory=forbid_current_directory,
        )
        os.replace(candidate, target)
    except Exception as publish_error:
        if moved_old and backup.exists():
            try:
                target = validate_generated_directory(
                    target,
                    protected_paths=protected_paths,
                    project_root=project_root,
                    forbid_current_directory=forbid_current_directory,
                )
                os.replace(backup, target)
            except Exception as rollback_error:
                raise RuntimeError(
                    "staged publish failed and rollback could not restore the old directory; "
                    f"the preserved backup is at {backup}: {rollback_error}"
                ) from publish_error
        raise

    if moved_old and backup.exists():
        try:
            backup = validate_generated_directory(
                backup,
                protected_paths=(*protected_paths, target, candidate),
                project_root=project_root,
                forbid_current_directory=forbid_current_directory,
            )
            shutil.rmtree(backup)
        except Exception as exc:
            LOGGER.warning("published %s but could not remove verified backup %s: %s", target, backup, exc)
    return target


def cleanup_staging_directory(
    staging: str | Path,
    destination: str | Path,
    *,
    protected_paths: Iterable[str | Path] = (),
    project_root: str | Path = PROJECT_ROOT,
    forbid_current_directory: bool = False,
) -> None:
    """Remove only the staging sibling created for this destination."""

    target = Path(destination).expanduser().resolve()
    candidate = Path(staging).expanduser().resolve()
    if candidate.parent != target.parent or not candidate.name.startswith(f".{target.name}.staging-"):
        raise ValueError(f"refusing to clean a directory not owned by this build: {candidate}")
    try:
        candidate = validate_generated_directory(
            candidate,
            protected_paths=(*protected_paths, target),
            project_root=project_root,
            forbid_current_directory=forbid_current_directory,
        )
        if candidate.exists():
            shutil.rmtree(candidate)
    except Exception as exc:
        LOGGER.warning("could not remove verified staging directory %s: %s", candidate, exc)


__all__ = [
    "DEFAULT_RAW_DIR",
    "paths_overlap",
    "validate_distinct_generated_directories",
    "validate_generated_directory",
    "unique_generated_sibling",
    "publish_staged_directory",
    "cleanup_staging_directory",
]
