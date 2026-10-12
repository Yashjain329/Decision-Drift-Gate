import type { DdgState, Route } from './types';

// The engine injects a per-session token into the served HTML; every POST must echo it back.
export function sessionToken(): string {
  if (typeof document === 'undefined') return '';
  return document.querySelector<HTMLMetaElement>('meta[name="ddg-session-token"]')?.content ?? '';
}

async function parse(response: Response): Promise<DdgState> {
  let payload: { state?: DdgState; error?: string } | null = null;
  try { payload = await response.json(); } catch { /* fall through to the status error */ }
  if (!response.ok) throw new Error(payload?.error || `Request failed (${response.status}).`);
  if (!payload?.state) throw new Error('The server returned an invalid state response.');
  return payload.state;
}

export async function fetchState(): Promise<DdgState> {
  return parse(await fetch('/api/state', { headers: { Accept: 'application/json' }, cache: 'no-store' }));
}

export type RouteBody = {
  propose: { mode: 'live' | 'recorded' };
  validate: { draft_digest: string };
  approve: { draft_digest: string; reviewer: string; reason: string };
  run: { scenario: string };
};

export async function post<R extends Route>(route: R, body: RouteBody[R]): Promise<DdgState> {
  return parse(await fetch(`/api/${route}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-DDG-Session': sessionToken() },
    body: JSON.stringify(body),
  }));
}
