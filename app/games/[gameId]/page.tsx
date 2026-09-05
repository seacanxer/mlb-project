'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { FinalStateChip, ExperimentalBadge } from '@/components/FinalStateChip';
import { formatWIB, formatUTC } from '@/lib/utils/timezone';

function FactorCard({ label, points, max, detail }: { label: string; points: number; max: number; detail?: string }) {
  return (
    <div className="card-sm">
      <div className="flex-between" style={{ marginBottom: '0.4rem' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0' }}>{label}</span>
        <span className="mono-val" style={{ fontWeight: 700, color: 'var(--blue-lt)' }}>{points} <span className="muted">/ {max}</span></span>
      </div>
      <div className="score-bar">
        <div className="score-bar-fill" style={{ width: `${(points / max) * 100}%`, background: 'var(--blue)' }} />
      </div>
      {detail && <div className="muted" style={{ fontSize: '0.75rem', marginTop: '0.4rem' }}>{detail}</div>}
    </div>
  );
}

function OUAdjCard({ label, value, detail }: { label: string; value: number | null; detail?: string }) {
  const color = value === null ? 'var(--muted)' : value > 0 ? 'var(--green-lt)' : value < 0 ? 'var(--red-lt)' : 'var(--muted)';
  return (
    <div className="card-sm">
      <div className="flex-between">
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0' }}>{label}</span>
        <span className="mono-val" style={{ fontWeight: 700, color }}>
          {value == null ? '—' : (value > 0 ? '+' : '') + value.toFixed(3)}
        </span>
      </div>
      {detail && <div className="muted" style={{ fontSize: '0.75rem', marginTop: '0.3rem' }}>{detail}</div>}
    </div>
  );
}

function lockSideForRun(run: any): string {
  if (run.modelId.startsWith('OU_')) {
    try {
      return JSON.parse(run.outputJson)?.selectedSide
        ?? (run.finalState?.startsWith('UNDER') ? 'under' : 'over');
    } catch {
      return run.finalState?.startsWith('UNDER') ? 'under' : 'over';
    }
  }
  try {
    return JSON.parse(run.outputJson)?.candidate === 'away' ? 'away' : 'home';
  } catch {
    return 'home';
  }
}

function isLockableRun(run: any): boolean {
  return ['T1', 'OVER_STRONG_GAP', 'UNDER_STRONG_GAP']
    .includes(run.finalState);
}

export default function MatchDetail() {
  const { gameId } = useParams() as { gameId: string };
  const [game, setGame] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [locking, setLocking] = useState('');

  useEffect(() => {
    fetch(`/api/games/${gameId}`)
      .then((r) => r.json())
      .then((d) => { setGame(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [gameId]);

  const lockForecast = async (runId: string, side: string) => {
    setLocking(runId);
    const res = await fetch(`/api/model-runs/${runId}/lock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selectedSide: side }),
    });
    const data = await res.json();
    if (data.ok) {
      alert(`Forecast locked! ID: ${data.forecastId}`);
      // Refresh game data
      const g = await fetch(`/api/games/${gameId}`).then((r) => r.json());
      setGame(g);
    } else {
      alert(`Failed: ${data.error}`);
    }
    setLocking('');
  };

  if (loading) return <div className="muted" style={{ padding: '3rem', textAlign: 'center' }} aria-live="polite">Loading match detail…</div>;
  if (!game || game.error) return <div className="muted" style={{ padding: '3rem', textAlign: 'center' }} role="alert">Game not found.</div>;

  const mlRun = game.modelRuns?.find((r: any) => r.modelId === 'ML_COMBO_V2' && !r.isInvalidated);
  const ouRun = game.modelRuns?.find((r: any) => r.modelId === 'OU_UNIFIED' && !r.isInvalidated)
    ?? game.modelRuns?.find((r: any) => r.modelId === 'OU_V3' && !r.isInvalidated)
    ?? game.modelRuns?.find((r: any) => r.modelId === 'OU_V2_3' && !r.isInvalidated);
  const usesStaffProjection = ouRun?.modelId !== 'OU_V2_3';
  const market = game.marketSnapshots?.[0];
  const mlOut = mlRun ? JSON.parse(mlRun.outputJson) : null;
  const ouOut = ouRun ? JSON.parse(ouRun.outputJson) : null;
  const mlActionable = mlRun?.finalState === 'T1' || mlRun?.finalState === 'T2';
  const mlPickTeam = mlOut?.candidateTeamName
    ?? (mlOut?.candidate === 'away' ? game.awayTeam?.name : game.homeTeam?.name);
  const mlPickOdds = mlOut?.candidateDecimalOdds
    ?? (mlOut?.candidate === 'away' ? market?.moneylineAway : market?.moneylineHome);

  return (
    <div>
      {/* ---- Header ---- */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {game.awayTeam?.name} <span className="muted">@</span> {game.homeTeam?.name}
          </h1>
          <p className="page-subtitle">
            {game.venue?.name} · {game.startTimeUtc ? formatWIB(game.startTimeUtc) : '—'}
            <span className="muted" style={{ marginLeft: '0.5rem', fontSize: '0.75rem' }}>
              (UTC: {game.startTimeUtc ? formatUTC(game.startTimeUtc) : '—'})
            </span>
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {mlRun && <FinalStateChip state={mlRun.finalState} />}
          {ouRun && <><FinalStateChip state={ouRun.finalState} /><ExperimentalBadge /></>}
        </div>
      </div>

      {/* ---- Market header ---- */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', marginBottom: '0.2rem' }}>ML Odds (Away)</div>
            <div className="mono-val" style={{ fontWeight: 700 }}>{market?.moneylineAwayOrig ?? '—'}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', marginBottom: '0.2rem' }}>ML Odds (Home)</div>
            <div className="mono-val" style={{ fontWeight: 700 }}>{market?.moneylineHomeOrig ?? '—'}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', marginBottom: '0.2rem' }}>Total Line</div>
            <div className="mono-val" style={{ fontWeight: 700 }}>{market?.totalLine ?? '—'}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', marginBottom: '0.2rem' }}>Over / Under</div>
            <div className="mono-val">{market?.totalOverDecimal?.toFixed(2)} / {market?.totalUnderDecimal?.toFixed(2)}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.75rem', marginBottom: '0.2rem' }}>Retrieved</div>
            <div style={{ fontSize: '0.8rem' }}>{market ? formatWIB(market.retrievedAt, 'HH:mm dd/MM') : '—'}</div>
          </div>
          {!market && (
            <span className="gate-pill" role="alert">ODDS_PROVIDER_NOT_CONFIGURED</span>
          )}
        </div>
      </div>

      {/* ---- Moneyline section ---- */}
      {mlOut && (
        <section aria-labelledby="ml-heading">
          <h2 id="ml-heading" style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem', color: '#f1f5f9' }}>
            Moneyline — Combo Score v2.1 (heuristic score, not win probability)
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <div className="muted" style={{ fontSize: '0.75rem' }}>Raw Score</div>
              <div className="mono-val" style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--blue-lt)' }}>
                {mlOut.rawScore?.toFixed(0)}
              </div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: '0.75rem' }}>ML Pick</div>
              {mlActionable ? (
                <div style={{ fontWeight: 700, color: 'var(--green-lt)' }}>
                  {mlPickTeam} <span className="mono-val">@{mlPickOdds != null ? Number(mlPickOdds).toFixed(2) : '—'}</span>
                </div>
              ) : (
                <div className="muted" style={{ fontWeight: 700 }}>NO PICK</div>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <div className="score-bar" style={{ height: 10 }}>
                <div
                  className="score-bar-fill"
                  style={{
                    width: `${Math.min(mlOut.rawScore ?? 0, 100)}%`,
                    background: mlRun.finalState === 'T1' ? 'var(--green)' : mlRun.finalState === 'T2' ? 'var(--blue)' : 'var(--muted)',
                  }}
                />
              </div>
              <div className="flex-between" style={{ marginTop: '0.3rem' }}>
                <span className="muted" style={{ fontSize: '0.7rem' }}>0</span>
                <span className="muted" style={{ fontSize: '0.7rem' }}>55 (T2)</span>
                <span className="muted" style={{ fontSize: '0.7rem' }}>70 (T1)</span>
                <span className="muted" style={{ fontSize: '0.7rem' }}>100</span>
              </div>
            </div>
            <FinalStateChip state={mlRun.finalState} />
          </div>
          <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
            <FactorCard label="ERA Gap" points={mlOut.eraGapPoints} max={35} detail={`EraGap: ${mlOut.eraGap?.toFixed(2)}`} />
            <FactorCard label="Offense Quality" points={mlOut.offensePoints} max={25} detail={`AVG: ${mlOut.offenseAvgLabel} · OPS: ${mlOut.offenseOpsLabel}`} />
            <FactorCard label="Pitcher Last 5" points={mlOut.gameLogPoints} max={20} detail={`${mlOut.gameLogGoodStarts} good starts · Trend: ${mlOut.trend}`} />
            <FactorCard
              label="Market Alignment"
              points={mlOut.marketAlignmentPoints}
              max={10}
              detail={`Heuristic anchor: ${mlOut.fairDecimal?.toFixed(2) ?? 'N/A'} · No-vig market: ${mlOut.marketNoVigProbability == null ? '—' : `${(mlOut.marketNoVigProbability * 100).toFixed(1)}%`}`}
            />
            <FactorCard label="Team Form" points={mlOut.teamFormPoints} max={10} />
          </div>
        </section>
      )}

      {/* ---- O/U section ---- */}
      {ouOut && (
        <section aria-labelledby="ou-heading" style={{ marginTop: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <h2 id="ou-heading" style={{ fontSize: '1rem', fontWeight: 700, color: '#f1f5f9' }}>
              Over/Under — {ouRun.modelId === 'OU_UNIFIED'
                ? `Unified MLB Totals v${ouOut.modelVersion ?? '4.0.0'}`
                : ouRun.modelId === 'OU_V3'
                ? `Archived Staff Run Model v${ouOut.modelVersion ?? '3.1.0'}`
                : 'Archived Formula v2.3'}
            </h2>
            <ExperimentalBadge />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div>
              <div className="muted" style={{ fontSize: '0.75rem' }}>Gap</div>
              <div className="mono-val" style={{ fontSize: '1.8rem', fontWeight: 700, color: (ouOut.gap ?? 0) > 0 ? 'var(--green-lt)' : (ouOut.gap ?? 0) < 0 ? 'var(--blue-lt)' : 'var(--muted)' }}>
                {ouOut.gap != null ? (ouOut.gap > 0 ? '+' : '') + ouOut.gap.toFixed(3) : '—'}
              </div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: '0.75rem' }}>{usesStaffProjection ? 'Projected Total' : 'Adjusted Total'}</div>
              <div className="mono-val" style={{ fontSize: '1.2rem', fontWeight: 600 }}>
                {(ouOut.projectedTotal ?? ouOut.adjustedTotal)?.toFixed(2) ?? '—'}
              </div>
            </div>
            {ouOut.selectedSide && (
              <div>
                <div className="muted" style={{ fontSize: '0.75rem' }}>Signal / Price</div>
                <div className="mono-val" style={{ fontWeight: 700, textTransform: 'uppercase' }}>
                  {ouOut.selectedSide} @{ouOut.selectedPrice?.toFixed(2) ?? '—'}
                </div>
              </div>
            )}
            {ouOut.dataQualityScore != null && (
              <div>
                <div className="muted" style={{ fontSize: '0.75rem' }}>Data Quality</div>
                <div className="mono-val" style={{ fontWeight: 700 }}>{ouOut.dataQualityScore}/100</div>
              </div>
            )}
            {ouOut.estimatedOverProbability != null && (
              <div>
                <div className="muted" style={{ fontSize: '0.75rem' }}>Experimental O / U / Push</div>
                <div className="mono-val" style={{ fontWeight: 700 }}>
                  {(ouOut.estimatedOverProbability * 100).toFixed(1)}% / {(ouOut.estimatedUnderProbability * 100).toFixed(1)}% / {(ouOut.estimatedPushProbability * 100).toFixed(1)}%
                </div>
              </div>
            )}
            {ouOut.capReached && <span className="warning-pill">⚠ CAP REACHED ±3.0</span>}
            <FinalStateChip state={ouRun.finalState} />
          </div>
          {usesStaffProjection ? (
            <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
              <OUAdjCard label="Independent Total" value={ouOut.independentModelTotal} detail="50% team RPG + 50% opposing staff allowance, then park adjustment" />
              <OUAdjCard label="Effective Park Factor" value={ouOut.effectiveParkFactor} detail={`Raw ${ouOut.rawParkFactor?.toFixed(3) ?? '—'}; fallback sources are attenuated`} />
              <OUAdjCard label="Line Movement" value={ouOut.lineMovement} detail={`Opening ${ouOut.openingTotalLine ?? '—'} → current ${ouOut.marketLine ?? '—'}`} />
            </div>
          ) : (
            <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
              <OUAdjCard label="Offense Adj" value={ouOut.offAdj} detail="((AwayRPG-4.1)+(HomeRPG-4.1)) × 0.60" />
              <OUAdjCard label="Pitching Adj" value={ouOut.pitchAdj} detail="(Last5ERA - SeasonERA) × 0.50 (both)" />
              <OUAdjCard label="Park Adj" value={ouOut.parkAdj} detail="(HomePF - 1.0) × Line × 2.5" />
            </div>
          )}
          <div className="card-sm">
            <div className="flex-between">
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Away L5 ERA</span>
              <span className="mono-val">{ouOut.awayLastFiveEra?.toFixed(2) ?? '—'}</span>
            </div>
            <div className="divider" style={{ margin: '0.5rem 0' }} />
            <div className="flex-between">
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Home L5 ERA</span>
              <span className="mono-val">{ouOut.homeLastFiveEra?.toFixed(2) ?? '—'}</span>
            </div>
            {usesStaffProjection && <>
              <div className="divider" style={{ margin: '0.5rem 0' }} />
              <div className="flex-between">
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Away starter / staff runs</span>
                <span className="mono-val">{ouOut.awayBlendedStarterEra?.toFixed(2) ?? '—'} / {ouOut.awayStaffRunsAllowed?.toFixed(2) ?? '—'}</span>
              </div>
              <div className="divider" style={{ margin: '0.5rem 0' }} />
              <div className="flex-between">
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Home starter / staff runs</span>
                <span className="mono-val">{ouOut.homeBlendedStarterEra?.toFixed(2) ?? '—'} / {ouOut.homeStaffRunsAllowed?.toFixed(2) ?? '—'}</span>
              </div>
              <div className="divider" style={{ margin: '0.5rem 0' }} />
              {ouOut.awayExpectedRuns != null && <>
                <div className="flex-between">
                  <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Projected team runs (away / home)</span>
                  <span className="mono-val">{ouOut.awayExpectedRuns.toFixed(2)} / {ouOut.homeExpectedRuns?.toFixed(2) ?? '—'}</span>
                </div>
                <div className="divider" style={{ margin: '0.5rem 0' }} />
              </>}
              <div className="muted" style={{ fontSize: '0.75rem' }}>
                Distribution probabilities are experimental diagnostics, not calibrated betting confidence. Estimated edge versus the no-vig market: {ouOut.estimatedProbabilityEdge == null ? '—' : `${(ouOut.estimatedProbabilityEdge * 100).toFixed(1)}pp`}. Missing context: {ouOut.missingContexts?.join(', ') ?? '—'}.
              </div>
            </>}
          </div>
        </section>
      )}

      {/* ---- Hard gates + Warnings ---- */}
      {(mlRun?.warnings?.length > 0 || ouRun?.warnings?.length > 0) && (
        <section style={{ marginTop: '2rem' }} aria-labelledby="gates-heading">
          <h2 id="gates-heading" style={{ fontSize: '1rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '1rem' }}>
            Hard Gates &amp; Warnings
          </h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {mlRun?.warnings?.filter((w: any) => w.message?.startsWith('Hard gate')).map((w: any) => (
              <span key={w.id} className="gate-pill" role="img" aria-label={`Hard gate: ${w.code}`}>⛔ {w.code}</span>
            ))}
            {mlRun?.warnings?.filter((w: any) => !w.message?.startsWith('Hard gate')).map((w: any) => (
              <span key={w.id} className="warning-pill" role="img" aria-label={`Warning: ${w.code}`}>⚠ {w.code}</span>
            ))}
            {ouRun?.warnings?.map((w: any) => (
              <span key={w.id} className="warning-pill" role="img" aria-label={`Warning: ${w.code}`}>⚠ {w.code}</span>
            ))}
          </div>
        </section>
      )}

      {/* ---- Model metadata ---- */}
      <section style={{ marginTop: '2rem' }} aria-labelledby="meta-heading">
        <h2 id="meta-heading" style={{ fontSize: '1rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '1rem' }}>
          Model &amp; Source Lineage
        </h2>
        <div className="card-sm">
          {[mlRun, ouRun].filter(Boolean).map((run: any) => (
            <div key={run.id} style={{ marginBottom: '0.75rem' }}>
              <div className="flex-between">
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0' }}>{run.modelId}</span>
                <span className="muted mono-val" style={{ fontSize: '0.75rem' }}>v{run.configVersion?.semver}</span>
              </div>
              <div className="muted" style={{ fontSize: '0.75rem', marginTop: '0.2rem' }}>
                Run ID: <span className="mono-val">{run.id}</span> ·
                InputSnapshot: <span className="mono-val">{run.inputSnapshotId}</span> ·
                {run.isLocked ? ' 🔒 Locked' : ' Unlocked'}
              </div>
              {!run.isLocked && !run.isInvalidated && isLockableRun(run) && (
                <button
                  id={`btn-lock-${run.id}`}
                  className="btn btn-ghost btn-sm"
                  style={{ marginTop: '0.5rem' }}
                  disabled={!!locking}
                  onClick={() => lockForecast(run.id, lockSideForRun(run))}
                  aria-label={`Lock ${run.modelId} forecast`}
                >
                  {locking === run.id ? '⏳ Locking…' : '🔒 Lock Forecast'}
                </button>
              )}
              {!run.isLocked && !run.isInvalidated && !isLockableRun(run) && ['T2', 'OVER_RISKY', 'UNDER_RISKY', 'OVER_LEAN', 'UNDER_LEAN'].includes(run.finalState) && (
                <div className="muted" style={{ fontSize: '0.75rem', marginTop: '0.4rem' }}>
                  Watchlist/shadow signal — not eligible for official settlement.
                </div>
              )}
              {run.forecasts?.map((f: any) => (
                <div key={f.id} className="muted" style={{ fontSize: '0.75rem', marginTop: '0.3rem' }}>
                  Forecast {f.id.slice(0, 8)}… locked at {formatWIB(f.lockedAt)} ·
                  Settlement: {f.settlement?.outcome ?? 'pending'}
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
