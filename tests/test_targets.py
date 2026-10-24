"""No fixed layout: the job-client target comes from the decision scope, ids are inferred or chosen.

The end-to-end class drives the real CLI on a brand-new repository whose job client lives at
services/billing/jobs.py (not the demo's src/job_client.py).
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import adapters
from ddg.demo import _DECISION_1, _DECISION_2, build_demo
from ddg.gitio import read_at
from ddg.proposal import infer_decision_id, load_context, next_check_id
from tests.e2e.harness import DOCKER_OK, cli, load
from tests.test_identity import GOOD, commit, git, policy

TARGET = "services/billing/jobs.py"
JOB = adapters.get("python_job_client_v1")


def js(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def _demo_sources(folder):
    """Bad, corrected and exception job-client sources, taken from the generated demo."""
    demo = build_demo(Path(folder) / "demo")
    repo, refs = Path(demo["repo"]), demo["refs"]
    return {k: read_at(repo, refs[f"calibration_{k}"], "src/job_client.py") for k in ("bad", "good", "exception")}


def build_job_repo(folder, sources):
    """A fresh repository with the job client at TARGET and decisions scoped to it."""
    repo = Path(folder) / "jobs-repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    old = {**_DECISION_1, "scope": TARGET}
    new = {**_DECISION_2, "scope": TARGET}
    commit(repo, {".ddg/approvers.json": policy(), ".ddg/decisions/DEC-001.json": js({**old, "status": "active"}),
                  TARGET: sources["bad"]}, "initial")
    bad = commit(repo, {".ddg/decisions/DEC-001.json": js(old), ".ddg/decisions/DEC-002.json": js(new)}, "replace rule")
    good = commit(repo, {TARGET: sources["good"]}, "dedupe by operation id")
    exception = commit(repo, {TARGET: sources["exception"]}, "allowed retry")
    return repo, {"bad": bad, "good": good, "exception": exception}


class TargetUnitTests(unittest.TestCase):
    def test_job_target_is_the_decision_scope(self):
        self.assertEqual(JOB.target_path({"scope": TARGET}), TARGET)
        self.assertEqual(JOB.source_path({}, {"scope": TARGET}), TARGET)
        for scope in ("billing module", "../x.py", "/abs/x.py", "a//b.py", None):
            with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, "decision scope"):
                JOB.target_path({"scope": scope})

    def test_decision_is_inferred_only_when_unambiguous(self):
        one = {"DEC-001": {"status": "superseded", "supersedes": None}, "DEC-002": {"status": "active", "supersedes": "DEC-001"}}
        self.assertEqual(infer_decision_id(one), "DEC-002")
        two = {**one, "DEC-004": {"status": "active", "supersedes": "DEC-003"}, "DEC-003": {"status": "superseded", "supersedes": None}}
        with self.assertRaisesRegex(ValueError, "DEC-002, DEC-004"):
            infer_decision_id(two)
        with self.assertRaisesRegex(ValueError, "no active decision"):
            infer_decision_id({"DEC-001": {"status": "active", "supersedes": None}})

    def test_next_check_id_and_missing_target(self):
        with TemporaryDirectory(prefix="ddg-targets-") as tmp:
            repo = Path(tmp)
            git(repo, "init", "--quiet")
            first = commit(repo, {".ddg/approvers.json": policy()}, "init")
            self.assertEqual(next_check_id(repo, first), "CHK-001")
            second = commit(repo, {".ddg/checks/CHK-001.json": "{}", ".ddg/checks/CHK-003.json": "{}"}, "checks")
            self.assertEqual(next_check_id(repo, second), "CHK-002")
            old = {**_DECISION_1, "scope": TARGET}
            new = {**_DECISION_2, "scope": TARGET}
            head = commit(repo, {".ddg/decisions/DEC-001.json": js(old), ".ddg/decisions/DEC-002.json": js(new)}, "rules")
            with self.assertRaisesRegex(ValueError, f"Target module {TARGET} .* not in commit"):
                load_context(repo, revision=head)


class AnyLayoutEndToEndTests(unittest.TestCase):
    """init-free real repo: propose -> validate -> approve -> commit -> run, all through the CLI."""

    mode = "docker" if DOCKER_OK else "host"

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory(prefix="ddg targets e2e ")
        cls.addClassCleanup(cls._tmp.cleanup)
        tmp = Path(cls._tmp.name)
        cls.sources = _demo_sources(tmp)
        cls.repo, cls.refs = build_job_repo(tmp, cls.sources)
        cls.work = tmp / "work"
        cls.work.mkdir()
        check = tmp / "check.json"
        check.write_text(Path("examples/manual_check.json").read_text(encoding="utf-8"), encoding="utf-8")
        draft, validation = cls.work / "draft.json", cls.work / "validation.json"

        def run(*args):
            result = cli(args, cls.mode, cwd=cls.repo)
            assert result.returncode == 0, (args[0], result.stdout, result.stderr)
            return result

        # No --decision: DEC-002 is the only active decision that supersedes another.
        run("propose", "--repo", cls.repo, "--adapter", "python_job_client_v1", "--mode", "manual",
            "--check", check, "--revision", cls.refs["good"], "--out", draft)
        run("validate", "--repo", cls.repo, "--draft", draft, "--out", validation,
            "--calibration-bad", cls.refs["bad"], "--calibration-good", cls.refs["good"],
            "--calibration-exception", cls.refs["exception"])
        git(cls.repo, "checkout", "--quiet", "-b", "main", cls.refs["good"])
        run("approve", "--repo", cls.repo, "--draft", draft, "--validation", validation,
            "--reviewer", "Alice", "--reason", "Calibrated on bad, good and exception")
        cls.base = commit(cls.repo, {}, "Approve CHK-001", email=GOOD)
        git(cls.repo, "checkout", "--quiet", "-b", "regression", cls.base)
        commit(cls.repo, {TARGET: cls.sources["bad"]}, "restore blind retry")
        git(cls.repo, "checkout", "--quiet", "-b", "feature", cls.base)
        commit(cls.repo, {"README.md": "docs\n"}, "unrelated change")

    def run_head(self, head):
        out = self.work / f"{head}.json"
        result = cli(["run", "--repo", self.repo, "--base", "main", "--head", head, "--out", out], self.mode, cwd=self.repo)
        return result, load(out)

    def test_regression_at_custom_path_fails(self):
        result, report = self.run_head("regression")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report["aggregate"], "FAILED")
        check = report["checks"][0]
        self.assertEqual((check["check_id"], check["verdict"]), ("CHK-001", "VIOLATION_INTRODUCED"))
        self.assertEqual((check["base"]["unique_jobs"], check["head"]["unique_jobs"]), (1, 2))
        self.assertIn(TARGET, check["diff"])
        self.assertEqual(report["ordinary_tests"]["head"]["status"], "PASS")
        self.assertEqual(report["sandbox"], self.mode)

    def test_unrelated_change_passes(self):
        result, report = self.run_head("feature")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")

    def test_unreachable_source_commit_names_the_cause(self):
        """A squashed/rewritten history: the validation pins a commit the clone does not have."""
        out = self.work / "rewritten.json"
        with TemporaryDirectory(prefix="ddg-squash-") as tmp:
            clone = Path(tmp) / "clone"
            git(Path(tmp), "clone", "--quiet", "--single-branch", "--branch", "main", str(self.repo), str(clone))
            # Rewrite main to one squashed commit: the pinned calibration/source commits disappear.
            git(clone, "checkout", "--quiet", "--orphan", "squashed")
            git(clone, "commit", "--quiet", "-m", "squash", email=GOOD)
            git(clone, "branch", "-D", "main")
            git(clone, "remote", "remove", "origin")
            git(clone, "reflog", "expire", "--expire=now", "--all")
            git(clone, "gc", "--quiet", "--prune=now")
            result = cli(["run", "--repo", clone, "--base", "squashed", "--head", "squashed", "--out", out], self.mode, cwd=clone)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        messages = " ".join(w["message"] for w in load(out)["warnings"])
        self.assertIn("Proposal source commit " + json.loads(
            (self.repo / ".ddg/validations/CHK-001.json").read_text(encoding="utf-8"))["source_sha"][:12], messages)
        self.assertIn("squashed", messages)


if __name__ == "__main__":
    unittest.main()
