/**
 * components/fc/Results.tsx
 *
 * ROI dashboard primitives (brief FR-2). The dashboard is a MIRROR:
 * aggregates render `tracker.summary.*` verbatim — never recomputed from
 * row lists (brief §10.2/§11.4.7, enforced by the ROI parity script).
 */
'use client';
import { useEffect, useRef } from 'react';
import type { MarketPerformance, TrackedBet, TrackerSummary, VersionPerformance } from '@/lib/fc/types';
import { formatOdds, formatProfit, formatRoi, NULL_GLYPH, roiTone } from '@/lib/fc/format';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { MarketBadge } from './shared';

function toneClass(v: number | null | undefined): string {
  const t = roiTone(v);
  return t === 'positive' ? 'fc-pos' : t === 'negative' ? 'fc-neg' : 'fc-zero';
}

export function KpiRow({ summary }: { summary: TrackerSummary }) {
  const wlp = `${summary.wins}–${summary.losses}–${summary.pushes}`;
  return (
    <div className="fc-kpis" role="group" aria-label="Ringksan ROI">
      <div className="card card-sm"><div className="muted">Settled</div><div className="fc-kpi" data-testid="kpi-settled">{summary.settled_picks}</div></div>
      <div className="card card-sm"><div className="muted">W–L–P</div><div className="fc-kpi" data-testid="kpi-wlp">{wlp}</div></div>
      <div className="card card-sm"><div className="muted">Profit</div><div className={`fc-kpi ${toneClass(summary.profit_units)}`} data-testid="kpi-profit">{formatProfit(summary.profit_units)}</div></div>
      <div className="card card-sm"><div className="muted">ROI</div><div className={`fc-kpi ${toneClass(summary.roi_pct)}`} data-testid="kpi-roi">{formatRoi(summary.roi_pct)}</div></div>
      <div className="card card-sm"><div className="muted">Hit rate</div><div className="fc-kpi" data-testid="kpi-hit">{formatRoi(summary.hit_rate_pct)}</div></div>
    </div>
  );
}

/** Cumulative-profit equity curve on a light canvas (no chart lib). */
export function EquityChart({ settled }: { settled: TrackedBet[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const pts: number[] = [];
  {
    let run = 0;
    const ordered = [...settled].sort((a, b) => (a.start_ts ?? 0) - (b.start_ts ?? 0));
    for (const b of ordered) {
      if (typeof b.profit === 'number' && Number.isFinite(b.profit)) {
        run += b.profit;
        pts.push(Math.round(run * 100) / 100);
      }
    }
  }
  useEffect(() => {
    const cv = ref.current;
    if (!cv || pts.length === 0) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;
    const W = (cv.width = cv.offsetWidth * 2);
    const H = (cv.height = 240);
    ctx.clearRect(0, 0, W, H);
    const min = Math.min(0, ...pts);
    const max = Math.max(0, ...pts);
    const span = max - min || 1;
    const x = (i: number) => (pts.length === 1 ? W / 2 : (i / (pts.length - 1)) * (W - 16) + 8);
    const y = (v: number) => H - 16 - ((v - min) / span) * (H - 32);
    ctx.strokeStyle = 'rgba(148,163,184,0.4)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, y(0));
    ctx.lineTo(W, y(0));
    ctx.stroke();
    ctx.strokeStyle = pts[pts.length - 1] >= 0 ? '#22c55e' : '#ef4444';
    ctx.lineWidth = 3;
    ctx.beginPath();
    pts.forEach((v, i) => (i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v))));
    ctx.stroke();
  }, [settled]);
  if (pts.length === 0) return <p className="muted">Belum ada equity curve — belum ada settled bet.</p>;
  return <canvas ref={ref} className="fc-equity" role="img" aria-label={`Equity curve, ${pts.length} settled bets`} />;
}

function resultOf(b: TrackedBet): 'W' | 'L' | 'P' | null {
  if (b.won === 1) return 'W';
  if (b.won === 0) return 'L';
  if (b.settled && b.won === null) return 'P';
  return null;
}

