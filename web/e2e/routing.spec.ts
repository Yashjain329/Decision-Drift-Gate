// Routing: hash router, deep links, aliases, invalid hashes, history, reload, in-page links, skip link.
import { startDemo, type Demo } from './harness';
import { VIEWS, expect, expectOnlyView, go, open, test, view } from './fixtures';

let demo: Demo;
test.beforeAll(async () => { demo = await startDemo({ scenario: 'regression' }); });
test.afterAll(async () => { await demo?.stop(); });

test('no hash opens Overview and writes #overview', async ({ page }) => {
  await page.goto(`${demo.url}/`);
  await expectOnlyView(page, 'overview');
});

for (const id of VIEWS) {
  test(`deep link #${id} opens only that view`, async ({ page }) => {
    await open(page, demo, id);
    await expectOnlyView(page, id);
    await expect(view(page, id).locator('h1')).toHaveCount(1);
    await expect(page).toHaveTitle('Decision Drift Gate');
  });
}

for (const [alias, target] of [['decision', 'decisions'], ['approval', 'approvals'], ['review', 'runs']] as const) {
  test(`legacy #${alias} redirects to #${target} (deep link and in-app)`, async ({ page }) => {
    await open(page, demo, alias);
    await expectOnlyView(page, target);
    await go(page, 'overview');
    await page.evaluate((h) => { location.hash = h; }, alias);
    await expectOnlyView(page, target);
  });
}

test('unknown hash on load falls back to Overview and rewrites the URL', async ({ page }) => {
  for (const bad of ['nope', 'RUNS', 'runs?x=1', 'view-runs', '']) {
    await page.goto(`${demo.url}/#${bad}`);
    await expectOnlyView(page, 'overview');
  }
});

test('unknown hash after navigation keeps the current view and restores its hash', async ({ page }) => {
  await open(page, demo, 'runs');
  await page.evaluate(() => { location.hash = 'definitely-not-a-view'; });
  await expectOnlyView(page, 'runs');
});

test('every rail item navigates; exactly one is current', async ({ page }) => {
  await open(page, demo, 'overview');
  for (const id of [...VIEWS].reverse()) await go(page, id);
});

test('browser back and forward walk the view history', async ({ page }) => {
  await open(page, demo, 'overview');
  await go(page, 'checks');
  await go(page, 'runs');
  await go(page, 'reports');
  await page.goBack(); await expectOnlyView(page, 'runs');
  await page.goBack(); await expectOnlyView(page, 'checks');
  await page.goBack(); await expectOnlyView(page, 'overview');
  await page.goForward(); await expectOnlyView(page, 'checks');
});

test('reload keeps the current view', async ({ page }) => {
  await open(page, demo, 'approvals');
  await page.reload();
  await expectOnlyView(page, 'approvals');
});

test('brand link returns to Overview', async ({ page }) => {
  await open(page, demo, 'reports');
  await page.locator('a.brand').click();
  await expectOnlyView(page, 'overview');
});

test('navigating scrolls back to the top', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 600 });
  await open(page, demo, 'runs');
  await page.mouse.wheel(0, 2000);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await go(page, 'decisions');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});

test('in-page links route correctly', async ({ page }) => {
  await open(page, demo, 'overview');
  // the signal band's single next action for a failed run
  await expect(page.locator('#ov-action')).toHaveAttribute('href', '#runs');
  await page.locator('#ov-action').click();
  await expectOnlyView(page, 'runs');
  await page.locator('#view-runs a.text-link[href="#reports"]').click();
  await expectOnlyView(page, 'reports');
  await go(page, 'decisions');
  await page.locator('#view-decisions a[href="#checks"]').click();
  await expectOnlyView(page, 'checks');
  await go(page, 'overview');
  await page.locator('#attention a').first().click();
  await expectOnlyView(page, 'runs');
});

test('skip link moves to the workspace without breaking the route', async ({ page }) => {
  await open(page, demo, 'checks');
  await page.keyboard.press('Tab');
  await expect(page.locator('a.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expectOnlyView(page, 'checks');
});
