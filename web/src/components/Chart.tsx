// One rounded block per job actually observed. A missing observation is a hatched orange outline, never an
// empty or green column. The dashed purple line is what the approved check expects.
import type { CSSProperties } from 'react';
import type { Tone } from '@/lib/model';

export interface Column { label?: string; note?: string; jobs?: number | null; tone?: Tone; placeholder?: boolean }

interface Props {
  columns: Column[];
  expected?: number | null;
  /** stacked: one block per job; otherwise one capsule whose height is the job count */
  stacked?: boolean;
  colW?: number; gap?: number; unit?: number; padB?: number; notes?: boolean;
  className?: string;
  label: string;
  id?: string;
}

export function Columns({ columns, expected = null, stacked = true, colW = 64, gap = 40, unit = 46, padB = 66, notes = true, className = 'chart', label, id }: Props) {
  const counts = columns.map((c) => (Number.isInteger(c.jobs) ? (c.jobs as number) : 0));
  const max = Math.min(6, Math.max(3, expected ?? 0, ...counts));
  const u = Math.min(unit, (unit * 3) / max);
  const padL = 30; const padR = expected === null ? 12 : 86; const padT = 12;
  const width = padL + padR + columns.length * (colW + gap);
  const base = padT + max * u;
  const ticks = Array.from({ length: max + 1 }, (_, n) => n);

  return (
    <svg id={id} className={className} viewBox={`0 0 ${width} ${base + padB}`} role="img" aria-label={label}>
      {ticks.map((n) => (
        <g key={`t${n}`}>
          <line x1={padL} y1={base - n * u} x2={width - padR + 8} y2={base - n * u} className="grid-line" />
          <text x={padL - 10} y={base - n * u + 4} textAnchor="end" className="tick">{n}</text>
        </g>
      ))}
      {columns.map((col, i) => {
        if (col.placeholder) return null;
        const x = padL + gap / 2 + i * (colW + gap);
        const cx = x + colW / 2;
        const jobs = Number.isInteger(col.jobs) ? (col.jobs as number) : null;
        const delay = (k: number) => ({ '--i': String(k) }) as CSSProperties;
        let bars;
        if (jobs === null || col.tone === 'inc') {
          bars = <g className="bar" style={delay(i)}><rect x={x + 1} y={base - u + 3} width={colW - 2} height={u - 4} rx={stacked ? 7 : colW / 2.4} className="j-inc" /></g>;
        } else if (stacked) {
          bars = Array.from({ length: jobs }, (_, k) => (
            <g key={k} className="bar" style={delay(i * 3 + k)}><rect x={x} y={base - (k + 1) * u + 3} width={colW} height={u - 6} rx={7} className={`j-${col.tone ?? 'pass'}`} /></g>
          ));
        } else if (jobs > 0) {
          bars = <g className="bar" style={delay(i)}><rect x={x} y={base - jobs * u + 2} width={colW} height={jobs * u - 2} rx={Math.min(colW / 2, 16)} className={`j-${col.tone ?? 'pass'}`} /></g>;
        }
        return (
          <g key={`c${i}`}>
            {bars}
            <text x={cx} y={base + 24} textAnchor="middle" className="col-value">{jobs === null ? '—' : jobs}</text>
            {col.label ? <text x={cx} y={base + 42} textAnchor="middle" className="col-label">{col.label}</text> : null}
            {notes && col.note ? <text x={cx} y={base + 58} textAnchor="middle" className="col-note">{col.note}</text> : null}
          </g>
        );
      })}
      {Number.isInteger(expected) ? (
        <g>
          <line x1={padL} y1={base - (expected as number) * u} x2={width - padR + 8} y2={base - (expected as number) * u} className="exp-line" />
          <text x={width - padR + 14} y={base - (expected as number) * u + 4} className="exp-label">expected {expected}</text>
        </g>
      ) : null}
    </svg>
  );
}
