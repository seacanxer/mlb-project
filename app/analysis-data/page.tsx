'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { formatWIB, mlbScheduleDate } from '@/lib/utils/timezone';

type CoverageStatus = 'ok' | 'missing' | 'stale' | 'unconfirmed' | 'fallback' | 'partial' | 'pending';

const DEFAULT_DATE = mlbScheduleDate();

const STATUS_STYLE: Record<CoverageStatus, { label: string; icon: string; color: string; bg: string; border: string }> = {
  ok: { label: 'OK', icon: '✓', color: 'var(--green-lt)', bg: 'rgba(22,163,74,0.12)', border: 'rgba(22,163,74,0.3)' },
  missing: { label: 'MISSING', icon: '✕', color: 'var(--red-lt)', bg: 'rgba(220,38,38,0.12)', border: 'rgba(220,38,38,0.3)' },
  stale: { label: 'STALE', icon: '!', color: 'var(--red-lt)', bg: 'rgba(220,38,38,0.12)', border: 'rgba(220,38,38,0.3)' },
  unconfirmed: { label: 'UNCONFIRMED', icon: '?', color: 'var(--amber-lt)', bg: 'rgba(215,119,6,0.12)', border: 'rgba(215,119,6,0.3)' },
  fallback: { label: 'FALLBACK', icon: '!', color: 'var(--amber-lt)', bg: 'rgba(215,119,6,0.12)', border: 'rgba(215,119,6,0.3)' },
  partial: { label: 'PARTIAL', icon: '~', color: 'var(--amber-lt)', bg: 'rgba(215,119,6,0.12)', border: 'rgba(215,119,6,0.3)' },
  pending: { label: 'PENDING', icon: '…', color: 'var(--muted)', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.25)' },
};

function StatusChip({ status }: { status: CoverageStatus }) {
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.missing;
  return (
    <span
      className="chip"
      style={{ color: style.color, background: style.bg, border: `1px solid ${style.border}`, fontSize: '0.62rem', padding: '0.12rem 0.4rem' }}
      aria-label={`Data status: ${style.label}`}
    >
      {style.icon} {style.label}
    </span>
  );
}

function InputCell({ status, lines }: { status: CoverageStatus; lines: ReactNode[] }) {
  return (
    <div style={{ minWidth: 130 }}>
      <StatusChip status={status} />
      <div style={{ marginTop: '0.35rem', fontSize: '0.72rem', lineHeight: 1.55 }}>
        {lines.map((line, index) => <div key={index}>{line}</div>)}
      </div>
    </div>
  );
}

