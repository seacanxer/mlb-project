'use client';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { FinalStateChip, ExperimentalBadge } from '@/components/FinalStateChip';
import { formatWIB, mlbScheduleDate } from '@/lib/utils/timezone';

const DEFAULT_DATE = mlbScheduleDate();

function getLatestRun(runs: any[], modelId: string) {
  return runs?.find((r: any) => r.modelId === modelId && !r.isInvalidated);
}

function isActionableRun(run: any) {
  return ['T1', 'OVER_STRONG_GAP', 'UNDER_STRONG_GAP']
    .includes(run?.finalState);
}

function lockSideForRun(run: any): string {
  const output = JSON.parse(run.outputJson);
  if (run.modelId.startsWith('OU_')) return output.selectedSide;
  return output.candidate === 'away' ? 'away' : 'home';
}

function OddsAge({ retrievedAt }: { retrievedAt?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  if (!retrievedAt) return <span className="muted">—</span>;
  const mins = Math.max(0, Math.floor((now - new Date(retrievedAt).getTime()) / 60000));
  const color = mins > 240 ? 'var(--red-lt)' : mins > 60 ? 'var(--amber-lt)' : 'var(--green-lt)';
  return (
    <span
      style={{ color, fontSize: '0.75rem' }}
      title="Age since this odds snapshot was fetched. The unofficial 1xBit feed does not expose a bookmaker quote-update timestamp."
    >
      {mins}m ago
    </span>
  );
}

export default function DailySlate() {
  const [date, setDate] = useState(DEFAULT_DATE);
  const [games, setGames] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [refreshStatus, setRefreshStatus] = useState('');
  const [locking, setLocking] = useState('');

  const fetchSlate = useCallback(async (d: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/slates/${d}`);
      const text = await res.text();
      let data: any;
      try {
        data = JSON.parse(text);
      } catch {
        setError(`Server error (${res.status})`);
        return;
      }
      if (!res.ok) {
        setError(data.error || 'Failed to load slate.');
        return;
      }
      setGames(data.games ?? []);
    } catch {
      setError('Failed to load slate.');
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshSlate = async () => {
    setRefreshing(true);
    setError('');
    setRefreshStatus('');
    try {
      const res = await fetch(`/api/slates/${date}/refresh`, { method: 'POST' });
      const text = await res.text();
      let data: any;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(`Server error (${res.status})`);
      }
      if (!res.ok) {
        throw new Error(data.error ?? data.errors?.[0]?.message ?? `Refresh failed (${res.status})`);
      }
      const warningText = data.warnings?.length ? ` Warnings: ${data.warnings.length}.` : '';
      const scheduleText = data.scheduleSource === 'cache'
        ? ' MLB schedule API unavailable; cached schedule was used.'
        : '';
      const oddsError = data.errors?.find((item: any) => String(item.scope).startsWith('odds:'));
      setRefreshStatus(
        `Loaded ${data.scheduleGames} games, ${data.pitcherSnapshots} pitcher snapshots, ` +
        `${data.teamSnapshots} team snapshots, and ${data.oddsSnapshots} fresh odds snapshots.` +
        `${scheduleText}${warningText}`
      );
      await fetchSlate(date);
      if (data.oddsSnapshots === 0 && oddsError) {
        setError(`Schedule loaded, but odds refresh failed: ${oddsError.message}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh slate.');
    } finally {
      setRefreshing(false);
    }
  };

  const loadNextSlate = async () => {
    setRefreshing(true);
    setError('');
    setRefreshStatus('');
    try {
      const res = await fetch(`/api/slates/next/refresh?from=${date}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `Next-slate lookup failed (${res.status})`);
      setRefreshStatus(`Loaded the next MLB slate: ${data.scheduleGames} games on ${data.date}.`);
      if (data.date === date) await fetchSlate(date);
      else setDate(data.date);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to find the next MLB slate.');
    } finally {
      setRefreshing(false);
    }
  };

  const lockRun = async (run: any) => {
    setLocking(run.id);
    setError('');
    try {
      const res = await fetch(`/api/model-runs/${run.id}/lock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selectedSide: lockSideForRun(run) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Could not lock pick');
      setRefreshStatus('Pick locked. It will be graded automatically when the official final score is fetched.');
      await fetchSlate(date);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not lock pick');
    } finally {
      setLocking('');
    }
  };

  const lockAllPicks = async () => {
    setLocking('all');
    setError('');
    try {
      const res = await fetch(`/api/slates/${date}/lock`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Could not lock slate picks');
      setRefreshStatus(
        `Locked ${data.locked} pick(s); ${data.alreadyLocked} already locked. ` +
        'Official final scores will auto-grade WIN/LOSS/PUSH.'
      );
      await fetchSlate(date);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not lock slate picks');
    } finally {
      setLocking('');
    }
  };

  useEffect(() => { fetchSlate(date); }, [date, fetchSlate]);

  const wibGameDates = [...new Set(
    games
      .filter((game: any) => game.startTimeUtc)
      .map((game: any) => formatWIB(game.startTimeUtc, 'yyyy-MM-dd'))
  )];
  const wibDateLabel = wibGameDates.length > 0
    ? wibGameDates.map((value) => formatWIB(`${value}T00:00:00+07:00`, 'dd/MM/yyyy')).join(', ')
    : '—';

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Daily Slate</h1>
          <p className="page-subtitle">
            MLB slate date (US/ET): {date} · Jadwal WIB: {wibDateLabel}
          </p>
        </div>
        <div className="flex-row">
          <label style={{ display: 'grid', gap: '0.2rem' }}>
            <span className="muted" style={{ fontSize: '0.7rem' }}>MLB slate date (US/ET)</span>
            <input
              id="slate-date"
              type="date"
              className="input"
              style={{ width: 'auto' }}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-label="Official MLB slate date in US Eastern Time"
            />
          </label>
          <button
            id="btn-refresh-slate"
            className="btn btn-primary"
            onClick={refreshSlate}
            disabled={refreshing}
            aria-busy={refreshing}
          >
            {refreshing ? '⏳ Refreshing…' : '↻ Refresh'}
          </button>
          <button
            className="btn btn-ghost"
            onClick={lockAllPicks}
            disabled={!!locking || refreshing || games.length === 0}
            aria-busy={locking === 'all'}
          >
            {locking === 'all' ? '⏳ Locking…' : '🔒 Lock All Picks'}
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" style={{ color: 'var(--red-lt)', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(220,38,38,0.08)', borderRadius: 6 }}>
          ⚠ {error}
        </div>
      )}

      {refreshStatus && (
        <div role="status" style={{ color: 'var(--green-lt)', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(22,163,74,0.08)', borderRadius: 6 }}>
          ✓ {refreshStatus}
        </div>
      )}

      {loading ? (
        <div className="muted" style={{ padding: '2rem', textAlign: 'center' }} aria-live="polite">
          Loading MLB slate for {date} (US/ET)…
        </div>
      ) : games.length === 0 ? (
        <div style={{ padding: '3rem 0', textAlign: 'center' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>⚾</div>
          <p className="muted">No games found for MLB slate {date} (US/ET).</p>
          <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            Try refreshing to load from MLB Stats API, or select a different date.
          </p>
          <button id="btn-refresh-empty" className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={refreshSlate}>
            ↻ Load from MLB API
          </button>
          <button className="btn btn-ghost" style={{ marginTop: '1rem', marginLeft: '0.5rem' }} onClick={loadNextSlate} disabled={refreshing}>
            Find next MLB slate →
          </button>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" aria-label="Daily slate">
            <thead>
              <tr>
                <th>Game</th>
                <th>Start Date/Time (WIB)</th>
                <th>Starters</th>
                <th>Odds Fetch Age</th>
                <th>ML Score</th>
                <th>ML Signal</th>
                <th>ML Pick</th>
                <th>O/U Line</th>
                <th>O/U Gap</th>
                <th>O/U Signal</th>
                <th>Pick Lock</th>
                <th>Score</th>
                <th>⚠</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {games.map((game: any) => {
                const mlRun = getLatestRun(game.modelRuns, 'ML_COMBO_V2');
                const ouRun = getLatestRun(game.modelRuns, 'OU_UNIFIED')
                  ?? getLatestRun(game.modelRuns, 'OU_V3')
                  ?? getLatestRun(game.modelRuns, 'OU_V2_3');
                const market = game.marketSnapshots?.[0];
                const mlOut = mlRun ? JSON.parse(mlRun.outputJson) : null;
                const ouOut = ouRun ? JSON.parse(ouRun.outputJson) : null;
                const warnCount = (mlRun?.warnings?.length ?? 0) + (ouRun?.warnings?.length ?? 0);
                const homeStarter = game.probableStarterObservations?.find((starter: any) => starter.side === 'home');
                const awayStarter = game.probableStarterObservations?.find((starter: any) => starter.side === 'away');
                const mlActionable = mlRun?.finalState === 'T1' || mlRun?.finalState === 'T2';
                const mlOfficial = mlRun?.finalState === 'T1';
                const mlLocked = game.modelRuns?.some((run: any) =>
                  run.modelId === 'ML_COMBO_V2' && run.forecasts?.length > 0
                );
                const ouLocked = game.modelRuns?.some((run: any) =>
                  run.modelId === ouRun?.modelId && run.forecasts?.length > 0
                );
                const mlPickTeam = mlOut?.candidateTeamName
                  ?? (mlOut?.candidate === 'away' ? game.awayTeam?.name : game.homeTeam?.name);
                const mlPickOdds = mlOut?.candidateDecimalOdds
                  ?? (mlOut?.candidate === 'away' ? market?.moneylineAway : market?.moneylineHome);

                return (
                  <tr key={game.id}>
                    <td>
                      <div style={{ fontWeight: 600, color: '#e2e8f0' }}>
                        {game.awayTeam?.name ?? game.awayTeamId} <span className="muted">@</span> {game.homeTeam?.name ?? game.homeTeamId}
                      </div>
                      <div className="muted" style={{ fontSize: '0.75rem' }}>{game.venue?.name}</div>
                    </td>
                    <td className="mono-val" style={{ fontSize: '0.8rem' }}>
                      {game.startTimeUtc ? formatWIB(game.startTimeUtc, 'dd/MM HH:mm') : '—'}
                    </td>
                    <td style={{ fontSize: '0.8rem' }}>
                      <div>{awayStarter?.person?.fullName ?? 'TBD'}</div>
                      <div className="muted">vs {homeStarter?.person?.fullName ?? 'TBD'}</div>
                    </td>
                    <td><OddsAge retrievedAt={market?.retrievedAt} /></td>
                    <td>
                      {mlOut ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span className="mono-val" style={{ fontSize: '0.85rem' }}>{mlOut.rawScore?.toFixed(0) ?? '—'}</span>
                          <div className="score-bar" style={{ width: 60 }}>
                            <div
                              className="score-bar-fill"
                              style={{
                                width: `${Math.min(mlOut.rawScore ?? 0, 100)}%`,
                                background: (mlOut.rawScore ?? 0) >= 70 ? 'var(--green)' : (mlOut.rawScore ?? 0) >= 55 ? 'var(--blue)' : 'var(--muted)',
                              }}
                            />
                          </div>
                        </div>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      {mlRun ? <FinalStateChip state={mlRun.finalState} size="sm" /> : <span className="muted">—</span>}
                    </td>
                    <td>
                      {mlActionable ? (
                        <div aria-label={`Moneyline pick: ${mlPickTeam} at decimal odds ${mlPickOdds}`}>
                          <div style={{ fontWeight: 600, color: 'var(--green-lt)', fontSize: '0.8rem' }}>{mlPickTeam}</div>
                          <div className="mono-val muted" style={{ fontSize: '0.72rem' }}>
                            @{mlPickOdds != null ? Number(mlPickOdds).toFixed(2) : '—'}
                          </div>
                        </div>
                      ) : (
                        <span className="muted" style={{ fontSize: '0.75rem', fontWeight: 600 }}>NO PICK</span>
                      )}
                    </td>
                    <td className="mono-val">
                      {market?.totalLine ?? <span className="muted">—</span>}
                    </td>
                    <td className="mono-val" style={{ color: (ouOut?.gap ?? 0) > 0 ? 'var(--green-lt)' : (ouOut?.gap ?? 0) < 0 ? 'var(--blue-lt)' : 'inherit' }}>
                      {ouOut?.gap != null ? (ouOut.gap > 0 ? '+' : '') + ouOut.gap.toFixed(2) : <span className="muted">—</span>}
                    </td>
                    <td>
                      {ouRun ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <FinalStateChip state={ouRun.finalState} size="sm" />
                          <ExperimentalBadge />
                        </div>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <div style={{ display: 'grid', gap: '0.3rem', minWidth: 92 }}>
                        {mlOfficial && (
                          mlLocked ? <span style={{ color: 'var(--green-lt)', fontSize: '0.72rem' }}>🔒 ML locked</span> : (
                            <button className="btn btn-ghost btn-sm" disabled={!!locking} onClick={() => lockRun(mlRun)}>
                              {locking === mlRun.id ? '…' : 'Lock ML'}
                            </button>
                          )
                        )}
                        {isActionableRun(ouRun) && (
                          ouLocked ? <span style={{ color: 'var(--green-lt)', fontSize: '0.72rem' }}>🔒 O/U locked</span> : (
                            <button className="btn btn-ghost btn-sm" disabled={!!locking} onClick={() => lockRun(ouRun)}>
                              {locking === ouRun.id ? '…' : 'Lock O/U'}
                            </button>
                          )
                        )}
                        {!mlOfficial && !isActionableRun(ouRun) && <span className="muted">Watchlist</span>}
                      </div>
                    </td>
                    <td>
                      {game.gameResult ? (
                        <span
                          className="mono-val"
                          style={{ fontWeight: 700, color: 'var(--green-lt)', fontSize: '0.85rem' }}
                          aria-label={`Final score: ${game.awayTeam?.name ?? 'Away'} ${game.gameResult.awayScore} - ${game.homeTeam?.name ?? 'Home'} ${game.gameResult.homeScore}`}
                        >
                          {game.gameResult.awayScore} – {game.gameResult.homeScore}
                        </span>
                      ) : game.status === 'in_progress' ? (
                        <span style={{ color: 'var(--amber-lt)', fontWeight: 700, fontSize: '0.78rem' }}>🔴 LIVE</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {warnCount > 0 ? (
                        <span className="warning-pill" aria-label={`${warnCount} warnings`}>⚠ {warnCount}</span>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <Link
                        href={`/games/${game.id}`}
                        className="btn btn-ghost btn-sm"
                        id={`link-detail-${game.id}`}
                        aria-label={`Match detail for ${game.awayTeam?.name} @ ${game.homeTeam?.name}`}
                      >
                        Detail →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: '0.75rem', marginTop: '1rem' }}>
            T1 is the official ML tier; T2 remains a visible watchlist signal. Formula scores are not win probabilities. Only O/U STRONG can be locked; LEAN and RISKY remain shadow/watchlist while totals calibration is incomplete.
          </p>
        </div>
      )}
    </div>
  );
}
