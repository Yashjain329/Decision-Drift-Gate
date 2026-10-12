"""Mutation-style negative suite: every tampering of base authority must stop the gate going green.

Method: start from a fully approved repo, change ONE thing in the BASE commit's authority
(walking every JSON node of every ``.ddg`` file), and assert ``engine.compare`` answers
``INCOMPLETE``.  Three attacker models are replayed over the same mutants:

* raw edit by an allowed approver      -> digests/semantics must catch it
* digest-resealed edit by a stranger   -> approver identity must catch it
* digest-resealed edit by an approver  -> only fields documented as informational may survive

Documented decisions (see the tests that pin them):

* ``validation.cases.*.observation.events`` (recorded trace detail, only status/counts are judged) may be
  edited by a digest-resealing approver; strangers are still stopped by approver identity.
* ``approval.reviewer`` / ``approval.reason`` / ``approval.approved_at`` are free text that no digest
  binds; the authority is the Git author of the approval commit, so editing them is accepted.
* Timestamps in the future are accepted (clock skew must not make a valid bundle unverifiable);
  malformed or timezone-less timestamps are rejected.
* Adding a further approver to ``approvers.json`` keeps existing bundles valid; every other edit does not.
* Authority is always pinned to base: the same edits made only at HEAD yield
  ``POLICY_REVIEW_REQUIRED`` + ``INCOMPLETE`` while the base check still runs.
"""

import copy
import json
import os
import subprocess
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg.approval import _provenance_valid, approve, bundle_digest, validate_draft
from ddg.contracts import digest
from ddg.engine import compare
from ddg.gitio import list_at, read_at, resolve_commit
from ddg.proposal import load_context, wrap_draft
from ddg.report import is_stale
from tests.support import make_approved_demo
from tests.test_adapters import BAD, CHECK, DEC1, DEC2, GOOD_SRC, REFACTORED, FunctionAdapterBase, js
from tests.test_identity import GOOD, commit, git, policy

MALLORY = "mallory@example.com"
DEMO_APPROVER = "ddg-demo@example.invalid"
# In docker mode every surviving mutant runs in a container, so replay only a sample.
SAMPLE = 7 if os.environ.get("DDG_SANDBOX") == "docker" else 1


def informational(path, node, resealed):
    """Fields no verifier binds semantically: free text and recorded-but-unjudged evidence detail."""
    kind = kind_of(path)
    if kind == "approval" and node[:1] in (("reviewer",), ("reason",)):
        return True
    # Calibration observation traces are digest-bound but not judged (only status/counts are).
    return bool(resealed) and kind == "validation" and node[:1] == ("cases",) and node[2:3] == ("observation",) and node[3:4] in (("events",), ("results",))


# ---------------------------------------------------------------- git / json plumbing
def fast_commits(repo, parent, specs, email):
    """One commit per spec ({path: text|None}) on top of ``parent``, via a single fast-import."""
    ident = f"DDG Test <{email}> 1700000000 +0000".encode()
    ns = f"refs/ddg-tamper/{uuid.uuid4().hex}"
    out = bytearray()
    for index, files in enumerate(specs):
        out += f"commit {ns}/{index}\n".encode() + b"author " + ident + b"\ncommitter " + ident
        out += b"\ndata 8\nmutation\nfrom " + parent.encode() + b"\n"
        for path, text in files.items():
            if text is None:
                out += f"D {path}\n".encode()
            else:
                data = text.encode("utf-8")
                out += f"M 100644 inline {path}\ndata {len(data)}\n".encode() + data + b"\n"
        out += b"\n"
    subprocess.run(["git", "-C", str(repo), "fast-import", "--quiet"], input=bytes(out), check=True,
                   capture_output=True)
    listing = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", ns + "/")
    by_ref = dict(line.split() for line in listing.splitlines())
    return [by_ref[f"{ns}/{index}"] for index in range(len(specs))]


