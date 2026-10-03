# Decision Drift Gate Implementation Plan

> **For agentic workers:** Follow [the phased roadmap](../../../PHASES.md): GPT 6.1 Sol High orchestrates and reviews; GPT 6 Luna implements the assigned phase. Use superpowers:executing-plans for the phase's detailed tasks. Steps use checkbox syntax. This document is a plan, not executed source or test evidence.

**Goal:** demonstrate a real AI proposal becoming a developer-approved behavioral check that catches a later regression and explains the governing decision.

**Architecture:** a small Python engine reads pinned Git revisions, validates versioned decisions and approvals, and runs one structured check against each revision in a fresh process. A CLI and local browser share the application functions. The model drafts the check once; subsequent verdicts come from execution.

**Tech Stack:** Python 3.12+, Git, unittest, JSON, hashlib, subprocess, argparse, http.server; optional google-genai for live proposals; plain HTML/CSS/JavaScript for the browser.

**Spec:** [Decision Drift Gate Design](../specs/2026-10-03-decision-drift-gate-design.md).

## Global Constraints

- Python 3.12 or newer; Windows PowerShell and Linux shells are supported.
- Git is required; the local execution engine and its tests use the Python standard library.
- The only planned third-party runtime dependency is google-genai for the optional live proposal provider.
- MVP coverage is one trusted synthetic Python module at src/job_client.py with submit_job(service, payload, operation_id) -> str.
- The browser server binds only to 127.0.0.1:8765; no deployment or public service is required.
- All approved active checks run; AI never selects which checks to skip.
- The authoritative decision, check, and approval bundle comes from the pinned target revision.
- Missing evidence, execution errors, or unapproved policy changes cannot produce a green aggregate result.
- No LLM call is required to execute an approved check.
- No live customer data, PAN, or tax identifier is used.
- Generated demo repositories, secrets, local sessions, and evaluation outputs are ignored by source Git.
- No source-code implementation, external publication, or remote push is part of this planning change.

The last constraint describes the current request. Executing this plan is a subsequent implementation action. All commands below are intended commands to become runnable during execution.

## Review Focus

- A weak check can count duplicates while allowing silent failure; require the abort case in Task 2 and calibration rejection in Task 4.
- A candidate can change its own approval or decision; require policy-edit and digest-tamper tests in Task 5.
- A target can already fail; require PRE_EXISTING_FAILURE and RESOLVED tests in Task 5.
- A subprocess can fail without emitting usable results; require crash, timeout, and missing-module tests in Tasks 2 and 5.
- A browser can display stale results or replayed AI as live; require ref-move, mode-label, and stale-draft tests in Tasks 6 and 7.

## File map

```text
ddg/
  __init__.py          package marker
  __main__.py          main() entrypoint
  contracts.py         schema validation, canonical JSON, fingerprints
  gitio.py             fixed-revision reads and diffs
  demo.py              safe synthetic history and scenario construction
  harness.py           trusted fake service, assertion evaluation
  worker.py            fresh-process module execution
  proposal.py          live/recorded proposal and grounded citations
  approval.py          calibration, approval, demo activation
  engine.py            authority checks, two-version execution, verdict
  report.py            report serialization and current-ref status
  cli.py               argparse commands and exit codes
  web.py               local HTTP actions and persisted demo session
web/
  index.html           decision, approval, review views
  app.js               actions, state rendering, mode and stale labels
  style.css            legible layout, states, keyboard focus
tests/
  __init__.py
  support.py           reusable temporary-demo builders
  test_gitio.py
  test_demo.py
  test_contracts.py
  test_harness.py
  test_proposal.py
  test_approval.py
  test_engine.py
  test_cli.py
  test_web.py
  test_evaluate.py
examples/
  manual_check.json    disclosed hand-authored schema example
evidence/
  README.md            evidence provenance and interpretation
scripts/
  evaluate.py          case matrix and raw timing export
requirements-ai.txt   only google-genai, release-pinned after live verification
.gitignore             generated repos, .env, sessions, outputs, caches
README.md              setup, quickstart, scope, actual verification status
docs/                  architecture, plan, demo, delivery, evaluation
```