export function ResultsTable({ rows }: { rows: TrackedBet[] }) {
  if (rows.length === 0) return <p className="muted">Belum ada hasil settled.</p>;
  return (
    <div className="fc-table-wrap">
      <table className="data-table" aria-label="Hasil settled">
        <thead>
          <tr>
            <th>Tanggal</th><th>Match</th><th>Market</th><th>Pick</th><th>Odds</th>
            <th>Skor FT</th><th>Hasil</th><th>Profit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => {
            const r = resultOf(b);
            const score = b.home_score !== null && b.away_score !== null && b.home_score !== undefined && b.away_score !== undefined
              ? `${b.home_score}–${b.away_score}` : NULL_GLYPH;
            return (
              <tr key={`${b.id ?? i}-${b.match}-${b.market}`}>
                <td className="mono-val" style={{ fontSize: '0.8rem' }}>{formatKickoffWIB(b.start_ts)}</td>
                <td>
                  <div style={{ fontWeight: 600 }}>{b.match ?? NULL_GLYPH}</div>
                  <div className="muted" style={{ fontSize: '0.75rem' }}>{b.league ?? NULL_GLYPH}</div>
                </td>
                <td><MarketBadge market={b.market} /></td>
                <td>{b.pick ?? NULL_GLYPH}</td>
                <td className="mono-val">{formatOdds(b.odds)}</td>
                <td className="mono-val">{score}{b.score_status ? <span className="muted"> · {b.score_status}</span> : null}</td>
                <td><span className={`chip ${r === 'W' ? 'chip-fc-win' : r === 'L' ? 'chip-fc-loss' : r === 'P' ? 'chip-fc-push' : ''}`}>{r ?? NULL_GLYPH}</span></td>
                <td className={`mono-val ${toneClass(b.profit)}`}>{formatProfit(b.profit)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function MarketBreakdown({ rows }: { rows: MarketPerformance[] }) {
  if (rows.length === 0) return <p className="muted">Belum ada breakdown per market.</p>;
  return (
    <div className="fc-table-wrap">
      <table className="data-table" aria-label="Breakdown per market">
        <thead><tr><th>Market</th><th>Bets</th><th>Win%</th><th>Profit</th><th>ROI</th></tr></thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.market}>
              <td><MarketBadge market={m.market} /></td>
              <td className="mono-val">{m.bets}</td>
              <td className="mono-val">{formatRoi(m.win_rate_pct)}</td>
              <td className={`mono-val ${toneClass(m.profit_units)}`}>{formatProfit(m.profit_units)}</td>
              <td className={`mono-val ${toneClass(m.roi_pct)}`}>{formatRoi(m.roi_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** by_version cohort table (brief FR-2, mandatory). */
export function ByVersionTable({ rows }: { rows: VersionPerformance[] }) {
  if (rows.length === 0) return <p className="muted">Belum ada kohort versi — muncul setelah ada settled bet berversi.</p>;
  return (
    <div className="fc-table-wrap">
      <table className="data-table" aria-label="Kohort per versi formula">
        <thead><tr><th>Formula</th><th>Status</th><th>Bets</th><th>Profit</th><th>ROI</th><th>CI95 ±</th></tr></thead>
        <tbody>
          {rows.map((v, i) => (
            <tr key={`${v.formula_version}-${v.selection_status}-${i}`}>
              <td className="mono-val" style={{ fontSize: '0.8rem' }}>{v.formula_version}</td>
              <td>{v.selection_status}</td>
              <td className="mono-val">{v.bets}</td>
              <td className={`mono-val ${toneClass(v.profit_units)}`}>{formatProfit(v.profit_units)}</td>
              <td className={`mono-val ${toneClass(v.roi_pct)}`} data-testid={`byver-roi-${i}`}>{formatRoi(v.roi_pct)}</td>
              <td className="mono-val muted">{v.ci95_hw_pct === null || v.ci95_hw_pct === undefined ? NULL_GLYPH : `${v.ci95_hw_pct.toFixed(2)}pp`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
