# Decision Drift Gate Design

**Date:** 3 October 2026. **Purpose:** define the prototype for the Algo Works Hackathon live demo, documentation, and source submission. **Status:** design selected under the user's delegated planning authority; implementation and validation are outstanding.

## 1. Product promise and success

When a team replaces an engineering rule, the agent helps turn that decision into a developer-approved executable check. Later code changes run the check, and observed failures carry the reason the rule exists.

The user is a developer reviewing changes. A potential buyer is an engineering lead responsible for recurring regressions; willingness to pay has not been established. The demonstration succeeds when an unfamiliar reviewer understands one observed failure and its governing decision without a lengthy explanation.

The prototype must prove a complete lifecycle: changed decision, real AI proposal, calibration, explicit developer approval, execution on later code, and a cited report. It must also accept a valid exception and catch a variation that was absent from the proposal and calibration inputs.

## 2. Approaches considered

| Approach | Benefit | Limitation | Decision |
|---|---|---|---|
| AI judges each diff against decision prose | Quick review demonstration | Verdicts are difficult to verify; overlap with general reviewers | Retain only as historical context |
| AI generates unrestricted Python tests | Broad potential coverage | More execution and dependency complexity; difficult to make a small demo reliable | Expansion after the bounded proof |
| AI drafts a structured check interpreted by a known runner | Inspectable proposal, repeatable execution, explicit supported behavior | Covers one adapter and a small set of scenarios | Build this prototype |

A structured check is executable: its scenario and assertions drive the fake service and runner. It is not an AI-written Python program. The bounded vocabulary is an explicit product limit. AI selects the relevant scenario and measurable assertions from the decision; validation can reject an inadequate selection.

## 3. Global constraints

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

No deadline or team size has been supplied. Work is sequenced by release gates, not by invented dates. A local browser demonstration satisfies the known live-demo requirement; a hosted URL is not currently specified.

## 4. Demonstration behavior

DEC-001 allows retrying a 503. DEC-002 explicitly replaces it: an operation must not create duplicate jobs when the first submission succeeds but its acknowledgement fails. Reconcile by operation ID, or retry using a service-supported stable idempotency key. Returning a fabricated success or silently abandoning the operation is also invalid.

The trusted fake service supports create(payload, operation_id, idempotency_key=None) and lookup(operation_id). create returns a response with status and job_id. Its first call can either commit a job and return 503, or reject before committing and return 503. Subsequent successful calls return 201 and an existing or newly created job ID. lookup returns the first matching job ID or None. A stable key deduplicates repeated creates; operation_id alone does not deduplicate creates.

The decisive scenario is commit_then_503. The old client blindly retries and creates job-1 followed by job-2. The corrected client looks up the first operation and returns job-1. The exception client retries with the same idempotency key and also returns job-1. The check measures unique_jobs and whether the returned ID belongs to a created job.

Happy-path tests use a service without a fault. They genuinely pass on both the old and corrected implementation because they exercise ordinary success only. Their coverage gap is deliberate and disclosed in the synthetic demo; this is not evidence that arbitrary production suites would miss the bug.

## 5. Decision and check records

Target-repository layout:

```text
src/job_client.py
.ddg/decisions/DEC-001.json
.ddg/decisions/DEC-002.json
.ddg/checks/CHK-001.json
.ddg/validations/CHK-001.json
.ddg/approvals/CHK-001.json
```

Decision records contain schema_version, id, status, supersedes, scope, rule, and exceptions. IDs are unique. Each supersedes reference must exist; cycles or two active successors to the same decision require clarification. Historical records remain inspectable. Only status=active decisions can govern a check. The tool supplies the source revision from Git rather than asking the model to invent a commit hash.

Example check body:

```json
{
  "schema_version": 1,
  "id": "CHK-001",
  "decision_id": "DEC-002",
  "supersedes": "DEC-001",
  "adapter": "python_job_client_v1",
  "scenario": "commit_then_503",
  "assertions": [
    {"metric": "unique_jobs", "equals": 1},
    {"metric": "returned_job_exists", "equals": true}
  ],
  "rationale": "A failed acknowledgement must not duplicate an accepted operation.",
  "citations": [
    {"decision_id": "DEC-002", "quote": "must not create duplicate jobs"}
  ]
}
```

