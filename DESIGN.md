# Design system: Obsidian control surface

Recorded on 12 October 2026 from the built viewer (`web/index.html`, `web/style.css`, `web/app.js`). Product truth is in [PRODUCT.md](PRODUCT.md). This file describes what exists, not an aspiration.

## Concept

The review screen is a measuring instrument. The gate result is read from real observations: one column of slabs for the target revision, one for the candidate, and a dashed marker for what the approved check expects. Nothing drawn is invented, missing data never looks healthy, and the screen never claims anything was blocked (DDG returns an exit code; the CI job or a person acts).

## Tokens (`:root` in `style.css`)

| Role | Value | Use |
|---|---|---|
| Obsidian | `#090B0E` | page background, input wells |
| Surface | `#13171D` | panels |
| Raised | `#1A2028` | tags, secondary buttons, notices |
| Line / line-strong | `#242B35` / `#323C49` | hairline borders (declared once per panel; no shadows) |
| Ink / ink-2 / muted | `#E9EDF2` / `#B4BDCA` / `#8892A1` | primary, secondary, tertiary text |
| Control (emerald) | `#40E0A0` | held control, primary action, verified, PASS |
| Context (blue) | `#5C9DFF` | baseline, expected-count marker, links, focus ring |
| Warning (amber) | `#FFB454` | unproven, incomplete, stale, not observed |
| Danger (red) | `#FF6B6B` | proven violation, unverified-approver warning, host-unsafe |

Ambient light: two fixed radial gradients (emerald top-left, blue bottom-right) at 7% opacity. No grid overlay on the page; gridlines exist only inside the state field, where they are the axis.

## Type

Geist (UI) and Geist Mono (ids, SHAs, counts, exit codes), both bundled variable fonts in `web/fonts/` under the SIL Open Font License, served by `ddg/web.py`. Verdict word `clamp(34px, 3.8vw, 54px)` weight 600, tracking -0.03em. Body 14px. Radius 14px on panels, 10px on controls.

## Components

- **Readout bar** (`.statusbar`): check id, proposal source and model, approver (verified or UNVERIFIED), isolation (docker, podman, host UNSAFE). Values come from the report; unknown reads "none", "not recorded" or "no run yet".
- **Step rail** (`.nav-item[data-state]`): done (filled ring), attention (amber diamond), failed (red filled diamond), pending (dashed ring). State is also written as text.
- **Gate result** (`.gate-verdict`): icon in a ring (check, cross, question, clock, dash) plus the word PASSED, FAILED, INCOMPLETE, STALE or NOT RUN, a summary, and `exit code N`.
- **State field** (`#state-field`, `drawField()` in `app.js`): inline SVG. One slab per observed job. Tone by observation status: emerald PASS, red FAIL. An errored or absent observation is an amber hatched dashed box labelled "not observed". Expected count from the approved check's `unique_jobs` assertion. The same function draws the compact three-column calibration chart.
- **Steps** (`.steps`): Detect, Explain, Enforce, Audit, each filled from the report. Numbers are shown because the sequence carries information.
- **Service trace** (`.timeline`): events with shape-coded markers (circle, rounded square, diamond) and mono metadata.
- **Tags and chips**: tone class plus a text label; never colour alone.

## Motion

Slabs rise once (800 ms exponential ease-out, 110 ms stagger); views and the verdict word settle in over 350 to 500 ms. All of it is inside `prefers-reduced-motion: no-preference`. `forced-colors` has an outline fallback.

## Responsive

Below 1180 px the steps drop under the verdict and field. Below 900 px the layout is one column, the rail becomes a three-button bar, and the readouts form a 2 by 2 grid. Checked at 1440 and 390 px with no horizontal overflow.

## Rules for future work

1. Draw only data in `GET /api/state`. Anything illustrative must be labelled as such and kept out of the live views.
2. Unknown, incomplete, stale and errored are never green and never blank.
3. Pair every colour with text and a glyph.
4. Do not imply enforcement that the backend has not confirmed.
5. Keep element ids and the `ddg-session-token` meta tag; `web/app.js`, `tests/test_web.py` and `tests/e2e/` rely on them.

## Known limits

- The slab chart caps at six jobs per column (the scale compresses above three).
- The designer's detector reports "overused font" for Geist; it is kept because the brief names it.
- Screenshots in `evidence/ui-obsidian-*.png` are of a Docker-mode demo; the viewer has been checked in Chromium only.
