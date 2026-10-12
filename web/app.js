(() => {
  const tokenMeta = document.querySelector('meta[name="ddg-session-token"]');
  const sessionToken = tokenMeta ? tokenMeta.content : '';
  const byId = (id) => document.getElementById(id);
  const state = { value: null, view: 'decision', busy: false };
  const VIEWS = ['decision', 'approval', 'review'];
  const SVGNS = 'http://www.w3.org/2000/svg';

  // ---- small helpers (all text is set with textContent; nothing is parsed as HTML) -------------
  const safeText = (el, value, fallback = 'Not recorded') => {
    el.textContent = value === undefined || value === null || value === '' ? fallback : String(value);
  };
  const objectText = (value) => (value === undefined || value === null ? 'Not recorded' : JSON.stringify(value, null, 2));
  const node = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const svgEl = (tag, attrs = {}, parent) => {
    const el = document.createElementNS(SVGNS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
    if (parent) parent.append(el);
    return el;
  };
  const visible = (el, show) => { el.hidden = !show; };
  const formatLabel = (value) => String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
  const short = (sha) => (typeof sha === 'string' ? sha.slice(0, 10) : '—');
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const setTone = (el, tone) => {
    el.classList.remove('is-good', 'is-warn', 'is-bad');
    if (tone) el.classList.add(`is-${tone}`);
  };

  function setNotice(message, kind = 'error') {
    const notice = byId('notice');
    safeText(notice, message, '');
    notice.className = `notice notice-${kind}`;
    visible(notice, Boolean(message));
  }

  function setBusy(busy) {
    state.busy = busy;
    document.body.classList.toggle('is-busy', busy);
    document.querySelectorAll('button').forEach((button) => button.setAttribute('aria-busy', busy ? 'true' : 'false'));
    syncControls();
  }

  function syncControls() {
    const data = state.value || {};
    const approved = Boolean(data.approval);
    byId('propose-button').disabled = state.busy || approved;
    byId('proposal-mode').disabled = state.busy || approved;
    byId('validate-button').disabled = state.busy || !data.draft || approved;
    byId('approve-button').disabled = state.busy || data.validation?.eligible !== true || approved;
    byId('run-button').disabled = state.busy || !approved || !(data.scenarios || []).length;
    byId('scenario-select').disabled = state.busy || !approved || !(data.scenarios || []).length;
  }

  async function refresh() {
    const response = await fetch('/api/state', { headers: { Accept: 'application/json' }, cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || !payload || !payload.state) throw new Error(payload?.error || 'Could not load the local demo state.');
    state.value = payload.state;
    byId('connection-label').textContent = 'Local demo connected';
    document.querySelector('.connection-dot').classList.add('is-connected');
    if (!state.started) {
      // Choose the opening view before the first render so render() never overwrites a deep link.
      state.started = true;
      const wanted = location.hash.slice(1);
      state.view = VIEWS.includes(wanted) ? wanted : payload.state.approval ? 'review' : 'decision';
    }
    render();
  }

  async function act(route, body) {
    if (state.busy) return;
    const pending = route === 'propose'
      ? body.mode === 'live' ? 'Requesting live proposal…' : 'Loading recorded proposal…'
      : route === 'validate' ? 'Calibrating proposal…'
        : route === 'approve' ? 'Recording approval…' : 'Running approved check…';
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
      if (!payload || !payload.state) throw new Error('The server returned an invalid state response.');
      state.value = payload.state;
      render();
      setNotice(route === 'run' ? 'Execution completed. The result below comes from this run.' : 'Change saved.', 'success');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'The local action failed.');
      try { await refresh(); } catch { /* keep the action error visible when a reload also fails */ }
    } finally {
      setBusy(false);
    }
  }

  function showView(view) {
    if (!VIEWS.includes(view)) view = 'decision';
    state.view = view;
    document.querySelectorAll('.view').forEach((panel) => visible(panel, panel.id === `view-${view}`));
    document.querySelectorAll('.nav-item').forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    if (location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
  }

  const tagClass = (tone) => `tag tag-${tone}`;
  function setBadge(el, text, tone = 'muted') {
    safeText(el, text);
    el.className = tagClass(tone);
  }

  // ---- the state field: one slab per job actually observed ------------------------------------
  function drawField(svg, columns, { unit = 78, expected = null, compact = false } = {}) {
    svg.replaceChildren();
    const observed = columns.map((c) => (Number.isInteger(c.jobs) ? c.jobs : 0));
    const max = Math.min(6, Math.max(3, expected ?? 0, ...observed));
    const u = unit * 3 / max;
    const colW = compact ? 40 : 96;
    const depth = compact ? 13 : 28;
    const gap = compact ? 22 : 56;
    const padL = compact ? 22 : 38;
    const padR = compact ? 50 : 92;
    const padT = compact ? 14 : 26;
    const padB = compact ? 50 : 84;
    const span = colW + depth + gap;
    const width = padL + padR + columns.length * span;
    const base = padT + depth + max * u;
    const height = base + padB;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const defs = svgEl('defs', {}, svg);
    const hatch = svgEl('pattern', { id: `hatch-${svg.id}`, width: 8, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
    svgEl('line', { x1: 0, y1: 0, x2: 0, y2: 8, class: 'hatch-line' }, hatch);

    for (let n = 0; n <= max; n += 1) {
      const y = base - n * u;
      svgEl('line', { x1: padL, y1: y, x2: width - padR + 10, y2: y, class: 'grid-line' }, svg);
      const tick = svgEl('text', { x: padL - 9, y: y + 4, 'text-anchor': 'end', class: 'tick' }, svg);
      tick.textContent = String(n);
    }
    if (Number.isInteger(expected)) {
      const y = base - expected * u;
      svgEl('line', { x1: padL, y1: y, x2: width - padR + 10, y2: y, class: 'expect-line' }, svg);
      const label = svgEl('text', { x: width - padR + 16, y: y + 4, class: 'expect-label' }, svg);
      label.textContent = compact ? `exp ${expected}` : `expected ${expected}`;
    }

    columns.forEach((col, i) => {
      const x0 = padL + gap / 2 + i * span;
      const cx = x0 + (colW + depth) / 2;
      const tone = col.tone === 'ok' ? 'ok' : col.tone === 'bad' ? 'bad' : col.tone === 'info' ? 'info' : null;
      const jobs = Number.isInteger(col.jobs) ? col.jobs : null;
      if (jobs !== null && tone) {
        for (let k = 0; k < jobs; k += 1) {
          const slabH = u - 8;
          const y = base - (k + 1) * u + 4;
          const g = svgEl('g', { class: 'slab' }, svg);
          g.style.setProperty('--i', String(k));
          svgEl('rect', { x: x0, y, width: colW, height: slabH, rx: 2, class: `face-front-${tone}` }, g);
          svgEl('polygon', { points: `${x0 + colW},${y} ${x0 + colW + depth},${y - depth} ${x0 + colW + depth},${y - depth + slabH} ${x0 + colW},${y + slabH}`, class: `face-side-${tone}` }, g);
          svgEl('polygon', { points: `${x0},${y} ${x0 + depth},${y - depth} ${x0 + colW + depth},${y - depth} ${x0 + colW},${y}`, class: `face-top-${tone}` }, g);
        }
      } else {
        const g = svgEl('g', { class: 'slab' }, svg);
        const slabH = u - 8;
        svgEl('rect', { x: x0, y: base - u + 4, width: colW, height: slabH, rx: 2, class: 'missing', fill: `url(#hatch-${svg.id})` }, g);
      }
      const value = svgEl('text', { x: cx, y: base + (compact ? 26 : 34), 'text-anchor': 'middle', class: 'col-value' }, svg);
      if (compact) value.setAttribute('font-size', '15');
      value.textContent = jobs === null ? '—' : String(jobs);
      const label = svgEl('text', { x: cx, y: base + (compact ? 42 : 56), 'text-anchor': 'middle', class: 'col-label' }, svg);
      if (compact) label.setAttribute('font-size', '11');
      label.textContent = col.label;
      if (!compact) {
        const note = svgEl('text', { x: cx, y: base + 74, 'text-anchor': 'middle', class: 'col-note' }, svg);
        note.textContent = col.note || '';
      }
    });
  }

  const observationJobs = (obs) => (obs && obs.status !== 'ERROR' && Number.isInteger(obs.unique_jobs) ? obs.unique_jobs : null);
  const toneOf = (obs) => (!obs || obs.status === 'ERROR' ? 'missing' : obs.status === 'PASS' ? 'ok' : 'bad');
  const noteOf = (obs) => (!obs ? 'no observation' : obs.status === 'ERROR' ? 'not observed' : `check ${obs.status.toLowerCase()}`);
  const expectedJobs = (check) => {
    const found = (check?.assertions || []).find((a) => a.metric === 'unique_jobs');
    return found && Number.isInteger(found.equals) ? found.equals : null;
  };

  // ---- glyphs: state is never colour alone ------------------------------------------------------
  function setVerdictIcon(el, glyph) {
    el.replaceChildren();
    const svg = svgEl('svg', { viewBox: '0 0 24 24' }, el);
    const paths = {
      check: 'M5 12.5l4.5 4.5L19 7.5',
      cross: 'M6 6l12 12M18 6L6 18',
      question: 'M9 9.2a3 3 0 1 1 4.3 2.7c-.9.5-1.3 1-1.3 2M12 17.5v.01',
      clock: 'M12 6.5V12l3.5 2M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z',
      dash: 'M7 12h10'
    };
    svgEl('path', { d: paths[glyph] || paths.dash }, svg);
  }

  // ---- decision / approval views ----------------------------------------------------------------
  function renderDecisions(data) {
    const oldDecision = data.old_decision || {};
    const newDecision = data.new_decision || {};
    safeText(byId('old-decision-title'), `${oldDecision.id || 'Previous decision'} · ${oldDecision.status || 'historical'}`);
    safeText(byId('old-decision-rule'), oldDecision.rule);
    safeText(byId('old-decision-exceptions'), oldDecision.exceptions?.length ? `Exception: ${oldDecision.exceptions.join(' ')}` : 'No exception recorded.');
    safeText(byId('new-decision-title'), `${newDecision.id || 'Active decision'} · ${newDecision.status || 'active'}`);
    safeText(byId('new-decision-rule'), newDecision.rule);
    safeText(byId('new-decision-exceptions'), newDecision.exceptions?.length ? `Permitted exception: ${newDecision.exceptions.join(' ')}` : 'No exception recorded.');
    byId('decision-evidence').textContent = objectText({ old_decision: oldDecision, new_decision: newDecision, source_sha: data.draft?.source_sha });
    safeText(byId('decision-mode'), data.lifecycle ? formatLabel(data.lifecycle) : 'Synthetic records');
  }

  function proposalLabel(draft, mode) {
    const m = draft?.proposal_mode || mode;
    return m === 'live' ? 'Live proposal' : m === 'recorded' ? 'Recorded proposal' : m === 'manual' ? 'Manual sample' : 'Proposal source unknown';
  }

  function renderCalibration(data, check) {
    const field = byId('cal-field');
    const cases = data.validation?.cases;
    const names = [['bad', 'Known-bad'], ['good', 'Corrected'], ['exception', 'Exception']];
    const result = (key) => {
      const obs = cases?.[key]?.observation;
      return obs?.status ? `${obs.status}${obs.unique_jobs == null ? '' : ` · ${plural(obs.unique_jobs, 'job')}`}` : 'Not run';
    };
    safeText(byId('cal-bad'), result('bad'));
    safeText(byId('cal-good'), result('good'));
    safeText(byId('cal-exception'), result('exception'));
    if (!cases) { visible(field, false); return; }
    visible(field, true);
    const columns = names.map(([key, label]) => {
      const obs = cases[key]?.observation;
      return { label, jobs: observationJobs(obs), tone: toneOf(obs) };
    });
    drawField(field, columns, { unit: 52, expected: expectedJobs(check), compact: true });
    field.setAttribute('aria-label', 'Calibration observations: ' + columns.map((c) => `${c.label} ${c.jobs === null ? 'not observed' : plural(c.jobs, 'job')}`).join(', '));
  }

  function renderDraft(data) {
    const draft = data.draft;
    const check = draft?.check || null;
    const validation = data.validation;
    const approval = data.approval;
    const selectedMode = draft?.proposal_mode || data.mode;
    if (selectedMode === 'live' || selectedMode === 'recorded') byId('proposal-mode').value = selectedMode;
    safeText(byId('review-check-id'), draft?.check?.id || approval?.check_id, 'No approved check');
    safeText(byId('proposal-mode-stamp'), proposalLabel(draft, data.mode));
    safeText(byId('approval-identity'), approval?.reviewer ? `Approved by ${approval.reviewer} (typed label)` : 'Reviewer not recorded');
    if (!draft) {
      setBadge(byId('proposal-source-label'), 'No proposal loaded', 'muted');
      safeText(byId('proposal-provenance'), 'Choose a proposal source to begin.');
      safeText(byId('check-id'), 'Not recorded');
      safeText(byId('check-rationale'), 'Draft a proposal to inspect its scenario, assertions and decision citation.');
      safeText(byId('check-citation'), 'No citation loaded.');
      byId('assertions').replaceChildren();
      byId('draft-evidence').textContent = 'No proposal is loaded.';
    } else {
      const mode = draft.proposal_mode || data.mode || 'manual';
      setBadge(byId('proposal-source-label'), proposalLabel(draft, data.mode), mode === 'live' ? 'info' : mode === 'recorded' ? 'warn' : 'muted');
      const provider = draft.request_metadata?.provider;
      safeText(byId('proposal-provenance'), [provider, draft.model, draft.captured_at, draft.sdk_version ? `client ${draft.sdk_version}` : null].filter(Boolean).join(' · '), 'Provider provenance unavailable');
      safeText(byId('check-id'), check?.id);
      safeText(byId('check-rationale'), check?.rationale, 'No rationale recorded.');
      const assertions = byId('assertions');
      assertions.replaceChildren();
      (Array.isArray(check?.assertions) ? check.assertions : []).forEach((assertion) => {
        const row = node('div', 'assertion-row');
        row.append(node('span', 'assertion-metric', assertion.metric || 'Unknown metric'));
        row.append(node('code', 'assertion-value', `${assertion.equals === true ? 'true' : assertion.equals === false ? 'false' : assertion.equals ?? 'Not set'}`));
        assertions.append(row);
      });
      const citations = Array.isArray(check?.citations) ? check.citations : [];
      safeText(byId('check-citation'), citations.length ? citations.map((c) => `“${c.quote}” · ${c.decision_id}`).join('  /  ') : 'No exact decision citation.');
      byId('draft-evidence').textContent = objectText(draft);
    }
    renderCalibration(data, check);
    const isEligible = validation?.eligible === true;
    setBadge(byId('validation-status'), validation ? (isEligible ? 'Eligible' : 'Needs work') : 'Not run', validation ? (isEligible ? 'good' : 'bad') : 'muted');
    safeText(byId('calibration-explanation'), validation ? (isEligible ? 'All required behaviors matched the calibration contract.' : 'At least one required behavior did not match. Approval is unavailable.') : 'Validation executes the proposal against all three fixtures.');
    byId('validation-evidence').textContent = objectText(validation);
    const approved = Boolean(approval);
    safeText(byId('lifecycle-label'), approved ? `Approved by ${approval.reviewer || 'reviewer'}` : validation ? (isEligible ? 'Awaiting developer approval' : 'Calibration needs work') : draft ? 'Draft ready for validation' : 'No approved check');
    byId('approval-form').classList.toggle('is-approved', approved);
    byId('reviewer').disabled = approved;
    byId('reason').disabled = approved;
    byId('approve-button').textContent = approved ? 'Check approved' : 'Approve exact check';
    syncControls();

    const navState = (id, text, tone) => { const el = byId(id); safeText(el, text); el.closest('.nav-item').dataset.state = tone; };
    navState('decision-nav-state', data.new_decision?.id ? 'Changed' : 'Ready', data.new_decision?.id ? 'done' : 'pending');
    navState('approval-nav-state', approved ? 'Approved' : validation ? (isEligible ? 'Validated' : 'Needs work') : draft ? 'Draft' : 'Pending',
      approved ? 'done' : validation ? (isEligible ? 'attention' : 'failed') : 'pending');
  }

  function renderScenarioSelect(data) {
    const select = byId('scenario-select');
    const prior = select.value;
    select.replaceChildren();
    const scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
    scenarios.forEach((scenario) => select.append(new Option(scenario.label || scenario.id, scenario.id)));
    const reportScenario = scenarioIdForReport(data.report, scenarios);
    if (prior && scenarios.some((s) => s.id === prior)) select.value = prior;
    else if (reportScenario) select.value = reportScenario;
    syncControls();
  }

  function scenarioIdForReport(report, scenarios) {
    const aliases = {
      'unseen-regression': 'unseen_regression', 'approved-abort': 'abort', 'approved-crashing': 'crashing',
      'approved-timing-out': 'timing_out', 'approved-missing-entrypoint': 'missing_entrypoint',
      'policy-edit': 'policy_edit', 'preexisting-head': 'preexisting_failure'
    };
    const head = report?.head_ref;
    if (typeof head !== 'string') return null;
    const id = aliases[head] || head;
    return scenarios.some((item) => item.id === id) ? id : null;
  }

  function eventLabel(event) {
    const name = event?.event || 'event';
    if (name === 'accepted') return `Job ${event.job_id || 'unknown'} accepted`;
    if (name === 'response') return `Service returned ${event.status ?? 'unknown'}`;
    if (name === 'submit') return `Submission ${event.call ?? ''} sent`.trim();
    if (name === 'lookup') return event.job_id ? `Reconciled to job ${event.job_id}` : 'Lookup found no job';
    if (name === 'deduplicated') return `Stable key reused job ${event.job_id || 'unknown'}`;
    return `${formatLabel(name)}${event.job_id ? ` · ${event.job_id}` : ''}`;
  }

  // ---- the gate ---------------------------------------------------------------------------------
  const VERDICT_SUMMARY = {
    VIOLATION_INTRODUCED: 'The candidate newly violates this approved behavior.',
    PRE_EXISTING_FAILURE: 'This failure already exists in the target revision.',
    RESOLVED: 'The candidate resolves a failure present in the target.',
    CHECK_PASSED: 'The approved check passed on both revisions.',
    NOT_CHECKED: 'Execution did not establish a result for both revisions.'
  };

  function gateModel(report, stale, check) {
    if (!report) return { tone: 'info', label: 'NOT RUN', glyph: 'dash', exit: 'exit code —', summary: 'No current report.' };
    if (stale) return { tone: 'warn', label: 'STALE', glyph: 'clock', exit: 'exit code —, rerun required', summary: 'This report is bound to earlier revisions. Rerun required.' };
    const codes = new Set((Array.isArray(report.warnings) ? report.warnings : []).map((w) => w?.code));
    if (report.aggregate === 'PASSED_CHECKS') {
      return { tone: 'good', label: 'PASSED', glyph: 'check', exit: 'exit code 0', summary: VERDICT_SUMMARY[check?.verdict] || 'The approved checks held on both revisions.' };
    }
    if (report.aggregate === 'FAILED') {
      return { tone: 'bad', label: 'FAILED', glyph: 'cross', exit: 'exit code 1', summary: VERDICT_SUMMARY[check?.verdict] || 'An approved check failed.' };
    }
    const summary = codes.has('POLICY_REVIEW_REQUIRED') ? 'The candidate changes approved policy; review is required before this result can be green.'
      : codes.has('MISSING_APPROVED_COVERAGE') || codes.has('NO_ACTIVE_APPROVED_CHECKS') ? 'Required active decision coverage is missing from the approved target.'
        : codes.has('APPROVER_NOT_VERIFIED') ? 'The approver of this check could not be verified, so the check did not run.'
          : codes.has('EXECUTION_ERROR') || codes.has('AUTHORITY_UNAVAILABLE') ? 'Execution or authority evidence is incomplete; inspect the report details.'
            : 'Required evidence is incomplete; inspect the report details.';
    return { tone: 'warn', label: 'INCOMPLETE', glyph: 'question', exit: 'exit code 2, not proven', summary };
  }

  function lines(el, parts) {
    el.replaceChildren();
    parts.forEach((part, index) => {
      if (index) el.append(document.createElement('br'));
      if (typeof part === 'string') { el.append(document.createTextNode(part)); return; }
      part.forEach((piece) => {
        if (typeof piece === 'string') el.append(document.createTextNode(piece));
        else el.append(node(piece.tag || 'span', piece.cls || '', piece.text));
      });
    });
  }

  function renderSteps(report, check, gate, expected, baseJobs, headJobs) {
    const set = (id, tone) => { const li = byId(id).closest('.step'); li.classList.remove('is-good', 'is-bad', 'is-warn'); if (tone) li.classList.add(`is-${tone}`); };
    const detect = byId('step-detect');
    if (!report) {
      safeText(detect, 'No observation yet.');
    } else if (baseJobs !== null && headJobs !== null) {
      const parts = [`Target created ${plural(baseJobs, 'job')} for 1 operation; candidate created ${plural(headJobs, 'job')}.`];
      if (expected !== null) parts.push(`The approved check expects ${plural(expected, 'job')}.`);
      safeText(detect, parts.join(' '));
    } else {
      safeText(detect, `Observation unavailable: ${check?.head?.error || check?.base?.error || 'the engine did not establish both observations'}.`);
    }
    set('step-detect', report && check?.verdict === 'VIOLATION_INTRODUCED' ? 'bad' : report && (baseJobs === null || headJobs === null) ? 'warn' : report ? 'good' : null);

    const decision = check?.decision || report?.active_decisions?.[0];
    const explain = byId('step-explain');
    if (decision?.id) {
      lines(explain, [[{ cls: 'mono', text: decision.id }, decision.supersedes ? ` supersedes ${decision.supersedes}.` : '.'], decision.rule || 'No rule text recorded.']);
    } else {
      safeText(explain, report ? 'Governing rule not present in the report.' : 'No governing decision loaded.');
    }

    const enforce = byId('step-enforce');
    if (report) {
      const codes = [...new Set((Array.isArray(report.warnings) ? report.warnings : []).map((w) => w?.code).filter(Boolean))];
      lines(enforce, [[{ tag: 'b', text: gate.label }, check?.verdict ? ` · ${check.verdict}` : ''], gate.exit + '. ddg run reports this result; it did not block anything.', codes.length ? [{ cls: 'mono', text: codes.join(', ') }] : 'No warnings.']);
    } else {
      safeText(enforce, 'Nothing was evaluated.');
    }
    set('step-enforce', report ? gate.tone : null);

    const audit = byId('step-audit');
    if (report) {
      const approver = check?.approver;
      const first = approver?.commits?.[0];
      const sig = { G: 'good signature', N: 'unsigned', B: 'bad signature', U: 'untrusted signature', E: 'signature unchecked', X: 'expired signature', Y: 'expired key', R: 'revoked key' }[first?.signature] || `signature ${first?.signature}`;
      const who = approver?.verified ? [{ tag: 'b', text: 'Verified' }, ` approver ${first?.author_email || ''}${first ? ` (${sig})` : ''}`]
        : [{ tag: 'b', text: 'Unverified' }, ` approver${approver?.reason ? `: ${approver.reason}` : ''}`];
      lines(audit, [
        who,
        [{ cls: 'mono', text: `${short(report.base_sha)} → ${short(report.head_sha)}` }],
        [`Isolation ${report.sandbox || 'not recorded'}`, check?.check_digest ? ` · check ${short(check.check_digest)}` : ''],
        report.run_at ? `Run ${report.run_at}` : 'Run time not recorded'
      ]);
      set('step-audit', approver?.verified === true && report.sandbox && report.sandbox !== 'host' ? 'good' : 'warn');
    } else {
      safeText(audit, 'No record yet.');
      set('step-audit', null);
    }
  }

  function renderBar(data, report, check) {
    const approval = data.approval;
    safeText(byId('sb-check'), approval?.check_id || data.draft?.check?.id, 'none approved');
    const src = data.draft ? `${proposalLabel(data.draft, data.mode).replace(' proposal', '')}${data.draft.model ? ` · ${data.draft.model}` : ''}` : 'none';
    safeText(byId('sb-source'), src);
    const approver = check?.approver;
    const sbApprover = byId('sb-approver');
    if (report && approver) {
      safeText(sbApprover, approver.verified ? `verified · ${approver.commits?.[0]?.author_email || 'git author'}` : 'UNVERIFIED');
      setTone(sbApprover, approver.verified ? 'good' : 'warn');
    } else {
      safeText(sbApprover, approval?.reviewer ? `${approval.reviewer} (typed label)` : 'not recorded');
      setTone(sbApprover, null);
    }
    const sbIso = byId('sb-isolation');
    const iso = report?.sandbox;
    safeText(sbIso, !iso ? 'no run yet' : iso === 'host' ? 'host · UNSAFE' : iso === 'unavailable' ? 'unavailable' : iso);
    setTone(sbIso, !iso ? null : iso === 'host' ? 'bad' : iso === 'unavailable' ? 'warn' : 'good');
  }

  function renderReport(data) {
    const report = data.report;
    const stale = data.report_stale === true;
    const scenario = scenarioIdForReport(report, Array.isArray(data.scenarios) ? data.scenarios : []);
    const scenarioLabel = data.scenarios?.find((item) => item.id === scenario)?.label;
    const checks = Array.isArray(report?.checks) ? report.checks : [];
    const check = checks.find((entry) => entry.verdict !== 'HISTORICAL_CHECK_IGNORED') || checks[0] || null;

    const freshness = byId('report-freshness');
    safeText(freshness, report ? (stale ? 'STALE · rerun required' : `Current · ${report.aggregate || 'complete'}`) : 'Not run');
    setTone(freshness, !report ? null : stale ? 'warn' : report.aggregate === 'PASSED_CHECKS' ? 'good' : report.aggregate === 'FAILED' ? 'bad' : 'warn');
    safeText(byId('report-case'), scenarioLabel ? `Report for ${scenarioLabel}` : 'No report candidate');
    visible(byId('stale-notice'), Boolean(report && stale));
    visible(byId('empty-review'), !report);
    visible(byId('review-content'), Boolean(report));
    renderBar(data, report, check);

    const navItem = byId('review-nav-state').closest('.nav-item');
    if (!report) {
      safeText(byId('review-nav-state'), 'Not run');
      navItem.dataset.state = 'pending';
      return;
    }
    const gate = gateModel(report, stale, check);
    safeText(byId('review-nav-state'), stale ? 'Rerun required' : report.aggregate);
    navItem.dataset.state = stale ? 'attention' : gate.tone === 'good' ? 'done' : gate.tone === 'bad' ? 'failed' : 'attention';

    safeText(byId('verdict'), gate.label);
    byId('verdict').className = `verdict-text verdict-${gate.tone}`;
    byId('verdict-icon').className = `verdict-icon verdict-${gate.tone}`;
    setVerdictIcon(byId('verdict-icon'), gate.glyph);
    safeText(byId('verdict-summary'), gate.summary);
    safeText(byId('exit-line'), gate.exit);

    const head = check?.head || {};
    const base = check?.base || {};
    const baseJobs = observationJobs(base);
    const headJobs = observationJobs(head);
    const expected = expectedJobs(check?.check);
    const events = Array.isArray(head.events) ? head.events : [];
    const operationIds = new Set(events.map((e) => e?.operation_id).filter((id) => typeof id === 'string' && id));
    safeText(byId('operation-count'), operationIds.size ? operationIds.size : events.length ? 1 : '—');
    safeText(byId('job-count'), headJobs === null ? '—' : headJobs);
    safeText(byId('job-count-label'), head.status === 'ERROR' ? head.error || 'Candidate observation unavailable' : 'Observed created jobs');

    const field = byId('state-field');
    if (check) {
      drawField(field, [
        { label: 'Target', jobs: baseJobs, tone: toneOf(base), note: noteOf(base) },
        { label: 'Candidate', jobs: headJobs, tone: toneOf(head), note: noteOf(head) }
      ], { unit: 78, expected });
      field.setAttribute('aria-label', `Jobs created for one operation. Target: ${baseJobs === null ? 'not observed' : plural(baseJobs, 'job')}. Candidate: ${headJobs === null ? 'not observed' : plural(headJobs, 'job')}.${expected === null ? '' : ` The check expects ${plural(expected, 'job')}.`}`);
      safeText(byId('field-caption'), `${short(report.base_sha)} → ${short(report.head_sha)}`);
    } else {
      field.replaceChildren();
      field.setAttribute('aria-label', 'No approved check produced an observation.');
      safeText(byId('field-caption'), '');
    }
    renderSteps(report, check, gate, expected, baseJobs, headJobs);

    const ordinary = report.ordinary_tests || {};
    const ob = ordinary.base || {};
    const oh = ordinary.head || {};
    const fmt = (o) => (o.status ? `${o.status}${o.unique_jobs == null ? '' : ` · ${plural(o.unique_jobs, 'job')}`}` : 'Not run');
    safeText(byId('ordinary-base'), fmt(ob));
    safeText(byId('ordinary-head'), fmt(oh));
    const ordinaryPass = ob.status === 'PASS' && oh.status === 'PASS';
    const ordinaryErr = ob.status === 'ERROR' || oh.status === 'ERROR';
    setBadge(byId('ordinary-status'), ordinaryPass ? 'Both passed' : ordinaryErr ? `${ob.status === 'ERROR' ? 'Target' : 'Candidate'} errored` : (ob.status || oh.status ? 'Failed' : 'Not run'), ordinaryPass ? 'good' : ordinaryErr || ob.status === 'FAIL' || oh.status === 'FAIL' ? 'bad' : 'muted');
    const decision = check?.decision || report.active_decisions?.find((item) => item.id === check?.decision_id) || report.active_decisions?.[0] || {};
    setBadge(byId('governing-id'), decision.id || check?.decision_id, decision.id ? 'good' : 'muted');
    safeText(byId('governing-rule'), decision.rule || 'Governing rule not present in report.');

    const timeline = byId('timeline');
    timeline.replaceChildren();
    if (!events.length) {
      timeline.append(node('li', 'timeline-empty', head.error ? `No event trace: ${head.error}` : 'No events were recorded.'));
    } else {
      events.forEach((event, index) => {
        const item = node('li', 'timeline-item');
        item.dataset.kind = String(event?.event || 'event');
        const marker = node('span', 'timeline-marker');
        marker.append(node('span', '', String(index + 1)));
        item.append(marker);
        const detail = node('div', 'timeline-detail');
        detail.append(node('strong', '', eventLabel(event)));
        const meta = [event.operation_id, event.call ? `call ${event.call}` : null].filter(Boolean).join(' · ');
        if (meta) detail.append(node('span', 'timeline-meta', meta));
        item.append(detail);
        timeline.append(item);
      });
    }
    safeText(byId('timeline-summary'), `${plural(events.length, 'event')} observed on the candidate`);
    byId('report-evidence').textContent = objectText(report);
  }

  function render() {
    const data = state.value;
    if (!data) return;
    renderDecisions(data);
    renderDraft(data);
    renderScenarioSelect(data);
    renderReport(data);
    showView(state.view);
  }

  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
  document.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', (event) => { event.preventDefault(); showView(button.dataset.go); }));
  window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (VIEWS.includes(v)) showView(v); });
  byId('propose-button').addEventListener('click', () => act('propose', { mode: byId('proposal-mode').value }));
  byId('validate-button').addEventListener('click', () => {
    const draft = state.value?.draft;
    if (draft?.draft_digest) act('validate', { draft_digest: draft.draft_digest });
  });
  byId('approval-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const draft = state.value?.draft;
    if (!draft?.draft_digest || byId('approve-button').disabled) return;
    act('approve', { draft_digest: draft.draft_digest, reviewer: byId('reviewer').value.trim(), reason: byId('reason').value.trim() });
  });
  byId('run-button').addEventListener('click', () => {
    const scenario = byId('scenario-select').value;
    if (scenario) act('run', { scenario });
  });

  refresh().catch((error) => {
    byId('connection-label').textContent = 'Local demo unavailable';
    setNotice(error instanceof Error ? error.message : 'Could not connect to the local demo.');
  });
})();
