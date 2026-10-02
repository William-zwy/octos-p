"""Workspace and data-copy helpers for seed integrity checks.

The helpers in this module deliberately know nothing about an application's
database schema.  They only describe ordinary files, copy a disposable
workspace, and compare or restore byte-level snapshots.  Runtime/Harness code
can consume the structured ``inconclusive`` result without guessing whether a
missing path is a valid application state.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable


EXCLUDED_NAMES = frozenset(
    {
        ".git",
        ".arc",
        "node_modules",
        "dist",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "coverage",
        ".coverage",
    }
)


def _inconclusive(reason: str, **details: object) -> dict:
    return {"status": "inconclusive", "reason": reason, **details}


def _resolve_directory(value: os.PathLike[str] | str, label: str) -> tuple[Path | None, dict | None]:
    try:
        path = Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, _inconclusive("invalid_path", path_label=label, error=str(exc))
    if not path.exists():
        return None, _inconclusive("missing_path", path_label=label, path=str(path))
    if not path.is_dir():
        return None, _inconclusive("not_directory", path_label=label, path=str(path))
    return path, None


def _relative_to(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _excluded(path: Path, root: Path) -> bool:
    relative = _relative_to(path, root)
    if relative is None:
        return True
    return any(part in EXCLUDED_NAMES for part in Path(relative).parts)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(files: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        record = files[relative]
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(int(record["size_bytes"]).to_bytes(8, "big"))
        digest.update(str(record["sha256"]).encode("ascii"))
    return digest.hexdigest()


def _iter_files(root: Path, selected: Iterable[Path]) -> tuple[list[tuple[Path, str]] | None, dict | None]:
    files: dict[str, Path] = {}
    for start in selected:
        if _excluded(start, root):
            continue
        if start.is_symlink():
            return None, _inconclusive("symlink_not_supported", path=str(start))
        if start.is_file():
            relative = _relative_to(start, root)
            if relative:
                files[relative] = start
            continue
        try:
            for current, directories, names in os.walk(start, topdown=True, followlinks=False):
                current_path = Path(current)
                if _excluded(current_path, root):
                    directories[:] = []
                    continue
                kept_directories: list[str] = []
                for name in directories:
                    candidate = current_path / name
                    if name in EXCLUDED_NAMES:
                        continue
                    if candidate.is_symlink():
                        return None, _inconclusive("symlink_not_supported", path=str(candidate))
                    kept_directories.append(name)
                directories[:] = kept_directories
                for name in names:
                    candidate = current_path / name
                    if candidate.is_symlink():
                        return None, _inconclusive("symlink_not_supported", path=str(candidate))
                    if not candidate.is_file():
                        return None, _inconclusive("non_regular_file", path=str(candidate))
                    relative = _relative_to(candidate, root)
                    if relative:
                        files[relative] = candidate
        except OSError as exc:
            return None, _inconclusive("scan_error", path=str(start), error=str(exc))
    return sorted(files.items()), None


def _selected_paths(root: Path, data_roots: Iterable[os.PathLike[str] | str]) -> tuple[list[Path] | None, dict | None]:
    values = list(data_roots or ())
    if not values:
        return [root], None
    selected: list[Path] = []
    seen: set[Path] = set()
    for raw in values:
        try:
            candidate = Path(raw)
            candidate = (root / candidate).resolve(strict=False) if not candidate.is_absolute() else candidate.resolve(strict=False)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return None, _inconclusive("invalid_data_root", value=str(raw), error=str(exc))
        relative = _relative_to(candidate, root)
        if relative is None:
            return None, _inconclusive("path_outside_root", path=str(candidate), root=str(root))
        if not candidate.exists():
            return None, _inconclusive("missing_data_root", path=str(candidate), root=str(root))
        if not candidate.is_dir() and not candidate.is_file():
            return None, _inconclusive("not_regular_data_root", path=str(candidate))
        if candidate not in seen:
            selected.append(candidate)
            seen.add(candidate)
    return selected, None


def baseline_manifest(root: os.PathLike[str] | str, data_roots: Iterable[os.PathLike[str] | str] = ()) -> dict:
    """Return a deterministic SHA-256 manifest or a structured inconclusive result."""
    resolved, error = _resolve_directory(root, "root")
    if error:
        return error
    assert resolved is not None
    selected, error = _selected_paths(resolved, data_roots)
    if error:
        return error
    assert selected is not None
    entries, error = _iter_files(resolved, selected)
    if error:
        return error
    assert entries is not None
    files: dict[str, dict[str, object]] = {}
    for relative, path in entries:
        try:
            files[relative] = {"sha256": _file_digest(path), "size_bytes": path.stat().st_size}
        except OSError as exc:
            return _inconclusive("read_error", path=str(path), error=str(exc))
    return {
        "status": "ok",
        "root": str(resolved),
        "scope": [str(path.relative_to(resolved).as_posix()) or "." for path in selected],
        "excluded_names": sorted(EXCLUDED_NAMES),
        "file_count": len(files),
        "files": files,
        "tree_sha256": _tree_digest(files),
    }


def compare_manifest(before: dict, after: dict) -> dict:
    """Compare two manifests without inferring whether a change is legitimate."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return _inconclusive("invalid_manifest")
    if before.get("status") != "ok" or after.get("status") != "ok":
        return _inconclusive("manifest_inconclusive", before_status=before.get("status"), after_status=after.get("status"))
    before_files = before.get("files")
    after_files = after.get("files")
    if not isinstance(before_files, dict) or not isinstance(after_files, dict):
        return _inconclusive("invalid_manifest_files")
    before_names = set(before_files)
    after_names = set(after_files)
    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    changed = sorted(
        name for name in before_names & after_names
        if before_files[name] != after_files[name]
    )
    unchanged = sorted((before_names & after_names) - set(changed))
    return {
        "status": "unchanged" if not (added or removed or changed) else "changed",
        "changed": bool(added or removed or changed),
        "added": added,
        "removed": removed,
        "modified": changed,
        "unchanged": unchanged,
        "before_tree_sha256": before.get("tree_sha256"),
        "after_tree_sha256": after.get("tree_sha256"),
    }


