"""Git-layer edge cases: unreliable repository evidence must never produce PASSED_CHECKS."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import gitio, identity
from ddg.engine import compare
from ddg.gitio import resolve_commit
from tests import test_adapters as ta
from tests.test_identity import ART, GOOD, commit, git, policy

MALLORY = "mallory@example.com"
NOCRLF = ("-c", "core.autocrlf=false", "-c", "core.safecrlf=false")


def head_sha(repo):
    return resolve_commit(Path(repo), "HEAD")


def commit_bytes(repo, files, msg="c", email=GOOD):
    for rel, data in files.items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    git(repo, "add", "-A", extra=NOCRLF)
    git(repo, "commit", "--quiet", "-m", msg, email=email, extra=NOCRLF)
    return head_sha(repo)


def add_entry(repo, mode, path, target=b"target", sha=None, msg="entry"):
    """Commit a raw index entry (symlink 120000 / gitlink 160000) without needing OS symlink support."""
    if sha is None:
        sha = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=target,
                             check=True, capture_output=True).stdout.decode().strip()
    git(repo, "rm", "--quiet", "--cached", "--ignore-unmatch", "-r", path)
    subprocess.run(["git", "-C", str(repo), "update-index", "-z", "--index-info"], check=True, capture_output=True,
                   input=(mode + " " + sha + chr(9) + path + chr(0)).encode())
    git(repo, "commit", "--quiet", "-m", msg)
    return head_sha(repo)


class EdgeBase(ta.FunctionAdapterBase):
    def start(self, name, parent=None):
        git(self.repo, "clean", "--quiet", "-fd")
        git(self.repo, "checkout", "--quiet", "-f", "-B", name, parent or self.base)

    def assert_never_green(self, report, verdict=None):
        self.assertNotEqual(report["aggregate"], "PASSED_CHECKS")
        if verdict:
            self.assertEqual(report["checks"][0]["verdict"], verdict)


class ShallowTests(EdgeBase):
    def test_shallow_clone_history_and_engine_fail_closed(self):
        git(self.repo, "branch", "-f", "main", self.base)
        git(self.repo, "checkout", "--quiet", "main")
        with TemporaryDirectory() as tmp:
            clone = Path(tmp) / "shallow clone"
            subprocess.run(["git", "clone", "--quiet", "--depth", "1", self.repo.as_uri(), str(clone)],
                           check=True, capture_output=True)
            self.assertEqual(git(clone, "rev-parse", "--is-shallow-repository"), "true")
            with self.assertRaisesRegex(ValueError, "Shallow clone"):
                gitio.commits_touching(clone, self.base, ART[2])
            with self.assertRaisesRegex(identity.IdentityError, "Shallow clone"):
                identity.verify_approver(clone, self.base, "CHK-001")
            report = compare(clone, self.base, self.base)
            self.assert_never_green(report, "NOT_CHECKED")
            self.assertEqual(report["aggregate"], "INCOMPLETE")
            # The pre-clone history is not there, so older revisions cannot even be resolved.
            with self.assertRaises(ValueError):
                resolve_commit(clone, git(self.repo, "rev-parse", self.base + "~1"))


class RefTests(EdgeBase):
    def test_detached_head_resolves_and_compares(self):
        head = self.head("refactor", ta.REFACTORED)
        git(self.repo, "checkout", "--quiet", "--detach", head)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "")
        self.assertEqual(head_sha(self.repo), head)
        report = compare(self.repo, self.base, "HEAD")
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertEqual(report["head_sha"], head)

    def test_merge_commit_as_head(self):
        a = self.head("side-a", ta.REFACTORED)
        self.start("side-b")
        commit(self.repo, {"README.md": "docs\n"}, "docs")
        git(self.repo, "merge", "--quiet", "--no-ff", "-m", "merge", a)
        merge = head_sha(self.repo)
        self.assertEqual(len(git(self.repo, "rev-list", "--parents", "-n1", merge).split()), 3)
        self.assertIn("src/pricing.py", gitio.diff_at(self.repo, self.base, merge, "src/pricing.py"))
        self.assertEqual(sorted(gitio.changed_paths_at(self.repo, self.base, merge)), ["README.md", "src/pricing.py"])
        self.assertEqual(compare(self.repo, self.base, merge)["aggregate"], "PASSED_CHECKS")
        # A merge whose result reintroduces the regression is still caught.
        bad = self.head("bad", ta.BAD)
        self.start("side-c")
        commit(self.repo, {"README.md": "docs\n"}, "docs")
        git(self.repo, "merge", "--quiet", "--no-ff", "-m", "merge bad", bad)
        self.assertEqual(compare(self.repo, self.base, head_sha(self.repo))["aggregate"], "FAILED")


class SourceShapeTests(EdgeBase):
    def test_unusable_source_is_never_green(self):
        cases = {
            "empty": lambda: commit_bytes(self.repo, {"src/pricing.py": b""}),
            "binary": lambda: commit_bytes(self.repo, {"src/pricing.py": b"\x00\xff\xfe\x80\x00" * 50}),
            "non-utf8": lambda: commit_bytes(self.repo, {"src/pricing.py": b"# caf\xe9\n" + ta.GOOD_SRC.encode()}),
        }
        for name, build in cases.items():
            with self.subTest(name):
                self.start(name)
                head = build()
                self.assert_never_green(compare(self.repo, self.base, head), "NOT_CHECKED")
                self.assertIsInstance(gitio.diff_at(self.repo, self.base, head, "src/pricing.py"), str)

    def test_renamed_and_deleted_source_never_green(self):
        self.start("renamed")
        git(self.repo, "mv", "src/pricing.py", "src/pricing_new.py")
        git(self.repo, "commit", "--quiet", "-m", "rename")
        self.assert_never_green(compare(self.repo, self.base, head_sha(self.repo)), "NOT_CHECKED")
        self.start("deleted")
        git(self.repo, "rm", "--quiet", "src/pricing.py")
        git(self.repo, "commit", "--quiet", "-m", "delete")
        head = head_sha(self.repo)
        self.assertEqual(gitio.diff_at(self.repo, self.base, head, "src/pricing.py").count("deleted file"), 1)
        self.assert_never_green(compare(self.repo, self.base, head), "NOT_CHECKED")

    def test_crlf_source_is_preserved_and_still_checked(self):
        self.start("crlf")
        head = commit_bytes(self.repo, {"src/pricing.py": ta.REFACTORED.replace("\n", "\r\n").encode()})
        self.assertIn("\r\n", gitio.read_at(self.repo, head, "src/pricing.py"))
        self.assertEqual(compare(self.repo, self.base, head)["aggregate"], "PASSED_CHECKS")

    def test_crlf_json_is_readable_and_non_utf8_json_is_incomplete(self):
        self.start("crlf-json")
        raw = json.dumps({"a": 1}, indent=2).replace("\n", "\r\n").encode()
        base = commit_bytes(self.repo, {".ddg/decisions/DEC-009.json": raw})
        self.assertEqual(json.loads(gitio.read_at(self.repo, base, ".ddg/decisions/DEC-009.json")), {"a": 1})
        self.start("bad-json", base)
        base = commit_bytes(self.repo, {".ddg/decisions/DEC-009.json": b'{"a": "\xff\xfe"}'})
        with self.assertRaises(ValueError):
            gitio.read_at(self.repo, base, ".ddg/decisions/DEC-009.json")
        self.start("head-of-bad", base)
        head = commit_bytes(self.repo, {"src/pricing.py": ta.REFACTORED.encode()})
        self.assert_never_green(compare(self.repo, base, head))
        self.assertEqual(compare(self.repo, base, head)["aggregate"], "INCOMPLETE")


class LinkTests(EdgeBase):
    def test_symlink_and_submodule_are_never_read_or_listed(self):
        self.start("links")
        link = add_entry(self.repo, "120000", "src/alias.py", b"pricing.py")
        sub = add_entry(self.repo, "160000", "src/sub.py", sha="1" * 40)
        for sha, path in ((link, "src/alias.py"), (sub, "src/sub.py"), (sub, "src")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                gitio.read_at(self.repo, sha, path)
        with self.assertRaises(ValueError):
            gitio.list_at(self.repo, sub, "src")
        self.assertEqual(gitio.read_at(self.repo, sub, "src/pricing.py"), ta.GOOD_SRC)

    def test_link_in_ddg_tree_makes_authority_unavailable(self):
        for name, mode, sha in (("symlink", "120000", None), ("gitlink", "160000", "2" * 40)):
            with self.subTest(name):
                self.start(name)
                base = add_entry(self.repo, mode, ".ddg/checks/CHK-002.json", b"CHK-001.json", sha=sha)
                with self.assertRaises(ValueError):
                    gitio.list_at(self.repo, base, ".ddg/checks")
                self.start(name + "-head", base)
                head = commit_bytes(self.repo, {"src/pricing.py": ta.REFACTORED.encode()})
                report = compare(self.repo, base, head)
                self.assert_never_green(report)
                self.assertEqual(report["aggregate"], "INCOMPLETE")

    def test_symlinked_ddg_directory_is_rejected(self):
        self.start("ddg-link")
        git(self.repo, "rm", "-r", "--quiet", ".ddg")
        base = add_entry(self.repo, "120000", ".ddg", b"elsewhere")
        with self.assertRaises(ValueError):
            gitio.list_at(self.repo, base, ".ddg")
        with self.assertRaises(ValueError):
            gitio.read_at(self.repo, base, ".ddg/approvers.json")
        self.assertEqual(gitio.list_at(self.repo, base, ".ddg/checks"), [])

    def test_symlinked_source_in_head_is_not_checked(self):
        for name, mode, sha in (("symlink", "120000", None), ("gitlink", "160000", "3" * 40)):
            with self.subTest(name):
                self.start("src-" + name)
                head = add_entry(self.repo, mode, "src/pricing.py", b"../elsewhere.py", sha=sha)
                self.assert_never_green(compare(self.repo, self.base, head), "NOT_CHECKED")


class PathTests(EdgeBase):
    def test_spaces_unicode_and_dashes(self):
        self.start("paths")
        names = ["src/-dash name.py", "src/uni\u00e9\u4e2d.py", "src/sp ace.py"]
        head = commit_bytes(self.repo, {n: n.encode() for n in names})
        for n in names:
            with self.subTest(n):
                self.assertEqual(gitio.read_at(self.repo, head, n), n)
        self.assertEqual(set(gitio.list_at(self.repo, head, "src")), {"src/pricing.py", *names})
        for bad in ("-rf", "--output=x", "a/../b", "/abs", "C:/x", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gitio.read_at(self.repo, head, bad)


class HugeDiffTests(EdgeBase):
    def test_diff_is_capped_with_marker_and_engine_still_passes(self):
        self.start("huge")
        padding = "".join(f"# filler line {i:08d} ................................\n" for i in range(8000))
        head = commit_bytes(self.repo, {"src/pricing.py": (ta.REFACTORED + padding).encode()})
        text = gitio.diff_at(self.repo, self.base, head, "src/pricing.py")
        self.assertLessEqual(len(text.encode()), gitio.DIFF_CAP_BYTES + len(gitio.DIFF_TRUNCATION_MARKER))
        self.assertTrue(text.endswith(gitio.DIFF_TRUNCATION_MARKER))
        small = gitio.diff_at(self.repo, self.base, self.head("small", ta.REFACTORED), "src/pricing.py")
        self.assertNotIn("truncated", small)
        report = compare(self.repo, self.base, head)
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertTrue(report["checks"][0]["diff"].endswith(gitio.DIFF_TRUNCATION_MARKER))


class Sha256Tests(unittest.TestCase):
    def test_sha256_repository_fails_closed_with_explicit_message(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""}):
            repo = Path(tmp)
            git(repo, "init", "--quiet", "--object-format=sha256")
            for text, msg in ((ta.GOOD_SRC, "one"), (ta.REFACTORED, "two")):
                (repo / "src").mkdir(exist_ok=True)
                (repo / "src" / "pricing.py").write_text(text, encoding="utf-8")
                git(repo, "add", "-A")
                git(repo, "commit", "--quiet", "-m", msg)
            full = git(repo, "rev-parse", "HEAD")
            self.assertEqual(len(full), 64)
            with self.assertRaisesRegex(ValueError, "SHA-256 repositories are not supported"):
                resolve_commit(repo, "HEAD")
            for call in (lambda: gitio.read_at(repo, full, "src/pricing.py"),
                         lambda: gitio.list_at(repo, full, "src"),
                         lambda: gitio.diff_at(repo, full, full, "src/pricing.py"),
                         lambda: compare(repo, "HEAD~1", "HEAD")):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    call()


class HistoryRewriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "--quiet")
        env = patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        env.start()
        self.addCleanup(env.stop)
        self.policy = commit(self.repo, {".ddg/approvers.json": policy()}, "policy")
        self.other = commit(self.repo, {"README.md": "x\n"}, "unrelated")
        self.approval = commit(self.repo, {a: "{}\n" for a in ART}, "approve")

    def test_control_original_history_verifies(self):
        self.assertTrue(identity.verify_approver(self.repo, self.approval, "CHK-001")["verified"])

    def test_force_pushed_replacement_by_other_author_is_rejected(self):
        git(self.repo, "reset", "--quiet", "--hard", self.other)
        forced = commit(self.repo, {a: "{}\n" for a in ART}, "approve (replaced)", email=MALLORY)
        with self.assertRaisesRegex(identity.IdentityError, "not an allowed approver"):
            identity.verify_approver(self.repo, forced, "CHK-001")

    def test_rebase_that_changes_author_is_flagged(self):
        git(self.repo, "rebase", "--quiet", "--exec", "git commit --amend --no-edit --reset-author", self.policy,
            email=MALLORY)
        rebased = head_sha(self.repo)
        self.assertNotEqual(rebased, self.approval)
        with self.assertRaisesRegex(identity.IdentityError, "not an allowed approver"):
            identity.verify_approver(self.repo, rebased, "CHK-001")

    def test_side_branch_edit_hidden_by_ours_merge_is_still_seen(self):
        git(self.repo, "checkout", "--quiet", "-b", "side", self.approval)
        sneaky = commit(self.repo, {ART[2]: "{ }\n"}, "sneaky", email=MALLORY)
        git(self.repo, "checkout", "--quiet", "-")
        commit(self.repo, {"README.md": "y\n"}, "main moves")
        git(self.repo, "merge", "--quiet", "-s", "ours", "-m", "discard side", "side")
        merged = head_sha(self.repo)
        # Default history simplification hides the side branch; the identity lookup must not.
        self.assertNotIn(sneaky, git(self.repo, "log", "--format=%H", merged, "--", ART[2]).split())
        self.assertIn(sneaky, gitio.commits_touching(self.repo, merged, ART[2]))
        with self.assertRaisesRegex(identity.IdentityError, "not an allowed approver|mixes"):
            identity.verify_approver(self.repo, merged, "CHK-001")

    def test_unreadable_policy_is_not_treated_as_absent_even_in_unverified_mode(self):
        with patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": "1"}):
            for name, build in (("symlink", lambda: add_entry(self.repo, "120000", ".ddg/approvers.json", b"x")),
                                ("non-utf8", lambda: commit_bytes(self.repo, {".ddg/approvers.json": b"\xff\xfe{}"}))):
                with self.subTest(name):
                    with self.assertRaisesRegex(identity.IdentityError, "unreadable"):
                        identity.verify_approver(self.repo, build(), "CHK-001")

    def test_merge_commit_cannot_smuggle_other_paths(self):
        git(self.repo, "checkout", "--quiet", "-b", "side", self.policy)
        commit(self.repo, {"src/x.py": "x = 1\n"}, "side work")
        git(self.repo, "checkout", "--quiet", "-")
        git(self.repo, "merge", "--quiet", "--no-ff", "-m", "merge", "side")
        info = gitio.commit_identity(self.repo, head_sha(self.repo))
        self.assertIn("src/x.py", info["paths"])


class HostileConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.marks = tmp / "marks"
        self.marks.mkdir()
        script = tmp / "evil.py"
        script.write_text("import sys, pathlib\npathlib.Path(sys.argv[1], sys.argv[2]).write_text('ran')\n"
                          "print('')\n", encoding="utf-8")
        self.evil = lambda name: f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}" "{self.marks.as_posix()}" {name}'
        self.repo = tmp / "repo dir"
        self.repo.mkdir()
        git(self.repo, "init", "--quiet")
        commit(self.repo, {"src/pricing.py": "a = 1\n", ".gitattributes": "*.py diff=evil\n", ".ddg/x.json": "{}\n"}, "one")
        self.one = head_sha(self.repo)
        commit(self.repo, {"src/pricing.py": "a = 2\n"}, "two")
        self.two = head_sha(self.repo)
        for key, name in (("core.fsmonitor", "fsmonitor"), ("diff.external", "extdiff"), ("diff.evil.textconv", "textconv"),
                          ("gpg.program", "gpg"), ("gpg.ssh.program", "sshgpg"), ("core.pager", "pager")):
            git(self.repo, "config", "--local", key, self.evil(name))
        hooks = tmp / "hooks"
        hooks.mkdir()
        for hook in ("post-checkout", "reference-transaction", "post-index-change"):
            (hooks / hook).write_text(f"#!/bin/sh\n{self.evil('hook')}\n", encoding="utf-8")
        git(self.repo, "config", "--local", "core.hooksPath", hooks.as_posix())

    def ran(self):
        return sorted(p.name for p in self.marks.iterdir())

    def test_control_unhardened_git_would_execute_config(self):
        subprocess.run(["git", "-C", str(self.repo), "diff", self.one, self.two], capture_output=True)
        self.assertTrue({"extdiff", "textconv"} & set(self.ran()), "control: hostile config must be live")

    def test_gitio_never_executes_repository_config(self):
        repo = self.repo
        gitio.resolve_commit(repo, "HEAD")
        gitio.read_at(repo, self.two, "src/pricing.py")
        gitio.list_at(repo, self.two, ".ddg")
        self.assertIn("a = 2", gitio.diff_at(repo, self.one, self.two, "src/pricing.py"))
        self.assertEqual(gitio.changed_paths_at(repo, self.one, self.two), ["src/pricing.py"])
        gitio.commits_touching(repo, self.two, "src/pricing.py")
        gitio.commit_identity(repo, self.two)
        self.assertEqual(self.ran(), [])


if __name__ == "__main__":
    unittest.main()