Do not create a database, queue, agent framework, or frontend build pipeline. Standard-library tests run offline. Version-lock the single optional SDK after a successful live run and record that tested version; the core must still work without it installed.

## Common contracts

Use plain dictionaries rather than a framework. Validation occurs at every external boundary. Functions raise ValueError for invalid user/domain input; the application boundary converts these into structured errors. Execution failures return ERROR observations so they cannot be mistaken for assertion failures.

```python
def resolve_commit(repo: Path, ref: str) -> str: ...
def read_at(repo: Path, sha: str, path: str) -> str: ...
def diff_at(repo: Path, base_sha: str, head_sha: str) -> str: ...
def build_demo(destination: Path) -> dict: ...
def canonical_bytes(value: dict) -> bytes: ...
def validate_check(value: dict) -> dict: ...
def observe(repo: Path, sha: str, check: dict, timeout: float = 10) -> dict: ...
def propose(context: dict, mode: str, client=None) -> dict: ...
def validate_draft(repo: Path, draft: dict, refs: dict) -> dict: ...
def approve(repo: Path, draft: dict, validation: dict,
            reviewer: str, reason: str, commit_demo: bool = False) -> dict: ...
def compare(repo: Path, base: str, head: str) -> dict: ...
def write_report(report: dict, destination: Path) -> None: ...
def is_stale(repo: Path, report: dict, base: str, head: str) -> bool: ...
def main(argv: list[str] | None = None) -> int: ...
def create_server(repo: Path, state_dir: Path, port: int = 8765): ...
```

These signatures are interface declarations for implementation, not placeholder tasks. Concrete behavior, fixtures, test assertions, and commands are defined below. The spec fixes full check and result semantics.

Proposal envelope: check, draft_digest, input_digest, decision, proposal_mode, model, captured_at, source_sha. Validation envelope: draft_digest, decision_digest, adapter_version, calibration hashes, cases, eligible, validated_at. On-disk approval: bundle_digest, reviewer, reason, approved_at, calibration hashes. The return value from approve additionally contains base_sha after an explicit demo commit; keep it in external metadata rather than creating a circular hash inside the commit. Report envelope: aggregate, base_sha, head_sha, checks, warnings, run_at, adapter_version, ordinary_tests; each check has verdict, base, head, decision, check_digest, approval, diff.

## Task 1: Create reproducible Git history and fixed-revision reads

**Files:** create ddg/__init__.py, ddg/gitio.py, ddg/demo.py, tests/__init__.py, tests/support.py, tests/test_gitio.py, tests/test_demo.py, .gitignore.

**Interfaces:** consumes Git through subprocess argument arrays; produces resolve_commit, read_at, diff_at, build_demo. build_demo returns repo plus refs with calibration_bad, calibration_good, calibration_exception, decision_change, missing_policy, crashing, timing_out. It writes an ignored metadata file marking the repository as DDG-generated. Scenario templates for holdout and later review branches are generated only when approval activates the demo in Task 4.

- [ ] Write a temporary-repository test that proves a branch movement cannot change a read using its original SHA:

```python
class GitReadTests(unittest.TestCase):
    def test_pinned_read_survives_ref_move(self):
        with TemporaryDirectory(prefix="ddg space ") as folder:
            demo = build_demo(Path(folder) / "repo")
            repo = Path(demo["repo"])
            sha = resolve_commit(repo, demo["refs"]["calibration_good"])
            original = read_at(repo, sha, "src/job_client.py")
            subprocess.run(["git", "-C", str(repo), "update-ref",
                            "refs/heads/moved", sha], check=True)
            bad_sha = resolve_commit(repo, demo["refs"]["calibration_bad"])
            subprocess.run(["git", "-C", str(repo), "update-ref",
                            "refs/heads/moved", bad_sha], check=True)
            self.assertEqual(read_at(repo, sha, "src/job_client.py"), original)
            self.assertNotEqual(read_at(repo, resolve_commit(repo, "moved"),
                                       "src/job_client.py"), original)
            self.assertEqual(len(sha), 40)  # explicitly use SHA-1 demo repositories
```

