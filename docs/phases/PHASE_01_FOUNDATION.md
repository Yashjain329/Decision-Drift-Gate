# Phase 01 Foundation and Behavioral Proof

**State:** ACCEPTED; see [verified handoff](handoffs/PHASE_01.md). **Orchestrator:** GPT 6.1 Sol High. **Executor:** GPT 6 Luna. **Detailed scope:** Tasks 1 and 2 in [the implementation plan](../superpowers/plans/2026-10-03-decision-drift-gate.md).

## Outcome

Create a synthetic Git history and a real runner that shows blind retries create two jobs, while reconciliation and a stable idempotency key create one. This phase proves behavior without a live model or browser.

## Entry and ownership

Entry: execution is requested, the repository is inspected, and the design/common contracts are supplied to Luna.

Luna owns `ddg/__init__.py`, `ddg/gitio.py`, `ddg/demo.py`, `ddg/contracts.py`, `ddg/harness.py`, `ddg/worker.py`, `tests/__init__.py`, `tests/support.py`, `tests/test_gitio.py`, `tests/test_demo.py`, `tests/test_contracts.py`, `tests/test_harness.py`, `examples/manual_check.json`, `.gitignore`, and `docs/phases/handoffs/PHASE_01.md`. Required references are the [design](../superpowers/specs/2026-10-03-decision-drift-gate-design.md) and Tasks 1-2 of the detailed plan.

## Execution checklist

- [ ] Inspect Python/Git versions and working-tree state; preserve existing planning work.
- [ ] Implement Task 1's fixed-revision reads, path handling, empty-destination guard, synthetic decisions and fixture history.
- [ ] Implement Task 2's strict check schema, both required metrics, fake service, isolated worker and observable traces.
- [ ] Keep manual examples labeled manual and provider-independent.
- [ ] Run the targeted tests and inspect bad/good/exception observations.
- [ ] Commit the two independently testable task deliveries and write the actual handoff.

## Verification and acceptance

```powershell
python -m unittest tests.test_gitio tests.test_demo -v
python -m unittest tests.test_contracts tests.test_harness -v
```

Require pinned reads despite moved refs; refusal to overwrite existing content; Windows paths with spaces; explicit supersession records; duplicate case FAIL with two jobs; reconciliation and exception PASS with one job; silent abort FAIL; malformed check refusal; timeout/crash/missing entrypoint ERROR rather than PASS.

Sol reviews revision pinning, actual service semantics, subprocess environment, and whether assertions measure behavior instead of matching code text. Sol checks that generated fixtures/temp data are ignored and no unrelated files changed.

## Handoff to Phase 02

Provide the accepted commits, function signatures, check schema/adapter version, fixture refs and observed outcomes. Phase 02 extends the same contracts and fixtures; it must not replace them with mocks or hardcoded outcomes.

Phase completion is behavioral evidence only. It does not establish that AI generated a check or that the product saves review time.
