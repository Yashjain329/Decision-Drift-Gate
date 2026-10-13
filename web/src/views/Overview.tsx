'use client';
// Port of legacy/index.html section "overview" + renderOverview() in legacy/app.js.
import { Columns, type Column } from '@/components/Chart';
import { Icon } from '@/components/Icon';
import { View } from '@/components/Shell';
import { EnumLine, ExitChip, PageHead, Result, Sha, Tag } from '@/components/ui';
import {
  AGGREGATE_LABEL, OUTCOMES, attentionItems, clock, fixturesMatched, focusCheck, headLabel, outcomeOf, overall, plural, realChecks, refLabel,
} from '@/lib/model';
import { useDdg, type RunRecord } from '@/lib/store';

const runTone = (h: RunRecord): Column['tone'] =>
  h.aggregate === 'INCOMPLETE' || h.verdict === 'NOT_CHECKED' || h.jobs === null ? 'inc'
    : h.verdict === 'PRE_EXISTING_FAILURE' ? 'pre' : h.aggregate === 'FAILED' ? 'fail' : 'pass';

function HistoryChart({ history }: { history: RunRecord[] }) {
  if (!history.length) {
    return <svg id="history-chart" className="chart" viewBox="0 0 600 60" role="img" aria-label="No runs in this tab yet"><text x={0} y={34} className="col-note">No runs in this tab yet.</text></svg>;
  }
  const cols: Column[] = history.map((h) => ({
    label: h.label.length > 12 ? `${h.label.slice(0, 11)}…` : h.label,
    note: clock(h.at),
    jobs: h.jobs,
    tone: runTone(h),
  }));
  while (cols.length < 12) cols.push({ placeholder: true });
  const expected = history.map((h) => h.expected).find((e): e is number => Number.isInteger(e)) ?? null;
  const label = `Runs this session: ${history.map((h) => `${h.label} ${AGGREGATE_LABEL[h.aggregate] ?? h.aggregate}${h.jobs === null ? ', not observed' : `, ${plural(h.jobs, h.unit === 'case' ? 'failing case' : 'job')}`}`).join('; ')}`;
  return <Columns id="history-chart" columns={cols} expected={expected} stacked={false} colW={34} gap={48} unit={38} label={label} />;
}