- [ ] Add tests for nonempty destination refusal, missing ref/object, a ref beginning with '-', paths with spaces, dirty checkout preservation, and explicit supersession records. Assert refusal leaves all original files and Git refs unchanged.
- [ ] Run `python -m unittest tests.test_gitio tests.test_demo -v`; expect failures because the functions are absent.
- [ ] Implement reads using this fixed invocation form:

```python
def resolve_commit(repo, ref):
    if not ref or ref.startswith("-"):
        raise ValueError("Invalid revision")
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", ref + "^{commit}"],
        capture_output=True, text=True, check=True, timeout=10)
    return result.stdout.strip()
```

read_at uses `git show SHA:path`; diff_at uses `git diff --unified=3 BASE HEAD -- src/job_client.py`. Convert Git errors to ValueError with the operation and safe ref, without environment contents. Demo creation uses `git init --object-format=sha1`; demo-only author identity is supplied with per-command Git config, never global config.

- [ ] Construct DEC-001, DEC-002, blind retry, reconciliation, and stable-key implementations from explicit strings in demo.py. Each implements submit_job(service, payload, operation_id). Keep the known-good code as:

```python
def submit_job(service, payload, operation_id):
    response = service.create(payload, operation_id)
    if response.status == 503:
        existing = service.lookup(operation_id)
        if existing is not None:
            return existing
        response = service.create(payload, operation_id)
    return response.job_id
```

The bad version performs a second create on 503 without lookup/key. The exception passes idempotency_key=operation_id on both creates. Crash raises RuntimeError; timeout loops without producing output. Commit decision history in the new synthetic repository only.

- [ ] Run the same tests; require all pass and inspect the generated history. Commit this task's source and tests with `feat: add reproducible decision history and pinned Git reads`.

## Task 2: Execute structured behavioral checks

**Files:** create ddg/contracts.py, ddg/harness.py, ddg/worker.py, examples/manual_check.json, tests/test_contracts.py, tests/test_harness.py.

**Interfaces:** consumes read_at and the synthetic submit_job contract; produces canonical_bytes, validate_check, observe. observe returns status=PASS|FAIL|ERROR, unique_jobs, returned_job_exists, returned_job_id, submit_calls, events, and error. On ERROR, unavailable metrics are null rather than made-up observations.

- [ ] Use the exact valid check from the spec as examples/manual_check.json and a test input. Add the central observable test:

```python
class HarnessTests(unittest.TestCase):
    def test_lost_ack_exposes_duplicate(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            check = json.loads(Path("examples/manual_check.json").read_text())
            bad = observe(Path(demo["repo"]), demo["refs"]["calibration_bad"], check)
            good = observe(Path(demo["repo"]), demo["refs"]["calibration_good"], check)
            self.assertEqual((bad["status"], bad["unique_jobs"]), ("FAIL", 2))
            self.assertEqual((good["status"], good["unique_jobs"]), ("PASS", 1))
            self.assertTrue(good["returned_job_exists"])
```

- [ ] Add assertions for stable-key PASS, silent-abort FAIL, reject_then_503 semantics, unknown schema fields, empty/duplicate assertions, missing returned_job_exists assertion, boolean used as an integer, unsupported adapter, missing entrypoint, crash, timeout, and removal of provider keys from the worker environment. Require both metrics before execution. A supported assertion failure must be FAIL; a crash must be ERROR.
- [ ] Run `python -m unittest tests.test_contracts tests.test_harness -v`; expect missing-function failures.
- [ ] Implement strict schema validation, exact enum/type checks, and canonical serialization:

```python
def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

def evaluate_assertions(check, observed):
    return all(observed[item["metric"]] == item["equals"]
               for item in check["assertions"])
```

The FakeService records committed jobs before returning the fault. Deduplicate creates only on a supplied stable key. Track whether the client's return names an existing job. The worker loads the extracted job_client.py with importlib.util; invoke it with the trusted tool as cwd, timeout, shell=False, and a small explicit environment without model keys. stdout is one JSON result; trace events are in that JSON. Catch import/runtime errors into ERROR. Each revision gets separate state.

- [ ] Run both suites; require all pass. Commit `feat: run bounded behavioral checks with observable traces`.

## Task 3: Draft a real AI check and record its provenance

