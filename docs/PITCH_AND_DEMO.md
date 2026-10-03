# Decision Drift Gate Pitch and Demo

**Updated:** 4 October 2026. **Status:** browser lifecycle and fresh reveal verified; human speaking rehearsal pending. **Audience:** Algo Works Hackathon judges. **Deliverables:** live demonstration, documentation, and source repository.

## Twenty second pitch

> Your tests can pass while an old mistake returns. Decision Drift Gate turns changed engineering decisions into developer-approved checks. When later code breaks one, we show the failing behavior and why the rule exists. Watch this change pass ordinary tests but create a duplicate job.

This is a rehearsal target, not a measured speaking duration. Deliver the last sentence while running the case. Do not introduce ADRs, Git SHAs, LLM providers, or architecture in the opening pitch. The check's actual execution must be visible before presenting it as working.

One-line description for slides and repository: **Turn changed engineering decisions into approved checks that catch old behavior returning.**

## Fast live reveal

Have the real approved check ready before the fast reveal. State that it was approved earlier; show that lifecycle in the longer walkthrough. Execute the comparison during the demonstration rather than opening an old screenshot.

| Time | Presenter action | Judge sees |
|---|---|---|
| 0-5 seconds | Explain that old mistakes can return despite passing tests | Review card with genuine happy-path test results |
| 5-10 seconds | Point to the changed rule and its approved check | DEC-001 replaced by DEC-002; visible reviewer/check identity |
| 10-15 seconds | Run the blind-retry change | Fresh trace: accepted job, 503, repeated submission, two jobs |
| 15-20 seconds | Point to the failed check and governing decision | Expected 1, observed 2; replacement rule; fix is reconciliation or a stable key |

These timings are targets. If the measured run is slower, shorten the opening and use a second operator to trigger it on cue. Do not speed up or disguise execution logs.

The main card should require no scrolling at 1366x768. Make the observable contrast large: **one operation / two jobs**. Display the replacement decision beneath it. Keep hash details in the evidence drawer.

## Ninety second lifecycle walkthrough

1. **0-15 seconds:** open the old and replacement rule. Explain how a failed response can follow a successful operation. Both records are synthetic and versioned.
2. **15-35 seconds:** choose Live proposal. AI selects the lost-acknowledgement scenario and observable assertions. Show its exact decision citation. If generation exceeds the slot, say so and move to the labeled prior capture.
3. **35-50 seconds:** Validate. Known-bad fails; known-good and the stable-key exception pass. Show the developer's explicit approval of these exact bytes.
4. **50-65 seconds:** run the regression and show ordinary tests passing alongside the new check failing, with two created jobs.
5. **65-80 seconds:** run the helper-based unseen regression, then the valid stable-key implementation. The first fails; the exception passes. Neither verdict is an LLM opinion.
6. **80-90 seconds:** explain the limit: this proves one approved behavior in this adapter. Future expansion follows measured value.

Keep the policy-edit, preexisting failure, and stale-report cases ready for technical questions. They are confidence evidence, not the opening story.

## Answers to likely judge questions

**Why not write a normal test?** A normal test is the execution mechanism. We help turn a changed decision into a calibrated, approved check and keep its reason attached to future failures. We must still show this saves effort over doing that manually.

**Where does AI add value?** It reads the decision replacement and proposes the fault scenario, assertions, exception, and explanation. A human validates the draft. The later result comes from running the approved check.

**Is this another AI reviewer?** The demonstration centers on a specific decision-linked check lifecycle. Generic review and test generation already exist; our proposed advantage is less effort maintaining this lifecycle and clearer evidence when a rule is broken.

**Can AI invent a rule?** A proposal must cite exact supplied decision text. The developer checks whether the scenario and assertions express that rule. Unsupported or conflicting records remain unapproved or not checked.

**What prevents a PR from deleting the test?** Execution uses the check/approval from the target revision. Policy edits at the proposed revision trigger explicit policy review and an incomplete aggregate result.

**Does passing mean the change is safe?** It means the approved checks passed for those code revisions. The tool does not certify untested behaviors or undocumented decisions.

**Is it tied to GitHub?** The engine reads local Git revisions. GitHub PRs and GitLab MRs can supply the same inputs later. The first release demonstrates a local browser workflow and ships source on GitHub; it does not claim a live hosting integration.

**What if the internet fails?** Executing approved checks still works. The generation step can use a labeled capture from a previous real AI call. A manual sample is labeled separately.

**Have you reduced review time by 50%?** That is our original experimental target. State actual measured results and sample size once available; currently no saving has been established.

**Who would use or buy it?** Developers working on recurring incident fixes and changing engineering rules are the first user hypothesis. Engineering leads may value it if saved work exceeds approval and maintenance costs. Buyer demand is not yet validated.

## Claims ledger

| Claim | Present status | Evidence required before saying it publicly |
|---|---|---|
| Selected top 25 from 125 | Team-reported | Organizer confirmation if used on a public slide |
| AI drafts a grounded check | Verified capture | Real Gemini capture; a later browser Live request timed out and required explicit Recorded selection |
| Later regression produces duplicate jobs | Verified execution | Actual browser and CLI runs, one→two jobs with ordinary tests passing |
| Equivalent unseen regression is caught | Verified synthetic case | Helper variant absent from provider/calibration inputs; see evaluation evidence |
| Legitimate exception passes | Verified synthetic case | Stable-key case completes with one real job |
| Candidate cannot silently remove its own rule | Verified engine behavior | Target authority retained; policy-edit case returns INCOMPLETE |
| 50% less review time | Unmeasured target | Counterbalanced baseline comparison with raw timing/sample size |
| Works for all repositories/languages | Unsupported | Never use this claim for the prototype |

## Preparation checklist

- Confirm the application was built and the current cases passed.
- Display Live or Recorded proposal mode throughout.
- Have a real saved proposal and fresh offline execution available.
- Open the browser at the case selector; hide unrelated windows and terminal clutter.
- Use one presenter and one operator if two people are available.
- Rehearse the pitch five times and record actual durations.
- Keep the source repository and setup instructions available for inspection.
- End with the observed result and governing rule; avoid an unsupported market-size or savings claim.
