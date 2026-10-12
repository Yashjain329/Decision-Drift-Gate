// States the demo repository cannot produce on its own, built by altering the engine's real /api/state response
// in the network layer: failed calibration, unverifiable approver, unknown verdicts, missing fields, many checks.
// The point is the UI's honesty rule: anything unproven, unknown or missing is never shown as healthy.
import type { Page } from '@playwright/test';
import { startDemo, type Demo } from './harness';
import { expect, go, open, test, view } from './fixtures';

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

async function withState(page: Page, mutate: (s: Json) => void): Promise<void> {
  await page.route('**/api/state', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { state: Json };
    mutate(body.state);
    await route.fulfill({ response, json: body });
  });
}

let approved: Demo; // approved, no run
let ran: Demo;      // approved + regression run
test.beforeAll(async () => { [approved, ran] = await Promise.all([startDemo({ approve: true }), startDemo({ scenario: 'regression' })]); });
test.afterAll(async () => { await Promise.all([approved?.stop(), ran?.stop()]); });

test('failed calibration: Mismatch rows, Needs work, approval blocked, attention raised', async ({ page }) => {
  await withState(page, (s) => {
    s.approval = null; s.scenarios = []; s.report = null;
    s.validation.eligible = false;
    s.validation.cases.bad.observation.status = 'PASS'; // the known-bad fixture slipped through
  });
  await open(page, approved, 'checks');
  await expect(page.locator('#matrix-body .tag')).toHaveText(['Mismatch', 'Valid', 'Valid']);
  await expect(page.locator('#matrix-body .tag').first()).toHaveClass(/tag-fail/);
  await expect(view(page, 'checks').locator('.page-head .tag').first()).toHaveText('Calibration · needs work');
  await expect(page.locator('#calibration-explanation')).toContainText('2 of 3 fixtures matched');
  await go(page, 'approvals');
  await expect(page.locator('.flow-step').nth(1)).toHaveClass(/is-failed/);
  await page.locator('#reviewer').fill('Someone');
  await page.locator('#reason').fill('Trying anyway');
  await expect(page.locator('#approve-button')).toBeDisabled();
  await go(page, 'overview');
  await expect(page.locator('#st-calibration')).toHaveText('Needs work');
  await expect(page.locator('#attention')).toContainText('Calibration failed.');
  await expect(page.locator('.nav-item[href="#checks"] .nav-state')).toHaveText('needs work');
});

test('unverifiable approver: never "Verified", flagged in red everywhere', async ({ page }) => {
  await withState(page, (s) => {
    for (const c of s.report.checks) c.approver = { verified: false, require_signed: true, reason: 'approval commit is not signed', commits: [{ commit: 'abc', author_email: 'mallory@example.com', signature: 'N' }] };
  });
  await open(page, ran, 'approvals');
  await expect(page.locator('#approval-state')).toHaveText('Unverifiable');
  await expect(page.locator('#approval-state .tag')).toHaveClass(/tag-fail/);
  await expect(page.locator('#git-state')).toHaveText('Unverifiable');
  await expect(page.locator('.flow-step').nth(3)).toHaveClass(/is-failed/);
  await expect(page.locator('.flow-step').nth(3)).toContainText('approval commit is not signed');
  await expect(page.locator('#rec-require')).toHaveText('yes');
  const approver = page.locator('.readout').filter({ hasText: 'Approver' }).locator('dd');
  await expect(approver).toHaveText('UNVERIFIED');
  await expect(approver).toHaveClass(/is-fail/);
  await go(page, 'runs');
  await expect(page.locator('.evidence-stack details').filter({ hasText: 'Approval provenance' }).locator('.summary-meta')).toHaveText('NOT verified');
  await go(page, 'overview');
  await expect(page.locator('#attention')).toContainText('Approver not verified.');
});

test('unknown verdict from a newer engine is treated as Not checked, never a pass', async ({ page }) => {
  await withState(page, (s) => { s.report.checks[0].verdict = 'SOMETHING_NEW'; });
  await open(page, ran, 'runs');
  await expect(page.locator('#detail .tag')).toHaveText('Not checked');
  await expect(page.locator('#detail .tag')).toHaveAttribute('title', 'SOMETHING_NEW');
  await expect(page.locator('#result-groups .group')).toHaveClass(/g-inc/);
  await go(page, 'reports');
  await expect(page.locator('#rep-rows .enum')).toHaveText('SOMETHING_NEW');
});

test('unknown aggregate is shown as Incomplete with exit 2', async ({ page }) => {
  await withState(page, (s) => { s.report.aggregate = 'FUTURE_STATE'; });
  await open(page, ran, 'runs');
  await expect(page.locator('#run-result .result-word')).toHaveText('Incomplete');
  await expect(page.locator('#run-summary')).toHaveClass(/tone-inc/);
  await expect(page.locator('#run-summary .exit-chip')).toHaveText('exit 2');
});

