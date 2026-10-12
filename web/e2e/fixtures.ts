// Shared fixtures and page helpers. Every test fails on any console error, page error or failed request.
import { test as base, expect, type Page } from '@playwright/test';
import { startDemo, type Demo } from './harness';

export const VIEWS = ['overview', 'decisions', 'checks', 'runs', 'approvals', 'reports', 'settings'] as const;
export type ViewId = (typeof VIEWS)[number];

type Fixtures = { problems: string[] };

export const test = base.extend<Fixtures>({
  problems: [async ({ page }, use) => {
    const problems: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') problems.push(`console ${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
    page.on('requestfailed', (r) => problems.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`));
    await use(problems);
    expect(problems, 'browser reported problems').toEqual([]);
  }, { auto: true }],
});
export { expect };

/** Open the viewer at a hash and wait until the engine state has rendered. */
export async function open(page: Page, demo: Demo, hash: ViewId | string = 'overview'): Promise<void> {
  await page.goto(`${demo.url}/#${hash}`);
  await expect(page.locator('.connection')).toContainText('Local engine connected');
}

export const view = (page: Page, id: ViewId) => page.locator(`#view-${id}`);

export async function expectOnlyView(page: Page, id: ViewId): Promise<void> {
  await expect(view(page, id)).toBeVisible();
  for (const other of VIEWS) if (other !== id) await expect(view(page, other)).toBeHidden();
  await expect(page.locator(`.nav-item[href="#${id}"]`)).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('.nav-item[aria-current="page"]')).toHaveCount(1);
  expect(new URL(page.url()).hash).toBe(`#${id}`);
}

export async function go(page: Page, id: ViewId): Promise<void> {
  await page.locator(`.nav-item[href="#${id}"]`).click();
  await expectOnlyView(page, id);
}

/** Run a scenario through the UI (select + button) and wait for the engine's completion notice. */
export async function runScenario(page: Page, scenario: string): Promise<void> {
  await go(page, 'runs');
  await page.locator('#scenario-select').selectOption(scenario);
  await page.locator('#run-button').click();
  await expect(page.locator('#notice')).toContainText('Run completed', { timeout: 180_000 });
}

/** True when the document is wider than the viewport (horizontal scrolling). */
export const overflows = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);

/** How the UI must name an isolation mode: host execution is always called out as unsafe. */
export const isolationText = (sandbox: string) => (sandbox === 'host' ? 'host · UNSAFE' : sandbox);

export async function withDemo<T>(opts: Parameters<typeof startDemo>[0], fn: (demo: Demo) => Promise<T>): Promise<T> {
  const demo = await startDemo(opts);
  try { return await fn(demo); } finally { await demo.stop(); }
}
