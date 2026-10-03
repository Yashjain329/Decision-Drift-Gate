import copy
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg.approval import approve, validate_draft
from ddg.engine import compare
from ddg.gitio import read_at
from ddg.proposal import load_context, wrap_draft
from tests.support import commit_fixture, make_approved_demo


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix="ddg engine space ")
        cls.demo = make_approved_demo(Path(cls.temp.name) / "repo")
        cls.repo = Path(cls.demo["repo"])
        cls.refs = cls.demo["refs"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_reports_new_failure_and_valid_exception(self):
        bad = compare(self.repo, self.refs["approved_base"], self.refs["regression"])
        allowed = compare(self.repo, self.refs["approved_base"], self.refs["exception"])
        self.assertEqual(bad["aggregate"], "FAILED")
        self.assertEqual(bad["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        self.assertEqual([event["event"] for event in bad["checks"][0]["head"]["events"]],
                         ["submit", "accepted", "response", "submit", "accepted", "response"])
        self.assertEqual(allowed["aggregate"], "PASSED_CHECKS")
        self.assertEqual(allowed["checks"][0]["verdict"], "CHECK_PASSED")

    def test_reports_real_ordinary_observations_for_both_revisions(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["regression"])
        self.assertEqual(report["ordinary_tests"]["base"]["status"], "PASS")
        self.assertEqual(report["ordinary_tests"]["head"]["status"], "PASS")
        self.assertEqual(report["ordinary_tests"]["head"]["unique_jobs"], 1)

    def test_holdout_regression_is_detected_from_behavior(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["unseen_regression"])
        check = report["checks"][0]
        self.assertEqual((report["aggregate"], check["verdict"]), ("FAILED", "VIOLATION_INTRODUCED"))
        self.assertEqual((check["head"]["unique_jobs"], check["head"]["returned_job_exists"]), (2, True))

    def test_abort_is_a_new_violation_even_when_only_one_job_was_created(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["review_abort"])
        check = report["checks"][0]
        self.assertEqual(check["verdict"], "VIOLATION_INTRODUCED")
        self.assertEqual(check["head"]["unique_jobs"], 1)
        self.assertFalse(check["head"]["returned_job_exists"])

    def test_unrelated_change_runs_checks_and_ordinary_observations(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["unrelated"])
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertEqual(len(report["checks"]), 1)
        self.assertEqual(report["checks"][0]["verdict"], "CHECK_PASSED")
        self.assertEqual(report["checks"][0]["base"]["status"], "PASS")
        self.assertEqual(report["checks"][0]["head"]["status"], "PASS")
        self.assertEqual(report["ordinary_tests"]["base"]["status"], "PASS")
        self.assertEqual(report["ordinary_tests"]["head"]["status"], "PASS")

    def test_policy_edit_at_head_is_incomplete_but_keeps_observations(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["policy_edit"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertIn("POLICY_REVIEW_REQUIRED", {warning["code"] for warning in report["warnings"]})
        self.assertEqual(report["checks"][0]["verdict"], "CHECK_PASSED")
        self.assertEqual(report["checks"][0]["head"]["status"], "PASS")

    def test_head_check_deletion_cannot_remove_base_authority(self):
        base = self.refs["approved_base"]
        check_path = ".ddg/checks/CHK-001.json"
        head = commit_fixture(self.repo, base, {check_path: None}, "Delete candidate check")
        report = compare(self.repo, base, head)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertIn("POLICY_REVIEW_REQUIRED", {warning["code"] for warning in report["warnings"]})
        self.assertEqual(report["checks"][0]["check_id"], "CHK-001")
        self.assertEqual(report["checks"][0]["verdict"], "CHECK_PASSED")

    def test_tampered_base_approval_digest_is_not_checked(self):
        base = self.refs["approved_base"]
        path = ".ddg/approvals/CHK-001.json"
        approval = json.loads(read_at(self.repo, base, path))
        approval["bundle_digest"] = "0" * 64
        tampered = commit_fixture(self.repo, base, {path: json.dumps(approval)}, "Tamper approval bundle")
        report = compare(self.repo, tampered, self.refs["regression"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
        self.assertIsNone(report["checks"][0]["base"]["unique_jobs"])

    def test_unapproved_check_at_base_is_not_executed(self):
        base = self.refs["approved_base"]
        path = ".ddg/approvals/CHK-001.json"
        unapproved = commit_fixture(self.repo, base, {path: None}, "Remove approval")
        report = compare(self.repo, unapproved, self.refs["regression"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
        self.assertIn("MISSING_APPROVED_COVERAGE", {warning["code"] for warning in report["warnings"]})

    def test_check_path_and_record_id_must_match(self):
        base = self.refs["approved_base"]
        path = ".ddg/checks/CHK-001.json"
        check = json.loads(read_at(self.repo, base, path))
        check["id"] = "CHK-002"
        malformed = commit_fixture(self.repo, base, {path: json.dumps(check)}, "Mismatch check path and id")
        report = compare(self.repo, malformed, self.refs["regression"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
        self.assertIsNone(report["checks"][0]["base"]["unique_jobs"])

    def test_missing_and_cyclic_decision_graphs_are_incomplete(self):
        base = self.refs["approved_base"]
        missing = commit_fixture(self.repo, base, {".ddg/decisions/DEC-001.json": None}, "Remove predecessor")
        cycle_decision = json.loads(read_at(self.repo, base, ".ddg/decisions/DEC-001.json"))
        cycle_decision["supersedes"] = "DEC-002"
        cycle_decision["status"] = "superseded"
        cyclic = commit_fixture(
            self.repo, base,
            {".ddg/decisions/DEC-001.json": json.dumps(cycle_decision)},
            "Create decision cycle",
        )
        for bad_base in (missing, cyclic):
            with self.subTest(base=bad_base):
                report = compare(self.repo, bad_base, self.refs["unrelated"])
                self.assertEqual(report["aggregate"], "INCOMPLETE")
                self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
                self.assertIn("INVALID_DECISION_GRAPH", {warning["code"] for warning in report["warnings"]})

    def test_uncovered_second_active_decision_keeps_valid_checks_visible(self):
        base = self.refs["approved_base"]
        decision = {"schema_version": 1, "id": "DEC-003", "status": "active", "supersedes": None,
                    "scope": "src/job_client.py", "rule": "Record a distinct active rule.", "exceptions": []}
        incomplete_base = commit_fixture(
            self.repo, base,
            {".ddg/decisions/DEC-003.json": json.dumps(decision)},
            "Add uncovered active decision",
        )
        report = compare(self.repo, incomplete_base, self.refs["unrelated"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "CHECK_PASSED")
        self.assertIn("DEC-003", " ".join(warning["message"] for warning in report["warnings"]))
        self.assertEqual(report["active_decisions"][0]["id"], "DEC-002")
        self.assertTrue(report["active_decisions"][0]["rule"])

    def test_superseded_check_is_skipped_without_blocking_successor(self):
        base = self.refs["approved_base"]
        decision_2 = json.loads(read_at(self.repo, base, ".ddg/decisions/DEC-002.json"))
        decision_2["status"] = "superseded"
        decision_3 = {"schema_version": 1, "id": "DEC-003", "status": "active", "supersedes": "DEC-001",
                      "scope": "src/job_client.py", "rule": "This operation must remain covered by an approved check.",
                      "exceptions": []}
        historical_base = commit_fixture(
            self.repo, base,
            {".ddg/decisions/DEC-002.json": json.dumps(decision_2),
             ".ddg/decisions/DEC-003.json": json.dumps(decision_3)},
            "Supersede the checked decision",
        )
        subprocess.run(["git", "-C", str(self.repo), "checkout", "--quiet", "--detach", historical_base],
                       check=True, capture_output=True, text=True, encoding="utf-8")
        context = load_context(self.repo, decision_id="DEC-003", revision=historical_base)
        check = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))
        check.update({"id": "CHK-002", "decision_id": "DEC-003", "supersedes": "DEC-001"})
        check["citations"] = [{"decision_id": "DEC-003", "quote": "must remain covered by an approved check"}]
        draft = wrap_draft(context, check, mode="manual")
        validation = validate_draft(self.repo, draft, self.refs)
        approve(self.repo, draft, validation, "Test Developer", "Review successor coverage")
        current_base = commit_fixture(self.repo, historical_base, {}, "Approve successor check")
        source = read_at(self.repo, current_base, "src/job_client.py")
        head = commit_fixture(self.repo, current_base, {"src/job_client.py": "# harmless change\n" + source},
                              "Change source under successor policy")

        report = compare(self.repo, current_base, head)
        old = next(item for item in report["checks"] if item["check_id"] == "CHK-001")
        new = next(item for item in report["checks"] if item["check_id"] == "CHK-002")
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertEqual(old["verdict"], "HISTORICAL_CHECK_IGNORED")
        self.assertIsNone(old["base"])
        self.assertEqual(new["verdict"], "CHECK_PASSED")
        self.assertEqual(report["active_decisions"], [decision_3])
        self.assertIn("HISTORICAL_CHECK_IGNORED", {warning["code"] for warning in report["warnings"]})

    def test_file_mode_change_under_ddg_triggers_policy_review(self):
        base = self.refs["approved_base"]
        subprocess.run(["git", "-C", str(self.repo), "checkout", "--quiet", "--detach", base],
                       check=True, capture_output=True, text=True, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "-c", "core.filemode=true", "update-index", "--chmod=+x",
                        "--", ".ddg/checks/CHK-001.json"], check=True, capture_output=True,
                       text=True, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=DDG Test", "-c",
                        "user.email=ddg-test@example.invalid", "commit", "--quiet", "-m", "Mode-only policy edit"],
                       check=True, capture_output=True, text=True, encoding="utf-8")
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        report = compare(self.repo, base, head)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertIn("POLICY_REVIEW_REQUIRED", {warning["code"] for warning in report["warnings"]})

    def test_missing_changed_line_evidence_cannot_produce_green(self):
        with patch("ddg.engine.diff_at", side_effect=ValueError("diff unavailable")):
            report = compare(self.repo, self.refs["approved_base"], self.refs["exception"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "CHECK_PASSED")
        self.assertIn("DIFF_UNAVAILABLE", {warning["code"] for warning in report["warnings"]})
        self.assertEqual(report["checks"][0]["base"]["status"], "PASS")
        self.assertEqual(report["checks"][0]["head"]["status"], "PASS")

    def test_zero_checks_is_incomplete_not_empty_green(self):
        base = self.refs["approved_base"]
        paths = {
            f".ddg/{kind}/CHK-001.json": None
            for kind in ("checks", "validations", "approvals")
        }
        no_checks = commit_fixture(self.repo, base, paths, "Remove all approved checks")
        report = compare(self.repo, no_checks, self.refs["unrelated"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"], [])
        self.assertIn("NO_ACTIVE_APPROVED_CHECKS", {warning["code"] for warning in report["warnings"]})

    def test_preexisting_failure_and_resolution_are_attributed_correctly(self):
        preexisting = compare(self.repo, self.refs["preexisting_base"], self.refs["preexisting_head"])
        resolved = compare(self.repo, self.refs["preexisting_base"], self.refs["resolved"])
        self.assertEqual((preexisting["aggregate"], preexisting["checks"][0]["verdict"]),
                         ("FAILED", "PRE_EXISTING_FAILURE"))
        self.assertEqual((resolved["aggregate"], resolved["checks"][0]["verdict"]),
                         ("PASSED_CHECKS", "RESOLVED"))

    def test_crash_timeout_and_missing_entrypoint_are_not_checked(self):
        for key in ("review_crashing", "review_missing_entrypoint"):
            report = compare(self.repo, self.refs["approved_base"], self.refs[key])
            self.assertEqual(report["aggregate"], "INCOMPLETE", key)
            self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED", key)
            self.assertEqual(report["checks"][0]["head"]["status"], "ERROR", key)
        with patch("ddg.engine.RUNNER_TIMEOUT_SECONDS", 0.2):
            report = compare(self.repo, self.refs["approved_base"], self.refs["review_timing_out"])
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
        self.assertEqual(report["checks"][0]["head"]["status"], "ERROR")

    def test_missing_source_object_is_not_checked_and_ref_errors_raise(self):
        base = self.refs["approved_base"]
        missing_source = commit_fixture(self.repo, base, {"src/job_client.py": None}, "Remove adapter source")
        report = compare(self.repo, base, missing_source)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")
        self.assertEqual(report["checks"][0]["head"]["status"], "ERROR")
        with self.assertRaises(ValueError):
            compare(self.repo, base, "missing-revision")

    def test_report_keeps_full_hashes_and_exact_observations(self):
        report = compare(self.repo, self.refs["approved_base"], self.refs["regression"])
        self.assertRegex(report["base_sha"], r"^[0-9a-f]{40}$")
        self.assertRegex(report["head_sha"], r"^[0-9a-f]{40}$")
        self.assertEqual(report["base_sha"], self.refs["approved_base"])
        self.assertEqual(report["head_sha"], self.refs["regression"])
        check = report["checks"][0]
        self.assertEqual((check["base"]["unique_jobs"], check["head"]["unique_jobs"]), (1, 2))
        self.assertIn("src/job_client.py", check["diff"])
        self.assertEqual(report["adapter_version"], "python_job_client_v1")


if __name__ == "__main__":
    unittest.main()
