/**
 * app/fc/page.tsx — FR-1 Today's Pick.
 *
 * Server filters run in /api/fc/picks; the decision filter (top/official/
 * watch) is client-side over the returned page. Scan trigger stays honestly
 * disabled while engine_offline (user decision).
 */
'use client';
import { useMemo, useState } from 'react';
import { useFcPoll } from '@/lib/fc/hooks';
import { buildQuery } from '@/lib/fc/client';
import type { PicksResponse } from '@/lib/fc/types';
import { FilterBar, PickCards, PickTable, type PickFilters } from '@/components/fc/PickTable';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

const DEFAULT_FILTERS: PickFilters = {
  market: 'all', league: 'all', decision: 'all', search: '', sort_by: 'rank_score', sort_order: 'desc',
};

export default function FcTodayPick() {
  const [filters, setFilters] = useState<PickFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(0);
  const LIMIT = 50;

  const query = useMemo(
    () =>
      buildQuery({
        market: filters.market === 'all' ? undefined : filters.market,
        league: filters.league === 'all' ? undefined : filters.league,
        search: filters.search || undefined,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
        limit: LIMIT,
        offset: page * LIMIT,
      }),
    [filters, page],
  );

  const { data, loading, error, refresh } = useFcPoll<PicksResponse>(`/api/fc/picks${query}`, 60000);

  const picks = useMemo(() => {
    const list = data?.picks ?? [];
    if (filters.decision === 'all') return list;
    return list.filter((p) => {
      if (filters.decision === 'top_pick') return p.is_top_pick || p.decision === 'top_pick';
      return p.decision === filters.decision;
    });
  }, [data, filters.decision]);

  const total = data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / LIMIT));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Today&apos;s Pick</h1>
          <p className="page-subtitle">
            {data ? `${total} pick lolos gate · ${data.summary.top_pick_count} top · ${data.summary.official_count} official · ${data.summary.watch_count} watch` : 'Memuat…'}
          </p>
        </div>
        <div className="fc-scanrow">
          <button
            className="btn btn-primary"
            disabled
            title="Engine offline — trigger scan aktif lagi setelah engine direstore di VPS."
          >
            ▶ Run Live Scan (offline)
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      <FilterBar
        filters={filters}
        leagues={data?.summary.leagues ?? []}
        onChange={(f) => {
          setFilters(f);
          setPage(0);
        }}
      />

      {loading && !data ? (
        <SkeletonRows rows={6} label="Memuat picks…" />
      ) : picks.length === 0 ? (
        <EmptyState
          title="Belum ada pick yang lolos gate hari ini"
          body="Slot kosong berarti belum ada yang memenuhi syarat model + harga — bukan error dan bukan diisi paksa."
          showWhy
        />
      ) : (
        <>
          <div className="fc-table-wrap">
            <PickTable picks={picks} />
          </div>
          <PickCards picks={picks} />
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
