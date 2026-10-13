// Product vocabulary and pure derivations. No React here, so every view and any test can share it.
import type { Check, CheckResult, DdgState, FixtureKey, Observation, Report, Scenario } from './types';

export type Tone = 'pass' | 'fail' | 'pre' | 'inc' | 'muted';
export type Glyph =
  | 'overview' | 'decisions' | 'checks' | 'runs' | 'approvals' | 'reports' | 'settings' | 'terminal' | 'play'
  | 'check' | 'x' | 'help' | 'history' | 'resolved' | 'clock' | 'minus' | 'alert' | 'commit' | 'box' | 'lock'
  | 'user' | 'download' | 'arrow' | 'git';

// Human label first; the exact enum stays available as secondary audit metadata.
export interface Outcome { verdict: string; label: string; tone: Tone; glyph: Glyph; desc: string }
export const OUTCOMES: Outcome[] = [
  { verdict: 'VIOLATION_INTRODUCED', label: 'Violation introduced', tone: 'fail', glyph: 'x', desc: 'Passes on base, fails on head.' },
  { verdict: 'PRE_EXISTING_FAILURE', label: 'Pre-existing failure', tone: 'pre', glyph: 'history', desc: 'Already fails on base. Not this change.' },
  { verdict: 'RESOLVED', label: 'Resolved', tone: 'pass', glyph: 'resolved', desc: 'Fails on base, passes on head.' },
  { verdict: 'CHECK_PASSED', label: 'Check passed', tone: 'pass', glyph: 'check', desc: 'Passes on both revisions.' },
  { verdict: 'NOT_CHECKED', label: 'Not checked', tone: 'inc', glyph: 'help', desc: 'No result established.' },
];
/** Unknown verdicts are treated as NOT_CHECKED: never as a pass. */
export const outcomeOf = (verdict?: string): Outcome => OUTCOMES.find((o) => o.verdict === verdict) ?? OUTCOMES[4]!;

export const AGGREGATE_LABEL: Record<string, string> = { PASSED_CHECKS: 'Checks passed', FAILED: 'Failed', INCOMPLETE: 'Incomplete' };

export const VERDICT_TEXT: Record<string, string> = {
  VIOLATION_INTRODUCED: 'Passed on base, failed on head. This change introduces the violation.',
  PRE_EXISTING_FAILURE: 'Already failing on base. Not caused by this change.',
  RESOLVED: 'Failed on base, passes on head. This change fixes it.',
  CHECK_PASSED: 'Held on both revisions.',
  NOT_CHECKED: 'No result for both revisions.',
};

export const SIGNATURE: Record<string, string> = {
  G: 'good signature', N: 'unsigned', B: 'bad signature', U: 'untrusted signature',
  E: 'signature could not be checked', X: 'expired signature', Y: 'expired key', R: 'revoked key',
};

export interface Fixture { key: FixtureKey; name: string; short: string; expect: 'PASS' | 'FAIL' }
export const FIXTURES: Fixture[] = [
  { key: 'bad', name: 'Known-bad implementation', short: 'Known-bad', expect: 'FAIL' },
  { key: 'good', name: 'Corrected implementation', short: 'Corrected', expect: 'PASS' },
  { key: 'exception', name: 'Documented exception', short: 'Exception', expect: 'PASS' },
];

