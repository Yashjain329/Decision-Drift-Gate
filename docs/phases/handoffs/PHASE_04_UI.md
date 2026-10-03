# Phase 04 UI handoff

## Implemented

The plain HTML/CSS/JavaScript browser interface lives in `web/`. It provides Decision change, Approve check, and Review change views. It displays the previous and active decision, proposal source and provenance, structured assertions and citations, calibration cases, explicit reviewer approval, and execution reports. An already approved demo opens to Review change; a fresh demo opens to Decision change.

The review view uses the server's actual report: ordinary target/candidate observations, the check verdict, observed unique-job count, distinct operation IDs from the event trace, governing decision text, timeline events, and expandable hashes/provenance. It distinguishes missing execution from completed evidence and shows stale reports with a rerun-required label. Check identity, source mode, approving reviewer, and report freshness are visible in the review heading. Dynamic data is rendered with `textContent`, `createElement`, and text-valued form options. No client framework, remote asset, font, or image dependency is used.

The layout is designed for a compact 1366x768 review card and reflows for narrow screens. It includes keyboard focus styles, skip navigation, semantic buttons/labels, visible textual status alongside color, and reduced-motion support. Visual style follows the minimalist warm-monochrome direction: system sans, Georgia editorial headings, monospace evidence, 1px borders, muted status colors, and square/short-radius surfaces. Narrow screens scale the literal verdict text without breaking it mid-word. Each action announces specific progress in the live status region while buttons are busy.

## Verification

- `node --check web/app.js` — passed after the latest mobile and pending-state changes.
- Python's standard-library HTML parser accepted `web/index.html`.
- `python -m unittest tests.test_web -v` — 8 tests passed in 44.889 seconds after the server boundary fix. Root subsequently reports 9 HTTP tests passed in 49.420 seconds.
- Safe-rendering review found no `innerHTML`, `outerHTML`, or `insertAdjacentHTML` use. All proposal, decision, report, and event fields go through text nodes.
- Root's browser pass confirmed the regression review showed ordinary tests PASS/PASS and one operation versus two jobs with a real timeline. At 1366x768 the layout was readable with no horizontal overflow. That pass exposed a mid-word mobile verdict wrap; the CSS now uses a narrower mobile font while retaining the literal verdict. A concise action-specific progress notice was also added after the provider request appeared busy without visible feedback.

The orchestrator is completing the post-fix narrow viewport and full lifecycle browser pass. This handoff does not claim unobserved provider completion timing or screenshots.

## API contract

The UI reads `GET /api/state` as `{state: {mode, lifecycle, old_decision, new_decision, draft, validation, approval, report, report_stale, scenarios, busy}}`. It posts `propose {mode}`, `validate {draft_digest}`, `approve {draft_digest, reviewer, reason}`, and `run {scenario}` to `/api/<action>`, sends the token from `meta[name=ddg-session-token]` as `X-DDG-Session`, and expects `{state}` for success or `{error}` for failure.
