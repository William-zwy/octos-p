import shutil
import subprocess
import unittest
from pathlib import Path


class PackScriptTests(unittest.TestCase):
    def test_interpreter_probe_is_dependency_aware_and_ordered(self):
        script = (Path(__file__).parents[1] / "pack.sh").read_text(encoding="utf-8")
        self.assertIn("import yaml", script)
        self.assertLess(script.index('"${PYTHON:-}"'), script.index("python3 python"))
        self.assertIn("no usable Python interpreter with PyYAML", script)

    def test_shell_syntax_when_posix_shell_is_available(self):
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX shell unavailable on this Windows host")
        subprocess.run([shell, "-n", str(Path(__file__).parents[1] / "pack.sh")], check=True)


if __name__ == "__main__":
    unittest.main()