// ---- small helpers -----------------------------------------------------------------------------------
export const short = (sha?: string | null, n = 10): string => (typeof sha === 'string' && sha ? sha.slice(0, n) : '—');
export const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`;
export const clock = (iso?: string | null): string => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.valueOf()) ? d.toISOString().slice(11, 19) : '—';
};
export const orText = (value: unknown, fallback = 'not recorded'): string =>
  value === undefined || value === null || value === '' ? fallback : String(value);

// ---- report derivations ------------------------------------------------------------------------------
export const realChecks = (report?: Report | null): CheckResult[] =>
  Array.isArray(report?.checks) ? report.checks.filter((c) => c && c.verdict !== 'HISTORICAL_CHECK_IGNORED') : [];
export const warningCodes = (report?: Report | null): string[] =>
  [...new Set((report?.warnings ?? []).map((w) => w?.code).filter((c): c is string => Boolean(c)))];
/** The check that best explains the run: the first non-passing one, else the first. */
export const focusCheck = (report?: Report | null): CheckResult | undefined => {
  const checks = realChecks(report);
  return checks.find((c) => c.verdict !== 'CHECK_PASSED') ?? checks[0];
};

/** A real repository is shown read-only: records come from Git, actions run through the ddg CLI. */
export const isReadOnly = (s?: DdgState | null): boolean => s?.source?.kind === 'repository';
/** Job-client scenarios are a name; function scenarios are {path, function}. */
export const scenarioText = (s?: Check['scenario']): string =>
  !s ? '—' : typeof s === 'string' ? s : `${s.path ?? '?'} · ${s.function ?? '?'}()`;
/** python_function_v1 checks assert on calls, not on jobs: they get a per-case view instead of job columns. */
export const isFunctionCheck = (check?: Check | null): boolean =>
  check?.adapter === 'python_function_v1' || (typeof check?.scenario === 'object' && check.scenario !== null);
const brief = (v: unknown, n: number): string => { const s = JSON.stringify(v) ?? 'undefined'; return s.length > n ? `${s.slice(0, n - 1)}…` : s; };
/** One function assertion as `fn(args) returns x` / `fn(args) raises E`, each JSON value cut to `n` characters. */
export const caseText = (a: NonNullable<Check['assertions']>[number], fn: string, n = 60): string =>
  `${fn}(${(a.args ?? []).map((v) => brief(v, n)).join(', ')}) ${a.expect && 'raises' in a.expect ? `raises ${String(a.expect.raises)}` : `returns ${brief(a.expect?.returns, n)}`}`;
export const functionName = (check?: Check | null): string =>
  typeof check?.scenario === 'object' && check.scenario?.function ? check.scenario.function : 'function';
/** Function-adapter observations: how many assertion cases matched. */
export const casesOf = (obs?: Observation | null): { matched: number; total: number } | null =>
  Array.isArray(obs?.matched) ? { matched: obs.matched.filter(Boolean).length, total: obs.matched.length } : null;
export const jobsOf = (obs?: Observation | null): number | null =>
  obs && obs.status !== 'ERROR' && Number.isInteger(obs.unique_jobs) ? (obs.unique_jobs as number) : null;
export const statusTone = (obs?: Observation | null): Tone =>
  !obs?.status || obs.status === 'ERROR' ? 'inc' : obs.status === 'PASS' ? 'pass' : 'fail';
export const obsText = (obs?: Observation | null): string =>
  !obs?.status ? 'not observed'
    : obs.status === 'ERROR' ? 'ERROR · not observed'
      : `${obs.status}${Number.isInteger(obs.unique_jobs) ? ` · ${plural(obs.unique_jobs as number, 'job')}` : casesOf(obs) ? ` · ${casesOf(obs)!.matched} of ${casesOf(obs)!.total} cases` : ''}`;
export const expectedJobs = (check?: Check | null): number | null => {
  const found = (check?.assertions ?? []).find((a) => a.metric === 'unique_jobs');
  return found && Number.isInteger(found.equals) ? (found.equals as number) : null;
};
export const fixturesMatched = (state: DdgState): number =>
  FIXTURES.filter((f) => state.validation?.cases?.[f.key]?.observation?.status === f.expect).length;

// ---- the overall run result ---------------------------------------------------------------------------
export interface Overall { tone: Tone; word: string; raw: string; glyph: Glyph; exit: string; summary: string }

export function overall(report?: Report | null, stale = false): Overall {
  if (!report) return { tone: 'muted', word: 'Not run', raw: '', glyph: 'minus', exit: '—', summary: 'No run yet.' };
  if (stale) return { tone: 'inc', word: 'Stale', raw: String(report.aggregate ?? ''), glyph: 'clock', exit: '—', summary: 'Refs moved since this run. Rerun before trusting it.' };
  const first = focusCheck(report);
  const word = AGGREGATE_LABEL[String(report.aggregate)] ?? 'Incomplete';
  if (report.aggregate === 'PASSED_CHECKS') return { tone: 'pass', word, raw: report.aggregate, glyph: 'check', exit: '0', summary: VERDICT_TEXT[String(first?.verdict)] ?? 'Every approved check held.' };
  if (report.aggregate === 'FAILED') return { tone: 'fail', word, raw: report.aggregate, glyph: 'x', exit: '1', summary: VERDICT_TEXT[String(first?.verdict)] ?? 'An approved check detected a violation.' };
  const codes = new Set(warningCodes(report));
  const summary = codes.has('POLICY_REVIEW_REQUIRED') ? 'Head changes approved policy. Needs review before it can pass.'
    : codes.has('MISSING_APPROVED_COVERAGE') || codes.has('NO_ACTIVE_APPROVED_CHECKS') ? 'An active decision has no approved check.'
      : codes.has('APPROVER_NOT_VERIFIED') ? 'Approver not verified, so the check did not run.'
        : codes.has('EXECUTION_ERROR') || codes.has('AUTHORITY_UNAVAILABLE') ? 'Execution evidence is incomplete.'
          : 'Not proven safe. Never treat this as a pass.';
  return { tone: 'inc', word, raw: String(report.aggregate ?? 'INCOMPLETE'), glyph: 'help', exit: '2', summary };
}

// ---- scenarios -------------------------------------------------------------------------------------------
const HEAD_ALIASES: Record<string, string> = {
  'unseen-regression': 'unseen_regression', 'approved-abort': 'abort', 'approved-crashing': 'crashing',
  'approved-timing-out': 'timing_out', 'approved-missing-entrypoint': 'missing_entrypoint',
  'policy-edit': 'policy_edit', 'preexisting-head': 'preexisting_failure',
};
export function scenarioId(report: Report | null | undefined, scenarios: Scenario[]): string | null {
  const head = report?.head_ref;
  if (typeof head !== 'string') return null;
  const id = HEAD_ALIASES[head] ?? head;
  return scenarios.some((s) => s.id === id) ? id : null;
}
/** A ref name as written; a bare 40-hex SHA (CLI reports name commits, not refs) is shortened. */
export const refLabel = (ref?: string | null): string | undefined => (ref && /^[0-9a-f]{40}$/.test(ref) ? short(ref) : ref ?? undefined);
export const headLabel = (state: DdgState): string => {
  const report = state.report;
  const scenarios = state.scenarios ?? [];
  const id = scenarioId(report, scenarios);
  const ref = report?.head_ref;
  return scenarios.find((s) => s.id === id)?.label ?? refLabel(ref) ?? 'head';
};

export const proposalLabel = (state: DdgState): string => {
  const m = state.draft?.proposal_mode ?? state.mode;
  return m === 'live' ? 'Live proposal' : m === 'recorded' ? 'Recorded proposal' : m === 'manual' ? 'Manual check' : 'Source unknown';
};

// ---- what needs attention (drives the Overview next action) ---------------------------------------------
export interface AttentionItem { tone: 'fail' | 'inc' | 'todo' | 'ok'; glyph: Glyph; title: string; text?: string; href?: string; link?: string }

export function attentionItems(state: DdgState): AttentionItem[] {
  const out: AttentionItem[] = [];
  const report = state.report;
  const v = state.validation;
  const m = overall(report, state.report_stale === true);
  if (!state.draft) out.push({ tone: 'todo', glyph: 'checks', title: 'No check drafted.', href: 'checks', link: 'Draft a check' });
  else if (!v) out.push({ tone: 'todo', glyph: 'checks', title: 'Proposal not calibrated.', href: 'checks', link: 'Validate proposal' });
  else if (!v.eligible) out.push({ tone: 'fail', glyph: 'x', title: 'Calibration failed.', text: 'Cannot be approved.', href: 'checks', link: 'See matrix' });
  else if (!state.approval) out.push({ tone: 'todo', glyph: 'approvals', title: `${state.draft.check?.id ?? 'Check'} is eligible.`, text: 'Needs approval.', href: 'approvals', link: 'Review and approve' });
  if (state.approval && !report) out.push({ tone: 'todo', glyph: 'play', title: 'No run yet.', href: 'runs', link: 'Start a run' });
  if (report) {
    const checks = realChecks(report);
    if (state.report_stale === true) out.push({ tone: 'inc', glyph: 'clock', title: 'Report is stale.', href: 'runs', link: 'Rerun' });
    checks.filter((c) => c.verdict === 'VIOLATION_INTRODUCED').forEach((c) =>
      out.push({ tone: 'fail', glyph: 'x', title: `${c.decision?.id ?? c.check?.decision_id ?? 'Decision'} regressed`, text: `on ${headLabel(state)}.`, href: 'runs', link: 'Inspect evidence' }));
    checks.filter((c) => c.verdict === 'NOT_CHECKED').forEach((c) =>
      out.push({ tone: 'inc', glyph: 'help', title: `${c.check_id} not checked.`, text: c.error ?? c.head?.error ?? c.base?.error ?? '', href: 'runs', link: 'See reason' }));
    if (m.tone === 'inc' && !checks.some((c) => c.verdict === 'NOT_CHECKED')) out.push({ tone: 'inc', glyph: 'help', title: 'Run incomplete.', text: m.summary, href: 'runs', link: 'See warnings' });
    const approver = checks[0]?.approver;
    if (approver && !approver.verified) out.push({ tone: 'fail', glyph: 'user', title: 'Approver not verified.', href: 'approvals', link: 'See provenance' });
    if (report.sandbox === 'host') out.push({ tone: 'inc', glyph: 'box', title: 'Head ran without isolation.', href: 'reports', link: 'See report' });
  }
  if (!out.length) out.push({ tone: 'ok', glyph: 'check', title: 'Nothing needs attention.', text: 'Latest run passed, verified and isolated.' });
  return out;
}
