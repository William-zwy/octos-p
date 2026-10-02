import tempfile
import unittest
import zipfile
from pathlib import Path

from build_identity import embed_identity
from package_gate import PackageGateError, make_binding, validate_archive
from package_shape import AGENT_REQUIRED_DIRS, AGENT_REQUIRED_FILES


COMMIT = "1" * 40
REQUIREMENTS = "2" * 64


def fixture_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in AGENT_REQUIRED_FILES:
            if name == "agent-build.json":
                continue
            if name == "main.py":
                payload = "import sys\n"
            elif name.endswith("/manifest.json"):
                payload = '{"name":"arc-project-context","version":"1.0.0","tools":[]}'
            elif name.endswith("/index.js"):
                payload = ('process.stdin.resume();process.stdin.on("end",()=>'
                           'process.stdout.write(JSON.stringify({success:true,project_map_hash:"fixture"})));')
            elif name.endswith("/main"):
                payload = '#!/bin/sh\nexec node "$(dirname "$0")/index.js" "$@"\n'
            else:
                payload = "# fixture\n"
            archive.writestr(name, payload)
        for name in AGENT_REQUIRED_DIRS:
            archive.writestr(f"{name}/fixture.txt", "fixture")


class PackageGateTests(unittest.TestCase):
    def test_validate_runs_shape_identity_and_import_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "agent.zip"
            fixture_archive(archive)
            embed_identity(archive, COMMIT)
            report = validate_archive(archive)
            self.assertTrue(report["ok"])
            self.assertEqual(report["offline_import"]["status"], "passed")
            self.assertEqual(report["offline_import"]["context_skill"]["status"], "passed")
            self.assertEqual(report["agent_build"]["commit_sha"], COMMIT)

    def test_binding_contains_full_artifact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "agent.zip"
            fixture_archive(archive)
            embed_identity(archive, COMMIT)
            binding = make_binding(
                archive, COMMIT, "competition--task", "suite--task", REQUIREMENTS, None
            )
            self.assertEqual(binding["status"], "verified")
            self.assertEqual(binding["artifact"]["sha256"], _sha256(archive))
            self.assertTrue(binding["build"]["id"])

    def test_placeholder_identity_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "agent.zip"
            fixture_archive(archive)
            embed_identity(archive, COMMIT)
            with self.assertRaisesRegex(PackageGateError, "placeholder"):
                make_binding(
                    archive, COMMIT, "PENDING", "suite--task", REQUIREMENTS, None
                )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
