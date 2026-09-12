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
import type { TrackerResponse } from '@/lib/fc/types';
import { ByVersionTable, EquityChart, KpiRow, MarketBreakdown, ResultsTable } from '@/components/fc/Results';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

export default function FcResults() {
  const { data, loading, error, refresh } = useFcPoll<TrackerResponse>('/api/fc/tracker', 60000);
  const [market, setMarket] = useState('all');
  const [result, setResult] = useState('all');

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
            disabled
            title="Engine offline — refresh settlement aktif lagi setelah engine direstore di VPS."
          >
            ↻ Refresh settlement (offline)
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}

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
    </div>
  );
}
