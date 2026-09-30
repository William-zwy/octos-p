#!/usr/bin/env python3
"""Deterministic build identity and release provenance for ARC Agent bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


SCHEMA_VERSION = 1
PACKAGE_CONTRACT = "arc_agent_bundle_v1"
IDENTITY_FILENAME = "agent-build.json"
BUILD_ID_PREFIX = "arc-agent-v1"

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9A-F]{64}$")


class BuildIdentityError(RuntimeError):
    """The bundle identity or release sidecars are incomplete or inconsistent."""


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _normalise_entry(name: str) -> str:
    value = name.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def _unsafe_entry(name: str) -> bool:
    value = name.replace("\\", "/")
    parts = PurePosixPath(value).parts
    return value.startswith("/") or bool(parts and ":" in parts[0]) or ".." in parts


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def payload_tree_identity(archive: Path) -> tuple[str, int]:
    """Hash every packaged file path and byte payload except the identity itself."""
    digest = hashlib.sha256()
    records: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            if _unsafe_entry(info.filename):
                raise BuildIdentityError(f"unsafe archive entry: {info.filename}")
            name = _normalise_entry(info.filename)
            if not name:
                continue
            if name in seen:
                raise BuildIdentityError(f"duplicate archive entry: {name}")
            seen.add(name)
            if name == IDENTITY_FILENAME:
                continue
            records.append((name, handle.read(info)))
    for name, payload in sorted(records):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest().upper(), len(records)


def make_identity(commit_sha: str, payload_tree_sha256: str,
                  managed_file_count: int) -> dict:
    commit_sha = commit_sha.strip().lower()
    payload_tree_sha256 = payload_tree_sha256.strip().upper()
    if not _HEX_40.fullmatch(commit_sha):
        raise BuildIdentityError("commit_sha must be a full 40-character Git SHA")
    if not _HEX_64.fullmatch(payload_tree_sha256):
        raise BuildIdentityError("payload_tree_sha256 must be a full SHA-256")
    if int(managed_file_count) < 0:
        raise BuildIdentityError("managed_file_count must be non-negative")
    stable = {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "payload_tree_sha256": payload_tree_sha256,
        "managed_file_count": int(managed_file_count),
        "package_contract": PACKAGE_CONTRACT,
    }
    build_digest = hashlib.sha256(_canonical_bytes(stable)).hexdigest()
    return {**stable, "build_id": f"{BUILD_ID_PREFIX}-{build_digest[:24]}"}


def validate_identity(identity: dict) -> dict:
    try:
        expected = make_identity(
            str(identity.get("commit_sha", "")),
            str(identity.get("payload_tree_sha256", "")),
            int(identity.get("managed_file_count", -1)),
        )
    except (TypeError, ValueError) as exc:
        raise BuildIdentityError("managed_file_count must be an integer") from exc
    if identity.get("schema_version") != SCHEMA_VERSION:
        raise BuildIdentityError("unsupported agent build identity schema")
    if identity.get("package_contract") != PACKAGE_CONTRACT:
        raise BuildIdentityError("agent build identity package contract mismatch")
    if identity.get("build_id") != expected["build_id"]:
        raise BuildIdentityError("agent build ID does not match its stable fields")
    return identity


def load_identity(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildIdentityError(f"could not read build identity: {path}") from exc
    if not isinstance(value, dict):
        raise BuildIdentityError("agent build identity must be a JSON object")
    return validate_identity(value)


def read_archive_identity(archive: Path) -> dict:
    try:
        with zipfile.ZipFile(archive) as handle:
            value = json.loads(handle.read(IDENTITY_FILENAME).decode("utf-8"))
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise BuildIdentityError("archive does not contain a valid root agent-build.json") from exc
    if not isinstance(value, dict):
        raise BuildIdentityError("embedded agent build identity must be a JSON object")
    return validate_identity(value)


def embed_identity(archive: Path, commit_sha: str) -> dict:
    with zipfile.ZipFile(archive) as handle:
        if IDENTITY_FILENAME in {_normalise_entry(info.filename) for info in handle.infolist()}:
            raise BuildIdentityError(f"archive already contains {IDENTITY_FILENAME}")
    payload_sha256, count = payload_tree_identity(archive)
    identity = make_identity(commit_sha, payload_sha256, count)
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    info = zipfile.ZipInfo(IDENTITY_FILENAME, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(archive, "a") as handle:
        handle.writestr(info, payload.encode("utf-8"))
    verify_archive_identity(archive)
    return identity


def verify_archive_identity(archive: Path) -> dict:
    identity = read_archive_identity(archive)
    payload_sha256, count = payload_tree_identity(archive)
    if identity["payload_tree_sha256"] != payload_sha256:
        raise BuildIdentityError("embedded payload tree SHA-256 does not match archive bytes")
    if identity["managed_file_count"] != count:
        raise BuildIdentityError("embedded managed file count does not match archive")
    return identity


def write_json(value: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_release_provenance(archive: Path, shape_path: Path, release_path: Path,
                             checksum_path: Path) -> dict:
    identity = verify_archive_identity(archive)
    try:
        shape = json.loads(shape_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildIdentityError("shape manifest is missing or invalid") from exc
    archive_sha256 = file_sha256(archive)
    stages = shape.get("stages") or []
    stage = stages[0] if stages else {}
    if not shape.get("ok") or shape.get("contract") != PACKAGE_CONTRACT:
        raise BuildIdentityError("shape manifest did not pass the Agent package contract")
    if stage.get("archive_sha256") != archive_sha256:
        raise BuildIdentityError("shape manifest archive SHA-256 does not match release archive")
    if not (stage.get("required") or {}).get(IDENTITY_FILENAME):
        raise BuildIdentityError("shape manifest does not confirm root agent-build.json")
    if shape.get("agent_build") != identity:
        raise BuildIdentityError("shape manifest build identity does not match release archive")
    release = {
        "schema_version": SCHEMA_VERSION,
        "build_identity": identity,
        "artifact": {
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": archive_sha256,
        },
        "shape_manifest": {
            "filename": shape_path.name,
            "sha256": file_sha256(shape_path),
            "contract": shape["contract"],
            "ok": True,
        },
    }
    write_json(release, release_path)
    checksum_path.write_text(f"{archive_sha256}  {archive.name}\n", encoding="utf-8")
    return release


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    embed = subparsers.add_parser("embed", help="append a deterministic identity to an Agent ZIP")
    embed.add_argument("--archive", type=Path, required=True)
    embed.add_argument("--commit", required=True)
    inspect = subparsers.add_parser("inspect", help="verify and print an embedded identity")
    inspect.add_argument("--archive", type=Path, required=True)
    inspect.add_argument("--field")
    release = subparsers.add_parser("release", help="bind a ZIP to its external sidecars")
    release.add_argument("--archive", type=Path, required=True)
    release.add_argument("--shape", type=Path, required=True)
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--checksum", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "embed":
            result = embed_identity(args.archive, args.commit)
        elif args.command == "inspect":
            result = verify_archive_identity(args.archive)
            if args.field:
                if args.field not in result:
                    raise BuildIdentityError(f"unknown identity field: {args.field}")
                print(result[args.field])
                return 0
        else:
            result = write_release_provenance(
                args.archive, args.shape, args.output, args.checksum,
            )
    except BuildIdentityError as exc:
        print(f"build-identity gate failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
