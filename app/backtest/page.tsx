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

  const signed = (value: number | null | undefined, suffix = '') => {
    if (value == null) return '—';
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}${suffix}`;
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
          ⚠ Formula scores are not calibrated win probabilities. ROI uses the actual locked decimal price and a flat one-unit stake.
          Small samples and missing closing quotes remain explicitly marked.
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
          <div className="stat-grid" style={{ marginBottom: '1.5rem' }}>
            {[
              { label: 'Record', value: `${data.overall.wins}-${data.overall.losses}-${data.overall.pushes}` },
              { label: 'Profit', value: signed(data.overall.profitUnits, 'u') },
              { label: 'ROI', value: signed(data.overall.roiPct, '%') },
              { label: 'Average odds', value: data.overall.averageOdds?.toFixed(2) ?? '—' },
              { label: 'Average CLV', value: signed(data.overall.averageClvPct, '%') },
              { label: 'CLV coverage', value: `${data.overall.closingPriceCoverage}/${data.overall.pricedSettlements}` },
            ].map((item) => (
              <div className="card" key={item.label} style={{ padding: '1rem' }}>
                <div className="muted" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>{item.label}</div>
                <div className="mono-val" style={{ fontSize: '1.25rem', fontWeight: 800, marginTop: '0.25rem' }}>{item.value}</div>
              </div>
            ))}
          </div>
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
                <th>Profit</th>
                <th>ROI</th>
                <th>Avg Odds</th>
                <th>Avg CLV</th>
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
                  <td className="mono-val" style={{ fontWeight: 600 }}>{hitRate(row.wins, row.wins + row.losses)}</td>
                  <td className="mono-val">{signed(row.profitUnits, 'u')}</td>
                  <td className="mono-val">{signed(row.roiPct, '%')}</td>
                  <td className="mono-val">{row.averageOdds?.toFixed(2) ?? '—'}</td>
                  <td className="mono-val" title={`${row.closingPriceCoverage} closing quote(s) available`}>
                    {signed(row.averageClvPct, '%')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            {[
              { title: 'Performance by Market', rows: data.byMarket },
              { title: 'Performance by Tier', rows: data.byTier },
            ].map((section) => (
              <div className="card" key={section.title} style={{ overflowX: 'auto' }}>
                <h2 style={{ fontSize: '0.95rem', marginBottom: '0.75rem' }}>{section.title}</h2>
                <table className="data-table">
                  <thead><tr><th>Group</th><th>Record</th><th>Profit</th><th>ROI</th><th>CLV</th></tr></thead>
                  <tbody>
                    {section.rows?.map((row: any) => (
                      <tr key={row.key}>
                        <td style={{ fontWeight: 600 }}>{String(row.key).replaceAll('_', ' ')}</td>
                        <td className="mono-val">{row.wins}-{row.losses}-{row.pushes}</td>
                        <td className="mono-val">{signed(row.profitUnits, 'u')}</td>
                        <td className="mono-val">{signed(row.roiPct, '%')}</td>
                        <td className="mono-val">{signed(row.averageClvPct, '%')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: '0.75rem', marginTop: '1rem' }}>
            {data.note}
            {' '}{data.stakePolicy}
          </p>
        </>
      )}
    </div>
  );
}
