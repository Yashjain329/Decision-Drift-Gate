// The whole product lifecycle driven only through the UI, on a fresh unapproved demo, checking every block of
// every view at each stage: empty → drafted → calibrated → approved → failed run → passing run → history.
import { readFileSync } from 'node:fs';
import { startDemo, type Demo } from './harness';
import { expect, go, isolationText, open, runScenario, test, view } from './fixtures';

test.describe.configure({ mode: 'serial' });
let demo: Demo;
test.beforeAll(async () => { demo = await startDemo(); });
test.afterAll(async () => { await demo?.stop(); });

const readout = (page: import('@playwright/test').Page, label: string) =>
  page.locator('.readout').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) }).locator('dd');
const navState = (page: import('@playwright/test').Page, id: string) => page.locator(`.nav-item[href="#${id}"] .nav-state`);
const flow = (page: import('@playwright/test').Page, n: number) => page.locator('.flow-step').nth(n - 1);

test('fresh demo: every view shows honest empty states', async ({ page }) => {
  await open(page, demo, 'overview');
  await test.step('top bar and rail', async () => {
    await expect(readout(page, 'Latest run')).toHaveText('no run yet');
    await expect(readout(page, 'Exit')).toHaveText('—');
    await expect(readout(page, 'Approver')).toHaveText('not recorded');
    await expect(readout(page, 'Isolation')).toHaveText('no run yet');
    await expect(page.locator('.ws-meta')).toHaveText('no approved base');
    await expect(navState(page, 'decisions')).toHaveText('1 active');
    for (const id of ['checks', 'runs', 'approvals', 'reports']) await expect(navState(page, id)).toHaveCount(0);
    await expect(navState(page, 'settings')).toHaveText('recorded');
  });
  await test.step('overview', async () => {
    const ov = view(page, 'overview');
    await expect(ov.locator('#ov-result .result-word')).toHaveText('Not run');
    await expect(ov.locator('#ov-signal .exit-chip')).toHaveCount(0);
    await expect(ov.locator('#ov-summary')).toHaveText('No check drafted.');
    await expect(ov.locator('#ov-action')).toHaveAttribute('href', '#checks');
    await expect(ov.locator('#ov-action-text')).toHaveText('Draft a check');
    await expect(ov.locator('#latest-empty')).toBeVisible();
    await expect(ov.locator('.outcome-n')).toHaveText(['—', '—', '—', '—', '—']);
    await expect(ov.locator('#st-approved')).toHaveText('0');
    await expect(ov.locator('#st-approved-note')).toHaveText('none yet');
    await expect(ov.locator('#st-decisions')).toHaveText('1');
    await expect(ov.locator('#st-decisions-note')).toHaveText('DEC-002');
    await expect(ov.locator('#st-calibration')).toHaveText('No draft');
    await expect(ov.locator('#st-runs')).toHaveText('0');
    await expect(ov.locator('#history-chart')).toHaveAttribute('aria-label', 'No runs in this tab yet');
    await expect(ov.locator('#attention-count')).toHaveText('1');
  });
  await test.step('decisions', async () => {
    await go(page, 'decisions');
    const items = page.locator('#decision-list > li');
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toHaveClass(/is-active/);
    await expect(items.nth(0)).toContainText('DEC-002');
    await expect(items.nth(0)).toContainText('Active');
    await expect(items.nth(0)).toContainText('Permitted exception');
    await expect(items.nth(0)).not.toContainText('protected by');
    await expect(items.nth(1)).toHaveClass(/is-superseded/);
    await expect(items.nth(1)).toContainText('DEC-001');
    await expect(items.nth(1)).toContainText('Superseded');
  });
  await test.step('check studio', async () => {
    await go(page, 'checks');
    const cs = view(page, 'checks');
    await expect(cs.locator('.page-head .tag')).toHaveText(['Calibration · not run', 'Approval · pending']);
    await expect(page.locator('#propose-button')).toBeEnabled();
    await expect(page.locator('#validate-button')).toBeDisabled();
    await expect(page.locator('#check-id')).toHaveText('not recorded');
    await expect(page.locator('#matrix-body tr')).toHaveCount(3);
    await expect(page.locator('#matrix-body .tag')).toHaveText(['Not run', 'Not run', 'Not run']);
    await expect(cs.locator('svg.chart')).toHaveCount(0);
  });
  await test.step('runs', async () => {
    await go(page, 'runs');
    await expect(page.locator('#scenario-select')).toBeDisabled();
    await expect(page.locator('#scenario-select option')).toHaveText(['Approve a check first']);
    await expect(page.locator('#run-button')).toBeDisabled();
    await expect(view(page, 'runs').locator('.empty')).toContainText('No run yet');
    await expect(page.locator('#run-content')).toHaveCount(0);
  });
  await test.step('approvals', async () => {
    await go(page, 'approvals');
    await expect(page.locator('#approval-state')).toHaveText('Not eligible yet');
    await expect(flow(page, 1)).toContainText('Draft a proposal first.');
    await expect(flow(page, 1)).toHaveClass(/is-current/);
    await expect(page.locator('#approve-button')).toBeDisabled();
    await expect(page.locator('#approval-record')).toHaveCount(0);
    await expect(page.locator('#git-state')).toHaveText('Not yet verified');
  });
  await test.step('reports and settings', async () => {
    await go(page, 'reports');
    await expect(page.locator('#download-report')).toBeDisabled();
    await expect(view(page, 'reports').locator('.empty')).toContainText('No report yet');
    await go(page, 'settings');
    await expect(view(page, 'settings').locator('.kv-stack')).toContainText('No proposal has been drafted.');
  });
});

