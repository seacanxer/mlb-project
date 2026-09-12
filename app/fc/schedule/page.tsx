'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchAllMatches } from '@/lib/fc/allMatches';
import type { DetailedMatch } from '@/lib/fc/types';
import { ScheduleTable } from '@/components/fc/Schedule';
import { EmptyState, ErrorBanner, SkeletonRows } from '@/components/fc/shared';

const POLL_MS = 60000;

export default function FcSchedule() {
  const [matches, setMatches] = useState<DetailedMatch[] | null>(null);
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    try {
      const all = await fetchAllMatches();
      setMatches(all);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal memuat jadwal.');
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      if (!document.hidden) void load();
    }, POLL_MS);
    const onVisible = () => {
      if (!document.hidden) void load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      abortRef.current?.abort();
    };
  }, [load]);

  const scrapeNow = async () => {
    setScanning(true);
    setScanMsg('');
    try {
      const res = await fetch('/api/fc/scan', { method: 'POST' });
      const body = (await res.json()) as { status: string; fixtures?: number; message?: string };
      if (!res.ok) throw new Error(body.message ?? `Scrape gagal (${res.status})`);
      setScanMsg(`✓ ${body.message ?? 'Jadwal terupdate.'} (jadwal saja — tanpa analisa model)`);
      await load();
    } catch (err) {
      setScanMsg(`⚠ ${err instanceof Error ? err.message : 'Scrape gagal.'}`);
    } finally {
      setScanning(false);
    }
  };

  const total = matches?.length ?? 0;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Today&apos;s Schedule</h1>
          <p className="page-subtitle">{matches ? `${total} fixture 24 jam ke depan` : 'Memuat…'}</p>
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

      {error && <ErrorBanner message={error} onRetry={load} />}

      {matches === null ? (
        <SkeletonRows rows={6} label="Memuat jadwal…" />
      ) : matches.length === 0 ? (
        <EmptyState
          title="Belum ada fixture 24 jam ke depan"
          body="Klik “Scrape jadwal” untuk mengambil fixture 24 jam dari 1xbit. Hasil scrape adalah jadwal saja — pick/analisa muncul setelah engine direstore."
        />
      ) : (
        <ScheduleTable matches={matches} />
      )}
    </div>
  );
}