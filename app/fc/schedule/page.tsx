/**
 * app/fc/schedule/page.tsx — FR-3 Today's Schedule (future fixtures only,
 * enforced server-side in readMatches).
 */
'use client';
import { useState } from 'react';
import { useFcPoll } from '@/lib/fc/hooks';
import { buildQuery } from '@/lib/fc/client';
import type { MatchesResponse } from '@/lib/fc/types';
import { ScheduleTable } from '@/components/fc/Schedule';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

const LIMIT = 50;

export default function FcSchedule() {
  const [page, setPage] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState('');
  const { data, loading, error, refresh } = useFcPoll<MatchesResponse>(
    `/api/fc/matches${buildQuery({ limit: LIMIT, offset: page * LIMIT })}`,
    60000,
  );

  const total = data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  const matches = data?.matches ?? [];

  const scrapeNow = async () => {
    setScanning(true);
    setScanMsg('');
    try {
      const res = await fetch('/api/fc/scan', { method: 'POST' });
      const body = (await res.json()) as { status: string; fixtures?: number; message?: string };
      if (!res.ok) throw new Error(body.message ?? `Scrape gagal (${res.status})`);
      setScanMsg(`✓ ${body.message ?? 'Jadwal terupdate.'} (jadwal saja — tanpa analisa model)`);
      setPage(0);
      refresh();
    } catch (err) {
      setScanMsg(`⚠ ${err instanceof Error ? err.message : 'Scrape gagal.'}`);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Today&apos;s Schedule</h1>
          <p className="page-subtitle">{data ? `${total} fixture 24 jam ke depan` : 'Memuat…'}</p>
        </div>
        <div className="fc-scanrow">
          <button className="btn btn-primary" onClick={scrapeNow} disabled={scanning} aria-busy={scanning}>
            {scanning ? '⏳ Scraping…' : '↻ Scrape jadwal'}
          </button>
        </div>
      </div>

      {scanMsg && (
        <div role="status" className="muted" style={{ marginBottom: '1rem' }}>
          {scanMsg}
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      {loading && !data ? (
        <SkeletonRows rows={6} label="Memuat jadwal…" />
      ) : matches.length === 0 ? (
        <EmptyState
          title="Belum ada fixture 24 jam ke depan"
          body="Klik “Scrape jadwal” untuk mengambil fixture 24 jam dari 1xbit. Hasil scrape adalah jadwal saja (badge “Jadwal saja”) — pick/analisa muncul setelah engine direstore."
        />
      ) : (
        <>
          <ScheduleTable matches={matches} />
          {pages > 1 && (
            <div className="fc-scanrow" role="navigation" aria-label="Pagination">
              <button className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                ← Prev
              </button>
              <span className="muted">Hal {page + 1} / {pages}</span>
              <button className="btn btn-ghost btn-sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