test('draft a recorded proposal through Check Studio', async ({ page }) => {
  await open(page, demo, 'checks');
  await page.locator('#proposal-mode').selectOption('recorded');
  await page.locator('#propose-button').click();
  await expect(page.locator('#notice')).toHaveText('Proposal drafted. Validate it next.');
  await expect(page.locator('#notice')).toHaveClass(/notice-success/);
  await expect(page.locator('#check-id')).toHaveText('CHK-001');
  await expect(view(page, 'checks').locator('pre.code-lg')).toHaveText('expect unique_jobs == 1\nexpect returned_job_exists == true');
  await expect(page.locator('#check-decision')).toContainText('DEC-002');
  await expect(page.locator('#check-scenario')).toHaveText('commit_then_503');
  await expect(page.locator('#citation-summary')).toHaveText('Grounded in 2 citations');
  await expect(page.locator('#check-citation')).toBeHidden();
  await page.locator('#citation-summary').click();
  await expect(page.locator('#check-citation li')).toHaveCount(2);
  await expect(page.locator('#validate-button')).toBeEnabled();
  await expect(navState(page, 'checks')).toHaveText('draft');
  await go(page, 'overview');
  await expect(page.locator('#ov-action-text')).toHaveText('Validate proposal');
  await expect(page.locator('#st-calibration')).toHaveText('Not run');
  await go(page, 'decisions');
  await expect(page.locator('#decision-list > li').first()).toContainText('protected by CHK-001');
  await go(page, 'settings');
  await expect(view(page, 'settings').locator('.kv-stack')).toContainText('gemini-3.8-flash');
  await expect(view(page, 'settings').locator('.kv-stack')).toContainText('recorded capture');
  await go(page, 'approvals');
  await expect(flow(page, 1)).toHaveClass(/is-done/);
  await expect(page.locator('#approve-button')).toBeDisabled();
});

