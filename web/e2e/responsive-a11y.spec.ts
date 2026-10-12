// Layout at every breakpoint, touch targets, keyboard, reduced motion, landmarks, chart labels, and an axe scan
// of every view in a fully populated state.
import AxeBuilder from '@axe-core/playwright';
import { startDemo, type Demo } from './harness';
import { VIEWS, expect, go, open, overflows, test, view } from './fixtures';

let demo: Demo;
test.beforeAll(async () => { demo = await startDemo({ scenario: 'regression' }); });
test.afterAll(async () => { await demo?.stop(); });

const SIZES = [
  { name: 'phone 360', width: 360, height: 780 },
  { name: 'phone 390', width: 390, height: 844 },
  { name: 'small 560', width: 560, height: 900 },
  { name: 'tablet 900', width: 900, height: 1000 },
  { name: 'laptop 1180', width: 1180, height: 800 },
  { name: 'desktop 1440', width: 1440, height: 900 },
  { name: 'wide 1920', width: 1920, height: 1080 },
];

for (const size of SIZES) {
  test(`${size.name}: no view scrolls sideways`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await open(page, demo, 'overview');
    for (const id of VIEWS) {
      await go(page, id);
      expect(await overflows(page), `${id} overflows at ${size.width}px`).toBe(false);
    }
  });
}

test('phone: rail becomes a scrolling bar and touch targets are at least 44px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, demo, 'overview');
  const list = page.locator('.nav-list');
  expect(await list.evaluate((el) => getComputedStyle(el).display)).toBe('flex');
  for (const id of VIEWS) {
    await go(page, id);
    const small = await page.locator(`#view-${id}`).evaluate((root) =>
      [...root.querySelectorAll<HTMLElement>('button, select, input, textarea, a.button')]
        .filter((el) => el.offsetParent !== null)
        .map((el) => ({ id: el.id || el.className, h: el.getBoundingClientRect().height }))
        .filter((x) => Math.round(x.h) < 44)); // round: sub-pixel layout reports 43.99997 for 44
    expect(small, `small controls on ${id}`).toEqual([]);
  }
  const navHeights = await page.locator('.nav-item').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  expect(Math.min(...navHeights)).toBeGreaterThanOrEqual(44);
});

test('keyboard: skip link, rail, and Enter navigation with a visible focus ring', async ({ page }) => {
  await open(page, demo, 'overview');
  await page.keyboard.press('Tab');
  await expect(page.locator('a.skip-link')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator('a.brand')).toBeFocused();
  let guard = 0;
  while (!(await page.locator('.nav-item[href="#runs"]').evaluate((el) => el === document.activeElement)) && guard++ < 20) await page.keyboard.press('Tab');
  const outline = await page.locator('.nav-item[href="#runs"]').evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe('none');
  await page.keyboard.press('Enter');
  await expect(view(page, 'runs')).toBeVisible();
  await expect(page.locator('.nav-item[href="#runs"]')).toHaveAttribute('aria-current', 'page');
  // result rows are real buttons: reachable and operable from the keyboard
  await page.locator('.result-row').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.result-row')).toHaveAttribute('aria-pressed', 'true');
});

test('reduced motion turns animation off', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page, demo, 'runs');
  const anims = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>('.view:not([hidden]), .chart .bar')]
    .map((el) => getComputedStyle(el).animationName));
  expect(anims.length).toBeGreaterThan(0);
  expect(anims.every((a) => a === 'none')).toBe(true);
});

test('landmarks, headings and labelled charts on every view', async ({ page }) => {
  await open(page, demo, 'overview');
  await expect(page.locator('header.topbar')).toHaveCount(1);
  await expect(page.locator('nav[aria-label="Destinations"]')).toHaveCount(1);
  await expect(page.locator('main#main')).toHaveCount(1);
  await expect(page.locator('#notice')).toHaveAttribute('aria-live', 'polite');
  for (const id of VIEWS) {
    await go(page, id);
    const v = view(page, id);
    await expect(v.locator('h1')).toHaveCount(1);
    const labelledBy = await v.getAttribute('aria-labelledby');
    await expect(page.locator(`#${labelledBy}`)).toHaveText(/\S/);
    for (const chart of await v.locator('svg.chart').all()) {
      await expect(chart).toHaveAttribute('role', 'img');
      await expect(chart).toHaveAttribute('aria-label', /\S/);
    }
  }
});

for (const id of VIEWS) {
  test(`axe: no serious or critical WCAG A/AA violations on ${id}`, async ({ page }) => {
    await open(page, demo, id);
    // open every disclosure so hidden evidence is scanned too
    await page.locator(`#view-${id} details:not([open]) > summary`).evaluateAll((els) => els.forEach((e) => (e as HTMLElement).click()));
    const result = await new AxeBuilder({ page }).include(`#view-${id}`).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    const bad = result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
    expect(bad).toEqual([]);
  });
}

test('axe: shell (top bar and rail)', async ({ page }) => {
  await open(page, demo, 'overview');
  const result = await new AxeBuilder({ page }).include('header.topbar').include('nav.rail').withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([]);
});
