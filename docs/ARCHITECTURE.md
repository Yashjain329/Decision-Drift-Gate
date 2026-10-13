# Decision Drift Gate architecture

This document describes the design as built on `master` (12 October 2026). The original prototype design is in [the design specification](superpowers/specs/2026-10-03-decision-drift-gate-design.md); [phase status](phases/STATUS.md) keeps its verification record.

A model (or a developer) proposes a check once. A developer calibrates and approves that exact proposal. Subsequent review results come from executing the approved check against fixed Git revisions; they do not require a model call.

```mermaid
flowchart TD
    D[Versioned old and replacement decisions] --> P[Model provider, disclosed prior capture, or manual check]
    S[Corrected source and bounded vocabulary] --> P
    P --> C[Strict schema and exact citations]
    C --> V[Bad, good and exception calibration]
    V --> A[Explicit developer approval]
    A --> B[Check, validation and approval committed at target]
    B --> I[Verify approver identity from Git history and base approvers file]
    I --> E[Read authority from pinned target revision]
    E --> AD[Adapter registry picks the observer]
    AD --> R[Fresh container for each code revision]
    R --> O[Observed results held in the runner process]
    O --> F[Two-version verdict and reproducible report]
    F --> U[Shared CLI and local browser]
```

## Authority and evidence

The target revision supplies decisions, checks, validation and approval. The proposed revision supplies the code being reviewed. Changes to policy at the proposed revision require policy review and make aggregate coverage incomplete; they cannot silently remove an existing check.