Allowed scenarios are commit_then_503 and reject_then_503. Allowed metrics are unique_jobs with an integer from 0 to 2 and returned_job_exists with a boolean. Exactly two distinct assertions, one for each metric, are required: checking duplicates alone would permit silent failure. Unknown fields, arbitrary expressions, executable code, paths, and shell commands are rejected. The sample is an intended valid check, not a recorded model output.

Each citation must name an input decision and quote an exact substring from its rule or exceptions. A correct citation does not prove the check captures the rule: calibration and developer review remain necessary. The provider returns an envelope with status=DRAFT or UNSUPPORTED_DECISION, check=the check body or null, and reason. An unsupported response never becomes an approvable draft. The local proposal envelope adds digests and provenance after validation.

Canonical JSON uses sort_keys=True, separators=(",", ":"), ensure_ascii=False and UTF-8. SHA-256 binds the check body, canonical active decision, adapter version, and validation record. The approval record stores that bundle digest, local reviewer name, rationale, UTC timestamp, and calibration revision hashes. It is a local attestation, not authenticated enterprise identity or a digital signature.

## 6. Proposal and approval lifecycle

1. The operator selects a decision replacement from a fixed demo repository. The tool resolves its full Git revision and gathers the old/new records, supported adapter contract, and corrected source. It excludes holdout implementations and expected answers.
2. A live Gemini call returns structured JSON. The tool validates schema and citations and saves the request metadata, sanitized response, model identifier, and input digest. The input digest covers the actual old/new decision content, corrected source, adapter vocabulary, and prompt version. Source revision is separate provenance metadata; it is not part of the content digest, allowing a recorded capture to be reused only when a rebuilt synthetic history has identical inputs. API keys are never recorded.
3. The UI shows the proposed fault, assertions, citations, and rationale. A developer may reject it or revise it; edits produce a new digest and invalidate earlier validation.
4. Explicit Validate runs the draft against known-bad, known-good, and permitted-exception fixtures. Approval requires bad=FAIL, good=PASS, exception=PASS, with no execution error.
5. Explicit Approve requires a nonblank reviewer and reason. It writes the exact validated bundle to the synthetic target repository. It does not merge or push. The operator's explicit demo approval action may commit only the new check, validation, and approval files in that synthetic repository and update the demo's authoritative target revision. The resulting commit hash is kept in external demo metadata, never inside its own committed approval file; this avoids a circular commit-hash dependency.
6. Fresh candidate commits are constructed on that approved target: seeded regression, unseen equivalent, exception, unrelated change, and policy edit. The unseen implementation is never used to tune the draft. Changing the check requires a fresh holdout experiment.

Live mode requires GEMINI_API_KEY and DDG_GEMINI_MODEL. Model choice is configuration, not a guessed latest version. Use the official structured-output client surface and record the actual model and SDK version used. A 30-second proposal timeout, malformed response, or unavailable provider leaves the draft unapproved. One bounded schema-repair retry is allowed; both attempts are recorded. No silent switch to a fixture is permitted.

For an offline fallback, Recorded proposal mode loads a previously captured real model response and labels it with model and capture time. Execution is still fresh. A handwritten example is labeled Manual sample and cannot be presented as AI-generated. Release requires evidence of at least one successful real model proposal.

## 7. Execution and authority

Resolve base and head with git rev-parse --verify <ref>^{commit}, then use the full hashes for all reads and reports. The synthetic demo refs contain no option-like user input; general CLI refs beginning with '-' are rejected. Resolve once per run. Preserve spaces in filesystem paths by invoking subprocesses with argument arrays and shell=False.

Read decisions, checks, and approvals exclusively from base. Changes under .ddg at head generate POLICY_REVIEW_REQUIRED; the existing approved checks may still run and show observations, but the aggregate stays non-green. A candidate cannot remove its own check or declare its own replacement decision authoritative.

