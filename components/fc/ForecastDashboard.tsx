'use client';
import { useEffect, useState } from 'react';
import { fetchAllMatches } from '@/lib/fc/allMatches';
import { fcGet, fcPost } from '@/lib/fc/client';
import { FC_UI_VERSION } from '@/lib/fc/predictions';
import type { DetailedMatch } from '@/lib/fc/types';
import { PredictionBoard, type BoardView } from './PredictionBoard';
import { ScheduleList } from './ScheduleList';
import { ErrorBanner, SkeletonRows } from './shared';

// The live scan script allows 10 minutes server-side; keep the client above it.
const SCAN_TIMEOUT_MS = 660000;

export function ForecastDashboard({ view = 'all', title = 'Prediksi Pertandingan', mode = 'board' }: { view?: BoardView; title?: string; mode?: 'board' | 'schedule' | 'value' | 'market' }) {
  const [matches, setMatches] = useState<DetailedMatch[] | null>(null);
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    let busy = false;
    const load = async () => {
      if (busy) return;
      busy = true;
      try { const rows = await fetchAllMatches(); if (active) { setMatches(rows); setError(''); } }
      catch (err) { if (active) setError(err instanceof Error ? err.message : 'Gagal memuat pertandingan.'); }
      finally { busy = false; }
    };
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 60000);
    const visible = () => { if (!document.hidden) void load(); };
    document.addEventListener('visibilitychange', visible);
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  const scan = async () => {
    setScanning(true); setMessage('Memperbarui fixture, odds, dan model liga. Proses dapat memerlukan beberapa menit.');
    try {
      const start = await fcPost<{ status?: string; message?: string }>('/api/fc/scan', undefined, {}, 20000);
      if (start.status === 'busy') { setMessage(start.message || 'Scan sedang berjalan, tunggu sebentar.'); }
      else {
        let elapsed = 0;
        while (elapsed < SCAN_TIMEOUT_MS) {
          await new Promise((r) => setTimeout(r, 3000));
          elapsed += 3000;
          const status = await fcGet<{ running: boolean; last: { status: string; message?: string } | null }>('/api/fc/scan');
          if (!status.running && status.last) {
            if (status.last.status === 'done') { setMessage(status.last.message || 'Analisis diperbarui.'); setRefresh((n) => n + 1); }
            else if (status.last.status === 'error') { setMessage(status.last.message || 'Scan gagal.'); }
            break;
          }
        }
        if (elapsed >= SCAN_TIMEOUT_MS) setMessage('Scan melebihi batas waktu, coba lagi.');
      }
    } catch (err) { setMessage(err instanceof Error ? err.message : 'Scan gagal.'); }
    finally { setScanning(false); }
  };
  return <div className="forecast-dashboard" data-ui-version={FC_UI_VERSION}>
    <header className="prediction-page-header"><div><span className="prediction-eyebrow">FOOTBALL MARKET INTELLIGENCE</span><h1>{title}</h1><p>Temukan pertandingan. Bandingkan pasar. Susun pilihan Anda.</p></div><button type="button" className="prediction-scan" onClick={scan} disabled={scanning} aria-busy={scanning}>{scanning ? 'Memproses analisis…' : '↻ Perbarui analisis'}</button></header>
    {message && <p className="prediction-scan-message" role="status">{message}</p>}
    {error && <ErrorBanner message={error} onRetry={() => setRefresh((n) => n + 1)} />}
    {matches === null ? <SkeletonRows rows={5} label="Memuat pertandingan…" /> : mode === 'schedule' ? <ScheduleList matches={matches} /> : <PredictionBoard matches={matches} initialView={view} marketScope={mode === 'market' ? 'top' : 'all'} />}
  </div>;
}