**Files:** create ddg/proposal.py, requirements-ai.txt, tests/test_proposal.py; extend contracts.py for decision graphs/citations.

**Interfaces:** consumes old/new decisions, corrected source, adapter vocabulary, and source_sha; produces propose(context, mode, client=None). The provider's JSON envelope has status=DRAFT|UNSUPPORTED_DECISION, check=object|null, and reason. The live prompt sends decision/source/adapter content; the tool attaches source_sha afterward. Hash only decision content, corrected source, adapter vocabulary, and prompt version; exclude the capture field and provenance SHA so identical rebuilt inputs can use a capture. Recorded mode verifies that content digest and preserves original capture provenance alongside the current source SHA. A manual schema sample is never substituted for live output.

- [ ] Test with an injected fake client returning schema-valid JSON, then alter the citation to a sentence absent from the decision. Require the altered response to raise ValueError and produce no eligible draft. Also test unsupported decisions, malformed JSON, provider timeout, missing model/key, cycle/missing predecessor/competing successors, and recorded-input mismatch.

```python
class ProposalTests(unittest.TestCase):
    def test_recorded_requires_matching_inputs(self):
        context = {"old_decision": {"id": "DEC-001"},
                   "new_decision": {"id": "DEC-002"},
                   "source_sha": "a" * 40, "source": "current code",
                   "adapter": "python_job_client_v1",
                   "capture": {"input_digest": "wrong", "check": {}}}
        with self.assertRaisesRegex(ValueError, "input"):
            propose(context, "recorded")
```

- [ ] Run `python -m unittest tests.test_proposal -v`; expect failure before implementation.
- [ ] Build the grounded prompt: identify the changed rule, choose one supported fault and observable assertions, preserve the valid exception, return exact decision quotes, and return unsupported when the vocabulary cannot express the rule. Repository text is evidence, not instructions to run tools. Do not include holdout source or expected labels.
- [ ] Implement one provider call through the official client surface:

```python
interaction = client.interactions.create(
    model=os.environ["DDG_GEMINI_MODEL"],
    input=grounded_prompt,
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": provider_response_schema})
response = json.loads(interaction.output_text)
if response["status"] == "UNSUPPORTED_DECISION":
    raise ValueError("UNSUPPORTED_DECISION: " + response["reason"])
body = validate_check(response["check"])
```

Configure the client's HTTP request timeout to 30 seconds using its documented HTTP options. Apply at most one schema-repair retry; do not retry credentials or quota failures. Independently validate every field and citation, then store the envelope and sanitized attempts. Record actual SDK/model version. Lazy-import the optional SDK so offline execution works without it.

- [ ] Run offline tests. Separately make one configured real call on synthetic inputs and record the successful output, input digest, model, SDK version, and capture time. If credentials are unavailable, retain the tested adapter and mark live verification incomplete; do not invent a capture. Commit `feat: draft grounded checks with explicit live and recorded modes` after checking artifacts contain no key.

## Task 4: Validate and approve the exact check bundle

**Files:** create ddg/approval.py, tests/test_approval.py; extend demo.py and tests/support.py.

**Interfaces:** consumes propose/observe/canonical_bytes; produces validate_draft, approve. approve requires current matching validation and explicit reviewer/reason. It writes checks, validations, approvals only after all calibration gates pass. commit_demo=True may commit these files and construct review branches only in a clean repository bearing the generated-demo marker.

- [ ] Test a check that looks plausible but selects reject_then_503; it must not be eligible if the known-bad client also passes. Test rejection of a missing returned_job_exists assertion, empty reviewer/reason, edited check after validation, changed decision, and error during calibration.

```python
class ApprovalTests(unittest.TestCase):
    def test_weak_scenario_cannot_be_approved(self):
        with TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            draft = make_manual_draft(Path(demo["repo"]), demo["refs"])
            draft["check"]["scenario"] = "reject_then_503"
            draft = refingerprint(draft)
            result = validate_draft(Path(demo["repo"]), draft, demo["refs"])
            self.assertFalse(result["eligible"])
            with self.assertRaises(ValueError):
                approve(Path(demo["repo"]), draft, result, "Dev", "Reviewed")
```

