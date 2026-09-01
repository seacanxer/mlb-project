'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildPickerRequest } from '@/lib/aiPickerGame';
import { currentDisplayDate, formatWIB, shiftDateOnly } from '@/lib/utils/timezone';
import { parlayRecommendations } from '@/lib/aiFinalPickMath';

const MODELS = [
  'gr/claude-opus-5',
  'xkiro/deepseek/deepseek-v4-pro',
  'xkiro/deepseek/deepseek-v4-flash',
  'qwentele/qwen3.8-max',
];

type FinalPick = {
  id: string;
  gameId: string;
  selection: string;
  market: string;
  decimalOdds: number | null;
  classification: string;
  frameworkState: string;
  frameworkScore: number | null;
  aiModel: string;
  aiRating: number;
  aiVerdict: string;
  rationale: string;
  status: string;
  profitUnits: number | null;
  settlementNote: string | null;
  game: any;
};

type Summary = {
  total: number;
  pending: number;
  settled: number;
  wins: number;
  losses: number;
  pushes: number;
  netUnits: number;
  roi: number | null;
};

const EMPTY_SUMMARY: Summary = { total: 0, pending: 0, settled: 0, wins: 0, losses: 0, pushes: 0, netUnits: 0, roi: null };

async function evaluateSlate(games: any[], selectedModel: string, signal: AbortSignal) {
  const results: any[] = [];
  let next = 0;
  const workers = Array.from({ length: Math.min(2, games.length) }, async () => {
    while (next < games.length) {
      const index = next++;
      const game = games[index];
      const model = selectedModel === 'auto' ? MODELS[index % MODELS.length] : selectedModel;
      try {
        const response = await fetch('/api/pick', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildPickerRequest(game, model)),
          signal,
        });
        const result = await response.json();
        if (response.ok && result.ok !== false) results.push({ gameId: game.id, result });
      } catch (error: any) {
        if (error?.name === 'AbortError') throw error;
      }
    }
  });
  await Promise.all(workers);
  return results;
}

