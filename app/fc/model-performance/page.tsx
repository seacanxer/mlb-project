/**
 * app/fc/model-performance/page.tsx — Kinerja Model (projections ledger).
 *
 * MIRROR rule: renders reports/fc-model-performance.json verbatim via
 * /api/fc/model-performance. Hit rate / Brier / calibration gap measure
 * MODEL skill across ALL scan projections — no odds, no stake, no lock.
 * ROI tetap hanya di Hasil & ROI (tracker).
 */
'use client';
import { useMemo } from 'react';
import { useFcPoll } from '@/lib/fc/hooks';
import type { ModelPerformanceResponse } from '@/lib/fc/types';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(value);
}

export default function FcModelPerformance() {
  const { data, loading, error, refresh } = useFcPoll<ModelPerformanceResponse>(
    '/api/fc/model-performance',
    60000,
  );

  const markets = useMemo(() => Object.keys(data?.by_market ?? {}).sort(), [data]);

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
        <strong>Bukan laporan ROI.</strong>
        <p className="muted">
          Halaman ini mengukur skill MODEL (probabilitas vs hasil) dari seluruh proyeksi —
          termasuk yang tidak pernah di-lock. Tanpa odds, stake, atau uang. Laporan uang
          tetap hanya di <a href="/fc/results">Hasil &amp; ROI</a>.
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
                    {markets.map((market) => {
                      const bucket = data.by_market[market];
                      return (
                        <tr key={market}>
                          <td>{market}</td>
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
