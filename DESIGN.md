# Design system: Obsidian / Signal Lime

Recorded on 12 October 2026 from the built viewer: a Next.js + TypeScript app in `web/src` (views in `web/src/views`, shared primitives in `web/src/components`, product vocabulary and derivations in `web/src/lib/model.ts`, styles in `web/src/app/globals.css`), statically exported to `web/out`. Product truth is in [PRODUCT.md](PRODUCT.md); the creative brief is `../ddg-reference/creative-direction.txt`. This file describes what exists.

Formula: reference architecture + Signal Lime visual system + complete evidence + progressive disclosure + signal-first readability.

## Information architecture

Seven destinations in a fixed left rail (a horizontal scroller below 900 px): Overview, Decisions, Check Studio, Runs & Regressions, Approvals, Reports, Providers & CLI. Old hashes `#decision`, `#approval`, `#review` redirect to Decisions, Approvals, Runs.

## Hierarchy rule: signal first, evidence on demand

Every screen leads with the outcome, a one-line reason, and one next action. Hashes, traces, diffs, digests, rationale, citations and raw JSON sit behind `<details>`, each summary carrying a one-line meta (for example `base 4 events · head 6 events`, `+0 −3`, `verified · author`) so a collapsed section still informs. Copy is capped at 56–66ch.

## Tokens (`:root`)

| Role | Value | Use |
|---|---|---|
| Obsidian | `#0B0C0D` | page, wells |
| Surface / Elevated | `#17191C` / `#272A2E` | panels / controls, neutral chips |
| Signal Lime | `#D7FF67` | primary action, active nav icon, verified-healthy states, focus ring. Accent only, never a surface. |
| Analytical Purple | `#9B8AFB` | trusted base, pre-existing failure, expected-count line, decision quotes |
| Evidence Orange | `#F5A36B` | incomplete, not checked, stale; always with a diagonal hatch in charts |
| Red | `#FF6B6B` | proven violation only |

Links and command names are neutral ink with an underline; lime appears on hover.

## State language

Human label first, raw enum second in small mono (`Violation introduced` / `VIOLATION_INTRODUCED`). Overall results: Checks passed (exit 0), Failed (1), Incomplete (2), Stale, Not run. Every tone also carries a Lucide-style glyph and a word. Unknown, incomplete, unverified and host-isolation states are never lime.

## Key components

- **Signal band** (`#ov-signal`, `.run-summary`): result glyph and word, exit chip, reason, next action; left border in the result tone. Sticky on Runs at desktop widths.
- **Trust boundary** (`.revpair`): Base · trusted (purple, lock), Head · untrusted (box), Isolation.
- **Run inspector**: non-empty outcome groups with their checks; empty outcomes collapse into one muted line. The selected check shows reason, governing decision and the base-vs-head job chart; evidence accordion below.
- **Charts** (`drawColumns()`): one rounded block per job observed; hatched orange outline when not observed; dashed purple expected line. The Overview session chart counts only runs made in this tab (sessionStorage), and says so.
- **Approval**: four-step flow; the approval record and Git provenance are separate. "Verified" only after a run reads the approval commit.

## Motion and accessibility

150–220 ms transitions, no continuous animation, all motion off under `prefers-reduced-motion`. Skip link, `aria-current` nav, live notice region, labelled charts, forced-colors outlines, 44 px controls under 900 px.

## Responsive

1320 px trims topbar readouts; 1180 px stacks the inspector and goes to two-column outcomes; 900 px turns the rail into a scrolling bar and stacks base/head; 560 px single-column flows, toolbars and commands, 2×2 stats. Checked at 1440 and 390 px with no horizontal overflow.

## Rules

1. Draw only data in `GET /api/state` (plus runs seen in this tab, labelled).
2. Never imply DDG blocked anything; it reports an exit code.
3. Keep the `ddg-session-token` meta tag; `tests/test_web.py` relies on it.
