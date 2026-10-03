# Phase 02 AI Proposal and Developer Approval

**State:** PLANNED. **Orchestrator:** GPT 6.1 Sol High. **Executor:** GPT 6 Luna. **Detailed scope:** Tasks 3 and 4 in [the implementation plan](../superpowers/plans/2026-10-03-decision-drift-gate.md).

## Outcome

Turn the recorded rule change into a grounded AI proposal, validate it on calibration fixtures, and obtain a developer approval bound to the exact check/decision/validation bytes.

## Entry and ownership

Entry: Phase 01 accepted, its interfaces/check vocabulary stable, and its handoff reviewed. Provider access is a separate live-evidence prerequisite; offline code can be developed without it.

Luna owns `ddg/proposal.py`, `ddg/approval.py`, `requirements-ai.txt`, `tests/test_proposal.py`, `tests/test_approval.py`, and `docs/phases/handoffs/PHASE_02.md`. Luna may extend `ddg/contracts.py`, `ddg/demo.py`, `tests/support.py`, and relevant predecessor tests to implement Tasks 3-4 while preserving accepted behavior. Sanitized real capture files are written only after a real call and under an orchestrator-approved evidence path.

## Execution checklist

- [ ] Read Phase 01's real interfaces and implement the provider envelope, strict citations and input-content digest.
- [ ] Implement live and recorded modes with visible provenance, bounded failure handling and no silent fallback.
- [ ] Keep holdout source and expected answers outside the provider inputs.
- [ ] Implement calibration and rejection of weak, edited, unsupported or failed drafts.
- [ ] Bind approval to check, active decision, validation and adapter version; avoid circular commit hashes.
- [ ] Activate review branches only through the explicit generated-demo action; refuse ordinary/dirty repositories.
- [ ] Verify live proposal separately, pin the tested optional SDK, and preserve sanitized metadata.
- [ ] Commit task deliveries and provide the actual handoff.

## Verification and acceptance

```powershell
python -m unittest tests.test_proposal tests.test_approval -v
python -m unittest tests.test_gitio tests.test_demo tests.test_contracts tests.test_harness -v
```

Require schema/citation refusal; provider errors that leave a draft unapproved; recorded input mismatch refusal; unsupported decisions; cycle/missing predecessor/competing successor handling; bad FAIL/good PASS/exception PASS calibration; required completion assertion; invalidation after edits; reviewer/reason requirement; exact bundle digest; restricted demo commits; usable approved-base and review refs.

Sol reviews actual model inputs and grounded response, calibration semantics, immutable approval bytes, and demo activation. The execution agent label GPT 6 Luna is distinct from the Gemini provider used by the application; record both accurately.

## External evidence and handoff

ACCEPTED requires at least one real model proposal with matching inputs, capture time and model/SDK provenance. If credentials or provider access are unavailable, record CODE_VERIFIED_EVIDENCE_PENDING after Sol verifies the code. Sol can permit dependent offline engine work, but cannot declare live AI capability demonstrated.

Give Phase 03 accepted interfaces, approval/bundle layout, live/recorded state, fixture mappings and delivered commits. Never let a manually authored example become claimed AI evidence.