def kind_of(path):
    for folder, kind in ((".ddg/checks/", "check"), (".ddg/validations/", "validation"),
                         (".ddg/approvals/", "approval"), (".ddg/decisions/", "decision")):
        if path.startswith(folder):
            return kind
    return "approvers"


def nodes(obj, path=()):
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from nodes(value, path + (key,))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from nodes(value, path + (index,))


def _walk(doc, path):
    for step in path[:-1]:
        doc = doc[step]
    return doc


def mutants(doc):
    """Yield (path, op, mutated deep copy): one edit per JSON node, deletion, extra key and type swap."""
    for path, value in nodes(doc):
        edits = []
        if isinstance(value, dict):
            edits.append(("extra_key", lambda parent, key: parent[key].update(zz_extra=1)))
        elif isinstance(value, list):
            edits.append(("append", lambda parent, key: parent[key].append("zz_extra")))
        elif isinstance(value, bool):
            edits.append(("flip", lambda parent, key: parent.__setitem__(key, not parent[key])))
        elif isinstance(value, (int, float)):
            edits.append(("plus_one", lambda parent, key: parent.__setitem__(key, parent[key] + 1)))
        elif isinstance(value, str):
            edits.append(("suffix", lambda parent, key: parent.__setitem__(key, parent[key] + "x")))
            edits.append(("empty", lambda parent, key: parent.__setitem__(key, "")))
        else:
            edits.append(("from_null", lambda parent, key: parent.__setitem__(key, "zz")))
        if path:
            if value is not None:
                edits.append(("null", lambda parent, key: parent.__setitem__(key, None)))
            if not isinstance(value, (dict, list)):
                edits.append(("wrap", lambda parent, key: parent.__setitem__(key, [parent[key]])))
            edits.append(("delete", lambda parent, key: parent.pop(key)))
        for op, apply in edits:
            clone = copy.deepcopy(doc)
            if path:
                apply(_walk(clone, path), path[-1])
            else:
                apply({"": clone}, "")
            yield path, op, clone


def load_docs(repo, sha):
    return {path: json.loads(read_at(repo, sha, path)) for path in list_at(repo, sha, ".ddg")}


def reseal(docs):
    """Recompute approval digests so a tampered bundle looks internally consistent."""
    for path, approval in docs.items():
        if kind_of(path) != "approval":
            continue
        try:
            cid = approval["check_id"]
            check = docs[f".ddg/checks/{cid}.json"]
            validation = docs[f".ddg/validations/{cid}.json"]
            decision = docs[f".ddg/decisions/{check['decision_id']}.json"]
            approval["validation_digest"] = digest(validation)
            approval["bundle_digest"] = bundle_digest(check, decision, check["adapter"], validation)
            approval["calibration_hashes"] = validation["calibration_hashes"]
        except (KeyError, TypeError):
            pass
    return docs


def text_of(value):
    return js(value)