test('validate: three fixtures, chart, eligibility is not approval', async ({ page }) => {
  await open(page, demo, 'checks');
  await page.locator('#validate-button').click();
  await expect(page.locator('#notice')).toHaveText('Calibration finished.', { timeout: 180_000 });
  await expect(page.locator('#matrix-body .tag')).toHaveText(['Valid', 'Valid', 'Valid']);
  await expect(page.locator('#matrix-body tr').nth(0)).toContainText('Fail');
  await expect(page.locator('#matrix-body tr').nth(0).locator('td').nth(3)).toHaveText('2');
  await expect(page.locator('#calibration-explanation')).toContainText('3 of 3 fixtures matched');
  const chart = view(page, 'checks').locator('svg.chart');
  await expect(chart).toHaveAttribute('aria-label', /Known-bad 2 jobs.*Corrected 1 job.*Exception 1 job/);
  await expect(chart.locator('.exp-label')).toHaveText('expected 1');
  await expect(view(page, 'checks').locator('.page-head .tag')).toHaveText(['Calibration · eligible', 'Approval · pending']);
  await expect(navState(page, 'checks')).toHaveText('eligible');
  await go(page, 'overview');
  await expect(page.locator('#st-calibration')).toHaveText('Eligible');
  await expect(page.locator('#st-calibration-note')).toHaveText('3 of 3 fixtures');
  await expect(page.locator('#ov-action')).toHaveAttribute('href', '#approvals');
});

test('approve: whitespace is rejected, values are trimmed, approval is not shown as verified', async ({ page }) => {
  await open(page, demo, 'approvals');
  await expect(page.locator('#approval-state')).toHaveText('Pending');
  await expect(flow(page, 3)).toHaveClass(/is-current/);
  const button = page.locator('#approve-button');
  await expect(button).toBeDisabled();
  await page.locator('#reviewer').fill('   ');
  await page.locator('#reason').fill('   ');
  await expect(button).toBeDisabled();
  await page.locator('#reviewer').fill('  Dana Reviewer  ');
  await expect(button).toBeDisabled();
  await page.locator('#reason').fill('  Checked bad, good and exception fixtures  ');
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.locator('#notice')).toContainText('Approval recorded.');
  await expect(page.locator('#approval-form')).toHaveCount(0);
  await expect(page.locator('#rec-label')).toHaveText('Dana Reviewer');
  await expect(page.locator('#rec-note')).toHaveText('Checked bad, good and exception fixtures');
  await expect(page.locator('#rec-check')).toHaveText('CHK-001');
  await expect(page.locator('#rec-digest')).toBeHidden();
  await page.locator('#approval-record summary').click();
  await expect(page.locator('#rec-digest')).toHaveText(/^[0-9a-f]{64}$/);
  await expect(page.locator('#approval-state')).toHaveText('Recorded · awaiting verification');
  await expect(page.locator('#git-state')).toHaveText('Not yet verified');
  await expect(flow(page, 4)).toContainText('Verified at next run.');
  await expect(readout(page, 'Approver')).toHaveText('recorded · not yet verified');
  await expect(navState(page, 'approvals')).toHaveText('recorded');
  await go(page, 'checks');
  await expect(page.locator('#propose-button')).toBeDisabled();
  await expect(page.locator('#proposal-mode')).toBeDisabled();
  await expect(page.locator('#validate-button')).toBeDisabled();
  await expect(view(page, 'checks').locator('.page-head .tag').nth(1)).toHaveText('Approval · recorded');
  await go(page, 'runs');
  await expect(page.locator('#scenario-select')).toBeEnabled();
  await expect(page.locator('#scenario-select option')).toHaveCount(12);
  await expect(page.locator('#run-button')).toBeEnabled();
  await go(page, 'overview');
  await expect(page.locator('#ov-action-text')).toHaveText('Start a run');
});

