// `ddg serve` on a real repository (no demo marker): a read-only view of the approved function check and a
// saved `ddg run` report. Every action is unavailable in the UI and refused by the engine.
import AxeBuilder from '@axe-core/playwright';
import { startRepository, type Demo } from './harness';
import { expect, go, isolationText, open, overflows, test, view, VIEWS } from './fixtures';

let repo: Demo & { base: string; head: string };
test.beforeAll(async () => { repo = await startRepository(); });
test.afterAll(async () => { await repo?.stop(); });

test('shell names the repository, read-only, and the records commit', async ({ page }) => {
  await open(page, repo, 'overview');
  await expect(page.locator('.ws-label')).toHaveText('Repository · read-only');
  await expect(page.locator('.ws-repo')).toHaveText('repo');
  await expect(page.locator('.ws-meta')).toHaveText(`records @ ${repo.base.slice(0, 7)}`);
  await expect(page.locator('#notice')).toHaveClass(/notice-info/);
  await expect(page.locator('#notice')).toContainText('Read-only view of a repository');
  const iso = page.locator('.readout').filter({ hasText: 'Isolation' }).locator('dd');
  await expect(iso).toHaveText(isolationText(repo.sandbox));
});

test('overview shows the saved report: failed, the regressed decision, failing cases on head', async ({ page }) => {
  await open(page, repo, 'overview');
  await expect(page.locator('#ov-result .result-word')).toHaveText('Failed');
  await expect(page.locator('#ov-head-ref')).toHaveText(repo.head.slice(0, 10));
  await expect(page.locator('#attention')).toContainText('DEC-002 regressed');
  await expect(page.locator('#history-title + span')).toHaveText('failing cases on head');
  await expect(page.locator('#history-chart')).toHaveAttribute('aria-label', /1 failing case/);
});

test('check studio: no proposal controls, calibration as a per-case matrix', async ({ page }) => {
  await open(page, repo, 'checks');
  await expect(page.locator('#propose-button')).toHaveCount(0);
  await expect(page.locator('#proposal-mode')).toHaveCount(0);
  await expect(page.locator('#validate-button')).toBeDisabled();
  await expect(page.locator('#check-scenario')).toHaveText('src/pricing.py · discount()');
  await expect(page.locator('#matrix-body .tag')).toHaveText(['Valid', 'Valid', 'Valid']);
  const cases = page.locator('#calibration-cases');
  await expect(cases.locator('thead th')).toHaveText(['#', 'Expectation', 'Known-bad', 'Corrected', 'Exception']);
  await expect(cases.locator('tbody tr')).toHaveCount(3);
  await expect(cases.locator('tbody tr').nth(1)).toContainText('discount(-1, "GOLD") raises ValueError');
  // the known-bad fixture fails exactly the negative-price case; the others pass every case
  await expect(cases.locator('tbody tr').nth(1).locator('td').nth(2)).toHaveText('fail');
  await expect(cases.locator('.cm.is-fail')).toHaveCount(1);
  await expect(cases.locator('.cm.is-pass')).toHaveCount(8);
});

test('runs: run controls locked, per-case base vs head, observed results', async ({ page }) => {
  await open(page, repo, 'runs');
  await expect(page.locator('#run-button')).toBeDisabled();
  await expect(page.locator('#scenario-select')).toBeDisabled();
  await expect(page.locator('#scenario-select option')).toHaveText(['Read-only: run with the ddg CLI']);
  await expect(page.locator('#run-result .result-word')).toHaveText('Failed');
  await expect(page.locator('#run-summary .exit-chip')).toHaveText('exit 1');
  await expect(page.locator('#detail .tag')).toHaveText('Violation introduced');
  const cases = page.locator('#detail-cases');
  await expect(cases.locator('thead th')).toHaveText(['#', 'Expectation', 'Base', 'Head']);
  await expect(cases.locator('tbody tr').nth(1).locator('td').nth(2)).toHaveText('pass');
  await expect(cases.locator('tbody tr').nth(1).locator('td').nth(3)).toHaveText('fail');
  await expect(page.locator('#ev-traces summary')).toContainText('Observed results');
  await expect(page.locator('#detail-base')).toHaveText('PASS · 3 of 3 cases');
  await expect(page.locator('#detail-head')).toHaveText('FAIL · 2 of 3 cases');
  await expect(view(page, 'runs')).not.toContainText('job');
});

test('approvals: verified Git approver, no approval form to submit', async ({ page }) => {
  await open(page, repo, 'approvals');
  await expect(page.locator('#git-state')).toHaveText('Verified');
  const button = page.locator('#approve-button');
  if (await button.count()) await expect(button).toBeDisabled();
});

test('the engine refuses actions even with the session token', async ({ page, problems }) => {
  await open(page, repo, 'overview');
  const before = await repo.state();
  const status = await page.evaluate(async (token) => (await fetch('/api/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-DDG-Session': token }, body: JSON.stringify({ scenario: 'regression' }),
  })).status, repo.token);
  expect(status).toBe(403);
  expect(await repo.state()).toEqual(before);
  // the deliberate 403 is the only browser noise allowed here
  problems.splice(0, problems.length, ...problems.filter((x) => !/403|Failed to load resource/.test(x)));
});

test('no view overflows on a phone and nothing renders "undefined"', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, repo, 'overview');
  for (const id of VIEWS) {
    await go(page, id);
    expect(await overflows(page), `${id} overflows`).toBe(false);
    await expect(view(page, id)).not.toContainText('undefined');
    await expect(view(page, id)).not.toContainText('[object Object]');
  }
});

for (const id of ['checks', 'runs'] as const) {
  test(`axe: no serious or critical violations on ${id} with a function check`, async ({ page }) => {
    await open(page, repo, id);
    await page.locator(`#view-${id} details:not([open]) > summary`).evaluateAll((els) => els.forEach((e) => (e as HTMLElement).click()));
    const result = await new AxeBuilder({ page }).include(`#view-${id}`).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    expect(result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([]);
  });
}

test('without a report: approved records shown, runs view says not run', async ({ page }) => {
  const bare = await startRepository({ report: false });
  try {
    await open(page, bare, 'overview');
    await expect(page.locator('#ov-result .result-word')).toHaveText('Not run');
    await go(page, 'checks');
    await expect(page.locator('#calibration-cases')).toBeVisible();
  } finally { await bare.stop(); }
});
