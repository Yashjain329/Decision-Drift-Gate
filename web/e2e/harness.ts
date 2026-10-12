// Real-engine harness: every test gets its own `ddg serve` on a fresh demo repository and a free port.
// Nothing is mocked: the browser talks to the actual Python engine, sandbox and Git refs.
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createInterface } from 'node:readline';

export const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = process.env.DDG_PYTHON ?? 'python';

export type Sandbox = 'docker' | 'podman' | 'host';
export interface Demo {
  url: string;
  repo: string;
  token: string;
  sandbox: Sandbox;
  /** POST to the engine with the session token, exactly as the UI does. Returns the new state. */
  post: (route: string, body: unknown) => Promise<EngineState>;
  state: () => Promise<EngineState>;
  git: (...args: string[]) => string;
  stop: () => Promise<void>;
}
// Minimal typing of what tests read back from the engine.
export interface EngineState {
  draft?: { draft_digest?: string; check?: { id?: string } } | null;
  validation?: { eligible?: boolean } | null;
  approval?: { reviewer?: string; check_id?: string } | null;
  report?: {
    aggregate?: string; base_ref?: string; head_ref?: string; base_sha?: string; head_sha?: string; sandbox?: string;
    checks?: { check_id: string; verdict?: string; error?: string | null; head?: { status?: string; error?: string | null; unique_jobs?: number | null }; base?: { status?: string; unique_jobs?: number | null } }[];
    warnings?: { code?: string }[];
  } | null;
  report_stale?: boolean;
  scenarios?: { id: string; label?: string }[];
}

export const sandboxMode = (): Sandbox => (process.env.DDG_SANDBOX as Sandbox | undefined) ?? 'docker';

export async function startDemo(opts: { sandbox?: Sandbox; approve?: boolean; scenario?: string; env?: Record<string, string> } = {}): Promise<Demo> {
  const sandbox = opts.sandbox ?? sandboxMode();
  const work = mkdtempSync(path.join(tmpdir(), 'ddg-ui-e2e-'));
  const repo = path.join(work, 'demo');
  const env = { ...process.env, DDG_SANDBOX: sandbox, PYTHONPATH: REPO_ROOT, PYTHONUTF8: '1', ...opts.env };
  execFileSync(PYTHON, ['-m', 'ddg', 'demo-init', '--destination', repo], { cwd: REPO_ROOT, env, stdio: 'pipe' });

  const child: ChildProcess = spawn(PYTHON, ['-m', 'ddg', 'serve', '--repo', repo, '--state-dir', path.join(work, 'state'), '--port', '0'],
    { cwd: REPO_ROOT, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const stderr: string[] = [];
  child.stderr?.on('data', (d: Buffer) => stderr.push(d.toString()));
  const url = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`ddg serve did not start: ${stderr.join('')}`)), 60_000);
    createInterface({ input: child.stdout! }).once('line', (line) => {
      clearTimeout(timer);
      try { resolve(String(JSON.parse(line).serving).replace(/\/$/, '')); } catch (e) { reject(e); }
    });
    child.once('exit', (code) => reject(new Error(`ddg serve exited ${code}: ${stderr.join('')}`)));
  });

  const html = await (await fetch(`${url}/`)).text();
  const token = /name="ddg-session-token" content="([^"]+)"/.exec(html)?.[1] ?? '';
  if (!token || token === '__DDG_SESSION_TOKEN__') throw new Error('session token was not injected');

  const post = async (route: string, body: unknown): Promise<EngineState> => {
    const r = await fetch(`${url}/api/${route}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-DDG-Session': token }, body: JSON.stringify(body) });
    const payload = (await r.json()) as { state?: EngineState; error?: string };
    if (!r.ok || !payload.state) throw new Error(`${route} failed (${r.status}): ${payload.error}`);
    return payload.state;
  };
  const state = async (): Promise<EngineState> => ((await (await fetch(`${url}/api/state`)).json()) as { state: EngineState }).state;
  const git = (...args: string[]) => execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8' }).trim();

  const demo: Demo = {
    url, repo, token, sandbox, post, state, git,
    stop: async () => {
      if (child.exitCode === null) {
        child.kill();
        await new Promise((r) => child.once('exit', r));
      }
      rmSync(work, { recursive: true, force: true, maxRetries: 5 });
    },
  };

  if (opts.approve || opts.scenario) await approveViaApi(demo);
  if (opts.scenario) await demo.post('run', { scenario: opts.scenario });
  return demo;
}

/** Draft (recorded), validate and approve through the engine API: the fast path for tests that start later. */
export async function approveViaApi(demo: Demo): Promise<void> {
  const proposed = await demo.post('propose', { mode: 'recorded' });
  const digest = proposed.draft?.draft_digest;
  if (!digest) throw new Error('no draft digest');
  const validated = await demo.post('validate', { draft_digest: digest });
  if (!validated.validation?.eligible) throw new Error('recorded proposal was not eligible');
  await demo.post('approve', { draft_digest: digest, reviewer: 'E2E Reviewer', reason: 'Reviewed recorded calibration' });
}
