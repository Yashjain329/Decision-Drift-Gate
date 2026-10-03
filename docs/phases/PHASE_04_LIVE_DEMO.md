# Phase 04 Live Browser Demonstration

**State:** PLANNED. **Orchestrator:** GPT 6.1 Sol High. **Executor:** GPT 6 Luna. **Detailed scope:** Task 7 in [the implementation plan](../superpowers/plans/2026-10-03-decision-drift-gate.md).

## Outcome

Let judges see the decision change, AI proposal, validation, approval and a freshly executed code review in a clear local browser interface.

## Entry and ownership

Entry: Phase 03 accepted and its CLI/engine/report contracts reproducible. Live-provider evidence from Phase 02 remains a release dependency even if browser development can use an explicitly labeled capture.

Luna owns `ddg/web.py`, `web/index.html`, `web/app.js`, `web/style.css`, `tests/test_web.py`, README browser setup, and `docs/phases/handoffs/PHASE_04.md`. Engine/contract changes require Sol's direction; do not silently fork them for UI convenience.

## Execution checklist

- [ ] Build the local named-asset server and specified JSON routes backed by the existing functions.
- [ ] Implement per-session action token, local Host/Origin checks, body limits, serialized mutation and atomic session state.
- [ ] Implement Decision change, Approve check and Review change views.
- [ ] Show draft/capture mode, validation, approval identity and stale state explicitly.
- [ ] Display real ordinary-test results, expected/observed job count, service timeline and governing decision.
- [ ] Inspect full lifecycle, action errors, refresh persistence, keyboard access and projector-size layout in a real browser.
- [ ] Verify fresh fast reveal and longer walkthrough, commit the delivery and write the handoff.

## Verification and acceptance

```powershell
python -m unittest tests.test_web -v
python -m ddg demo-init --destination .ddg-demo
python -m ddg serve --repo .ddg-demo --state-dir .ddg-state
```

The destination must be new/empty; use another explicit task-owned destination if a demo already exists. Do not delete or reset an existing checkout merely to run these commands.

Require actual API lifecycle -> FAILED on regression; 409 on premature approval/busy mutations; 403 on missing token/external origin; 400 on unknown scenario; 413 on oversized body; stale-draft refusal; safe text rendering; honest live/recorded labels; persistent non-secret state; no fabricated badges.

Sol reviews the browser against the [pitch/demo script](../PITCH_AND_DEMO.md), independently observes a fresh execution, and checks readable no-scroll reveal at 1366x768. Captured screenshots are evidence of inspected behavior, not substitutes for a working demo.

## Handoff to Phase 05

Provide server startup/shutdown instructions, actual browser observations/screenshots, live/recorded availability, known usability limits, accepted commit and measured local run duration if collected. Phase 05 performs timed rehearsal and evaluation; do not invent these measurements here.
