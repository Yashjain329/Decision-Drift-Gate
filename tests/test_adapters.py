import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import adapters, sandbox
from ddg.approval import approve, validate_draft
from ddg.contracts import validate_check
from ddg.engine import compare
from ddg.gitio import resolve_commit
from ddg.proposal import load_context, wrap_draft
from tests.test_identity import GOOD, commit, git, policy

ADAPTER = "python_function_v1"
BAD = "def discount(price, tier):\n    return price * 0.8 if tier == 'GOLD' else float(price)\n"
GOOD_SRC = ("def discount(price, tier):\n    if price < 0:\n        raise ValueError('negative')\n"
            "    return price * 0.8 if tier == 'GOLD' else float(price)\n")
REFACTORED = ("def _rate(tier):\n    return 0.8 if tier == 'GOLD' else 1.0\n\n"
              "def discount(price, tier):\n    if price < 0:\n        raise ValueError('negative')\n    return price * _rate(tier)\n")
WRONG_EXC = GOOD_SRC.replace("ValueError", "TypeError")
DEC1 = {"schema_version": 1, "id": "DEC-001", "status": "superseded", "supersedes": None,
        "scope": "src/pricing.py", "rule": "Apply the tier rate to any price.", "exceptions": []}
DEC2 = {"schema_version": 1, "id": "DEC-002", "status": "active", "supersedes": "DEC-001",
        "scope": "src/pricing.py", "rule": "discount must reject negative prices with ValueError.",
        "exceptions": ["A zero price is valid and costs nothing."]}
CHECK = {
    "schema_version": 1, "id": "CHK-001", "decision_id": "DEC-002", "supersedes": "DEC-001", "adapter": ADAPTER,
    "scenario": {"path": "src/pricing.py", "function": "discount"},
    "assertions": [
        {"args": [100, "GOLD"], "expect": {"returns": 80.0}},
        {"args": [-1, "GOLD"], "expect": {"raises": "ValueError"}},
        {"args": [0, "GOLD"], "expect": {"returns": 0.0}},
    ],
    "rationale": "Negative prices must raise ValueError; zero stays valid.",
    "citations": [{"decision_id": "DEC-002", "quote": "must reject negative prices with ValueError"}],
}


