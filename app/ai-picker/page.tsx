'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { currentDisplayDate, shiftDateOnly } from '@/lib/utils/timezone';
import { analysisForGame, marketForGame, starterForSide } from '@/lib/aiPickerGame';

const MODELS = [
  { id: 'auto', name: '🔄 Auto Model Rotation (Claude / DeepSeek / Qwen)' },
  { id: 'gr/claude-opus-5', name: 'Claude Opus 5 (GR) — Live' },
  { id: 'xkiro/deepseek/deepseek-v4-pro', name: 'DeepSeek v4 Pro — Live' },
  { id: 'xkiro/deepseek/deepseek-v4-flash', name: 'DeepSeek v4 Flash — Live' },
  { id: 'xkiro/deepseek/deepseek-chat-v3.1', name: 'DeepSeek Chat v3.1 — Live' },
  { id: 'qwentele/qwen3.8-max', name: 'Qwen3.8 Max (Fast)' },
  { id: 'sec', name: 'DeepSeek v4 Pro (Sec)' },
];

const ROTATION_MODELS = [
  'gr/claude-opus-5',
  'xkiro/deepseek/deepseek-v4-pro',
  'xkiro/deepseek/deepseek-v4-flash',
  'qwentele/qwen3.8-max',
  'sec',
];

async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<void>
) {
  let nextIndex = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      await worker(items[index], index);
    }
  });
  await Promise.all(runners);
}

