'use client';
// Port of legacy/index.html section "runs" + renderScenarioSelect(), trace(), renderRuns(), renderDetail() in legacy/app.js.
import { useEffect, useState } from 'react';
import { Columns } from '@/components/Chart';
import { Icon } from '@/components/Icon';
import { View } from '@/components/Shell';
import { Assertions, Empty, EnumLine, Evidence, ExitChip, OutcomeTag, PageHead, Result, Sha } from '@/components/ui';
import {
  expectedJobs, headLabel, jobsOf, obsText, OUTCOMES, outcomeOf, overall, plural, realChecks, scenarioId, SIGNATURE,
  statusTone, VERDICT_TEXT, type Tone,
} from '@/lib/model';
import { useDdg, useDdgState } from '@/lib/store';
import type { Check, CheckResult, Observation, Report } from '@/lib/types';

const isTone = (t: Tone | null | undefined): string => (t && t !== 'muted' ? `is-${t}` : '');

/** Service events as readable lines; a second accepted job for the same operation is flagged as a duplicate. */
function Trace({ obs }: { obs?: Observation }) {
  const events = Array.isArray(obs?.events) ? obs.events : [];
  if (!events.length) return <ol className="trace"><li className="empty-ev">{obs?.error ? `No trace: ${obs.error}` : 'No events recorded.'}</li></ol>;
  const jobs = new Set<string | undefined>();
  return (
    <ol className="trace">
      {events.map((e, i) => {
        const name = e?.event;
        let text = name || 'event';
        let cls = '';
        if (name === 'submit') text = `submit · call ${e.call ?? '?'}`;
        else if (name === 'accepted') { const dup = jobs.size > 0; text = `job ${e.job_id ?? '?'} created${dup ? ' · duplicate' : ''}`; cls = dup ? 'ev-dup' : 'ev-accepted'; jobs.add(e.job_id); }
        else if (name === 'response') text = `service returned ${e.status ?? '?'}`;
        else if (name === 'lookup') text = e.job_id ? `lookup found ${e.job_id}` : 'lookup found nothing';
        else if (name === 'deduplicated') text = `stable key reused ${e.job_id ?? '?'}`;
        return <li key={i} className={cls || undefined}>{text}</li>;
      })}
    </ol>
  );
}

const eventCount = (obs?: Observation): number => (Array.isArray(obs?.events) ? obs.events.length : 0);

function Detail({ report, c }: { report: Report; c: CheckResult | null }) {
  const reason = c?.verdict === 'NOT_CHECKED' ? ` ${c.error || c.head?.error || c.base?.error || 'Reason not recorded.'}` : '';
  const decision = c?.decision ?? report.active_decisions?.find((d) => d.id === c?.check?.decision_id);
  const expected = expectedJobs(c?.check);

  return (
      <section className="panel detail" id="detail" aria-labelledby="detail-title" aria-live="polite">
        <div className="panel-head">
          <h2 id="detail-title"><span id="detail-check">{c?.check_id || 'No check'}</span></h2>
          {c ? <OutcomeTag verdict={c.verdict} /> : <span className="tag tag-muted">—</span>}
        </div>
        <p id="detail-explain" className="detail-explain">
          {c ? `${VERDICT_TEXT[String(c.verdict)] ?? 'Unrecognised outcome; treated as not checked.'}${reason}` : 'Select a check result.'}
        </p>
        <p id="detail-decision" className="detail-decision">
          {decision ? <><span className="mono dec-id">{decision.id}</span>{` ${decision.rule ?? 'rule not recorded'}`}</> : 'Governing decision not in the report.'}
        </p>
        <div className="detail-chart">
          {c ? (
            <Columns
              columns={[
                { label: 'Base', note: obsText(c.base), jobs: jobsOf(c.base), tone: statusTone(c.base) },
                { label: 'Head', note: obsText(c.head), jobs: jobsOf(c.head), tone: statusTone(c.head) },
              ]}
              expected={expected} colW={84} gap={84} unit={40}
              label={`Jobs created for one operation. Base ${obsText(c.base)}. Head ${obsText(c.head)}.${expected !== null ? ` Expected ${expected}.` : ''}`}
            />
          ) : null}
        </div>
      </section>
  );
}

