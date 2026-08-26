'use client';
import { useEffect, useState } from 'react';
import { FinalStateChip } from '@/components/FinalStateChip';

export default function ForecastHistory() {
  const [forecasts, setForecasts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch all forecasts via game detail (simplified)
    fetch('/api/backtest')
      .then((r) => r.json())
      .then(() => {
        // For now, query directly
        fetch('/api/forecast-history')
          .then((r) => r.json())
          .then((d) => { setForecasts(d.forecasts ?? []); setLoading(false); })
          .catch(() => setLoading(false));
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Forecast History</h1>
          <p className="page-subtitle">All locked forecasts with original lines, revisions, results, and settlements</p>
        </div>
      </div>
      {loading ? (
        <div className="muted" style={{ padding: '2rem', textAlign: 'center' }} aria-live="polite">Loading…</div>
      ) : forecasts.length === 0 ? (
        <div style={{ padding: '3rem 0', textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>🔒</div>
          <p className="muted">No locked forecasts yet.</p>
          <p className="muted" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            Open a Match Detail and lock a forecast before first pitch.
          </p>
        </div>
      ) : (
        <table className="data-table" aria-label="Forecast history">
          <thead>
            <tr>
              <th>Forecast ID</th>
              <th>Game</th>
              <th>Locked At</th>
              <th>Market Line</th>
              <th>Final State</th>
              <th>Settlement</th>
            </tr>
          </thead>
          <tbody>
            {forecasts.map((f: any) => (
              <tr key={f.id}>
                <td className="mono-val" style={{ fontSize: '0.75rem' }}>{f.id.slice(0, 12)}…</td>
                <td>{f.modelRun?.gameId ?? '—'}</td>
                <td style={{ fontSize: '0.8rem' }}>{new Date(f.lockedAt).toLocaleString()}</td>
                <td className="mono-val">{f.marketLine ?? '—'}</td>
                <td><FinalStateChip state={f.finalState} size="sm" /></td>
                <td>
                  {f.settlement ? (
                    <span className={`chip ${f.settlement.outcome === 'win' ? 'chip-t1' : f.settlement.outcome === 'push' ? 'chip-t2' : 'chip-skip'}`}>
                      {f.settlement.outcome?.toUpperCase()}
                    </span>
                  ) : <span className="muted">Pending</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
