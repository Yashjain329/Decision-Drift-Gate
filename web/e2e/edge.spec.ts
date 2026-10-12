// Edge cases: engine failures, session token, double submits, stale refs, unsafe isolation, provider failure,
// multiple tabs. Expected browser noise (e.g. a deliberate 403) is allowed explicitly per test, nothing else.
import { startDemo } from './harness';
import { expect, go, open, runScenario, test, view, withDemo } from './fixtures';

/** Remove only the browser problems a test deliberately provoked. */
const allow = (problems: string[], pattern: RegExp) => {
  const keep = problems.filter((p) => !pattern.test(p));
  problems.splice(0, problems.length, ...keep);
};

test('engine stops mid-session: the action fails loudly and nothing claims success', async ({ page, problems }) => {
  const demo = await startDemo({ approve: true });
  await open(page, demo, 'runs');
  await demo.stop();
  await page.locator('#run-button').click();
  await expect(page.locator('#notice')).toHaveClass(/notice-error/);
  await expect(page.locator('#notice')).not.toContainText('Run completed');
  await expect(page.locator('#run-button')).toBeEnabled(); // busy state released
  await expect(view(page, 'runs').locator('.empty')).toBeVisible(); // no fabricated report
  allow(problems, /ERR_CONNECTION_REFUSED|Failed to fetch|Failed to load resource/);
});

test('engine unreachable at load: an error is shown and no data is invented', async ({ page, problems }) => {
  const demo = await startDemo();
  const url = demo.url;
  await page.route('**/api/state', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"engine offline"}' }));
  await page.goto(`${url}/#overview`);
  await expect(page.locator('#notice')).toHaveText('engine offline');
  await expect(page.locator('.connection')).toContainText('Connecting');
  await expect(page.locator('#ov-result .result-word')).toHaveText('Not run');
  await demo.stop();
  allow(problems, /503|Failed to load resource/);
});

test('a malformed state response is rejected, not rendered', async ({ page, problems }) => {
  await withDemo({}, async (demo) => {
    await page.route('**/api/state', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"nope":1}' }));
    await page.goto(`${demo.url}/#overview`);
    await expect(page.locator('#notice')).toHaveText('The server returned an invalid state response.');
  });
  allow(problems, /Failed to load resource/);
});

test('tampered session token: the engine refuses (403) and the UI says so', async ({ page, problems }) => {
  await withDemo({ approve: true }, async (demo) => {
    await open(page, demo, 'runs');
    await page.evaluate(() => document.querySelector('meta[name="ddg-session-token"]')!.setAttribute('content', 'forged'));
    await page.locator('#run-button').click();
    await expect(page.locator('#notice')).toHaveText('Session token is missing or invalid');
    await expect(page.locator('#notice')).toHaveClass(/notice-error/);
    expect((await demo.state()).report ?? null).toBeNull();
  });
  allow(problems, /403|Failed to load resource/);
});

test('double click runs once; controls lock while the engine works', async ({ page }) => {
  await withDemo({ approve: true }, async (demo) => {
    await open(page, demo, 'runs');
    const posts: string[] = [];
    page.on('request', (r) => { if (r.method() === 'POST') posts.push(new URL(r.url()).pathname); });
    await page.locator('#scenario-select').selectOption('regression');
    await page.locator('#run-button').dblclick();
    await expect(page.locator('#notice')).toHaveClass(/notice-pending/);
    await expect(page.locator('#run-button')).toBeDisabled();
    await expect(page.locator('#scenario-select')).toBeDisabled();
    await expect(page.locator('#notice')).toContainText('Run completed', { timeout: 180_000 });
    expect(posts).toEqual(['/api/run']);
    await expect(page.locator('#run-button')).toBeEnabled();
  });
});

