# Phase 04 UI handoff

## Implemented

The plain HTML/CSS/JavaScript browser interface lives in `web/`. It provides Decision change, Approve check, and Review change views. It displays the previous and active decision, proposal source and provenance, structured assertions and citations, calibration cases, explicit reviewer approval, and execution reports. An already approved demo opens to Review change; a fresh demo opens to Decision change.

The review view uses the server's actual report: ordinary target/candidate observations, the check verdict, observed unique-job count, distinct operation IDs from the event trace, governing decision text, timeline events, and expandable hashes/provenance. It distinguishes missing execution from completed evidence and shows stale reports with a rerun-required label. The selected candidate restores from the report's recorded head ref; a separate label identifies which candidate produced the report if the selector later changes. `INCOMPLETE` takes primary display priority over a passing per-check result, with a reason for policy, coverage, or execution gaps. Check identity, source mode, approving reviewer, and report freshness are visible in the review heading. Dynamic data is rendered with `textContent`, `createElement`, and text-valued form options. No client framework, remote asset, font, or image dependency is used.

The layout is designed for a compact 1366x768 review card and reflows for narrow screens. It includes keyboard focus styles, skip navigation, semantic buttons/labels, visible textual status alongside color, and reduced-motion support. Visual style follows the minimalist warm-monochrome direction: system sans, Georgia editorial headings, monospace evidence, 1px borders, muted status colors, and square/short-radius surfaces. Narrow screens scale the literal verdict text without breaking it mid-word. Each action announces specific progress in the live status region while buttons are busy.

## Verification

- `node --check web/app.js` — passed after the latest mobile and pending-state changes.
- Python's standard-library HTML parser accepted `web/index.html`.
- `python -m unittest tests.test_web -v` — 11 tests passed in 69.406 seconds, including rejection of proposal/validation after approval and canonical approval restoration when a persisted session tries to hide it.
- Safe-rendering review found no `innerHTML`, `outerHTML`, or `insertAdjacentHTML` use. All proposal, decision, report, and event fields go through text nodes.
- Root's browser pass confirmed the regression review showed ordinary tests PASS/PASS and one operation versus two jobs with a real timeline. At 1366x768 the layout was readable with no horizontal overflow. At 390px, the literal verdict now fits on one line without horizontal overflow. A concise action-specific progress notice appears during proposal, calibration, approval, and execution requests.
- Root completed a fresh Recorded proposal, calibration, approval, and regression run; the result was `FAILED`. Follow-up review cases identified and fixed report selection after reload and `INCOMPLETE` precedence for policy edits. Root is rerunning those final browser checks.

The orchestrator is completing the final post-review browser checks. This handoff does not claim unobserved live-provider completion timing.

## API contract

The UI reads `GET /api/state` as `{state: {mode, lifecycle, old_decision, new_decision, draft, validation, approval, report, report_stale, scenarios, busy}}`. It posts `propose {mode}`, `validate {draft_digest}`, `approve {draft_digest, reviewer, reason}`, and `run {scenario}` to `/api/<action>`, sends the token from `meta[name=ddg-session-token]` as `X-DDG-Session`, and expects `{state}` for success or `{error}` for failure.