def _validate_copy_paths(source: os.PathLike[str] | str, destination: os.PathLike[str] | str) -> tuple[Path | None, Path | None, dict | None]:
    source_path, error = _resolve_directory(source, "source")
    if error:
        return None, None, error
    destination_path, error = _resolve_directory(destination, "destination")
    if error:
        return None, None, error
    assert source_path is not None and destination_path is not None
    if source_path == destination_path:
        return None, None, _inconclusive("same_path", path=str(source_path))
    if _relative_to(destination_path, source_path) is not None:
        return None, None, _inconclusive("destination_inside_source", source=str(source_path), destination=str(destination_path))
    if _relative_to(source_path, destination_path) is not None:
        return None, None, _inconclusive("source_inside_destination", source=str(source_path), destination=str(destination_path))
    return source_path, destination_path, None


def _copy_tree(source: Path, destination: Path, manifest: dict | None = None) -> dict | None:
    manifest = manifest or baseline_manifest(source)
    if manifest.get("status") != "ok":
        return manifest
    for relative in manifest["files"]:
        source_file = source / relative
        destination_file = destination / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)
    return None


def copy_disposable_workspace(source: os.PathLike[str] | str, destination_parent: os.PathLike[str] | str) -> dict:
    """Copy ordinary source files into a fresh disposable sibling directory."""
    source_path, error = _resolve_directory(source, "source")
    if error:
        return error
    assert source_path is not None
    try:
        parent = Path(destination_parent).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _inconclusive("invalid_path", path_label="destination_parent", error=str(exc))
    if not parent.exists():
        return _inconclusive("missing_path", path_label="destination_parent", path=str(parent))
    if not parent.is_dir():
        return _inconclusive("not_directory", path_label="destination_parent", path=str(parent))
    # A temporary parent may be an ancestor of the source; reject only a
    # parent inside the source tree.
    if parent == source_path or _relative_to(parent, source_path) is not None:
        return _inconclusive("copy_path_overlap", source=str(source_path), destination_parent=str(parent))
    try:
        destination = Path(tempfile.mkdtemp(prefix="arc-disposable-", dir=parent))
        copy_error = _copy_tree(source_path, destination)
        if copy_error:
            shutil.rmtree(destination, ignore_errors=True)
            return copy_error
        manifest = baseline_manifest(destination)
    except (OSError, shutil.Error) as exc:
        return _inconclusive("copy_error", source=str(source_path), error=str(exc))
    if manifest.get("status") != "ok":
        return manifest
    return {"status": "ok", "source": str(source_path), "destination": str(destination), "manifest": manifest}


def restore_from_copy(source: os.PathLike[str] | str, destination: os.PathLike[str] | str) -> dict:
    """Restore ordinary files from a disposable copy into an existing directory."""
    source_path, destination_path, error = _validate_copy_paths(source, destination)
    if error:
        return error
    assert source_path is not None and destination_path is not None
    source_manifest = baseline_manifest(source_path)
    if source_manifest.get("status") != "ok":
        return source_manifest
    before = baseline_manifest(destination_path)
    if before.get("status") != "ok":
        return before
    copy_error = _copy_tree(source_path, destination_path, source_manifest)
    if copy_error:
        return copy_error
    source_files = set(source_manifest["files"])
    for relative in before["files"]:
        if relative in source_files:
            continue
        try:
            (destination_path / relative).unlink()
        except OSError as exc:
            return _inconclusive("restore_remove_error", path=str(destination_path / relative), error=str(exc))
    after = baseline_manifest(destination_path)
    if after.get("status") != "ok":
        return after
    return {
        "status": "ok",
        "source": str(source_path),
        "destination": str(destination_path),
        "source_manifest": source_manifest,
        "before": before,
        "after": after,
        "comparison": compare_manifest(before, after),
    }