test('stale report: refs moved after the run are flagged everywhere, rerun clears it', async ({ page }) => {
  await withDemo({ scenario: 'regression' }, async (demo) => {
    const before = (await demo.state()).report!;
    demo.git('update-ref', 'refs/heads/regression', demo.git('rev-parse', 'corrected'));
    expect((await demo.state()).report_stale).toBe(true);
    await open(page, demo, 'runs');
    await expect(page.locator('#stale-notice')).toBeVisible();
    await expect(page.locator('#run-result .result-word')).toHaveText('Stale');
    await expect(page.locator('#run-summary')).toHaveClass(/tone-inc/);
    await expect(page.locator('#run-summary .exit-chip')).toHaveText('exit —');
    await expect(page.locator('.nav-item[href="#runs"] .nav-state')).toHaveText('stale');
    await go(page, 'overview');
    await expect(page.locator('#attention')).toContainText('Report is stale.');
    await go(page, 'reports');
    await expect(view(page, 'reports').locator('.panel-head .tag').first()).toHaveText('Stale');
    await runScenario(page, 'regression');
    await expect(page.locator('#stale-notice')).toHaveCount(0);
    const after = (await demo.state()).report!;
    expect(after.head_sha).not.toBe(before.head_sha);
    await expect(page.locator('#run-result .result-word')).toHaveText('Checks passed'); // head now points at the corrected code
  });
});

test('host isolation is labelled UNSAFE in every place it appears', async ({ page }) => {
  await withDemo({ sandbox: 'host', scenario: 'regression' }, async (demo) => {
    await open(page, demo, 'overview');
    const iso = page.locator('.readout').filter({ hasText: 'Isolation' }).locator('dd');
    await expect(iso).toHaveText('host · UNSAFE');
    await expect(iso).toHaveClass(/is-fail/);
    await expect(view(page, 'overview').locator('.tag', { hasText: 'host · unsafe' })).toHaveClass(/tag-fail/);
    await expect(page.locator('#attention')).toContainText('Head ran without isolation.');
    await go(page, 'runs');
    await expect(page.locator('#run-sandbox')).toHaveText('host · UNSAFE');
    await expect(page.locator('#run-sandbox')).toHaveClass(/is-fail/);
    await go(page, 'reports');
    await expect(page.locator('#rep-meta')).toContainText('host (UNSAFE)');
  });
});

test('live provider failure is reported as a provider error, not a check result (offline)', async ({ page, problems }) => {
  // custom_cli with a command that exits non-zero: no network, and env wins over the repository .env file
  await withDemo({ env: { DDG_PROVIDER: 'custom_cli', DDG_CLI_COMMAND: JSON.stringify(['python', '-c', 'import sys; sys.exit(7)']), GEMINI_API_KEY: '' } }, async (demo) => {
    await open(page, demo, 'checks');
    await page.locator('#proposal-mode').selectOption('live');
    await page.locator('#propose-button').click();
    await expect(page.locator('#notice')).toHaveClass(/notice-error/, { timeout: 60_000 });
    await expect(page.locator('#check-id')).toHaveText('not recorded');
    await expect(page.locator('#validate-button')).toBeDisabled();
    expect((await demo.state()).draft ?? null).toBeNull();
    await expect(page.locator('#propose-button')).toBeEnabled();
  });
  allow(problems, /Failed to load resource/);
});

test('a second tab sees the shared report but keeps its own session history', async ({ page, browser }) => {
  await withDemo({ scenario: 'regression' }, async (demo) => {
    await open(page, demo, 'overview');
    await expect(page.locator('#st-runs')).toHaveText('1');
    const other = await browser.newContext();
    const tab = await other.newPage();
    await open(tab, demo, 'overview');
    await expect(tab.locator('#ov-result .result-word')).toHaveText('Failed');
    await expect(tab.locator('#st-runs')).toHaveText('1');
    await other.close();
  });
});

test('the proposal source choice survives refreshes until the user changes it', async ({ page }) => {
  await withDemo({}, async (demo) => {
    await open(page, demo, 'checks');
    await expect(page.locator('#proposal-mode')).toHaveValue('recorded');
    await page.locator('#proposal-mode').selectOption('live');
    await go(page, 'overview');
    await go(page, 'checks');
    await expect(page.locator('#proposal-mode')).toHaveValue('live');
  });
});