make_manual_draft and refingerprint are test-only helpers in tests/support.py: read the disclosed example, bind the actual DEC-002/input revision, compute canonical digests, and label proposal_mode=manual. They do not masquerade as AI evidence.

- [ ] Run `python -m unittest tests.test_approval -v`; expect failure.
- [ ] Implement calibration with bad FAIL, good PASS, exception PASS; any ERROR sets eligible=false. Show all observations. On approve, recompute draft/decision hashes, verify calibration hashes, construct bundle digest, and atomically write JSON records. Include .ddg/validations/CHK-001.json in the bundle so execution can verify the calibration bytes.
- [ ] Implement explicit generated-demo activation: verify a clean checkout and DDG marker, commit only .ddg/checks/CHK-001.json, .ddg/validations/CHK-001.json, and .ddg/approvals/CHK-001.json, set refs/heads/approved-base, and create named candidate commits using fixture templates. Produce refs for regression, unseen_regression, corrected, exception, unrelated, abort, policy_edit, preexisting_base, preexisting_head, resolved. All review branches inherit the approved policy bundle; preexisting_base and preexisting_head both contain faulty client code, and resolved fixes that faulty base. Return full hashes in external metadata. Existing calibration fixtures stay untouched.
- [ ] Define tests.support.make_approved_demo(destination) -> dict using build_demo, make_manual_draft, validate_draft, approve(..., commit_demo=True). Return repo, refs, and approval. An engine test can use this helper without a model dependency.
- [ ] Require no writes on rejection and refusal to auto-commit ordinary repos or dirty demos. Run tests; commit `feat: calibrate and approve immutable decision check bundles`.

## Task 5: Compare two revisions without false authority or false attribution

**Files:** create ddg/engine.py, tests/test_engine.py; extend gitio.py to enumerate/read .ddg records at base.

**Interfaces:** consumes all earlier contracts; produces compare(repo, base, head) -> report. All check authority comes from base; all outcomes use the same approved bundle. A policy change at head adds an incomplete warning while retaining observations.

- [ ] Write the core classification tests:

```python
class EngineTests(unittest.TestCase):
    def test_reports_new_failure_and_valid_exception(self):
        with TemporaryDirectory() as folder:
            demo = make_approved_demo(Path(folder) / "repo")
            repo, refs = Path(demo["repo"]), demo["refs"]
            bad = compare(repo, refs["approved_base"], refs["regression"])
            allowed = compare(repo, refs["approved_base"], refs["exception"])
            self.assertEqual(bad["aggregate"], "FAILED")
            self.assertEqual(bad["checks"][0]["verdict"], "VIOLATION_INTRODUCED")
            self.assertEqual(allowed["aggregate"], "PASSED_CHECKS")
```

- [ ] Add case tests for the full spec matrix: holdout, abort, unrelated, missing/cyclic decisions, tampered bundle, deleted check at head, unapproved check at base, preexisting failure, resolved failure, crash, timeout, missing source/object, and zero checks. Assert all active checks ran for unrelated changes. Assert every report carries full SHAs and exact base/head metrics.
- [ ] Run `python -m unittest tests.test_engine -v`; expect failure.
- [ ] Implement classification as an explicit table:

```python
def verdict(base, head):
    if "ERROR" in (base["status"], head["status"]):
        return "NOT_CHECKED"
    return {
        ("PASS", "FAIL"): "VIOLATION_INTRODUCED",
        ("FAIL", "FAIL"): "PRE_EXISTING_FAILURE",
        ("FAIL", "PASS"): "RESOLVED",
        ("PASS", "PASS"): "CHECK_PASSED",
    }[(base["status"], head["status"])]
```

Resolve hashes once, validate decision graph, verify check/decision/calibration bundle digest and adapter version, detect head policy edits, and run every active approved check. Compute aggregate using the spec's precedence. Missing approval or uncovered active decisions produce an incomplete coverage warning. Changed lines are context, not an invented proof of the exact cause. Include ordinary happy-path results for both revisions from the trusted harness, not a static green badge.

- [ ] Run engine tests and all earlier suites. Commit `feat: report grounded two-revision decision check outcomes`.

