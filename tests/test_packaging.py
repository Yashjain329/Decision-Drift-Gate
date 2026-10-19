"""The wheel installs only the ddg package: the viewer and the recorded capture live inside it."""

import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import ddg

ROOT = Path(__file__).resolve().parents[1]


class WheelLayoutTests(unittest.TestCase):
    def test_wheel_has_no_generic_top_level_packages(self):
        with tempfile.TemporaryDirectory() as out:
            # Build from a minimal copy so the source tree gets no build/ or egg-info; --no-build-isolation keeps it
            # offline (uses the installed setuptools).
            src = Path(out) / "src"
            for part in ("pyproject.toml", "ddg", "web/out", "evidence/gemini-proposal.json"):
                target = src / part
                target.parent.mkdir(parents=True, exist_ok=True)
                if (ROOT / part).is_dir():
                    shutil.copytree(ROOT / part, target, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(ROOT / part, target)
            done = subprocess.run([sys.executable, "-m", "pip", "wheel", str(src), "--no-deps", "--no-build-isolation",
                                   "-q", "-w", out], capture_output=True, text=True, cwd=out)
            if done.returncode != 0 and "No module named" in done.stderr:
                self.skipTest("setuptools or wheel is not installed for an offline build")
            self.assertEqual(done.returncode, 0, done.stderr)
            names = zipfile.ZipFile(next(Path(out).glob("*.whl"))).namelist()
        self.assertEqual({n.split("/")[0] for n in names if not n.split("/")[0].endswith(".dist-info")}, {"ddg"})
        built = {n.removeprefix("ddg/_viewer/") for n in names if n.startswith("ddg/_viewer/")}
        expected = {p.relative_to(ROOT / "web" / "out").as_posix() for p in (ROOT / "web" / "out").rglob("*") if p.is_file()}
        self.assertEqual(built, expected)
        self.assertIn("ddg/_evidence/gemini-proposal.json", names)

    def test_checkout_resolves_to_source_paths(self):
        self.assertEqual(ddg.viewer_dir(), ROOT / "web" / "out")
        self.assertEqual(ddg.recorded_capture(), ROOT / "evidence" / "gemini-proposal.json")
        self.assertTrue((ddg.viewer_dir() / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