test('missing fields render as "not recorded", never "undefined" or blank-green', async ({ page }) => {
  await withState(page, (s) => {
    const r = s.report;
    delete r.sandbox; delete r.run_at; delete r.adapter_version;
    r.checks[0].head = { status: 'ERROR', error: null, events: [] };
    r.checks[0].verdict = 'NOT_CHECKED';
    r.aggregate = 'INCOMPLETE';
  });
  await open(page, ran, 'runs');
  await expect(page.locator('#run-sandbox')).toHaveText('not recorded');
  await expect(page.locator('#run-sandbox')).toHaveClass(/is-inc/);
  await expect(page.locator('#detail svg.chart rect.j-inc')).toHaveCount(1);
  await expect(page.locator('#detail-head')).toHaveText('ERROR · not observed');
  for (const id of ['overview', 'runs', 'reports', 'approvals'] as const) {
    await go(page, id);
    await expect(view(page, id)).not.toContainText('undefined');
    await expect(view(page, id)).not.toContainText('NaN');
  }
  const iso = page.locator('.readout').filter({ hasText: 'Isolation' }).locator('dd');
  await expect(iso).toHaveText('not recorded'); // a run happened; its isolation is unknown, not absent
  await expect(iso).toHaveClass(/is-inc/);
  await go(page, 'overview');
  await expect(view(page, 'overview').locator('.tag', { hasText: 'isolation not recorded' })).toHaveClass(/tag-inc/);
  await go(page, 'reports');
  await expect(page.locator('#rep-meta')).toContainText('not recorded');
});

test('several checks: grouping, counts, selection and the zero line', async ({ page }) => {
  await withState(page, (s) => {
    const [c] = s.report.checks;
    const clone = (id: string, verdict: string) => ({ ...structuredClone(c), check_id: id, verdict });
    s.report.checks = [c, clone('CHK-002', 'CHECK_PASSED'), clone('CHK-003', 'PRE_EXISTING_FAILURE'), clone('CHK-004', 'HISTORICAL_CHECK_IGNORED')];
  });
  await open(page, ran, 'runs');
  await expect(page.locator('#results-count')).toHaveText('3 checks'); // historical checks are not counted
  await expect(page.locator('#result-groups .group')).toHaveCount(3);
  await expect(page.locator('#result-groups .h-label')).toHaveText(['Violation introduced', 'Pre-existing failure', 'Check passed']);
  await expect(page.locator('#results-zero')).toHaveText('None resolved · not checked');
  // the first non-passing check is selected by default; clicking another moves the selection
  await expect(page.locator('.result-row[aria-pressed="true"] .rr-id')).toHaveText('CHK-001');
  await page.locator('.result-row', { hasText: 'CHK-002' }).click();
  await expect(page.locator('.result-row[aria-pressed="true"] .rr-id')).toHaveText('CHK-002');
  await expect(page.locator('#detail-check')).toHaveText('CHK-002');
  await expect(page.locator('#detail .tag')).toHaveText('Check passed');
  await go(page, 'overview');
  await expect(page.locator('.outcome-n')).toHaveText(['1', '1', '0', '1', '0']);
  await go(page, 'reports');
  await expect(page.locator('#rep-rows tr')).toHaveCount(3);
});

test('a report with no checks says so instead of showing an empty pass', async ({ page }) => {
  await withState(page, (s) => { s.report.checks = []; s.report.aggregate = 'INCOMPLETE'; s.report.warnings = [{ code: 'NO_ACTIVE_APPROVED_CHECKS', message: 'No approved check covers the active decision.' }]; });
  await open(page, ran, 'runs');
  await expect(page.locator('#result-groups')).toContainText('No approved check produced a result.');
  await expect(page.locator('#run-summary-text')).toHaveText('An active decision has no approved check.');
  await expect(page.locator('#run-warnings code')).toHaveText('NO_ACTIVE_APPROVED_CHECKS');
  await go(page, 'reports');
  await expect(page.locator('#rep-rows')).toContainText('No approved check');
});

test('hostile text from records is rendered as text, never as HTML', async ({ page }) => {
  const payload = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>';
  await withState(page, (s) => {
    s.new_decision.rule = payload;
    s.report.checks[0].decision.rule = payload;
    s.report.warnings = [{ code: 'X', message: payload }];
    s.approval.reviewer = payload;
  });
  await open(page, ran, 'decisions');
  await expect(page.locator('#decision-list')).toContainText('<script>');
  for (const id of ['runs', 'approvals', 'reports'] as const) await go(page, id);
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
});
