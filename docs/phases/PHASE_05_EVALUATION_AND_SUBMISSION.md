# Phase 05 Evaluation and Hackathon Submission

**State:** CODE_VERIFIED_EVIDENCE_PENDING; human evaluation/rehearsal outstanding. **Orchestrator:** GPT 6.1 Sol High. **Executor:** GPT 6 Luna. **Detailed scope:** Task 8 in [the implementation plan](../superpowers/plans/2026-10-03-decision-drift-gate.md).

## Outcome

Deliver verified source, accurate documentation, case-level evidence and a rehearsed live demonstration. Separate technical proof from measured reviewer benefit and commercial hypotheses.

## Entry and ownership

Entry: Phase 04 accepted and all preceding code gates verified. Actual live-provider evidence, participant feedback and source publication must be resolved or explicitly reported outstanding before final submission readiness.

Dispatch ownership: Luna owns `scripts/evaluate.py`, `tests/test_evaluate.py` and its evaluator handoff. Sol owns curated evidence, release documentation, final acceptance, truthful claims, serialized commits and publication within the user's authorized submission scope. Human reviewers/presenter own their observations and rehearsal; agents cannot supply fictional participants.

## Execution checklist

- [x] Implement deterministic acceptance-case evaluation and raw CSV timing fields.
- [x] Run the case matrix with actual verdicts, metrics, revisions and check digests.
- [x] Preserve mismatches/warnings/errors; record expectation-ledger corrections transparently.
- [x] Assemble real model capture, browser evidence and clearly labeled fallback.
- [x] Document setup, tested versions/platforms, architecture, supported adapter and actual limitations.
- [x] Prepare counterbalanced reviewer tasks and a header-only raw-observation template.
- [ ] Collect actual human feedback; no participants have completed the comparison.
- [ ] Rehearse the 45-word pitch five times and the longer walkthrough; record measured durations.
- [x] Inspect tracked source/evidence and verify setup from a fresh GitHub checkout.
- [x] Commit release documentation and complete the reviewed release handoff.
- [x] Publish under the user's implementation/submission authorization; verify remote commit and fresh-clone reproducibility.

## Verification and acceptance

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation
```

Require acceptance results with expected and observed verdicts, full hashes and metrics; no invented timing values; no secret/generated-repository files tracked; valid repository-relative links; fresh-checkout setup; honest model provenance; source matching the verified release commit.

At least three unfamiliar developers are the planned evaluation target. If unavailable, report the actual sample and keep reviewer-benefit evidence pending. The agents may prepare tasks and record user-supplied responses; they must not contact people through messaging tools without explicit authorization.

Sol accepts final delivery only after reviewing the evidence and distinguishing completed code, live demo readiness, human evaluation, and remote publication. If one is incomplete, record exactly which and why. Do not describe the 50% target as achieved without measurements.

## Final handoff

Include tested commit and remote commit, setup/run commands, evaluation outcome summary, actual live/recorded mode, projector demo instructions, rehearsal observations, and residual limitations. Link the source and documents the judges can inspect. The final pitch makes only claims supported by this handoff.
