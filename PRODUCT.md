# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
A developer or staff engineer reviewing a code change, who must decide whether it brings back a rule the team replaced. They read the evidence and the verdict, then act on it in their normal review and CI. A presenter also uses the same viewer to demonstrate the idea. (Confirmed by the user, 12 October 2026.)

## Product Purpose
Decision Drift Gate turns a changed engineering decision into a developer-approved, executable check, then runs that check on a base and a head Git revision and reports whether old behavior returned. Success is a review where the reviewer sees the exact observed difference, the governing decision, and who approved the check, without trusting a model's judgment. The viewer is the local browser interface for the synthetic demo scenario (decision change, approve check, review change).

## Positioning
The verdict comes from executing an approved check against pinned revisions, not from a model reading a diff. Authority (decisions, checks, approvers) is read from the base revision only. Anything unproven is reported as INCOMPLETE or NOT_CHECKED, never as a pass.

## Operating Context
Local-only server bound to 127.0.0.1, started with `ddg serve`, against a generated demo repository. State comes from `GET /api/state`; actions are `POST /api/propose`, `/api/validate`, `/api/approve`, `/api/run` with a session token. Three views exist today: Decision change, Approve check, Review change. Results come from a real execution in a container (or marked-unsafe host mode).

## Capabilities and Constraints
- Real data available per run: aggregate (PASSED_CHECKS, FAILED, INCOMPLETE), per-check verdict (VIOLATION_INTRODUCED, PRE_EXISTING_FAILURE, RESOLVED, CHECK_PASSED, NOT_CHECKED), base and head observations (unique jobs, event trace), ordinary-test results, governing decision text, approver evidence, sandbox mode, base and head SHAs, warnings, report freshness (stale after a ref moves).
- Real data not available: any time series, drift index, "decision health" percentage, multi-repository or multi-check history, confidence scores. None may be shown as if measured.
- DDG does not itself block anything. It returns an exit code (0, 1, 2, 3); the CI job or the human acts on it. The interface must not imply that execution was blocked.
- Missing or unprovable data (INCOMPLETE, NOT_CHECKED, STALE, not run) must never look healthy.
- The `ddg-session-token` meta tag (with `__DDG_SESSION_TOKEN__` in `web/src/app/layout.tsx`, replaced by `ddg serve`) and the `#notice` live region must keep working; tests and the browser audit rely on them.

## Brand Commitments
Name: Decision Drift Gate. Binding visual direction volunteered by the user on 12 October 2026 ("Obsidian Control Surface"): near-black #090B0E, surface #13171D, control emerald #40E0A0, context blue #5C9DFF, warning amber #FFB454, red for critical violations; Inter or Geist for interface text and Geist Mono for metrics, ids, timestamps and policy traces; calm high-contrast hierarchy; governance and approval states unmistakable; data-driven volumetric visualization, not decorative 3D; slow ambient motion that respects reduced-motion; never color alone.

## Evidence on Hand
Real screenshots of the earlier light interface in `evidence/browser-*.jpg` (4 October 2026). Real recorded run outputs in `evidence/case-results.json`. No real multi-run history, no customers, no measured review-time savings, no human evaluation. None of these may be invented.

## Product Principles
1. Observation is separate from enforcement: what the viewer shows never decides anything.
2. Every state is explicit. Healthy, failed, incomplete, stale, and not run are visibly different, and unknown is never green.
3. Every verdict leads to its evidence: observed events, governing decision, approver, revisions.
4. Only real data is drawn. Where DDG has nothing to show, the interface says so.
5. Overview first, evidence on demand.

## Accessibility & Inclusion
Never communicate state by color alone (pair with a label and a shape or icon). Readable contrast on a dark theme. Keyboard operable, visible focus, reduced-motion respected. Works at a projector and at 390 px width (earlier evidence images show both layouts).