function n(value: unknown, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function coverageState(field: any): CoverageStatus {
  if (field.missing > 0) return 'missing';
  if (field.stale > 0) return 'stale';
  if (field.unconfirmed > 0) return 'unconfirmed';
  if (field.partial > 0) return 'partial';
  if (field.fallback > 0) return 'fallback';
  if (field.pending > 0) return 'pending';
  return 'ok';
}

export default function AnalysisDataPage() {
  const [date, setDate] = useState(DEFAULT_DATE);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [refreshStatus, setRefreshStatus] = useState('');
  const [onlyBlocked, setOnlyBlocked] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/analysis-data?date=${encodeURIComponent(date)}`, { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? `Failed to load analysis data (${response.status})`);
      setData(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to load analysis data.');
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const refreshAndScrape = async () => {
    setRefreshing(true);
    setError('');
    setRefreshStatus('');
    try {
      const response = await fetch('/api/analysis-data/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date }),
      });
      const payload = await response.json();
      if (!response.ok && response.status !== 207) {
        throw new Error(payload.error ?? payload.slate?.errors?.[0]?.message ?? `Refresh failed (${response.status})`);
      }
      const slate = payload.slate;
      setRefreshStatus(
        `Scraped ${slate.scheduleGames} games, ${slate.pitcherSnapshots} pitcher, `
        + `${slate.teamSnapshots} team, ${slate.bullpenSnapshots} bullpen, and ${slate.oddsSnapshots} odds snapshots. `
        + `Repaired ${slate.starterFallbacks ?? 0} missing starter(s); ${slate.missingStarterSides ?? 0} starter side(s) remain TBD.`
      );
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to run scraper/worker.');
    } finally {
      setRefreshing(false);
    }
  };

  const visibleGames = useMemo(() => {
    const games = data?.games ?? [];
    return onlyBlocked ? games.filter((game: any) => !game.readyForAnalysis) : games;
  }, [data, onlyBlocked]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analysis Data</h1>
          <p className="page-subtitle">Input coverage for every matchup and every active model field · MLB slate date (US/ET)</p>
        </div>
        <div className="flex-row">
          <input
            type="date"
            className="input"
            style={{ width: 'auto' }}
            value={date}
            onChange={(event) => setDate(event.target.value)}
            aria-label="Analysis data date"
          />
          <button className="btn btn-primary" onClick={refreshAndScrape} disabled={loading || refreshing} aria-busy={refreshing}>
            {refreshing ? '⏳ Scraping…' : '↻ Refresh & Scrape'}
          </button>
        </div>
      </div>

      {error && <div role="alert" className="gate-pill" style={{ marginBottom: '1rem' }}>⚠ {error}</div>}
      {refreshStatus && (
        <div role="status" style={{ color: 'var(--green-lt)', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(22,163,74,0.08)', borderRadius: 6 }}>
          ✓ {refreshStatus}
        </div>
      )}

      {loading && !data ? (
        <div className="muted" style={{ padding: '3rem', textAlign: 'center' }}>Loading input coverage…</div>
      ) : data ? (
        <>
          <section aria-labelledby="coverage-summary-heading">
            <h2 id="coverage-summary-heading" style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.75rem' }}>Overall Coverage</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
              {[
                { label: 'Total Matches', value: data.summary.totalGames, color: 'var(--blue-lt)' },
                { label: 'Ready for Analysis', value: data.summary.readyForAnalysis, color: 'var(--green-lt)' },
                { label: 'Blocked Matches', value: data.summary.blockedMatches, color: data.summary.blockedMatches ? 'var(--red-lt)' : 'var(--green-lt)' },
                { label: 'Required Fields Missing', value: data.summary.requiredMissingFields, color: data.summary.requiredMissingFields ? 'var(--red-lt)' : 'var(--green-lt)' },
                { label: 'Fallback / Partial Fields', value: data.summary.qualityFields ?? data.summary.fallbackFields, color: (data.summary.qualityFields ?? data.summary.fallbackFields) ? 'var(--amber-lt)' : 'var(--green-lt)' },
                { label: 'Optional Fields Missing', value: data.summary.optionalMissingFields, color: data.summary.optionalMissingFields ? 'var(--amber-lt)' : 'var(--green-lt)' },
              ].map((item) => (
                <div className="card-sm" key={item.label} style={{ textAlign: 'center' }}>
                  <div className="mono-val" style={{ fontSize: '1.65rem', fontWeight: 700, color: item.color }}>{item.value}</div>
                  <div className="muted" style={{ fontSize: '0.75rem' }}>{item.label}</div>
                </div>
              ))}
            </div>
          </section>

          <section aria-labelledby="field-coverage-heading">
            <div className="flex-between" style={{ marginBottom: '0.75rem', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h2 id="field-coverage-heading" style={{ fontSize: '0.95rem', fontWeight: 700 }}>Field Coverage</h2>
                <p className="muted" style={{ fontSize: '0.75rem' }}>Missing, stale, or unconfirmed required fields block publication. Partial and fallback inputs remain visible with confidence safeguards.</p>
              </div>
              <div className="flex-row" aria-label="Data status legend" style={{ flexWrap: 'wrap' }}>
                {(['ok', 'missing', 'stale', 'unconfirmed', 'fallback', 'partial', 'pending'] as CoverageStatus[]).map((status) => (
                  <StatusChip key={status} status={status} />
                ))}
              </div>
            </div>
            <div className="card" style={{ padding: 0, overflowX: 'auto', marginBottom: '1.5rem' }}>
              <table className="data-table" aria-label="Overall field coverage">
                <thead>
                  <tr>
                    <th>Input Field</th>
                    <th>Used By</th>
                    <th>Required</th>
                    <th>Status</th>
                    <th>Usable</th>
                    <th>Missing</th>
                    <th>Stale / Unconfirmed / Partial</th>
                    <th>Fallback / Pending</th>
                  </tr>
                </thead>
                <tbody>
                  {data.fieldCoverage.map((field: any) => (
                    <tr key={field.key}>
                      <td style={{ fontWeight: 600 }}>{field.label}</td>
                      <td className="muted">{field.usedBy}</td>
                      <td>{field.required ? <span style={{ color: 'var(--green-lt)' }}>Yes</span> : <span className="muted">No</span>}</td>
                      <td><StatusChip status={coverageState(field)} /></td>
                      <td className="mono-val">{field.ok + field.fallback + field.partial} / {data.summary.totalGames}</td>
                      <td className="mono-val" style={{ color: field.missing ? 'var(--red-lt)' : undefined }}>{field.missing}</td>
                      <td className="mono-val" style={{ color: field.stale + field.unconfirmed + field.partial ? 'var(--amber-lt)' : undefined }}>{field.stale + field.unconfirmed + field.partial}</td>
                      <td className="mono-val" style={{ color: field.fallback ? 'var(--amber-lt)' : undefined }}>{field.fallback} / {field.pending}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="match-input-heading">
            <div className="flex-between" style={{ marginBottom: '0.75rem', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h2 id="match-input-heading" style={{ fontSize: '0.95rem', fontWeight: 700 }}>Match Input Matrix</h2>
                <p className="muted" style={{ fontSize: '0.75rem' }}>{visibleGames.length} of {data.summary.totalGames} matches shown · A = away, H = home</p>
              </div>
              <button className={`btn btn-sm ${onlyBlocked ? 'btn-danger' : 'btn-ghost'}`} onClick={() => setOnlyBlocked((value) => !value)}>
                {onlyBlocked ? 'Showing Blocked Only' : 'Show Blocked Only'}
              </button>
            </div>

            {visibleGames.length === 0 ? (
              <div className="card muted" style={{ textAlign: 'center' }}>No matching games for this filter.</div>
            ) : (
              <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
                <table className="data-table" aria-label="Per-match analysis inputs" style={{ minWidth: 1900 }}>
                  <thead>
                    <tr>
                      <th>Match / Schedule</th>
                      <th>Starters</th>
                      <th>ERA / WHIP / IP</th>
                      <th>Pitcher L5</th>
                      <th>Offense / Form</th>
                      <th>ML Odds</th>
                      <th>Total / O-U Odds</th>
                      <th>Bullpen</th>
                      <th>Park Factor</th>
                      <th>Final Score</th>
                      <th>Missing Required</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleGames.map((game: any) => {
                      const d = game.data;
                      return (
                        <tr key={game.gameId}>
                          <td style={{ minWidth: 210 }}>
                            <Link href={`/games/${game.gameId}`} style={{ fontWeight: 650 }}>
                              {game.awayTeam.name} @ {game.homeTeam.name}
                            </Link>
                            <div className="muted" style={{ fontSize: '0.72rem' }}>{formatWIB(game.startTimeUtc, 'dd/MM HH:mm')} · {d.schedule.gameStatus}</div>
                            <div className="muted" style={{ fontSize: '0.7rem' }}>{d.schedule.venue}</div>
                          </td>
                          <td>
                            <InputCell status={d.starters.status} lines={[
                              `A: ${d.starters.away?.name ?? 'MISSING'} (${d.starters.away?.confirmation ?? '—'})`,
                              `H: ${d.starters.home?.name ?? 'MISSING'} (${d.starters.home?.confirmation ?? '—'})`,
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.pitching.status} lines={[
                              `A: ERA ${n(d.pitching.away?.era)} · WHIP ${n(d.pitching.away?.whip)} · IP ${n(d.pitching.away?.inningsPitched, 1)}`,
                              `H: ERA ${n(d.pitching.home?.era)} · WHIP ${n(d.pitching.home?.whip)} · IP ${n(d.pitching.home?.inningsPitched, 1)}`,
                              ...(d.pitching.status === 'fallback' ? [
                                `Source: ${d.pitching.away?.provider?.includes('minor-league-fallback') || d.pitching.home?.provider?.includes('minor-league-fallback') ? 'Official MiLB fallback (not MLB-equivalent)' : 'Fallback'}`,
                              ] : []),
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.lastFive.status} lines={[
                              `A: ${d.lastFive.awayCount}/5 starts${d.lastFive.awayLevelFallback ? ' · official MiLB fallback' : ''}`,
                              `H: ${d.lastFive.homeCount}/5 starts${d.lastFive.homeLevelFallback ? ' · official MiLB fallback' : ''}`,
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.offense.status} lines={[
                              `A: AVG ${n(d.offense.away?.avg, 3)} · OPS ${n(d.offense.away?.ops, 3)} · RPG ${n(d.offense.away?.runsPerGame)}`,
                              `H: AVG ${n(d.offense.home?.avg, 3)} · OPS ${n(d.offense.home?.ops, 3)} · RPG ${n(d.offense.home?.runsPerGame)}`,
                              `L10 A/H: ${d.offense.away?.last10 ?? '—'} / ${d.offense.home?.last10 ?? '—'}`,
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.moneyline.status} lines={[
                              `A: ${n(d.moneyline.away)}`,
                              `H: ${n(d.moneyline.home)}`,
                              d.moneyline.provider ?? 'No provider',
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.totals.status} lines={[
                              `Line: ${n(d.totals.line, 1)}`,
                              `Over: ${n(d.totals.over)} · Under: ${n(d.totals.under)}`,
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.bullpen.status} lines={[
                              `A: ERA ${n(d.bullpen.away?.era)} · WHIP ${n(d.bullpen.away?.whip)}`,
                              `H: ERA ${n(d.bullpen.home?.era)} · WHIP ${n(d.bullpen.home?.whip)}`,
                              `${d.bullpen.away?.relievers ?? '—'} / ${d.bullpen.home?.relievers ?? '—'} relievers (A/H)`,
                              'Required by O/U v3 staff-run model',
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.park.status} lines={[
                              `Factor: ${n(d.park.factor, 3)}`,
                              d.park.source ?? 'No source',
                            ]} />
                          </td>
                          <td>
                            <InputCell status={d.result.status} lines={[
                              d.result.status === 'pending' ? 'Game not final' : `A ${d.result.awayScore ?? '—'} - H ${d.result.homeScore ?? '—'}`,
                            ]} />
                          </td>
                          <td style={{ minWidth: 180 }}>
                            {!game.readyForAnalysis ? (
                              <>
                                <StatusChip status={game.blockingIssues?.[0]?.status ?? 'missing'} />
                                <div style={{ marginTop: '0.35rem', fontSize: '0.7rem', color: 'var(--amber-lt)' }}>
                                  {(game.blockingIssues ?? []).map((issue: any) => `${issue.label}: ${issue.status}`).join(', ')}
                                </div>
                              </>
                            ) : (
                              <>
                                <StatusChip status={game.qualityIssues.length ? 'fallback' : 'ok'} />
                                <div className="muted" style={{ marginTop: '0.35rem', fontSize: '0.7rem' }}>
                                  {game.qualityIssues.length ? game.qualityIssues.join(', ') : 'All required inputs usable'}
                                </div>
                              </>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="muted" style={{ fontSize: '0.72rem', marginTop: '1rem' }}>
            Generated {formatWIB(data.generatedAt, 'dd/MM/yyyy HH:mm:ss')} WIB. Fallback data remains usable but should be replaced by an authoritative source before production decisions.
          </p>
        </>
      ) : null}
    </div>
  );
}
