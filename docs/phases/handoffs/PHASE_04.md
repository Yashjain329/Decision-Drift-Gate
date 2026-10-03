# Phase 04 integrated browser review

The orchestrator independently reviewed the parallel Luna [server](PHASE_04_SERVER.md) and [UI](PHASE_04_UI.md) deliveries. Source ownership stayed separate; Git staging and acceptance are serialized by the orchestrator.

## Independent verification

- `python -m unittest tests.test_web -v`: 9 tests passed in 49.420 seconds, exit 0, after correcting Windows connection resets on rejection paths. Small request bodies are drained within bounded size/time before returning structured errors.
- `python -m unittest tests.test_proposal -v`: 13 tests passed in 29.585 seconds, exit 0. A blocked provider test verifies the caller deadline and refusal of late output.
- `python -m py_compile ddg/web.py ddg/proposal.py`: exit 0.
- Actual browser at `127.0.0.1:8765`: fresh regression execution showed `VIOLATION_INTRODUCED`, target one job, candidate two jobs, ordinary PASS/PASS, DEC-002 text and a six-event service timeline. Reload after server restart preserved verified approval and execution evidence.
- Projector inspection at 1366×768: primary verdict, job counts, ordinary tests and decision fit without scrolling. The trace and expanded evidence can extend below the opening card. Narrow inspection at 390×844 showed no horizontal overflow; keyboard Tab reached the next visible link. The narrow verdict font was subsequently reduced to prevent mid-word splitting.
- Fresh lifecycle at `127.0.0.1:8766`: changed decision → explicit Recorded proposal → eligible calibration (bad FAIL/two jobs, corrected PASS/one job, stable-key PASS/one job) → exact approval by `Codex integration reviewer`. This is an AI integration attestation, not human evaluation evidence.
- Running that newly approved check completed with `FAILED` / `VIOLATION_INTRODUCED`, ordinary PASS/PASS and one→two jobs. The repaired narrow verdict fits on one line at 390 pixels.
- Browser holdout execution also introduced a violation; the stable-key exception returned `CHECK_PASSED` with one job. Moving the exception ref caused a reload to show `STALE` and `Rerun required`; the task-owned ref was restored afterward.

## Live request finding

A real browser Live request outlived SDK network timeouts. The execution agent added a 30-second caller deadline per interaction and visible action progress. Independent real retry returned `Proposal provider request timed out`, left no draft/approval, and re-enabled controls. Root explicitly selected Recorded afterward. The prior real Gemini capture remains valid; this browser attempt is not represented as successful live generation.

The daemon request worker can finish late but transfers only a result/exception through a queue. It cannot create a proposal or modify session state after the caller abandons it. No silent fallback is implemented.

## Evidence and operation

Phase-boundary review corrections: the API now refuses proposal/validation after approval and recovers canonical repository authority when a saved session hides it. Worker HTTP suite passed 11 tests in 69.406 seconds. Actual browser reload restored the exception selector and its report label. Actual policy-edit execution displayed amber `INCOMPLETE` as the primary result, with the policy-review explanation, despite passing individual observations. The final release suite includes these corrections.

Screenshots: [regression](../../../evidence/browser-regression.jpg), [calibration](../../../evidence/browser-calibration.jpg), [exception](../../../evidence/browser-exception.jpg), [narrow layout](../../../evidence/browser-narrow.jpg), [stale report](../../../evidence/browser-stale.jpg), [live timeout](../../../evidence/browser-live-timeout.jpg). They document actual inspected states, not mocked execution or a timed human rehearsal.

Start with `python -m ddg serve --repo .ddg-demo --state-dir .ddg-state`; Ctrl+C stops it. Use a fresh `demo-init` destination for another full lifecycle. An approved demo resumes directly in Review. Live generation requires the optional SDK and local ignored `.env`; approved execution and Recorded generation work without credentials.

Human rehearsal, video recording and reviewer comparison remain Phase 05 external evidence. The source adapter remains limited to trusted synthetic Python code.
