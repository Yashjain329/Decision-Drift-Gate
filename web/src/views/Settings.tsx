'use client';
// Reference port: shows the pattern every view follows (View + PageHead + panels, data from useDdgState(),
// derivations from lib/model, no fabricated values, "not recorded" for anything missing).
import type { ReactNode } from 'react';
import { View } from '@/components/Shell';
import { PageHead, Tag } from '@/components/ui';
import { orText, proposalLabel } from '@/lib/model';
import { useDdgState } from '@/lib/store';

const COMMANDS: [string, ReactNode][] = [
  ['init', <>create <code>.ddg/</code> and approvers</>],
  ['propose', 'draft a check'],
  ['validate', 'calibrate on three fixtures'],
  ['approve', 'record reviewer approval'],
  ['run', 'compare base and head'],
  ['status', 'detect moved refs'],
  ['providers', 'list model providers'],
  ['serve', 'start this viewer'],
];

export default function Settings() {
  const s = useDdgState();
  const draft = s.draft;
  const mode = draft?.proposal_mode ?? s.mode;
  const rm = draft?.request_metadata ?? {};
  const rows: [string, unknown][] = draft
    ? [
      ['Provider', rm.provider ?? (mode === 'recorded' ? 'recorded capture (no network call)' : undefined)],
      ['Model', draft.model],
      ['Prompt version', rm.prompt_version],
      ['Timeout', rm.timeout_seconds ? `${rm.timeout_seconds}s` : undefined],
      ['Client', draft.sdk_version],
      ['Captured at', draft.captured_at],
      ['Attempts', draft.attempts?.map((a) => a.result).join(', ')],
    ]
    : [['Status', 'No proposal has been drafted.']];

  return (
    <View id="settings" labelledBy="settings-title">
      <PageHead id="settings-title" crumb="Providers & CLI" title="Providers and command line" lede="A provider failure never means a check failed." />
      <div className="grid">
        <article className="panel span-5">
          <div className="panel-head"><h2>Proposal provenance</h2><Tag tone={mode === 'live' ? 'pre' : 'muted'}>{mode ? proposalLabel(s) : 'No proposal'}</Tag></div>
          <dl className="kv kv-stack">
            {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="mono">{orText(v)}</dd></div>)}
          </dl>
          <p className="foot-note">Set <code>DDG_PROVIDER</code> and <code>DDG_MODEL</code>. List options with <code>ddg providers</code>.</p>
        </article>
        <article className="panel span-7">
          <div className="panel-head"><h2>Exit codes · <code>ddg run</code></h2></div>
          <ul className="exit-list">
            <li><span className="exit-chip mono tone-pass">0</span><b>Checks passed</b><span>every approved check held</span></li>
            <li><span className="exit-chip mono tone-fail">1</span><b>Failed</b><span>a check detected a violation</span></li>
            <li><span className="exit-chip mono tone-inc">2</span><b>Incomplete</b><span>not proven safe; never a pass</span></li>
            <li><span className="exit-chip mono tone-muted">3</span><b>Usage / infra</b><span>bad input or no container runtime</span></li>
          </ul>
        </article>
        <article className="panel span-12">
          <div className="panel-head"><h2>Commands</h2><span className="muted small">python -m ddg &lt;command&gt;</span></div>
          <ul className="cmd-grid">
            {COMMANDS.map(([cmd, text]) => <li key={cmd}><code>{cmd}</code><span>{text}</span></li>)}
          </ul>
        </article>
      </div>
    </View>
  );
}
