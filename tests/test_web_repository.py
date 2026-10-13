"""`ddg serve` on a real repository (no demo marker): read-only view of the approved bundle and a saved report."""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ddg.demo import build_demo
from ddg.engine import compare
from ddg.web import create_server
from tests.test_adapters import BAD, FunctionAdapterBase
from tests.test_identity import commit, git
from tests import test_web


class RepositoryModeTests(unittest.TestCase):
    request = test_web.WebServerTests.request
    state = test_web.WebServerTests.state

    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {"DDG_SANDBOX": "host", "DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        cls.env.start()
        cls.temp = tempfile.TemporaryDirectory(prefix="ddg web repo ")
        root = Path(cls.temp.name)
        cls.repo, cls.base, _validation = FunctionAdapterBase.build(root)
        git(cls.repo, "checkout", "--quiet", "-B", "regression", cls.base)
        cls.head = commit(cls.repo, {"src/pricing.py": BAD}, "drop the negative-price guard")
        git(cls.repo, "checkout", "--quiet", "--detach", cls.base)
        cls.report = compare(cls.repo, cls.base, cls.head)
        cls.state_dir = root / "state"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        cls.env.stop()

    def serve(self, repo=None, **kwargs):
        self.server = create_server(repo or self.repo, self.state_dir, port=0, **kwargs)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.host, self.port = self.server.server_address[:2]

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=3)
        self.addCleanup(stop)

    def test_shows_approved_bundle_and_saved_report(self):
        self.assertEqual(self.report["aggregate"], "FAILED")
        self.serve(base=self.base, report=self.report)
        state, _token = self.state()
        self.assertEqual(state["source"], {"kind": "repository", "repo": self.repo.name, "base_sha": self.base})
        self.assertEqual(state["lifecycle"], "reviewed")
        self.assertEqual(state["new_decision"]["id"], "DEC-002")
        self.assertEqual(state["old_decision"]["id"], "DEC-001")
        self.assertTrue(state["validation"]["eligible"])
        self.assertIsNotNone(state["approval"])
        self.assertEqual(state["report"]["aggregate"], "FAILED")
        self.assertEqual(state["report"]["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        self.assertFalse(state["report_stale"])
        self.assertEqual(state["scenarios"], [])

    def test_every_action_is_refused_and_nothing_changes(self):
        self.serve(report=self.report)
        before, token = self.state()
        for route, body in (("/api/propose", {"mode": "recorded"}), ("/api/validate", {"draft_digest": "x"}),
                            ("/api/approve", {"draft_digest": "x", "reviewer": "a", "reason": "b"}),
                            ("/api/run", {"scenario": "regression"})):
            status, response, _ = self.request("POST", route, body, token=token)
            self.assertEqual(status, 403, route)
            self.assertIn("read-only", response["error"])
        status, _response, _ = self.request("POST", "/api/run", {"scenario": "regression"}, token="forged")
        self.assertEqual(status, 403)
        after, _ = self.state()
        self.assertEqual(before, after)
        self.assertFalse((self.state_dir / "session.json").exists())

    def test_without_report_and_default_base_head(self):
        git(self.repo, "checkout", "--quiet", "--detach", self.base)
        self.serve()
        state, _ = self.state()
        self.assertEqual(state["lifecycle"], "approved")
        self.assertIsNone(state["report"])
        self.assertEqual(state["source"]["base_sha"], self.base)

    def test_report_for_commits_missing_here_is_stale(self):
        foreign = dict(self.report, base_sha="1" * 40, head_sha="2" * 40)
        self.serve(report=foreign)
        state, _ = self.state()
        self.assertTrue(state["report_stale"])

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            create_server(self.repo, self.state_dir, port=0, report={"aggregate": "FAILED"})
        with self.assertRaises(ValueError):
            create_server(self.repo, self.state_dir, port=0, report=dict(self.report, base_sha="short"))
        with self.assertRaises(ValueError):
            create_server(self.repo, self.state_dir, port=0, base="no-such-ref")

    def test_repository_without_ddg_records_is_empty_not_broken(self):
        plain = Path(self.temp.name) / "plain"
        plain.mkdir()
        git(plain, "init", "--quiet")
        commit(plain, {"README.md": "hello\n"}, "initial")
        self.serve(repo=plain)
        state, _ = self.state()
        self.assertEqual(state["lifecycle"], "decision_changed")
        self.assertIsNone(state["approval"])
        self.assertIsNone(state["new_decision"])

    def test_demo_marker_keeps_interactive_mode_and_rejects_repository_flags(self):
        demo = Path(self.temp.name) / "demo"
        build_demo(demo)
        with self.assertRaises(ValueError):
            create_server(demo, self.state_dir, port=0, base="HEAD")
        self.serve(repo=demo)
        state, _ = self.state()
        self.assertEqual(state["source"]["kind"], "demo")


if __name__ == "__main__":
    unittest.main()
