import json
import os
import subprocess
import copy
from functools import partial
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg.demo import build_demo
from ddg import harness
from ddg.harness import FakeService, _small_worker_environment

# The demo repository keeps its job client at the decision scope src/job_client.py.
observe = partial(harness.observe, path="src/job_client.py")
observe_happy_path = partial(harness.observe_happy_path, path="src/job_client.py")


CHECK = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))


class FakeServiceTests(unittest.TestCase):
    def test_commit_then_503_commits_before_lost_ack(self):
        service = FakeService("commit_then_503")
        first = service.create({"x": 1}, "op-1")
        self.assertEqual(first.status, 503)
        self.assertEqual(len(service.jobs), 1)
        self.assertEqual(service.lookup("op-1"), "job-1")
        second = service.create({"x": 1}, "op-1")
        self.assertEqual(second.status, 201)
        self.assertEqual(second.job_id, "job-2")

    def test_stable_idempotency_key_deduplicates_retries(self):
        service = FakeService("commit_then_503")
        first = service.create({}, "op-1", idempotency_key="stable")
        second = service.create({}, "op-1", idempotency_key="stable")
        self.assertEqual(first.status, 503)
        self.assertEqual((second.status, second.job_id), (201, "job-1"))
        self.assertEqual(len(service.jobs), 1)

    def test_reject_then_503_does_not_create_on_fault(self):
        service = FakeService("reject_then_503")
        first = service.create({}, "op-1")
        self.assertEqual(first.status, 503)
        self.assertIsNone(first.job_id)
        self.assertEqual(service.lookup("op-1"), None)
        self.assertEqual(len(service.jobs), 0)
        second = service.create({}, "op-1")
        self.assertEqual((second.status, second.job_id), (201, "job-1"))


class RunnerTests(unittest.TestCase):
    def test_lost_ack_exposes_duplicate_while_reconciliation_passes(self):
        with TemporaryDirectory(prefix="ddg runner space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            bad = observe(repo, demo["refs"]["calibration_bad"], CHECK)
            good = observe(repo, demo["refs"]["calibration_good"], CHECK)
            exception = observe(repo, demo["refs"]["calibration_exception"], CHECK)
            self.assertEqual((bad["status"], bad["unique_jobs"]), ("FAIL", 2))
            self.assertEqual((good["status"], good["unique_jobs"]), ("PASS", 1))
            self.assertTrue(good["returned_job_exists"])
            self.assertEqual((exception["status"], exception["unique_jobs"]), ("PASS", 1))

    def test_happy_path_is_an_ordinary_success_without_fault(self):
        with TemporaryDirectory(prefix="ddg happy space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            result = observe_happy_path(Path(demo["repo"]), demo["refs"]["calibration_bad"])
            self.assertEqual((result["status"], result["unique_jobs"]), ("PASS", 1))

    def test_worker_failures_are_errors_with_unavailable_metrics(self):
        with TemporaryDirectory(prefix="ddg errors space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            for ref in ("crashing", "timing_out", "missing_entrypoint"):
                result = observe(Path(demo["repo"]), demo["refs"][ref], CHECK, timeout=0.2 if ref == "timing_out" else 10)
                self.assertEqual(result["status"], "ERROR", ref)
                self.assertTrue(result["error"], ref)
                for key in ("unique_jobs", "returned_job_exists", "returned_job_id", "submit_calls"):
                    self.assertIsNone(result[key], (ref, key))

    def test_silent_abort_is_a_failed_completion_assertion(self):
        with TemporaryDirectory(prefix="ddg abort space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            result = observe(Path(demo["repo"]), demo["refs"]["abort"], CHECK)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["unique_jobs"], 1)
            self.assertFalse(result["returned_job_exists"])

    def test_check_allowing_missing_return_still_fails_good_calibration(self):
        check = copy.deepcopy(CHECK)
        check["assertions"][1]["equals"] = False
        with TemporaryDirectory(prefix="ddg completion space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            result = observe(Path(demo["repo"]), demo["refs"]["calibration_good"], check)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["returned_job_exists"])

    def test_worker_environment_excludes_provider_secrets(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-a", "DDG_GEMINI_MODEL": "secret-b", "API_KEY": "secret-c"}):
            worker_env = _small_worker_environment()
        self.assertNotIn("GEMINI_API_KEY", worker_env)
        self.assertNotIn("DDG_GEMINI_MODEL", worker_env)
        self.assertNotIn("API_KEY", worker_env)

    def test_external_import_is_an_execution_error(self):
        with TemporaryDirectory(prefix="ddg import space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            source = repo / "src" / "job_client.py"
            source.write_text("import definitely_not_a_stdlib_package\n" + source.read_text(encoding="utf-8"), encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "--quiet", "-m", "unsupported import fixture"],
                check=True,
            )
            result = observe(repo, "HEAD", CHECK)
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("Unsupported import", result["error"])

    def test_dynamic_import_of_trusted_runner_is_rejected(self):
        with TemporaryDirectory(prefix="ddg dynamic import ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            source = repo / "src" / "job_client.py"
            source.write_text(
                "import importlib\n"
                "def submit_job(service, payload, operation_id):\n"
                "    importlib.import_module('ddg')\n"
                "    return service.create(payload, operation_id).job_id\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "--quiet", "-m", "dynamic import fixture"],
                check=True,
            )
            result = observe_happy_path(repo, "HEAD")
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("dynamic", result["error"].lower())

    def _commit_source(self, repo, source):
        (repo / "src" / "job_client.py").write_text(source, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@e.invalid",
                        "commit", "--quiet", "-m", "fixture"], check=True)

    def test_target_cannot_tamper_with_observed_service_state(self):
        source = (
            "def submit_job(service, payload, operation_id):\n"
            "    service.create(payload, operation_id)\n"
            "    r = service.create(payload, operation_id)\n"
            "    service.jobs = []\n"
            "    service.events = []\n"
            "    service._create_calls = 1\n"
            "    return r.job_id\n"
        )
        with TemporaryDirectory(prefix="ddg tamper ") as folder:
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            self._commit_source(repo, source)
            result = observe(repo, "HEAD", CHECK)
            self.assertEqual((result["status"], result["unique_jobs"]), ("FAIL", 2))

    def test_filesystem_and_process_modules_are_rejected(self):
        source = "import os\ndef submit_job(service, payload, operation_id):\n    return None\n"
        with TemporaryDirectory(prefix="ddg denied ") as folder:
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            self._commit_source(repo, source)
            result = observe(repo, "HEAD", CHECK)
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("Unsupported import", result["error"])

    def test_invalid_check_is_rejected_before_worker_starts(self):
        invalid = dict(CHECK)
        invalid["assertions"] = CHECK["assertions"][:1]
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            with self.assertRaises(ValueError):
                observe(Path(demo["repo"]), demo["refs"]["calibration_good"], invalid)


if __name__ == "__main__":
    unittest.main()
