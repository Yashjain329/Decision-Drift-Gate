import copy
import json
import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from ddg.demo import build_demo
from ddg.proposal import input_digest, load_context, propose, validate_citations, wrap_draft
from ddg.proposal import _load_env_file
from ddg.gitio import resolve_commit
from ddg.contracts import digest, validate_check

ROOT = Path(__file__).resolve().parents[1]
MANUAL = json.loads((ROOT / "examples/manual_check.json").read_text(encoding="utf-8"))


class FakeInteractions:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text):
        self.interactions = FakeInteractions(output_text)


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="proposal space ")
        demo = build_demo(Path(self.temp.name) / "repo")
        self.repo = Path(demo["repo"])
        self.revision = demo["refs"]["decision_change"]
        self.context = load_context(self.repo, revision=self.revision)

    def tearDown(self):
        self.temp.cleanup()

    def test_content_digest_excludes_source_revision(self):
        changed_ref = {**self.context, "source_sha": "a" * 40}
        self.assertEqual(input_digest(changed_ref), input_digest(self.context))
        changed_input = {**self.context, "source": self.context["source"] + "\n# changed"}
        self.assertNotEqual(input_digest(changed_input), input_digest(self.context))

    def test_context_uses_pinned_decision_and_corrected_source_only(self):
        self.assertEqual(self.context["source_sha"], resolve_commit(self.repo, self.revision))
        self.assertEqual(self.context["new_decision"]["id"], "DEC-002")
        self.assertEqual(self.context["old_decision"]["id"], "DEC-001")
        self.assertIn("lookup", self.context["source"])
        self.assertEqual(self.context["adapter_version"], "python_job_client_v1")
        self.assertNotIn("holdout", json.dumps(self.context).lower())

    def test_manual_mode_requires_explicit_check_and_labels_provenance(self):
        draft = wrap_draft(self.context, MANUAL, mode="manual")
        self.assertEqual(draft["proposal_mode"], "manual")
        self.assertEqual(draft["check"], validate_check(MANUAL))
        self.assertEqual(draft["input_digest"], input_digest(self.context))
        self.assertEqual(draft["source_sha"], self.context["source_sha"])
        with self.assertRaises(ValueError):
            propose(self.context, "manual")

    def test_draft_fingerprint_binds_check_and_provenance(self):
        draft = wrap_draft(self.context, MANUAL, mode="manual")
        body = {key: value for key, value in draft.items() if key != "draft_digest"}
        self.assertEqual(draft["draft_digest"], digest(body))
        body["source_sha"] = "b" * 40
        self.assertNotEqual(draft["draft_digest"], digest(body))

    def test_live_structured_proposal_passes_local_schema_and_grounding(self):
        output = json.dumps({"status": "DRAFT", "check": MANUAL, "reason": "Supported."})
        client = FakeClient(output)
        with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
            draft = propose(self.context, "live", client=client)
        self.assertEqual(draft["proposal_mode"], "live")
        self.assertEqual(draft["model"], "gemini-3.8-flash")
        self.assertEqual(draft["check"], MANUAL)
        self.assertEqual(len(client.interactions.calls), 1)
        call = client.interactions.calls[0]
        self.assertEqual(call["response_format"]["mime_type"], "application/json")
        prompt = call["input"]
        self.assertIn(self.context["new_decision"]["rule"], prompt)
        self.assertNotIn("calibration_bad", prompt)
        self.assertNotIn("known-bad", prompt)
        self.assertEqual(draft["provider_response"]["status"], "DRAFT")
        self.assertEqual(draft["request_metadata"]["timeout_seconds"], 30)
        self.assertEqual(draft["request_metadata"]["input_digest"], input_digest(self.context))

    def test_bad_citation_from_model_is_rejected(self):
        check = copy.deepcopy(MANUAL)
        check["citations"][0]["quote"] = "invented claim absent from DEC-002"
        client = FakeClient(json.dumps({"status": "DRAFT", "check": check, "reason": ""}))
        with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
            with self.assertRaisesRegex(ValueError, "citation|quote"):
                propose(self.context, "live", client=client)

    def test_model_cannot_select_an_unprovided_active_decision(self):
        predecessor = {"schema_version": 1, "id": "DEC-004", "status": "superseded", "supersedes": None,
                       "scope": "src/job_client.py", "rule": "An unrelated older rule.", "exceptions": []}
        unrelated = {"schema_version": 1, "id": "DEC-003", "status": "active", "supersedes": "DEC-004",
                     "scope": "src/job_client.py", "rule": "A separate unrelated rule.", "exceptions": []}
        check = copy.deepcopy(MANUAL)
        check["decision_id"] = "DEC-003"
        check["supersedes"] = "DEC-004"
        check["citations"] = [{"decision_id": "DEC-003", "quote": "A separate unrelated rule."}]
        context = {**self.context, "decisions": {**self.context["decisions"], "DEC-004": predecessor, "DEC-003": unrelated}}
        client = FakeClient(json.dumps({"status": "DRAFT", "check": check, "reason": ""}))
        with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
            with self.assertRaisesRegex(ValueError, "Proposal failed"):
                propose(context, "live", client=client)

    def test_unsupported_malformed_and_missing_provider_configuration_fail_closed(self):
        client = FakeClient(json.dumps({"status": "UNSUPPORTED_DECISION", "check": None, "reason": "No measurable rule."}))
        with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
            with self.assertRaisesRegex(ValueError, "UNSUPPORTED_DECISION"):
                propose(self.context, "live", client=client)
            with self.assertRaises(ValueError):
                propose(self.context, "live", client=FakeClient("not json"))
        no_env_context = {**self.context, "env_file": str(Path(self.temp.name) / "missing.env")}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DDG_GEMINI_MODEL"):
                propose(no_env_context, "live", client=client)

    def test_provider_exception_is_sanitized(self):
        class Broken:
            class interactions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("request failed with secret-key=do-not-leak")
        with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
            with self.assertRaisesRegex(ValueError, "provider") as raised:
                propose(self.context, "live", client=Broken())
        self.assertNotIn("do-not-leak", str(raised.exception))

    def test_blocked_provider_call_returns_at_hard_deadline_without_accepting_late_result(self):
        started = threading.Event()
        release = threading.Event()

        class SlowInteractions:
            def create(self, **_kwargs):
                started.set()
                release.wait(0.15)
                return SimpleNamespace(output_text=json.dumps({"status": "DRAFT", "check": MANUAL, "reason": "late"}))

        client = SimpleNamespace(interactions=SlowInteractions())
        began = time.monotonic()
        try:
            with patch("ddg.proposal._PROVIDER_CALL_DEADLINE_SECONDS", 0.03, create=True):
                with patch.dict(os.environ, {"DDG_GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "fake-test-key"}):
                    with self.assertRaisesRegex(ValueError, "timed out"):
                        propose(self.context, "live", client=client)
            self.assertTrue(started.is_set())
            self.assertLess(time.monotonic() - began, 0.12)
        finally:
            release.set()

    def test_recorded_capture_requires_matching_content_inputs_and_provenance(self):
        capture = wrap_draft(self.context, MANUAL, mode="live", model="gemini-3.8-flash", sdk_version="test-sdk")
        capture["request_metadata"] = {"model": capture["model"], "input_digest": capture["input_digest"]}
        capture["provider_response"] = {"status": "DRAFT", "reason": "synthetic test capture"}
        body = {key: value for key, value in capture.items() if key != "draft_digest"}
        capture["draft_digest"] = digest(body)
        context = {**self.context, "capture": capture}
        mismatched = copy.deepcopy(capture)
        mismatched["input_digest"] = "wrong"
        mismatched["request_metadata"]["input_digest"] = "wrong"
        mismatched_body = {key: value for key, value in mismatched.items() if key != "draft_digest"}
        mismatched["draft_digest"] = digest(mismatched_body)
        context["capture"] = mismatched
        with self.assertRaisesRegex(ValueError, "input"):
            propose(context, "recorded")
        context["capture"] = capture
        draft = propose(context, "recorded")
        self.assertEqual(draft["proposal_mode"], "recorded")
        self.assertEqual(draft["model"], capture["model"])
        self.assertEqual(draft["captured_at"], capture["captured_at"])
        self.assertEqual(draft["provider_response"], capture["provider_response"])

        tampered = copy.deepcopy(capture)
        tampered["model"] = "changed-model"
        context["capture"] = tampered
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            propose(context, "recorded")

    def test_env_loader_only_imports_provider_variables_and_never_prints_values(self):
        env_file = Path(self.temp.name) / "provider.env"
        env_file.write_text("GEMINI_API_KEY=test-secret\nDDG_GEMINI_MODEL=local-model\nUNRELATED=ignored\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            _load_env_file(env_file)
            self.assertEqual(os.environ["GEMINI_API_KEY"], "test-secret")
            self.assertEqual(os.environ["DDG_GEMINI_MODEL"], "local-model")
            self.assertNotIn("UNRELATED", os.environ)

    def test_unknown_mode_and_ungrounded_decision_are_rejected(self):
        with self.assertRaises(ValueError):
            propose(self.context, "automatic")
        bad_check = copy.deepcopy(MANUAL)
        bad_check["supersedes"] = "DEC-999"
        with self.assertRaises(ValueError):
            validate_citations(bad_check, {"DEC-001": self.context["old_decision"], "DEC-002": self.context["new_decision"]})


if __name__ == "__main__":
    unittest.main()
