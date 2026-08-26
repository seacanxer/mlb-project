'use client';
import { useEffect, useState } from 'react';

export default function DataHealth() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetch('/api/data-health')
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Data Health</h1>
          <p className="page-subtitle">Provider status, stale observations, and affected games</p>
        </div>
        <button id="btn-refresh-health" className="btn btn-ghost" onClick={load} disabled={loading}>
          ↻ Refresh
        </button>
      </div>

      {loading ? (
        <div className="muted" style={{ padding: '2rem', textAlign: 'center' }} aria-live="polite">Loading…</div>
      ) : !data ? (
        <div role="alert" className="muted" style={{ padding: '2rem', textAlign: 'center' }}>Failed to load data health.</div>
      ) : (
        <>
          {/* Providers */}
          <section aria-labelledby="providers-heading">
            <h2 id="providers-heading" style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.75rem' }}>
              Providers
            </h2>
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <table className="data-table" aria-label="Provider status">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.providers?.map((p: any) => (
                    <tr key={p.name}>
                      <td className="mono-val">{p.name}</td>
                      <td>
                        <span
                          className="chip"
                          style={{
                            background: p.status === 'configured' ? 'rgba(22,163,74,0.12)' : 'rgba(215,119,6,0.12)',
                            color: p.status === 'configured' ? 'var(--green-lt)' : 'var(--amber-lt)',
                            border: `1px solid ${p.status === 'configured' ? 'rgba(22,163,74,0.3)' : 'rgba(215,119,6,0.3)'}`,
                          }}
                          role="status"
                          aria-label={`${p.name} is ${p.status}`}
                        >
                          {p.status === 'configured' ? '✓' : '!'} {p.status}
                        </span>
                      </td>
                      <td className="muted" style={{ fontSize: '0.85rem' }}>{p.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Summary counters */}
          <section aria-labelledby="summary-heading">
            <h2 id="summary-heading" style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.75rem' }}>
              Observation Health
            </h2>
            <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
              {[
                { label: 'Stale Market Odds', value: data.summary?.staleMarkets, color: data.summary?.staleMarkets > 0 ? 'var(--red-lt)' : 'var(--green-lt)' },
                { label: 'Stale Team Stats', value: data.summary?.staleTeamStats, color: data.summary?.staleTeamStats > 0 ? 'var(--amber-lt)' : 'var(--green-lt)' },
                { label: 'Unconfirmed Starters', value: data.summary?.unconfirmedStarters, color: data.summary?.unconfirmedStarters > 0 ? 'var(--amber-lt)' : 'var(--green-lt)' },
              ].map((item) => (
                <div key={item.label} className="card-sm" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: item.color, fontFamily: 'JetBrains Mono, monospace' }}>
                    {item.value ?? 0}
                  </div>
                  <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>{item.label}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Manual odds import */}
          <section aria-labelledby="import-heading">
            <h2 id="import-heading" style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.75rem' }}>
              Manual Odds Import
            </h2>
            <div className="card">
              <p className="muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
                POST JSON to <code className="mono-val">/api/odds/import</code> with an array of odds rows:
              </p>
              <pre style={{ background: 'var(--navy-800)', padding: '1rem', borderRadius: 6, fontSize: '0.8rem', overflowX: 'auto', color: '#e2e8f0' }}>
{`[
  {
    "gameId": "DEMO_01",
    "moneylineHomeOrig": "-130",
    "moneylineAwayOrig": "+110",
    "totalLine": 8.5,
    "totalOverOrig": "-110",
    "totalUnderOrig": "-110"
  }
]`}
              </pre>
              <p className="muted" style={{ fontSize: '0.8rem', marginTop: '0.75rem' }}>
                Accepts American (e.g. &quot;-145&quot;) or decimal (e.g. &quot;1.69&quot;) odds strings.
                No credentials or secrets are exposed client-side.
              </p>
            </div>
          </section>

          <p className="muted" style={{ fontSize: '0.75rem', marginTop: '1.5rem' }}>
            Last checked: {new Date(data.timestamp).toLocaleString()}
          </p>
        </>
      )}
    </div>
  );
}