For the small adapter, extract only src/job_client.py from each pinned revision into separate task-owned temporary directories. Run each version in a fresh subprocess with a fresh FakeService, the same approved check, and a 10-second timeout. Worker environments exclude model keys. This is process separation for trusted synthetic code, not a sandbox for arbitrary repositories. Unsupported imports, missing entrypoints, crashes, timeouts, or malformed worker output are execution errors. Temporary directories are cleaned within their verified task-owned root.

Each observed result includes status, unique_jobs, returned_job_exists, returned_job_id, submit_calls, and the service event trace. The adapter requires a returned existing job ID independently of candidate draft assertions: a draft asserting returned_job_exists=false is schema-valid but cannot pass known-good calibration or be approved. Dynamic import/execution mechanisms are outside this bounded adapter's vocabulary and produce execution errors. These checks are not a sandbox for malicious source. Git and worker JSON use explicit UTF-8 on Windows and Linux. Report exact observed events, not an inferred production incident. Changed-line context comes from git diff --unified=3 base head -- src/job_client.py. If no precise causative line is established, label these as changed lines for review; do not invent causal attribution.

All active approved checks run on both versions, even for an unrelated diff. This deliberately prioritizes completeness over optimization for the single-adapter prototype. If an active decision lacks an approved check, aggregate coverage is incomplete.

## 8. Result contract

| Base check | Head check | Per-check result | Meaning |
|---|---|---|---|
| PASS | FAIL | VIOLATION_INTRODUCED | The proposed version newly fails this check |
| FAIL | FAIL | PRE_EXISTING_FAILURE | The failure already existed; do not blame this change |
| FAIL | PASS | RESOLVED | The proposed version resolves this checked failure |
| PASS | PASS | CHECK_PASSED | This approved check passed on both versions |
| ERROR | Any | NOT_CHECKED | Execution did not establish a result |
| Any | ERROR | NOT_CHECKED | Execution did not establish a result |

Aggregate precedence: NOT_CHECKED or POLICY_REVIEW_REQUIRED -> INCOMPLETE; otherwise any VIOLATION_INTRODUCED or PRE_EXISTING_FAILURE -> FAILED; otherwise all covered active checks are CHECK_PASSED or RESOLVED -> PASSED_CHECKS. Zero active approved checks -> INCOMPLETE, never an empty green result. CLI exit codes: PASSED_CHECKS=0, FAILED=1, INCOMPLETE=2; invalid CLI invocation=2.

Every report includes base/head hashes, active decision IDs and text, check/bundle digest, approval and validation provenance, adapter version, observations for each version, changed-line context, warnings, and UTC run time. Human-readable copy says Approved checks passed, never PR safe or All decisions satisfied.

Reports remain valid evidence for their recorded hashes. If selected refs move, the UI compares them with the report and labels the report STALE with Rerun required; it never relabels an old run as current. Staleness is a presentation state and does not rewrite the saved execution outcome.

## 9. Interfaces and browser experience

The CLI provides demo-init, propose, validate, approve, run, and serve. demo-init takes a new empty destination, never destroys an existing checkout. The browser is a small HTML/CSS/JavaScript page served by Python's standard library. No frontend build system is needed.

One page has three views: Decision change, Approve check, and Review change. The default review card shows Ordinary tests, Unique jobs, Approved check, and Governing decision. A timeline underneath shows accepted request, 503 response, repeat submission, and duplicate. Evidence details reveal hashes and records. Use visible text and icons alongside color, clear keyboard focus, and readable contrast.

Actions call the same application functions used by the CLI. GET /api/state returns mode, lifecycle, available scenarios, current draft, validation, approval, and report. POST /api/propose accepts mode=live|recorded. POST /api/validate accepts the current draft digest. POST /api/approve accepts draft digest, reviewer, and reason. POST /api/run accepts a fixture scenario ID, not an arbitrary shell command or repository path.