export default function AiFinalPicksPage() {
  const [date, setDate] = useState(currentDisplayDate);
  const [model, setModel] = useState('auto');
  const [picks, setPicks] = useState<FinalPick[]>([]);
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async (targetDate: string) => {
    const response = await fetch(`/api/ai-final-picks?date=${targetDate}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to load AI final picks');
    setPicks(data.picks || []);
    setSummary(data.summary || EMPTY_SUMMARY);
  }, []);

  useEffect(() => {
    setMessage('');
    load(date).catch((error) => setMessage(error.message));
    return () => controller.current?.abort();
  }, [date, load]);

  const generate = async () => {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setLoading(true);
    setMessage('Loading WIB slate and reviewing eligible games…');
    try {
      const slateResponse = await fetch(`/api/slates/${date}?timezone=Asia%2FJakarta`, { signal: active.signal, cache: 'no-store' });
      const slate = await slateResponse.json();
      if (!slateResponse.ok) throw new Error(slate.error || 'Failed to load slate');
      if (!slate.games?.length) throw new Error(`No games found for ${date} WIB`);

      const results = await evaluateSlate(slate.games, model, active.signal);
      const saveResponse = await fetch('/api/ai-final-picks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, results }),
        signal: active.signal,
      });
      const saved = await saveResponse.json();
      if (!saveResponse.ok) throw new Error(saved.error || 'Failed to save final picks');
      setPicks(saved.picks || []);
      setSummary(saved.summary || EMPTY_SUMMARY);
      const externalReviews = results.filter((entry) => entry.result?.source === 'llm').length;
      setMessage(externalReviews
        ? `Reviewed ${slate.games.length} games; ${saved.picks.length} validated final picks saved.`
        : 'No external AI review was available. Check the server-side AI Picker configuration.');
    } catch (error: any) {
      if (error?.name !== 'AbortError') setMessage(error.message || 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const settle = async (id: string, outcome: string) => {
    const response = await fetch('/api/ai-final-picks', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, outcome }),
    });
    const data = await response.json();
    if (!response.ok) return setMessage(data.error || 'Settlement failed');
    await load(date);
    setMessage(`Settlement updated: ${outcome.toUpperCase()}`);
  };

  const parlays = useMemo(() => parlayRecommendations(picks), [picks]);

  return (
    <div style={{ padding: '1.5rem 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
        <div>
          <h1 className="page-title">⭐ AI Final Picks</h1>
          <p className="muted">AI-curated shortlist from validated Daily Slate evidence. Hard blocks remain NO BET.</p>
        </div>
        <button className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? 'Reviewing slate…' : 'Generate AI Final Picks'}
        </button>
      </div>

      <div className="card" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <button className="btn btn-ghost" onClick={() => setDate((value) => shiftDateOnly(value, -1))}>‹ Prev</button>
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} style={{ padding: '0.45rem', borderRadius: 6 }} />
        <button className="btn btn-ghost" onClick={() => setDate((value) => shiftDateOnly(value, 1))}>Next ›</button>
        <button className="btn btn-ghost" onClick={() => setDate(currentDisplayDate())}>Today (WIB)</button>
        <select value={model} onChange={(event) => setModel(event.target.value)} style={{ marginLeft: 'auto', padding: '0.5rem', borderRadius: 6 }}>
          <option value="auto">Auto model rotation</option>
          {MODELS.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>

      {message && <div className="card-sm" style={{ marginBottom: '1rem', color: message.includes('failed') || message.includes('No external') ? 'var(--amber-lt)' : '#cbd5e1' }}>{message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(145px,1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {[
          ['Final Picks', summary.total], ['Pending', summary.pending], ['Record', `${summary.wins}W-${summary.losses}L-${summary.pushes}P`],
          ['Net Units', `${summary.netUnits >= 0 ? '+' : ''}${summary.netUnits.toFixed(2)}u`], ['ROI', summary.roi == null ? '—' : `${summary.roi.toFixed(1)}%`],
        ].map(([label, value]) => <div className="card-sm" key={String(label)}><div className="muted" style={{ fontSize: '0.72rem' }}>{label}</div><div style={{ fontSize: '1.25rem', fontWeight: 800 }}>{value}</div></div>)}
      </div>

      <section className="card" style={{ marginBottom: '1.5rem', overflowX: 'auto' }}>
        <h2 style={{ marginBottom: '0.75rem' }}>Final Pick Shortlist</h2>
        {picks.length === 0 ? <p className="muted">No saved final picks. Generate a slate after AI provider configuration is available.</p> : (
          <table className="data-table">
            <thead><tr><th>Matchup</th><th>Pick</th><th>Odds</th><th>Source</th><th>AI Rating</th><th>Framework</th><th>Rationale</th></tr></thead>
            <tbody>{picks.map((pick) => <tr key={pick.id}>
              <td><strong>{pick.game.awayTeam.name} @ {pick.game.homeTeam.name}</strong><div className="muted">{formatWIB(pick.game.startTimeUtc, 'dd/MM HH:mm')} WIB</div></td>
              <td>{pick.selection}</td>
              <td className="mono">{pick.decimalOdds?.toFixed(2) ?? '—'}</td>
              <td><span className={`chip ${pick.classification === 'framework_confirmed' ? 'chip-t1' : 'chip-over'}`}>{pick.classification === 'framework_confirmed' ? 'Framework + AI' : 'AI-only'}</span></td>
              <td><strong>{pick.aiRating}/100</strong><div className="muted">{pick.aiVerdict}</div></td>
              <td>{pick.frameworkState}{pick.frameworkScore != null ? ` · ${pick.frameworkScore}` : ''}</td>
              <td style={{ maxWidth: 360 }}>{pick.rationale}</td>
            </tr>)}</tbody>
          </table>
        )}
      </section>

      <section className="card" style={{ marginBottom: '1.5rem', overflowX: 'auto' }}>
        <h2>Parlay Recommendations</h2>
        <p className="muted" style={{ marginBottom: '0.75rem' }}>Combinations use separate games and valid current decimal odds. Implied chance comes from multiplied market odds, not AI probability.</p>
        {parlays.length === 0 ? <p className="muted">At least two pending picks with valid odds are required.</p> : (
          <table className="data-table"><thead><tr><th>Parlay</th><th>Legs</th><th>Combined Odds</th><th>Market Implied</th></tr></thead>
            <tbody>{parlays.map((row) => <tr key={row.label}><td><strong>{row.label}</strong></td><td>{row.legs.map((leg) => leg.selection).join(' + ')}</td><td className="mono">{row.odds.toFixed(2)}</td><td>{row.implied.toFixed(1)}%</td></tr>)}</tbody>
          </table>
        )}
      </section>

      <section className="card" style={{ overflowX: 'auto' }}>
        <h2>Simple Settlement Tracker</h2>
        <p className="muted" style={{ marginBottom: '0.75rem' }}>Flat 1-unit tracking: win = odds − 1, loss = −1, push/void = 0.</p>
        {picks.length === 0 ? <p className="muted">No picks to settle.</p> : (
          <table className="data-table"><thead><tr><th>Game</th><th>Pick</th><th>Final Score</th><th>Status</th><th>Profit</th><th>Settle</th></tr></thead>
            <tbody>{picks.map((pick) => <tr key={pick.id}>
              <td>{pick.game.awayTeam.abbreviation} @ {pick.game.homeTeam.abbreviation}</td><td>{pick.selection}</td>
              <td>{pick.game.gameResult ? `${pick.game.gameResult.awayScore}-${pick.game.gameResult.homeScore}` : 'Not final'}</td>
              <td><strong>{pick.status.toUpperCase()}</strong></td><td className="mono">{pick.profitUnits == null ? '—' : `${pick.profitUnits >= 0 ? '+' : ''}${pick.profitUnits.toFixed(2)}u`}</td>
              <td><select value={pick.status} onChange={(event) => settle(pick.id, event.target.value)}>
                {['pending', 'win', 'loss', 'push', 'void'].map((status) => <option key={status} value={status}>{status.toUpperCase()}</option>)}
              </select></td>
            </tr>)}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