test('failed run: every block of the inspector, overview, approvals and report', async ({ page }) => {
  await open(page, demo, 'runs');
  await runScenario(page, 'regression');
  const engine = (await demo.state()).report!;
  const check = engine.checks![0]!;
  await expect(page.locator('#notice')).toHaveText('Run completed: Failed, exit 1.');
  await expect(page.locator('#notice')).toHaveClass(/notice-error/);

  await test.step('signal and trust boundary', async () => {
    await expect(page.locator('#run-summary')).toHaveClass(/tone-fail/);
    await expect(page.locator('#run-result .result-word')).toHaveText('Failed');
    await expect(page.locator('#run-summary .exit-chip')).toHaveText('exit 1');
    await expect(page.locator('#run-summary .exit-chip')).toHaveAttribute('title', 'FAILED');
    await expect(page.locator('#run-summary-text')).toHaveText('Passed on base, failed on head. This change introduces the violation.');
    await expect(page.locator('#run-base-ref')).toHaveText('approved-base');
    await expect(page.locator('#run-head-ref')).toHaveText('Retry regression');
    await expect(page.locator('#view-runs .rev-base code')).toHaveText(engine.base_sha!.slice(0, 10));
    await expect(page.locator('#view-runs .rev-base code')).toHaveAttribute('title', engine.base_sha!);
    await expect(page.locator('#view-runs .rev-head code')).toHaveAttribute('title', engine.head_sha!);
    await expect(page.locator('#run-sandbox')).toHaveText(isolationText(demo.sandbox));
    await expect(page.locator('#run-cli')).toHaveText('ddg run --base approved-base --head regression');
  });
  await test.step('results and detail', async () => {
    await expect(page.locator('#result-groups .group')).toHaveCount(1);
    await expect(page.locator('#result-groups .group')).toHaveClass(/g-fail/);
    await expect(page.locator('#result-groups .h-label')).toHaveText('Violation introduced');
    await expect(page.locator('#result-groups .enum')).toHaveText('VIOLATION_INTRODUCED');
    await expect(page.locator('.result-row')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('.result-row .rr-obs')).toHaveText('base PASS · 1 job → head FAIL · 2 jobs');
    await expect(page.locator('#results-zero')).toHaveText('None pre-existing failure · resolved · check passed · not checked');
    await expect(page.locator('#run-warnings')).toHaveCount(0);
    await expect(page.locator('#detail-check')).toHaveText(check.check_id);
    await expect(page.locator('#detail .tag')).toHaveText('Violation introduced');
    await expect(page.locator('#detail-decision')).toContainText('DEC-002');
    const chart = page.locator('#detail svg.chart');
    await expect(chart).toHaveAttribute('aria-label', /Base PASS · 1 job\. Head FAIL · 2 jobs\. Expected 1\./);
    await expect(chart.locator('rect.j-fail')).toHaveCount(2);
    await expect(chart.locator('rect.j-pass')).toHaveCount(1);
    await expect(chart.locator('rect.j-inc')).toHaveCount(0);
  });
  await test.step('evidence on demand', async () => {
    const traces = page.locator('#ev-traces');
    await expect(traces).toHaveAttribute('open', '');
    await expect(traces.locator('.summary-meta')).toHaveText('base 4 events · head 6 events');
    await expect(traces.locator('li.ev-dup')).toHaveCount(1);
    await expect(traces.locator('li.ev-dup')).toContainText('duplicate');
    const diff = page.locator('#detail-diff-block');
    await expect(diff).not.toHaveAttribute('open', '');
    await expect(diff.locator('.summary-meta')).toHaveText(/^\+\d+ −\d+$/);
    await diff.locator('summary').click();
    await expect(page.locator('#detail-diff')).toContainText('diff --git');
    const ev = page.locator('.evidence-stack details');
    await expect(ev.filter({ hasText: 'Approved check' }).locator('.summary-meta')).toHaveText('2 assertions');
    await expect(ev.filter({ hasText: 'Approval provenance' }).locator('.summary-meta')).toHaveText('verified · ddg-demo@example.invalid');
    await expect(ev.filter({ hasText: 'Ordinary tests' }).locator('.summary-meta')).toHaveText('both passed');
    await traces.locator('summary').click();
    await expect(traces).not.toHaveAttribute('open', '');
  });
  await test.step('chrome, overview, approvals, reports agree', async () => {
    await expect(readout(page, 'Latest run')).toHaveText('Failed');
    await expect(readout(page, 'Exit')).toHaveText('1');
    await expect(readout(page, 'Approver')).toHaveText('verified · ddg-demo@example.invalid');
    await expect(readout(page, 'Isolation')).toHaveText(isolationText(demo.sandbox));
    await expect(navState(page, 'runs')).toHaveText('failed');
    await expect(navState(page, 'approvals')).toHaveText('verified');
    await go(page, 'overview');
    await expect(page.locator('#ov-signal')).toHaveClass(/tone-fail/);
    await expect(page.locator('#ov-check')).toHaveText('CHK-001 · DEC-002 · VIOLATION_INTRODUCED');
    await expect(page.locator('#ov-action-text')).toHaveText('Inspect evidence');
    await expect(page.locator('.outcome-n')).toHaveText(['1', '0', '0', '0', '0']);
    await expect(page.locator('#attention li').first()).toContainText('DEC-002 regressed');
    await expect(page.locator('#st-runs')).toHaveText('1');
    await expect(page.locator('#history-chart')).toHaveAttribute('aria-label', 'Runs this session: Retry regression Failed, 2 jobs');
    await go(page, 'approvals');
    await expect(page.locator('#approval-state')).toHaveText('Verified');
    await expect(flow(page, 4)).toHaveClass(/is-done/);
    await expect(page.locator('#rec-author')).toHaveText('ddg-demo@example.invalid · on allowlist');
    await expect(page.locator('#rec-signature')).toHaveText('unsigned');
    await go(page, 'reports');
    await expect(view(page, 'reports').locator('.panel-head .tag').nth(1)).toHaveText('Failed · exit 1');
    await expect(page.locator('#rep-rows tr')).toHaveCount(1);
    await expect(page.locator('#rep-rows tr')).toContainText('Violation introduced');
    await expect(page.locator('#rep-rows .enum')).toHaveText('VIOLATION_INTRODUCED');
    await expect(page.locator('#rep-meta')).toContainText(engine.head_sha!);
    await expect(page.locator('#rep-warnings')).toHaveText('No warnings.');
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-report').click()]);
    expect(download.suggestedFilename()).toMatch(/^ddg-report-regression-\d{4}-\d{2}-\d{2}T\d{6}Z\.json$/);
    const saved = JSON.parse(readFileSync((await download.path())!, 'utf8'));
    expect(saved).toEqual(engine);
  });
});