# ---------------------------------------------------------------- shared assertions
class TamperMixin:
    """Needs: repo, base, approver, benign_head_files, source_path."""

    sample = SAMPLE

    def verdict(self, base, head):
        return compare(self.repo, base, head)

    def replay(self, mode, approver_email, resealed):
        docs = load_docs(self.repo, self.base)
        labels, specs, thin = [], [], 0
        for path in sorted(docs):
            for node, op, mutated in mutants(docs[path]):
                if resealed and op in {"empty", "null", "wrap"}:
                    continue  # raw walk covers these; keeps the resealed replays affordable
                if kind_of(path) == "validation":  # every other validation mutant; all other files are walked fully
                    thin += 1
                    if thin % 2:
                        continue
                labels.append((path, node, op))
                full = copy.deepcopy(docs)
                full[path] = mutated
                if resealed and kind_of(path) != "approval":
                    reseal(full)
                specs.append({path: text_of(full[path])} | (
                    {p: text_of(full[p]) for p in full if kind_of(p) == "approval" and full[p] != docs[p]}))
        shas = fast_commits(self.repo, self.base, specs, approver_email)
        failures, survivors = [], []
        picked = [(label, sha) for index, (label, sha) in enumerate(zip(labels, shas)) if index % self.sample == 0]
        with ThreadPoolExecutor(8) as pool:  # compare() is thread-safe (see the concurrency test)
            aggregates = list(pool.map(lambda item: self.verdict(item[1], item[1])["aggregate"], picked))
        for (label, _), aggregate in zip(picked, aggregates):
            path, node, op = label
            if aggregate == "PASSED_CHECKS" and informational(path, node, resealed):
                survivors.append(label)
            elif aggregate != "INCOMPLETE":
                failures.append((label, aggregate))
        self.assertEqual(sorted(map(repr, failures)), [], f"{mode}: tampering silently accepted")
        return survivors

    # -- mutation walks -------------------------------------------------------------
    def test_control_unmutated_base_passes(self):
        self.assertEqual(self.verdict(self.base, self.base)["aggregate"], "PASSED_CHECKS")

    def test_raw_edits_by_an_approver_never_pass(self):
        survivors = self.replay("raw", self.approver, resealed=False)
        # reviewer/reason are unbound free text (Git author is the authority); nothing else may survive.
        self.assertTrue(all(kind_of(path) == "approval" for path, _, _ in survivors), survivors)

    def test_resealed_edits_by_a_stranger_never_pass(self):
        self.assertEqual(self.replay("resealed/stranger", MALLORY, resealed=True), [])

    def test_resealed_edits_by_an_approver_only_touch_informational_fields(self):
        survivors = self.replay("resealed/approver", self.approver, resealed=True)
        self.assertTrue(all(informational(p, n, True) for p, n, _ in survivors), survivors)

    # -- artifacts and approvers ------------------------------------------------------
    def test_deleting_any_authority_file_is_incomplete(self):
        paths = sorted(load_docs(self.repo, self.base))
        shas = fast_commits(self.repo, self.base, [{p: None} for p in paths], self.approver)
        for path, sha in zip(paths, shas):
            with self.subTest(path):
                self.assertEqual(self.verdict(sha, sha)["aggregate"], "INCOMPLETE")

    def test_every_artifact_swapped_for_garbage_is_incomplete(self):
        for path in load_docs(self.repo, self.base):
            for junk in ("", "not json", "[]", "null", "{}", '{"a": NaN}', "﻿{}"):
                with self.subTest(path=path, junk=junk):
                    (sha,) = fast_commits(self.repo, self.base, [{path: junk}], self.approver)
                    self.assertEqual(self.verdict(sha, sha)["aggregate"], "INCOMPLETE")

    def test_extra_approver_keeps_bundle_valid_but_losing_the_author_does_not(self):
        pol = lambda **kw: policy(**kw)  # noqa: E731
        ok, no_author, signed = fast_commits(self.repo, self.base, [
            {".ddg/approvers.json": pol(approvers=(self.approver, "bob@example.com"))},
            {".ddg/approvers.json": pol(approvers=("bob@example.com",))},
            {".ddg/approvers.json": pol(require_signed=True, approvers=(self.approver,))},
        ], self.approver)
        self.assertEqual(self.verdict(ok, ok)["aggregate"], "PASSED_CHECKS")
        self.assertEqual(self.verdict(no_author, no_author)["aggregate"], "INCOMPLETE")
        self.assertEqual(self.verdict(signed, signed)["aggregate"], "INCOMPLETE")

    def test_second_active_decision_without_a_check_is_a_coverage_hole(self):
        old = {**DEC1, "id": "DEC-801", "status": "superseded", "supersedes": None}
        new = {**DEC2, "id": "DEC-802", "supersedes": "DEC-801"}
        (sha,) = fast_commits(self.repo, self.base, [{
            ".ddg/decisions/DEC-801.json": text_of(old), ".ddg/decisions/DEC-802.json": text_of(new)}],
            self.approver)
        report = self.verdict(sha, sha)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertIn("MISSING_APPROVED_COVERAGE", {w["code"] for w in report["warnings"]})

    # -- head-only edits stay pinned to base -------------------------------------------
    def head_specs(self):
        docs = load_docs(self.repo, self.base)
        specs = []
        for path, doc in sorted(docs.items()):
            specs.append({path: None})
            specs.append({path: text_of(next(m for _, _, m in mutants(doc)))})
            specs.append({path: text_of(doc) + "\n\n"})
        specs.append({".ddg/checks/CHK-999.json": "{}\n"})
        specs.append({".ddg/decisions/DEC-999.json": "{}\n"})
        return specs

    def test_same_edits_only_at_head_leave_authority_pinned_to_base(self):
        specs = [{**spec, **self.benign_head_files} for spec in self.head_specs()]
        for spec, sha in zip(specs, fast_commits(self.repo, self.base, specs, self.approver)):
            with self.subTest(sorted(spec)[0]):
                report = self.verdict(self.base, sha)
                self.assertEqual(report["aggregate"], "INCOMPLETE")
                self.assertIn("POLICY_REVIEW_REQUIRED", {w["code"] for w in report["warnings"]})
                self.assertEqual([c["verdict"] for c in report["checks"]], ["CHECK_PASSED"])

    # -- no-op and reversed ranges ------------------------------------------------------
    def test_base_equals_head_is_a_clean_noop(self):
        report = self.verdict(self.base, self.base)
        self.assertEqual((report["aggregate"], report["base_sha"] == report["head_sha"]), ("PASSED_CHECKS", True))
        self.assertEqual([w["code"] for w in report["warnings"]], [])

    def test_head_that_is_an_ancestor_of_base_is_incomplete(self):
        parent = git(self.repo, "rev-parse", f"{self.base}~1")
        report = self.verdict(self.base, parent)
        self.assertEqual(report["aggregate"], "INCOMPLETE")  # head predates the approval -> policy differs


