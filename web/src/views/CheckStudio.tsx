'use client';
// Port of legacy/index.html "CHECK STUDIO" + renderStudio()/assertionLines() in legacy/app.js.
// Calibration eligibility and approval are two separate states: eligible is never shown as approved.
import { useState } from 'react';
import { View } from '@/components/Shell';
import { Columns } from '@/components/Chart';
import { Evidence, Json, PageHead, Tag } from '@/components/ui';
import { FIXTURES, expectedJobs, fixturesMatched, jobsOf, plural, proposalLabel, statusTone } from '@/lib/model';
import { useDdg } from '@/lib/store';
import type { Check } from '@/lib/types';

type Source = 'recorded' | 'live';

/** `expect metric == value`, one line per assertion. */
function Assertions({ check }: { check?: Check | null }) {
  const list = Array.isArray(check?.assertions) ? check.assertions : [];
  return (
    <pre className="code-block code-lg" aria-label="Check assertions">
      {list.length ? list.map((a, i) => (
        <span key={i}>{i ? '\n' : ''}<span className="kw">expect </span>{`${a.metric || 'unknown'} == `}<span className="num">{a.equals === undefined ? 'unset' : JSON.stringify(a.equals)}</span></span>
      )) : '—'}
    </pre>
  );
}

const statusWord = (s?: string): string => (s === 'PASS' ? 'Pass' : s === 'FAIL' ? 'Fail' : s ? 'Error' : '—');

