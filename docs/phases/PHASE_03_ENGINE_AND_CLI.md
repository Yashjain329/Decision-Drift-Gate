# Phase 03 Review Engine and Command Line

**State:** ACCEPTED; see [verified handoff](handoffs/PHASE_03.md). **Orchestrator:** GPT 6.1 Sol High. **Executor:** GPT 6 Luna. **Detailed scope:** Tasks 5 and 6 in [the implementation plan](../superpowers/plans/2026-10-03-decision-drift-gate.md).

## Outcome

Run the target's approved checks against both target and proposed code, distinguish new/preexisting/resolved failures, and produce reproducible reports through a real CLI.

## Entry and ownership

Entry: reviewed Phase 02 interfaces and usable approved artifacts. Phase 02 is normally accepted; a documented offline-work exception may apply when only external live evidence is pending.

Luna owns `ddg/engine.py`, `ddg/report.py`, `ddg/cli.py`, `ddg/__main__.py`, `tests/test_engine.py`, `tests/test_cli.py`, README quickstart updates, and `docs/phases/handoffs/PHASE_03.md`. Luna may extend `ddg/gitio.py`, `tests/support.py`, and fixture construction for the assigned cases while preserving prior gates.

## Execution checklist

- [ ] Implement authority validation from the pinned base and run all active approved checks.
- [ ] Implement policy-edit, uncovered-decision and invalid-approval incomplete results.
- [ ] Implement the full two-version verdict table and aggregate precedence.
- [ ] Produce real ordinary-test observations, event traces, changed-line context and exact provenance.
- [ ] Implement CLI lifecycle commands, JSON/Markdown reports and exit codes.
- [ ] Mark moved-ref reports stale without altering saved execution evidence.
- [ ] Run the case matrix and CLI integration tests, commit task deliveries and write the actual handoff.

## Verification and acceptance

```powershell
python -m unittest tests.test_engine tests.test_cli -v
python -m unittest discover -s tests -v
```

Require new regression and helper-based holdout -> VIOLATION_INTRODUCED; valid exception and unrelated change -> CHECK_PASSED; silent abort -> failure; base/head both bad -> PRE_EXISTING_FAILURE; corrected head against bad base -> RESOLVED; authority change or missing evidence -> INCOMPLETE; crash/timeout -> NOT_CHECKED; no approved checks -> INCOMPLETE; CLI codes 0/1/2; moved refs -> stale.

Sol reviews that a head change cannot approve or remove its own governing check, checks are never selected away by AI, and report text does not call a passing PR safe. Verify the ordinary-test badge is executable evidence, not static copy.

## Handoff to Phase 04

Provide runnable commands, case/ref mapping, stable report envelopes, known failure messages, accepted commits and sample reports. Phase 04 must call these same functions; it must not create a separate browser verdict engine.
