import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ddg.demo import build_demo
from ddg.gitio import diff_at, read_at, resolve_commit


class GitReadTests(unittest.TestCase):
    def test_pinned_read_survives_ref_move(self):
        with TemporaryDirectory(prefix="ddg space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            sha = resolve_commit(repo, demo["refs"]["calibration_good"])
            original = read_at(repo, sha, "src/job_client.py")
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/moved", sha], check=True)
            bad_sha = resolve_commit(repo, demo["refs"]["calibration_bad"])
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/moved", bad_sha], check=True)
            self.assertEqual(read_at(repo, sha, "src/job_client.py"), original)
            self.assertNotEqual(read_at(repo, resolve_commit(repo, "moved"), "src/job_client.py"), original)
            self.assertEqual(len(sha), 40)

    def test_rejects_invalid_and_non_full_object_ids(self):
        with TemporaryDirectory() as folder:
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            for ref in ("-bad", "not-a-ref"):
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    resolve_commit(repo, ref)
            for sha, path in (("HEAD", "src/job_client.py"), ("0" * 40, "src/job_client.py"),
                              (resolve_commit(repo, "HEAD"), "../.ddg-demo.json")):
                with self.subTest(sha=sha, path=path), self.assertRaises(ValueError):
                    read_at(repo, sha, path)

    def test_missing_path_and_diff_are_safe(self):
        with TemporaryDirectory(prefix="ddg path space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            sha = resolve_commit(repo, demo["refs"]["calibration_good"])
            self.assertIn("submit_job", read_at(repo, sha, "src/job_client.py"))
            with self.assertRaises(ValueError):
                read_at(repo, sha, "missing file.py")
            bad = resolve_commit(repo, demo["refs"]["calibration_bad"])
            context = diff_at(repo, bad, sha, "src/job_client.py")
            self.assertIn("submit_job", context)
            self.assertNotIn(".ddg/decisions", context)
            policy_context = diff_at(repo, sha, resolve_commit(repo, demo["refs"]["missing_policy"]), "src/job_client.py")
            self.assertNotIn(".ddg/decisions", policy_context)

    def test_git_failure_is_value_error(self):
        with TemporaryDirectory() as folder, self.assertRaises(ValueError):
            resolve_commit(Path(folder), "HEAD")

    def test_read_at_round_trips_utf8_source_exactly(self):
        with TemporaryDirectory() as folder:
            repo = Path(folder) / "repo"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init", "--quiet", "--object-format=sha1"], check=True)
            source = "def submit_job(service, payload, operation_id):\n    if 'é' == '\\u00e9':\n        return service.lookup(operation_id)\n    response = service.create(payload, operation_id)\n    if response.status == 503:\n        response = service.create(payload, operation_id)\n    return response.job_id\n"
            source_path = repo / "src" / "job_client.py"
            source_path.parent.mkdir()
            source_path.write_text(source, encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
            subprocess.run([
                "git", "-C", str(repo), "-c", "user.name=Test", "-c",
                "user.email=test@example.invalid", "commit", "--quiet", "-m", "utf8",
            ], check=True)
            sha = resolve_commit(repo, "HEAD")
            self.assertEqual(read_at(repo, sha, "src/job_client.py"), source)


if __name__ == "__main__":
    unittest.main()
