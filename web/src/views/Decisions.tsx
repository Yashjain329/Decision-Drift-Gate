'use client';
// Port of legacy/index.html "decisions" + renderDecisions() in legacy/app.js.
import { View } from '@/components/Shell';
import { Icon } from '@/components/Icon';
import { Evidence, Json, PageHead, Tag } from '@/components/ui';
import { short } from '@/lib/model';
import { useDdgState } from '@/lib/store';
import type { Decision } from '@/lib/types';

export default function Decisions() {
  const s = useDdgState();
  const linked = s.approval?.check_id ?? s.draft?.check?.id;
  const linkedDecision = s.draft?.check?.decision_id;
  const decisions = [s.new_decision, s.old_decision].filter((d): d is Decision => Boolean(d));

  return (
    <View id="decisions" labelledBy="decisions-title">
      <PageHead id="decisions-title" crumb="Decisions" title="What the team agreed to" lede={<>Versioned records in <code>.ddg/decisions/</code>. Newest first.</>} />
      <ol id="decision-list" className="decision-list" aria-label="Decision history, newest first">
        {decisions.length ? null : <li className="panel empty">No decision records were found in .ddg/decisions/.</li>}
        {decisions.map((d) => {
          const active = d.status === 'active';
          const meta: [string, string][] = [
            ['scope', d.scope || '—'],
            ['supersedes', d.supersedes || 'nothing'],
            ['schema', `v${d.schema_version ?? '?'}`],
          ];
          if (active && s.draft?.source_sha) meta.push(['read at', short(s.draft.source_sha)]);
          return (
            <li key={d.id} className={`panel decision ${active ? 'is-active' : 'is-superseded'}`}>
              <div className="decision-head">
                <span className="decision-id">{d.id}</span>
                <Tag tone={active ? 'pass' : 'muted'} glyph={active ? 'check' : 'history'}>
                  {active ? 'Active' : d.status === 'superseded' ? 'Superseded' : d.status || 'unknown'}
                </Tag>
                {active && linked && linkedDecision === d.id
                  ? <Tag tone={s.approval ? 'pass' : 'muted'} glyph="approvals">protected by {linked}</Tag>
                  : null}
              </div>
              <p className="decision-rule">{d.rule || 'No rule text recorded.'}</p>
              {(d.exceptions ?? []).map((e) => <p key={e} className="decision-exc">Permitted exception: {e}</p>)}
              <p className="decision-meta">{meta.map(([k, v]) => <span key={k}>{k} <b>{v}</b></span>)}</p>
              {active ? <a className="text-link" href="#checks">Open in Check Studio<Icon name="arrow" /></a> : null}
            </li>
          );
        })}
      </ol>
      <Evidence title="Decision records (JSON)">
        <Json value={{ active: s.new_decision, superseded: s.old_decision }} />
      </Evidence>
    </View>
  );
}
