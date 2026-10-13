# UI end-to-end suite

Playwright tests for the browser viewer. Nothing is mocked by default: every test starts its own `ddg serve` on a fresh demo repository and a free port (`harness.ts`), and the browser talks to the real Python engine, sandbox and Git refs. The viewer under test is the committed build in `web/out`, so run `npm run build` after changing `web/src`.

```bash
cd web
npm ci
npx playwright install chromium        # once
npm run build                          # after UI changes
npm run test:e2e                       # Docker sandbox (default)
DDG_SANDBOX=host npm run test:e2e      # host mode; the UI must label it UNSAFE
```

Docker Desktop must be running for the default mode. Tests are offline: the live-provider test forces `custom_cli` with a failing command, and environment variables win over the repository `.env`.

| Spec | Covers |
|---|---|
| `routing.spec.ts` | hash router: default view, all seven deep links, legacy aliases (`#decision`, `#approval`, `#review`) and their canonical rewrite, invalid hashes, back/forward, reload, brand link, in-page links, scroll reset, skip link |
| `lifecycle.spec.ts` | the whole product through the UI on a fresh demo: empty states of every view, draft, validate, approve (whitespace rejected, values trimmed, not shown as verified), a failed run checked block by block against the engine report (signal, trust boundary, groups, detail, chart, traces, diff, provenance, ordinary tests), top bar, rail states, Overview, Approvals, Reports and the JSON download, notice tones, per-tab history |
| `scenarios.spec.ts` | all 12 candidate heads run through the UI; result, exit code, verdict, warnings, reason and isolation must equal the engine's report, and the known engine contract table |
| `edge.spec.ts` | engine stops mid-session, engine unreachable at load, malformed state, forged session token (403), double click, stale refs and rerun, host isolation, offline live-provider failure, second tab, proposal-source persistence |
| `state-variants.spec.ts` | states the demo cannot produce, made by altering the real `/api/state` response: failed calibration, unverifiable approver, unknown verdict and aggregate, missing fields, several checks and selection, no checks, hostile text rendered as text |
| `repository.spec.ts` | `ddg serve` on a real repository (no demo marker) with an approved `python_function_v1` check and a saved report: read-only shell and notice, no proposal or run controls, per-case calibration and base/head matrices, verified approver, engine refuses actions even with the token, phone widths, axe scan of Check Studio and Runs |
| `responsive-a11y.spec.ts` | seven widths from 360 to 1920 px without sideways scroll, 44 px touch targets on phones, keyboard navigation and focus ring, reduced motion, landmarks and labelled charts, axe WCAG 2.1 A/AA scan of every view and the shell |

Every test also fails on any browser console error, page error or failed request unless the test deliberately provokes it.
