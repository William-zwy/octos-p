#!/usr/bin/env python3
"""Audit generated-app and Agent ZIP root shape without changing the inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Iterable

from build_identity import BuildIdentityError, verify_archive_identity


APP_REQUIRED_DIRS = ("frontend", "backend")
APP_OBSERVED_FILES = ("main.py",)
APP_OBSERVED_DIRS = ("tests",)

AGENT_REQUIRED_FILES = (
    "main.py",
    "octos_stdio.py",
    "requirement_order.py",
    "acceptance.py",
    "guard.py",
    "llm_proxy.py",
    "codegen.py",
    "build_identity.py",
    "package_shape.py",
    "run_controls.py",
    "agent-build.json",
    "requirements.txt",
)
AGENT_REQUIRED_DIRS = ("arcbench_agent_runtime", "hooks", "public-tests")

IGNORED_DIRECTORY_PARTS = {".git", "node_modules", "__pycache__"}
AGENT_FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
AGENT_SENSITIVE_FILENAMES = {
    ".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
}
AGENT_SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class PackageShapeError(RuntimeError):
    """A supplied directory or archive does not satisfy its root contract."""


def _normalise_entry(name: str) -> str:
    normalised = name.replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised.lstrip("/")


def _unsafe_entry(name: str) -> bool:
    normalised = name.replace("\\", "/")
    parts = PurePosixPath(normalised).parts
    has_drive_prefix = bool(parts and ":" in parts[0])
    return normalised.startswith("/") or has_drive_prefix or ".." in parts


def _directory_entries(root: Path) -> list[str]:
    entries: list[str] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRECTORY_PARTS)
        relative_root = Path(current).relative_to(root)
        for name in dirs:
            entries.append((relative_root / name).as_posix().strip("/") + "/")
        for name in sorted(files):
            entries.append((relative_root / name).as_posix())
    return sorted(set(filter(None, entries)))


def _archive_entries(archive: Path) -> tuple[list[str], list[str], list[str]]:
    with zipfile.ZipFile(archive) as handle:
        raw = [info.filename for info in handle.infolist()]
    unsafe = sorted(name for name in raw if _unsafe_entry(name))
    normalised = list(filter(None, (_normalise_entry(name) for name in raw)))
    duplicates = sorted(name for name, count in Counter(normalised).items() if count > 1)
    return sorted(set(normalised)), unsafe, duplicates


def _agent_archive_safety(archive: Path, entries: Iterable[str]) -> tuple[list[str], list[str]]:
    forbidden: set[str] = set()
    for entry in entries:
        parts = PurePosixPath(entry).parts
        lower_parts = {part.lower() for part in parts}
        filename = parts[-1].lower() if parts else ""
        if lower_parts & AGENT_FORBIDDEN_PARTS or filename.endswith((".pyc", ".pyo", ".tmp")):
            forbidden.add(entry)
        if filename.endswith(".zip"):
            forbidden.add(entry)
        if filename in AGENT_SENSITIVE_FILENAMES or filename.endswith((".pem", ".key")):
            forbidden.add(entry)

    secret_hits: set[str] = set()
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir() or info.file_size > 8 * 1024 * 1024:
                continue
            name = _normalise_entry(info.filename)
            with handle.open(info) as stream:
                payload = stream.read()
            if any(pattern.search(payload) for pattern in AGENT_SECRET_PATTERNS):
                secret_hits.add(name)
    return sorted(forbidden), sorted(secret_hits)


def _has_root_dir(entries: Iterable[str], name: str) -> bool:
    prefix = name.rstrip("/") + "/"
    return any(entry == prefix or entry.startswith(prefix) for entry in entries)


def _has_root_file(entries: Iterable[str], name: str) -> bool:
    return name in entries


def _entries_digest(entries: Iterable[str]) -> str:
    payload = "\n".join(entries).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inventory(source: Path, stage: str, contract: str = "app") -> dict:
    """Return a deterministic root-level inventory for a directory or ZIP."""
    source = source.resolve()
    result = {
        "stage": stage,
        "source": str(source),
        "contract": contract,
        "source_exists": source.exists(),
        "source_kind": "missing",
        "entry_count": 0,
        "entries_sha256": _entries_digest([]),
        "entries": [],
        "unsafe_entries": [],
        "duplicate_entries": [],
        "forbidden_entries": [],
        "secret_value_hits": [],
    }
    entries: list[str] = []
    if source.is_dir():
        result["source_kind"] = "directory"
        entries = _directory_entries(source)
    elif source.is_file() and zipfile.is_zipfile(source):
        result["source_kind"] = "zip"
        entries, unsafe, duplicates = _archive_entries(source)
        result["unsafe_entries"] = unsafe
        result["duplicate_entries"] = duplicates
        result["archive_sha256"] = _file_digest(source)
    elif source.is_file():
        result["source_kind"] = "non_zip_file"

    result["entry_count"] = len(entries)
    result["entries_sha256"] = _entries_digest(entries)
    result["entries"] = entries

    if contract == "app":
        required_dirs = APP_REQUIRED_DIRS
        required_files: tuple[str, ...] = ()
        result["observed"] = {
            **{name + "/": _has_root_dir(entries, name) for name in APP_OBSERVED_DIRS},
            **{name: _has_root_file(entries, name) for name in APP_OBSERVED_FILES},
        }
    elif contract == "agent":
        required_dirs = AGENT_REQUIRED_DIRS
        required_files = AGENT_REQUIRED_FILES
        if source.is_file() and zipfile.is_zipfile(source):
            forbidden, secret_hits = _agent_archive_safety(source, entries)
            result["forbidden_entries"] = forbidden
            result["secret_value_hits"] = secret_hits
    else:
        raise ValueError(f"unknown package-shape contract: {contract}")

    present = {
        **{name + "/": _has_root_dir(entries, name) for name in required_dirs},
        **{name: _has_root_file(entries, name) for name in required_files},
    }
    result["required"] = present
    result["missing"] = [name for name, available in present.items() if not available]
    result["ok"] = bool(
        result["source_exists"]
        and not result["unsafe_entries"]
        and not result["duplicate_entries"]
        and not result["forbidden_entries"]
        and not result["secret_value_hits"]
        and not result["missing"]
    )
    return result


def inspect_pipeline(workspace: Path, staging: Path | None = None,
                     archive: Path | None = None) -> dict:
    """Inspect every supplied app-packaging stage and name the first bad one."""
    supplied = [("workspace", workspace), ("staging", staging), ("final_zip", archive)]
    stages = [inventory(path, name, "app") for name, path in supplied if path is not None]
    first_missing = next((stage["stage"] for stage in stages if not stage["ok"]), None)
    return {
        "schema_version": 1,
        "contract": "web_app_root_v1",
        "required_root_entries": [name + "/" for name in APP_REQUIRED_DIRS],
        "first_missing_stage": first_missing,
        "ok": first_missing is None,
        "stages": stages,
    }


def write_report(report: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stage_summary(stage: dict) -> str:
    missing = ", ".join(stage["missing"]) or "none"
    return (f"{stage['stage']} kind={stage['source_kind']} entries={stage['entry_count']} "
            f"entries_sha256={stage['entries_sha256']} missing={missing} "
            f"unsafe={len(stage['unsafe_entries'])} duplicates={len(stage['duplicate_entries'])} "
            f"forbidden={len(stage['forbidden_entries'])} secrets={len(stage['secret_value_hits'])}")


def require_report(report: dict) -> None:
    if not report["ok"]:
        if report.get("identity_error"):
            raise PackageShapeError(
                f"agent_zip does not satisfy {report['contract']}: {report['identity_error']}"
            )
        stage = report["first_missing_stage"]
        failed = next(item for item in report["stages"] if item["stage"] == stage)
        findings = list(failed["missing"])
        findings.extend(f"unsafe:{name}" for name in failed["unsafe_entries"])
        findings.extend(f"duplicate:{name}" for name in failed["duplicate_entries"])
        findings.extend(f"forbidden:{name}" for name in failed["forbidden_entries"])
        findings.extend(f"secret:{name}" for name in failed["secret_value_hits"])
        details = ", ".join(findings) or "unknown shape failure"
        raise PackageShapeError(f"{stage} does not satisfy {report['contract']}: {details}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline = subparsers.add_parser("pipeline", help="inspect generated-app packaging stages")
    pipeline.add_argument("--workspace", type=Path, required=True)
    pipeline.add_argument("--staging", type=Path)
    pipeline.add_argument("--archive", type=Path)
    pipeline.add_argument("--output", type=Path)

    agent = subparsers.add_parser("agent", help="inspect a platform Agent ZIP")
    agent.add_argument("--archive", type=Path, required=True)
    agent.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "pipeline":
        report = inspect_pipeline(args.workspace, args.staging, args.archive)
    else:
        stage = inventory(args.archive, "agent_zip", "agent")
        report = {
            "schema_version": 1,
            "contract": "arc_agent_bundle_v1",
            "first_missing_stage": None if stage["ok"] else stage["stage"],
            "ok": stage["ok"],
            "stages": [stage],
        }
        try:
            report["agent_build"] = verify_archive_identity(args.archive)
        except BuildIdentityError as exc:
            report["agent_build"] = None
            report["identity_error"] = str(exc)
            report["first_missing_stage"] = stage["stage"]
            report["ok"] = False
    if args.output:
        write_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        require_report(report)
    except PackageShapeError as exc:
        print(f"package-shape gate failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
