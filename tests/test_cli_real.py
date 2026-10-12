"""CLI lifecycle on a brand-new repository (no demo marker) with the python_function_v1 adapter."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ddg import sandbox
from tests.test_adapters import ADAPTER, BAD, CHECK, DEC1, DEC2, GOOD_SRC, REFACTORED, js
from tests.test_identity import GOOD, commit, git

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, env=None, cwd=ROOT):
    environment = dict(os.environ, DDG_ALLOW_UNVERIFIED_APPROVERS="")
    environment.update(env or {})
    return subprocess.run([sys.executable, "-m", "ddg", *map(str, args)], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", env=environment, timeout=120)


def new_repo(folder):
    repo = Path(folder) / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    git(repo, "config", "user.email", GOOD)
    return repo


class InitTests(unittest.TestCase):
    def test_init_writes_policy_from_git_email_and_refuses_overwrite(self):
        with TemporaryDirectory() as tmp:
            repo = new_repo(tmp)
            first = run_cli("init", "--repo", repo)
            self.assertEqual(first.returncode, 0, first.stderr)
            policy = json.loads((repo / ".ddg/approvers.json").read_text(encoding="utf-8"))
            self.assertEqual(policy, {"schema_version": 1, "require_signed": False, "approvers": [GOOD]})
            before = (repo / ".ddg/approvers.json").read_bytes()
            second = run_cli("init", "--repo", repo, "--approver", "evil@example.com")
            self.assertEqual(second.returncode, 3)
            self.assertIn("Refusing to overwrite", second.stderr)
            self.assertEqual((repo / ".ddg/approvers.json").read_bytes(), before)

    def test_init_explicit_approvers_and_error_cases(self):
        with TemporaryDirectory() as tmp:
            repo = new_repo(tmp)
            ok = run_cli("init", "--repo", repo, "--approver", "a@x.org", "--approver", "b@x.org")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads((repo / ".ddg/approvers.json").read_text(encoding="utf-8"))["approvers"],
                             ["a@x.org", "b@x.org"])
            plain = Path(tmp) / "not-git"
            plain.mkdir()
            self.assertEqual(run_cli("init", "--repo", plain).returncode, 3)
            self.assertEqual(run_cli("init", "--repo", repo / "missing").returncode, 3)
            bad = run_cli("init", "--repo", plain, "--approver", "no-at-sign")
            self.assertEqual(bad.returncode, 3)
            self.assertFalse((plain / ".ddg").exists())


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory(prefix="ddg real ")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.repo = repo = new_repo(cls.tmp.name)
        assert run_cli("init", "--repo", repo).returncode == 0
        commit(repo, {".ddg/decisions/DEC-001.json": js({**DEC1, "status": "active"}),
                      "src/pricing.py": BAD}, "initial")
        cls.bad = commit(repo, {".ddg/decisions/DEC-001.json": js(DEC1),
                                ".ddg/decisions/DEC-002.json": js(DEC2)}, "new rule")
        cls.good = commit(repo, {"src/pricing.py": GOOD_SRC}, "validate input")
        cls.exception = commit(repo, {"src/pricing.py": "# zero is fine\n" + GOOD_SRC}, "document zero")
        cls.state = Path(cls.tmp.name) / "state"
        cls.state.mkdir()
        cls.check_file = cls.state / "check.json"
        cls.check_file.write_text(js(CHECK), encoding="utf-8")
        cls.draft = cls.state / "draft.json"
        cls.validation = cls.state / "validation.json"

    def cal(self, bad=None, good=None, exception=None):
        return ["--calibration-bad", bad or self.bad, "--calibration-good", good or self.good,
                "--calibration-exception", exception or self.exception]

    def test_lifecycle_exit_codes(self):
        repo, state = self.repo, self.state
        # propose: adapter rules
        live = run_cli("propose", "--repo", repo, "--adapter", ADAPTER, "--out", state / "x.json")
        self.assertEqual(live.returncode, 3)
        self.assertIn("supports only --mode manual", live.stderr)
        nocheck = run_cli("propose", "--repo", repo, "--adapter", ADAPTER, "--mode", "manual",
                          "--out", state / "x.json")
        self.assertEqual(nocheck.returncode, 3)
        job = run_cli("propose", "--repo", repo, "--mode", "manual", "--check", self.check_file,
                      "--out", state / "x.json")
        self.assertEqual(job.returncode, 3, "job adapter needs src/job_client.py")
        proposal = run_cli("propose", "--repo", repo, "--adapter", ADAPTER, "--mode", "manual",
                           "--revision", self.good, "--check", self.check_file, "--out", self.draft)
        self.assertEqual(proposal.returncode, 0, proposal.stderr)
        self.assertEqual(json.loads(self.draft.read_text(encoding="utf-8"))["adapter_version"], ADAPTER)

        # validate: refs come from flags only; no marker means an error
        out = ["--repo", repo, "--draft", self.draft, "--out", self.validation]
        self.assertEqual(run_cli("validate", *out).returncode, 3)
        partial = run_cli("validate", *out, "--calibration-bad", self.bad)
        self.assertEqual(partial.returncode, 3)
        self.assertIn("all of", partial.stderr)
        self.assertEqual(run_cli("validate", *out, *self.cal(bad="no-such-ref")).returncode, 3)
        swapped = run_cli("validate", *out, *self.cal(bad=self.good, good=self.bad))
        self.assertEqual(swapped.returncode, 1)
        self.assertFalse(json.loads(swapped.stdout)["eligible"])
        valid = run_cli("validate", *out, *self.cal(bad=self.bad[:12], good="HEAD~1"))
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertTrue(json.loads(self.validation.read_text(encoding="utf-8"))["eligible"])

        # approve: writes artifacts, never commits
        head_before = git(repo, "rev-parse", "HEAD")
        approval = run_cli("approve", "--repo", repo, "--draft", self.draft, "--validation", self.validation,
                           "--reviewer", "Alice", "--reason", "Reviewed pricing rule")
        self.assertEqual(approval.returncode, 0, approval.stderr)
        printed = json.loads(approval.stdout)
        self.assertEqual(len(printed["written"]), 3)
        for path in printed["written"]:
            self.assertTrue(Path(path).is_file())
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head_before)
        self.assertIn(".ddg/approvals/CHK-001.json", git(repo, "status", "--porcelain", "--untracked-files=all"))
        again = run_cli("approve", "--repo", repo, "--draft", self.draft, "--validation", self.validation,
                        "--reviewer", "Alice", "--reason", "twice")
        self.assertEqual(again.returncode, 3)

        # approver commits; runs on branches
        base = commit(repo, {}, "approve CHK-001")
        git(repo, "checkout", "--quiet", "-B", "regression", base)
        regression = commit(repo, {"src/pricing.py": BAD}, "regress")
        git(repo, "checkout", "--quiet", "-B", "refactor", base)
        refactor = commit(repo, {"src/pricing.py": REFACTORED}, "refactor")
        git(repo, "checkout", "--quiet", "-B", "policy", base)
        policy = commit(repo, {".ddg/decisions/DEC-002.json": js({**DEC2, "rule": DEC2["rule"] + " Edited."})}, "edit")

        report = state / "r.json"
        def run(head, *extra, base_rev=base, env=None):
            return run_cli("run", "--repo", repo, "--base", base_rev, "--head", head, "--out", report,
                           *extra, env=env)

        failed = run(regression)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["aggregate"], "FAILED")
        self.assertTrue(report.with_suffix(".md").exists())
        self.assertIn("UNSANDBOXED", failed.stderr)  # test default sandbox is host

        passed = run(refactor)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["aggregate"], "PASSED_CHECKS")

        self.assertEqual(run(policy).returncode, 2)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["aggregate"], "INCOMPLETE")

        # usage/infra errors
        self.assertEqual(run("no-such-rev").returncode, 3)
        self.assertEqual(run_cli("run", "--repo", state / "missing", "--base", base, "--head", refactor,
                                 "--out", report).returncode, 3)
        self.assertEqual(run_cli("run", "--repo", repo, "--base", base, "--head", refactor,
                                 "--out", repo / ".ddg" / "r.json").returncode, 3)
        self.assertEqual(run(refactor, "--sandbox", "bogus").returncode, 3)

        # --format
        for fmt, has_json, has_md in (("json", True, False), ("md", False, True), ("both", True, True)):
            with self.subTest(fmt):
                for path in (report, report.with_suffix(".md")):
                    path.unlink(missing_ok=True)
                result = run(refactor, "--format", fmt)
                self.assertEqual(result.returncode, 0)
                self.assertTrue(Path(json.loads(result.stdout)["report"]).is_file())
                self.assertEqual((report.exists(), report.with_suffix(".md").exists()), (has_json, has_md))

        # sandbox flag overrides the environment and host warns
        warned = run(refactor, "--sandbox", "host", env={"DDG_SANDBOX": "auto"})
        self.assertEqual(warned.returncode, 0, warned.stderr)
        self.assertIn("UNSANDBOXED", warned.stderr)
        if not sandbox._usable("podman"):
            self.assertEqual(run(refactor, "--sandbox", "podman").returncode, 3)

    def test_help_documents_exit_codes(self):
        helped = run_cli("--help")
        self.assertEqual(helped.returncode, 0)
        for fragment in ("PASSED_CHECKS", "FAILED", "INCOMPLETE", "usage/infra"):
            self.assertIn(fragment, helped.stdout)


@unittest.skipUnless(sandbox._usable("docker"), "no usable docker daemon; container run skipped")
class LifecycleDockerTests(unittest.TestCase):
    def test_init_to_run_in_container(self):
        with TemporaryDirectory() as tmp:
            repo = new_repo(tmp)
            state = Path(tmp) / "state"
            state.mkdir()
            self.assertEqual(run_cli("init", "--repo", repo).returncode, 0)
            commit(repo, {".ddg/decisions/DEC-001.json": js({**DEC1, "status": "active"}), "src/pricing.py": BAD}, "i")
            bad = commit(repo, {".ddg/decisions/DEC-001.json": js(DEC1), ".ddg/decisions/DEC-002.json": js(DEC2)}, "r")
            good = commit(repo, {"src/pricing.py": GOOD_SRC}, "g")
            exc = commit(repo, {"src/pricing.py": "# z\n" + GOOD_SRC}, "e")
            (state / "check.json").write_text(js(CHECK), encoding="utf-8")
            draft, validation = state / "d.json", state / "v.json"
            steps = [
                ("propose", "--repo", repo, "--adapter", ADAPTER, "--mode", "manual", "--revision", good,
                 "--check", state / "check.json", "--out", draft),
                ("validate", "--repo", repo, "--draft", draft, "--out", validation, "--calibration-bad", bad,
                 "--calibration-good", good, "--calibration-exception", exc),
                ("approve", "--repo", repo, "--draft", draft, "--validation", validation,
                 "--reviewer", "Alice", "--reason", "ok"),
            ]
            for step in steps:
                result = run_cli(*step, env={"DDG_SANDBOX": "docker"})
                self.assertEqual(result.returncode, 0, result.stderr)
            base = commit(repo, {}, "approve")
            git(repo, "checkout", "--quiet", "-B", "regression", base)
            commit(repo, {"src/pricing.py": BAD}, "regress")
            out = state / "report.json"
            final = run_cli("run", "--repo", repo, "--base", base, "--head", "regression", "--out", out,
                            env={"DDG_SANDBOX": "docker"})
            self.assertEqual(final.returncode, 1, final.stderr)
            self.assertNotIn("UNSANDBOXED", final.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((report["aggregate"], report["sandbox"]), ("FAILED", "docker"))


if __name__ == "__main__":
    unittest.main()
