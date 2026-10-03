import copy
import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg.approval import approve, bundle_digest, validate_draft, verify_bundle
from ddg.contracts import digest
from ddg.demo import build_demo
from tests.support import make_approved_demo, make_manual_draft, refingerprint


class ApprovalTests(unittest.TestCase):
    def test_calibration_requires_bad_fail_good_pass_and_exception_pass(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            validation = validate_draft(repo, make_manual_draft(repo, demo["refs"]), demo["refs"])
            self.assertTrue(validation["eligible"])
            self.assertEqual(validation["adapter_version"], "python_job_client_v1")
            self.assertEqual({case: validation["cases"][case]["observation"]["status"]
                              for case in ("bad", "good", "exception")},
                             {"bad": "FAIL", "good": "PASS", "exception": "PASS"})
            self.assertEqual(validation["cases"]["bad"]["observation"]["unique_jobs"], 2)
            self.assertEqual(validation["cases"]["good"]["observation"]["unique_jobs"], 1)
            self.assertEqual(validation["cases"]["exception"]["observation"]["unique_jobs"], 1)

    def test_weak_reject_scenario_is_not_eligible(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            draft["check"]["scenario"] = "reject_then_503"
            draft = refingerprint(draft)
            validation = validate_draft(repo, draft, demo["refs"])
            self.assertFalse(validation["eligible"])
            with self.assertRaises(ValueError):
                approve(repo, draft, validation, "Dev", "Reviewed")
            self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())

    def test_completion_is_mandatory_even_if_draft_asserts_false(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            for assertion in draft["check"]["assertions"]:
                if assertion["metric"] == "returned_job_exists":
                    assertion["equals"] = False
            draft = refingerprint(draft)
            validation = validate_draft(repo, draft, demo["refs"])
            self.assertFalse(validation["eligible"])
            self.assertEqual(validation["cases"]["good"]["observation"]["status"], "FAIL")
            with self.assertRaises(ValueError):
                approve(repo, draft, validation, "Dev", "Reviewed")

    def test_any_calibration_execution_error_blocks_approval(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            refs = dict(demo["refs"], calibration_good=demo["refs"]["crashing"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, refs)
            self.assertFalse(validation["eligible"])
            self.assertEqual(validation["cases"]["good"]["observation"]["status"], "ERROR")

    def test_review_identity_and_reason_are_required(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            for reviewer, reason in (("", "reason"), (" ", "reason"), ("Dev", ""), ("Dev", " ")):
                with self.subTest(reviewer=reviewer, reason=reason), self.assertRaises(ValueError):
                    approve(repo, draft, validation, reviewer, reason)
            self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())

    def test_check_edit_after_validation_invalidates_validation(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            edited = copy.deepcopy(draft)
            edited["check"]["rationale"] = "A changed rationale invalidates earlier calibration."
            edited = refingerprint(edited)
            with self.assertRaises(ValueError):
                approve(repo, edited, validation, "Dev", "Reviewed")

    def test_decision_edit_after_validation_invalidates_validation(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            edited = copy.deepcopy(draft)
            edited["decision"]["rule"] += " New uncalibrated requirement."
            edited = refingerprint(edited)
            with self.assertRaises(ValueError):
                approve(repo, edited, validation, "Dev", "Reviewed")

    def test_live_label_without_provider_provenance_is_refused(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            draft["proposal_mode"] = "live"
            draft = refingerprint(draft)
            with self.assertRaises(ValueError):
                validate_draft(repo, draft, demo["refs"])

    def test_malformed_draft_types_raise_value_error(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            bad_mode = make_manual_draft(repo, demo["refs"])
            bad_mode["proposal_mode"] = []
            for malformed in (bad_mode,):
                with self.assertRaises(ValueError):
                    validate_draft(repo, refingerprint(malformed), demo["refs"])
            bad_attempt = make_manual_draft(repo, demo["refs"])
            bad_attempt["attempts"] = [{"attempt": 1, "result": []}]
            with self.assertRaises(ValueError):
                validate_draft(repo, refingerprint(bad_attempt), demo["refs"])

    def test_approved_artifact_binds_exact_check_decision_and_validation(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            approval = approve(repo, draft, validation, "Dev", "Reviewed all calibrations.")
            check = json.loads((repo / ".ddg/checks/CHK-001.json").read_text(encoding="utf-8"))
            stored_validation = json.loads((repo / ".ddg/validations/CHK-001.json").read_text(encoding="utf-8"))
            stored_approval = json.loads((repo / ".ddg/approvals/CHK-001.json").read_text(encoding="utf-8"))
            self.assertEqual(check, draft["check"])
            self.assertEqual(stored_validation, validation)
            self.assertEqual(approval, stored_approval)
            expected_bundle = digest({"check": check, "decision": draft["decision"],
                                      "adapter_version": draft["adapter_version"],
                                      "validation": stored_validation})
            self.assertEqual(stored_approval["bundle_digest"], expected_bundle)
            self.assertTrue(verify_bundle(check, draft["decision"], stored_validation, stored_approval))
            tampered = copy.deepcopy(stored_validation)
            tampered["cases"]["good"]["observation"]["unique_jobs"] = 2
            self.assertFalse(verify_bundle(check, draft["decision"], tampered, stored_approval))
            rehashed_approval = copy.deepcopy(stored_approval)
            rehashed_approval["validation_digest"] = digest(tampered)
            rehashed_approval["bundle_digest"] = bundle_digest(check, draft["decision"], draft["adapter_version"], tampered)
            self.assertFalse(verify_bundle(check, draft["decision"], tampered, rehashed_approval))

            malformed_calls = copy.deepcopy(stored_validation)
            malformed_calls["cases"]["good"]["observation"]["submit_calls"] = True
            malformed_approval = copy.deepcopy(stored_approval)
            malformed_approval["validation_digest"] = digest(malformed_calls)
            malformed_approval["bundle_digest"] = bundle_digest(check, draft["decision"], draft["adapter_version"], malformed_calls)
            self.assertFalse(verify_bundle(check, draft["decision"], malformed_calls, malformed_approval))

    def test_bundle_verifier_rejects_rehashed_invalid_provenance_or_truthy_eligibility(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            approval = approve(repo, draft, validation, "Dev", "Reviewed")

            def rebind(candidate):
                candidate["proposal"].pop("draft_digest", None)
                candidate["proposal"]["draft_digest"] = digest(candidate["proposal"])
                candidate["draft_digest"] = candidate["proposal"]["draft_digest"]
                changed = copy.deepcopy(approval)
                changed["validation_digest"] = digest(candidate)
                changed["bundle_digest"] = bundle_digest(draft["check"], draft["decision"],
                                                          draft["adapter_version"], candidate)
                return changed

            for mutate in (
                lambda item: item.update(source_sha="not-a-sha"),
                lambda item: item.update(input_digest="not-a-sha256"),
                lambda item: item.update(eligible=1),
                lambda item: item["proposal"].update(attempts=None),
            ):
                candidate = copy.deepcopy(validation)
                mutate(candidate)
                changed_approval = rebind(candidate)
                self.assertFalse(verify_bundle(draft["check"], draft["decision"], candidate, changed_approval))

    def test_bundle_verifier_rejects_float_schema_versions_after_rehash(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            approval = approve(repo, draft, validation, "Dev", "Reviewed")

            def rebind(candidate, decision):
                candidate["proposal"].pop("draft_digest", None)
                candidate["proposal"]["draft_digest"] = digest(candidate["proposal"])
                candidate["draft_digest"] = candidate["proposal"]["draft_digest"]
                candidate["decision_digest"] = digest(decision)
                updated_approval = copy.deepcopy(approval)
                updated_approval["validation_digest"] = digest(candidate)
                updated_approval["bundle_digest"] = bundle_digest(draft["check"], decision,
                                                                    draft["adapter_version"], candidate)
                return updated_approval

            changed_validation = copy.deepcopy(validation)
            changed_validation["schema_version"] = 1.0
            self.assertFalse(verify_bundle(draft["check"], draft["decision"], changed_validation,
                                           rebind(changed_validation, draft["decision"])))

            changed_decision = copy.deepcopy(draft["decision"])
            changed_decision["schema_version"] = 1.0
            decision_validation = copy.deepcopy(validation)
            decision_validation["proposal"]["decision"] = changed_decision
            self.assertFalse(verify_bundle(draft["check"], changed_decision, decision_validation,
                                           rebind(decision_validation, changed_decision)))

            changed_approval = copy.deepcopy(approval)
            changed_approval["schema_version"] = 1.0
            self.assertFalse(verify_bundle(draft["check"], draft["decision"], validation, changed_approval))

    def test_approval_records_never_copy_environment_credentials(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"GEMINI_API_KEY": "secret-never-persist"}):
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            approve(repo, draft, validation, "Dev", "Reviewed")
            records = "".join(path.read_text(encoding="utf-8") for path in (repo / ".ddg").rglob("*.json"))
            self.assertNotIn("secret-never-persist", records)

    def test_commit_demo_requires_generated_clean_repository(self):
        with TemporaryDirectory() as folder:
            repo = Path(folder) / "ordinary"
            repo.mkdir()
            subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
            (repo / "file.txt").write_text("not a demo", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "ordinary"], check=True)
            with self.assertRaises(ValueError):
                approve(repo, {"check": {"id": "CHK-001"}}, {"eligible": True}, "Dev", "Reviewed", commit_demo=True)
            self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())

    def test_review_branch_collision_is_rejected_before_any_bundle_write(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            subprocess.run(["git", "-C", str(repo), "branch", "regression", demo["refs"]["calibration_good"]], check=True)
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            with self.assertRaises(ValueError):
                approve(repo, draft, validation, "Dev", "Reviewed", commit_demo=True)
            self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())
            self.assertFalse((repo / ".ddg/validations/CHK-001.json").exists())
            self.assertFalse((repo / ".ddg/approvals/CHK-001.json").exists())
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, "")

    def test_dirty_marked_demo_is_rejected_without_ref_or_artifact_changes(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            validation = validate_draft(repo, draft, demo["refs"])
            dirty = repo / "operator-note.txt"
            dirty.write_text("preserve this dirty state", encoding="utf-8")
            before_refs = subprocess.run(["git", "-C", str(repo), "show-ref"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
            before_status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
            with self.assertRaises(ValueError):
                approve(repo, draft, validation, "Dev", "Reviewed", commit_demo=True)
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "show-ref"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, before_refs)
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, before_status)
            self.assertEqual(dirty.read_text(encoding="utf-8"), "preserve this dirty state")
            self.assertFalse((repo / ".ddg/checks/CHK-001.json").exists())

    def test_reapproval_of_activated_demo_is_rejected_without_git_mutation(self):
        with TemporaryDirectory() as folder:
            demo = make_approved_demo(Path(folder) / "repo")
            repo, draft, validation = Path(demo["repo"]), demo["draft"], demo["validation"]
            before_refs = subprocess.run(["git", "-C", str(repo), "show-ref"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
            before_status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
            with self.assertRaises(ValueError):
                approve(repo, draft, validation, "Another Developer", "Second approval", commit_demo=True)
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "show-ref"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, before_refs)
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, before_status)

    def test_commit_demo_creates_approved_and_review_refs_without_touching_calibration(self):
        with TemporaryDirectory() as folder:
            demo = make_approved_demo(Path(folder) / "repo")
            repo, refs = Path(demo["repo"]), demo["refs"]
            names = {"approved_base", "regression", "unseen_regression", "corrected", "exception", "unrelated", "abort", "review_abort", "review_crashing", "review_timing_out", "review_missing_entrypoint", "policy_edit", "preexisting_base", "preexisting_head", "resolved"}
            self.assertTrue(names.issubset(refs))
            approved_base = refs["approved_base"]
            for ref in names:
                self.assertEqual(len(refs[ref]), 40, ref)
            for name in ("calibration_bad", "calibration_good", "calibration_exception", "crashing", "timing_out", "missing_entrypoint"):
                self.assertEqual(refs[name], demo["approval"]["refs"][name])
            marker = json.loads((repo / ".ddg-demo.json").read_text(encoding="utf-8"))
            self.assertEqual(refs["calibration_abort"], demo["approval"]["refs"]["calibration_abort"])
            self.assertEqual(refs["abort"], refs["review_abort"])
            self.assertNotEqual(refs["abort"], refs["calibration_abort"])
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "rev-parse", "corrected"], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip(), refs["corrected"])
            for name in names - {"approved_base"}:
                subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", approved_base, refs[name]], check=True)
            self.assertEqual(marker["refs"], refs)
            bundle_paths = {".ddg/checks/CHK-001.json", ".ddg/validations/CHK-001.json", ".ddg/approvals/CHK-001.json"}
            committed = set(subprocess.run(["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-only", "-r", approved_base], capture_output=True, text=True, encoding="utf-8", check=True).stdout.splitlines())
            self.assertEqual(committed, bundle_paths)
            self.assertTrue((repo / ".ddg-demo.json").exists())
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", check=True).stdout, "")

    def test_commit_demo_supports_other_valid_check_ids(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            draft = make_manual_draft(repo, demo["refs"])
            draft["check"]["id"] = "CHK-002"
            draft = refingerprint(draft)
            validation = validate_draft(repo, draft, demo["refs"])
            approval = approve(repo, draft, validation, "Dev", "Reviewed", commit_demo=True)
            self.assertEqual(approval["check_id"], "CHK-002")
            self.assertTrue((repo / ".ddg/checks/CHK-002.json").is_file())
            self.assertTrue((repo / ".ddg/validations/CHK-002.json").is_file())
            self.assertTrue((repo / ".ddg/approvals/CHK-002.json").is_file())
            committed = subprocess.run(["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-only", "-r", approval["base_sha"]], capture_output=True, text=True, encoding="utf-8", check=True).stdout.splitlines()
            self.assertEqual(set(committed), {".ddg/checks/CHK-002.json", ".ddg/validations/CHK-002.json", ".ddg/approvals/CHK-002.json"})


if __name__ == "__main__":
    unittest.main()
