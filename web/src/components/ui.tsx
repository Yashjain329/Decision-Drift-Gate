// Shared primitives. Every tone is paired with a glyph and a word; nothing renders colour alone.
import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { outcomeOf, short, type Glyph, type Overall, type Tone } from '@/lib/model';
import type { Check } from '@/lib/types';

export function Tag({ tone = 'muted', glyph, children, title, id }: { tone?: Tone; glyph?: Glyph | null; children: ReactNode; title?: string; id?: string }) {
  return <span className={`tag tag-${tone}`} title={title} id={id}>{glyph ? <Icon name={glyph} /> : null}{children}</span>;
}

/** Human label first, exact enum as secondary audit metadata. */
export function OutcomeTag({ verdict }: { verdict?: string }) {
  const o = outcomeOf(verdict);
  return <Tag tone={o.tone} glyph={o.glyph} title={verdict}>{o.label}</Tag>;
}

export function EnumLine({ label, raw }: { label: string; raw?: string }) {
  return <><span className="h-label">{label}</span>{raw ? <span className="enum">{raw}</span> : null}</>;
}

export function Result({ model, id }: { model: Overall; id?: string }) {
  return (
    <div className={`result tone-${model.tone}`} id={id}>
      <span className="result-glyph"><Icon name={model.glyph} className="" /></span>
      <span className="result-word">{model.word}</span>
    </div>
  );
}

export function ExitChip({ model, id }: { model: Overall; id?: string }) {
  const tone = model.tone === 'pre' ? 'muted' : model.tone;
  return <span className={`exit-chip mono tone-${tone}`} title={model.raw || undefined} id={id}>exit {model.exit}</span>;
}

/** Full SHA on hover; short SHA on screen. */
export function Sha({ sha, n = 10 }: { sha?: string | null; n?: number }) {
  return <code title={sha ?? ''}>{short(sha, n)}</code>;
}

/** Progressive disclosure: the summary meta must still say something useful when collapsed. */
export function Evidence({ title, meta, metaTone, open, children, className = '', id }: { title: string; meta?: ReactNode; metaTone?: Tone | null; open?: boolean; children: ReactNode; className?: string; id?: string }) {
  return (
    <details className={`evidence ${className}`} open={open} id={id}>
      <summary><span>{title}</span>{meta !== undefined ? <span className={`summary-meta${metaTone ? ` is-${metaTone}` : ''}`}>{meta}</span> : null}</summary>
      {children}
    </details>
  );
}

export function Empty({ glyph, children, id }: { glyph: Glyph; children: ReactNode; id?: string }) {
  return <div className="panel empty" id={id}><Icon name={glyph} className="ic ic-lg" /><p>{children}</p></div>;
}

export function PageHead({ crumb, title, lede, aside, id }: { crumb: string; title: string; lede?: ReactNode; aside?: ReactNode; id: string }) {
  return (
    <header className="page-head">
      <div>
        <p className="eyebrow">Workspace / {crumb}</p>
        <h1 id={id}>{title}</h1>
        {lede ? <p className="lede">{lede}</p> : null}
      </div>
      {aside}
    </header>
  );
}

/** Approved-check assertions as `expect metric == value` lines. */
export function Assertions({ check, className = 'code-block', label }: { check?: Check | null; className?: string; label?: string }) {
  const list = Array.isArray(check?.assertions) ? check.assertions : [];
  return (
    <pre className={className} aria-label={label}>
      {list.length ? list.map((a, i) => (
        <span key={i}>{i ? '\n' : ''}<span className="kw">expect </span>{`${a.metric || 'unknown'} == `}<span className="num">{a.equals === undefined ? 'unset' : JSON.stringify(a.equals)}</span></span>
      )) : '—'}
    </pre>
  );
}

export function Json({ value, id, label = 'JSON evidence' }: { value: unknown; id?: string; label?: string }) {
  return <pre id={id} tabIndex={0} aria-label={label}>{value === undefined || value === null ? 'Not recorded' : JSON.stringify(value, null, 2)}</pre>;
}