Require JSON, an application/json Content-Type, a body limit of 64 KiB, and the per-session token from the page for POSTs. Reject non-local Host/Origin values. Serve only the named static assets. These controls prevent unrelated websites from triggering local actions; this remains a local, single-operator demo. Escape decision/model text using textContent in the browser and html.escape in exports.

Live mode, recorded mode, and pending approval are always visible. Disable approval before successful validation, disable overlapping mutations, retain draft/report state across browser reloads in an ignored atomic JSON session file, and display errors as errors. Server mutations are serialized; a second request while an action is running returns 409. Starting without an API key still permits execution and recorded mode.

## 10. Acceptance matrix

| Case | Required result | What it tests |
|---|---|---|
| Old blind retry after approval | VIOLATION_INTRODUCED; 2 jobs | Main behavior |
| Retry implemented through a helper absent from AI inputs | VIOLATION_INTRODUCED; 2 jobs | Behavioral rather than keyword detection |
| Correct reconciliation | CHECK_PASSED; 1 job | Valid implementation |
| Stable service-supported idempotency key | CHECK_PASSED; 1 job | Legitimate exception |
| Unrelated documentation change | CHECK_PASSED; all active checks ran | No invented drift finding |
| Silent abort after 503 | VIOLATION_INTRODUCED; returned_job_exists=false | Avoid passing a duplicate-only check |
| Check deletion or decision change at head | POLICY_REVIEW_REQUIRED; INCOMPLETE | Candidate cannot approve itself |
| Missing/cyclic/disputed governing records | NOT_CHECKED; INCOMPLETE | Missing authority is visible |
| Tampered approval digest | NOT_CHECKED; INCOMPLETE | Approved bytes are the executed bytes |
| Bad behavior already in target and head | PRE_EXISTING_FAILURE | Correct attribution |
| Fixed behavior when target is faulty | RESOLVED | Correct attribution |
| Timeout, import failure, missing Git object | NOT_CHECKED; INCOMPLETE | No false green |
| Ref moves after run | STALE presentation | Evidence stays bound to its run |
| Invalid model JSON/citation or provider outage | Unapproved draft/error | Honest AI lifecycle |

## 11. Business and evaluation

Compare with a realistic baseline: decision record plus ordinary regression tests, Git search, and the team's existing AI reviewer where available. Count time to draft, validate, approve, maintain, and interpret checks. Report case-level outcomes, misses, incorrect warnings, reviewer task times, sample size, and provider costs. Holdout results assess only this adapter and scenario family.

Ask at least three developers unfamiliar with the history to explain the finding and choose an action. Counterbalance equivalent review tasks across baseline and assisted conditions; nobody reviews the identical answer twice as an independent timing comparison. With fewer participants, report individual observations and call the result preliminary. Do not claim statistical significance or the 50% target as achieved without measurements.

The commercial hypothesis is recurring use after incidents and decision changes. Continue toward a product only if developers retain the checks and the saved work exceeds approval and maintenance effort. An existing tool integration may be the better delivery form if standalone adoption is weak.

## 12. Release scope and references

Ship the local engine, real AI proposal evidence, browser demo, synthetic history generator, tests, setup instructions, architecture, pitch, evaluation evidence, and known limitations. Live GitHub/GitLab adapters, arbitrary languages, organization accounts, databases, and Memex are subsequent decisions after the first proof.

The GitHub repository must contain all required source and documentation without relying on D: drive paths. Check source and final claims before pushing. A recorded fallback is clearly labeled and accompanied by a live execution; no screenshot is passed off as a running check.

Primary technical references checked during planning:

- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output): the provider can request a JSON schema; local semantic validation is still required.
- [Gemini text generation](https://ai.google.dev/gemini-api/docs/text-generation): current provider invocation and configuration surface.
- [Python unittest](https://docs.python.org/3/library/unittest.html): standard-library test runner for this small implementation.
- [GitHub Copilot code review](https://docs.github.com/en/copilot/concepts/agents/code-review) and [test generation](https://docs.github.com/en/copilot/tutorials/write-tests): baseline capabilities; generic review and test generation are not novelty claims.

This specification supersedes the original read-only diff-review mechanism for the planned build.
