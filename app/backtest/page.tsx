'use client';
import { useEffect, useState } from 'react';
import { ExperimentalBadge } from '@/components/FinalStateChip';

export default function Backtest() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/backtest')
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const hitRate = (wins: number, total: number) => {
    if (total === 0) return '—';
    return `${((wins / total) * 100).toFixed(1)}%`;
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Backtest Dashboard</h1>
          <p className="page-subtitle">
            Performance by model version · Only forecasts locked before first pitch are counted
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem', background: 'rgba(215,119,6,0.06)', borderColor: 'rgba(215,119,6,0.3)' }}>
        <p style={{ fontSize: '0.85rem', color: 'var(--amber-lt)' }}>
          ⚠ Hit rate is based on formula scoring, not calibrated probability. Sample sizes below 50 are not predictive.
          ROI is hidden until market prices and a declared flat-stake policy are configured.
        </p>
      </div>

      {loading ? (
        <div className="muted" style={{ padding: '2rem', textAlign: 'center' }} aria-live="polite">Loading…</div>
      ) : !data ? (
        <div role="alert" className="muted" style={{ textAlign: 'center', padding: '2rem' }}>Failed to load backtest data.</div>
      ) : data.totalSettlements === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem 0' }}>
          <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📊</div>
          <p className="muted">No settled forecasts yet.</p>
          <p className="muted" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            Lock forecasts before games and ingest official results to populate this dashboard.
          </p>
        </div>
      ) : (
        <>
          <table className="data-table" aria-label="Backtest results by model version">
            <thead>
              <tr>
                <th>Model</th>
                <th>Config Version</th>
                <th>Sample Size</th>
                <th>Wins</th>
                <th>Losses</th>
                <th>Pushes</th>
                <th>Hit Rate</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody>
              {data.summary?.map((row: any) => (
                <tr key={`${row.model}-${row.version}`}>
                  <td style={{ fontWeight: 600 }}>
                    {row.model}
                    {row.model.includes('Over/Under') && (
                      <span style={{ marginLeft: '0.5rem' }}><ExperimentalBadge /></span>
                    )}
                  </td>
                  <td className="mono-val">{row.version}</td>
                  <td className="mono-val">
                    <strong style={{ color: row.total < 20 ? 'var(--amber-lt)' : '#e2e8f0' }}>{row.total}</strong>
                    {row.total < 20 && <span className="muted" style={{ fontSize: '0.75rem', marginLeft: '0.4rem' }}>⚠ small</span>}
                  </td>
                  <td className="mono-val" style={{ color: 'var(--green-lt)' }}>{row.wins}</td>
                  <td className="mono-val" style={{ color: 'var(--red-lt)' }}>{row.losses}</td>
                  <td className="mono-val" style={{ color: 'var(--muted)' }}>{row.pushes}</td>
                  <td className="mono-val" style={{ fontWeight: 600 }}>{hitRate(row.wins, row.total - row.pushes)}</td>
                  <td className="muted" style={{ fontSize: '0.8rem' }}>N/A — configure stake policy</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: '0.75rem', marginTop: '1rem' }}>
            {data.note}
          </p>
        </>
      )}
    </div>
  );
}
