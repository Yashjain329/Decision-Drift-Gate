# Human evaluation and pitch rehearsal

No human comparison results or measured speaking durations have been collected. Automated behavioral cases establish the prototype's execution behavior; they do not establish saved review time.

## Reviewer comparison

Recruit at least three developers who did not implement the demo. Each reviews equivalent variants in both baseline and assisted conditions. Baseline includes ordinary tests, linked decisions and Git inspection; record any existing AI reviewer used. Assisted adds Decision Drift Gate. Alternate condition order across reviewers and variants to reduce memorization.

Before timing, record participant/task assignment and the expected verdict in a separate facilitator sheet. Give each reviewer the same questions: which rule governs this change, what happened, and what action should the reviewer take? Score verdict and reason separately. Measure setup, generation/calibration/approval and review time separately; count maintenance work when comparing cost.

Use [the raw-observation template](../evidence/reviewer-observations.csv). It contains headers only. Do not fill it with simulated participants or inferred times. Report sample size, individual observations and failures before making a percentage-saving claim.

## Pitch rehearsal

Use [the pitch and demo script](PITCH_AND_DEMO.md). Start with an honestly disclosed previously approved check, then execute a fresh regression comparison during the reveal. Have the recorded proposal fallback ready, with mode visible. Rehearse the longer live generation/calibration/approval lifecycle separately.

Run five timed speaking rehearsals. Record actual durations, readability of the failure card, execution delay and any operator intervention. Target 18–22 seconds for the opening and approximately 90 seconds for the lifecycle. Word count and automated execution time are not measured speaking time.

| Attempt | Speaking seconds | Fresh run visible | Failure card readable | Notes |
|---|---|---|---|---|
| 1 | Pending | Pending | Pending | |
| 2 | Pending | Pending | Pending | |
| 3 | Pending | Pending | Pending | |
| 4 | Pending | Pending | Pending | |
| 5 | Pending | Pending | Pending | |

Publication of source and documentation does not complete these external evaluation steps. Preserve their pending status until someone actually performs them.