def js(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def branch(repo, name, parent, files, msg, email=GOOD):
    git(repo, "checkout", "--quiet", "-B", name, parent)
    return commit(repo, files, msg, email=email)


class FunctionAdapterBase(unittest.TestCase):
    sandbox_mode = "host"

    @classmethod
    def build(cls, folder):
        repo = Path(folder) / "repo"
        repo.mkdir()
        git(repo, "init", "--quiet")
        commit(repo, {".ddg/approvers.json": policy(), ".ddg/decisions/DEC-001.json": js({**DEC1, "status": "active"}),
                      "src/pricing.py": BAD}, "initial")
        bad = commit(repo, {".ddg/decisions/DEC-001.json": js(DEC1), ".ddg/decisions/DEC-002.json": js(DEC2)}, "new rule")
        good = commit(repo, {"src/pricing.py": GOOD_SRC}, "validate input")
        exception = commit(repo, {"src/pricing.py": "# zero is fine\n" + GOOD_SRC}, "document zero")
        refs = {"calibration_bad": bad, "calibration_good": good, "calibration_exception": exception}
        context = load_context(repo, decision_id="DEC-002", revision=good, adapter=ADAPTER)
        draft = wrap_draft(context, CHECK, mode="manual")
        validation = validate_draft(repo, draft, refs)
        assert validation["eligible"], validation["cases"]
        git(repo, "checkout", "--quiet", "--detach", good)
        approve(repo, draft, validation, "Alice", "Reviewed pricing rule")
        base = commit(repo, {}, "approve DEC-002 check")
        return repo, base, validation

    def setUp(self):
        env = patch.dict(os.environ, {"DDG_SANDBOX": self.sandbox_mode, "DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        env.start()
        self.addCleanup(env.stop)
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo, self.base, self.validation = self.build(tmp.name)

    def head(self, name, source):
        return branch(self.repo, name, self.base, {"src/pricing.py": source}, name)


class FunctionAdapterTests(FunctionAdapterBase):
    def test_registry_lists_both_adapters(self):
        self.assertEqual(adapters.names(), ["python_function_v1", "python_job_client_v1"])
        with self.assertRaises(ValueError):
            adapters.get("nope")

    def test_calibration_recorded_bad_fail_good_pass(self):
        cases = self.validation["cases"]
        self.assertEqual(cases["bad"]["observation"]["status"], "FAIL")
        self.assertEqual(cases["good"]["observation"]["status"], "PASS")
        self.assertEqual(cases["exception"]["observation"]["status"], "PASS")

    def test_regression_is_a_violation(self):
        report = compare(self.repo, self.base, self.head("regression", BAD))
        self.assertEqual(report["aggregate"], "FAILED")
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        self.assertEqual(report["ordinary_tests"], {})
        self.assertIn("src/pricing.py", report["checks"][0]["diff"])
        self.assertEqual(report["adapter_version"], ADAPTER)

    def test_equivalent_refactor_passes(self):
        report = compare(self.repo, self.base, self.head("refactor", REFACTORED))
        self.assertEqual((report["aggregate"], report["checks"][0]["verdict"]), ("PASSED_CHECKS", "CHECK_PASSED"))
        self.assertTrue(report["checks"][0]["approver"]["verified"])

    def test_wrong_exception_type_is_a_violation(self):
        report = compare(self.repo, self.base, self.head("wrong", WRONG_EXC))
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")

    def test_crash_timeout_and_missing_function_are_not_checked(self):
        for name, source in (("crash", "raise RuntimeError('boom')\n"),
                             ("nofn", "x = 1\n"),
                             ("syntax", "def discount(:\n"),
                             ("denied", "import os\n" + GOOD_SRC),
                             ("loop", "while True:\n    pass\n")):
            with self.subTest(name):
                with patch("ddg.engine.RUNNER_TIMEOUT_SECONDS", 4.0):
                    report = compare(self.repo, self.base, self.head(name, source))
                self.assertEqual(report["aggregate"], "INCOMPLETE")
                self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")

    def test_deleted_source_is_not_checked(self):
        git(self.repo, "checkout", "--quiet", "-B", "deleted", self.base)
        git(self.repo, "rm", "--quiet", "src/pricing.py")
        git(self.repo, "commit", "--quiet", "-m", "delete", email=GOOD)
        report = compare(self.repo, self.base, resolve_commit(self.repo, "HEAD"))
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")

    def test_unserializable_return_never_matches(self):
        src = "def discount(price, tier):\n    return {1, 2}\n"
        report = compare(self.repo, self.base, self.head("set", src))
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")

    def test_policy_edit_alongside_pass_is_incomplete(self):
        git(self.repo, "checkout", "--quiet", "-B", "pol", self.base)
        commit(self.repo, {".ddg/decisions/DEC-002.json": js({**DEC2, "rule": DEC2["rule"] + " Edited."})}, "edit")
        self.assertEqual(compare(self.repo, self.base, resolve_commit(self.repo, "HEAD"))["aggregate"], "INCOMPLETE")


class FunctionCheckValidationTests(unittest.TestCase):
    def test_valid_check_round_trips(self):
        self.assertEqual(validate_check(CHECK), CHECK)

    def test_malformed_checks_are_rejected(self):
        def mut(change):
            check = json.loads(json.dumps(CHECK))
            change(check)
            return check
        bad = [
            mut(lambda c: c["scenario"].update(path="../x.py")),
            mut(lambda c: c["scenario"].update(path="/etc/x.py")),
            mut(lambda c: c["scenario"].update(path="src/x.txt")),
            mut(lambda c: c["scenario"].update(function="__import__")),
            mut(lambda c: c["scenario"].update(function="a b")),
            mut(lambda c: c.update(scenario="commit_then_503")),
            mut(lambda c: c.update(assertions=[])),
            mut(lambda c: c.update(assertions=[{"args": [1], "expect": {"returns": 1, "raises": "E"}}])),
            mut(lambda c: c.update(assertions=[{"args": "x", "expect": {"returns": 1}}])),
            mut(lambda c: c.update(assertions=[{"args": [float("nan")], "expect": {"returns": 1}}])),
            mut(lambda c: c.update(assertions=[{"args": [1], "expect": {"raises": "not valid"}}])),
            mut(lambda c: c.update(assertions=[{"args": [1], "expect": {"returns": 1}}] * 51)),
            mut(lambda c: c.update(adapter="python_unknown_v9")),
        ]
        for index, check in enumerate(bad):
            with self.subTest(index):
                with self.assertRaises(ValueError):
                    validate_check(check)

    def test_ai_proposals_refuse_non_job_adapters(self):
        from ddg.proposal import propose
        with self.assertRaisesRegex(ValueError, "AI proposals support only"):
            propose({"adapter_version": ADAPTER}, mode="live")


@unittest.skipUnless(sandbox._usable("docker"), "no usable docker daemon; container test skipped")
class FunctionAdapterContainerTests(FunctionAdapterBase):
    sandbox_mode = "docker"

    def test_same_verdicts_inside_container(self):
        report = compare(self.repo, self.base, self.head("regression", BAD))
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        report = compare(self.repo, self.base, self.head("refactor", REFACTORED))
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertEqual(report["sandbox"], "docker")


if __name__ == "__main__":
    unittest.main()