## Task 6: Provide a reproducible CLI and evidence reports

**Files:** create ddg/report.py, ddg/cli.py, ddg/__main__.py, tests/test_cli.py; update README.md with runnable commands.

**Interfaces:** consumes the application functions above; produces main, write_report, is_stale. CLI commands carry explicit repo/ref paths. Session files/drafts are outside the target's governed .ddg artifacts until approval.

- [ ] Test actual subprocess invocation and exit mapping rather than implementation-shaped mocks:

```python
class CliTests(unittest.TestCase):
    def test_failure_has_machine_readable_evidence(self):
        with TemporaryDirectory() as folder:
            demo = make_approved_demo(Path(folder) / "repo")
            out = Path(folder) / "report.json"
            result = subprocess.run(
                [sys.executable, "-m", "ddg", "run", "--repo", demo["repo"],
                 "--base", demo["refs"]["approved_base"], "--head",
                 demo["refs"]["regression"], "--out", str(out)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(out.read_text())["aggregate"], "FAILED")
```

- [ ] Test codes 0/1/2, moved refs -> stale, same SHA -> current, HTML escaping in export, paths with spaces, invalid arguments, and absence of secrets in reports. Run `python -m unittest tests.test_cli -v`; expect failure.
- [ ] Implement argparse commands and use `raise SystemExit(main())` in __main__.py. Write JSON plus readable Markdown with exact decision text, observations, provenance, and diff. is_stale compares current refs to saved full hashes. Add a state status command or show stale state on run/serve; never silently overwrite a report's original hashes.
- [ ] The finished README quickstart must contain this PowerShell flow, with provider setup instructions separate from execution:

```powershell
python -m ddg demo-init --destination .ddg-demo
python -m ddg serve --repo .ddg-demo --state-dir .ddg-state
```

CLI lifecycle:

```powershell
python -m ddg propose --repo .ddg-demo --decision DEC-002 --mode live --out .ddg-state/draft.json
python -m ddg validate --repo .ddg-demo --draft .ddg-state/draft.json --out .ddg-state/validation.json
python -m ddg approve --repo .ddg-demo --draft .ddg-state/draft.json --validation .ddg-state/validation.json --reviewer Developer --reason "Checked bad, good and exception cases" --commit-demo
python -m ddg run --repo .ddg-demo --base approved-base --head regression --out .ddg-state/report.json
```

- [ ] Run suite, inspect a real generated report, and commit `feat: expose the check lifecycle through CLI and reports`.

## Task 7: Make the lifecycle understandable in a live browser demo

**Files:** create ddg/web.py, web/index.html, web/app.js, web/style.css, tests/test_web.py; update README.md.

**Interfaces:** consumes the same propose/validate/approve/compare functions; produces create_server and the GET/POST API specified in the design. Tests can use port=0; production default remains 8765.

- [ ] Start the server in a test thread and use urllib.request to exercise real routes. Assert approve before validation is 409, missing session token is 403, external Origin is 403, unknown scenario is 400, and large bodies are 413. Assert all validation failures preserve session/approval state. Add a round-trip integration test that uses a disclosed recorded fixture, validates, approves, runs regression, and receives FAILED.
- [ ] Run `python -m unittest tests.test_web -v`; expect failures.
- [ ] Implement named-asset GETs and JSON POST handling, fixed repo/scenario allowlists, content/body checks, token/local-origin checks, a mutation lock, and atomic state persistence. create_server stores bound repo, state_dir, state lock, and session token on the server instance. HTTP responses are JSON objects with state or error, never raw tracebacks or provider credentials.
- [ ] Implement safe frontend state updates:

```javascript
async function act(route, body) {
  const response = await fetch(`/api/${route}`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-DDG-Token": sessionToken},
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error);
  renderState(payload.state);
}
```

sessionToken is provided in the initial served page, not hardcoded. renderState uses textContent for model/decision text. Build the three views, visible mode/source labels, approval form, case selector, event timeline, side-by-side observations, and expandable evidence. Disable conflicting actions and stale approval submissions. Show stale reports after refs move. Never render ordinary-test success from a constant.

