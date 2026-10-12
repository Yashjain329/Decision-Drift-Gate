'use client';
import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { overall, realChecks, short, type Glyph, type Tone } from '@/lib/model';
import { useDdg } from '@/lib/store';
import type { DdgState, ViewId } from '@/lib/types';

const tone = (t: Tone | null | undefined) => (t && t !== 'muted' ? `is-${t}` : '');

function Readout({ label, value, t, mono }: { label: string; value: string; t?: Tone | null; mono?: boolean }) {
  return <div className="readout"><dt>{label}</dt><dd className={`${mono ? 'mono ' : ''}${tone(t)}`}>{value}</dd></div>;
}

export function Topbar() {
  const { state, connected } = useDdg();
  const s: DdgState = state ?? {};
  const report = s.report;
  const m = overall(report, s.report_stale === true);
  const approver = realChecks(report)[0]?.approver;
  const iso = report?.sandbox;
  return (
    <header className="topbar" aria-label="Workspace">
      <a className="brand" href="#overview" aria-label="Decision Drift Gate, overview">
        <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="4" height="16" rx="1.2" /><rect x="16" y="4" width="4" height="16" rx="1.2" /><rect x="10" y="9.5" width="4" height="5" rx="1.2" /></svg></span>
        <span className="brand-name">Decision Drift Gate</span>
      </a>
      <div className="workspace" aria-label="Repository">
        <span className="ws-label">Local workspace</span>
        <span className="ws-repo"><Icon name="git" /><span>demo repository</span></span>
        <span className="ws-meta mono">{report ? `${report.base_ref ?? 'base'} @ ${short(report.base_sha, 7)}` : s.approval ? 'approved base' : 'no approved base'}</span>
      </div>
      <dl className="readouts">
        <Readout label="Latest run" value={report ? m.word : 'no run yet'} t={report ? m.tone : null} />
        <Readout label="Exit" value={m.exit} t={report ? m.tone : null} mono />
        <Readout label="Approver" value={report && approver ? (approver.verified ? `verified · ${approver.commits?.[0]?.author_email ?? 'git author'}` : 'UNVERIFIED') : s.approval ? 'recorded · not yet verified' : 'not recorded'} t={report && approver ? (approver.verified ? 'pass' : 'fail') : null} mono />
        <Readout label="Isolation" value={!iso ? 'no run yet' : iso === 'host' ? 'host · UNSAFE' : iso} t={!iso ? null : iso === 'host' ? 'fail' : iso === 'unavailable' ? 'inc' : 'pass'} mono />
      </dl>
      <div className="connection"><span className={`connection-dot${connected ? ' is-connected' : ''}`} aria-hidden="true" /><span>{connected ? 'Local engine connected' : 'Connecting'}</span></div>
    </header>
  );
}

const NAV: { id: ViewId; label: string; glyph: Glyph }[] = [
  { id: 'overview', label: 'Overview', glyph: 'overview' },
  { id: 'decisions', label: 'Decisions', glyph: 'decisions' },
  { id: 'checks', label: 'Check Studio', glyph: 'checks' },
  { id: 'runs', label: 'Runs & Regressions', glyph: 'runs' },
  { id: 'approvals', label: 'Approvals', glyph: 'approvals' },
  { id: 'reports', label: 'Reports', glyph: 'reports' },
  { id: 'settings', label: 'Providers & CLI', glyph: 'settings' },
];

function navState(s: DdgState, id: ViewId): [string, Tone | null] {
  const report = s.report;
  const v = s.validation;
  const approver = report ? realChecks(report)[0]?.approver : undefined;
  switch (id) {
    case 'decisions': { const d = [s.new_decision, s.old_decision].filter(Boolean); return [d.length ? `${d.filter((x) => x?.status === 'active').length} active` : '', null]; }
    case 'checks': return [s.approval ? 'approved' : v ? (v.eligible ? 'eligible' : 'needs work') : s.draft ? 'draft' : '', s.approval ? 'pass' : v && !v.eligible ? 'fail' : null];
    case 'runs': { const m = overall(report, s.report_stale === true); return [report ? m.word.toLowerCase() : '', report ? m.tone : null]; }
    case 'approvals': return [approver?.verified ? 'verified' : approver ? 'unverified' : s.approval ? 'recorded' : v?.eligible ? 'pending' : '', approver?.verified ? 'pass' : approver ? 'fail' : null];
    case 'reports': return [report ? 'ready' : '', null];
    case 'settings': return [s.draft?.proposal_mode ?? s.mode ?? '', null];
    default: return ['', null];
  }
}

export function Rail() {
  const { state, view } = useDdg();
  const s = state ?? {};
  return (
    <nav className="rail" aria-label="Destinations">
      <ul className="nav-list">
        {NAV.map((n) => {
          const [text, t] = navState(s, n.id);
          const active = view === n.id;
          return (
            <li key={n.id} className={n.id === 'settings' ? 'nav-sep' : undefined}>
              <a className={`nav-item${active ? ' is-active' : ''}`} href={`#${n.id}`} aria-current={active ? 'page' : undefined}>
                <Icon name={n.glyph} /><span className="nav-name">{n.label}</span>{text ? <span className={`nav-state ${tone(t)}`}>{text}</span> : null}
              </a>
            </li>
          );
        })}
      </ul>
      <p className="rail-note"><Icon name="lock" /><span>Local only. Head code runs in the <b>sandbox</b>, never in this browser.</span></p>
    </nav>
  );
}

export function NoticeBar() {
  const { notice } = useDdg();
  return <div className={`notice notice-${notice?.kind ?? 'success'}`} role="status" aria-live="polite" hidden={!notice}>{notice?.text}</div>;
}

export function View({ id, labelledBy, children }: { id: ViewId; labelledBy: string; children: ReactNode }) {
  const { view } = useDdg();
  return <section className="view" id={`view-${id}`} aria-labelledby={labelledBy} hidden={view !== id}>{children}</section>;
}