Canonical UTF-8 JSON and SHA-256 bind the check, governing decision, adapter version and validation. The approval record keeps a reviewer name and reason, but the name is only text. Who approved is decided from Git history; see [Approver identity](#approver-identity). The containing approval commit is recorded externally because a commit cannot contain its own final hash.

Proposal provenance records mode, provider, model, client version, time limit, capture time and source revision separately from its input-content digest. A real capture can be replayed only when the old/new decisions, corrected source and vocabulary match. Replay is labeled Recorded. A handwritten sample is labeled Manual.

## Bounded adapter

The first adapter runs trusted synthetic `src/job_client.py` with `submit_job(service, payload, operation_id)`. The fake service can create a job before returning 503, or reject it before creating one. Checks observe unique jobs and whether the returned ID actually exists. Completion is mandatory: avoiding duplicates by abandoning the operation does not pass.

Each revision executes in a fresh worker with a fresh service and a timeout. Unsupported source, missing entrypoints, crashes and malformed child output are errors. Model credentials are excluded from child environments. The fake service and all recorded events live in the runner process; the worker reaches it only through a JSON-line proxy (`ddg/worker.py`), so the revision under test cannot edit the evidence (regression-tested in `tests/test_harness.py`). A static screen rejects filesystem, process and network modules and `open`/`eval`/`exec`. That screen is best-effort and is not a security boundary; the container (below) is.

## Git layer

All Git reads go through `ddg/gitio.py`. Every call disables repository-local code execution (hooks, fsmonitor, pagers, external diff, textconv, gpg programs). Revisions are full SHA-1 ids; SHA-256 repositories are rejected. File reads accept only regular files read by object id: symlinks, submodules and directories are refused, and `list_at` fails when it finds one under a prefix. Output is decoded as strict UTF-8 with line endings preserved. Shallow clones fail closed when approval history is needed. History walks use `--full-history` so a side-branch edit cannot hide behind a merge. Diffs are capped at 204,800 bytes for display, with a visible marker.

## Adapters

`ddg/adapters/__init__.py` holds a registry of modules. Each adapter module must define `NAME`, `validate_body`, `source_path`, `observe`, `ordinary` and `expected_case`; the registry refuses to import an adapter that lacks one. The engine collects the adapter names a run uses, and the adapter id is part of the approval digest.

| Adapter | Module | Observes |
|---|---|---|
| `python_job_client_v1` | `ddg/adapters/job_client.py`, runs `ddg/harness.py` | Jobs created and returned by `submit_job` in `src/job_client.py` against a fake service |
| `python_function_v1` | `ddg/adapters/python_function.py`, runs `ddg/worker_function.py` | Return value or exception type of one named function in one Python module that imports only pure standard-library modules: no `os`, `sys`, `subprocess`, `pathlib`, `io`, `tempfile`, network or process modules, and no `open`, `eval` or `exec`, for JSON arguments (up to 50 cases) |

Model proposals support only `python_job_client_v1`. Checks for `python_function_v1` are written by hand. For `python_function_v1` the observation is the function's own output, so it detects accidental regressions but cannot detect a revision that fabricates the expected answers.

## Sandbox

`ddg/sandbox.py` starts every worker. `DDG_SANDBOX` is `auto` (try Docker, then Podman), `docker`, `podman` or `host`. With no usable runtime, the run fails closed: the observation is an error and the verdict is NOT_CHECKED. `host` runs the worker as a plain subprocess with a small environment allowlist, and reports mark it UNSAFE.

The container uses no network, a read-only root, all capabilities dropped, `no-new-privileges`, a 64-process limit, 128 MB memory, 0.5 CPU and the user `65534:65534`. Source and worker are mounted read-only; `/tmp` is a 16 MB `noexec` tmpfs. The container is removed on timeout and on every other exit path. The image comes from `DDG_SANDBOX_IMAGE` (default `python:3.12-slim`). See the [threat model](THREAT_MODEL.md) for what this does not cover.

## Approver identity

`ddg/identity.py` reads `.ddg/approvers.json` from the **base** revision. The file has exactly `schema_version` (1), `require_signed` (boolean) and `approvers` (non-empty list of emails). For each approved check, the engine lists every commit that touched its check, validation and approval files, and requires for each commit:

- the author email is in `approvers` (case-insensitive);
- the commit changed only paths under `.ddg/checks/`, `.ddg/validations/` and `.ddg/approvals/`;
- if `require_signed` is true, Git reports signature status `G`.

A failure adds an `APPROVER_NOT_VERIFIED` warning and makes the aggregate INCOMPLETE. Missing history (a shallow clone) also fails. With no policy file, the run fails unless `DDG_ALLOW_UNVERIFIED_APPROVERS=1`. The identity of the approver is evidence in the report. This is as strong as the signing setup: author email alone can be forged.

## Model providers

`ddg/providers/` turns a prompt into raw text; `ddg/proposal.py` does everything else (strict schema, exact citations, one repair attempt, a hard wall-clock deadline in a daemon thread). Providers: `gemini_api`, `anthropic_api`, `openai_api` (including OpenAI-compatible servers), `bedrock`, `claude_cli`, `codex_cli`, `custom_cli`. The draft records provider, model, client version and the timeout used (1 to 600 seconds; default 30 for APIs, 180 for CLI agents). Old recorded drafts without a provider field remain valid. See [PROVIDERS.md](PROVIDERS.md).

## Command line and CI

`ddg` (or `python -m ddg`) exposes `init`, `demo-init`, `propose`, `providers`, `validate`, `approve`, `run`, `status` and `serve`. `run` returns 0 (passed), 1 (failed), 2 (incomplete) or 3 (usage or infrastructure error). `action.yml` wraps `ddg run` for pull requests and `scripts/pr_comment.py` renders the report as one upserted PR comment.

## Result semantics

| Target | Proposed | Result |
|---|---|---|
| Pass | Fail | Violation introduced |
| Fail | Fail | Preexisting failure |
| Fail | Pass | Resolved |
| Pass | Pass | Approved check passed |
| Error | Any | Not checked |
| Any | Error | Not checked |

Missing authority, uncovered active decisions, policy edits, unverifiable approvers, unreadable history and execution errors make the aggregate incomplete. The engine also rebuilds each check's proposal inputs from the base decision records and requires them to match the recorded input digest, so an edit to the superseded predecessor decision is caught. Otherwise an introduced or preexisting failure makes it failed. A passed aggregate means the covered approved checks passed for the recorded revisions.

All active approved checks run on both revisions, including unrelated changes. For the job adapter, ordinary happy-path tests also execute and their badge is derived from observations; reports for function-adapter-only runs have an empty `ordinary_tests`. Changed lines provide review context rather than a claim of exact causal attribution.

## Local application

Python's standard library supplies Git orchestration, tests, subprocess execution, JSON persistence and the local HTTP server. Plain HTML, CSS and JavaScript display the same application functions as the CLI. The Gemini SDK (`[ai]`) and boto3 (`[bedrock]`) are optional dependencies used only by those providers; the other providers use the standard library.

The browser binds to loopback, uses a session action token and local-origin checks, bounds request bodies and serializes mutations. Session state and generated demo repositories are ignored by source Git. The source repository contains the fixture generator, not nested generated Git histories.

Live interactions have a caller deadline equal to the provider time limit (30 seconds by default) in addition to network timeouts. A daemon worker transfers only a result or exception through a queue; a late response cannot create a proposal or mutate session state. The caller may make one repair interaction after invalid schema/citations. Provider failures are sanitized and require explicit Recorded selection rather than automatic fallback.