- [ ] Open the running page in the browser and verify the full lifecycle, keyboard navigation, labels, and reload persistence. Check 1366x768 projector size and a narrow viewport. Rehearse the fast reveal using preapproved policy but a fresh run; rehearse the longer generation/approval flow separately.
- [ ] Commit `feat: add a live local decision check demonstration` after HTTP tests and browser inspection pass. Screenshots document actual execution and carry mode labels.

## Task 8: Evaluate the proof and prepare the submission

**Files:** create scripts/evaluate.py, tests/test_evaluate.py, evidence/README.md, docs/EVALUATION.md, docs/ARCHITECTURE.md; update README.md, docs/PITCH_AND_DEMO.md, docs/DELIVERY_CHECKLIST.md; add the verified real capture with sanitized metadata.

**Interfaces:** consumes compare and approved demo refs; produces case_results.json and timing.csv under an ignored output directory. Curated sanitized summaries can be committed under evidence after review.

- [ ] Add a script test that runs every supported case and asserts case_results contains expected and observed verdict, metrics, exact hashes, and check digest. Manual timings are blank until recorded; no synthetic savings are inserted.
- [ ] Run `python -m unittest discover -s tests -v` and require all pass. Run `python scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation`; inspect misses and incorrect warnings.
- [ ] Implement the evaluator as a deterministic loop over the explicit acceptance cases, writing expected and observed results without changing either. CSV fields are reviewer_id, condition, task_id, order, setup_seconds, review_seconds, correct_verdict, correct_reason, notes. Condition is baseline or assisted; participant/task assignment is recorded before timing.
- [ ] Ask at least three unfamiliar developers to identify the governing rule and choose a review action. Counterbalance equivalent variants; count setup/approval time separately. Report individual observations if sample size is smaller. Preserve raw measurements and state limitations.
- [ ] Record the full live walkthrough and an explicitly labeled offline fallback. Fill release documentation with actual installation, tested versions/platforms, run commands, screenshots, check/adapter limits, and observed case results. No invented 50% claim enters the README or pitch.
- [ ] Rehearse the 20-second script five times with a timer; target 18-22 seconds with a readable failure card. Record the observed duration, rather than inferring it from word count. Rehearse a 90-second lifecycle demonstration.
- [ ] Check Git-tracked files for secrets, generated repos, broken relative links, and references to unavailable parent-folder files. Compare source status against release checklist. Confirm origin before any future push. Prepare a clean source commit `docs: add verified demo evidence and submission instructions`.
- [ ] Publish to the configured GitHub origin only as part of the implementation/submission request; verify the remote commit and that a fresh checkout reproduces the documented setup. The current planning request does not publish.

## Release gates and ownership

| Gate | Tasks | Evidence needed | Responsible role |
|---|---|---|---|
| A: behavioral proof | 1-2 | Bad fails, reconciliation/exception pass, abort fails | Engine developer |
| B: AI-to-approved-check lifecycle | 3-4 | Real capture, grounded proposal, calibration, digest-bound approval | AI/workflow developer and decision reviewer |
| C: credible review | 5-6 | Holdout, authority edits, failures, attribution, CLI reports | Engine developer and independent evaluator |
| D: live demonstration | 7 | Browser actions invoke real engine, honest labels, timed reveal | Demo developer and presenter |
| E: submission | 8 | Source reproduces, documentation accurate, evaluated cases | Release owner |

One person may hold several roles; team size is not assumed. Tasks are sequential because their interfaces and proof build on one another. If time becomes constrained, reduce visual polish and live host adapters first; preserve real execution, approval, valid exception, holdout, and provenance.

## Plan self-review

Coverage: decision authority and pinned revisions -> Tasks 1/5; bounded structured schema and behavior -> Task 2; live/recorded provenance -> Task 3; calibration and exact approval -> Task 4; complete state/error matrix -> Task 5; reproducible commands and stale evidence -> Task 6; live usability/local action controls -> Task 7; experiment, pitch rehearsal, documentation/source submission -> Task 8.

All five Review Focus cases have owners and concrete expected results. All shared names used by later tasks are declared above or explicitly introduced by their owning task. The current repository contains planning documents only; these tests have not been executed yet.
