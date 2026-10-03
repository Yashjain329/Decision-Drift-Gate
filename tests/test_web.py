"""Offline HTTP boundary tests for the local browser server."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from ddg.demo import build_demo
from ddg.approval import approve, validate_draft
from ddg.contracts import digest
from ddg.proposal import load_context, propose
from ddg.web import create_server


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ddg web ")
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        build_demo(self.repo)
        self.state_dir = self.root / "state"
        self.server = create_server(self.repo, self.state_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, method, path, payload=None, *, token=None, headers=None):
        connection = HTTPConnection(self.host, self.port, timeout=15)
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"} if data is not None else {}
        if token is not None:
            request_headers["X-DDG-Session"] = token
        if headers:
            request_headers.update(headers)
        connection.request(method, path, body=data, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        status = response.status
        response_headers = dict(response.getheaders())
        connection.close()
        try:
            parsed = json.loads(raw) if "application/json" in response_headers.get("Content-Type", "") else raw
        except (ValueError, UnicodeError):
            parsed = raw
        return status, parsed, response_headers

    def state(self):
        status, body, headers = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        token = headers.get("X-DDG-Session")
        self.assertTrue(token)
        return body["state"], token

    def approve_and_run_regression(self):
        _initial, token = self.state()
        status, proposed, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        self.assertEqual(status, 200, proposed)
        draft = proposed["state"]["draft"]
        status, validated, _ = self.request("POST", "/api/validate", {"draft_digest": draft["draft_digest"]}, token=token)
        self.assertEqual(status, 200, validated)
        status, approved, _ = self.request("POST", "/api/approve", {
            "draft_digest": draft["draft_digest"], "reviewer": "Local reviewer", "reason": "Verify approval state",
        }, token=token)
        self.assertEqual(status, 200, approved)
        status, result, _ = self.request("POST", "/api/run", {"scenario": "regression"}, token=token)
        self.assertEqual(status, 200, result)
        return result["state"], token

    def test_html_injects_escaped_per_server_session_token_and_serves_only_named_assets(self):
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'ddg-session-token', body)
        self.assertNotIn(b"__DDG_SESSION_TOKEN__", body)
        token = headers.get("X-DDG-Session")
        self.assertIsNotNone(token)
        self.assertEqual(self.request("GET", "/../.env")[0], 404)
        self.assertEqual(self.request("GET", "/not-an-asset")[0], 404)

    def test_missing_token_external_origin_and_external_host_are_rejected(self):
        for _ in range(3):
            self.assertEqual(self.request("POST", "/api/validate", {"draft_digest": "x"})[0], 403)
        _, token = self.state()
        self.assertEqual(self.request("POST", "/api/validate", {"draft_digest": "x"}, token=token,
                                       headers={"Origin": "https://attacker.invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "attacker.invalid"})[0], 403)

    def test_state_directory_inside_governed_records_is_rejected_before_writes(self):
        target = self.repo / ".ddg" / "sessions" / "unsafe"
        with self.assertRaisesRegex(ValueError, "outside repository .ddg"):
            create_server(self.repo, target, port=0)
        self.assertFalse(target.exists())

    def test_body_size_content_type_and_unknown_scenario_fail_at_boundary(self):
        _, token = self.state()
        conn = HTTPConnection(self.host, self.port, timeout=5)
        conn.request("POST", "/api/run", body=b"x" * (64 * 1024 + 1),
                     headers={"Content-Length": str(64 * 1024 + 1), "Content-Type": "application/json",
                              "X-DDG-Session": token})
        response = conn.getresponse()
        self.assertEqual(response.status, 413)
        response.read()
        conn.close()
        status, _, _ = self.request("POST", "/api/run", {"scenario": "arbitrary-command"}, token=token)
        self.assertEqual(status, 400)
        status, _, _ = self.request("POST", "/api/run", {"scenario": []}, token=token)
        self.assertEqual(status, 400)
        connection = HTTPConnection(self.host, self.port, timeout=5)
        connection.request("POST", "/api/propose", body=b"{}", headers={"Content-Type": "text/plain",
                                                                            "X-DDG-Session": token})
        response = connection.getresponse()
        self.assertEqual(response.status, 415)
        response.read()
        connection.close()

    def test_premature_approval_stale_digest_and_busy_lock_are_conflicts(self):
        _, token = self.state()
        status, _, _ = self.request("POST", "/api/approve", {"draft_digest": "x", "reviewer": "R", "reason": "ok"}, token=token)
        self.assertEqual(status, 409)
        status, body, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        self.assertEqual(status, 200, body)
        self.assertFalse(body["state"]["busy"])
        draft_digest = body["state"]["draft"]["draft_digest"]
        status, _, _ = self.request("POST", "/api/validate", {"draft_digest": "stale"}, token=token)
        self.assertEqual(status, 409)
        self.server.mutation_lock.acquire()
        try:
            status, _, _ = self.request("POST", "/api/validate", {"draft_digest": draft_digest}, token=token)
            self.assertEqual(status, 409)
        finally:
            self.server.mutation_lock.release()

    def test_recorded_lifecycle_persists_without_session_token_and_run_reports_failure(self):
        state, token = self.state()
        self.assertEqual(state["mode"], "recorded")
        status, result, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        self.assertEqual(status, 200, result)
        draft = result["state"]["draft"]
        status, result, _ = self.request("POST", "/api/validate", {"draft_digest": draft["draft_digest"]}, token=token)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["state"]["validation"]["eligible"])
        status, result, _ = self.request("POST", "/api/approve", {
            "draft_digest": draft["draft_digest"], "reviewer": "Local reviewer", "reason": "Test the demo flow",
        }, token=token)
        self.assertEqual(status, 200, result)
        self.assertIsNotNone(result["state"]["approval"])
        status, result, _ = self.request("POST", "/api/run", {"scenario": "regression"}, token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["state"]["report"]["aggregate"], "FAILED")
        saved = (self.state_dir / "session.json").read_text(encoding="utf-8")
        self.assertNotIn("GEMINI_API_KEY", saved)
        self.assertNotIn("__DDG_SESSION", saved)

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.server = create_server(self.repo, self.state_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        restored, new_token = self.state()
        self.assertNotEqual(token, new_token)
        self.assertIsNotNone(restored["approval"])
        self.assertEqual(restored["report"]["aggregate"], "FAILED")

        saved_path = self.state_dir / "session.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        saved["state"]["draft"]["check"]["rationale"] = "tampered after approval"
        saved_path.write_text(json.dumps(saved), encoding="utf-8")
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.server = create_server(self.repo, self.state_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        recovered, _ = self.state()
        self.assertEqual(recovered["lifecycle"], "approved")
        self.assertEqual(recovered["draft"], recovered["validation"]["proposal"])
        self.assertIsNone(recovered["report"])

    def test_failed_state_write_does_not_publish_candidate_session_state(self):
        original, token = self.state()
        with patch("ddg.web._persist", side_effect=RuntimeError("disk unavailable")):
            status, body, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        self.assertEqual(status, 500, body)
        refreshed, _ = self.state()
        self.assertEqual(refreshed["lifecycle"], original["lifecycle"])
        self.assertIsNone(refreshed["draft"])

    def test_approved_demo_rejects_propose_and_validate_without_changing_report_state(self):
        before, token = self.approve_and_run_regression()
        digest = before["draft"]["draft_digest"]
        validation_status, _, _ = self.request("POST", "/api/validate", {"draft_digest": digest}, token=token)
        propose_status, _, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        after, _ = self.state()
        self.assertEqual(validation_status, 409)
        self.assertEqual(propose_status, 409)
        self.assertEqual(after, before)

    def test_activated_demo_restores_verified_approval_when_saved_state_hides_it(self):
        before, _token = self.approve_and_run_regression()
        saved_path = self.state_dir / "session.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        saved["state"]["approval"] = None
        saved_path.write_text(json.dumps(saved), encoding="utf-8")

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.server = create_server(self.repo, self.state_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        recovered, _ = self.state()
        self.assertIsNotNone(recovered["approval"])
        self.assertEqual(recovered["draft"], recovered["validation"]["proposal"])
        self.assertEqual(recovered["approval"], before["approval"])

    def test_report_staleness_tracks_live_ref_names(self):
        _, token = self.state()
        # A comparison records the current refs; moving regression makes the report stale.
        status, proposed, _ = self.request("POST", "/api/propose", {"mode": "recorded"}, token=token)
        self.assertEqual(status, 200, proposed)
        draft = proposed["state"]["draft"]
        self.request("POST", "/api/validate", {"draft_digest": draft["draft_digest"]}, token=token)
        status, approved, _ = self.request("POST", "/api/approve", {
            "draft_digest": draft["draft_digest"], "reviewer": "Reviewer", "reason": "Test stale reporting",
        }, token=token)
        self.assertEqual(status, 200, approved)
        status, run, _ = self.request("POST", "/api/run", {"scenario": "regression"}, token=token)
        self.assertEqual(status, 200, run)
        self.assertFalse(run["state"]["report_stale"])
        # Mutate a fixture ref without changing the report; status is checked on every state read.
        import subprocess
        subprocess.run(["git", "-C", str(self.repo), "branch", "-f", "regression", "approved-base"], check=True)
        refreshed, _ = self.state()
        self.assertTrue(refreshed["report_stale"])

    def test_unpersisted_server_bootstraps_a_verified_nondefault_check_id(self):
        repo = self.root / "generic-check-repo"
        demo = build_demo(repo)
        marker = json.loads((repo / ".ddg-demo.json").read_text(encoding="utf-8"))
        context = load_context(repo, revision=marker["refs"]["decision_change"])
        project = Path(__file__).resolve().parents[1]
        context["capture"] = json.loads((project / "evidence" / "gemini-proposal.json").read_text(encoding="utf-8"))
        draft = propose(context, mode="recorded")
        draft["check"]["id"] = "CHK-002"
        draft.pop("draft_digest")
        draft["draft_digest"] = digest(draft)
        validation = validate_draft(repo, draft, demo["refs"])
        approve(repo, draft, validation, "Bootstrap reviewer", "Verify generic check id", commit_demo=True)

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.repo = repo
        state_dir = self.root / "generic-state"
        self.server = create_server(repo, state_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        state, _ = self.state()
        self.assertEqual(state["draft"]["check"]["id"], "CHK-002")
        self.assertEqual(state["approval"]["check_id"], "CHK-002")
        self.assertEqual(state["lifecycle"], "approved")


if __name__ == "__main__":
    unittest.main()
