'use client';
// One store for the whole viewer: engine state, busy flag, notice, current view (hash routed) and the
// per-tab run history. Views read it with useDdg(); only act() talks to the engine.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { fetchState, post, type RouteBody } from './api';
import { casesOf, expectedJobs, focusCheck, headLabel, isFunctionCheck, isReadOnly, jobsOf, overall } from './model';
import type { CheckResult, DdgState, Route, ViewId } from './types';

export const VIEWS: ViewId[] = ['overview', 'decisions', 'checks', 'runs', 'approvals', 'reports', 'settings'];
const ALIASES: Record<string, ViewId> = { decision: 'decisions', approval: 'approvals', review: 'runs' };
const HISTORY_KEY = 'ddg-session-runs';

/** `jobs` holds jobs created on head, or for function checks (`unit: 'case'`) the failing cases on head. */
export interface RunRecord { id: string; at: string; label: string; aggregate: string; verdict: string | null; jobs: number | null; expected: number | null; unit?: 'job' | 'case' }
export interface Notice { text: string; kind: 'error' | 'success' | 'pending' | 'warn' | 'info' }

interface Store {
  state: DdgState | null;
  connected: boolean;
  busy: boolean;
  notice: Notice | null;
  view: ViewId;
  history: RunRecord[];
  go: (view: ViewId) => void;
  act: <R extends Route>(route: R, body: RouteBody[R]) => Promise<void>;
}

const Ctx = createContext<Store | null>(null);

export function useDdg(): Store {
  const store = useContext(Ctx);
  if (!store) throw new Error('useDdg must be used inside <DdgProvider>');
  return store;
}
/** Convenience for views that only render once state has loaded. */
export function useDdgState(): DdgState {
  return useDdg().state ?? {};
}

const parseView = (hash: string): ViewId | null => {
  const raw = hash.replace(/^#/, '');
  const v = (ALIASES[raw] ?? raw) as ViewId;
  return VIEWS.includes(v) ? v : null;
};

function loadHistory(): RunRecord[] {
  try { const v = JSON.parse(sessionStorage.getItem(HISTORY_KEY) ?? '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}

function recordRun(state: DdgState): RunRecord[] {
  const report = state.report;
  const history = loadHistory();
  if (!report?.run_at) return history;
  const id = `${report.run_at}|${report.head_ref}|${report.head_sha}`;
  if (history.some((h) => h.id === id)) return history;
  const check = focusCheck(report);
  history.push({ id, at: report.run_at, label: headLabel(state), aggregate: String(report.aggregate ?? ''), verdict: check?.verdict ?? null, ...measure(check) });
  const kept = history.slice(-16);
  try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(kept)); } catch { /* storage disabled: chart shows what it has */ }
  return kept;
}

function measure(check?: CheckResult): Pick<RunRecord, 'jobs' | 'expected' | 'unit'> {
  if (!isFunctionCheck(check?.check)) return { jobs: jobsOf(check?.head), expected: expectedJobs(check?.check), unit: 'job' };
  const cases = check?.head?.status === 'ERROR' ? null : casesOf(check?.head);
  return { jobs: cases ? cases.total - cases.matched : null, expected: 0, unit: 'case' };
}

const PENDING: Record<Route, (body: unknown) => string> = {
  propose: (b) => ((b as RouteBody['propose']).mode === 'live' ? 'Requesting a live proposal from the provider…' : 'Loading the recorded proposal…'),
  validate: () => 'Calibrating against three fixtures in the sandbox…',
  approve: () => 'Recording approval…',
  run: () => 'Running approved checks on base and head…',
};

export function DdgProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DdgState | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [view, setView] = useState<ViewId>('overview');
  const [history, setHistory] = useState<RunRecord[]>([]);
  const viewRef = useRef(view);
  viewRef.current = view;

  const accept = useCallback((next: DdgState) => { setState(next); setHistory(recordRun(next)); }, []);

  // hash routing: #runs etc.; old #decision/#approval/#review links redirect
  useEffect(() => {
    const sync = () => {
      const v = parseView(location.hash);
      if (v) {
        // canonicalise legacy aliases (#review -> #runs) so the address bar always names the real view
        if (location.hash !== `#${v}`) window.history.replaceState(null, '', `#${v}`);
        setView(v);
        window.scrollTo({ top: 0 });
      }
      else window.history.replaceState(null, '', `#${viewRef.current}`);
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  useEffect(() => {
    fetchState()
      .then((s) => {
        accept(s); setConnected(true);
        if (isReadOnly(s)) setNotice({ kind: 'info', text: 'Read-only view of a repository. Records come from Git; propose, validate, approve and run with the ddg CLI.' });
      })
      .catch((e: unknown) => setNotice({ text: e instanceof Error ? e.message : 'Could not connect to the local engine.', kind: 'error' }));
  }, [accept]);

  const go = useCallback((v: ViewId) => { if (location.hash !== `#${v}`) location.hash = v; else setView(v); }, []);

  const act = useCallback(async <R extends Route>(route: R, body: RouteBody[R]) => {
    if (busy || isReadOnly(state)) return;
    setBusy(true);
    setNotice({ text: PENDING[route](body), kind: 'pending' });
    try {
      const next = await post(route, body);
      accept(next);
      if (route === 'run') {
        const m = overall(next.report, next.report_stale === true);
        setNotice({ text: `Run completed: ${m.word}, exit ${m.exit}.${viewRef.current === 'runs' ? '' : ' See Runs & Regressions.'}`, kind: m.tone === 'fail' ? 'error' : m.tone === 'pass' ? 'success' : 'warn' });
      } else {
        const done: Record<string, string> = { propose: 'Proposal drafted. Validate it next.', validate: 'Calibration finished.', approve: 'Approval recorded. It is verified when the next run reads the approval commit.' };
        setNotice({ text: done[route] ?? 'Done.', kind: 'success' });
      }
    } catch (e: unknown) {
      setNotice({ text: e instanceof Error ? e.message : 'The local action failed.', kind: 'error' });
      try { accept(await fetchState()); } catch { /* keep the original error visible */ }
    } finally {
      setBusy(false);
    }
  }, [busy, accept, state]);

  const value = useMemo<Store>(() => ({ state, connected, busy, notice, view, history, go, act }), [state, connected, busy, notice, view, history, go, act]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