class FunctionTamperTests(TamperMixin, FunctionAdapterBase):
    sandbox_mode = os.environ.get("DDG_SANDBOX", "host")

    def setUp(self):
        super().setUp()
        self.approver = GOOD
        self.benign_head_files = {"src/pricing.py": REFACTORED}

    # -- head-only weakening cannot rescue a regression --------------------------------
    def test_head_deleting_the_check_cannot_hide_a_regression(self):
        (sha,) = fast_commits(self.repo, self.base, [
            {".ddg/checks/CHK-001.json": None, ".ddg/validations/CHK-001.json": None,
             ".ddg/approvals/CHK-001.json": None, "src/pricing.py": BAD}], GOOD)
        report = compare(self.repo, self.base, sha)
        self.assertEqual(report["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertIn("POLICY_REVIEW_REQUIRED", {w["code"] for w in report["warnings"]})

    def test_tampered_base_plus_real_regression_never_goes_green(self):
        docs = load_docs(self.repo, self.base)
        docs[".ddg/checks/CHK-001.json"]["assertions"] = docs[".ddg/checks/CHK-001.json"]["assertions"][:1]
        (tampered,) = fast_commits(self.repo, self.base, [
            {".ddg/checks/CHK-001.json": text_of(docs[".ddg/checks/CHK-001.json"])}], GOOD)
        (head,) = fast_commits(self.repo, tampered, [{"src/pricing.py": BAD}], GOOD)
        report = compare(self.repo, tampered, head)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual(report["checks"][0]["verdict"], "NOT_CHECKED")

    # -- timestamps (clock skew) -------------------------------------------------------
    def stamped(self, artifact, value, remove=False):
        docs = load_docs(self.repo, self.base)
        path = f".ddg/{artifact}s/CHK-001.json"
        field = "validated_at" if artifact == "validation" else "approved_at"
        docs[path][field] = value
        reseal(docs)
        files = {p: text_of(docs[p]) for p in (path, ".ddg/approvals/CHK-001.json")}
        (sha,) = fast_commits(self.repo, self.base, [files], GOOD)
        return compare(self.repo, sha, sha)["aggregate"]

    def test_future_timestamps_are_accepted_when_the_digest_is_valid(self):
        # Decision: clock skew (a signer's clock running ahead) must never make a bundle unverifiable.
        for artifact in ("validation", "approval"):
            for value in ("2999-01-01T00:00:00Z", "2999-01-01T00:00:00+05:30"):
                with self.subTest(artifact=artifact, value=value):
                    self.assertEqual(self.stamped(artifact, value), "PASSED_CHECKS")

    def test_malformed_timestamps_are_rejected(self):
        for artifact in ("validation", "approval"):
            for value in ("yesterday", "2026-13-45T00:00:00Z", "2026-10-12T00:00:00", "", 1760000000, None, [], True):
                with self.subTest(artifact=artifact, value=value):
                    self.assertEqual(self.stamped(artifact, value), "INCOMPLETE")

    def test_captured_at_future_is_accepted_and_malformed_is_rejected(self):
        def recorded(captured_at):
            return {"proposal_mode": "recorded", "model": "m", "sdk_version": "1", "captured_at": captured_at,
                    "capture_source_sha": "a" * 40, "input_digest": "d" * 64,
                    "request_metadata": {"model": "m", "prompt_version": "p", "input_digest": "d" * 64,
                                         "request_count": 1, "response_format": "application/json",
                                         "timeout_seconds": 30},
                    "provider_response": {"status": "DRAFT", "reason": ""},
                    "attempts": [{"attempt": 1, "result": "recorded_capture"}]}
        self.assertTrue(_provenance_valid(recorded("2026-10-12T00:00:00Z")))
        self.assertTrue(_provenance_valid(recorded("2999-01-01T00:00:00Z")))
        for bad in ("soon", "2026-10-12T00:00:00", "", None, 5):
            with self.subTest(bad):
                self.assertFalse(_provenance_valid(recorded(bad)))

    # -- stale reports -----------------------------------------------------------------
    def test_report_goes_stale_when_a_ref_moves_or_is_force_pushed(self):
        git(self.repo, "branch", "-f", "pr", self.head("pr-a", REFACTORED))
        git(self.repo, "branch", "-f", "target", self.base)
        report = compare(self.repo, "target", "pr")
        self.assertFalse(is_stale(self.repo, report, "target", "pr"))
        old_head = report["head_sha"]
        git(self.repo, "branch", "-f", "pr", self.head("pr-b", REFACTORED + "# new push\n"))  # fast-forward-ish push
        self.assertTrue(is_stale(self.repo, report, "target", "pr"))
        git(self.repo, "branch", "-f", "pr", old_head)  # moved back: matches the report again
        self.assertFalse(is_stale(self.repo, report, "target", "pr"))
        git(self.repo, "branch", "-f", "pr", self.head("pr-c", GOOD_SRC + "# rewritten\n"))  # force-push to a sibling
        self.assertTrue(is_stale(self.repo, report, "target", "pr"))
        git(self.repo, "branch", "-f", "target", self.head("tgt", GOOD_SRC + "# base moved\n"))
        git(self.repo, "branch", "-f", "pr", old_head)
        self.assertTrue(is_stale(self.repo, report, "target", "pr"))  # base moved
        git(self.repo, "branch", "-D", "pr")
        self.assertTrue(is_stale(self.repo, report, "target", "pr"))  # deleted ref

    def test_stale_check_rejects_a_forged_report(self):
        for forged in ({}, {"base_sha": "x", "head_sha": "y"}, None):
            with self.assertRaises(ValueError):
                is_stale(self.repo, forged, self.base, self.base)

    # -- concurrency -------------------------------------------------------------------
    def test_concurrent_compares_agree_and_leave_nothing_behind(self):
        head = self.head("conc", REFACTORED)
        reports, errors = [], []
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)

        def work():
            try:
                reports.append(compare(self.repo, self.base, head))
            except Exception as exc:  # pragma: no cover - the assertion below reports it
                errors.append(repr(exc))

        with patch.object(tempfile, "tempdir", scratch.name):
            threads = [threading.Thread(target=work) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(180)
        self.assertEqual(errors, [])
        self.assertEqual(len(reports), 4)
        strip = lambda r: {k: v for k, v in r.items() if k != "run_at"}  # noqa: E731
        self.assertTrue(all(strip(r) == strip(reports[0]) for r in reports))
        self.assertEqual(reports[0]["aggregate"], "PASSED_CHECKS")
        self.assertEqual(os.listdir(scratch.name), [])
        if reports[0]["sandbox"] != "host":
            runtime = reports[0]["sandbox"]
            left = subprocess.run([runtime, "ps", "-a", "--filter", "name=ddg-", "--filter", "status=exited",
                                   "--filter", "status=created", "--format", "{{.Names}}"],
                                  capture_output=True, text=True).stdout.split()
            self.assertEqual(left, [])


class JobAdapterTamperTests(TamperMixin, unittest.TestCase):
    """Same walks over the job-client adapter (sampled: its ordinary-test observation is slower)."""

    @classmethod
    def setUpClass(cls):
        cls.sample = SAMPLE * 3
        cls.env = patch.dict(os.environ, {"DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        cls.env.start()
        cls.tmp = TemporaryDirectory(prefix="ddg tamper ")
        demo = make_approved_demo(Path(cls.tmp.name) / "repo")
        cls.repo = Path(demo["repo"])
        cls.base = demo["refs"]["approved_base"]
        cls.approver = DEMO_APPROVER
        cls.benign_head_files = {"src/job_client.py": read_at(cls.repo, demo["refs"]["unrelated"], "src/job_client.py")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.env.stop()


class MultiCheckBase(unittest.TestCase):
    """A repo with N independently approved checks."""

    N = 2

    @classmethod
    def build(cls, folder, count):
        repo = Path(folder) / "repo"
        repo.mkdir()
        git(repo, "init", "--quiet")
        pair = lambda i: (f"DEC-{2 * i - 1:03d}", f"DEC-{2 * i:03d}")  # noqa: E731
        old = {".ddg/approvers.json": policy(), "src/pricing.py": BAD}
        new = {}
        for i in range(1, count + 1):
            a, b = pair(i)
            old[f".ddg/decisions/{a}.json"] = js({**DEC1, "id": a, "status": "active"})
            new[f".ddg/decisions/{a}.json"] = js({**DEC1, "id": a})
            new[f".ddg/decisions/{b}.json"] = js({**DEC2, "id": b, "supersedes": a, "rule": DEC2["rule"] + f" #{i}"})
        commit(repo, old, "initial")
        bad = commit(repo, new, "new rules")
        good = commit(repo, {"src/pricing.py": GOOD_SRC}, "validate input")
        exception = commit(repo, {"src/pricing.py": "# zero is fine\n" + GOOD_SRC}, "document zero")
        refs = {"calibration_bad": bad, "calibration_good": good, "calibration_exception": exception}
        git(repo, "checkout", "--quiet", "--detach", good)
        for i in range(1, count + 1):
            a, b = pair(i)
            check = {**CHECK, "id": f"CHK-{i:03d}", "decision_id": b, "supersedes": a,
                     "citations": [{"decision_id": b, "quote": "must reject negative prices with ValueError"}]}
            draft = wrap_draft(load_context(repo, decision_id=b, revision=good, adapter=CHECK["adapter"]),
                               check, mode="manual")
            validation = validate_draft(repo, draft, refs)
            assert validation["eligible"]
            approve(repo, draft, validation, "Alice", "Reviewed pricing rule")
            commit(repo, {}, f"approve CHK-{i:03d}")
        return repo, resolve_commit(repo, "HEAD")

    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {"DDG_SANDBOX": os.environ.get("DDG_SANDBOX", "host"),
                                          "DDG_ALLOW_UNVERIFIED_APPROVERS": ""})
        cls.env.start()
        cls.tmp = TemporaryDirectory()
        cls.repo, cls.base = cls.build(cls.tmp.name, cls.N)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.env.stop()


class SwapTests(MultiCheckBase):
    N = 2

    def test_control_both_checks_pass(self):
        report = compare(self.repo, self.base, self.base)
        self.assertEqual((report["aggregate"], [c["verdict"] for c in report["checks"]]),
                         ("PASSED_CHECKS", ["CHECK_PASSED"] * 2))

    def test_swapping_artifacts_between_two_checks_is_incomplete(self):
        docs = load_docs(self.repo, self.base)
        swaps = []
        for kind in ("checks", "validations", "approvals"):
            a, b = (f".ddg/{kind}/CHK-001.json", f".ddg/{kind}/CHK-002.json")
            swaps.append({a: text_of(docs[b]), b: text_of(docs[a])})  # swap both
            swaps.append({a: text_of(docs[b])})                     # overwrite one with the other's
        for kind in ("validations", "approvals"):  # bundle halves from different checks, own paths kept
            swaps.append({f".ddg/{kind}/CHK-001.json": text_of(docs[f".ddg/{kind}/CHK-002.json"]),
                          f".ddg/{kind}/CHK-002.json": text_of(docs[f".ddg/{kind}/CHK-001.json"])})
        for spec, sha in zip(swaps, fast_commits(self.repo, self.base, swaps, GOOD)):
            with self.subTest(sorted(spec)):
                report = compare(self.repo, sha, sha)
                self.assertEqual(report["aggregate"], "INCOMPLETE")
                self.assertIn("NOT_CHECKED", {c["verdict"] for c in report["checks"]})

    def test_one_tampered_check_does_not_taint_or_hide_the_other(self):
        (sha,) = fast_commits(self.repo, self.base, [{".ddg/validations/CHK-002.json": None}], GOOD)
        report = compare(self.repo, sha, sha)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        self.assertEqual({c["check_id"]: c["verdict"] for c in report["checks"]},
                         {"CHK-001": "CHECK_PASSED", "CHK-002": "NOT_CHECKED"})


@unittest.skipIf(os.environ.get("DDG_SANDBOX", "host") != "host", "50-check scale run is host-only (container runs are slow)")
class ScaleTests(MultiCheckBase):
    N = 50

    def test_fifty_checks_stay_correct(self):
        report = compare(self.repo, self.base, self.base)
        self.assertEqual(report["aggregate"], "PASSED_CHECKS")
        self.assertEqual(len(report["checks"]), 50)
        self.assertEqual({c["verdict"] for c in report["checks"]}, {"CHECK_PASSED"})

    def test_one_bad_check_among_fifty_flips_only_itself(self):
        docs = load_docs(self.repo, self.base)
        doc = docs[".ddg/approvals/CHK-037.json"]
        doc["reviewer"] = ""
        (sha,) = fast_commits(self.repo, self.base, [{".ddg/approvals/CHK-037.json": text_of(doc)}], GOOD)
        report = compare(self.repo, sha, sha)
        self.assertEqual(report["aggregate"], "INCOMPLETE")
        verdicts = {c["check_id"]: c["verdict"] for c in report["checks"]}
        self.assertEqual(verdicts.pop("CHK-037"), "NOT_CHECKED")
        self.assertEqual(set(verdicts.values()), {"CHECK_PASSED"})


if __name__ == "__main__":
    unittest.main()
