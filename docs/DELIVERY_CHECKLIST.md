# Decision Drift Gate Team Delivery Checklist

**Date:** 3 October 2026. **Next-round deliverables confirmed by user:** live demo, documentation, GitHub source. **Deadline and team size:** not supplied; sequence work through the gates below.

## Definition of done

- [ ] A fresh checkout can build the synthetic history and start the local browser using documented commands.
- [ ] A real AI call has produced a schema-valid, grounded proposal; its sanitized capture and input digest are inspectable.
- [ ] A developer explicitly approves the exact check after bad/good/exception calibration.
- [ ] The blind-retry and unseen helper-based regressions fail; reconciliation and stable-key exception pass.
- [ ] Silent abort fails; unapproved policy changes and missing authority produce incomplete results.
- [ ] The report separates newly introduced, preexisting, and resolved failures.
- [ ] Ordinary-test badges are based on real execution, and reports include exact revisions and check identity.
- [ ] The fast reveal is fresh execution with a previously approved check, labeled honestly.
- [ ] The longer walkthrough shows proposal, validation, approval, and execution.
- [ ] Offline mode runs approved checks and labels recorded proposal provenance.
- [ ] Standard-library tests and the browser walkthrough pass on the presentation machine.
- [ ] Documentation states supported adapter, limitations, measured outcomes, and actual tested versions.
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

Before publishing implementation, inspect git status and remote, review tracked artifacts, run the documented checks, and rehearse from a fresh checkout. Verify the remote commit after a push. The source repository currently contains planning work; application completion and remote publication remain outstanding.

## If schedule pressure appears

Preserve the behavioral runner, real AI proposal evidence, approval, valid exception, unseen variation, and exact provenance. Simplify visual polish and extra adapters first. Do not replace the engine with a narrated mockup or describe a recorded model output as a fresh call. A smaller working claim is easier to defend in judging.
