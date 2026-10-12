// Every candidate head the demo offers, run through the UI. For each, the screen must show exactly what the
// engine returned (aggregate, exit code, verdict, reason, warnings, isolation), never anything greener.
import { startDemo, type Demo, type EngineState } from './harness';
import { expect, go, isolationText, open, runScenario, test } from './fixtures';

test.describe.configure({ mode: 'serial' });
let demo: Demo;
test.beforeAll(async () => { demo = await startDemo({ approve: true }); });
test.afterAll(async () => { await demo?.stop(); });

// Known engine contract (tests/e2e/test_lifecycle.py): scenario id -> [exit, aggregate, verdict].
// The last two are not in that table; the UI is still checked against the engine's own answer.
const KNOWN: Record<string, [string, string, string] | null> = {
  regression: ['1', 'FAILED', 'VIOLATION_INTRODUCED'],
  unseen_regression: ['1', 'FAILED', 'VIOLATION_INTRODUCED'],
  corrected: ['0', 'PASSED_CHECKS', 'CHECK_PASSED'],
  exception: ['0', 'PASSED_CHECKS', 'CHECK_PASSED'],
  unrelated: ['0', 'PASSED_CHECKS', 'CHECK_PASSED'],
  abort: ['1', 'FAILED', 'VIOLATION_INTRODUCED'],
  crashing: ['2', 'INCOMPLETE', 'NOT_CHECKED'],
  timing_out: ['2', 'INCOMPLETE', 'NOT_CHECKED'],
  missing_entrypoint: ['2', 'INCOMPLETE', 'NOT_CHECKED'],
  policy_edit: ['2', 'INCOMPLETE', 'CHECK_PASSED'],
  preexisting_failure: null,
  resolved: null,
};
const WORD: Record<string, [string, string, string]> = { PASSED_CHECKS: ['Checks passed', '0', 'pass'], FAILED: ['Failed', '1', 'fail'], INCOMPLETE: ['Incomplete', '2', 'inc'] };
const LABEL: Record<string, [string, string]> = {
  VIOLATION_INTRODUCED: ['Violation introduced', 'fail'], PRE_EXISTING_FAILURE: ['Pre-existing failure', 'pre'],
  RESOLVED: ['Resolved', 'pass'], CHECK_PASSED: ['Check passed', 'pass'], NOT_CHECKED: ['Not checked', 'inc'],
};

test('the candidate list is exactly the engine allowlist', async ({ page }) => {
  await open(page, demo, 'runs');
  const engine = (await demo.state()).scenarios ?? [];
  expect(engine.map((s) => s.id).sort()).toEqual(Object.keys(KNOWN).sort());
  await expect(page.locator('#scenario-select option')).toHaveText(engine.map((s) => s.label ?? s.id));
});

for (const id of Object.keys(KNOWN)) {
  test(`scenario ${id}: UI matches the engine`, async ({ page }) => {
    await open(page, demo, 'runs');
    await runScenario(page, id);
    const s: EngineState = await demo.state();
    const r = s.report!;
    const check = r.checks!.find((c) => c.verdict !== 'HISTORICAL_CHECK_IGNORED')!;
    const known = KNOWN[id];
    if (known) {
      expect([String(WORD[r.aggregate!]?.[1]), r.aggregate, check.verdict]).toEqual(known);
    }
    const [word, exit, tone] = WORD[r.aggregate!]!;
    const [label, vtone] = LABEL[check.verdict!] ?? LABEL.NOT_CHECKED!;

    await expect(page.locator('#run-summary')).toHaveClass(new RegExp(`tone-${tone}`));
    await expect(page.locator('#run-result .result-word')).toHaveText(word);
    await expect(page.locator('#run-summary .exit-chip')).toHaveText(`exit ${exit}`);
    await expect(page.locator('#run-head-ref')).toHaveText(s.scenarios!.find((x) => x.id === id)!.label!);
    await expect(page.locator('#run-base-ref')).toHaveText(r.base_ref!);
    await expect(page.locator('#run-cli')).toHaveText(`ddg run --base ${r.base_ref} --head ${r.head_ref}`);
    await expect(page.locator('#run-sandbox')).toHaveText(isolationText(demo.sandbox));
    await expect(page.locator('#result-groups .group')).toHaveClass(new RegExp(`g-${vtone}`));
    await expect(page.locator('#result-groups .h-label')).toHaveText(label);
    await expect(page.locator('#detail .tag')).toHaveText(label);
    await expect(page.locator('#detail .tag')).toHaveAttribute('title', check.verdict!);

    // warnings: every engine warning code is listed, none invented
    const codes = (r.warnings ?? []).map((w) => w.code ?? 'WARNING');
    if (codes.length) await expect(page.locator('#run-warnings code')).toHaveText(codes);
    else await expect(page.locator('#run-warnings')).toHaveCount(0);

    // an unobserved head is a hatched outline with the engine's reason; it is never drawn as a pass
    const chart = page.locator('#detail svg.chart');
    if (check.verdict === 'NOT_CHECKED') {
      await expect(chart.locator('rect.j-inc')).toHaveCount(1);
      const reason = check.error ?? check.head?.error ?? '';
      if (reason) await expect(page.locator('#detail-explain')).toContainText(reason.split('\n')[0]!.slice(0, 40));
    }
    if (check.head?.status === 'FAIL') await expect(chart.locator('rect.j-fail').first()).toBeVisible();
    if (r.aggregate !== 'PASSED_CHECKS') await expect(page.locator('#run-summary')).not.toHaveClass(/tone-pass/);

    // the rest of the product agrees with the run
    await go(page, 'overview');
    await expect(page.locator('#ov-result .result-word')).toHaveText(word);
    await expect(page.locator('#ov-check .enum')).toHaveText(check.verdict!);
    const count = page.locator(`#ov-outcomes .o-${vtone}`).filter({ hasText: label }).locator('.outcome-n');
    await expect(count).toHaveText('1');
    if (r.aggregate === 'INCOMPLETE') await expect(page.locator('#attention-count')).not.toHaveText('0');
    await go(page, 'reports');
    await expect(page.locator('#rep-rows .enum')).toHaveText(check.verdict!);
    if (codes.length) await expect(page.locator('#rep-warnings code')).toHaveText(codes);
  });
}
