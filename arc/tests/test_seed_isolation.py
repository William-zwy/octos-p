import tempfile
import unittest
from pathlib import Path

from seed_isolation import (
    baseline_manifest,
    compare_manifest,
    copy_disposable_workspace,
    restore_from_copy,
)


class SeedIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arc-seed-test-")
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        (self.root / "seed.json").write_text('{"value": 1}\n', encoding="utf-8")
        (self.root / "frontend").mkdir()
        (self.root / "frontend" / "index.html").write_text("<main />\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "ignored").write_text("runtime\n", encoding="utf-8")
        (self.root / "dist").mkdir()
        (self.root / "dist" / "bundle.js").write_text("generated\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_manifest_is_stable_and_excludes_runtime_directories(self):
        before = baseline_manifest(self.root)
        after = baseline_manifest(self.root)
        self.assertEqual(before["status"], "ok")
        self.assertEqual(before["tree_sha256"], after["tree_sha256"])
        self.assertNotIn(".git/ignored", before["files"])
        self.assertNotIn("dist/bundle.js", before["files"])
        self.assertEqual(compare_manifest(before, after)["status"], "unchanged")

    def test_manifest_reports_changes(self):
        before = baseline_manifest(self.root)
        (self.root / "seed.json").write_text('{"value": 2}\n', encoding="utf-8")
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")
        after = baseline_manifest(self.root)
        comparison = compare_manifest(before, after)
        self.assertEqual(comparison["status"], "changed")
        self.assertIn("seed.json", comparison["modified"])
        self.assertIn("new.txt", comparison["added"])

    def test_copy_and_restore_preserve_bytes(self):
        parent = Path(self.temp.name) / "copies"
        parent.mkdir()
        copied = copy_disposable_workspace(self.root, parent)
        self.assertEqual(copied["status"], "ok")
        disposable = Path(copied["destination"])
        self.assertEqual(copied["manifest"]["tree_sha256"], baseline_manifest(disposable)["tree_sha256"])
        (self.root / "seed.json").write_text('{"value": 9}\n', encoding="utf-8")
        (self.root / "smoke-artifact.json").write_text("temporary\n", encoding="utf-8")
        restored = restore_from_copy(disposable, self.root)
        self.assertEqual(restored["status"], "ok")
        self.assertEqual((self.root / "seed.json").read_text(encoding="utf-8"), '{"value": 1}\n')
        self.assertFalse((self.root / "smoke-artifact.json").exists())

    def test_copy_allows_destination_parent_ancestor(self):
        copied = copy_disposable_workspace(self.root, Path(self.temp.name))
        self.assertEqual(copied["status"], "ok")
        self.assertTrue(Path(copied["destination"]).is_dir())

    def test_missing_and_outside_paths_are_inconclusive(self):
        missing = baseline_manifest(self.root / "missing")
        self.assertEqual(missing["status"], "inconclusive")
        outside = baseline_manifest(self.root, data_roots=["../outside"])
        self.assertEqual(outside["status"], "inconclusive")
        parent = Path(self.temp.name) / "copies"
        parent.mkdir()
        overlap = copy_disposable_workspace(self.root, self.root)
        self.assertEqual(overlap["status"], "inconclusive")
        missing_destination = restore_from_copy(self.root, self.root / "missing")
        self.assertEqual(missing_destination["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
