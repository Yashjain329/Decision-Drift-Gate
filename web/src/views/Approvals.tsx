'use client';
// Port of legacy/index.html "APPROVALS" + renderApprovals() and the approval-form submit handler in legacy/app.js.
// An approval is only "Verified" once a run's report shows approver.verified === true; recording it never is.
import { useState, type FormEvent } from 'react';
import { View } from '@/components/Shell';
import { Icon } from '@/components/Icon';
import { PageHead, Tag } from '@/components/ui';
import { clock, fixturesMatched, orText, realChecks, short, SIGNATURE, type Glyph, type Tone } from '@/lib/model';
import { useDdg } from '@/lib/store';

type StepClass = 'is-done' | 'is-current' | 'is-failed' | '';

function FlowStep({ n, cls, title, text }: { n: number; cls: StepClass; title: string; text: string }) {
  return (
    <li className={`flow-step ${cls}`} id={`flow-${n}`}>
      <span className="flow-no">{String(n).padStart(2, '0')}</span>
      <div><h3>{title}</h3><p id={`flow-${n}-text`}>{text}</p></div>
    </li>
  );
}

/** Legacy safeText() fallback: missing values read "Not recorded". */
const rec = (value: unknown, fallback = 'Not recorded') => orText(value, fallback);

export default function Approvals() {
  const { state, busy, act } = useDdg();
  const s = state ?? {};
  const [reviewer, setReviewer] = useState('');
  const [reason, setReason] = useState('');

  const draft = s.draft;
  const v = s.validation;
  const ap = s.approval;
  const who = s.report ? realChecks(s.report)[0]?.approver : undefined;
  const commit = who?.commits?.[0];
  const matched = fixturesMatched(s);
  const canApprove = !busy && v?.eligible === true && !ap && Boolean(draft?.draft_digest);

  const [stateWord, stateTone, stateGlyph]: [string, Tone, Glyph | null] = who?.verified ? ['Verified', 'pass', 'check']
    : who ? ['Unverifiable', 'fail', 'x']
      : ap ? ['Recorded · awaiting verification', 'pre', 'clock']
        : v?.eligible ? ['Pending', 'muted', null] : ['Not eligible yet', 'muted', null];
  const [gitWord, gitTone, gitGlyph]: [string, Tone, Glyph | null] = who?.verified ? ['Verified', 'pass', 'check'] : who ? ['Unverifiable', 'fail', 'x'] : ['Not yet verified', 'muted', null];
  const h = ap?.calibration_hashes;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const digest = draft?.draft_digest;
    if (!digest || !canApprove) return;
    void act('approve', { draft_digest: digest, reviewer: reviewer.trim(), reason: reason.trim() });
  };

  return (
    <View id="approvals" labelledBy="approvals-title">
      <PageHead id="approvals-title" crumb="Approvals" title="Who authorized this exact check?"
        lede="The gate trusts the Git author of the approval commit, not a typed name."
        aside={<span id="approval-state"><Tag tone={stateTone} glyph={stateGlyph}>{stateWord}</Tag></span>} />

      <ol className="flow" aria-label="Approval flow">
        <FlowStep n={1} title="Review exact check" cls={draft ? 'is-done' : 'is-current'}
          text={draft ? `${orText(draft.check?.id, 'check')} · draft ${short(draft.draft_digest, 8)}` : 'Draft a proposal first.'} />
        <FlowStep n={2} title="Verify eligibility" cls={v ? (v.eligible ? 'is-done' : 'is-failed') : draft ? 'is-current' : ''}
          text={v ? (v.eligible ? `${matched} of 3 fixtures matched` : `${matched} of 3 matched · blocked`) : 'Not calibrated.'} />
        <FlowStep n={3} title="Authorize" cls={ap ? 'is-done' : v?.eligible ? 'is-current' : ''}
          text={ap ? `Recorded ${clock(ap.approved_at)} UTC` : v?.eligible ? 'Approve below.' : 'Waiting.'} />
        <FlowStep n={4} title="Confirm provenance" cls={who?.verified ? 'is-done' : who ? 'is-failed' : ap ? 'is-current' : ''}
          text={who?.verified ? `Verified · ${orText(commit?.author_email, 'unknown author')}` : who ? `Unverifiable${who.reason ? `: ${who.reason}` : ''}` : ap ? 'Verified at next run.' : 'Waiting.'} />
      </ol>

      <div className="grid">
        {!ap ? (
          <form id="approval-form" className="panel span-6" onSubmit={submit}>
            <div className="panel-head"><h2>Approve exact check</h2><code id="approve-target" className="muted">{draft?.check?.id ? `${draft.check.id} · ${short(draft.draft_digest, 8)}` : '—'}</code></div>
            <label className="field-label" htmlFor="reviewer">Review label</label>
            <input id="reviewer" name="reviewer" autoComplete="name" required maxLength={160} placeholder="Your name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
            <label className="field-label" htmlFor="reason">Review note</label>
            <textarea id="reason" name="reason" rows={3} required maxLength={2000} placeholder="What did you check?" value={reason} onChange={(e) => setReason(e.target.value)} />
            <button className="button button-primary full" id="approve-button" type="submit" disabled={!canApprove} aria-busy={busy}><Icon name="approvals" />Approve exact check</button>
            <details className="inline-details"><summary>How this is trusted</summary><p className="body-copy">In this demo the server commits the approval as the demo identity. In a real repository it lands as a signed commit by an allowlisted approver (<code>ddg approve</code>, then <code>git commit -S</code>).</p></details>
          </form>
        ) : (
          <section id="approval-record" className="panel span-6" aria-labelledby="record-title">
            <div className="panel-head"><h2 id="record-title">Approval record</h2><Tag tone="pre" glyph="commit">Recorded</Tag></div>
            <dl className="kv kv-stack">
              <div><dt>Check</dt><dd id="rec-check" className="mono">{rec(ap.check_id)}</dd></div>
              <div><dt>Review label</dt><dd id="rec-label">{rec(ap.reviewer)}</dd></div>
              <div><dt>Review note</dt><dd id="rec-note">{rec(ap.reason)}</dd></div>
              <div><dt>Approved at</dt><dd id="rec-time" className="mono">{rec(ap.approved_at)}</dd></div>
            </dl>
            <details className="inline-details"><summary>Digests</summary>
              <dl className="kv kv-stack">
                <div><dt>Bundle</dt><dd id="rec-digest" className="mono hash">{rec(ap.bundle_digest)}</dd></div>
                <div><dt>Validation</dt><dd id="rec-vdigest" className="mono hash">{rec(ap.validation_digest)}</dd></div>
              </dl>
            </details>
          </section>
        )}

        <section className="panel span-6" aria-labelledby="git-title">
          <div className="panel-head"><h2 id="git-title">Git provenance</h2><span id="git-state"><Tag tone={gitTone} glyph={gitGlyph}>{gitWord}</Tag></span></div>
          <dl className="kv kv-stack">
            <div><dt>Verified Git author</dt><dd id="rec-author">{who ? `${commit?.author_email || 'unknown'}${who.verified ? ' · on allowlist' : ''}` : 'verified at next run'}</dd></div>
            <div><dt>Signature</dt><dd id="rec-signature">{commit ? `${orText(SIGNATURE[commit.signature ?? ''] ?? commit.signature)}${commit.signer ? ` · ${commit.signer}` : ''}` : '—'}</dd></div>
            <div><dt>Signed commits required</dt><dd id="rec-require">{who ? (who.require_signed ? 'yes' : 'no (allowlist only)') : '—'}</dd></div>
          </dl>
          <details className="inline-details"><summary>Commit and fixtures</summary>
            <dl className="kv kv-stack">
              <div><dt>Approval commit</dt><dd id="rec-commit" className="mono hash">{orText(commit?.commit, '—')}</dd></div>
              <div><dt>Calibration fixtures</dt><dd id="rec-hashes" className="mono hash">{h ? `bad ${short(h.bad, 7)} · good ${short(h.good, 7)} · exception ${short(h.exception, 7)}` : '—'}</dd></div>
            </dl>
          </details>
        </section>
      </div>
    </View>
  );
}
