# Phase 03 Engine Handoff

## Delivered

Implemented `ddg.engine.compare(repo, base, head)` as the shared two-revision runner. It resolves both refs to canonical full SHAs, loads decision/check/validation/approval records only from pinned base, validates the complete decision graph and record paths, checks citations against base decisions, and calls `verify_bundle` before any approved check can execute. Each eligible active approved check runs on both revisions; head policy edits only add a review-required warning and never replace base authority.

Per-check results contain `check_id`, `verdict`, `base`, `head`, `decision`, `check`, `check_digest`, `approval`, `validation`, `diff`, and `error`. The report includes `aggregate`, full `base_sha` / `head_sha`, the checks, `active_decisions` (full base decision records), `{code, message}` warnings, `run_at`, `adapter_version`, and observed `ordinary_tests` for both revisions. The source diff is context for review; it does not assert causal attribution.

Git reports any path changed under `.ddg` (including mode-only changes) as `POLICY_REVIEW_REQUIRED`; observations are retained and the aggregate is `INCOMPLETE`. Missing active-decision coverage, invalid base authority, tampered bundles, missing source, worker failures, timeouts, ordinary-test errors, or unavailable required source diff evidence also produce `INCOMPLETE`. A valid historical check whose schema and path match an existing superseded decision is retained with `HISTORICAL_CHECK_IGNORED` and skipped; its successor still requires its own approved coverage. This preserves historical artifacts without allowing them to govern current behavior.

## Verification

```powershell
python -m unittest tests.test_engine -v
```

Result: **20 tests passed**. The tests cover introduced and holdout regressions, valid exception and unrelated changes, abort behavior, check deletion and policy changes at head, tampered or absent approval, missing/cyclic decisions, uncovered second active decisions, zero checks, historical-check retirement, preexisting and resolved failures, crash/timeout/missing-entrypoint/missing-source errors, path/ID consistency, mode-only `.ddg` changes, missing diff evidence, full hashes, ordinary-test results, and event traces.

I also ran the engine read-only against the actual recorded-proposal `.ddg-demo` using its existing approved base `a14eead32bad9880f042efe5275c4c82ab986dec` and regression `ccdd8eb1f705dd47172ce29781dd19b2f9e2b5c6`. It returned `FAILED` / `VIOLATION_INTRODUCED`, with base=1 unique job, head=2, and ordinary observations `PASS` on both revisions. The demo repository was not modified.

The helper-generated historical-successor test uses a synthetic active root replacement because the current proposal context validator accepts the fixed DEC-001 → DEC-002 predecessor pair. No broader proposal-chain behavior was added in this task. Reports keep historical checks for inspection; they are not executed.

No source files were staged or committed. CLI/report integration and orchestrator acceptance remain outside this handoff.
