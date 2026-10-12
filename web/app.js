(() => {
  const tokenMeta = document.querySelector('meta[name="ddg-session-token"]');
  const sessionToken = tokenMeta ? tokenMeta.content : '';
  const byId = (id) => document.getElementById(id);
  const VIEWS = ['overview', 'decisions', 'checks', 'runs', 'approvals', 'reports', 'settings'];
  const ALIASES = { decision: 'decisions', approval: 'approvals', review: 'runs' }; // links from the previous viewer
  const state = { value: null, view: 'overview', busy: false, started: false, selected: null };
  const SVGNS = 'http://www.w3.org/2000/svg';
  const HISTORY_KEY = 'ddg-session-runs';

  // ---- helpers: all text goes through textContent; nothing is parsed as HTML ---------------------
  const safeText = (el, value, fallback = 'Not recorded') => {
    el.textContent = value === undefined || value === null || value === '' ? fallback : String(value);
  };
  const json = (value) => (value === undefined || value === null ? 'Not recorded' : JSON.stringify(value, null, 2));
  const node = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  };
  const svgEl = (tag, attrs = {}, parent) => {
    const el = document.createElementNS(SVGNS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
    if (parent) parent.append(el);
    return el;
  };
  const icon = (name, cls = 'ic') => {
    const svg = svgEl('svg', { class: cls, 'aria-hidden': 'true' });
    svgEl('use', { href: `#i-${name}` }, svg);
    return svg;
  };
  const visible = (el, show) => { el.hidden = !show; };
  const short = (sha, n = 10) => (typeof sha === 'string' && sha ? sha.slice(0, n) : '—');
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const clock = (iso) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.valueOf()) ? d.toISOString().slice(11, 19) : '—'; };
  const setTone = (el, tone) => { el.classList.remove('is-pass', 'is-fail', 'is-pre', 'is-inc'); if (tone) el.classList.add(`is-${tone}`); };
  const tag = (el, text, tone = 'muted', glyph) => {
    el.className = `tag tag-${tone}`;
    el.replaceChildren();
    if (glyph) el.append(icon(glyph));
    el.append(document.createTextNode(text));
  };

  // ---- the product's vocabulary -------------------------------------------------------------------
  const OUTCOMES = [
    { verdict: 'VIOLATION_INTRODUCED', tone: 'fail', glyph: 'x', desc: 'Base passes; head fails. Introduced by this change.' },
    { verdict: 'PRE_EXISTING_FAILURE', tone: 'pre', glyph: 'history', desc: 'Already fails on base. Not attributed to this change.' },
    { verdict: 'RESOLVED', tone: 'pass', glyph: 'resolved', desc: 'Base fails; head passes.' },
    { verdict: 'CHECK_PASSED', tone: 'pass', glyph: 'check', desc: 'The approved check passes on both revisions.' },
    { verdict: 'NOT_CHECKED', tone: 'inc', glyph: 'help', desc: 'No result could be established. The reason is shown.' }
  ];
  const outcomeOf = (verdict) => OUTCOMES.find((o) => o.verdict === verdict) || OUTCOMES[4];
  const VERDICT_TEXT = {
    VIOLATION_INTRODUCED: 'The approved check passed on base but failed on head: this change introduces the violation.',
    PRE_EXISTING_FAILURE: 'The check already fails on base, so the failure is not attributed to this change.',
    RESOLVED: 'The check fails on base and passes on head: this change resolves an existing failure.',
    CHECK_PASSED: 'The approved check passed on both revisions.',
    NOT_CHECKED: 'Execution did not establish a result for both revisions.'
  };
  const SIGNATURE = { G: 'good signature', N: 'unsigned', B: 'bad signature', U: 'untrusted signature', E: 'signature could not be checked', X: 'expired signature', Y: 'expired key', R: 'revoked key' };
  const FIXTURES = [
    { key: 'bad', name: 'Known-bad implementation', expect: 'FAIL' },
    { key: 'good', name: 'Corrected implementation', expect: 'PASS' },
    { key: 'exception', name: 'Documented exception', expect: 'PASS' }
  ];

  const realChecks = (report) => (Array.isArray(report?.checks) ? report.checks.filter((c) => c && c.verdict !== 'HISTORICAL_CHECK_IGNORED') : []);
  const warningCodes = (report) => [...new Set((Array.isArray(report?.warnings) ? report.warnings : []).map((w) => w?.code).filter(Boolean))];
  const jobsOf = (obs) => (obs && obs.status !== 'ERROR' && Number.isInteger(obs.unique_jobs) ? obs.unique_jobs : null);
  const statusTone = (obs) => (!obs || obs.status === 'ERROR' || !obs.status ? 'inc' : obs.status === 'PASS' ? 'pass' : 'fail');
  const obsText = (obs) => (!obs?.status ? 'not observed' : obs.status === 'ERROR' ? 'ERROR · not observed' : `${obs.status}${Number.isInteger(obs.unique_jobs) ? ` · ${plural(obs.unique_jobs, 'job')}` : ''}`);
  const expectedJobs = (check) => {
    const found = (check?.assertions || []).find((a) => a.metric === 'unique_jobs');
    return found && Number.isInteger(found.equals) ? found.equals : null;
  };

  function overall(report, stale) {
    if (!report) return { tone: 'muted', word: 'NOT RUN', glyph: 'minus', exit: '—', summary: 'No run yet.' };
    if (stale) return { tone: 'inc', word: 'STALE', glyph: 'clock', exit: '—', summary: 'This report is bound to earlier revisions. Rerun required before it can be trusted.' };
    const first = realChecks(report).find((c) => c.verdict !== 'CHECK_PASSED') || realChecks(report)[0];
    if (report.aggregate === 'PASSED_CHECKS') return { tone: 'pass', word: 'PASSED', glyph: 'check', exit: '0', summary: VERDICT_TEXT[first?.verdict] || 'Every approved check held.' };
    if (report.aggregate === 'FAILED') return { tone: 'fail', word: 'FAILED', glyph: 'x', exit: '1', summary: VERDICT_TEXT[first?.verdict] || 'An approved check detected a violation.' };
    const codes = new Set(warningCodes(report));
    const summary = codes.has('POLICY_REVIEW_REQUIRED') ? 'The head changes approved policy. A reviewer must approve the new policy before this can pass.'
      : codes.has('MISSING_APPROVED_COVERAGE') || codes.has('NO_ACTIVE_APPROVED_CHECKS') ? 'An active decision has no approved check on the base revision.'
        : codes.has('APPROVER_NOT_VERIFIED') ? 'The approver of this check could not be verified, so the check did not run.'
          : codes.has('EXECUTION_ERROR') || codes.has('AUTHORITY_UNAVAILABLE') ? 'Execution or authority evidence is incomplete. Inspect the reason below.'
            : 'The gate could not prove the change safe. Never treat this as a pass.';
    return { tone: 'inc', word: 'INCOMPLETE', glyph: 'help', exit: '2', summary };
  }

  function setResult(el, model) {
    el.className = `result tone-${model.tone}`;
    const glyph = el.querySelector('.result-glyph');
    glyph.replaceChildren(icon(model.glyph, ''));
    safeText(el.querySelector('.result-word'), model.word);
  }
  function setExit(el, model) {
    el.className = `exit-chip mono tone-${model.tone === 'pre' ? 'muted' : model.tone}`;
    safeText(el, `exit ${model.exit}`);
  }

  // ---- runs observed in this browser session (DDG itself keeps only the latest report) -----------
  const loadHistory = () => { try { const v = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; } };
  function recordRun(data) {
    const report = data.report;
    if (!report?.run_at) return loadHistory();
    const id = `${report.run_at}|${report.head_ref}|${report.head_sha}`;
    const history = loadHistory();
    if (history.some((h) => h.id === id)) return history;
    const check = realChecks(report).find((c) => c.verdict !== 'CHECK_PASSED') || realChecks(report)[0];
    const label = data.scenarios?.find((s) => s.id === scenarioId(report, data.scenarios || []))?.label || report.head_ref || 'head';
    history.push({ id, at: report.run_at, label, aggregate: report.aggregate, verdict: check?.verdict || null, jobs: jobsOf(check?.head), expected: expectedJobs(check?.check) });
    const kept = history.slice(-16);
    try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(kept)); } catch { /* storage full or disabled: chart shows what it has */ }
    return kept;
  }

  // ---- charts: one block per job actually observed; missing data is a hatched outline ------------
  function drawColumns(svg, cols, { expected = null, stacked = true, colW = 64, gap = 40, unit = 46, padB = 66, notes = true, minMax = 3 } = {}) {
    svg.replaceChildren();
    const max = Math.min(6, Math.max(minMax, expected ?? 0, ...cols.map((c) => (Number.isInteger(c.jobs) ? c.jobs : 0))));
    const u = Math.min(unit, (unit * 3) / max);
    const padL = 30; const padR = expected === null ? 12 : 86; const padT = 12;
    const width = padL + padR + cols.length * (colW + gap);
    const base = padT + max * u;
    svg.setAttribute('viewBox', `0 0 ${width} ${base + padB}`);
    for (let n = 0; n <= max; n += 1) {
      const y = base - n * u;
      svgEl('line', { x1: padL, y1: y, x2: width - padR + 8, y2: y, class: 'grid-line' }, svg);
      svgEl('text', { x: padL - 10, y: y + 4, 'text-anchor': 'end', class: 'tick' }, svg).textContent = String(n);
    }
    cols.forEach((col, i) => {
      const x = padL + gap / 2 + i * (colW + gap);
      const cx = x + colW / 2;
      if (col.placeholder) return;
      const jobs = Number.isInteger(col.jobs) ? col.jobs : null;
      if (jobs === null || col.tone === 'inc') {
        const g = svgEl('g', { class: 'bar' }, svg);
        g.style.setProperty('--i', String(i));
        svgEl('rect', { x: x + 1, y: base - u + 3, width: colW - 2, height: u - 4, rx: stacked ? 7 : colW / 2.4, class: 'j-inc' }, g);
      } else if (stacked) {
        for (let k = 0; k < jobs; k += 1) {
          const g = svgEl('g', { class: 'bar' }, svg);
          g.style.setProperty('--i', String(i * 3 + k));
          svgEl('rect', { x, y: base - (k + 1) * u + 3, width: colW, height: u - 6, rx: 7, class: `j-${col.tone}` }, g);
        }
      } else if (jobs > 0) {
        const g = svgEl('g', { class: 'bar' }, svg);
        g.style.setProperty('--i', String(i));
        svgEl('rect', { x, y: base - jobs * u + 2, width: colW, height: jobs * u - 2, rx: Math.min(colW / 2, 16), class: `j-${col.tone}` }, g);
      }
      svgEl('text', { x: cx, y: base + 24, 'text-anchor': 'middle', class: 'col-value' }, svg).textContent = jobs === null ? '—' : String(jobs);
      svgEl('text', { x: cx, y: base + 42, 'text-anchor': 'middle', class: 'col-label' }, svg).textContent = col.label;
      if (notes && col.note) svgEl('text', { x: cx, y: base + 58, 'text-anchor': 'middle', class: 'col-note' }, svg).textContent = col.note;
    });
    if (Number.isInteger(expected)) {
      const y = base - expected * u;
      svgEl('line', { x1: padL, y1: y, x2: width - padR + 8, y2: y, class: 'exp-line' }, svg);
      svgEl('text', { x: width - padR + 14, y: y + 4, class: 'exp-label' }, svg).textContent = `expected ${expected}`;
    }
  }

  // ---- notices, busy state, transport ------------------------------------------------------------
  function setNotice(message, kind = 'error') {
    const notice = byId('notice');
    safeText(notice, message, '');
    notice.className = `notice notice-${kind}`;
    visible(notice, Boolean(message));
  }
  function syncControls() {
    const data = state.value || {};
    const approved = Boolean(data.approval);
    const scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
    byId('propose-button').disabled = state.busy || approved;
    byId('proposal-mode').disabled = state.busy || approved;
    byId('validate-button').disabled = state.busy || !data.draft || approved;
    byId('approve-button').disabled = state.busy || data.validation?.eligible !== true || approved;
    byId('reviewer').disabled = approved;
    byId('reason').disabled = approved;
    byId('run-button').disabled = state.busy || !approved || !scenarios.length;
    byId('scenario-select').disabled = state.busy || !approved || !scenarios.length;
    byId('download-report').disabled = !data.report;
  }
  function setBusy(busy) {
    state.busy = busy;
    document.body.classList.toggle('is-busy', busy);
    document.querySelectorAll('button').forEach((b) => b.setAttribute('aria-busy', busy ? 'true' : 'false'));
    syncControls();
  }

  async function refresh() {
    const response = await fetch('/api/state', { headers: { Accept: 'application/json' }, cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || !payload?.state) throw new Error(payload?.error || 'Could not load the local repository state.');
    state.value = payload.state;
    byId('connection-label').textContent = 'Local engine connected';
    document.querySelector('.connection-dot').classList.add('is-connected');
    if (!state.started) {
      state.started = true;
      const wanted = ALIASES[location.hash.slice(1)] || location.hash.slice(1);
      state.view = VIEWS.includes(wanted) ? wanted : 'overview';
    }
    render();
  }

  async function act(route, body) {
    if (state.busy) return;
    const pending = { propose: body?.mode === 'live' ? 'Requesting a live proposal from the provider…' : 'Loading the recorded proposal…', validate: 'Calibrating against three fixtures in the sandbox…', approve: 'Recording approval…', run: 'Running approved checks on base and head…' }[route];
    setNotice(pending, 'pending');
    setBusy(true);
    try {
      const response = await fetch(`/api/${route}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-DDG-Session': sessionToken },
        body: JSON.stringify(body)
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || `Request failed (${response.status}).`);
      if (!payload?.state) throw new Error('The server returned an invalid state response.');
      state.value = payload.state;
      if (route === 'run') state.selected = null;
      render();
      if (route === 'run') {
        const m = overall(state.value.report, state.value.report_stale === true);
        setNotice(`Run completed: ${m.word}, exit ${m.exit}.${state.view === 'runs' ? '' : ' Open Runs & Regressions to inspect it.'}`, m.tone === 'fail' ? 'error' : 'success');
      } else {
        setNotice({ propose: 'Proposal drafted. Validate it next.', validate: 'Calibration finished.', approve: 'Approval recorded. It is verified when the next run reads the approval commit.' }[route], 'success');
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'The local action failed.');
      try { await refresh(); } catch { /* keep the original error visible */ }
    } finally {
      setBusy(false);
    }
  }

  function showView(view, { scroll = false } = {}) {
    view = ALIASES[view] || view;
    if (!VIEWS.includes(view)) view = 'overview';
    state.view = view;
    document.querySelectorAll('.view').forEach((panel) => visible(panel, panel.id === `view-${view}`));
    document.querySelectorAll('.nav-item').forEach((link) => {
      const active = link.dataset.view === view;
      link.classList.toggle('is-active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    if (location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
    if (scroll) window.scrollTo({ top: 0 });
  }

  // ---- shared: scenario mapping --------------------------------------------------------------------
  function scenarioId(report, scenarios) {
    const aliases = {
      'unseen-regression': 'unseen_regression', 'approved-abort': 'abort', 'approved-crashing': 'crashing',
      'approved-timing-out': 'timing_out', 'approved-missing-entrypoint': 'missing_entrypoint',
      'policy-edit': 'policy_edit', 'preexisting-head': 'preexisting_failure'
    };
    const head = report?.head_ref;
    if (typeof head !== 'string') return null;
    const id = aliases[head] || head;
    return scenarios.some((s) => s.id === id) ? id : null;
  }

  // ---- top bar & navigation states -------------------------------------------------------------------
  function renderChrome(data) {
    const report = data.report;
    const stale = data.report_stale === true;
    const m = overall(report, stale);
    const first = realChecks(report)[0];
    const approver = first?.approver;
    safeText(byId('ws-base'), report ? `${report.base_ref || 'base'} @ ${short(report.base_sha, 7)}` : data.approval ? 'approved base' : 'no approved base');
    const sbResult = byId('sb-result');
    safeText(sbResult, report ? m.word : 'no run yet'); setTone(sbResult, report ? m.tone : null);
    const sbExit = byId('sb-exit');
    safeText(sbExit, m.exit); setTone(sbExit, report ? m.tone : null);
    const sbApprover = byId('sb-approver');
    if (report && approver) { safeText(sbApprover, approver.verified ? `verified · ${approver.commits?.[0]?.author_email || 'git author'}` : 'UNVERIFIED'); setTone(sbApprover, approver.verified ? 'pass' : 'fail'); }
    else { safeText(sbApprover, data.approval ? 'recorded · not yet verified' : 'not recorded'); setTone(sbApprover, null); }
    const sbIso = byId('sb-isolation');
    const iso = report?.sandbox;
    safeText(sbIso, !iso ? 'no run yet' : iso === 'host' ? 'host · UNSAFE' : iso); setTone(sbIso, !iso ? null : iso === 'host' ? 'fail' : iso === 'unavailable' ? 'inc' : 'pass');

    const nav = (id, text, tone) => { const el = byId(`nav-${id}`); safeText(el, text, ''); setTone(el, tone); };
    const decisions = [data.new_decision, data.old_decision].filter(Boolean);
    nav('decisions', decisions.length ? `${decisions.filter((d) => d.status === 'active').length} active` : '', null);
    const v = data.validation;
    nav('checks', data.approval ? 'approved' : v ? (v.eligible ? 'eligible' : 'needs work') : data.draft ? 'draft' : '', data.approval ? 'pass' : v && !v.eligible ? 'fail' : null);
    nav('runs', report ? (stale ? 'stale' : m.word.toLowerCase()) : '', report ? m.tone : null);
    nav('approvals', approver?.verified ? 'verified' : report && approver ? 'unverified' : data.approval ? 'recorded' : v?.eligible ? 'pending' : '', approver?.verified ? 'pass' : report && approver ? 'fail' : null);
    nav('reports', report ? 'ready' : '', null);
    nav('settings', data.draft?.proposal_mode || data.mode || '', null);
  }

  // ---- overview ---------------------------------------------------------------------------------------
  function renderOverview(data, history) {
    const report = data.report;
    const stale = data.report_stale === true;
    const m = overall(report, stale);
    visible(byId('latest-empty'), !report);
    visible(byId('latest-body'), Boolean(report));
    if (report) {
      setResult(byId('ov-result'), m);
      setExit(byId('ov-exit'), m);
      safeText(byId('ov-base-ref'), report.base_ref, 'base');
      safeText(byId('ov-head-ref'), data.scenarios?.find((s) => s.id === scenarioId(report, data.scenarios || []))?.label || report.head_ref, 'head');
      safeText(byId('ov-base-sha'), short(report.base_sha));
      safeText(byId('ov-head-sha'), short(report.head_sha));
      const focus = realChecks(report).find((c) => c.verdict !== 'CHECK_PASSED') || realChecks(report)[0];
      safeText(byId('ov-check'), focus ? `${focus.check_id} · ${focus.decision?.id || focus.check?.decision_id || 'decision'} · ${focus.verdict}` : 'No approved check produced a result');
      safeText(byId('ov-summary'), m.summary);
    }

    const counts = Object.fromEntries(OUTCOMES.map((o) => [o.verdict, 0]));
    realChecks(report).forEach((c) => { counts[outcomeOf(c.verdict).verdict] += 1; });
    const list = byId('ov-outcomes');
    list.replaceChildren();
    OUTCOMES.forEach((o) => {
      const li = node('li', `outcome o-${o.tone}${counts[o.verdict] ? '' : ' is-zero'}`);
      li.append(icon(o.glyph), node('span', 'outcome-name', o.verdict), node('span', 'outcome-n', report ? counts[o.verdict] : '—'));
      list.append(li);
    });

    const approvedChecks = report ? realChecks(report).length : data.approval ? 1 : 0;
    safeText(byId('st-approved'), approvedChecks);
    safeText(byId('st-approved-note'), data.approval ? `${data.approval.check_id} on the approved base` : 'none on the approved base');
    const active = report?.active_decisions || [data.new_decision].filter((d) => d?.status === 'active');
    safeText(byId('st-decisions'), active.length);
    safeText(byId('st-decisions-note'), active.map((d) => d.id).join(', '), 'none recorded');
    const v = data.validation;
    const cal = byId('st-calibration');
    safeText(cal, v ? (v.eligible ? 'Eligible' : 'Needs work') : data.draft ? 'Not run' : 'No draft');
    setTone(cal, v ? (v.eligible ? 'pass' : 'fail') : null);
    safeText(byId('st-calibration-note'), v ? `${FIXTURES.filter((f) => v.cases?.[f.key]?.observation?.status === f.expect).length} of 3 fixtures matched` : '3 fixtures required');
    safeText(byId('st-runs'), history.length);
    safeText(byId('st-runs-note'), history.length ? `last at ${clock(history[history.length - 1].at)} UTC` : 'in this browser tab');

    const chart = byId('history-chart');
    if (!history.length) {
      chart.replaceChildren();
      chart.setAttribute('viewBox', '0 0 600 60');
      svgEl('text', { x: 0, y: 34, class: 'col-note' }, chart).textContent = 'No runs in this tab yet.';
      chart.setAttribute('aria-label', 'No runs in this tab yet');
    } else {
      const cols = history.map((h) => ({
        label: h.label.length > 12 ? `${h.label.slice(0, 11)}…` : h.label,
        note: clock(h.at),
        jobs: h.jobs,
        tone: h.aggregate === 'INCOMPLETE' || h.verdict === 'NOT_CHECKED' || h.jobs === null ? 'inc' : h.verdict === 'PRE_EXISTING_FAILURE' ? 'pre' : h.aggregate === 'FAILED' ? 'fail' : 'pass'
      }));
      const expected = history.map((h) => h.expected).find(Number.isInteger) ?? null;
      while (cols.length < 6) cols.push({ placeholder: true });
      drawColumns(chart, cols, { expected, stacked: false, colW: 34, gap: 48, unit: 38 });
      chart.setAttribute('aria-label', `Runs this session: ${history.map((h) => `${h.label} ${h.aggregate}${h.jobs === null ? ', not observed' : `, ${plural(h.jobs, 'job')}`}`).join('; ')}`);
    }

    const items = attentionItems(data, m);
    const ul = byId('attention');
    ul.replaceChildren();
    items.forEach((it) => {
      const li = node('li', `a-${it.tone}`);
      const body = node('div');
      const p = node('p'); p.append(node('b', '', it.title), document.createTextNode(it.text ? ` ${it.text}` : ''));
      body.append(p);
      if (it.href) { const a = node('a', '', it.link); a.href = `#${it.href}`; body.append(a); }
      li.append(icon(it.glyph), body);
      ul.append(li);
    });
    const actionable = items.filter((i) => i.tone !== 'ok').length;
    const count = byId('attention-count');
    safeText(count, actionable);
    count.className = `count-chip${actionable ? '' : ''}`;
  }

  function attentionItems(data, m) {
    const out = [];
    const report = data.report;
    const v = data.validation;
    if (!data.draft) out.push({ tone: 'todo', glyph: 'checks', title: 'No check drafted.', text: 'Draft a check for the active decision.', href: 'checks', link: 'Open Check Studio' });
    else if (!v) out.push({ tone: 'todo', glyph: 'checks', title: 'Proposal not calibrated.', text: 'Validate it against the three fixtures.', href: 'checks', link: 'Validate' });
    else if (!v.eligible) out.push({ tone: 'fail', glyph: 'x', title: 'Calibration failed.', text: 'This check cannot be approved.', href: 'checks', link: 'See the matrix' });
    else if (!data.approval) out.push({ tone: 'todo', glyph: 'approvals', title: `${data.draft.check?.id || 'Check'} is eligible.`, text: 'It still needs human approval of the exact check.', href: 'approvals', link: 'Review and approve' });
    if (data.approval && !report) out.push({ tone: 'todo', glyph: 'play', title: 'No run yet.', text: 'Compare a candidate head against the approved base.', href: 'runs', link: 'New run' });
    if (report) {
      if (data.report_stale === true) out.push({ tone: 'inc', glyph: 'clock', title: 'Report is stale.', text: 'Refs moved since this run.', href: 'runs', link: 'Rerun' });
      realChecks(report).filter((c) => c.verdict === 'VIOLATION_INTRODUCED').forEach((c) => out.push({ tone: 'fail', glyph: 'x', title: `${c.decision?.id || c.check?.decision_id} regressed.`, text: `${c.check_id} fails on head ${report.head_ref}.`, href: 'runs', link: 'Inspect evidence' }));
      realChecks(report).filter((c) => c.verdict === 'NOT_CHECKED').forEach((c) => out.push({ tone: 'inc', glyph: 'help', title: `${c.check_id} not checked.`, text: c.error || c.head?.error || c.base?.error || 'No result established.', href: 'runs', link: 'See reason' }));
      if (m.tone === 'inc' && !realChecks(report).some((c) => c.verdict === 'NOT_CHECKED')) out.push({ tone: 'inc', glyph: 'help', title: 'Run incomplete.', text: m.summary, href: 'runs', link: 'See warnings' });
      const approver = realChecks(report)[0]?.approver;
      if (approver && !approver.verified) out.push({ tone: 'fail', glyph: 'user', title: 'Approver not verified.', text: approver.reason || '', href: 'approvals', link: 'See provenance' });
      if (report.sandbox === 'host') out.push({ tone: 'inc', glyph: 'box', title: 'Head ran without isolation.', text: 'Sandbox mode was host.', href: 'reports', link: 'See report' });
    }
    if (!out.length) out.push({ tone: 'ok', glyph: 'check', title: 'Nothing needs attention.', text: 'The latest run passed with a verified approver in an isolated sandbox.' });
    return out;
  }

  // ---- decisions ---------------------------------------------------------------------------------------
  function renderDecisions(data) {
    const list = byId('decision-list');
    list.replaceChildren();
    const linked = data.approval?.check_id || data.draft?.check?.id;
    const linkedDecision = data.draft?.check?.decision_id;
    const decisions = [data.new_decision, data.old_decision].filter(Boolean);
    if (!decisions.length) list.append(node('li', 'panel empty', 'No decision records were found in .ddg/decisions/.'));
    decisions.forEach((d) => {
      const activeD = d.status === 'active';
      const li = node('li', `panel decision ${activeD ? 'is-active' : 'is-superseded'}`);
      const head = node('div', 'decision-head');
      head.append(node('span', 'decision-id', d.id));
      const status = node('span');
      tag(status, activeD ? 'Active' : d.status === 'superseded' ? 'Superseded' : d.status || 'unknown', activeD ? 'pass' : 'muted', activeD ? 'check' : 'history');
      head.append(status);
      if (activeD && linkedDecision === d.id && linked) { const c = node('span'); tag(c, `protected by ${linked}`, data.approval ? 'pass' : 'muted', 'approvals'); head.append(c); }
      li.append(head, node('p', 'decision-rule', d.rule || 'No rule text recorded.'));
      (Array.isArray(d.exceptions) ? d.exceptions : []).forEach((e) => li.append(node('p', 'decision-exc', `Permitted exception: ${e}`)));
      const meta = node('p', 'decision-meta');
      const kv = (k, val) => { const s = node('span', '', `${k} `); s.append(node('b', '', val)); meta.append(s); };
      kv('scope', d.scope || '—');
      kv('supersedes', d.supersedes || 'nothing');
      kv('schema', `v${d.schema_version ?? '?'}`);
      if (activeD && data.draft?.source_sha) kv('read at', short(data.draft.source_sha));
      li.append(meta);
      if (activeD) { const a = node('a', 'text-link', 'Open in Check Studio'); a.href = '#checks'; a.append(icon('arrow')); li.append(a); }
      list.append(li);
    });
    byId('decision-evidence').textContent = json({ active: data.new_decision, superseded: data.old_decision });
  }

  // ---- check studio --------------------------------------------------------------------------------------
  function proposalLabel(draft, mode) {
    const m = draft?.proposal_mode || mode;
    return m === 'live' ? 'Live proposal' : m === 'recorded' ? 'Recorded proposal' : m === 'manual' ? 'Manual check' : 'Source unknown';
  }
  function assertionLines(el, check) {
    el.replaceChildren();
    const list = Array.isArray(check?.assertions) ? check.assertions : [];
    if (!list.length) { el.textContent = '—'; return; }
    list.forEach((a, i) => {
      if (i) el.append(document.createTextNode('\n'));
      el.append(node('span', 'kw', 'expect '), document.createTextNode(`${a.metric || 'unknown'} == `), node('span', 'num', a.equals === undefined ? 'unset' : JSON.stringify(a.equals)));
    });
  }

  function renderStudio(data) {
    const draft = data.draft;
    const check = draft?.check || null;
    const v = data.validation;
    if (draft?.proposal_mode === 'live' || draft?.proposal_mode === 'recorded') byId('proposal-mode').value = draft.proposal_mode;
    if (!draft) {
      tag(byId('proposal-source-label'), 'No proposal loaded');
      safeText(byId('proposal-provenance'), 'Choose a source and draft a proposal.');
    } else {
      tag(byId('proposal-source-label'), proposalLabel(draft, data.mode), draft.proposal_mode === 'live' ? 'pre' : 'muted');
      safeText(byId('proposal-provenance'), [draft.request_metadata?.provider, draft.model, draft.captured_at].filter(Boolean).join(' · '), 'provenance unavailable');
    }
    safeText(byId('check-id'), check?.id, 'not recorded');
    safeText(byId('check-decision'), check ? `${check.decision_id}${check.supersedes ? ` (supersedes ${check.supersedes})` : ''}` : '—');
    safeText(byId('check-scenario'), check?.scenario, '—');
    safeText(byId('check-adapter'), check?.adapter || draft?.adapter_version, '—');
    safeText(byId('check-rationale'), check?.rationale, 'Draft a proposal to inspect its scenario, assertions and decision citation.');
    assertionLines(byId('assertions'), check);
    const cites = byId('check-citation');
    cites.replaceChildren();
    const citations = Array.isArray(check?.citations) ? check.citations : [];
    if (!citations.length) cites.append(node('li', '', check ? 'No exact decision citation.' : 'No citation loaded.'));
    citations.forEach((c) => { const li = node('li', '', `“${c.quote}” `); li.append(node('code', '', c.decision_id)); cites.append(li); });

    const body = byId('matrix-body');
    body.replaceChildren();
    let matched = 0;
    FIXTURES.forEach((f) => {
      const obs = v?.cases?.[f.key]?.observation;
      const ok = obs?.status === f.expect;
      if (ok) matched += 1;
      const tr = node('tr');
      const name = node('td'); name.append(node('div', '', f.name), node('div', 'mono small muted', short(v?.cases?.[f.key]?.sha || v?.calibration_hashes?.[f.key], 7)));
      const exp = node('td', 'mono', f.expect === 'PASS' ? 'Pass' : 'Fail');
      const got = node('td', 'mono', obs?.status ? (obs.status === 'PASS' ? 'Pass' : obs.status === 'FAIL' ? 'Fail' : 'Error') : '—');
      const jobs = node('td', 'mono', Number.isInteger(obs?.unique_jobs) ? obs.unique_jobs : '—');
      const elig = node('td'); const t = node('span');
      if (!v) tag(t, 'Not run'); else tag(t, ok ? 'Valid' : 'Mismatch', ok ? 'pass' : 'fail', ok ? 'check' : 'x');
      elig.append(t);
      tr.append(name, exp, got, jobs, elig);
      body.append(tr);
    });
    tag(byId('validation-status'), v ? (v.eligible ? 'Eligible' : 'Needs work') : 'Not run', v ? (v.eligible ? 'pass' : 'fail') : 'muted', v ? (v.eligible ? 'check' : 'x') : null);
    safeText(byId('calibration-explanation'), v ? (v.eligible ? `${matched} of 3 fixtures matched. Human approval of the exact check is still required.` : `${matched} of 3 fixtures matched. This check cannot be approved.`) : 'Validation executes the proposal against all three fixtures in the sandbox.');
    tag(byId('cs-eligibility'), `Calibration · ${v ? (v.eligible ? 'eligible' : 'needs work') : 'not run'}`, v ? (v.eligible ? 'pass' : 'fail') : 'muted');
    tag(byId('cs-approval'), `Approval · ${data.approval ? 'recorded' : 'pending'}`, data.approval ? 'pre' : 'muted');

    const chart = byId('cal-chart');
    visible(chart, Boolean(v));
    if (v) {
      const cols = FIXTURES.map((f) => { const o = v.cases?.[f.key]?.observation; return { label: f.key === 'bad' ? 'Known-bad' : f.key === 'good' ? 'Corrected' : 'Exception', jobs: jobsOf(o), tone: statusTone(o) }; });
      drawColumns(chart, cols, { expected: expectedJobs(check), colW: 52, gap: 34, unit: 34, padB: 50, notes: false });
      chart.setAttribute('aria-label', `Calibration: ${cols.map((c) => `${c.label} ${c.jobs === null ? 'not observed' : plural(c.jobs, 'job')}`).join(', ')}`);
    }
    byId('draft-evidence').textContent = json(draft);
    byId('validation-evidence').textContent = json(v);
  }

  // ---- runs & regressions ----------------------------------------------------------------------------------
  function renderScenarioSelect(data) {
    const select = byId('scenario-select');
    const prior = select.value;
    select.replaceChildren();
    const scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
    if (!scenarios.length) select.append(new Option('Approve a check first', ''));
    scenarios.forEach((s) => select.append(new Option(s.label || s.id, s.id)));
    const current = scenarioId(data.report, scenarios);
    if (prior && scenarios.some((s) => s.id === prior)) select.value = prior;
    else if (current) select.value = current;
  }

  function trace(el, obs) {
    el.replaceChildren();
    const events = Array.isArray(obs?.events) ? obs.events : [];
    if (!events.length) { el.append(node('li', 'empty-ev', obs?.error ? `No trace: ${obs.error}` : 'No events recorded.')); return; }
    const jobs = new Set();
    events.forEach((e) => {
      const name = e?.event;
      let text = name || 'event';
      let cls = '';
      if (name === 'submit') text = `submit · call ${e.call ?? '?'}`;
      else if (name === 'accepted') { text = `job ${e.job_id} created`; cls = jobs.size ? 'ev-dup' : 'ev-accepted'; if (jobs.size) text += ' · duplicate'; jobs.add(e.job_id); }
      else if (name === 'response') text = `service returned ${e.status ?? '?'}`;
      else if (name === 'lookup') text = e.job_id ? `lookup found ${e.job_id}` : 'lookup found nothing';
      else if (name === 'deduplicated') text = `stable key reused ${e.job_id}`;
      el.append(node('li', cls, text));
    });
  }

  function renderRuns(data) {
    renderScenarioSelect(data);
    const report = data.report;
    const stale = data.report_stale === true;
    const m = overall(report, stale);
    visible(byId('stale-notice'), Boolean(report && stale));
    visible(byId('empty-run'), !report);
    visible(byId('run-content'), Boolean(report));
    safeText(byId('run-cli'), report ? `ddg run --base ${report.base_ref} --head ${report.head_ref}` : 'ddg run --base <approved-ref> --head <candidate-ref>');
    if (!report) return;

    const summary = byId('run-summary');
    summary.className = `run-summary tone-${m.tone}`;
    setResult(byId('run-result'), m);
    setExit(byId('run-exit'), m);
    safeText(byId('run-summary-text'), m.summary);
    safeText(byId('run-base-ref'), report.base_ref, 'base');
    safeText(byId('run-head-ref'), data.scenarios?.find((s) => s.id === scenarioId(report, data.scenarios || []))?.label || report.head_ref, 'head');
    safeText(byId('run-base-sha'), report.base_sha);
    safeText(byId('run-head-sha'), report.head_sha);
    safeText(byId('run-sandbox'), report.sandbox === 'host' ? 'host (UNSAFE, no isolation)' : report.sandbox, 'not recorded');

    const checks = realChecks(report);
    safeText(byId('results-count'), plural(checks.length, 'approved check'));
    if (!checks.some((c) => c.check_id === state.selected)) state.selected = (checks.find((c) => c.verdict !== 'CHECK_PASSED') || checks[0])?.check_id || null;
    const groups = byId('result-groups');
    groups.replaceChildren();
    OUTCOMES.forEach((o) => {
      const members = checks.filter((c) => outcomeOf(c.verdict).verdict === o.verdict);
      const g = node('div', `group g-${o.tone}${members.length ? '' : ' is-empty'}`);
      const head = node('div', 'group-head');
      head.append(icon(o.glyph), node('span', '', o.verdict), node('span', 'n', members.length));
      g.append(head, node('p', 'group-desc', o.desc));
      const rows = node('div', 'group-rows');
      members.forEach((c) => {
        const b = node('button', 'result-row');
        b.type = 'button';
        b.setAttribute('aria-pressed', String(c.check_id === state.selected));
        b.append(node('span', 'rr-id', c.check_id), node('span', 'rr-dec', c.decision?.id || c.check?.decision_id || ''), node('span', 'rr-obs', `base ${obsText(c.base)}  →  head ${obsText(c.head)}`));
        b.addEventListener('click', () => { state.selected = c.check_id; renderRuns(state.value); });
        rows.append(b);
      });
      g.append(rows);
      groups.append(g);
    });
    if (!checks.length) groups.append(node('p', 'body-copy', 'No approved check produced a result for this run.'));

    const warnBox = byId('run-warnings');
    const warnings = Array.isArray(report.warnings) ? report.warnings : [];
    visible(warnBox, warnings.length > 0);
    warnBox.replaceChildren(node('p', 'field-label', 'Warnings'));
    warnings.forEach((w) => { const p = node('p', 'warning'); const t = node('span'); t.append(node('code', '', w?.code || 'WARNING'), document.createTextNode(w?.message ? ` ${w.message}` : w?.detail ? ` ${w.detail}` : '')); p.append(icon('alert'), t); warnBox.append(p); });

    renderDetail(report, checks.find((c) => c.check_id === state.selected) || null);
  }

  function renderDetail(report, c) {
    const o = c ? outcomeOf(c.verdict) : null;
    tag(byId('detail-verdict'), c ? c.verdict : 'no check', o ? o.tone : 'muted', o ? o.glyph : null);
    const reason = c && c.verdict === 'NOT_CHECKED' ? ` Reason: ${c.error || c.head?.error || c.base?.error || 'not recorded'}.` : '';
    safeText(byId('detail-explain'), c ? `${VERDICT_TEXT[c.verdict] || 'Outcome not recognised; treated as not checked.'}${reason}` : 'Select a check result to inspect its evidence.');
    const decision = c?.decision || report.active_decisions?.find((d) => d.id === c?.check?.decision_id);
    safeText(byId('detail-decision'), decision ? `${decision.id} · ${decision.rule}` : 'Governing decision not present in the report.');
    safeText(byId('detail-check'), c?.check_id, '—');
    safeText(byId('detail-digest'), short(c?.check_digest, 12));
    assertionLines(byId('detail-assertions'), c?.check);
    const field = byId('state-field');
    if (c) {
      drawColumns(field, [
        { label: 'Base', note: obsText(c.base), jobs: jobsOf(c.base), tone: statusTone(c.base) },
        { label: 'Head', note: obsText(c.head), jobs: jobsOf(c.head), tone: statusTone(c.head) }
      ], { expected: expectedJobs(c.check), colW: 92, gap: 90, unit: 44 });
      field.setAttribute('aria-label', `Jobs created for one operation. Base ${obsText(c.base)}. Head ${obsText(c.head)}.${Number.isInteger(expectedJobs(c.check)) ? ` The check expects ${plural(expectedJobs(c.check), 'job')}.` : ''}`);
    } else { field.replaceChildren(); }
    const side = (id, obs) => { const el = byId(id); safeText(el, obsText(obs)); setTone(el, statusTone(obs)); };
    side('detail-base', c?.base); side('detail-head', c?.head);
    trace(byId('trace-base'), c?.base);
    trace(byId('trace-head'), c?.head);
    const diff = typeof c?.diff === 'string' ? c.diff.trim() : '';
    visible(byId('detail-diff-block'), Boolean(diff));
    byId('detail-diff').textContent = diff;
    const ap = c?.approval; const who = c?.approver; const commit = who?.commits?.[0];
    safeText(byId('detail-approval'), c ? [
      ap ? `Approved ${ap.approved_at || ''} with review label “${ap.reviewer}”.` : 'No approval record in the report.',
      who ? (who.verified ? `Git author ${commit?.author_email || 'unknown'} verified against the allowlist (${SIGNATURE[commit?.signature] || 'signature not reported'}).` : `Approver NOT verified${who.reason ? `: ${who.reason}` : ''}.`) : 'Approver verification not reported.'
    ].join(' ') : '—');
    const ord = report.ordinary_tests || {};
    safeText(byId('ordinary-base'), obsText(ord.base));
    safeText(byId('ordinary-head'), obsText(ord.head));
  }

  // ---- approvals ----------------------------------------------------------------------------------------------
  function renderApprovals(data) {
    const draft = data.draft; const v = data.validation; const ap = data.approval;
    const first = realChecks(data.report)[0];
    const who = data.report ? first?.approver : null;
    const commit = who?.commits?.[0];
    const step = (n, cls, text) => { const li = byId(`flow-${n}`); li.className = `flow-step ${cls}`; safeText(byId(`flow-${n}-text`), text); };
    step(1, draft ? 'is-done' : 'is-current', draft ? `${draft.check?.id} · draft ${short(draft.draft_digest, 8)}` : 'Draft a proposal in Check Studio.');
    const matched = FIXTURES.filter((f) => v?.cases?.[f.key]?.observation?.status === f.expect).length;
    step(2, v ? (v.eligible ? 'is-done' : 'is-failed') : draft ? 'is-current' : '', v ? (v.eligible ? `${matched} of 3 fixtures matched` : `${matched} of 3 matched; approval unavailable`) : 'Calibration not run.');
    step(3, ap ? 'is-done' : v?.eligible ? 'is-current' : '', ap ? `Recorded ${clock(ap.approved_at)} UTC · label “${ap.reviewer}”` : v?.eligible ? 'Approve the exact check below.' : 'Waiting for an eligible check.');
    step(4, who?.verified ? 'is-done' : who ? 'is-failed' : ap ? 'is-current' : '', who?.verified ? `Verified · ${commit?.author_email}` : who ? `Unverifiable${who.reason ? `: ${who.reason}` : ''}` : ap ? 'Verified when the next run reads the approval commit.' : 'Nothing committed yet.');

    tag(byId('approval-state'), who?.verified ? 'Verified' : who ? 'Unverifiable' : ap ? 'Recorded · awaiting verification' : v?.eligible ? 'Pending' : 'Not eligible yet',
      who?.verified ? 'pass' : who ? 'fail' : ap ? 'pre' : 'muted', who?.verified ? 'check' : who ? 'x' : ap ? 'clock' : null);
    safeText(byId('approve-target'), draft?.check?.id ? `${draft.check.id} · ${short(draft.draft_digest, 8)}` : '—');
    visible(byId('approval-form'), !ap);
    visible(byId('approval-record'), Boolean(ap));
    if (ap) {
      safeText(byId('rec-check'), ap.check_id);
      safeText(byId('rec-label'), ap.reviewer);
      safeText(byId('rec-note'), ap.reason);
      safeText(byId('rec-time'), ap.approved_at);
      safeText(byId('rec-digest'), ap.bundle_digest);
      safeText(byId('rec-vdigest'), ap.validation_digest);
    }
    tag(byId('git-state'), who?.verified ? 'Verified' : who ? 'Unverifiable' : 'Not yet verified', who?.verified ? 'pass' : who ? 'fail' : 'muted', who?.verified ? 'check' : who ? 'x' : null);
    safeText(byId('rec-author'), who ? `${commit?.author_email || 'unknown'}${who.verified ? ' · on allowlist' : ''}` : null, 'verified when a run reads the approval commit');
    safeText(byId('rec-commit'), commit?.commit, '—');
    safeText(byId('rec-signature'), commit ? `${SIGNATURE[commit.signature] || commit.signature}${commit.signer ? ` · ${commit.signer}` : ''}` : null, '—');
    safeText(byId('rec-require'), who ? (who.require_signed ? 'yes' : 'no (allowlist only)') : null, '—');
    const h = ap?.calibration_hashes;
    safeText(byId('rec-hashes'), h ? `bad ${short(h.bad, 7)} · good ${short(h.good, 7)} · exception ${short(h.exception, 7)}` : null, '—');
  }

  // ---- reports -------------------------------------------------------------------------------------------------
  function renderReports(data) {
    const report = data.report;
    const stale = data.report_stale === true;
    visible(byId('empty-report'), !report);
    visible(byId('report-content'), Boolean(report));
    if (!report) return;
    const m = overall(report, stale);
    tag(byId('rep-fresh'), stale ? 'Stale' : 'Current', stale ? 'inc' : 'pass', stale ? 'clock' : 'check');
    tag(byId('rep-result'), `${report.aggregate} · exit ${m.exit}`, m.tone, m.glyph);
    const meta = byId('rep-meta');
    meta.replaceChildren();
    [['Overall', `${report.aggregate || 'unknown'} (exit ${m.exit})`], ['Run at', report.run_at], ['Base', `${report.base_ref} @ ${report.base_sha}`], ['Head', `${report.head_ref} @ ${report.head_sha}`],
      ['Adapter', report.adapter_version], ['Isolation', report.sandbox === 'host' ? 'host (UNSAFE)' : report.sandbox], ['Checks evaluated', realChecks(report).length]].forEach(([k, val]) => {
      const row = node('div'); row.append(node('dt', '', k), node('dd', 'mono', val ?? 'not recorded')); meta.append(row);
    });
    const rows = byId('rep-rows');
    rows.replaceChildren();
    realChecks(report).forEach((c) => {
      const tr = node('tr');
      const o = outcomeOf(c.verdict); const t = node('span'); tag(t, c.verdict, o.tone, o.glyph);
      const out = node('td'); out.append(t);
      tr.append(node('td', 'mono', c.check_id), node('td', 'mono', c.decision?.id || c.check?.decision_id || '—'), node('td', 'mono', obsText(c.base)), node('td', 'mono', obsText(c.head)), out);
      rows.append(tr);
    });
    if (!rows.children.length) { const tr = node('tr'); const td = node('td', '', 'No approved check produced a result.'); td.colSpan = 5; tr.append(td); rows.append(tr); }
    const wl = byId('rep-warnings');
    wl.replaceChildren();
    const warnings = Array.isArray(report.warnings) ? report.warnings : [];
    if (!warnings.length) { const li = node('li', 'ok'); li.append(icon('check'), node('span', '', 'No warnings.')); wl.append(li); }
    warnings.forEach((w) => { const li = node('li'); const s = node('span'); s.append(node('code', '', w?.code || 'WARNING'), document.createTextNode(w?.message ? ` ${w.message}` : '')); li.append(icon('alert'), s); wl.append(li); });
    byId('report-evidence').textContent = json(report);
  }

  // ---- providers ------------------------------------------------------------------------------------------------
  function renderSettings(data) {
    const draft = data.draft;
    const mode = draft?.proposal_mode || data.mode;
    tag(byId('prov-mode'), mode ? proposalLabel(draft, data.mode) : 'No proposal', mode === 'live' ? 'pre' : 'muted');
    const meta = byId('prov-meta');
    meta.replaceChildren();
    const rm = draft?.request_metadata || {};
    const rows = draft ? [['Provider', rm.provider || (mode === 'recorded' ? 'recorded capture (no network call)' : 'not recorded')], ['Model', draft.model], ['Prompt version', rm.prompt_version], ['Timeout', rm.timeout_seconds ? `${rm.timeout_seconds}s` : null],
      ['Client', draft.sdk_version], ['Captured at', draft.captured_at], ['Attempts', Array.isArray(draft.attempts) ? draft.attempts.map((a) => a.result).join(', ') : null]] : [['Status', 'No proposal has been drafted.']];
    rows.forEach(([k, val]) => { const row = node('div'); row.append(node('dt', '', k), node('dd', 'mono', val ?? 'not recorded')); meta.append(row); });
  }

  // ---- render -----------------------------------------------------------------------------------------------------
  function render() {
    const data = state.value;
    if (!data) return;
    const history = recordRun(data);
    renderChrome(data);
    renderOverview(data, history);
    renderDecisions(data);
    renderStudio(data);
    renderRuns(data);
    renderApprovals(data);
    renderReports(data);
    renderSettings(data);
    syncControls();
    showView(state.view);
  }

  window.addEventListener('hashchange', () => showView(location.hash.slice(1), { scroll: true }));
  byId('propose-button').addEventListener('click', () => act('propose', { mode: byId('proposal-mode').value }));
  byId('validate-button').addEventListener('click', () => { const d = state.value?.draft; if (d?.draft_digest) act('validate', { draft_digest: d.draft_digest }); });
  byId('approval-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const d = state.value?.draft;
    if (!d?.draft_digest || byId('approve-button').disabled) return;
    act('approve', { draft_digest: d.draft_digest, reviewer: byId('reviewer').value.trim(), reason: byId('reason').value.trim() });
  });
  byId('run-button').addEventListener('click', () => { const s = byId('scenario-select').value; if (s) act('run', { scenario: s }); });
  byId('download-report').addEventListener('click', () => {
    const report = state.value?.report;
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
    const a = node('a'); a.href = url; a.download = `ddg-report-${report.head_ref || 'head'}-${(report.run_at || '').replace(/[:]/g, '')}.json`;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  refresh().catch((error) => {
    byId('connection-label').textContent = 'Local engine unavailable';
    setNotice(error instanceof Error ? error.message : 'Could not connect to the local engine.');
    showView(ALIASES[location.hash.slice(1)] || location.hash.slice(1));
  });
})();
