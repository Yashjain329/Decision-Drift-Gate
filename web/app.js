(() => {
  const tokenMeta = document.querySelector('meta[name="ddg-session-token"]');
  const sessionToken = tokenMeta ? tokenMeta.content : '';
  const byId = (id) => document.getElementById(id);
  const state = { value: null, view: 'decision', busy: false };
  const safeText = (node, value, fallback = 'Not recorded') => {
    node.textContent = value === undefined || value === null || value === '' ? fallback : String(value);
  };
  const objectText = (value) => value === undefined || value === null ? 'Not recorded' : JSON.stringify(value, null, 2);
  const node = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const visible = (el, show) => { el.hidden = !show; };
  const formatLabel = (value) => String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

  function setNotice(message, kind = 'error') {
    const notice = byId('notice');
    safeText(notice, message, '');
    notice.className = `notice notice-${kind}`;
    visible(notice, Boolean(message));
  }

  function setBusy(busy) {
    state.busy = busy;
    document.body.classList.toggle('is-busy', busy);
    const buttons = document.querySelectorAll('button');
    buttons.forEach((button) => {
      if (button.dataset.keepEnabled === 'true') return;
      button.setAttribute('aria-busy', busy ? 'true' : 'false');
    });
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
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-DDG-Session': sessionToken },
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
      try { await refresh(); } catch { /* Keep the action error visible when a reload also fails. */ }
    } finally {
      setBusy(false);
    }
  }

  function showView(view) {
    state.view = view;
    document.querySelectorAll('.view').forEach((panel) => visible(panel, panel.id === `view-${view}`));
    document.querySelectorAll('.nav-item').forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  }

  function setBadge(el, text, tone = 'muted') {
    safeText(el, text);
    el.className = `status-badge status-${tone}`;
  }

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

  function renderDraft(data) {
    const draft = data.draft;
    const check = draft?.check || null;
    const validation = data.validation;
    const approval = data.approval;
    const selectedMode = draft?.proposal_mode || data.mode;
    if (selectedMode === 'live' || selectedMode === 'recorded') byId('proposal-mode').value = selectedMode;
    safeText(byId('review-check-id'), draft?.check?.id || data.approval?.check_id, 'No approved check');
    const visibleMode = draft?.proposal_mode || data.mode;
    safeText(byId('proposal-mode-stamp'), visibleMode === 'live' ? 'Live proposal' : visibleMode === 'recorded' ? 'Recorded proposal' : visibleMode === 'manual' ? 'Manual sample' : 'Proposal source unknown');
    safeText(byId('approval-identity'), data.approval?.reviewer ? `Approved by ${data.approval.reviewer}` : 'Reviewer not recorded');
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
      const sourceName = mode === 'live' ? 'Live proposal' : mode === 'recorded' ? 'Recorded proposal' : 'Manual sample';
      setBadge(byId('proposal-source-label'), sourceName, mode === 'live' ? 'info' : mode === 'recorded' ? 'warn' : 'muted');
      safeText(byId('proposal-provenance'), [draft.model, draft.captured_at, draft.sdk_version ? `SDK ${draft.sdk_version}` : null].filter(Boolean).join(' · '), 'Provider provenance unavailable');
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
      safeText(byId('check-citation'), citations.length
        ? citations.map((citation) => `“${citation.quote}” · ${citation.decision_id}`).join('  /  ')
        : 'No exact decision citation.');
      byId('draft-evidence').textContent = objectText(draft);
    }
    const cases = validation?.cases || {};
    const result = (key) => {
      const observation = cases[key]?.observation;
      return observation?.status ? `${observation.status}${observation.unique_jobs == null ? '' : ` · ${observation.unique_jobs} job${observation.unique_jobs === 1 ? '' : 's'}`}` : 'Not run';
    };
    safeText(byId('cal-bad'), result('bad'));
    safeText(byId('cal-good'), result('good'));
    safeText(byId('cal-exception'), result('exception'));
    const isEligible = validation?.eligible === true;
    setBadge(byId('validation-status'), validation ? (isEligible ? 'Eligible' : 'Needs work') : 'Not run', validation ? (isEligible ? 'good' : 'bad') : 'muted');
    safeText(byId('calibration-explanation'), validation ? (isEligible ? 'All required behaviors matched the calibration contract.' : 'At least one required behavior did not match. Approval is unavailable.') : 'Validation executes the proposal against all three fixtures.');
    byId('validation-evidence').textContent = objectText(validation);
    const form = byId('approval-form');
    const approved = Boolean(approval);
    const lifecycle = approved ? `Approved by ${approval.reviewer || 'reviewer'}` : validation ? (isEligible ? 'Awaiting developer approval' : 'Calibration needs work') : draft ? 'Draft ready for validation' : 'No approved check';
    safeText(byId('lifecycle-label'), lifecycle);
    safeText(byId('approval-nav-state'), approved ? 'Approved' : validation ? 'Validated' : draft ? 'Draft' : 'Pending');
    form.classList.toggle('is-approved', approved);
    byId('reviewer').disabled = approved;
    byId('reason').disabled = approved;
    byId('propose-button').disabled = state.busy || approved;
    byId('proposal-mode').disabled = state.busy || approved;
    byId('validate-button').disabled = state.busy || !draft || approved;
    byId('approve-button').disabled = state.busy || !isEligible || approved;
    byId('approve-button').textContent = approved ? 'Check approved' : 'Approve exact check';
    safeText(byId('approval-nav-state'), approved ? 'Approved' : validation ? 'Validated' : draft ? 'Draft' : 'Pending');
    safeText(byId('decision-nav-state'), newDecisionLabel(data));
    safeText(byId('review-nav-state'), data.report ? data.report_stale ? 'Rerun' : data.report.aggregate || 'Complete' : 'Not run');
  }

  function newDecisionLabel(data) {
    return data.new_decision?.id ? 'Changed' : 'Ready';
  }

  function renderScenarioSelect(data) {
    const select = byId('scenario-select');
    const prior = select.value;
    select.replaceChildren();
    const scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
    scenarios.forEach((scenario) => {
      select.append(new Option(scenario.label || scenario.id, scenario.id));
    });
    const reportScenario = scenarioIdForReport(data.report, scenarios);
    if (prior && scenarios.some((scenario) => scenario.id === prior)) select.value = prior;
    else if (reportScenario) select.value = reportScenario;
    select.disabled = state.busy || !data.approval || scenarios.length === 0;
    byId('run-button').disabled = state.busy || !data.approval || scenarios.length === 0;
  }

  function scenarioIdForReport(report, scenarios) {
    const aliases = {
      'unseen-regression': 'unseen_regression',
      'approved-abort': 'abort',
      'approved-crashing': 'crashing',
      'approved-timing-out': 'timing_out',
      'approved-missing-entrypoint': 'missing_entrypoint',
      'policy-edit': 'policy_edit',
      'preexisting-head': 'preexisting_failure'
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

  function toneForVerdict(verdict) {
    if (verdict === 'VIOLATION_INTRODUCED' || verdict === 'PRE_EXISTING_FAILURE') return 'bad';
    if (verdict === 'CHECK_PASSED' || verdict === 'RESOLVED') return 'good';
    return 'warn';
  }

  function renderReport(data) {
    const report = data.report;
    const stale = data.report_stale === true;
    safeText(byId('report-freshness'), report ? (stale ? 'STALE · Rerun required' : `Current · ${report.aggregate || 'complete'}`) : 'Not run');
    const scenario = scenarioIdForReport(report, Array.isArray(data.scenarios) ? data.scenarios : []);
    const scenarioLabel = data.scenarios?.find((item) => item.id === scenario)?.label;
    safeText(byId('report-case'), scenarioLabel ? `Report for ${scenarioLabel}` : 'No report candidate');
    byId('report-freshness').classList.toggle('freshness-stale', Boolean(report && stale));
    visible(byId('stale-notice'), Boolean(report && stale));
    visible(byId('empty-review'), !report);
    visible(byId('review-content'), Boolean(report));
    if (!report) {
      safeText(byId('review-nav-state'), 'Not run');
      return;
    }
    const checks = Array.isArray(report.checks) ? report.checks : [];
    const check = checks.find((entry) => entry.verdict !== 'HISTORICAL_CHECK_IGNORED') || checks[0] || {};
    const head = check.head || {};
    const base = check.base || {};
    const verdict = stale ? 'STALE' : report.aggregate === 'INCOMPLETE' ? 'INCOMPLETE' : check.verdict || report.aggregate || 'NOT_CHECKED';
    safeText(byId('verdict'), verdict);
    byId('verdict').className = `verdict-text verdict-${toneForVerdict(verdict)}`;
    const warningCodes = new Set((Array.isArray(report.warnings) ? report.warnings : []).map((warning) => warning?.code));
    const summary = {
      VIOLATION_INTRODUCED: 'The candidate newly violates this approved behavior.',
      PRE_EXISTING_FAILURE: 'This failure already exists in the target revision.',
      RESOLVED: 'The candidate resolves a failure present in the target.',
      CHECK_PASSED: 'The approved check passed on both revisions.',
      NOT_CHECKED: 'Execution did not establish a result for both revisions.'
    };
    const incompleteSummary = warningCodes.has('POLICY_REVIEW_REQUIRED')
      ? 'The candidate changes approved policy; review is required before this result can be green.'
      : warningCodes.has('MISSING_APPROVED_COVERAGE') || warningCodes.has('NO_ACTIVE_APPROVED_CHECKS')
        ? 'Required active decision coverage is missing from the approved target.'
        : warningCodes.has('EXECUTION_ERROR') || warningCodes.has('AUTHORITY_UNAVAILABLE')
          ? 'Execution or authority evidence is incomplete; inspect the report details.'
          : 'Required evidence is incomplete; inspect the report details.';
    safeText(byId('verdict-summary'), stale ? 'This report is bound to earlier revisions. Rerun required.'
      : report.aggregate === 'INCOMPLETE' ? incompleteSummary
        : summary[check.verdict] || 'The aggregate includes the report findings.');
    const jobs = head.unique_jobs;
    const events = Array.isArray(head.events) ? head.events : [];
    const operationIds = new Set(events.map((event) => event?.operation_id).filter((id) => typeof id === 'string' && id));
    safeText(byId('operation-count'), operationIds.size ? operationIds.size : events.length ? 1 : '—');
    safeText(byId('job-count'), jobs === undefined || jobs === null ? '—' : jobs);
    safeText(byId('job-count-label'), head.status === 'ERROR' ? head.error || 'Candidate observation unavailable' : 'Observed created jobs');
    const ordinary = report.ordinary_tests || {};
    const ordinaryBase = ordinary.base || {};
    const ordinaryHead = ordinary.head || {};
    safeText(byId('ordinary-base'), ordinaryBase.status ? `${ordinaryBase.status}${ordinaryBase.unique_jobs == null ? '' : ` · ${ordinaryBase.unique_jobs} job${ordinaryBase.unique_jobs === 1 ? '' : 's'}`}` : 'Not run');
    safeText(byId('ordinary-head'), ordinaryHead.status ? `${ordinaryHead.status}${ordinaryHead.unique_jobs == null ? '' : ` · ${ordinaryHead.unique_jobs} job${ordinaryHead.unique_jobs === 1 ? '' : 's'}`}` : 'Not run');
    const ordinaryPass = ordinaryBase.status === 'PASS' && ordinaryHead.status === 'PASS';
    setBadge(byId('ordinary-status'), ordinaryPass ? 'Both passed' : (ordinaryBase.status || ordinaryHead.status || 'Not run'), ordinaryPass ? 'good' : ordinaryBase.status === 'ERROR' || ordinaryHead.status === 'ERROR' ? 'bad' : 'muted');
    const decision = check.decision || report.active_decisions?.find((item) => item.id === check.decision_id) || report.active_decisions?.[0] || {};
    setBadge(byId('governing-id'), decision.id || check.decision_id, decision.id ? 'good' : 'muted');
    safeText(byId('governing-rule'), decision.rule || (typeof decision === 'string' ? decision : 'Governing rule not present in report.'));
    const timeline = byId('timeline');
    timeline.replaceChildren();
    if (!events.length) {
      timeline.append(node('li', 'timeline-empty', head.error ? `No event trace: ${head.error}` : 'No events were recorded.'));
    } else {
      events.forEach((event, index) => {
        const item = node('li', 'timeline-item');
        item.append(node('span', 'timeline-marker', String(index + 1).padStart(2, '0')));
        const detail = node('div', 'timeline-detail');
        detail.append(node('strong', '', eventLabel(event)));
        const meta = [event.operation_id, event.call ? `call ${event.call}` : null].filter(Boolean).join(' · ');
        if (meta) detail.append(node('span', 'timeline-meta', meta));
        item.append(detail);
        timeline.append(item);
      });
    }
    safeText(byId('timeline-summary'), `${events.length} event${events.length === 1 ? '' : 's'} recorded`);
    byId('report-evidence').textContent = objectText(report);
    safeText(byId('review-nav-state'), stale ? 'Rerun required' : report.aggregate);
  }

  function render() {
    const data = state.value;
    if (!data) return;
    renderDecisions(data);
    renderDraft(data);
    renderScenarioSelect(data);
    renderReport(data);
    const defaultView = data.approval ? 'review' : 'decision';
    showView(state.view || defaultView);
  }

  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
  document.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', (event) => {
    event.preventDefault();
    showView(button.dataset.go);
  }));
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
  document.querySelectorAll('[data-go="approval"]').forEach((button) => button.addEventListener('click', () => { byId('proposal-mode').focus(); }));

  refresh().then(() => {
    const approved = Boolean(state.value?.approval);
    showView(approved ? 'review' : 'decision');
  }).catch((error) => {
    byId('connection-label').textContent = 'Local demo unavailable';
    setNotice(error instanceof Error ? error.message : 'Could not connect to the local demo.');
  });
})();
