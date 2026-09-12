/**
 * components/fc/PickTable.tsx
 *
 * Today's Pick list: desktop table + mobile cards (brief FR-1, mobile-first).
 * Watch picks render dimmed + separated (never mixed silently with Official).
 */
'use client';
import type { FcPick } from '@/lib/fc/types';
import { formatCalibratedProb, formatEv, formatOdds, formatProb, NULL_GLYPH } from '@/lib/fc/format';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { CoverageBadge, MarketBadge, StatusBadge } from './shared';

export interface PickFilters {
  market: string;
  league: string;
  decision: string;
  search: string;
  sort_by: string;
  sort_order: string;
}

export function FilterBar({
  filters,
  leagues,
  onChange,
}: {
  filters: PickFilters;
  leagues: string[];
  onChange: (f: PickFilters) => void;
}) {
  const set = (k: keyof PickFilters, v: string) => onChange({ ...filters, [k]: v });
  return (
    <form className="fc-filters" role="search" aria-label="Filter picks" onSubmit={(e) => e.preventDefault()}>
      <label>
        Market
        <select value={filters.market} onChange={(e) => set('market', e.target.value)} aria-label="Market">
          {['all', 'ah', 'ou', 'btts', '1x2'].map((m) => (
            <option key={m} value={m}>{m === 'all' ? 'Semua' : m.toUpperCase()}</option>
          ))}
        </select>
      </label>
      <label>
        Liga
        <select value={filters.league} onChange={(e) => set('league', e.target.value)} aria-label="Liga">
          <option value="all">Semua liga</option>
          {leagues.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select value={filters.decision} onChange={(e) => set('decision', e.target.value)} aria-label="Status">
          <option value="all">Semua</option>
          <option value="top_pick">Top Pick</option>
          <option value="official">Official</option>
          <option value="watch">Watch</option>
        </select>
      </label>
      <label className="fc-search">
        Cari tim
        <input
          type="search"
          placeholder="cth: Arsenal"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
          aria-label="Cari tim"
        />
      </label>
      <label>
        Urut
        <select value={filters.sort_by} onChange={(e) => set('sort_by', e.target.value)} aria-label="Urut berdasar">
          <option value="rank_score">Rank</option>
          <option value="ev">EV</option>
          <option value="odds">Odds</option>
          <option value="start_ts">Kickoff</option>
        </select>
      </label>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => set('sort_order', filters.sort_order === 'desc' ? 'asc' : 'desc')}
        aria-label="Balik urutan"
      >
        {filters.sort_order === 'desc' ? '↓' : '↑'}
      </button>
    </form>
  );
}

function StakeCell({ p }: { p: FcPick }) {
  if (p.suggested_stake === null || p.suggested_stake === undefined) return <span className="muted">{NULL_GLYPH}</span>;
  return <span className="mono-val">{Number(p.suggested_stake).toFixed(2)}u</span>;
}

function CalibCell({ p }: { p: FcPick }) {
  const v = formatCalibratedProb(p.calibrated_prob);
  // calibrated_prob null → "—", never a number (brief DoD).
  if (v === null) return <span className="muted" title="Kalibrasi belum lolos validasi">{NULL_GLYPH}</span>;
  return <span className="mono-val muted" title="Attach-only, belum tervalidasi">{v}</span>;
}

export function PickTable({ picks }: { picks: FcPick[] }) {
  const top = picks.filter((p) => p.is_top_pick || p.decision === 'top_pick' || p.selection_status === 'top_pick');
  const rest = picks.filter((p) => !(p.is_top_pick || p.decision === 'top_pick' || p.selection_status === 'top_pick'));
  return (
    <div className="fc-table-wrap">
      <table className="data-table" aria-label="Today's picks">
        <thead>
          <tr>
            <th>Match</th>
            <th>Kickoff WIB</th>
            <th>Market</th>
            <th>Pick</th>
            <th>Odds</th>
            <th>Prob</th>
            <th>EV</th>
            <th>Stake</th>
            <th>Status</th>
            <th>Cakupan</th>
            <th>Kalibrasi</th>
          </tr>
        </thead>
        <tbody>
          {[...top, ...rest].map((p, i) => {
            const dim = p.tier === 'watch' || p.decision === 'watch';
            return (
              <tr key={`${p.match_id ?? p.match}-${p.market}-${p.pick}-${i}`} className={dim ? 'fc-row-watch' : p.is_top_pick ? 'fc-row-top' : undefined}>
                <td>
                  <div style={{ fontWeight: p.is_top_pick ? 700 : 600 }}>{p.match ?? NULL_GLYPH}</div>
                  <div className="muted" style={{ fontSize: '0.75rem' }}>{p.league ?? NULL_GLYPH}</div>
                </td>
                <td className="mono-val" style={{ fontSize: '0.8rem' }}>{formatKickoffWIB(p.start_ts)}</td>
                <td><MarketBadge market={p.market} /></td>
                <td style={{ fontWeight: 600 }}>{p.pick ?? NULL_GLYPH}</td>
                <td className="mono-val">{formatOdds(p.odds)}</td>
                <td className="mono-val">{formatProb(p.probability)}</td>
                <td className="mono-val">{formatEv(p.ev)}</td>
                <td><StakeCell p={p} /></td>
                <td><StatusBadge decision={p.decision} isTop={p.is_top_pick} /></td>
                <td><CoverageBadge coverage={p.coverage_status} /></td>
                <td><CalibCell p={p} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function PickCards({ picks }: { picks: FcPick[] }) {
  return (
    <div className="fc-cards">
      {picks.map((p, i) => {
        const dim = p.tier === 'watch' || p.decision === 'watch';
        return (
          <article key={`${p.match_id ?? p.match}-${p.market}-${i}`} className={`card fc-card${dim ? ' fc-card-watch' : ''}${p.is_top_pick ? ' fc-card-top' : ''}`}>
            <div className="fc-card-head">
              <StatusBadge decision={p.decision} isTop={p.is_top_pick} />
              <MarketBadge market={p.market} />
            </div>
            <h3 className="fc-card-match">{p.match ?? NULL_GLYPH}</h3>
            <p className="muted fc-card-league">{p.league ?? NULL_GLYPH} · {formatKickoffWIB(p.start_ts)}</p>
            <dl className="fc-card-grid">
              <div><dt>Pick</dt><dd>{p.pick ?? NULL_GLYPH}</dd></div>
              <div><dt>Odds</dt><dd className="mono-val">{formatOdds(p.odds)}</dd></div>
              <div><dt>Prob</dt><dd className="mono-val">{formatProb(p.probability)}</dd></div>
              <div><dt>EV</dt><dd className="mono-val">{formatEv(p.ev)}</dd></div>
            </dl>
            <div className="fc-card-foot">
              <CoverageBadge coverage={p.coverage_status} />
              <span className="muted" style={{ fontSize: '0.75rem' }}>
                Kalibrasi: {formatCalibratedProb(p.calibrated_prob) ?? NULL_GLYPH}
              </span>
            </div>
          </article>
        );
      })}
    </div>
  );
}
