# Evidence provenance

`gemini-proposal.json` is a sanitized capture from a real Gemini call on synthetic Decision Drift Gate inputs. It is not a handwritten fixture.

- Provider model: `gemini-3.8-flash`.
- SDK: `google-genai` version `2.28.0`.
- The capture records its actual UTC time, source revision, input-content digest, accepted check and proposal fingerprint.
- Gemini selected `commit_then_503`, expecting one unique job and an existing returned job ID, with exact DEC-002 citations.
- API keys, request headers and raw SDK exceptions are excluded.

Use the application’s Recorded mode to replay this capture only when current input content matches. Recorded generation is disclosed; subsequent approved-check execution is fresh. Live mode makes a new provider request. A source revision from the original generated repository is provenance, not a claim that this SHA belongs to the source-code repository.

## Automated case matrix

[case-results.json](case-results.json) records root's independent 15-case run from clean source commit `c3feee81c6403361e449ec677accf97a7e27d899`: **15 matched expectations, zero mismatches**. Expected aggregates, per-check verdicts, warnings and metrics are all compared; execution errors are retained as errors/incomplete.

| Cases | Observed result |
|---|---|
| Regression, unseen helper regression, silent abort | FAILED / VIOLATION_INTRODUCED |
| Corrected, stable-key exception, unrelated | PASSED_CHECKS / CHECK_PASSED |
| Preexisting failure | FAILED / PRE_EXISTING_FAILURE |
| Resolved | PASSED_CHECKS / RESOLVED |
| Crash, timeout, missing entrypoint | INCOMPLETE / NOT_CHECKED |
| Candidate policy edit | INCOMPLETE, despite passing individual observations |
| Zero authority, missing approval, forged approval | INCOMPLETE; unapproved authority never executes |

The absolute input-repository path was replaced with `<generated approved demo>` in the curated copy. All other recorded observations, errors, hashes and source provenance are retained. Missing/forged fixtures were generated in a disposable clone with fixed synthetic commit metadata; they do not modify the input demo. The original local outputs stay ignored under `.ddg-evaluation`.

The worker's initial expectation ledger omitted ordinary-test error warnings and policy-change warnings in some error/authority cases. Those expectation omissions are described in [the evaluator handoff](../docs/phases/handoffs/PHASE_05_EVAL.md). Actual observations were retained, not changed to force a match. This small authored matrix is not an independent production benchmark or a statistical performance claim.

## Actual browser observations

All images were captured from the local application on 4 October 2026. They document actual UI states; the opening reveal still requires a fresh run during judging.

- [Regression](browser-regression.jpg): ordinary PASS/PASS, one operation/two jobs, introduced violation and governing DEC-002.
- [Calibration and approval](browser-calibration.jpg): bad FAIL/two jobs, fixed and stable-key PASS/one job, exact citations and explicitly labeled AI integration attestation.
- [Exception](browser-exception.jpg): stable-key completion reuses one real job.
- [Policy review](browser-policy-review.jpg): primary INCOMPLETE despite passing individual observations.
- [Stale report](browser-stale.jpg): a moved ref requires a rerun; the task-owned ref was restored afterward.
- [Narrow layout](browser-narrow.jpg): readable verdict at 390 pixels without horizontal overflow.
- [Live timeout](browser-live-timeout.jpg): real provider retry failed at the caller deadline, with no draft/approval. Root then explicitly selected Recorded; this attempt is not claimed as successful live generation.

The prior successful live capture and the later timed-out browser request are separate events. Approval identity `Codex integration reviewer` is an AI local attestation, not a human participant or authenticated person. [The integrated browser handoff](../docs/phases/handoffs/PHASE_04.md) records the lifecycle and review corrections.

## Human and release evidence

[reviewer-observations.csv](reviewer-observations.csv) contains headers only. No review-time savings, participant feedback or timed speaking rehearsal have been measured. Video recording remains pending. Use [the protocol](../docs/HUMAN_EVALUATION.md) to collect those observations.

[Phase status](../docs/phases/STATUS.md) and [evaluation](../docs/EVALUATION.md) record final tests, release and fresh-checkout reproduction separately from these artifacts.

[remote-reproduction.json](remote-reproduction.json) records fresh GitHub clone `8d5ca14895bd05b638ee37614cf35c7c989b9533`: documented Recorded CLI lifecycle, correct regression/exception/policy exits, real local server/assets and all 15 expected case outcomes. Provider credentials were removed from command environments. The final documentation update retains identical implementation files. Root's full suite passed 110 tests in 280.603 seconds on implementation `c3feee81c6403361e449ec677accf97a7e27d899`.

## Addendum 12 October 2026

Everything above is the unchanged record of 4 October 2026. Later changes that affect how to read it:

- The 110-test figure belongs to commit `c3feee81c6403361e449ec677accf97a7e27d899`. The suite has 370 tests on `master` as of 12 October 2026, all passing in the last full run (host and Docker modes).
- `case-results.json` and `remote-reproduction.json` were produced when workers ran as host subprocesses and approval trusted a typed name. They have not been regenerated with the container sandbox or approver identity checks.
- The approval identity `Codex integration reviewer` is a typed label. A demo built with current code approves as the Git author `ddg-demo@example.invalid`, listed in the demo's `.ddg/approvers.json`.
- No human observations have been added. `reviewer-observations.csv` still has headers only.
- On 12 October 2026 the 15-case matrix was re-run in Docker mode on the final code with a freshly built demo and matched 15 of 15. That output was not added to this folder; `case-results.json` remains the earlier record.

## Addendum 12 October 2026: redesigned viewer

The `ui-obsidian-*.png` images were captured on 12 October 2026 from the redesigned viewer (Playwright and Chromium, a freshly built approved demo, real runs in Docker mode). They show the same product states as the earlier `browser-*.jpg` images, which remain the unchanged 4 October record of the light interface:

- [Review, FAILED](ui-obsidian-review-failed.png): regression, one target job and two candidate jobs against an expected one.
- [Review, PASSED](ui-obsidian-review-passed.png): the corrected implementation.
- [Review, INCOMPLETE](ui-obsidian-review-incomplete.png): a crashing candidate; its observation is shown as not observed.
- [Review on a 390 px screen](ui-obsidian-review-mobile.png): policy edit at the head, INCOMPLETE.
- [Approval](ui-obsidian-approval.png) and [decision change](ui-obsidian-decision.png) views.