function EvidenceStack({ report, c }: { report: Report; c: CheckResult | null }) {
  const diff = typeof c?.diff === 'string' ? c.diff.trim() : '';
  const lines = diff.split('\n');
  const add = lines.filter((l) => l.startsWith('+') && !l.startsWith('+++')).length;
  const del = lines.filter((l) => l.startsWith('-') && !l.startsWith('---')).length;
  const ap = c?.approval; const who = c?.approver; const commit = who?.commits?.[0];
  const ord = report.ordinary_tests ?? {};
  const bothPassed = ord.base?.status === 'PASS' && ord.head?.status === 'PASS';

  return (
    <div className="evidence-stack" aria-label="Evidence">
      <Evidence id="ev-traces" title="Service traces" open meta={c ? `base ${plural(eventCount(c.base), 'event')} · head ${plural(eventCount(c.head), 'event')}` : '—'}>
        <div className="side-by-side">
          <div><p className="side-title side-base">Base</p><p id="detail-base" className={`side-result ${isTone(statusTone(c?.base))}`}>{obsText(c?.base)}</p><Trace obs={c?.base} /></div>
          <div><p className="side-title side-head">Head</p><p id="detail-head" className={`side-result ${isTone(statusTone(c?.head))}`}>{obsText(c?.head)}</p><Trace obs={c?.head} /></div>
        </div>
      </Evidence>
      <Evidence id="detail-diff-block" title="Change in scope" meta={diff ? `+${add} −${del}` : 'no change in scope'}>
        <pre id="detail-diff" className="code-block diff" tabIndex={0} aria-label="Diff of files in the check scope">{diff || 'No change to files in the check scope.'}</pre>
      </Evidence>
      <Evidence title="Approved check" meta={c?.check ? plural((c.check.assertions ?? []).length, 'assertion') : '—'}>
        <div className="ev-body">
          <Assertions check={c?.check} />
          <p className="mono small muted">digest <span id="detail-digest">{c?.check_digest || '—'}</span></p>
        </div>
      </Evidence>
      <Evidence
        title="Approval provenance"
        meta={who ? (who.verified ? `verified · ${commit?.author_email || 'git author'}` : 'NOT verified') : 'not reported'}
        metaTone={who ? (who.verified ? null : 'fail') : 'inc'}
      >
        <p id="detail-approval" className="ev-body body-copy">
          {c ? [
            ap ? `Approved ${ap.approved_at ?? ''}, label “${ap.reviewer ?? 'not recorded'}”.` : 'No approval record in the report.',
            who ? (who.verified
              ? `Author ${commit?.author_email || 'unknown'} is on the allowlist (${SIGNATURE[String(commit?.signature)] ?? 'signature not reported'}).`
              : `Approver not verified${who.reason ? `: ${who.reason}` : ''}.`) : '',
          ].join(' ') : '—'}
        </p>
      </Evidence>
      <Evidence title="Ordinary tests" meta={bothPassed ? 'both passed' : ord.base || ord.head ? 'see results' : 'not run'}>
        <p className="ev-body mono small">base <b id="ordinary-base">{obsText(ord.base)}</b> · head <b id="ordinary-head">{obsText(ord.head)}</b></p>
      </Evidence>
      <a className="text-link" href="#reports">Full audit report <Icon name="arrow" /></a>
    </div>
  );
}

