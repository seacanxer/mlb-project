/**
 * app/fc/model-performance/page.tsx — Kinerja Model (projections ledger).
 *
 * MIRROR rule: renders reports/fc-model-performance.json verbatim via
 * /api/fc/model-performance. Hit rate / Brier / calibration gap measure
 * MODEL skill across ALL scan projections — no odds, no stake, no lock.
 * ROI tetap hanya di Hasil & ROI (tracker). Filters below only narrow the
 * detail table — they never recompute aggregates.
 */
'use client';
import { useMemo, useState } from 'react';
import { useFcPoll } from '@/lib/fc/hooks';
import type { ModelPerformanceResponse, RecentGrade } from '@/lib/fc/types';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(value);
}

function outcomeChip(outcome?: string): string {
  switch (outcome) {
    case 'win': return 'W';
    case 'half_win': return 'HW';
    case 'push': return 'P';
    case 'half_loss': return 'HL';
    case 'loss': return 'L';
    default: return outcome ?? '—';
  }
}

export default function FcModelPerformance() {
  const { data, loading, error, refresh } = useFcPoll<ModelPerformanceResponse>(
    '/api/fc/model-performance',
    60000,
  );
  const [market, setMarket] = useState('all');
  const [result, setResult] = useState('all');
  const [search, setSearch] = useState('');

  const markets = useMemo(() => Object.keys(data?.by_market ?? {}).sort(), [data]);

  const detail = useMemo(() => {
    const rows: RecentGrade[] = data?.recent ?? [];
    const query = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (market !== 'all' && (row.market ?? '').toLowerCase() !== market) return false;
      if (result !== 'all') {
        const won = row.outcome === 'win' || row.outcome === 'half_win';
        const lost = row.outcome === 'loss' || row.outcome === 'half_loss';
        if (result === 'W' && !won) return false;
        if (result === 'L' && !lost) return false;
        if (result === 'P' && row.outcome !== 'push') return false;
      }
      if (query) {
        const hay = `${row.match ?? ''} ${row.pick ?? ''} ${row.league ?? ''}`.toLowerCase();
        if (!hay.includes(query)) return false;
      }
      return true;
    });
  }, [data, market, result, search]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Kinerja Model</h1>
          <p className="page-subtitle">
            Semua proyeksi per scan vs hasil aktual · hit rate / Brier / kalibrasi · bukan ROI
          </p>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      <div className="card card-sm" style={{ marginBottom: '1rem' }}>
        <strong>Bukan laporan ROI — cara baca yang benar.</strong>
        <p className="muted">
          Setiap line dinilai di <em>semua sisi yang ditawarkan</em> (over+under, home+away,
          yes+no), sehingga hit rate selalu memusat di 0.5 (biner) / 0.33 (1X2) secara
          struktural. Itu normal, bukan bagus atau jelek. Untuk skill model, baca{' '}
          <strong>Brier</strong> (makin kecil makin baik; acak ≈ 0.25) dan{' '}
          <strong>cal gap</strong> (≈ 0 berarti probabilitas jujur). Laporan uang tetap
          hanya di <a href="/fc/results">Hasil &amp; ROI</a>.
        </p>
      </div>

      {loading && !data ? (
        <SkeletonRows rows={6} label="Memuat kinerja model…" />
      ) : !data || data.report_missing ? (
        <EmptyState
          title="Report kinerja belum tersedia"
          body="Cron ledger belum pernah jalan (scripts/fc-ledger-cron.sh). Report muncul otomatis setelah grading pertama."
        />
      ) : (
        <>
          <div className="card card-sm" style={{ marginBottom: '1rem' }}>
            <strong>Ringkasan ledger</strong>
            <p className="muted">
              {data.ledger_entries} proyeksi tercatat · {data.graded} ter-grade ·{' '}
              {data.pending} menunggu hasil
              {data.generated_at ? ` · digenerate ${data.generated_at}` : ''}
            </p>
          </div>

          {data.graded === 0 ? (
            <EmptyState
              title="Belum ada proyeksi ter-grade"
              body="Ledger sudah mencatat proyeksi, tapi belum ada fixture yang lewat kickoff + 105 menit. Angka per-market muncul setelah grading pertama."
            />
          ) : (
            <>
              <h2 className="fc-section-title">Per market</h2>
              <div className="fc-table-wrap">
                <table className="data-table" aria-label="Kinerja model per market">
                  <thead>
                    <tr>
                      <th scope="col">Market</th>
                      <th scope="col">N decisif</th>
                      <th scope="col">Hit rate</th>
                      <th scope="col">Mean pred</th>
                      <th scope="col">Brier</th>
                      <th scope="col">Cal gap</th>
                      <th scope="col">W / HW / HL / L / Push</th>
                    </tr>
                  </thead>
                  <tbody>
                    {markets.map((key) => {
                      const bucket = data.by_market[key];
                      return (
                        <tr key={key}>
                          <td>{key}</td>
                          <td>{bucket.decisive}</td>
                          <td>{fmt(bucket.hit_rate)}</td>
                          <td>{fmt(bucket.mean_predicted)}</td>
                          <td>{fmt(bucket.brier)}</td>
                          <td>{fmt(bucket.calibration_gap)}</td>
                          <td>
                            {bucket.wins} / {bucket.half_wins} / {bucket.half_losses} /{' '}
                            {bucket.losses} / {bucket.pushes}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <h2 className="fc-section-title">Detail pick terbaru</h2>
              <p className="muted" style={{ marginBottom: '0.75rem' }}>
                <a className="btn btn-ghost btn-sm" href="/api/fc/model-performance/csv" download>
                  Unduh CSV full ({data.graded} baris ter-grade)
                </a>
              </p>
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
                <label>
                  Cari
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="tim / pick / liga"
                    aria-label="Cari"
                  />
                </label>
              </form>
              {(data.recent ?? []).length === 0 ? (
                <p className="muted">
                  Detail per-pick tersedia setelah cron berikutnya meregenerasi report
                  (maksimal 100 pick terbaru).
                </p>
              ) : detail.length === 0 ? (
                <EmptyState title="Tidak cocok filter" body="Ubah market, hasil, atau kata kunci." />
              ) : (
                <div className="fc-table-wrap">
                  <table className="data-table" aria-label="Detail pick ter-grade">
                    <thead>
                      <tr>
                        <th scope="col">Match</th>
                        <th scope="col">Pick</th>
                        <th scope="col">Prob</th>
                        <th scope="col">Hasil</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.map((row, i) => (
                        <tr key={`${row.match}-${row.market}-${row.pick}-${i}`}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{row.match ?? '—'}</div>
                            <div className="muted">{row.league ?? ''}</div>
                          </td>
                          <td>
                            <div style={{ fontWeight: 600 }}>{row.pick ?? '—'}</div>
                            <div className="muted">{row.market ?? ''}</div>
                          </td>
                          <td>{fmt(row.model_probability)}</td>
                          <td>{outcomeChip(row.outcome)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="muted" style={{ marginTop: '0.75rem' }}>
                Half-win/half-loss dihitung 0.5 pada hit rate &amp; Brier · push dikeluarkan
                dari decisif · cal gap = hit rate − mean predicted.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
