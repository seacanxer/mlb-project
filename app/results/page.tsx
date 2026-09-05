'use client';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { FinalStateChip } from '@/components/FinalStateChip';
import { formatWIB, mlbScheduleDate } from '@/lib/utils/timezone';

const DEFAULT_DATE = mlbScheduleDate();

// ─── helpers ────────────────────────────────────────────────────────────────

function getResultRun(runs: any[], modelId: string) {
  const matching = runs?.filter((r: any) => r.modelId === modelId && !r.isInvalidated) ?? [];
  return matching.find((r: any) => r.forecasts?.length > 0) ?? matching[0];
}

function getOuResultRun(runs: any[]) {
  return getResultRun(runs, 'OU_UNIFIED')
    ?? getResultRun(runs, 'OU_V3')
    ?? getResultRun(runs, 'OU_V2_3');
}

function getLockedForecast(run: any) {
  return run?.forecasts?.find((f: any) => f != null) ?? null;
}

function outcomeLabel(outcome?: string) {
  if (!outcome || outcome === 'pending') return null;
  return outcome.toUpperCase();
}

function outcomeColor(outcome?: string) {
  switch (outcome) {
    case 'win':  return 'var(--green-lt)';
    case 'loss': return 'var(--red-lt)';
    case 'push': return 'var(--amber-lt)';
    default:     return 'var(--muted)';
  }
}

function outcomeBg(outcome?: string) {
  switch (outcome) {
    case 'win':  return 'rgba(34,197,94,0.12)';
    case 'loss': return 'rgba(220,38,38,0.12)';
    case 'push': return 'rgba(251,191,36,0.12)';
    default:     return 'transparent';
  }
}

type LiveScore = {
  gameId: string;
  status: string;
  inning?: number;
  inningHalf?: string;
  homeScore: number | null;
  awayScore: number | null;
};

// ─── sub-components ─────────────────────────────────────────────────────────

function ScoreCell({
  game,
  live,
}: {
  game: any;
  live?: LiveScore;
}) {
  const result = game.gameResult;

  if (result) {
    return (
      <div style={{ textAlign: 'center' }}>
        <div
          className="mono-val"
          style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--green-lt)', letterSpacing: '0.04em' }}
          aria-label={`Final: Away ${result.awayScore} Home ${result.homeScore}`}
        >
          {result.awayScore} <span className="muted" style={{ fontWeight: 400 }}>–</span> {result.homeScore}
        </div>
        <div className="muted" style={{ fontSize: '0.68rem', marginTop: '0.15rem' }}>FINAL</div>
      </div>
    );
  }

  if (live && (live.status === 'in_progress' || live.homeScore !== null)) {
    const half = live.inningHalf === 'top' ? '▲' : '▼';
    return (
      <div style={{ textAlign: 'center' }}>
        <div className="mono-val" style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--amber-lt)' }}>
          {live.awayScore ?? 0} <span className="muted" style={{ fontWeight: 400 }}>–</span> {live.homeScore ?? 0}
        </div>
        {live.inning != null && (
          <div style={{ fontSize: '0.68rem', color: 'var(--amber-lt)', marginTop: '0.15rem' }}>
            🔴 {half} {live.inning}
          </div>
        )}
      </div>
    );
  }

  if (live?.status === 'postponed') {
    return <span className="muted" style={{ fontSize: '0.75rem' }}>PPD</span>;
  }
  if (live?.status === 'cancelled') {
    return <span className="muted" style={{ fontSize: '0.75rem' }}>CXL</span>;
  }

  return <span className="muted">—</span>;
}

function SettleCell({ forecast, label }: { forecast: any | null; label: string }) {
  if (!forecast) return <span className="muted" style={{ fontSize: '0.75rem' }}>No lock</span>;

  const outcome = forecast.settlement?.outcome;
  const lbl = outcomeLabel(outcome);

  return (
    <div>
      <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '0.2rem' }}>{label}</div>
      {lbl ? (
        <span
          style={{
            display: 'inline-block',
            padding: '0.18rem 0.55rem',
            borderRadius: 4,
            background: outcomeBg(outcome),
            color: outcomeColor(outcome),
            fontWeight: 700,
            fontSize: '0.78rem',
            letterSpacing: '0.04em',
          }}
        >
          {lbl}
        </span>
      ) : (
        <span className="muted" style={{ fontSize: '0.75rem' }}>Pending</span>
      )}
    </div>
  );
}