export default function Runs() {
  const { busy, act } = useDdg();
  const s = useDdgState();
  const report = s.report;
  const stale = s.report_stale === true;
  const scenarios = Array.isArray(s.scenarios) ? s.scenarios : [];
  const [picked, setPicked] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { setSelected(null); }, [report?.run_at]); // a new run starts from its most important check

  // keep the user's pick while it still exists; otherwise follow the scenario of the latest run
  const scenario = scenarios.some((x) => x.id === picked) ? picked : scenarioId(report, scenarios) ?? scenarios[0]?.id ?? '';
  const locked = busy || !s.approval || !scenarios.length;

  const checks = realChecks(report);
  const current = checks.find((c) => c.check_id === selected) ?? checks.find((c) => c.verdict !== 'CHECK_PASSED') ?? checks[0] ?? null;
  const m = overall(report, stale);
  const groups = OUTCOMES.map((o) => ({ o, members: checks.filter((c) => outcomeOf(c.verdict).verdict === o.verdict) }));
  const zero = groups.filter((g) => !g.members.length).map((g) => g.o.label.toLowerCase());

  return (
    <View id="runs" labelledBy="runs-title">
      <PageHead id="runs-title" crumb="Runs & Regressions" title="Run inspector" />

      <div className="panel run-toolbar">
        <label className="field-label" htmlFor="scenario-select">Candidate head</label>
        <select id="scenario-select" name="scenario" value={scenario} disabled={locked} onChange={(e) => setPicked(e.target.value)}>
          {scenarios.length ? scenarios.map((x) => <option key={x.id} value={x.id}>{x.label || x.id}</option>) : <option value="">Approve a check first</option>}
        </select>
        <button className="button button-primary" id="run-button" type="button" disabled={locked} aria-busy={busy}
          onClick={() => { if (scenario) void act('run', { scenario }); }}>
          <Icon name="play" />Run approved checks
        </button>
        <code id="run-cli" className="cli-hint">{report ? `ddg run --base ${report.base_ref ?? 'base'} --head ${report.head_ref ?? 'head'}` : 'ddg run --base <approved> --head <candidate>'}</code>
      </div>
      {report && stale ? <p id="stale-notice" className="stale"><Icon name="clock" />Refs moved since this run. Rerun before trusting it.</p> : null}

      {!report ? <Empty glyph="runs">No run yet. Pick a candidate head and run the approved checks.</Empty> : (
        <div id="run-content">
          <div className={`run-summary tone-${m.tone}`} id="run-summary">
            <Result model={m} id="run-result" />
            <ExitChip model={m} />
            <p id="run-summary-text" className="run-summary-text">{m.summary}</p>
          </div>

          <div className="revpair revpair-run">
            <div className="rev rev-base"><span className="rev-role"><Icon name="lock" />Base · trusted</span><span id="run-base-ref" className="rev-ref">{report.base_ref || 'base'}</span><Sha sha={report.base_sha} /></div>
            <Icon name="arrow" className="ic rev-arrow" />
            <div className="rev rev-head"><span className="rev-role"><Icon name="box" />Head · untrusted</span><span id="run-head-ref" className="rev-ref">{headLabel(s)}</span><Sha sha={report.head_sha} /></div>
            <div className="rev rev-sandbox">
              <span className="rev-role">Isolation</span>
              <span id="run-sandbox" className={`rev-ref ${report.sandbox === 'host' ? 'is-fail' : report.sandbox ? '' : 'is-inc'}`}>
                {report.sandbox === 'host' ? 'host · UNSAFE' : report.sandbox || 'not recorded'}
              </span>
              <span className="rev-note">head code ran here</span>
            </div>
          </div>

          <div className="inspector">
            <section className="panel results" aria-labelledby="results-title">
              <div className="panel-head"><h2 id="results-title">Check results</h2><span id="results-count" className="muted small">{plural(checks.length, 'check')}</span></div>
              <div id="result-groups">
                {groups.filter((g) => g.members.length).map(({ o, members }) => {
                  return (
                    <div key={o.verdict} className={`group g-${o.tone}`}>
                      <div className="group-head"><Icon name={o.glyph} /><span className="group-name"><EnumLine label={o.label} raw={o.verdict} /></span><span className="n">{members.length}</span></div>
                      <p className="group-desc">{o.desc}</p>
                      <div className="group-rows">
                        {members.map((c) => (
                          <button key={c.check_id} type="button" className="result-row" aria-pressed={c.check_id === current?.check_id} onClick={() => setSelected(c.check_id)}>
                            <span className="rr-id">{c.check_id}</span>
                            <span className="rr-dec">{c.decision?.id || c.check?.decision_id || ''}</span>
                            <span className="rr-obs">{`base ${obsText(c.base)} → head ${obsText(c.head)}`}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {!checks.length ? <p className="body-copy">No approved check produced a result.</p> : null}
              </div>
              <p id="results-zero" className="zero-line">{zero.length && checks.length ? `None ${zero.join(' · ')}` : ''}</p>
              {report.warnings?.length ? (
                <div id="run-warnings" className="warnings">
                  <p className="field-label">Warnings</p>
                  {report.warnings.map((w, i) => (
                    <p key={i} className="warning"><Icon name="alert" /><span><code>{w?.code || 'WARNING'}</code>{w?.message ? ` ${w.message}` : ''}</span></p>
                  ))}
                </div>
              ) : null}
            </section>
            <Detail report={report} c={current} />
          </div>

          <EvidenceStack report={report} c={current} />
        </div>
      )}
    </View>
  );
}
