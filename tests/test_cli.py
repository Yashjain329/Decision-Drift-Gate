import html
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ddg.report import is_stale, write_report
from tests.support import make_approved_demo

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix="ddg cli space ")
        cls.demo = make_approved_demo(Path(cls.temp.name) / "repo with spaces")
        cls.repo = Path(cls.demo["repo"])
        cls.refs = cls.demo["refs"]
        cls.reports = Path(cls.temp.name) / "output reports"
        cls.reports.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_cli(self, *args, env=None):
        environment = os.environ.copy()
        if env:
            environment.update(env)
        return subprocess.run([sys.executable, "-m", "ddg", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", env=environment,
                              timeout=90)

    def test_failure_writes_machine_readable_report_and_does_not_leak_environment_key(self):
        out = self.reports / "regression report.json"
        result = self.run_cli("run", "--repo", self.repo, "--base", "approved-base",
                              "--head", "regression", "--out", out,
                              env={"GEMINI_API_KEY": "local-secret-must-not-appear"})
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["aggregate"], "FAILED")
        self.assertEqual(report["base_sha"], self.refs["approved_base"])
        self.assertEqual(report["head_sha"], self.refs["regression"])
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        self.assertTrue(out.with_suffix(".md").exists())
        saved = out.read_text(encoding="utf-8") + out.with_suffix(".md").read_text(encoding="utf-8")
        self.assertNotIn("local-secret-must-not-appear", saved)
        self.assertNotIn("local-secret-must-not-appear", result.stdout + result.stderr)

    def test_exit_codes_cover_pass_and_incomplete(self):
        passed = self.run_cli("run", "--repo", self.repo, "--base", "approved-base",
                              "--head", "exception", "--out", self.reports / "exception.json")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads((self.reports / "exception.json").read_text(encoding="utf-8"))["aggregate"], "PASSED_CHECKS")
        incomplete = self.run_cli("run", "--repo", self.repo, "--base", "approved-base",
                                  "--head", "policy-edit", "--out", self.reports / "policy-edit.json")
        self.assertEqual(incomplete.returncode, 2, incomplete.stderr)
        self.assertEqual(json.loads((self.reports / "policy-edit.json").read_text(encoding="utf-8"))["aggregate"], "INCOMPLETE")

    def test_demo_init_recorded_proposal_calibration_approval_and_run(self):
        repo = Path(self.temp.name) / "演示 😊 lifecycle demo with spaces"
        state = Path(self.temp.name) / "lifecycle state"
        init = self.run_cli("demo-init", "--destination", repo)
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertIn("演示 😊", init.stdout)
        marker = json.loads((repo / ".ddg-demo.json").read_text(encoding="utf-8"))
        draft_path = state / "draft.json"
        proposal = self.run_cli("propose", "--repo", repo, "--decision", "DEC-002",
                                "--mode", "recorded", "--out", draft_path)
        self.assertEqual(proposal.returncode, 0, proposal.stderr)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(draft["proposal_mode"], "recorded")
        self.assertNotEqual(draft["source_sha"], draft["capture_source_sha"])
        validation_path = state / "validation.json"
        validation = self.run_cli("validate", "--repo", repo, "--draft", draft_path,
                                  "--out", validation_path)
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertTrue(json.loads(validation_path.read_text(encoding="utf-8"))["eligible"])
        rejected = self.run_cli("approve", "--repo", repo, "--draft", draft_path,
                                "--validation", validation_path, "--reviewer", "CLI reviewer",
                                "--reason", "Reviewed offline calibration cases", "--commit-demo",
                                "--out", repo / ".ddg" / "forbidden.json")
        self.assertEqual(rejected.returncode, 2)
        self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())
        approval = self.run_cli("approve", "--repo", repo, "--draft", draft_path,
                                "--validation", validation_path, "--reviewer", "CLI reviewer",
                                "--reason", "Reviewed offline calibration cases", "--commit-demo")
        self.assertEqual(approval.returncode, 0, approval.stderr)
        self.assertTrue((repo / ".ddg/approvals/CHK-001.json").is_file())
        report_path = state / "regression.json"
        run = self.run_cli("run", "--repo", repo, "--base", "approved-base", "--head", "regression",
                           "--out", report_path)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["aggregate"], "FAILED")

    def test_status_marks_moved_refs_stale_without_rewriting_report(self):
        out = self.reports / "stale report.json"
        run = self.run_cli("run", "--repo", self.repo, "--base", "approved-base",
                           "--head", "regression", "--out", out)
        self.assertEqual(run.returncode, 1, run.stderr)
        original = out.read_bytes()
        current = self.run_cli("status", "--repo", self.repo, "--report", out,
                               "--base", "approved-base", "--head", "regression")
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertIn("CURRENT", current.stdout)
        moved_sha = self.refs["corrected"]
        subprocess.run(["git", "-C", str(self.repo), "update-ref", "refs/heads/regression", moved_sha], check=True)
        stale = self.run_cli("status", "--repo", self.repo, "--report", out,
                             "--base", "approved-base", "--head", "regression")
        self.assertEqual(stale.returncode, 1, stale.stderr)
        self.assertIn("STALE", stale.stdout)
        self.assertIn("Rerun required", stale.stdout)
        self.assertEqual(out.read_bytes(), original)
        subprocess.run(["git", "-C", str(self.repo), "update-ref", "refs/heads/regression", self.refs["regression"]], check=True)

    def test_markdown_report_escapes_decision_and_diff_text(self):
        report = {
            "aggregate": "FAILED", "base_sha": self.refs["approved_base"], "head_sha": self.refs["corrected"],
            "run_at": "2026-10-04T00:00:00Z", "adapter_version": "python_job_client_v1",
            "ordinary_tests": {"base": {"status": "PASS"}, "head": {"status": "PASS"}},
            "active_decisions": [{"schema_version": 1, "id": "DEC-003", "status": "active",
                                  "supersedes": None, "scope": "<workspace>", "rule": "未覆盖决策 🙂 <em>rule</em>",
                                  "exceptions": ["<b>exception</b>"]}],
            "warnings": [],
            "checks": [{"verdict": "VIOLATION_INTRODUCED", "decision": {"id": "DEC-002", "rule": "处理 🙂 <script>alert(1)</script>", "exceptions": ["<b>safe</b>"]},
                        "base": {"status": "PASS"}, "head": {"status": "FAIL"},
                        "check_digest": "c" * 64, "approval": {"reviewer": "Dev"},
                        "validation": {"eligible": True}, "diff": "<img src=x onerror=alert(1)>"}],
        }
        path = self.reports / "escape.json"
        write_report(report, path)
        markdown = path.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("&lt;img", markdown)
        self.assertIn("处理 🙂", markdown)
        self.assertIn("DEC-003", markdown)
        self.assertIn("未覆盖决策 🙂", markdown)
        self.assertIn("&lt;em&gt;", markdown)
        self.assertNotIn("<script>", markdown)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
        self.assertFalse(is_stale(self.repo, json.loads(path.read_text(encoding="utf-8")),
                                  "approved-base", "corrected"))

    def test_invalid_arguments_return_two_without_traceback(self):
        result = self.run_cli("run", "--repo", self.repo)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("usage:", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
