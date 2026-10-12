"""Full-lifecycle e2e: real CLI subprocesses on fresh temp repos, in host and docker sandbox modes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg.gitio import resolve_commit
from tests.e2e.harness import (DOCKER_OK, DOCKER_SKIP_REASON, ROOT, cli, docker_leftovers, lifecycle, load)
from tests.test_adapters import (BAD, CHECK, DEC1, DEC2, GOOD_SRC, REFACTORED, js)
from tests.test_identity import commit, git, policy

ADAPTER = "python_function_v1"

# branch -> (exit code, aggregate, check verdict)
SCENARIOS = {
    "regression": (1, "FAILED", "VIOLATION_INTRODUCED"),
    "unseen-regression": (1, "FAILED", "VIOLATION_INTRODUCED"),
    "corrected": (0, "PASSED_CHECKS", "CHECK_PASSED"),
    "exception": (0, "PASSED_CHECKS", "CHECK_PASSED"),
    "unrelated": (0, "PASSED_CHECKS", "CHECK_PASSED"),
    "approved-abort": (1, "FAILED", "VIOLATION_INTRODUCED"),
    "approved-crashing": (2, "INCOMPLETE", "NOT_CHECKED"),
    "approved-timing-out": (2, "INCOMPLETE", "NOT_CHECKED"),
    "approved-missing-entrypoint": (2, "INCOMPLETE", "NOT_CHECKED"),
    "policy-edit": (2, "INCOMPLETE", "CHECK_PASSED"),
}


def build_function_repo(folder, approver_email="alice@example.com"):
    """Brand-new python_function_v1 repo (same shape as tests/test_adapters.py), built via the Python API.

    ponytail: the real CLI is demo-only for init/propose/approve, so artifacts come from the API.
    """
    from ddg.approval import approve, validate_draft
    from ddg.proposal import load_context, wrap_draft

    repo = Path(folder) / "fn-repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    commit(repo, {".ddg/approvers.json": policy(), ".ddg/decisions/DEC-001.json": js({**DEC1, "status": "active"}),
                  "src/pricing.py": BAD}, "initial")
    bad = commit(repo, {".ddg/decisions/DEC-001.json": js(DEC1), ".ddg/decisions/DEC-002.json": js(DEC2)}, "rule")
    good = commit(repo, {"src/pricing.py": GOOD_SRC}, "validate input")
    exception = commit(repo, {"src/pricing.py": "# zero is fine\n" + GOOD_SRC}, "document zero")
    refs = {"calibration_bad": bad, "calibration_good": good, "calibration_exception": exception}
    with patch.dict(os.environ, {"DDG_SANDBOX": "host"}):
        draft = wrap_draft(load_context(repo, decision_id="DEC-002", revision=good, adapter=ADAPTER),
                           CHECK, mode="manual")
        validation = validate_draft(repo, draft, refs)
        assert validation["eligible"], validation["cases"]
    git(repo, "checkout", "--quiet", "--detach", good)
    with patch.dict(os.environ, {"DDG_SANDBOX": "host"}):
        approve(repo, draft, validation, "Alice", "Reviewed pricing rule")
    base = commit(repo, {}, "approve DEC-002 check", email=approver_email)
    return repo, base


class LifecycleMixin:
    """Mode-agnostic scenarios. Subclasses set `mode`."""

    mode = "host"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = TemporaryDirectory(prefix="ddg e2e ")
        cls.addClassCleanup(cls._tmp.cleanup)
        # One approved demo per class: `run` never mutates the repo, so scenarios share it.
        test = unittest.TestCase()
        cls.repo, cls.state = lifecycle(test, cls.mode, cls._tmp.name)
        cls.refs = load(cls.repo / ".ddg-demo.json")["refs"]

    def run_branch(self, head, base="approved-base", repo=None, out_name=None):
        out = self.state / f"{out_name or head}.json"
        result = cli(["run", "--repo", repo or self.repo, "--base", base, "--head", head, "--out", out],
                     self.mode, cwd=repo or self.repo)
        return result, load(out), out

    def test_lifecycle_artifacts_are_committed_and_approved(self):
        self.assertTrue(load(self.state / "validation.json")["eligible"])
        for kind in ("checks", "validations", "approvals"):
            self.assertTrue((self.repo / ".ddg" / kind / "CHK-001.json").is_file(), kind)
        self.assertEqual(self.refs["approved_base"], resolve_commit(self.repo, "approved-base"))

    def test_every_scenario_branch(self):
        for head, (code, aggregate, verdict) in SCENARIOS.items():
            with self.subTest(head):
                result, report, _ = self.run_branch(head)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual(report["aggregate"], aggregate)
                self.assertEqual([c["verdict"] for c in report["checks"]], [verdict])
                self.assertEqual(report["sandbox"], self.mode)
                self.assertTrue(report["checks"][0]["approver"]["verified"])
                self.assertEqual(report["base_sha"], resolve_commit(self.repo, "approved-base"))
                self.assertEqual(report["head_sha"], resolve_commit(self.repo, head))
                self.assertEqual(json.loads(result.stdout)["aggregate"], aggregate)

    def test_incomplete_reports_carry_warning_codes(self):
        for head, code in (("policy-edit", "POLICY_REVIEW_REQUIRED"), ("approved-crashing", "EXECUTION_ERROR")):
            with self.subTest(head):
                _, report, _ = self.run_branch(head)
                self.assertIn(code, [w["code"] for w in report["warnings"]])

    def test_preexisting_failure_and_resolution(self):
        _, report, _ = self.run_branch("preexisting-head", base="preexisting-base")
        self.assertEqual(report["aggregate"], "FAILED")
        self.assertEqual(report["checks"][0]["verdict"], "PRE_EXISTING_FAILURE")
        result, report, _ = self.run_branch("resolved", base="preexisting-base")
        self.assertEqual((result.returncode, report["checks"][0]["verdict"]), (0, "RESOLVED"))

    def test_stale_report_detected_by_status(self):
        _, _, out = self.run_branch("regression")
        args = ["status", "--repo", self.repo, "--report", out, "--base", "approved-base", "--head", "regression"]
        fresh = cli(args, self.mode, cwd=self.repo)
        self.assertEqual((fresh.returncode, json.loads(fresh.stdout)["status"]), (0, "CURRENT"))
        # Work on a throwaway clone so the shared repo's refs never move.
        clone = Path(self._tmp.name) / f"stale-clone-{self.mode}"
        subprocess.run(["git", "clone", "--quiet", "--bare", "--no-local", str(self.repo), str(clone)], check=True,
                       capture_output=True)
        before = out.read_bytes()
        git(clone, "branch", "-f", "regression", self.refs["corrected"])
        stale = cli(["status", "--repo", clone, "--report", out, "--base", "approved-base", "--head", "regression"],
                    self.mode, cwd=clone)
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        self.assertEqual(json.loads(stale.stdout)["status"], "STALE")
        self.assertEqual(out.read_bytes(), before)

    def test_unapproved_author_is_incomplete(self):
        """Approval authored by someone outside .ddg/approvers.json cannot yield a PASS."""
        with TemporaryDirectory(prefix="ddg e2e ") as tmp:
            repo, _ = lifecycle(unittest.TestCase(), self.mode, tmp)
            # New base: the allowlist no longer names the author of the approval commit.
            git(repo, "checkout", "--quiet", "-B", "locked", "approved-base")
            commit(repo, {".ddg/approvers.json": policy(approvers=("someone-else@example.com",))}, "rotate approvers")
            result = cli(["run", "--repo", repo, "--base", "locked", "--head", "locked", "--out",
                          Path(tmp) / "r.json"], self.mode, cwd=repo)
            report = load(Path(tmp) / "r.json")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(report["aggregate"], "INCOMPLETE")
            self.assertIn("APPROVER_NOT_VERIFIED", [w["code"] for w in report["warnings"]])
            self.assertNotIn("CHECK_PASSED", [c["verdict"] for c in report["checks"]])

    def test_function_adapter_on_new_repo(self):
        with TemporaryDirectory(prefix="ddg e2e ") as tmp:
            repo, base = build_function_repo(tmp)
            cases = {"regression": (BAD, 1, "FAILED", "VIOLATION_INTRODUCED"),
                     "refactor": (REFACTORED, 0, "PASSED_CHECKS", "CHECK_PASSED"),
                     "crash": ("raise RuntimeError('boom')\n", 2, "INCOMPLETE", "NOT_CHECKED")}
            for name, (source, code, aggregate, verdict) in cases.items():
                with self.subTest(name):
                    git(repo, "checkout", "--quiet", "-B", name, base)
                    head = commit(repo, {"src/pricing.py": source}, name)
                    out = Path(tmp) / f"{name}.json"
                    result = cli(["run", "--repo", repo, "--base", base, "--head", head, "--out", out],
                                 self.mode, cwd=repo)
                    report = load(out)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertEqual((report["aggregate"], report["checks"][0]["verdict"]), (aggregate, verdict))
                    self.assertEqual(report["adapter_version"], ADAPTER)
                    self.assertEqual(report["sandbox"], self.mode)
                    self.assertTrue(report["checks"][0]["approver"]["verified"])

    def test_function_adapter_unapproved_author_is_incomplete(self):
        with TemporaryDirectory(prefix="ddg e2e ") as tmp:
            repo, base = build_function_repo(tmp, approver_email="mallory@example.com")
            out = Path(tmp) / "r.json"
            result = cli(["run", "--repo", repo, "--base", base, "--head", base, "--out", out], self.mode, cwd=repo)
            report = load(out)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("APPROVER_NOT_VERIFIED", [w["code"] for w in report["warnings"]])
            self.assertEqual(report["aggregate"], "INCOMPLETE")

    def test_serve_smoke(self):
        with TemporaryDirectory(prefix="ddg e2e ") as tmp:
            repo = Path(tmp) / "repo"
            self.assertEqual(cli(["demo-init", "--destination", repo], self.mode).returncode, 0)
            server = subprocess.Popen(
                [sys.executable, "-m", "ddg", "serve", "--repo", str(repo), "--state-dir", str(Path(tmp) / "st"),
                 "--port", "0"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", env={**os.environ, "DDG_SANDBOX": self.mode, "PYTHONPATH": str(ROOT)})
            self.addCleanup(self._stop, server)
            base = json.loads(server.stdout.readline())["serving"]  # --port 0 -> OS picks a free port
            self.assertIn("state", self._wait(base))
            with urllib.request.urlopen(base + "/", timeout=10) as page:
                token = re.search(r'name="ddg-session-token" content="([^"]+)"', page.read().decode()).group(1)

            def post(path, body):
                request = urllib.request.Request(base + path, json.dumps(body).encode(), method="POST", headers={
                    "Content-Type": "application/json", "X-DDG-Session": token})
                with urllib.request.urlopen(request, timeout=240) as response:
                    return json.loads(response.read())["state"]

            with self.assertRaises(urllib.error.HTTPError) as denied:  # no token -> 403
                urllib.request.urlopen(urllib.request.Request(
                    base + "/api/run", b"{}", method="POST", headers={"Content-Type": "application/json"}), timeout=10)
            self.assertEqual(denied.exception.code, 403)
            state = post("/api/propose", {"mode": "recorded"})
            digest = state["draft"]["draft_digest"]
            self.assertTrue(post("/api/validate", {"draft_digest": digest})["validation"]["eligible"])
            self.assertEqual(post("/api/approve", {"draft_digest": digest, "reviewer": "E2E Reviewer",
                                                   "reason": "Reviewed recorded calibration"})["lifecycle"], "approved")
            state = post("/api/run", {"scenario": "regression"})
            report = state["report"]
            self.assertEqual((report["aggregate"], report["checks"][0]["verdict"]), ("FAILED", "VIOLATION_INTRODUCED"))
            self.assertEqual(report["sandbox"], self.mode)
            self.assertTrue(report["checks"][0]["approver"]["verified"])
            self.assertEqual(self._wait(base)["state"]["report"]["aggregate"], "FAILED")
            self._stop(server)
            self.assertIsNotNone(server.poll())
            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(base + "/api/state", timeout=3)

    @staticmethod
    def _wait(base, seconds=30):
        deadline = time.time() + seconds
        while True:
            try:
                with urllib.request.urlopen(base + "/api/state", timeout=5) as response:
                    return json.loads(response.read())
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)

    @staticmethod
    def _stop(server):
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        for stream in (server.stdout, server.stderr):
            if stream:
                stream.close()


class HostLifecycleE2E(LifecycleMixin, unittest.TestCase):
    mode = "host"


@unittest.skipUnless(DOCKER_OK, DOCKER_SKIP_REASON)
class DockerLifecycleE2E(LifecycleMixin, unittest.TestCase):
    mode = "docker"

    @classmethod
    def tearDownClass(cls):
        # Retry: containers started by other concurrent runs on the same daemon may still be exiting.
        deadline = time.time() + 30
        while docker_leftovers() and time.time() < deadline:
            time.sleep(2)
        left = docker_leftovers()
        super().tearDownClass()
        assert not left, f"ddg-* containers left behind: {left}"


if __name__ == "__main__":
    unittest.main()
