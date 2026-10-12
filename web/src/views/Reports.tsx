'use client';
// Port of legacy/index.html "reports" + renderReports() and the download-report handler in legacy/app.js.
import { View } from '@/components/Shell';
import { Icon } from '@/components/Icon';
import { Empty, Evidence, Json, OutcomeTag, PageHead, Tag } from '@/components/ui';
import { obsText, orText, overall, realChecks } from '@/lib/model';
import { useDdgState } from '@/lib/store';
import type { Report } from '@/lib/types';

function download(report: Report) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `ddg-report-${report.head_ref || 'head'}-${(report.run_at || '').replace(/:/g, '')}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Reports() {
  const s = useDdgState();
  const report = s.report;
  const stale = s.report_stale === true;
  const m = overall(report, stale);
  const checks = realChecks(report);
  const warnings = report?.warnings ?? [];
  const meta: [string, unknown][] = report
    ? [
      ['Overall', `${m.word} · ${report.aggregate || 'unknown'} · exit ${m.exit}`],
      ['Run at', report.run_at],
      ['Base', `${orText(report.base_ref)} @ ${orText(report.base_sha)}`],
      ['Head', `${orText(report.head_ref)} @ ${orText(report.head_sha)}`],
      ['Adapter', report.adapter_version],
      ['Isolation', report.sandbox === 'host' ? 'host (UNSAFE)' : report.sandbox],
      ['Checks evaluated', checks.length],
    ]
    : [];

  return (
    <View id="reports" labelledBy="reports-title">
      <PageHead
        id="reports-title" crumb="Reports" title="Audit report"
        lede={<>Same report as <code>ddg run --out</code> and the GitHub Action comment.</>}
        aside={
          <button className="button button-secondary" id="download-report" type="button" disabled={!report} onClick={() => { if (report) download(report); }}>
            <Icon name="download" />Download JSON
          </button>
        }
      />
      {!report ? <Empty glyph="reports">No report yet. Run the approved checks.</Empty> : (
        <div id="report-content" className="grid">
          <article className="panel span-5">
            <div className="panel-head">
              <h2>Run metadata</h2>
              <Tag tone={stale ? 'inc' : 'pass'} glyph={stale ? 'clock' : 'check'}>{stale ? 'Stale' : 'Current'}</Tag>
            </div>
            <dl className="kv kv-stack" id="rep-meta">
              {meta.map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="mono">{orText(v)}</dd></div>)}
            </dl>
          </article>
          <article className="panel span-7">
            <div className="panel-head">
              <h2>Outcomes</h2>
              <Tag tone={m.tone} glyph={m.glyph} title={report.aggregate ?? ''}>{m.word} · exit {m.exit}</Tag>
            </div>
            <div className="table-wrap">
              <table className="matrix">
                <thead><tr><th scope="col">Check</th><th scope="col">Decision</th><th scope="col">Base</th><th scope="col">Head</th><th scope="col">Outcome</th></tr></thead>
                <tbody id="rep-rows">
                  {checks.length ? checks.map((c) => (
                    <tr key={c.check_id}>
                      <td className="mono">{c.check_id}</td>
                      <td className="mono">{c.decision?.id || c.check?.decision_id || '—'}</td>
                      <td className="mono">{obsText(c.base)}</td>
                      <td className="mono">{obsText(c.head)}</td>
                      <td><OutcomeTag verdict={c.verdict} /><div className="enum">{c.verdict}</div></td>
                    </tr>
                  )) : <tr><td colSpan={5}>No approved check produced a result.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="field-label spaced">Warnings</p>
            <ul id="rep-warnings" className="plain-list">
              {warnings.length ? warnings.map((w, i) => (
                <li key={`${w?.code ?? 'WARNING'}-${i}`}><Icon name="alert" /><span><code>{w?.code || 'WARNING'}</code>{w?.message ? ` ${w.message}` : ''}</span></li>
              )) : <li className="ok"><Icon name="check" /><span>No warnings.</span></li>}
            </ul>
          </article>
          <Evidence title="Full report (JSON)" className="span-12"><Json value={report} /></Evidence>
        </div>
      )}
    </View>
  );
}
