/**
 * app/fc/results/page.tsx — FR-2 Result & ROI Dashboard.
 *
 * MIRROR rule (brief §10.2): KPI cards render `tracker.summary.*` verbatim.
 * Filter di bawah hanya menyaring TABEL baris — tidak pernah menghitung ulang
 * agregat. Settle trigger disabled jujur selama engine offline.
 */
'use client';
import { useMemo, useState } from 'react';
import { useFcPoll } from '@/lib/fc/hooks';
import type { ManualParlay, TrackerResponse } from '@/lib/fc/types';
import { formatProfit } from '@/lib/fc/format';
import { slipStatusLabel } from '@/lib/fc/parlay';
import { ByVersionTable, EquityChart, KpiRow, MarketBreakdown, ResultsTable } from '@/components/fc/Results';
import { ParlayDialog } from '@/components/fc/ParlayDialog';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

export default function FcResults() {
  const { data, loading, error, refresh } = useFcPoll<TrackerResponse>('/api/fc/tracker', 60000);
  const [market, setMarket] = useState('all');
  const [result, setResult] = useState('all');
  const [settling, setSettling] = useState(false);
  const [settleNote, setSettleNote] = useState('');
  const [slipDetail, setSlipDetail] = useState<ManualParlay | null>(null);
  const offline = data?.engine_offline ?? false;

  const runSettle = async () => {
    setSettling(true);
    setSettleNote('Mengambil skor final dan menyelesaikan pick/parlay…');
    try {
      let token = '';
      try { token = sessionStorage.getItem('fc-lock-operator-token') || ''; } catch { /* Session storage is optional. */ }
      const res = await fetch('/api/fc/settle', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        cache: 'no-store',
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.message || `Settlement gagal (${res.status}).`);
      setSettleNote(body?.message || 'Settlement diperbarui.');
      refresh();
    } catch (err) {
      setSettleNote(err instanceof Error ? err.message : 'Settlement gagal.');
    } finally {
      setSettling(false);
    }
  };

  const settled = useMemo(() => {
    const rows = data?.settled ?? [];
    return rows.filter((b) => {
      if (market !== 'all' && (b.market ?? '').toLowerCase() !== market) return false;
      if (result === 'W') return b.won === 1;
      if (result === 'L') return b.won === 0;
      if (result === 'P') return b.settled !== 0 && b.won === null;
      return true;
    });
  }, [data, market, result]);

  const markets = useMemo(
    () => [...new Set((data?.settled ?? []).map((b) => (b.market ?? '').toLowerCase()).filter(Boolean))].sort(),
    [data],
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Result &amp; ROI</h1>
          <p className="page-subtitle">Flat-stake 1 unit · push = 0 · angka dibaca langsung dari tracker</p>
        </div>
        <div className="fc-scanrow">
          <button
            className="btn btn-ghost"
            disabled={offline || settling}
            aria-busy={settling}
            onClick={() => void runSettle()}
            title={offline
              ? 'Engine offline — refresh settlement aktif lagi setelah engine direstore di VPS.'
              : 'Ambil skor final lalu settle pick dan parlay manual (fc-settle-live.py).'}
          >
            {settling ? '↻ Refresh settlement…' : offline ? '↻ Refresh settlement (offline)' : '↻ Refresh settlement'}
          </button>
        </div>
      </div>

      {settleNote && <p className="muted" role="status" style={{ marginBottom: '1rem' }}>{settleNote}</p>}

      {error && <ErrorBanner message={error} onRetry={refresh} />}
      {data?.manual_summary && <div className="card card-sm" style={{ marginBottom: '1rem' }}><strong>Pilihan manual</strong><p className="muted">{data.manual_summary.locked_picks} menunggu hasil · {data.manual_summary.settled_picks} settled · ROI {data.manual_summary.roi_pct.toFixed(2)}%</p></div>}
      {data?.manual_parlay_summary && <div className="card card-sm" style={{ marginBottom: '1rem' }}>
        <strong>Parlay manual</strong><p className="muted">{data.manual_parlay_summary.pending_slips} menunggu hasil · {data.manual_parlay_summary.settled_slips} settled · {data.manual_parlay_summary.wins} menang · {data.manual_parlay_summary.losses} kalah · ROI {data.manual_parlay_summary.roi_pct.toFixed(2)}%</p>
        {!!data.manual_parlays?.length && <div className="muted">{data.manual_parlays.slice(0, 10).map((slip) => (
          <button
            key={slip.id}
            type="button"
            className="fc-slip-link"
            aria-label={`Detail parlay ${slip.id}`}
            onClick={() => setSlipDetail(slip)}
          >
            #{slip.id} · @{slip.combined_odds.toFixed(2)} · {slipStatusLabel(slip.status)}{slip.profit !== null && ` ${formatProfit(slip.profit)}`} · {(slip.legs?.length ?? 0) || '?'} leg
          </button>
        ))}</div>}
      </div>}

      {loading && !data ? (
        <SkeletonRows rows={6} label="Memuat hasil…" />
      ) : !data || data.summary.settled_picks === 0 ? (
        <EmptyState
          title="Belum ada hasil settled"
          body="ROI, equity curve, dan breakdown muncul otomatis setelah settlement pertama berjalan di engine."
        />
      ) : (
        <>
          <KpiRow summary={data.summary} />

          <h2 className="fc-section-title">Equity curve</h2>
          <div className="card"><EquityChart settled={data.settled} /></div>

          <h2 className="fc-section-title">Hasil settled</h2>
          <form className="fc-filters" onSubmit={(e) => e.preventDefault()}>
            <label>
              Market
              <select value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Market">
                <option value="all">Semua</option>
                {markets.map((m) => (
                  <option key={m} value={m}>{m.toUpperCase()}</option>
                ))}
              </select>
            </label>
            <label>
              Hasil
              <select value={result} onChange={(e) => setResult(e.target.value)} aria-label="Hasil">
                <option value="all">Semua</option>
                <option value="W">Won</option>
                <option value="L">Lost</option>
                <option value="P">Push</option>
              </select>
            </label>
          </form>
          <ResultsTable rows={settled} />

          <h2 className="fc-section-title">Breakdown per market</h2>
          <MarketBreakdown rows={data.market_performance} />

          <h2 className="fc-section-title">Kohort per versi formula</h2>
          <ByVersionTable rows={data.by_version} />
        </>
      )}
      <ParlayDialog slip={slipDetail} onClose={() => setSlipDetail(null)} />
    </div>
  );
}