// ─── main page ───────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const [date, setDate] = useState(DEFAULT_DATE);
  const [games, setGames] = useState<any[]>([]);
  const [liveMap, setLiveMap] = useState<Record<string, LiveScore>>({});
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [grading, setGrading] = useState(false);
  const [locking, setLocking] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [lastLiveFetch, setLastLiveFetch] = useState<Date | null>(null);

  // ── fetch DB results ────────────────────────────────────────────────────
  const fetchResults = useCallback(async (d: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/results?date=${d}`);
      const data = await res.json();
      setGames(data.games ?? []);
    } catch {
      setError('Failed to load results from database.');
    } finally {
      setLoading(false);
    }
  }, []);

  // ── fetch live scores from MLB API ──────────────────────────────────────
  const fetchLiveScores = useCallback(async (d: string, quiet = false) => {
    if (!quiet) setLiveLoading(true);
    try {
      const res = await fetch(`/api/scores/live?date=${d}`);
      const data = await res.json();
      if (data.scores) {
        const map: Record<string, LiveScore> = {};
        for (const s of data.scores) map[s.gameId] = s;
        setLiveMap(map);
        setLastLiveFetch(new Date());
      }
    } catch {
      // silently ignore live score fetch errors
    } finally {
      if (!quiet) setLiveLoading(false);
    }
  }, []);

  // ── fetch final scores + auto-grade forecasts ───────────────────────────
  const fetchFinalScores = async () => {
    setFetching(true);
    setError('');
    setStatus('');
    try {
      const res = await fetch('/api/results/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `Refresh failed (${res.status})`);
      const finalGamesUpdated = data.finalGamesUpdated ?? data.settled?.length ?? 0;
      const forecastsGraded = data.forecastsGraded ?? 0;
      setStatus(
        `✓ Final scores refreshed. ${finalGamesUpdated} game${finalGamesUpdated === 1 ? '' : 's'} updated; ` +
        `${forecastsGraded} forecast${forecastsGraded === 1 ? '' : 's'} graded.`
      );
      await fetchResults(date);
      await fetchLiveScores(date, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch final scores.');
    } finally {
      setFetching(false);
    }
  };

  // ── manually re-grade already-stored results ─────────────────────────────
  const reGrade = async () => {
    setGrading(true);
    setError('');
    setStatus('');
    try {
      const res = await fetch('/api/results/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `Re-grade failed (${res.status})`);
      setStatus(`✓ Re-grade complete. ${data.settled?.length ?? 0} forecast(s) settled.`);
      await fetchResults(date);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Re-grade failed.');
    } finally {
      setGrading(false);
    }
  };

  const lockSlatePicks = async () => {
    setLocking(true);
    setError('');
    setStatus('');
    try {
      const res = await fetch(`/api/slates/${date}/lock`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Lock failed');
      setStatus(`🔒 ${data.locked} pick(s) locked; ${data.alreadyLocked} already locked.`);
      await fetchResults(date);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lock failed.');
    } finally {
      setLocking(false);
    }
  };

  useEffect(() => { fetchResults(date); fetchLiveScores(date); }, [date, fetchResults, fetchLiveScores]);

  // ── auto-poll live scores every 90 s when tab visible ──────────────────
  useEffect(() => {
    const poll = setInterval(() => fetchLiveScores(date, true), 90_000);
    return () => clearInterval(poll);
  }, [date, fetchLiveScores]);

  // ── derived stats ──────────────────────────────────────────────────────
  const totalGames   = games.length;
  const finalGames   = games.filter(g => g.gameResult || g.status === 'final').length;
  const liveGames    = games.filter(g => liveMap[g.id]?.status === 'in_progress').length;
  const pendingGames = totalGames - finalGames - liveGames;

  const allForecasts = games.flatMap(g => {
    const ml = getResultRun(g.modelRuns, 'ML_COMBO_V2');
    const ou = getOuResultRun(g.modelRuns);
    return [getLockedForecast(ml), getLockedForecast(ou)].filter(Boolean);
  });
  const wins   = allForecasts.filter(f => f.settlement?.outcome === 'win').length;
  const losses = allForecasts.filter(f => f.settlement?.outcome === 'loss').length;
  const pushes = allForecasts.filter(f => f.settlement?.outcome === 'push').length;
  const pending = allForecasts.filter(f => !f.settlement).length;

  // ── settlement record: flat one-unit profit and ROI ─────────────────────
  let netUnits = 0, unitsCounted = 0;
  for (const fc of allForecasts as any[]) {
    if (!fc?.settlement) continue;
    if (fc.settlement.outcome === 'void') continue;
    const odds = Number(fc.marketPrice);
    if (!isFinite(odds) || odds <= 1) continue;
    unitsCounted++;
    if (fc.settlement.outcome === 'win') netUnits += odds - 1;
    else if (fc.settlement.outcome === 'loss') netUnits -= 1;
  }
  const settledCount = wins + losses + pushes;
  const winRate = wins + losses > 0 ? wins / (wins + losses) : null;
  const profitLabel = unitsCounted > 0 ? `${netUnits >= 0 ? '+' : ''}${netUnits.toFixed(2)}u` : '—';
  const roiLabel = unitsCounted > 0 ? `${netUnits >= 0 ? '+' : ''}${(netUnits / unitsCounted * 100).toFixed(1)}%` : '—';

  // current streak over settled picks (in game order)
  const orderedSettled = games.flatMap(g => {
    const ml = getResultRun(g.modelRuns, 'ML_COMBO_V2');
    const ou = getOuResultRun(g.modelRuns);
    return [getLockedForecast(ml), getLockedForecast(ou)].filter((f: any) => f?.settlement);
  });
  let streak = 0, streakType: 'win' | 'loss' | null = null;
  for (let i = orderedSettled.length - 1; i >= 0; i--) {
    const o = orderedSettled[i].settlement.outcome;
    if (o !== 'win' && o !== 'loss') continue;
    if (streakType === null) streakType = o;
    if (o === streakType) streak++;
    else break;
  }
  const streakLabel = streakType && streak > 0 ? `${streak} ${streakType === 'win' ? 'W' : 'L'}` : '—';

  const wibDateLabel = games.length > 0 && games[0].startTimeUtc
    ? formatWIB(games[0].startTimeUtc, 'dd/MM/yyyy')
    : '—';

  return (
    <div>
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Results</h1>
          <p className="page-subtitle">
            Skor final, live score &amp; settlement pick · MLB slate {date} (US/ET)
            {games.length > 0 && <span className="muted"> · WIB {wibDateLabel}</span>}
          </p>
        </div>
        <div className="flex-row" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
          <label style={{ display: 'grid', gap: '0.2rem' }}>
            <span className="muted" style={{ fontSize: '0.7rem' }}>MLB slate date (US/ET)</span>
            <input
              id="results-date"
              type="date"
              className="input"
              style={{ width: 'auto' }}
              value={date}
              onChange={e => setDate(e.target.value)}
              aria-label="Select date"
            />
          </label>
          <button
            id="btn-fetch-final"
            className="btn btn-primary"
            onClick={fetchFinalScores}
            disabled={fetching || grading}
            aria-busy={fetching}
          >
            {fetching ? '⏳ Fetching…' : '⚾ Fetch Final Scores'}
          </button>
          <button
            id="btn-lock-picks"
            className="btn btn-ghost"
            onClick={lockSlatePicks}
            disabled={locking || fetching || grading}
            aria-busy={locking}
            title="Lock every official T1 or O/U STRONG pick before first pitch"
          >
            {locking ? '⏳ Locking…' : '🔒 Lock Picks'}
          </button>
          <button
            id="btn-refresh-live"
            className="btn btn-ghost"
            onClick={() => fetchLiveScores(date)}
            disabled={liveLoading}
            aria-busy={liveLoading}
            title="Refresh live scores from MLB API (no DB write)"
          >
            {liveLoading ? '⏳' : '🔴 Refresh Live'}
          </button>
          <button
            id="btn-regrade"
            className="btn btn-ghost"
            onClick={reGrade}
            disabled={fetching || grading}
            aria-busy={grading}
            title="Re-run grading for already-stored final scores"
          >
            {grading ? '⏳ Grading…' : '⚖ Re-Grade'}
          </button>
        </div>
      </div>

      {/* ── Alerts ──────────────────────────────────────────────────────────── */}
      {error && (
        <div role="alert" style={{ color: 'var(--red-lt)', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(220,38,38,0.08)', borderRadius: 6 }}>
          ⚠ {error}
        </div>
      )}
      {status && (
        <div role="status" style={{ color: 'var(--green-lt)', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(22,163,74,0.08)', borderRadius: 6 }}>
          {status}
        </div>
      )}

      {/* ── Summary cards ────────────────────────────────────────────────────── */}
      {!loading && games.length > 0 && (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
          {[
            { label: 'Total Games', value: totalGames, color: 'var(--blue-lt)' },
            { label: 'Final', value: finalGames, color: 'var(--green-lt)' },
            { label: 'Live 🔴', value: liveGames, color: 'var(--amber-lt)' },
            { label: 'Upcoming', value: pendingGames, color: 'var(--muted)' },
            { label: '🏆 WIN', value: wins, color: 'var(--green-lt)' },
            { label: '❌ LOSS', value: losses, color: 'var(--red-lt)' },
            { label: '🔄 PUSH', value: pushes, color: 'var(--amber-lt)' },
            { label: '⏳ Pending', value: pending, color: 'var(--muted)' },
          ].map(card => (
            <div
              key={card.label}
              className="card-sm"
              style={{ minWidth: 90, textAlign: 'center', padding: '0.75rem 1rem' }}
            >
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: card.color }}>{card.value}</div>
              <div className="muted" style={{ fontSize: '0.7rem', marginTop: '0.2rem' }}>{card.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Settlement record strip: win rate, net units/ROI, streak ─────── */}
      {!loading && games.length > 0 && (
        <div
          className="card"
          style={{
            marginBottom: '1.5rem',
            padding: '0.85rem 1.25rem',
            display: 'flex',
            gap: '2rem',
            flexWrap: 'wrap',
            alignItems: 'center',
            background: 'linear-gradient(90deg, rgba(10,14,24,0.7), rgba(20,28,44,0.55))',
            border: '1px solid rgba(148,163,184,0.12)',
            borderRadius: 10,
          }}
        >
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Record</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800 }}>
              <span style={{ color: 'var(--green-lt)' }}>{wins}W</span>
              <span style={{ color: 'var(--muted)' }}>–</span>
              <span style={{ color: 'var(--red-lt)' }}>{losses}L</span>
              {pushes > 0 && <span style={{ color: 'var(--amber-lt)' }}>{pushes}P</span>}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Win Rate</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: winRate == null ? 'var(--muted)' : winRate >= 0.5 ? 'var(--green-lt)' : 'var(--red-lt)' }}>
              {winRate == null ? '—' : `${(winRate * 100).toFixed(0)}%`}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Profit</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: netUnits >= 0 ? 'var(--green-lt)' : 'var(--red-lt)' }}>
              {profitLabel}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>ROI</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: netUnits >= 0 ? 'var(--green-lt)' : 'var(--red-lt)' }}>{roiLabel}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Streak</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: streakType === 'win' ? 'var(--green-lt)' : 'var(--red-lt)' }}>
              {streakLabel}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Settled</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--muted)' }}>{settledCount}</div>
          </div>
        </div>
      )}

      {lastLiveFetch && (
        <p className="muted" style={{ fontSize: '0.72rem', marginBottom: '0.75rem' }}>
          Live scores updated: {lastLiveFetch.toLocaleTimeString('id-ID')} WIB · auto-refresh tiap 90 detik
        </p>
      )}

      {/* ── Table ───────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="muted" style={{ padding: '2rem', textAlign: 'center' }} aria-live="polite">
          Loading results…
        </div>
      ) : games.length === 0 ? (
        <div style={{ padding: '3rem 0', textAlign: 'center' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>📋</div>
          <p className="muted">Tidak ada game untuk tanggal {date}.</p>
          <p className="muted" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            Buka Daily Slate terlebih dahulu untuk load game dari MLB API.
          </p>
          <Link href="/" className="btn btn-primary" style={{ marginTop: '1rem', display: 'inline-block' }}>
            Ke Daily Slate →
          </Link>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" aria-label="Game results">
            <thead>
              <tr>
                <th>Game</th>
                <th>Start (WIB)</th>
                <th>Status</th>
                <th>Score</th>
                <th>ML Pick (locked)</th>
                <th>ML Settlement</th>
                <th>O/U Pick (locked)</th>
                <th>O/U Settlement</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {games.map((game: any) => {
                const live = liveMap[game.id];
                const mlRun = getResultRun(game.modelRuns, 'ML_COMBO_V2');
                const ouRun = getOuResultRun(game.modelRuns);
                const mlForecast = getLockedForecast(mlRun);
                const ouForecast = getLockedForecast(ouRun);
                const mlOut = mlRun ? JSON.parse(mlRun.outputJson) : null;
                const ouOut = ouRun ? JSON.parse(ouRun.outputJson) : null;
                const market = game.marketSnapshots?.[0];
                const mlPickTeam = mlOut?.candidateTeamName
                  ?? (mlOut?.candidate === 'away' ? game.awayTeam?.name : game.homeTeam?.name);
                const mlPickOdds = mlOut?.candidateDecimalOdds
                  ?? (mlOut?.candidate === 'away' ? market?.moneylineAway : market?.moneylineHome);
                const ouSide = ouOut?.selectedSide;
                const ouLine = ouForecast?.marketLine ?? market?.totalLine;

                // effective status: prefer live poll over DB status
                const effectiveStatus = live?.status ?? game.status;

                const rowBg = game.gameResult
                  ? 'rgba(34,197,94,0.04)'
                  : effectiveStatus === 'in_progress'
                  ? 'rgba(251,191,36,0.04)'
                  : 'transparent';

                return (
                  <tr key={game.id} style={{ background: rowBg }}>
                    <td>
                      <div style={{ fontWeight: 600, color: '#e2e8f0', fontSize: '0.85rem' }}>
                        {game.awayTeam?.name ?? game.awayTeamId}
                        <span className="muted"> @ </span>
                        {game.homeTeam?.name ?? game.homeTeamId}
                      </div>
                      <div className="muted" style={{ fontSize: '0.72rem' }}>{game.venue?.name}</div>
                    </td>

                    <td className="mono-val" style={{ fontSize: '0.78rem' }}>
                      {game.startTimeUtc ? formatWIB(game.startTimeUtc, 'dd/MM HH:mm') : '—'}
                    </td>

                    <td>
                      {effectiveStatus === 'final' || game.gameResult ? (
                        <span style={{ color: 'var(--green-lt)', fontWeight: 600, fontSize: '0.75rem' }}>✅ Final</span>
                      ) : effectiveStatus === 'in_progress' ? (
                        <span style={{ color: 'var(--amber-lt)', fontWeight: 600, fontSize: '0.75rem' }}>🔴 Live</span>
                      ) : effectiveStatus === 'postponed' ? (
                        <span className="muted" style={{ fontSize: '0.75rem' }}>PPD</span>
                      ) : effectiveStatus === 'cancelled' ? (
                        <span className="muted" style={{ fontSize: '0.75rem' }}>CXL</span>
                      ) : (
                        <span className="muted" style={{ fontSize: '0.75rem' }}>Upcoming</span>
                      )}
                    </td>

                    <td>
                      <ScoreCell game={game} live={live} />
                    </td>

                    {/* ── ML Pick ── */}
                    <td>
                      {mlForecast ? (
                        <div>
                          <div style={{ fontWeight: 600, color: 'var(--blue-lt)', fontSize: '0.8rem' }}>
                            {mlPickTeam ?? '—'}
                          </div>
                          <div className="muted mono-val" style={{ fontSize: '0.7rem' }}>
                            @{mlPickOdds != null ? Number(mlPickOdds).toFixed(2) : '—'}
                          </div>
                          <FinalStateChip state={mlRun?.finalState} size="sm" />
                        </div>
                      ) : mlRun ? (
                        <span className="muted" style={{ fontSize: '0.75rem' }}>
                          {mlRun.finalState === 'T1' ? 'Not locked' : mlRun.finalState === 'T2' ? 'Watchlist' : 'No pick'}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>

                    {/* ── ML Settlement ── */}
                    <td>
                      <SettleCell forecast={mlForecast} label="ML" />
                    </td>

                    {/* ── O/U Pick ── */}
                    <td>
                      {ouForecast ? (
                        <div>
                          <div style={{ fontWeight: 600, color: 'var(--blue-lt)', fontSize: '0.8rem', textTransform: 'uppercase' }}>
                            {ouSide ?? '—'} {ouLine != null ? `@${Number(ouLine).toFixed(1)}` : ''}
                          </div>
                          <FinalStateChip state={ouRun?.finalState} size="sm" />
                        </div>
                      ) : ouRun ? (
                        <span className="muted" style={{ fontSize: '0.75rem' }}>Not locked</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>

                    {/* ── O/U Settlement ── */}
                    <td>
                      <SettleCell forecast={ouForecast} label="O/U" />
                    </td>

                    <td>
                      <Link
                        href={`/games/${game.id}`}
                        className="btn btn-ghost btn-sm"
                        id={`results-detail-${game.id}`}
                        aria-label={`Detail ${game.awayTeam?.name} @ ${game.homeTeam?.name}`}
                      >
                        Detail →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: '0.72rem', marginTop: '1rem' }}>
            Klik <strong>Fetch Final Scores</strong> untuk menarik skor dari MLB Stats API dan auto-grade semua forecast yang sudah di-lock.
            Live scores diambil langsung dari MLB API tanpa disimpan ke DB.
          </p>
        </div>
      )}
    </div>
  );
}
