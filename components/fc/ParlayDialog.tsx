/**
 * components/fc/ParlayDialog.tsx
 *
 * Popup that shows the frozen legs of one manual parlay slip (Hasil & ROI).
 * The tracker snapshot is a mirror: the dialog only formats what
 * `manual_parlays[].legs` already contains — no odds or profit maths here.
 */
'use client';
import { useEffect, useRef } from 'react';
import type { ManualParlay, ParlayLeg } from '@/lib/fc/types';
import { formatOdds, formatProfit, NULL_GLYPH } from '@/lib/fc/format';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { legMatchLabel, legOutcome, outcomeChipClass, slipOutcome, slipStatusLabel } from '@/lib/fc/parlay';
import { MarketBadge } from './shared';

function LegRow({ leg }: { leg: ParlayLeg }) {
  const outcome = legOutcome(leg.result);
  const score = leg.home_score !== null && leg.home_score !== undefined &&
    leg.away_score !== null && leg.away_score !== undefined
    ? `${leg.home_score}–${leg.away_score}`
    : NULL_GLYPH;
  return (
    <tr>
      <td className="mono-val" style={{ fontSize: '0.8rem' }}>{leg.start_ts ? formatKickoffWIB(leg.start_ts) : NULL_GLYPH}</td>
      <td className="muted" style={{ fontSize: '0.75rem' }}>{leg.league || NULL_GLYPH}</td>
      <td>
        <div style={{ fontWeight: 600 }}>{legMatchLabel(leg)}</div>
        {leg.settled_at && <div className="muted" style={{ fontSize: '0.72rem' }}>settled {leg.settled_at.slice(0, 16).replace('T', ' ')}</div>}
      </td>
      <td><MarketBadge market={leg.market} /></td>
      <td>{leg.pick || NULL_GLYPH}</td>
      <td className="mono-val">{formatOdds(leg.odds)}</td>
      <td className="mono-val">{score}</td>
      <td><span className={`chip ${outcomeChipClass(outcome)}`}>{outcome ?? '…'}</span></td>
      <td className="mono-val muted">{typeof leg.leg_return === 'number' ? `×${leg.leg_return.toFixed(2)}` : NULL_GLYPH}</td>
    </tr>
  );
}

export function ParlayDialog({ slip, onClose }: { slip: ManualParlay | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (slip && !dialog.open) dialog.showModal();
    if (!slip && dialog.open) dialog.close();
  }, [slip]);

  const legs = slip?.legs ?? [];
  const outcome = slip ? slipOutcome(slip.status) : null;
  const profitTone = slip && slip.profit !== null
    ? slip.profit > 0 ? 'fc-pos' : slip.profit < 0 ? 'fc-neg' : 'fc-zero'
    : '';

  return (
    <dialog
      ref={ref}
      className="fc-slip-dialog"
      aria-label={slip ? `Detail parlay ${slip.id}` : 'Detail parlay'}
      onClose={onClose}
      onCancel={onClose}
      onClick={(event) => { if (event.target === ref.current) ref.current?.close(); }}
    >
      {slip && (
        <div className="fc-slip-body">
          <header className="fc-slip-header">
            <div>
              <h2 id="fc-slip-title">Parlay #{slip.id}</h2>
              <p className="muted" style={{ margin: '0.2rem 0 0', fontSize: '0.78rem' }}>
                {slip.generated_at ? `dikunci ${String(slip.generated_at).slice(0, 16).replace('T', ' ')}` : 'dikunci manual'} · {legs.length} leg
              </p>
            </div>
            <button type="button" className="btn btn-ghost" onClick={() => ref.current?.close()}>✕ Tutup</button>
          </header>

          <div className="fc-slip-meta">
            <span>Odds gabungan <strong className="mono-val">{formatOdds(slip.combined_odds)}</strong></span>
            <span>Status <span className={`chip ${outcomeChipClass(outcome)}`}>{slipStatusLabel(slip.status)}</span></span>
            <span>Hasil <strong className={profitTone}>{slip.profit === null || slip.profit === undefined ? 'Menunggu skor' : formatProfit(slip.profit)}</strong></span>
            {slip.settled_at && <span>Settled <strong>{String(slip.settled_at).slice(0, 16).replace('T', ' ')}</strong></span>}
          </div>

          {legs.length === 0 ? (
            <p className="muted">Isi parlay tidak ada di snapshot ini — jalankan ulang <strong>Refresh settlement</strong> (atau <code>python scripts/fc-snapshot.py</code>) di VPS.</p>
          ) : (
            <div className="fc-table-wrap">
              <table className="data-table" aria-label={`Leg parlay ${slip.id}`}>
                <thead>
                  <tr>
                    <th>Kickoff</th><th>Liga</th><th>Pertandingan</th><th>Market</th>
                    <th>Pick</th><th>Odds</th><th>Skor FT</th><th>Hasil</th><th>Ret.</th>
                  </tr>
                </thead>
                <tbody>{legs.map((leg, i) => <LegRow key={leg.id ?? i} leg={leg} />)}</tbody>
              </table>
            </div>
          )}

          <footer className="muted" style={{ fontSize: '0.75rem' }}>
            Odds gabungan = perkalian odds tiap leg (teoretis, bukan harga bandar) · flat stake 1 unit · Ret. = pengembalian per leg (push = ×1.00).
          </footer>
        </div>
      )}
    </dialog>
  );
}
