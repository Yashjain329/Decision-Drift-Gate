# Decision Drift Gate Team Delivery Checklist

**Updated:** 4 October 2026. **Next-round deliverables confirmed by user:** live demo, documentation, GitHub source. **Deadline and team size:** not supplied. [Phase status](phases/STATUS.md) distinguishes technical delivery from pending human rehearsal/evaluation.

## Definition of done

- [ ] A fresh checkout can build the synthetic history and start the local browser using documented commands.
- [x] A real AI call produced a schema-valid grounded proposal; sanitized capture and input digest are inspectable. A later browser Live retry timed out honestly.
- [x] Explicit exact-check approval workflow verified after bad/good/exception calibration, using a labeled Codex integration attestation. A presenter should review the check and supply their own attestation in their fresh walkthrough.
- [x] Blind-retry and unseen helper regressions fail; reconciliation and stable-key exception pass.
- [x] Silent abort fails; policy edits, missing authority and forged approvals remain incomplete.
- [x] The report separates newly introduced, preexisting, and resolved failures.
- [x] Ordinary-test badges come from real execution; reports include exact revisions and check identity.
- [x] Fast reveal executes fresh with an honestly disclosed previously approved check.
- [x] Actual browser walkthrough verified proposal, validation, approval and execution. Timed speaking/video rehearsal remains pending.
- [x] Offline generation/execution work with explicit Recorded provenance.
- [x] Standard-library suite passes: 110 tests in 280.603 seconds. Actual browser walkthrough verified on this Windows machine; recheck the final presentation machine if different.
- [x] Documentation states supported adapter, limitations, actual case outcomes and tested versions.
- [ ] Source and documentation are present in the configured GitHub repository and reproducible from its remote commit.

## Ownership

| Role | Owns | Concrete handoff |
|---|---|---|
| Engine developer | Git, harness, authority, verdicts | Case matrix and reports |
| AI/workflow developer | Proposal, calibration, approval | Real proposal capture and approved bundle |
| Decision reviewer | Rule intent and exceptions | Approval reason and known-good/bad expectations |
| Demo developer | Local browser and state | Fresh executable reveal and usable evidence drawer |
| Evaluator | Unseen cases and reviewer comparison | Raw outcomes/timings and interpretation |
| Presenter/release owner | Pitch, docs, repository | Rehearsed story and reproducible submission |

Roles can be shared. An unseen implementation should be authored or selected without showing it to the proposal generator. Evaluation should involve someone who did not write the demo.

## Evaluation record

Record case_id, expected_verdict, observed_verdict, base_sha, head_sha, check_digest, base_metrics, head_metrics, and error. A missed regression and an incorrectly rejected valid change are both visible failures, even if the main demo looks good.

For reviewer comparison, record reviewer_id, condition, task_id, order, setup_seconds, review_seconds, correct_verdict, correct_reason, and notes. Compare with normal tests, linked decisions, Git search, and the team's existing AI reviewer when available. Use equivalent tasks in counterbalanced order to reduce answer memorization. Include time spent drafting, validating, and maintaining the check.

The original 50% reduction is a target. Publish raw times/sample size and preliminary observations before a general saving claim. No participant counts, measured results, provider costs, or willingness-to-pay claims are invented.

The independent automated matrix matched all 15 expected outcomes on clean source `c3feee81c6403361e449ec677accf97a7e27d899`. [Raw case evidence](../evidence/case-results.json) preserves errors and warnings. Human sample size is zero; the reviewer CSV has headers only, and five speaking rehearsals/video recording remain pending.

## Required repository documentation

| Document | Must answer |
|---|---|
| README | What is it, what is actually built, how to run it, what does it cover? |
| Architecture | Where do AI, developer approval, executable checks, and Git authority fit? |
| Design and plan | What were the agreed behavior and release gates? |
| Evaluation | Which cases passed/failed, what was held out, what was measured? |
| Pitch/demo script | What should judges see in 20 seconds and the longer walkthrough? |
| Evidence index | Where did captures/screenshots/results come from, and which are live/recorded/manual? |

The older submission DOCX reflects the earlier planning conversation. Before reusing it for this round, compare its claims with actual implementation and results. Editing/exporting that Word artifact is separate from this Markdown planning update.

## Source and GitHub submission

Target: [Yashjain329/Decision-Drift-Gate](https://github.com/Yashjain329/Decision-Drift-Gate).

Keep source, synthetic fixture generator, tests, documentation, and sanitized evidence. Ignore .env, provider keys, generated nested Git repositories, temporary snapshots, session tokens, and raw local output directories. An API key is setup configuration and is never required merely to rerun an approved check.

The implementation, fixture generator, browser, tests and documentation are built. Final source checks and remote reproduction are recorded in the release handoff. Verify the remote commit after publication; neither a source push nor automated tests completes human evaluation or pitch rehearsal.

## If schedule pressure appears

Preserve the behavioral runner, real AI proposal evidence, approval, valid exception, unseen variation, and exact provenance. Simplify visual polish and extra adapters first. Do not replace the engine with a narrated mockup or describe a recorded model output as a fresh call. A smaller working claim is easier to defend in judging.
