# Phase 05 release review

Technical implementation and automated evidence are verified. Full phase acceptance remains pending human comparison, five timed speaking rehearsals and video recording; the agents have not fabricated any of those observations.

## Verified implementation

Source implementation commit: `c3feee81c6403361e449ec677accf97a7e27d899`. The parallel Luna workers implemented evaluator/tests and browser review corrections; root independently reviewed, tested, curated evidence and serialized commits. The [evaluator handoff](PHASE_05_EVAL.md) records its actual test runs and expectation-ledger corrections.

- Root `python -m unittest discover -s tests -v`: **110 tests passed in 280.603 seconds**, exit 0.
- Root `python scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation`: **15/15 expectations matched**, exit 0, clean source recorded by the evaluator.
- Full case/check hashes independently verified; curated [case results](../../../evidence/case-results.json) retain actual errors, warnings and metrics. The only sanitization replaces the input absolute path.
- Actual [browser lifecycle/review](PHASE_04.md) includes fresh regression/holdout failures, passing exception, incomplete policy review, stale display, persistence, responsive layout and explicit fallback after a real live timeout.
- Successful prior Gemini capture: `gemini-3.8-flash`, SDK `2.28.0`, capture UTC `2026-10-03T18:19:56.974766Z`. The later browser timeout is separate, disclosed evidence.
- Windows environment: Python 3.12.4, Git 2.51.0.windows.2. Core tests, Recorded generation and approved execution require no provider key or SDK.

## Run and pitch

Follow [the README](../../../README.md) for fresh CLI/browser setup. Start `python -m ddg serve --repo .ddg-demo --state-dir .ddg-state`, open the printed loopback URL, and stop with Ctrl+C. A generated destination must be new/empty.

For the opening pitch, disclose earlier approval and execute **Retry regression** fresh on Review change. Judges see ordinary tests passing while one operation creates two jobs; DEC-002 explains why. Then demonstrate **Unseen helper regression** and **Allowed idempotency exception**. Use the clearly labeled Recorded capture if live generation times out; never describe it as a new AI call.

The 45-word script is a target, not measured speaking time. [Human evaluation](../../HUMAN_EVALUATION.md) supplies counterbalanced tasks, a header-only CSV and five rehearsal slots. Human sample size is zero, and the 50% time-saving target is unmeasured. Approval labels identify Codex integration attestation rather than human participants.

## Publication and residual scope

Authorized destination: [Yashjain329/Decision-Drift-Gate](https://github.com/Yashjain329/Decision-Drift-Gate). The release owner is publishing the source and will record the verified remote commit and fresh-clone result here after they actually complete.

The supported product is one trusted synthetic Python job-client adapter and a DEC-001 → DEC-002 replacement. The evaluator targets its default CHK-001 fixtures. There is no arbitrary-repository sandbox, authenticated multiuser approval, live GitHub PR integration, general decision translation, established buyer demand or measured human saving.