test('passing run, notice tones, and the per-tab history', async ({ page }) => {
  await open(page, demo, 'runs');
  await runScenario(page, 'corrected');
  await expect(page.locator('#notice')).toHaveText('Run completed: Checks passed, exit 0.');
  await expect(page.locator('#notice')).toHaveClass(/notice-success/);
  await expect(page.locator('#run-result .result-word')).toHaveText('Checks passed');
  await expect(page.locator('#result-groups .h-label')).toHaveText('Check passed');
  await go(page, 'overview');
  await expect(page.locator('#attention li')).toHaveCount(1);
  if (demo.sandbox === 'host') {
    // even a passing run is not "nothing to do" when head code ran without isolation
    await expect(page.locator('#attention li')).toContainText('Head ran without isolation.');
    await expect(page.locator('#attention-count')).toHaveText('1');
  } else {
    await expect(page.locator('#attention li')).toContainText('Nothing needs attention.');
    await expect(page.locator('#attention-count')).toHaveText('0');
  }
  // a new tab records the report it opened on (regression) and then the corrected run
  await expect(page.locator('#st-runs')).toHaveText('2');
  await page.reload();
  await expect(page.locator('#st-runs')).toHaveText('2'); // reload does not double count
  await runScenario(page, 'crashing');
  await expect(page.locator('#notice')).toHaveText('Run completed: Incomplete, exit 2.');
  await expect(page.locator('#notice')).toHaveClass(/notice-warn/);
  await go(page, 'overview');
  await expect(page.locator('#st-runs')).toHaveText('3');
  await expect(page.locator('#history-chart rect.j-fail')).toHaveCount(1);
  await expect(page.locator('#history-chart rect.j-pass')).toHaveCount(1);
  await expect(page.locator('#history-chart rect.j-inc')).toHaveCount(1);
});
