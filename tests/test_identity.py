import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import identity
from ddg.gitio import resolve_commit

ART = [".ddg/checks/CHK-001.json", ".ddg/validations/CHK-001.json", ".ddg/approvals/CHK-001.json"]
GOOD = "alice@example.com"


def git(repo, *args, email=GOOD, extra=()):
    env = dict(os.environ, GIT_AUTHOR_NAME="x", GIT_COMMITTER_NAME="x",
               GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_EMAIL=email)
    return subprocess.run(["git", "-C", str(repo), *extra, *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", env=env).stdout.strip()


def write(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def commit(repo, files, msg="c", email=GOOD, extra=()):
    for rel, text in files.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", msg, email=email, extra=extra)
    return resolve_commit(Path(repo), "HEAD")


def policy(require_signed=False, approvers=(GOOD,)):
    return json.dumps({"schema_version": 1, "require_signed": require_signed, "approvers": list(approvers)})


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "--quiet")
        env = patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._tmp.cleanup)

    def approved(self, **kw):
        commit(self.repo, {".ddg/approvers.json": policy(**kw)}, "policy")
        return commit(self.repo, {a: "{}\n" for a in ART}, "approve")

    def test_allowed_author_is_verified(self):
        base = self.approved()
        result = identity.verify_approver(self.repo, base, "CHK-001")
        self.assertTrue(result["verified"])
        self.assertEqual(result["commits"][0]["author_email"], GOOD)

    def test_author_comparison_ignores_case(self):
        commit(self.repo, {".ddg/approvers.json": policy()}, "policy")
        base = commit(self.repo, {a: "{}\n" for a in ART}, "approve", email="ALICE@Example.com")
        self.assertTrue(identity.verify_approver(self.repo, base, "CHK-001")["verified"])

    def test_non_approver_author_is_rejected(self):
        commit(self.repo, {".ddg/approvers.json": policy()}, "policy")
        base = commit(self.repo, {a: "{}\n" for a in ART}, "approve", email="mallory@example.com")
        with self.assertRaisesRegex(identity.IdentityError, "not an allowed approver"):
            identity.verify_approver(self.repo, base, "CHK-001")

    def test_later_edit_by_non_approver_invalidates_bundle(self):
        self.approved()
        base = commit(self.repo, {ART[2]: "{ }\n"}, "sneaky whitespace edit", email="mallory@example.com")
        with self.assertRaisesRegex(identity.IdentityError, "not an allowed approver"):
            identity.verify_approver(self.repo, base, "CHK-001")

    def test_approval_commit_must_not_mix_other_paths(self):
        commit(self.repo, {".ddg/approvers.json": policy()}, "policy")
        base = commit(self.repo, {**{a: "{}\n" for a in ART}, "src/job_client.py": "x = 1\n"}, "approve + code")
        with self.assertRaisesRegex(identity.IdentityError, "mixes"):
            identity.verify_approver(self.repo, base, "CHK-001")

    def test_missing_policy_fails_closed_unless_explicitly_allowed(self):
        base = commit(self.repo, {a: "{}\n" for a in ART}, "approve")
        with self.assertRaisesRegex(identity.IdentityError, "No .ddg/approvers.json"):
            identity.verify_approver(self.repo, base, "CHK-001")
        with patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": "1"}):
            self.assertFalse(identity.verify_approver(self.repo, base, "CHK-001")["verified"])

    def test_malformed_policy_is_rejected(self):
        for n, bad in enumerate(("not json", "[]", json.dumps({"schema_version": 1, "require_signed": "yes", "approvers": [GOOD]}),
                    json.dumps({"schema_version": 1, "require_signed": False, "approvers": []}),
                    json.dumps({"schema_version": 1, "require_signed": False, "approvers": ["nobody"]}))):
            with self.subTest(bad=bad):
                commit(self.repo, {".ddg/approvers.json": bad}, "policy")
                base = commit(self.repo, {a: "{" + str(n) + "}\n" for a in ART}, "approve")
                with self.assertRaises(identity.IdentityError):
                    identity.verify_approver(self.repo, base, "CHK-001")

    def test_unsigned_commit_rejected_when_signatures_required(self):
        base = self.approved(require_signed=True)
        with self.assertRaisesRegex(identity.IdentityError, "good signature"):
            identity.verify_approver(self.repo, base, "CHK-001")

    def test_missing_history_is_rejected(self):
        commit(self.repo, {".ddg/approvers.json": policy()}, "policy")
        with self.assertRaisesRegex(identity.IdentityError, "No commit history"):
            identity.verify_approver(self.repo, resolve_commit(self.repo, "HEAD"), "CHK-001")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen unavailable")
class SignedCommitTests(unittest.TestCase):
    def test_good_ssh_signature_satisfies_require_signed_and_wrong_key_does_not(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""}):
            tmp = Path(tmp)
            repo = tmp / "r"
            repo.mkdir()
            git(repo, "init", "--quiet")
            keys = {}
            for name in ("good", "other"):
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp / name)],
                               check=True, capture_output=True)
                keys[name] = (tmp / f"{name}.pub").read_text().split()[:2]
            (tmp / "allowed").write_text(f"{GOOD} {keys['good'][0]} {keys['good'][1]}\n")
            cfg = ("-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={(tmp / 'allowed').as_posix()}",
                   "-c", "commit.gpgsign=true")
            def signed(files, msg, key):
                return commit(repo, files, msg, extra=(*cfg, "-c", f"user.signingkey={(tmp / key).as_posix()}"))
            signed({".ddg/approvers.json": policy(require_signed=True)}, "policy", "good")
            base = signed({a: "{}\n" for a in ART}, "approve", "good")
            with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "gpg.format",
                                         "GIT_CONFIG_VALUE_0": "ssh", "GIT_CONFIG_KEY_1": "gpg.ssh.allowedSignersFile",
                                         "GIT_CONFIG_VALUE_1": (tmp / "allowed").as_posix()}):
                self.assertTrue(identity.verify_approver(repo, base, "CHK-001")["verified"])
                forged = signed({ART[2]: "{ }\n"}, "signed by a key not in allowed signers", "other")
                with self.assertRaisesRegex(identity.IdentityError, "good signature"):
                    identity.verify_approver(repo, forged, "CHK-001")


class EngineIntegrationTests(unittest.TestCase):
    def test_engine_reports_verified_approver_and_fails_closed_without_policy(self):
        from ddg.engine import compare
        from tests.support import commit_fixture, make_approved_demo
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""}):
            demo = make_approved_demo(Path(tmp) / "repo")
            repo, refs = Path(demo["repo"]), demo["refs"]
            ok = compare(repo, refs["approved_base"], refs["corrected"])
            self.assertEqual(ok["aggregate"], "PASSED_CHECKS")
            self.assertTrue(ok["checks"][0]["approver"]["verified"])
            no_policy = commit_fixture(repo, refs["approved_base"], {".ddg/approvers.json": None}, "drop policy")
            bad = compare(repo, no_policy, refs["regression"])
            self.assertEqual(bad["aggregate"], "INCOMPLETE")
            self.assertIn("APPROVER_NOT_VERIFIED", {w["code"] for w in bad["warnings"]})
            self.assertEqual(bad["checks"][0]["verdict"], "NOT_CHECKED")


if __name__ == "__main__":
    unittest.main()