export default function Overview() {
  const { state, history } = useDdg();
  const s = state ?? {};
  const report = s.report;
  const m = overall(report, s.report_stale === true);
  const items = attentionItems(s);
  const checks = realChecks(report);
  const focus = focusCheck(report);
  const next = items.find((i) => i.href) ?? { href: 'runs', link: 'Open run inspector' };
  const sandbox = report?.sandbox;

  const counts = new Map<string, number>();
  checks.forEach((c) => { const v = outcomeOf(c.verdict).verdict; counts.set(v, (counts.get(v) ?? 0) + 1); });

  const active = report?.active_decisions ?? [s.new_decision].filter((d) => d?.status === 'active');
  const v = s.validation;
  const last = history[history.length - 1];

  return (
    <View id="overview" labelledBy="overview-title">
      <PageHead id="overview-title" crumb="Overview" title="Decision integrity" />

      <section className={`panel signal tone-${m.tone}`} id="ov-signal" aria-labelledby="ov-signal-label">
        <h2 id="ov-signal-label" className="sr-only">Does a change need your attention?</h2>
        <div className="signal-main">
          <div className="signal-row">
            <Result model={m} id="ov-result" />
            {report ? <ExitChip model={m} /> : null}
          </div>
          <p id="ov-summary" className="signal-reason">{report ? m.summary : items[0]?.title ?? 'No run yet.'}</p>
          <p id="ov-check" className="signal-meta mono">
            {focus ? <>{`${focus.check_id} · ${focus.decision?.id ?? focus.check?.decision_id ?? ''} · `}<span className="enum">{focus.verdict}</span></> : null}
          </p>
        </div>
        <div className="signal-action">
          <a id="ov-action" className="button button-primary" href={`#${next.href}`}><span id="ov-action-text">{next.link}</span><Icon name="arrow" /></a>
        </div>
      </section>

      <div className="grid">
        <article className="panel span-8" aria-labelledby="latest-title">
          <div className="panel-head">
            <h2 id="latest-title">Latest comparison</h2>
            <Tag tone={sandbox === 'host' ? 'fail' : report && !sandbox ? 'inc' : 'muted'} glyph={sandbox ? 'box' : report ? 'help' : null}>{!report ? 'isolation —' : !sandbox ? 'isolation not recorded' : sandbox === 'host' ? 'host · unsafe' : `isolated · ${sandbox}`}</Tag>
          </div>
          {report ? (
            <div id="latest-body" className="revpair">
              <div className="rev rev-base"><span className="rev-role"><Icon name="lock" />Base · trusted</span><span id="ov-base-ref" className="rev-ref">{refLabel(report.base_ref) || 'base'}</span><Sha sha={report.base_sha} /></div>
              <Icon name="arrow" className="ic rev-arrow" />
              <div className="rev rev-head"><span className="rev-role"><Icon name="box" />Head · untrusted</span><span id="ov-head-ref" className="rev-ref">{headLabel(s)}</span><Sha sha={report.head_sha} /></div>
            </div>
          ) : (
            <div id="latest-empty" className="empty"><Icon name="runs" className="ic ic-lg" /><p>No run yet.</p></div>
          )}
        </article>

        <article className="panel span-4" aria-labelledby="attention-title">
          <div className="panel-head"><h2 id="attention-title">Needs attention</h2><span id="attention-count" className="count-chip">{items.filter((i) => i.tone !== 'ok').length}</span></div>
          <ul id="attention" className="attention">
            {items.map((it, i) => (
              <li key={i} className={`a-${it.tone}`}>
                <Icon name={it.glyph} />
                <div>
                  <p><b>{it.title}</b>{it.text ? ` ${it.text}` : ''}</p>
                  {it.href ? <a href={`#${it.href}`}>{it.link}</a> : null}
                </div>
              </li>
            ))}
          </ul>
        </article>

        <article className="panel span-12" aria-labelledby="outcomes-title">
          <div className="panel-head"><h2 id="outcomes-title">Check outcomes</h2><span className="muted small">latest run</span></div>
          <ul id="ov-outcomes" className="outcome-list outcome-strip">
            {OUTCOMES.map((o) => {
              const n = counts.get(o.verdict) ?? 0;
              return (
                <li key={o.verdict} className={`outcome o-${o.tone}${n ? '' : ' is-zero'}`}>
                  <Icon name={o.glyph} />
                  <span className="outcome-name"><EnumLine label={o.label} raw={o.verdict} /></span>
                  <span className="outcome-n">{report ? n : '—'}</span>
                </li>
              );
            })}
          </ul>
        </article>

        <article className="panel stat span-3"><p className="stat-label">Approved checks</p><p id="st-approved" className="stat-value">{report ? checks.length : s.approval ? 1 : 0}</p><p id="st-approved-note" className="stat-note">{s.approval?.check_id || 'none yet'}</p></article>
        <article className="panel stat span-3"><p className="stat-label">Active decisions</p><p id="st-decisions" className="stat-value">{active.length}</p><p id="st-decisions-note" className="stat-note">{active.map((d) => d?.id).join(', ') || 'none recorded'}</p></article>
        <article className="panel stat span-3"><p className="stat-label">Calibration</p><p id="st-calibration" className={`stat-value stat-word${v ? (v.eligible ? ' is-pass' : ' is-fail') : ''}`}>{v ? (v.eligible ? 'Eligible' : 'Needs work') : s.draft ? 'Not run' : 'No draft'}</p><p id="st-calibration-note" className="stat-note">{v ? `${fixturesMatched(s)} of 3 fixtures` : '3 fixtures required'}</p></article>
        <article className="panel stat span-3"><p className="stat-label">Runs this session</p><p id="st-runs" className="stat-value">{history.length}</p><p id="st-runs-note" className="stat-note">{last ? `last ${clock(last.at)} UTC` : 'this tab only'}</p></article>

        <article className="panel span-12" aria-labelledby="history-title">
          <div className="panel-head"><h2 id="history-title">Runs this session</h2><span className="muted small">{history.at(-1)?.unit === 'case' ? 'failing cases on head' : 'jobs created on head'}</span></div>
          <HistoryChart history={history} />
          <ul className="legend" aria-label="Legend">
            <li><span className="key key-pass" />Passed</li><li><span className="key key-fail" />Violation</li>
            <li><span className="key key-pre" />Pre-existing</li><li><span className="key key-inc" />Not checked</li>
            <li><span className="key key-exp" />Expected</li>
          </ul>
        </article>
      </div>
    </View>
  );
}