export default function CheckStudio() {
  const { state, busy, act } = useDdg();
  const s = state ?? {};
  const draft = s.draft;
  const check = draft?.check ?? null;
  const v = s.validation;
  const approved = Boolean(s.approval);
  const draftSource: Source | undefined = draft?.proposal_mode === 'live' || draft?.proposal_mode === 'recorded' ? draft.proposal_mode : undefined;
  const [picked, setPicked] = useState<Source | null>(null);
  const source: Source = picked ?? draftSource ?? 'recorded';
  const citations = Array.isArray(check?.citations) ? check.citations : [];
  const matched = fixturesMatched(s);
  const provenance = draft ? [draft.request_metadata?.provider, draft.model, draft.captured_at].filter(Boolean).join(' · ') || 'provenance unavailable' : 'Choose a source and draft a proposal.';
  const columns = FIXTURES.map((f) => { const o = v?.cases?.[f.key]?.observation; return { label: f.short, jobs: jobsOf(o), tone: statusTone(o) }; });
  const vTone = v ? (v.eligible ? 'pass' : 'fail') : 'muted';
  const vGlyph = v ? (v.eligible ? 'check' : 'x') : null;

  return (
    <View id="checks" labelledBy="checks-title">
      <PageHead
        id="checks-title" crumb="Check Studio" title="Does this check prove the decision?"
        lede="Eligible means all three fixtures behaved. It is not approval."
        aside={(
          <div className="state-pair">
            <Tag tone={vTone} glyph={vGlyph}>{`Calibration · ${v ? (v.eligible ? 'eligible' : 'needs work') : 'not run'}`}</Tag>
            <Tag tone={approved ? 'pre' : 'muted'}>{`Approval · ${approved ? 'recorded' : 'pending'}`}</Tag>
          </div>
        )}
      />

      <div className="grid">
        <article className="panel span-12 proposal-bar">
          <label className="field-label" htmlFor="proposal-mode">Proposal source</label>
          <select id="proposal-mode" name="proposal-mode" value={source} disabled={busy || approved} onChange={(e) => setPicked(e.target.value === 'live' ? 'live' : 'recorded')}>
            <option value="recorded">Recorded proposal</option>
            <option value="live">Live proposal (provider)</option>
          </select>
          <button className="button button-secondary" id="propose-button" type="button" disabled={busy || approved} onClick={() => void act('propose', { mode: source })}>Draft proposal</button>
          <p className="source-line">
            <Tag tone={draft?.proposal_mode === 'live' ? 'pre' : 'muted'}>{draft ? proposalLabel(s) : 'No proposal loaded'}</Tag>
            <span id="proposal-provenance" className="muted">{provenance}</span>
          </p>
        </article>

        <article className="panel span-7" aria-labelledby="proposal-title">
          <div className="panel-head"><h2 id="proposal-title">Proposal</h2><code id="check-id" className="muted">{check?.id || 'not recorded'}</code></div>
          <Assertions check={check} />
          <dl className="kv">
            <div><dt>Decision</dt><dd id="check-decision">{check ? `${check.decision_id ?? 'not recorded'}${check.supersedes ? ` (supersedes ${check.supersedes})` : ''}` : '—'}</dd></div>
            <div><dt>Scenario</dt><dd id="check-scenario" className="mono">{check?.scenario || '—'}</dd></div>
            <div><dt>Adapter</dt><dd id="check-adapter" className="mono">{check?.adapter || draft?.adapter_version || '—'}</dd></div>
          </dl>
          <details className="inline-details"><summary>Why this check</summary><p id="check-rationale" className="body-copy">{check?.rationale || 'Draft a proposal first.'}</p></details>
          <details className="inline-details">
            <summary id="citation-summary">{citations.length ? `Grounded in ${plural(citations.length, 'citation')}` : 'Grounded in'}</summary>
            <ul id="check-citation" className="citations">
              {citations.length
                ? citations.map((c, i) => <li key={i}>{`“${c.quote}” `}<code>{c.decision_id}</code></li>)
                : <li>{check ? 'No exact decision citation.' : 'No citation loaded.'}</li>}
            </ul>
          </details>
        </article>

        <article className="panel span-5" aria-labelledby="matrix-title">
          <div className="panel-head"><h2 id="matrix-title">Calibration matrix</h2><Tag tone={vTone} glyph={vGlyph}>{v ? (v.eligible ? 'Eligible' : 'Needs work') : 'Not run'}</Tag></div>
          {v ? (
            <Columns
              columns={columns} expected={expectedJobs(check)} stacked colW={52} gap={34} unit={34} padB={50} notes={false}
              className="chart chart-compact"
              label={`Calibration: ${columns.map((c) => `${c.label} ${c.jobs === null ? 'not observed' : plural(c.jobs, 'job')}`).join(', ')}`}
            />
          ) : null}
          <div className="table-wrap">
            <table className="matrix">
              <thead><tr><th scope="col">Fixture</th><th scope="col">Expected</th><th scope="col">Observed</th><th scope="col">Jobs</th><th scope="col"><span className="sr-only">Eligibility</span></th></tr></thead>
              <tbody id="matrix-body">
                {FIXTURES.map((f) => {
                  const c = v?.cases?.[f.key];
                  const obs = c?.observation;
                  const ok = obs?.status === f.expect;
                  return (
                    <tr key={f.key}>
                      <td title={c?.sha ?? ''}>{f.name}</td>
                      <td className="mono">{statusWord(f.expect)}</td>
                      <td className="mono">{statusWord(obs?.status)}</td>
                      <td className="mono">{jobsOf(obs) ?? '—'}</td>
                      <td>{!v ? <Tag>Not run</Tag> : <Tag tone={ok ? 'pass' : 'fail'} glyph={ok ? 'check' : 'x'}>{ok ? 'Valid' : 'Mismatch'}</Tag>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p id="calibration-explanation" className="foot-note">
            {v ? `${matched} of 3 fixtures matched. ${v.eligible ? 'Human approval of the exact check is still required.' : 'This check cannot be approved.'}` : 'Validation executes the proposal against all three fixtures in the sandbox.'}
          </p>
          <button
            className="button button-secondary full" id="validate-button" type="button" disabled={busy || !draft?.draft_digest || approved}
            onClick={() => { if (draft?.draft_digest) void act('validate', { draft_digest: draft.draft_digest }); }}
          >Validate proposal</button>
        </article>
      </div>
      <Evidence title="Draft and provider provenance (JSON)"><Json value={draft} /></Evidence>
      <Evidence title="Validation evidence (JSON)"><Json value={v} /></Evidence>
    </View>
  );
}
