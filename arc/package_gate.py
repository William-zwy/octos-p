#!/usr/bin/env python3
"""Release gates for an ARC Agent ZIP.

This is a thin orchestration layer over the repository's tested
package_shape and build_identity helpers. It keeps the release contract
generic: task and suite values are supplied by the caller, never hard-coded
to a historical challenge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from build_identity import BuildIdentityError, file_sha256, verify_archive_identity
from package_shape import PackageShapeError, inventory, require_report, write_report


HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER = re.compile(
    r"^(?:|null|none|unknown|pending|placeholder(?:[_-].*)?|todo|n/?a)$", re.I
)


class PackageGateError(RuntimeError):
    """The release artifact is incomplete or not safely executable."""


def _identity_value(name: str, value: str,
                    pattern: re.Pattern[str] | None = None) -> str:
    value = str(value or "").strip()
    if PLACEHOLDER.fullmatch(value):
        raise PackageGateError(f"{name} is missing or placeholder")
    if pattern is not None and not pattern.fullmatch(value.lower()):
        raise PackageGateError(f"{name} must be a full hexadecimal digest")
    return value


def _payload_tree_sha(archive: Path) -> str:
    """Hash archive payload deterministically without trusting ZIP timestamps."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(archive) as handle:
        rows = []
        for info in handle.infolist():
            if info.is_dir() or info.filename == "agent-build.json":
                continue
            with handle.open(info) as stream:
                rows.append((info.filename.replace("\\", "/"), stream.read()))
        for name, payload in sorted(rows):
            encoded = name.encode("utf-8")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest().upper()


def offline_import_smoke(archive: Path) -> dict:
    """Extract to a disposable directory and import the packaged entrypoint."""
    with tempfile.TemporaryDirectory(prefix="arc-agent-smoke-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(root)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-c", "import main"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "status": "passed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
        }


def validate_archive(archive: Path, shape_output: Path | None = None,
                     run_smoke: bool = True) -> dict:
    archive = archive.resolve()
    stage = inventory(archive, "agent_zip", "agent")
    report = {
        "schema_version": 1,
        "contract": "arc_agent_bundle_v1",
        "first_missing_stage": None if stage["ok"] else stage["stage"],
        "ok": stage["ok"],
        "stages": [stage],
        "archive_sha256": file_sha256(archive) if archive.is_file() else None,
        "offline_import": None,
    }
    try:
        report["agent_build"] = verify_archive_identity(archive)
    except (BuildIdentityError, OSError, zipfile.BadZipFile) as exc:
        report["agent_build"] = None
        report["identity_error"] = str(exc)
        report["first_missing_stage"] = stage["stage"]
        report["ok"] = False
    if report["ok"] and run_smoke:
        try:
            report["offline_import"] = offline_import_smoke(archive)
        except (OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            report["offline_import"] = {"status": "error", "error": str(exc)}
        report["ok"] = report["offline_import"]["status"] == "passed"
        if not report["ok"]:
            report["first_missing_stage"] = "agent_zip"
    if shape_output:
        write_report(report, shape_output)
    return report


def make_binding(archive: Path, source_commit: str, task_key: str, suite_key: str,
                 requirements_sha256: str, build_id: str | None,
                 shape_output: Path | None = None) -> dict:
    report = validate_archive(archive, shape_output=shape_output, run_smoke=True)
    try:
        require_report(report)
    except PackageShapeError as exc:
        raise PackageGateError(str(exc)) from exc
    if report["offline_import"]["status"] != "passed":
        raise PackageGateError("offline import smoke did not pass")
    identity = report.get("agent_build") or {}
    source_commit = _identity_value("source_commit", source_commit, HEX_40).lower()
    task_key = _identity_value("task_key", task_key)
    suite_key = _identity_value("suite_key", suite_key)
    requirements_sha256 = _identity_value(
        "requirements_sha256", requirements_sha256, HEX_64
    ).lower()
    embedded_build_id = str(identity.get("build_id") or "")
    build_id = _identity_value("build_id", build_id or embedded_build_id)
    if embedded_build_id and build_id != embedded_build_id:
        raise PackageGateError("build_id does not match embedded agent-build.json")
    artifact_sha = file_sha256(archive).lower()
    return {
        "schema_version": 1,
        "status": "verified",
        "source": {"commit_sha": source_commit},
        "task": {"key": task_key},
        "suite": {"key": suite_key},
        "requirements": {"sha256": requirements_sha256},
        "build": {"id": build_id, "payload_tree_sha256": _payload_tree_sha(archive)},
        "artifact": {
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": artifact_sha,
        },
        "checks": {
            "package_shape": True,
            "offline_import": True,
            "placeholder_identity_rejected": True,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--archive", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    validate.add_argument("--no-smoke", action="store_true")
    bind = sub.add_parser("bind")
    bind.add_argument("--archive", type=Path, required=True)
    bind.add_argument("--output", type=Path, required=True)
    bind.add_argument("--shape-output", type=Path)
    bind.add_argument("--source-commit", required=True)
    bind.add_argument("--task-key", required=True)
    bind.add_argument("--suite-key", required=True)
    bind.add_argument("--requirements-sha256", required=True)
    bind.add_argument("--build-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            report = validate_archive(
                args.archive, shape_output=args.output, run_smoke=not args.no_smoke
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if not report["ok"]:
                raise PackageGateError(
                    f"archive gate failed at {report.get('first_missing_stage')}"
                )
        else:
            binding = make_binding(
                args.archive, args.source_commit, args.task_key, args.suite_key,
                args.requirements_sha256, args.build_id, shape_output=args.shape_output
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(binding, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(binding, ensure_ascii=False, indent=2))
    except (PackageGateError, OSError, ValueError) as exc:
        print(f"package gate failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
