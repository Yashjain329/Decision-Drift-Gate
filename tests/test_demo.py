import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ddg.demo import build_demo
from ddg.gitio import read_at, resolve_commit


class DemoTests(unittest.TestCase):
    def test_builds_named_sha1_refs_and_policy_history(self):
        with TemporaryDirectory(prefix="ddg demo space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            expected = {"calibration_bad", "calibration_good", "calibration_exception", "decision_change", "missing_policy", "crashing", "timing_out", "abort", "missing_entrypoint"}
            self.assertTrue(expected.issubset(demo["refs"]))
            for name, sha in demo["refs"].items():
                self.assertEqual(len(sha), 40, name)
            self.assertEqual(resolve_commit(repo, "calibration-good"), demo["refs"]["calibration_good"])
            self.assertEqual(resolve_commit(repo, "calibration-bad"), demo["refs"]["calibration_bad"])
            changed = json.loads(read_at(repo, demo["refs"]["decision_change"], ".ddg/decisions/DEC-002.json"))
            self.assertEqual((changed["status"], changed["supersedes"]), ("active", "DEC-001"))
            self.assertIn("must not create duplicate jobs", changed["rule"])
            self.assertIn("silently abandoning", changed["rule"])
            self.assertIn("fabricated success", changed["rule"])
            old = json.loads(read_at(repo, demo["refs"]["decision_change"], ".ddg/decisions/DEC-001.json"))
            self.assertEqual(old["status"], "superseded")
            marker = json.loads((repo / ".ddg-demo.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["repo"], str(repo))
            self.assertEqual(marker["refs"], demo["refs"])
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip(), "calibration-good")
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout, "")

    def test_refuses_nonempty_destination_without_touching_it(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "existing"
            destination.mkdir()
            original = destination / "keep.txt"
            original.write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_demo(destination)
            self.assertEqual(original.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(destination.iterdir()), [original])

    def test_refuses_file_destination(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "file"
            destination.write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_demo(destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "keep")

    def test_empty_destination_and_parent_checkout_are_preserved(self):
        with TemporaryDirectory() as folder:
            parent = Path(folder) / "source"
            parent.mkdir()
            tracked = parent / "tracked.txt"
            tracked.write_text("committed", encoding="utf-8")
            subprocess.run(["git", "init", str(parent)], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(parent), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(parent), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "base"], check=True)
            tracked.write_text("dirty", encoding="utf-8")
            (parent / "untracked.txt").write_text("preserve", encoding="utf-8")
            before = subprocess.run(["git", "-C", str(parent), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.splitlines()
            before_head = subprocess.run(["git", "-C", str(parent), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            empty = parent / "empty demo"
            empty.mkdir()
            demo = build_demo(empty)
            self.assertEqual(Path(demo["repo"]), empty.resolve())
            self.assertEqual(tracked.read_text(encoding="utf-8"), "dirty")
            self.assertEqual((parent / "untracked.txt").read_text(encoding="utf-8"), "preserve")
            after = subprocess.run(["git", "-C", str(parent), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertTrue(set(before).issubset(after))
            self.assertEqual([line for line in after if "empty demo" not in line], before)
            self.assertEqual(subprocess.run(["git", "-C", str(parent), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(), before_head)
            self.assertTrue((parent / ".git").exists())


if __name__ == "__main__":
    unittest.main()
