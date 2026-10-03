# Phase 04 server handoff

## Delivered

`ddg.web.create_server(repo, state_dir, port=8765)` binds to `127.0.0.1` and serves only `/`, `/app.js`, `/style.css`, and `/api/state`; its POST routes are `/api/propose`, `/api/validate`, `/api/approve`, and `/api/run`. It injects a per-server token into the `ddg-session-token` meta element and requires `X-DDG-Session` for mutations. State and successful action responses use `{"state": ...}`; boundary errors use `{"error": ...}` with an HTTP status.

The server enforces local Host/Origin checks, JSON-only requests, a 64 KiB body limit, a fixed scenario allowlist, and a nonblocking mutation lock. Session writes are atomic and kept outside `.ddg`; tokens and environment secrets are never persisted. Startup verifies approved artifacts from the pinned `approved_base` and hydrates the session from the repository when no valid session snapshot exists. Restored state must match the verified proposal, decision, and approval. Report freshness is recomputed against the selected live ref names.

POST bodies are `{"mode":"recorded|live"}`, `{"draft_digest":"..."}`, `{"draft_digest":"...","reviewer":"...","reason":"..."}`, and `{"scenario":"<allowlisted-id>"}` respectively. Scenario IDs are `regression`, `unseen_regression`, `corrected`, `exception`, `unrelated`, `abort`, `crashing`, `timing_out`, `missing_entrypoint`, `policy_edit`, `preexisting_failure`, and `resolved`.

## Verification

- TDD red: before `ddg/web.py` existed, `python -m unittest tests.test_web -v` failed at import with `ModuleNotFoundError: No module named 'ddg.web'`.
- Green: `.venv\Scripts\python.exe -m unittest tests.test_web -v` — 9 tests passed in 50.507 seconds after the final server recovery and rejection-body handling checks. These exercise real HTTP requests, the full recorded lifecycle to a `FAILED` report, persistence/restart/tamper recovery, stale refs, body limits, token/Host/Origin boundaries, conflict behavior, and a generic `CHK-002` approved bundle. Rejected modest request bodies are drained under a short socket timeout so clients can receive the structured rejection; bodies above the bounded drain limit close the connection without an unbounded read.
- `.venv\Scripts\python.exe -m unittest tests.test_engine -v` — 20 tests passed as part of the combined 28-test web/engine run (91.950 seconds); web recovery changes made after that combined run were separately verified by the full web suite above.
- Repeated rejection-boundary check: `.venv\Scripts\python.exe -m unittest tests.test_web.WebServerTests.test_missing_token_external_origin_and_external_host_are_rejected -v` — passed; the missing-token POST is sent three times and each receives 403.
- `.venv\Scripts\python.exe -m unittest tests.test_web.WebServerTests.test_state_directory_inside_governed_records_is_rejected_before_writes -v` — passed.
- `.venv\Scripts\python.exe -m py_compile ddg/web.py` and `git diff --check` — passed.

The server tests use only the recorded proposal fixture and synthetic Git repositories; they make no provider calls. Browser inspection and visual/accessibility evaluation remain with the orchestrator/frontend phase gate. No files were staged or committed by this worker.

## Frontend/API contract

The UI can read `/api/state` for `mode`, `lifecycle`, `old_decision`, `new_decision`, `draft`, `validation`, `approval`, `report`, `report_stale`, `scenarios` (`{id,label}` records), and `busy`. The session token is in `<meta name="ddg-session-token" content="...">`. Mutations serialize; a concurrent action returns 409. Approval before successful validation, or with a stale draft digest, returns 409. Unknown scenarios return 400; missing/wrong token or external Host/Origin returns 403; oversized bodies return 413.

Each live provider interaction has a hard 30-second caller deadline that also bounds SDK retries from the browser's perspective. A timed-out provider worker cannot publish a late proposal or mutate session state; the action returns a sanitized timeout error and does not fall back to recorded mode.

## Quick start

```powershell
python -m ddg serve --repo .ddg-demo --state-dir .ddg-state
```

The server prints its loopback URL. Use an approved demo marker for Review; a fresh demo can go through recorded proposal, validation, and explicit approval before running scenarios. Live proposal mode requires the existing project `.env` and provider configuration. No browser run was performed as part of this server-only handoff.
