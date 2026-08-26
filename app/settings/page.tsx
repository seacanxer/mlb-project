'use client';
import { useEffect, useState } from 'react';
import { DEFAULT_CONFIG } from '@/lib/config/modelConfig';

export default function Settings() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/settings/configs')
      .then((r) => r.json())
      .then((d) => { setConfigs(d.configs ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const cfg = DEFAULT_CONFIG;

  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <section style={{ marginBottom: '2rem' }} aria-labelledby={`section-${title.replace(/\s/g, '-')}`}>
      <h2 id={`section-${title.replace(/\s/g, '-')}`} style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.75rem' }}>
        {title}
      </h2>
      {children}
    </section>
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Versioned thresholds, freshness windows, and configuration history. Read-only view.</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem', background: 'rgba(37,99,235,0.06)', borderColor: 'rgba(37,99,235,0.3)' }}>
        <p style={{ fontSize: '0.85rem', color: '#60a5fa' }}>
          ℹ All thresholds are stored in versioned configuration. Editing creates a new immutable version. Existing forecasts retain their original config reference.
        </p>
      </div>

      <Section title="Moneyline v2.1 — ERA Gap Points">
        <div className="card" style={{ marginBottom: '1rem' }}>
          <table className="data-table" aria-label="ERA gap points table">
            <thead><tr><th>ERA Gap</th><th>Points</th></tr></thead>
            <tbody>
              {cfg.moneyline.eraGapBands.map((b, i) => (
                <tr key={i}>
                  <td className="mono-val">{b.maxGap ? `${b.minGap.toFixed(2)} – ${b.maxGap.toFixed(2)}` : `≥ ${b.minGap.toFixed(2)}`}</td>
                  <td className="mono-val" style={{ color: 'var(--blue-lt)', fontWeight: 700 }}>{b.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Moneyline v2.1 — Offense Composite Tiers">
        <div className="card" style={{ marginBottom: '1rem' }}>
          <table className="data-table" aria-label="Offense tiers">
            <thead><tr><th>Tier</th><th>AVG Range</th><th>OPS Range</th><th>Points</th></tr></thead>
            <tbody>
              {cfg.moneyline.offenseTiers.map((t) => (
                <tr key={t.label}>
                  <td style={{ fontWeight: 600 }}>{t.label}</td>
                  <td className="mono-val">{t.maxAvg ? `${t.minAvg.toFixed(3)}–${t.maxAvg.toFixed(3)}` : `> ${t.minAvg.toFixed(3)}`}</td>
                  <td className="mono-val">{t.maxOps ? `${t.minOps.toFixed(3)}–${t.maxOps.toFixed(3)}` : `> ${t.minOps.toFixed(3)}`}</td>
                  <td className="mono-val" style={{ color: 'var(--blue-lt)', fontWeight: 700 }}>{t.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Market Alignment — Fair Price Anchors">
        <div className="card" style={{ marginBottom: '1rem' }}>
          <p className="muted" style={{ fontSize: '0.8rem', marginBottom: '0.75rem' }}>
            These are heuristic anchors, not calibrated fair values or win probabilities.
          </p>
          <table className="data-table" aria-label="Fair price anchors">
            <thead><tr><th>ERA Gap Range</th><th>Fair Decimal</th></tr></thead>
            <tbody>
              {cfg.moneyline.marketAlignmentAnchors.map((a, i) => (
                <tr key={i}>
                  <td className="mono-val">{a.maxGap ? `${a.minGap.toFixed(2)} – ${a.maxGap.toFixed(2)}` : `≥ ${a.minGap.toFixed(2)}`}</td>
                  <td className="mono-val" style={{ color: 'var(--blue-lt)', fontWeight: 700 }}>{a.fairDecimal.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Tier Thresholds">
        <div className="grid-2">
          {[
            { label: 'T1 Minimum Score', value: cfg.moneyline.t1MinScore },
            { label: 'T2 Minimum Score', value: cfg.moneyline.t2MinScore },
            { label: 'Min Season IP', value: cfg.moneyline.minSeasonIp + ' IP' },
            { label: 'Warning IP Threshold', value: cfg.moneyline.minWarnIp + ' IP' },
            { label: 'Min Candidate AVG', value: '.' + String(cfg.moneyline.minCandidateAvg * 1000).padStart(3, '0') },
            { label: 'Hard Gate Bad Starts (of 5)', value: cfg.moneyline.maxBadStartsAllowed },
            { label: 'T1 Maximum Decimal Odds', value: cfg.moneyline.maxT1DecimalOdds.toFixed(2) },
          ].map((item) => (
            <div key={item.label} className="card-sm flex-between">
              <span style={{ fontSize: '0.85rem', color: '#e2e8f0' }}>{item.label}</span>
              <span className="mono-val" style={{ fontWeight: 700, color: 'var(--blue-lt)' }}>{item.value}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="O/U v2.3 Parameters">
        <div className="grid-2">
          {[
            { label: 'Offense Baseline RPG', value: cfg.ou.offenseBaseline },
            { label: 'Offense Weight', value: cfg.ou.offenseWeight },
            { label: 'Pitching Weight', value: cfg.ou.pitchingWeight },
            { label: 'Park Weight', value: cfg.ou.parkWeight },
            { label: 'Clamp Range', value: `±${cfg.ou.clampMax}` },
            { label: 'Strong Gap Min', value: `±${cfg.ou.strongGapMin}` },
            { label: 'Risky Gap Min', value: `±${cfg.ou.riskyGapMin}` },
            { label: 'Min Selected Price', value: cfg.ou.minSelectedPrice },
          ].map((item) => (
            <div key={item.label} className="card-sm flex-between">
              <span style={{ fontSize: '0.85rem', color: '#e2e8f0' }}>{item.label}</span>
              <span className="mono-val" style={{ fontWeight: 700, color: 'var(--blue-lt)' }}>{item.value}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Freshness Windows">
        <div className="grid-2">
          {[
            { label: 'Team Stats Stale After', value: cfg.moneyline.teamStatsStaleHours + 'h' },
            { label: 'Bullpen Data Stale After', value: cfg.moneyline.bullpenStaleHours + 'h' },
            { label: 'Odds Stale After', value: cfg.moneyline.oddsStaleHours + 'h' },
          ].map((item) => (
            <div key={item.label} className="card-sm flex-between">
              <span style={{ fontSize: '0.85rem', color: '#e2e8f0' }}>{item.label}</span>
              <span className="mono-val" style={{ fontWeight: 700, color: 'var(--amber-lt)' }}>{item.value}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Config Version History">
        {loading ? (
          <div className="muted" style={{ padding: '1rem' }} aria-live="polite">Loading…</div>
        ) : configs.length === 0 ? (
          <div className="muted card-sm">No config versions in database yet. Run seed to create default.</div>
        ) : (
          <table className="data-table" aria-label="Config version history">
            <thead><tr><th>Model</th><th>Version</th><th>Active</th><th>Created</th><th>By</th></tr></thead>
            <tbody>
              {configs.map((c: any) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.modelId}</td>
                  <td className="mono-val">{c.semver}</td>
                  <td>{c.isActive ? <span style={{ color: 'var(--green-lt)' }}>✓ Active</span> : <span className="muted">—</span>}</td>
                  <td style={{ fontSize: '0.8rem' }}>{new Date(c.createdAt).toLocaleString()}</td>
                  <td className="muted" style={{ fontSize: '0.8rem' }}>{c.createdBy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Environment">
        <div className="card-sm">
          <div className="flex-between" style={{ marginBottom: '0.5rem' }}>
            <span className="muted">Default Timezone</span>
            <span className="mono-val">Asia/Jakarta (WIB)</span>
          </div>
          <div className="flex-between" style={{ marginBottom: '0.5rem' }}>
            <span className="muted">Odds Provider</span>
            <span className="mono-val" style={{ color: 'var(--amber-lt)' }}>
              {process.env.NEXT_PUBLIC_ODDS_STATUS ?? 'NOT CONFIGURED — use manual import'}
            </span>
          </div>
          <div className="flex-between">
            <span className="muted">Database</span>
            <span className="mono-val">SQLite (demo) — set DATABASE_URL for PostgreSQL</span>
          </div>
        </div>
      </Section>
    </div>
  );
}
