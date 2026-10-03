# Phase 01 Runner Handoff

## Delivered

Implemented the trusted fake service and behavioral runner in `ddg/harness.py` and its fresh-process entry point in `ddg/worker.py`. The runner validates a structured check before reading or executing target code, resolves the requested revision to a full commit SHA, extracts only `src/job_client.py` into a temporary directory, and starts a new Python subprocess with a small allowlisted environment. The child imports the snapshot and trusted fake-service harness; target stdout is redirected away from the one-line JSON result protocol. Parent capture and worker stdin/stdout use UTF-8 explicitly, including a regression for non-ASCII diagnostics.

The fake service models `commit_then_503`, `reject_then_503`, and no-fault operation. Operation IDs alone do not deduplicate; a supplied stable idempotency key does. Worker, Git, unsupported import, malformed output, and timeout errors return `ERROR` with unavailable metrics as `null`. A valid execution that fails an assertion or returns no existing job ID returns `FAIL`. Although the check schema allows `returned_job_exists=false`, execution still requires a real returned job ID; a check drafted to expect a missing result therefore fails on known-good calibration and cannot be approved. `observe_happy_path` runs the same target module against the no-fault service.

Static vocabulary checks reject non-standard imports and dynamic import/execution mechanisms such as `importlib`, `runpy`, `__import__`, `eval`, and `exec`. This is a boundary check for the trusted synthetic module in this prototype; process separation and import restrictions do not provide a malicious-code sandbox.

Added the disclosed manual CHK-001 example and runner tests. The exact test command and current result are:

```powershell
python -m unittest tests.test_harness -v
```

Result: **14 tests passed** in the final runner suite. RED/GREEN evidence: the UTF-8 regression initially raised `UnicodeEncodeError`; the dynamic-import fixture initially returned `PASS`; and malformed list/dict statuses initially raised `AttributeError`. Each passed after the corresponding fix. Assertions establish the main behavior: blind retry returns `FAIL` with 2 unique jobs; reconciliation and stable-key retry return `PASS` with 1 job; silent abort returns `FAIL` with `returned_job_exists=false`; ordinary no-fault submission passes on the bad implementation; crashes, timeouts, missing entrypoints, unsupported imports, and dynamic imports return `ERROR`; provider keys are absent from the worker environment; malformed statuses and metric types return `ERROR`; and non-ASCII diagnostics survive the worker JSON protocol as UTF-8. The service tests also establish that reject-before-commit returns no first job, and that a second create without a key creates a second job.

The shared Phase 01 set was also run:

```powershell
python -m unittest tests.test_harness tests.test_contracts tests.test_gitio tests.test_demo -v
```

Runner and contracts tests passed. At that run, two failures remained outside runner-owned files: `tests.test_gitio.GitReadTests.test_missing_path_and_diff_are_safe` expected the Git helper's diff to omit `.ddg/decisions`, and `tests.test_demo.DemoTests.test_builds_named_sha1_refs_and_policy_history` expected DEC-002's rule text to contain “silently abandoning.” These were reported to the orchestrator for routing to the file owners.

## Interface

```python
FakeService(scenario="commit_then_503")
observe(repo: Path, sha: str, check: dict, timeout: float = 10) -> dict
observe_happy_path(repo: Path, sha: str, timeout: float = 10) -> dict
```

Both observations expose `status`, `unique_jobs`, `returned_job_exists`, `returned_job_id`, `submit_calls`, `events`, and `error`. The fixture references supplied by `build_demo` are full commit SHAs; `observe` resolves the input once more before the pinned read.

No source commit was created, as requested by the orchestrator. This handoff records runner verification only; the remaining shared test failures and orchestrator review still gate Phase 01 acceptance.
