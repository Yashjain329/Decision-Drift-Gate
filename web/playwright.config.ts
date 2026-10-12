import { defineConfig, devices } from '@playwright/test';

// UI end-to-end suite. Each test starts its own real `ddg serve` (see e2e/harness.ts), so no webServer block.
// The viewer under test is the committed static build in web/out: run `npm run build` first after UI changes.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