export default function AiPickerPage() {
  const [date, setDate] = useState(currentDisplayDate);
  const [selectedModel, setSelectedModel] = useState('auto');
  const [filter, setFilter] = useState<'all' | 'ml' | 'ou' | 'high_conf'>('all');
  const [games, setGames] = useState<any[]>([]);
  const [picks, setPicks] = useState<Record<string, any>>({});
  const [loadingGames, setLoadingGames] = useState(false);
  const [loadingPicks, setLoadingPicks] = useState(false);
  const [error, setError] = useState('');
  const requestCycle = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  const fetchSlate = useCallback(async (targetDate: string, modelChoice: string) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const cycle = ++requestCycle.current;
    setLoadingGames(true);
    setLoadingPicks(false);
    setError('');
    setPicks({});

    try {
      const res = await fetch(`/api/slates/${targetDate}?timezone=Asia%2FJakarta`, {
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!res.ok) {
        throw new Error(`Failed to load games: HTTP ${res.status}`);
      }
      const data = await res.json();
      const loadedGames = data.games || [];
      setGames(loadedGames);
      setLoadingGames(false);

      if (loadedGames.length > 0) {
        setLoadingPicks(true);
        const initialLoadingMap: Record<string, any> = {};
        loadedGames.forEach((g: any) => {
          initialLoadingMap[g.id] = { loading: true };
        });
        setPicks(initialLoadingMap);

        await runWithConcurrency(loadedGames, 3, (game: any, idx: number) =>
          generatePickForGame(game, modelChoice, idx, controller.signal, cycle)
        );
        if (requestCycle.current === cycle) setLoadingPicks(false);
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error(err);
      setError(err?.message || 'Error loading slate games.');
      setGames([]);
    } finally {
      if (requestCycle.current === cycle) setLoadingGames(false);
    }
  }, []);

  const generatePickForGame = async (
    game: any,
    modelChoice: string,
    index: number,
    signal?: AbortSignal,
    cycle: number = requestCycle.current
  ) => {
    const modelToUse = modelChoice === 'auto' ? ROTATION_MODELS[index % ROTATION_MODELS.length] : modelChoice;
    const awayName = game.awayTeam?.name || 'Away';
    const homeName = game.homeTeam?.name || 'Home';
    const awayStarter = starterForSide(game, 'away');
    const homeStarter = starterForSide(game, 'home');
    const awaySp = awayStarter?.person?.fullName || awayStarter?.person?.name || 'TBD';
    const homeSp = homeStarter?.person?.fullName || homeStarter?.person?.name || 'TBD';
    const { moneyline, total } = marketForGame(game);

    try {
      const res = await fetch('/api/pick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gameId: game.id,
          away: awayName,
          home: homeName,
          away_sp: awaySp,
          home_sp: homeSp,
          moneyline,
          total,
          model: modelToUse,
          venue: game.venue?.name || '',
          analysis: analysisForGame(game),
        }),
        signal,
      });

      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `Picker HTTP ${res.status}`);
      }
      let parsed = data;
      if (data.result && typeof data.result === 'string') {
        try {
          const jsonMatch = data.result.match(/\{[\s\S]*\}/);
          if (jsonMatch) parsed = { ...data, ...JSON.parse(jsonMatch[0]) };
        } catch (_) {}
      }

      if (requestCycle.current !== cycle) return;
      setPicks((prev) => ({
        ...prev,
        [game.id]: {
          data: parsed,
          model: modelToUse,
          loading: false,
          error: null,
        },
      }));
    } catch (err: any) {
      if (err?.name === 'AbortError' || requestCycle.current !== cycle) return;
      setPicks((prev) => ({
        ...prev,
        [game.id]: {
          data: null,
          model: modelToUse,
          loading: false,
          error: err?.message || 'Pick calculation error',
        },
      }));
    }
  };

  useEffect(() => {
    fetchSlate(date, selectedModel);
    return () => activeRequest.current?.abort();
  }, [date, selectedModel, fetchSlate]);

  const handleDateShift = (days: number) => {
    setDate((current) => shiftDateOnly(current, days));
  };

  // Filtered games
  const filteredGames = games.filter((game) => {
    const pickInfo = picks[game.id]?.data;
    if (filter === 'all') return true;
    if (!pickInfo) return true;
    const pickText = String(pickInfo.pick || '').toLowerCase();
    if (filter === 'ml') return pickText.includes('ml');
    if (filter === 'ou') return pickText.includes('over') || pickText.includes('under');
    if (filter === 'high_conf') return (pickInfo.confidence || 0) >= 70;
    return true;
  });

  const aiPicks = Object.values(picks).filter((p) =>
    p?.data?.source === 'llm' && p?.data?.actionable !== false && p?.data?.pick && p.data.pick !== 'NO PICK'
  ).length;
  const frameworkPicks = Object.values(picks).filter((p) => p?.data?.framework?.actionable).length;
  const confValues = Object.values(picks)
    .filter((p) => p?.data?.confidenceType === 'ai-opinion')
    .map((p) => p?.data?.confidence)
    .filter((c): c is number => typeof c === 'number' && c > 0);
  const avgConf = confValues.length ? Math.round(confValues.reduce((a, b) => a + b, 0) / confValues.length) : 0;

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '1.5rem 0' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '2rem' }}>⚾</span>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, margin: 0 }}>MLB AI Model Picker</h1>
            <span style={{
              background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
              color: '#fff',
              fontSize: '0.75rem',
              fontWeight: 700,
              padding: '3px 10px',
              borderRadius: '9999px',
              letterSpacing: '0.05em'
            }}>9ROUTER / MULTI-AI</span>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Advanced Sabermetric & Multi-Model AI Betting Analysis (GPT-5.6 Sol, Claude Fable, DeepSeek v4 Pro).
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <a
            href="/dashboard.html"
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary"
            style={{ fontSize: '0.85rem', padding: '0.5rem 1rem' }}
          >
            ↗ Open Standalone Dashboard
          </a>
          <button
            onClick={() => fetchSlate(date, selectedModel)}
            disabled={loadingGames || loadingPicks}
            className="btn btn-primary"
            style={{ fontSize: '0.85rem', padding: '0.5rem 1.25rem' }}
          >
            {loadingGames || loadingPicks ? '⟳ Calculating...' : '⟳ Refresh Slate & Picks'}
          </button>
        </div>
      </div>

      {/* Controls Bar */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1rem 1.25rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '1rem',
        marginBottom: '1.5rem',
      }}>
        {/* Date Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button onClick={() => handleDateShift(-1)} className="btn btn-secondary" style={{ padding: '0.4rem 0.75rem' }}>‹ Prev</button>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{
              background: '#070d18',
              border: '1px solid var(--border)',
              color: '#fff',
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              fontFamily: 'inherit',
              fontSize: '0.875rem',
            }}
          />
          <button onClick={() => handleDateShift(1)} className="btn btn-secondary" style={{ padding: '0.4rem 0.75rem' }}>Next ›</button>
          <button
            onClick={() => setDate(currentDisplayDate())}
            className="btn btn-secondary"
            style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
          >
            Today (WIB)
          </button>
        </div>

        {/* Model Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--muted)', fontWeight: 500 }}>AI Engine:</label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{
              background: '#070d18',
              border: '1px solid var(--border)',
              color: '#fff',
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              fontFamily: 'inherit',
              fontSize: '0.875rem',
              outline: 'none',
            }}
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>

        {/* Filter Pills */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {[
            { key: 'all', label: 'All Games' },
            { key: 'ml', label: 'Moneyline' },
            { key: 'ou', label: 'Totals O/U' },
            { key: 'high_conf', label: '⭐ High AI Rating (70+)' },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key as any)}
              style={{
                fontSize: '0.8rem',
                padding: '0.35rem 0.85rem',
                borderRadius: '9999px',
                background: filter === f.key ? '#1e3a5f' : 'transparent',
                color: filter === f.key ? '#fff' : 'var(--muted)',
                border: filter === f.key ? '1px solid #3b82f6' : '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Summary Strip */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '1rem',
        marginBottom: '1.5rem',
      }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '10px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Slate Games</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace' }}>{games.length}</div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '10px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Framework Picks</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: '#60a5fa' }}>{frameworkPicks} / {games.length}</div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '10px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>Avg AI Rating</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: '#34d399' }}>{avgConf ? `${avgConf}/100` : '—'}</div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '10px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', fontWeight: 600 }}>External AI Picks</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: '#fbbf24' }}>{aiPicks} / {games.length}</div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          color: '#fca5a5',
          padding: '1rem',
          borderRadius: '8px',
          marginBottom: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div><strong>Notice:</strong> {error}</div>
          <button onClick={() => fetchSlate(date, selectedModel)} className="btn btn-secondary" style={{ fontSize: '0.8rem' }}>Retry</button>
        </div>
      )}

      {/* Loading state */}
      {loadingGames ? (
        <div style={{ textAlign: 'center', padding: '4rem 1rem', color: 'var(--muted)' }}>
          <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>⚾ Loading slate games for {date}...</div>
        </div>
      ) : filteredGames.length === 0 ? (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          padding: '3rem',
          textAlign: 'center',
          color: 'var(--muted)',
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>⚾</div>
          <h3>No games found for {date} matching filter.</h3>
          <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>Try selecting a different date or filter above.</p>
        </div>
      ) : (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#0a1628', borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>Matchup & Starters</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>Market Odds</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>Framework Pick</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>AI Review</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>AI Rating & Verdict</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>AI Rationale</th>
                <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--muted)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredGames.map((game, idx) => {
                const pickEntry = picks[game.id];
                const p = pickEntry?.data;
                const isLoading = pickEntry?.loading;
                const homeName = game.homeTeam?.name || 'Home';
                const awayName = game.awayTeam?.name || 'Away';
                const homeStarter = starterForSide(game, 'home');
                const awayStarter = starterForSide(game, 'away');
                const homeSp = homeStarter?.person?.fullName || homeStarter?.person?.name || 'TBD';
                const awaySp = awayStarter?.person?.fullName || awayStarter?.person?.name || 'TBD';
                const { moneyline: ml, total } = marketForGame(game);

                const pickText = p?.pick || '—';
                const framework = p?.framework;
                const confidence = p?.confidence || 0;
                const reason = p?.reason || (isLoading ? 'Analyzing pitching metrics & lineups...' : 'No pick available');
                const modelUsed = p?.model || pickEntry?.model?.split('/').pop() || 'AI Model';
                const confidenceLabel = p?.confidenceType === 'model-score'
                  ? `${confidence} score`
                  : p?.confidenceType === 'data-quality'
                  ? `${confidence} quality`
                  : confidence
                  ? `${confidence}/100`
                  : '—';

                let pickColor = '#60a5fa';
                let pickBg = 'rgba(59, 130, 246, 0.15)';
                let pickBorder = 'rgba(59, 130, 246, 0.4)';
                if (pickText.toLowerCase().includes('away')) {
                  pickColor = '#fbbf24';
                  pickBg = 'rgba(245, 158, 11, 0.15)';
                  pickBorder = 'rgba(245, 158, 11, 0.4)';
                } else if (pickText.toLowerCase().includes('over')) {
                  pickColor = '#f472b6';
                  pickBg = 'rgba(236, 72, 153, 0.15)';
                  pickBorder = 'rgba(236, 72, 153, 0.4)';
                } else if (pickText.toLowerCase().includes('under')) {
                  pickColor = '#34d399';
                  pickBg = 'rgba(16, 185, 129, 0.15)';
                  pickBorder = 'rgba(16, 185, 129, 0.4)';
                }

                return (
                  <tr key={game.id} style={{ borderBottom: '1px solid rgba(30, 58, 95, 0.5)' }}>
                    {/* Matchup */}
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                        <span style={{ color: '#fde047' }}>{awayName}</span>
                        <span style={{ color: 'var(--muted)', margin: '0 6px', fontWeight: 400 }}>@</span>
                        <span style={{ color: '#93c5fd' }}>{homeName}</span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginTop: '3px' }}>
                        SP: {awaySp} vs {homeSp}
                      </div>
                      {game.venue?.name && (
                        <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '2px' }}>
                          📍 {game.venue.name}
                        </div>
                      )}
                    </td>

                    {/* Odds */}
                    <td style={{ padding: '1rem', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem' }}>
                      <div style={{ color: '#facc15' }}>ML: {ml}</div>
                      <div style={{ color: '#60a5fa', marginTop: '2px' }}>O/U: {total}</div>
                    </td>

                    {/* Pick */}
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontWeight: 700, color: framework?.actionable ? '#60a5fa' : '#94a3b8', fontSize: '0.85rem' }}>
                        {framework?.pick || (isLoading ? 'Calculating...' : '—')}
                      </div>
                      {framework && (
                        <>
                          <div style={{ color: '#94a3b8', fontSize: '0.72rem', marginTop: '3px' }}>
                            {framework.state}{framework.score != null ? ` · ${framework.score} ${framework.scoreType === 'data-quality' ? 'quality' : 'score'}` : ''}
                          </div>
                          <div style={{ color: '#64748b', fontSize: '0.7rem', marginTop: '3px', maxWidth: '220px' }}>{framework.reason}</div>
                        </>
                      )}
                    </td>

                    {/* Independent AI review */}
                    <td style={{ padding: '1rem' }}>
                      {isLoading ? (
                        <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>Calculating...</span>
                      ) : (
                        <div>
                          <span style={{
                            display: 'inline-block',
                            background: pickBg,
                            color: pickColor,
                            border: `1px solid ${pickBorder}`,
                            padding: '4px 10px',
                            borderRadius: '8px',
                            fontWeight: 700,
                            fontSize: '0.85rem',
                          }}>
                            🎯 {pickText}
                          </span>
                          {p?.projectedScore && (
                            <div style={{ fontSize: '0.75rem', fontFamily: 'JetBrains Mono, monospace', color: 'var(--muted)', marginTop: '4px' }}>
                              Proj: {p.projectedScore}
                            </div>
                          )}
                        </div>
                      )}
                    </td>

                    {/* AI rating & verdict */}
                    <td style={{ padding: '1rem', minWidth: '120px' }}>
                      {isLoading ? (
                        <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>—</span>
                      ) : (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>
                            <span>{confidenceLabel}</span>
                            {p?.valueEdge && <span style={{ color: '#34d399', fontSize: '0.75rem' }}>{p.valueEdge}</span>}
                          </div>
                          <div style={{ width: '100%', height: '6px', background: '#0a1628', borderRadius: '9999px', marginTop: '4px', overflow: 'hidden' }}>
                            <div style={{
                              width: `${confidence}%`,
                              height: '100%',
                              background: 'linear-gradient(90deg, #3b82f6, #10b981)',
                              borderRadius: '9999px',
                            }} />
                          </div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '3px' }}>
                            {modelUsed} · {p?.source === 'llm' ? 'external AI' : p?.source === 'not-run' ? 'not run' : 'unavailable'}
                          </div>
                          {p?.verdict && (
                            <div style={{
                              display: 'inline-block', marginTop: '5px', padding: '2px 7px', borderRadius: '9999px',
                              fontSize: '0.68rem', fontWeight: 800,
                              color: p.verdict === 'AGREE' ? '#34d399' : p.verdict === 'DISAGREE' ? '#fbbf24' : p.verdict === 'UNAVAILABLE' ? '#f87171' : '#94a3b8',
                              background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--border)'
                            }}>
                              {p.verdict}
                            </div>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Reason */}
                    <td style={{ padding: '1rem', fontSize: '0.82rem', color: '#cbd5e1', maxWidth: '320px', lineHeight: 1.45 }}>
                      {reason}
                    </td>

                    {/* Actions */}
                    <td style={{ padding: '1rem' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <button
                          onClick={() => generatePickForGame(game, selectedModel, idx)}
                          disabled={isLoading}
                          className="btn btn-secondary"
                          style={{ fontSize: '0.75rem', padding: '3px 8px' }}
                        >
                          🔄 Re-predict
                        </button>
                        <Link
                          href={`/games/${game.id}`}
                          className="btn btn-secondary"
                          style={{ fontSize: '0.75rem', padding: '3px 8px', textAlign: 'center' }}
                        >
                          🔍 Match Stats
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
