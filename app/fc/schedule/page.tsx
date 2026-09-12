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
  const { data, loading, error, refresh } = useFcPoll<MatchesResponse>(
    `/api/fc/matches${buildQuery({ limit: LIMIT, offset: page * LIMIT })}`,
    60000,
  );

  const total = data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  const matches = data?.matches ?? [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Today&apos;s Schedule</h1>
          <p className="page-subtitle">{data ? `${total} fixture 24 jam ke depan` : 'Memuat…'}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      {loading && !data ? (
        <SkeletonRows rows={6} label="Memuat jadwal…" />
      ) : matches.length === 0 ? (
        <EmptyState
          title="Belum ada fixture 24 jam ke depan"
          body="Jadwal muncul setelah engine scan berikutnya. Data lama tidak dihapus — halaman ini hanya kosong karena belum ada data."
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
