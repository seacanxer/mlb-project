'use client';
import { useEffect, useMemo, useState } from 'react';
import type { DetailedMatch, ForecastPick, Market } from '@/lib/fc/types';
import { forecastPicks, isCardVisible, isValue, laneLabel, matchKey, pickLabel, PREDICTION_MARKETS, reasonLabel, TIER_LABEL } from '@/lib/fc/predictions';
import { formatEv, formatOdds, formatProb } from '@/lib/fc/format';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { splitLeague } from '@/lib/fc/grouping';
import { SecondaryPredictionPanel } from './SecondaryPredictionPanel';
import { fcPost } from '@/lib/fc/client';
import { isActionable } from '@/lib/fc/quant';

export type BoardView = 'all' | 'ready' | 'model' | 'value' | 'unavailable' | 'saved';
type Choice = { match: DetailedMatch; pick: ForecastPick; id: string };
type LockedChoice = Choice & { lockedAt: string; settlementId?: number };
type LockedParlay = { id: number; odds: number; lockedAt: string; status: string; profit?: number | null; legs: { source_match_id: string; market: string; pick: string; home: string; away: string }[] };
type LockSingleResponse = { status?: string; message?: string; bet_id: number; locked_at: string };
type LockBatchResponse = { status?: string; message?: string; locked_at: string; parlay_id: number; odds: number; locks?: { id: string; bet_id: number; locked_at: string }[] };
const choiceId = (match: DetailedMatch, pick: ForecastPick) => `${matchKey(match)}|${pick.market}|${pick.pick}`;
const STORAGE_KEY = 'fc-prediction-watchlist-v2';
const LOCK_STORAGE_KEY = 'fc-prediction-locked-v1';
const PAGE_SIZE = 24;

const TOP_PICK_MIN_ODDS = 1.4;

/** Coin-flip markets (strongest side < 55%) are shown as balanced, not as a pick. */
function isNoLean(pick: ForecastPick): boolean {
  if (pick.display_status) return pick.display_status === 'no_lean';
  return !isValue(pick) && pick.confidence != null && pick.confidence < 0.55;
}

function payoutBreakdown(p: NonNullable<ForecastPick['payout']>): string {
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const parts = [`Menang ${pct(p.full_win + p.half_win)}`];
  if (p.push > 0.005) parts.push(`Refund ${pct(p.push)}`);
  parts.push(`Kalah ${pct(p.full_loss + p.half_loss)}`);
  return parts.join(' · ');
}

function scenarioLine(match: DetailedMatch): string {
  const s = match.analysis!.scenario!;
  const home = String(match.info.home ?? 'Home'), away = String(match.info.away ?? 'Away');
  const homeWin = `${home} menang ${formatProb(s.home_win)}`;
  const awayWin = `${away} menang ${formatProb(s.away_win)}`;
  const fav = s.favourite === 'home'
    ? `${homeWin} (selisih 1: ${formatProb(s.home_by1)} · ≥2: ${formatProb(s.home_by2_plus)}) · Seri ${formatProb(s.draw)} · ${awayWin}`
    : `${awayWin} (selisih 1: ${formatProb(s.away_by1)} · ≥2: ${formatProb(s.away_by2_plus)}) · Seri ${formatProb(s.draw)} · ${homeWin}`;
  return `Skenario skor: ${fav}`;
}

/** Explains a handicap on the side opposite the 1X2 projection (e.g. Juventus to win + Lazio +1). */
function handicapNote(ah: ForecastPick, one: ForecastPick | undefined, match: DetailedMatch): string | null {
  if (!one || isNoLean(one) || !['home', 'away'].includes(String(one.side)) || ah.side === one.side) return null;
  const s = match.analysis?.scenario;
  const fav = one.side === 'home' ? match.info.home : match.info.away;
  const by1 = s ? (one.side === 'home' ? s.home_by1 : s.away_by1) : null;
  const by2 = s ? (one.side === 'home' ? s.home_by2_plus : s.away_by2_plus) : null;
  const detail = by1 != null && by2 != null ? ` (selisih 1 gol ${formatProb(by1)}, ≥2 gol ${formatProb(by2)})` : '';
  return `Bukan kontradiksi: ${fav} diunggulkan menang, tapi kemungkinan menang tipis${detail}. Menang 1 gol = 1X2 menang, handicap ini refund.`;
}

function isHighConfidence(pick: ForecastPick): boolean {
  return pick.confidence_tier === 'TINGGI' || (pick.confidence != null && pick.confidence >= 0.65);
}

function isTopQuality(pick: ForecastPick): boolean {
  const odds = Number(pick.odds);
  if (!Number.isFinite(odds) || odds < TOP_PICK_MIN_ODDS) return false;
  // Top Picks only from big/major competitions (engine league_tier 1-2).
  if ((pick.league_tier ?? 3) > 2) return false;
  return isHighConfidence(pick) && isActionable(pick);
}

function valueScreenPick(match: DetailedMatch): ForecastPick | null {
  if (match.analysis?.status !== 'ready' || !match.analysis.quote_captured_at) return null;
  const candidates = forecastPicks(match).filter((pick) => {
    const odds = Number(pick.odds);
    return ['1x2', 'ah', 'ou', 'btts'].includes(pick.market) && Number.isFinite(odds) && odds >= 1.3 && isActionable(pick);
  });
  if (!candidates.length) return null;
  return [...candidates].sort((a, b) => {
    const aValue = isValue(a) ? 1 : 0;
    const bValue = isValue(b) ? 1 : 0;
    return bValue - aValue || (b.ev ?? -1) - (a.ev ?? -1) || (b.confidence ?? 0) - (a.confidence ?? 0);
  })[0];
}

function valueScreenUncertain(pick: ForecastPick): boolean {
  return !isValue(pick) || pick.confidence_source !== 'sharp' || (pick.confidence ?? 0) < 0.65;
}

function choicesFor(match: DetailedMatch, valueOnly = false, filter: 'top' | 'high' | 'all' = 'all'): ForecastPick[] {
  const screened = valueOnly ? valueScreenPick(match) : null;
  const picks = valueOnly ? (screened ? [screened] : []) : forecastPicks(match);
  if (filter === 'top') return picks.filter(isTopQuality);
  if (filter === 'high') return picks.filter(isHighConfidence);
  return picks;
}

function PredictionCard({ match, market, valueOnly, pickFilter, saved, lockedIds, onToggle }: {
  match: DetailedMatch; market: string; valueOnly: boolean; pickFilter: 'top' | 'high' | 'all'; saved: string[]; lockedIds: Set<string>; onToggle: (m: DetailedMatch, p: ForecastPick) => void;
}) {
  const info = match.info;
  const projections = choicesFor(match, valueOnly, pickFilter);
  const goals = match.analysis?.model_goals;
  const available = projections.length > 0;
  const reasons = match.analysis?.reason_codes.length ? match.analysis.reason_codes : ['RESCAN_REQUIRED'];
  const options = (pickFilter !== 'all' ? projections : (match.market_options ?? projections)).filter((p) => isCardVisible(p) && (market === 'all' || p.market === market));
  const cells = PREDICTION_MARKETS.filter((m) => ['1x2', 'ah', 'ou', 'btts'].includes(m.key) && projections.some((p) => p.market === m.key) && (market === 'all' || m.key === market));
  const uncertain = valueOnly && projections[0] ? valueScreenUncertain(projections[0]) : false;
  return <article className={`prediction-card${available ? '' : ' prediction-card-empty'}${uncertain ? ' prediction-card-uncertain' : ''}`}>
    <header className="prediction-meta">
      <span className="prediction-league"><span aria-hidden="true">◈</span> {info.league || 'Liga belum tersedia'}</span>
      <time>{formatKickoffWIB(info.start_ts)}</time>
      <span className={`prediction-status ${available ? 'is-ready' : ''}`}>{uncertain ? 'Perlu review' : available ? laneLabel(match.analysis?.lane) : goals ? 'Tanpa pick layak' : 'Data belum lengkap'}</span>
    </header>
    <div className="prediction-main">
      <div className="prediction-teams">
        <div><span className="team-monogram" aria-hidden="true">{(info.home || '?').slice(0, 2).toUpperCase()}</span><strong>{info.home || 'Home —'}</strong></div>
        <span className="prediction-versus">VS</span>
        <div><span className="team-monogram team-away" aria-hidden="true">{(info.away || '?').slice(0, 2).toUpperCase()}</span><strong>{info.away || 'Away —'}</strong></div>
      </div>
      {match.analysis?.scenario && <p className="prediction-scenario">{scenarioLine(match)}</p>}
      {cells.length > 0 && <div className="prediction-market-grid" style={{ '--market-count': cells.length } as React.CSSProperties}>
        {cells.map(({ key, label }) => {
          const pick = projections.find((p) => p.market === key);
          const selected = pick && saved.includes(choiceId(match, pick));
          const locked = pick && lockedIds.has(choiceId(match, pick));
          const balanced = pick && isNoLean(pick);
          const ahNote = pick && key === 'ah' && !balanced ? handicapNote(pick, projections.find((p) => p.market === '1x2'), match) : null;
          return <div className={`prediction-market market-${key}`} key={key}>
            <div className="prediction-market-heading">{label}</div>
            {pick && balanced ? <div className="prediction-no-market prediction-balanced">
              <strong>Seimbang</strong>
              <small>Sisi terkuat hanya {formatProb(pick.confidence ?? pick.probability)} — tidak ada arah jelas</small>
              <span className="prediction-tag tier-rendah">Tanpa pick</span>
            </div> : pick ? <button type="button" className={`prediction-selection${selected ? ' is-saved' : ''}`} aria-pressed={Boolean(selected)} aria-label={`${locked ? 'Terkunci' : selected ? 'Hapus' : 'Simpan'} ${pickLabel(pick, match)}`} onClick={() => onToggle(match, pick)}>
              <strong>{pickLabel(pick, match)}</strong>
              <span className="prediction-odds">@{formatOdds(pick.odds)} <span>{locked ? '🔒' : selected ? '✓' : '+'}</span></span>
              <small>Confidence {formatProb(pick.confidence ?? pick.probability)}</small>
              <small className="prediction-source" title="Kalibrasi dinilai per versi, sumber, dan market pada Kinerja Model.">
                {pick.confidence_label ?? 'Sumber belum tercatat'}
              </small>
              {key === 'ah' && pick.payout && <small className="prediction-source">{payoutBreakdown(pick.payout)}</small>}
              {ahNote && <small className="prediction-source prediction-note">{ahNote}</small>}
              {pick.confidence_source !== 'market' && pick.market_confidence != null && <small className="prediction-source">Pasar 1xbit {formatProb(pick.market_confidence)}{pick.confidence_source === 'sharp' && pick.model_confidence != null ? ` · Model ${formatProb(pick.model_confidence)}` : ''}</small>}
              <span className={`prediction-tag ${isValue(pick) ? 'is-value' : ''} tier-${(pick.confidence_tier ?? '').toLowerCase()}`}>{isValue(pick) ? 'Kandidat value' : valueOnly ? 'Belum cukup yakin' : TIER_LABEL[pick.confidence_tier ?? ''] ?? 'Proyeksi'}</span>
            </button> : <div className="prediction-no-market"><strong>—</strong><small>{match.analysis?.model_goals ? 'Tidak ada pick layak' : 'Menunggu data'}</small></div>}
          </div>;
        })}
      </div>}
    </div>
    <section className="prediction-goals" aria-label="Projection Goal dan proyeksi gol per tim">
      <div className="prediction-goals-title">Projection Goal</div>
      <div className="prediction-goal-value prediction-goal-total">
        <span>Total gol</span><strong>{goals ? (goals.home + goals.away).toFixed(2) : '—'}</strong>
      </div>
      <div className="prediction-goal-value">
        <span>{info.home || 'Home'} goal point</span><strong>{goals ? goals.home.toFixed(2) : '—'}</strong>
      </div>
      <div className="prediction-goal-value">
        <span>{info.away || 'Away'} goal point</span><strong>{goals ? goals.away.toFixed(2) : '—'}</strong>
      </div>
    </section>
    {match.analysis?.secondary_markets && <SecondaryPredictionPanel secondary={match.analysis.secondary_markets} info={info} market={market} />}
    <div className="prediction-footer">
      {available ? <span>{laneLabel(match.analysis?.lane)}<span className="prediction-divider">/</span><span>{match.analysis?.reason_codes?.length ? reasonLabel(match.analysis.reason_codes[0]) : 'Ada kandidat value'}</span></span> : <span>{reasonLabel(reasons[0])}</span>}
      {available && <span className="prediction-hint">Klik pilihan untuk menyimpan</span>}
    </div>
    <details className="prediction-details">
      <summary>{available ? 'Detail analisis & alternatif line' : 'Lihat kebutuhan data'} <span aria-hidden="true">↗</span></summary>
      <div className="prediction-explanation">
        <p>{match.analysis?.model_goals ? 'Confidence menunjukkan probabilitas harga W/(W+L). Pada handicap dan total dengan push atau hasil setengah, angka ini berbeda dari peluang payout positif. Metrik quant menyimpan kedua definisi secara terpisah. Kandidat value memerlukan EV positif dan bukti harga sharp yang masih berlaku. Kalibrasi dinilai per versi, sumber, dan market.' : reasons.map(reasonLabel).join(' ')}</p>
        <p>Official: {reasonLabel(match.analysis?.official_reason || 'MODEL_NOT_VALIDATED')} Probabilitas menang menghitung menang penuh dan setengah menang; EV memperhitungkan push dan hasil setengah.</p>
        {match.analysis?.quote_captured_at && <p>Odds 1xbit diambil: {formatKickoffWIB(match.analysis.quote_captured_at)}. Harga dapat berubah.</p>}
        {match.analysis?.model_data_as_of && <p>Hasil terakhir pada data model: {formatKickoffWIB(match.analysis.model_data_as_of)}.</p>}
        {available && match.analysis?.reason_codes.map((code) => <p key={code}>{reasonLabel(code)}</p>)}
      </div>
      {options.length > 0 && <div className="prediction-options-wrap"><table className="prediction-options"><thead><tr><th>Pasar / pilihan</th><th>Odds</th><th>P(menang)</th><th>Fair odds</th><th>EV</th><th>Status</th><th>Simpan</th></tr></thead><tbody>{options.map((p, i) => <tr key={`${p.market}-${p.pick}-${i}`}>
        <td>{p.market.toUpperCase()} · {pickLabel(p, match)}</td><td>{formatOdds(p.odds)}</td><td>{formatProb(p.probability)}</td><td>{formatOdds(p.fair_odds)}</td><td className={(p.ev ?? 0) > 0 ? 'positive' : ''}>{formatEv(p.ev)}</td>
        <td>{isValue(p) ? 'Kandidat value' : p.gate_reasons?.map(reasonLabel).join(' ') || 'Proyeksi model'}</td>
        <td><button type="button" onClick={() => onToggle(match, p)} aria-label={`${lockedIds.has(choiceId(match, p)) ? 'Terkunci' : 'Simpan alternatif'} ${pickLabel(p, match)}`} aria-pressed={saved.includes(choiceId(match, p))}>{lockedIds.has(choiceId(match, p)) ? '🔒' : saved.includes(choiceId(match, p)) ? '✓' : '+'}</button></td>
      </tr>)}</tbody></table></div>}
    </details>
  </article>;
}

const TOP_MARKET_TERMS = ['premier league', 'la liga', 'bundesliga', 'serie a', 'ligue 1', 'champions league', 'europa league', 'conference league', 'uefa champions', 'uefa europa', 'uefa conference', 'uefa nations league', 'nations league', 'j1 league', 'j league', 'k league', 'liga 1', 'indonesia', 'afc champions'];
function isTopMarketLeague(match: DetailedMatch): boolean {
  if (match.info.league_tier != null) return match.info.league_tier <= 2;
  const { country, league } = splitLeague(match.info.league);
  const text = `${country} ${league}`.toLowerCase();
  return TOP_MARKET_TERMS.some((term) => text.includes(term));
}

export function PredictionBoard({ matches, initialView = 'all', marketScope = 'all' }: { matches: DetailedMatch[]; initialView?: BoardView; marketScope?: 'all' | 'top' }) {
  const [view, setView] = useState<BoardView>(initialView);
  const [topMode, setTopMode] = useState<'top' | 'high' | 'all'>(initialView === 'model' ? 'top' : 'all');
  const [search, setSearch] = useState('');
  const [league, setLeague] = useState('all');
  const [market, setMarket] = useState<string>('all');
  const [sort, setSort] = useState('time');
  const [page, setPage] = useState(0);
  const [saved, setSaved] = useState<string[]>([]);
  const [lockedChoices, setLockedChoices] = useState<LockedChoice[]>([]);
  const [parlays, setParlays] = useState<LockedParlay[]>([]);
  const [locking, setLocking] = useState(false);
  const [operatorToken, setOperatorToken] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    try { const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); if (Array.isArray(stored)) setSaved(stored.filter((v): v is string => typeof v === 'string')); } catch { /* Storage is optional. */ }
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(LOCK_STORAGE_KEY) || '[]');
      if (Array.isArray(stored)) setLockedChoices(stored.filter((v): v is LockedChoice => Boolean(v && typeof v.id === 'string' && v.match?.info && v.pick && typeof v.lockedAt === 'string')));
    } catch { /* Storage is optional. */ }
    try { const token = sessionStorage.getItem('fc-lock-operator-token') || ''; setOperatorToken(token); } catch { /* Session storage is optional. */ }
  }, []);
  useEffect(() => {
    if (!operatorToken) return;
    let active = true;
    fetch('/api/fc/locks', { headers: { Authorization: `Bearer ${operatorToken}` }, cache: 'no-store' })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || 'Gagal memuat lock settlement.');
        if (!active) return;
        const server = (result.locks || []) as LockedChoice[];
        setParlays((result.parlays || []) as LockedParlay[]);
        setLockedChoices((previous) => {
          const ids = new Set(server.map((choice) => choice.id));
          const next = [...previous.filter((choice) => !choice.settlementId && !ids.has(choice.id)), ...server];
          try { localStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify(next)); } catch { /* Session state remains visible. */ }
          return next;
        });
      })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : 'Gagal memuat lock settlement.'); });
    return () => { active = false; };
  }, [operatorToken]);
  const updateSaved = (next: string[]) => { setSaved(next); try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { setMessage('Pilihan tersimpan untuk sesi ini; penyimpanan perangkat tidak tersedia.'); } };
  const updateLocked = (next: LockedChoice[]) => { setLockedChoices(next); try { localStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify(next)); } catch { setMessage('Lock hanya bertahan selama sesi ini; penyimpanan perangkat tidak tersedia.'); } };
  const lockedIds = new Set(lockedChoices.filter((choice) => choice.settlementId).map((choice) => choice.id));
  const toggle = (m: DetailedMatch, p: ForecastPick) => {
    if (!['1x2', 'ah', 'ou', 'btts'].includes(p.market)) { setMessage('Pilihan corner/kartu masih berupa proyeksi dan belum dapat dikunci.'); return; }
    const id = choiceId(m, p);
    if (lockedIds.has(id)) { setMessage('Pilihan ini terkunci. Buka lock di daftar pilihan sebelum mengubahnya.'); return; }
    const prefix = `${matchKey(m)}|${p.market}|`;
    if (lockedChoices.some((choice) => choice.settlementId && choice.id.startsWith(prefix))) { setMessage('Pasar ini sudah dikunci ke settlement.'); return; }
    updateSaved(saved.includes(id) ? saved.filter((v) => v !== id) : [...saved.filter((v) => !v.startsWith(prefix)), id]);
  };
  const lock = async (choice: Choice) => {
    if (!operatorToken) { setMessage('Hubungkan operator di halaman Hasil & ROI sebelum mengunci pick.'); return; }
    const matchId = choice.match.info.match_id;
    if (!matchId) { setMessage('Fixture tidak memiliki ID provider yang bisa diverifikasi.'); return; }
    try {
      const result = await fcPost<LockSingleResponse>('/api/fc/locks',
        { match_id: String(matchId), market: choice.pick.market, pick: choice.pick.pick, odds: choice.pick.odds },
        { Authorization: `Bearer ${operatorToken}` });
      if (result.status !== 'locked') throw new Error(result.message || 'Lock settlement gagal.');
      updateLocked([...lockedChoices.filter((item) => item.id !== choice.id), {
        id: choice.id, match: { info: { ...choice.match.info } }, pick: { ...choice.pick },
        lockedAt: result.locked_at || new Date().toISOString(), settlementId: result.bet_id,
      }]);
      setMessage(`Pick masuk settlement sebagai #${result.bet_id}. Odds @${formatOdds(choice.pick.odds)} dikunci.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lock settlement gagal.'); }
  };
  const lockBatch = async (mode: 'singles' | 'parlay') => {
    if (!operatorToken) { setMessage('Hubungkan operator di halaman Hasil & ROI sebelum mengunci pilihan.'); return; }
    const choices = savedChoices.filter((choice) => !lockedIds.has(choice.id));
    if (mode === 'parlay' && choices.length < 2) { setMessage('Parlay membutuhkan sedikitnya dua pilihan belum dikunci.'); return; }
    if (!choices.length) { setMessage('Tidak ada pilihan baru untuk dikunci.'); return; }
    if (choices.some((choice) => !choice.match.info.match_id)) { setMessage('Ada fixture tanpa ID provider.'); return; }
    setLocking(true);
    try {
      const result = await fcPost<LockBatchResponse>('/api/fc/locks',
        { mode, choices: choices.map((choice) => ({ match_id: String(choice.match.info.match_id), market: choice.pick.market, pick: choice.pick.pick, odds: choice.pick.odds })) },
        { Authorization: `Bearer ${operatorToken}` });
      if (result.status !== 'locked') throw new Error(result.message || 'Batch lock gagal.');
      if (mode === 'singles') {
        const byId = new Map((result.locks as { id: string; bet_id: number; locked_at: string }[]).map((item) => [item.id, item]));
        updateLocked([...lockedChoices.filter((item) => !byId.has(item.id)), ...choices.map((choice) => ({
          ...choice, lockedAt: byId.get(choice.id)!.locked_at, settlementId: byId.get(choice.id)!.bet_id,
        }))]);
        setMessage(`${choices.length} pick dikunci ke settlement sebagai single.`);
      } else {
        const slip: LockedParlay = { id: result.parlay_id, odds: result.odds, lockedAt: result.locked_at,
          status: 'pending', legs: choices.map((choice) => ({ source_match_id: String(choice.match.info.match_id),
            market: choice.pick.market, pick: choice.pick.pick, home: choice.match.info.home || '', away: choice.match.info.away || '' })) };
        setParlays((previous) => [slip, ...previous.filter((item) => item.id !== slip.id)]);
        setMessage(`Parlay #${slip.id} dikunci dengan ${choices.length} leg. Odds gabungan teoretis @${formatOdds(slip.odds)}.`);
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Batch lock gagal.'); }
    finally { setLocking(false); }
  };
  const scopedMatches = marketScope === 'top' ? matches.filter(isTopMarketLeague) : matches;
  const savedChoices = useMemo(() => {
    const unique = new Map<string, Choice>();
    matches.forEach((match) => [...forecastPicks(match), ...(match.qualified_picks ?? []), ...(match.market_options ?? [])].forEach((pick) => {
      const id = choiceId(match, pick); if (saved.includes(id)) unique.set(id, { match, pick, id });
    }));
    lockedChoices.forEach((choice) => unique.set(choice.id, choice));
    return [...unique.values()];
  }, [matches, saved, lockedChoices]);
  const leagues = useMemo(() => [...new Set(matches.map((m) => m.info.league).filter((v): v is string => Boolean(v)))].sort(), [matches]);
  const ready = matches.filter((m) => forecastPicks(m).length > 0).length;
  const scopedReady = scopedMatches.filter((m) => forecastPicks(m).length > 0).length;
  const topMatches = scopedMatches.filter((m) => choicesFor(m, false, 'top').length > 0);
  const highMatches = scopedMatches.filter((m) => choicesFor(m, false, 'high').length > 0);
  const values = matches.reduce((n, m) => n + (m.qualified_picks ?? []).filter(isValue).length, 0);
  const unsupportedLeagues = matches.filter((m) => m.analysis?.reason_codes?.includes('LEAGUE_MODEL_UNAVAILABLE')).length;
  const unmatchedTeams = matches.filter((m) => m.analysis?.reason_codes?.includes('TEAM_UNMATCHED')).length;
  const selectedKeys = new Set(savedChoices.map(({ match }) => matchKey(match)));
  const unavailableReasons = new Map<string, number>();
  matches.filter((m) => !forecastPicks(m).length).forEach((m) => (m.analysis?.reason_codes?.length ? m.analysis.reason_codes : ['RESCAN_REQUIRED']).forEach((code) => unavailableReasons.set(code, (unavailableReasons.get(code) ?? 0) + 1)));
  const filtered = scopedMatches.filter((m) => {
    const picks = choicesFor(m, view === 'value', view === 'model' ? topMode : 'all');
    if ((view === 'ready' || view === 'model') && !picks.length) return false;
    if (view === 'value' && !picks.length) return false;
    if (view === 'unavailable' && forecastPicks(m).length) return false;
    if (view === 'saved' && !selectedKeys.has(matchKey(m))) return false;
    if (league !== 'all' && m.info.league !== league) return false;
    if (market !== 'all' && !picks.some((p) => p.market === market)) return false;
    const hay = `${m.info.home} ${m.info.away} ${m.info.league}`.toLowerCase();
    return hay.includes(search.trim().toLowerCase());
  }).sort((a, b) => sort === 'value' ? Math.max(0, ...(b.qualified_picks ?? []).map((p) => p.ev ?? 0)) - Math.max(0, ...(a.qualified_picks ?? []).map((p) => p.ev ?? 0)) : (Number(a.info.league_tier ?? 3) - Number(b.info.league_tier ?? 3)) || Number(a.info.start_ts || 0) - Number(b.info.start_ts || 0));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const activePage = Math.min(page, pages - 1);
  const changeView = (next: BoardView) => { setView(next); setPage(0); };
  const copy = async () => {
    try { await navigator.clipboard.writeText(savedChoices.map(({ match, pick, id }) => `${match.info.home} vs ${match.info.away} | ${pickLabel(pick, match)} @${formatOdds(pick.odds)} | EV ${formatEv(pick.ev)} | ${formatKickoffWIB(match.info.start_ts)} | ${lockedIds.has(id) ? 'Dikunci manual' : isValue(pick) ? 'Kandidat value' : 'Proyeksi'}`).join('\n')); setMessage('Ringkasan berhasil disalin.'); } catch { setMessage('Clipboard tidak tersedia. Pilihan tetap tersimpan di daftar.'); }
  };

  return <>
    <div className="prediction-stats">
      <div><span>Pertandingan mendatang</span><strong>{matches.length}</strong><small>Jendela scan 24 jam</small></div>
      <div><span>Siap dianalisis</span><strong>{ready}<em>match</em></strong><small>Memiliki hasil model</small></div>
      <div><span>Kandidat value</span><strong className="positive">{values}</strong><small>Belum berstatus Official</small></div>
      <div><span>Perlu data tambahan</span><strong>{matches.length - ready}</strong><small>Alasan tersedia per match</small></div>
    </div>
    {ready === 0 && matches.length > 0 && <p role="status" className="prediction-feedback">Belum ada pertandingan dengan proyeksi model pada jadwal ini. {unsupportedLeagues} pertandingan berasal dari liga tanpa model{unmatchedTeams ? `; ${unmatchedTeams} pertandingan memiliki tim yang belum cocok dengan histori` : ''}. Jadwal tetap ditampilkan agar cakupan dapat diperiksa.</p>}
    {view === 'unavailable' && unavailableReasons.size > 0 && <div className="prediction-data-summary"><strong>Penyebab data belum cukup</strong><ul>{[...unavailableReasons].sort((a, b) => b[1] - a[1]).map(([code, count]) => <li key={code}><b>{count}</b> {reasonLabel(code)}</li>)}</ul></div>}
    <div className="prediction-workspace">
      <section className="prediction-content" aria-label="Daftar Prediksi Pertandingan">
        <div className="prediction-view-tabs" role="group" aria-label="Jenis hasil">
          {([['all', 'Semua pertandingan'], ['model', `Pilihan model (${scopedReady})`], ['value', 'Kandidat value'], ['unavailable', 'Perlu data'], ['saved', `Tersimpan (${savedChoices.length})`]] as [BoardView, string][]).map(([key, label]) => <button key={key} type="button" aria-pressed={view === key} onClick={() => { changeView(key); if (key === 'model') setTopMode('top'); }}>{label}</button>)}
        </div>
        {view === 'model' && <div className="prediction-top-subnav" role="group" aria-label="Filter Top Picks"><button type="button" aria-pressed={topMode === 'top'} onClick={() => { setTopMode('top'); setPage(0); }}>Top Picks ({topMatches.length})</button><button type="button" aria-pressed={topMode === 'high'} onClick={() => { setTopMode('high'); setPage(0); }}>Confidence tinggi ({highMatches.length})</button><button type="button" aria-pressed={topMode === 'all'} onClick={() => { setTopMode('all'); setPage(0); }}>Semua pilihan model ({scopedReady})</button><span>Top Picks: value terverifikasi + confidence tinggi + odds minimum 1.40 · confidence tinggi ≥ 65%</span></div>}
        <div className="prediction-filters">
          <label className="prediction-search"><span>Cari pertandingan</span><input type="search" placeholder="Cari tim atau liga…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} /></label>
          <label><span>Liga</span><select value={league} onChange={(e) => { setLeague(e.target.value); setPage(0); }}><option value="all">Semua liga</option>{leagues.map((l) => <option key={l}>{l}</option>)}</select></label>
          <label><span>Urutkan</span><select value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }}><option value="time">Kickoff terdekat</option><option value="value">EV tertinggi</option></select></label>
        </div>
        <div className="prediction-list-heading"><div><h2>Daftar Prediksi Pertandingan</h2><p>{filtered.length} pertandingan · waktu Indonesia Barat</p></div><div className="prediction-market-tabs" role="group" aria-label="Market"><button type="button" aria-pressed={market === 'all'} onClick={() => { setMarket('all'); setPage(0); }}>Semua</button>{PREDICTION_MARKETS.map((m) => <button key={m.key} type="button" aria-pressed={market === m.key} onClick={() => { setMarket(m.key); setPage(0); }}>{m.label}</button>)}</div></div>
        <div className="prediction-list">{filtered.slice(activePage * PAGE_SIZE, (activePage + 1) * PAGE_SIZE).map((m) => <PredictionCard key={matchKey(m)} match={m} market={market} valueOnly={view === 'value'} pickFilter={view === 'model' ? topMode : 'all'} saved={saved} lockedIds={lockedIds} onToggle={toggle} />)}</div>
        {!filtered.length && <div className="prediction-empty"><span aria-hidden="true">⌕</span><h3>{view === 'value' ? 'Belum ada kandidat value' : view === 'model' ? 'Belum ada pilihan model' : 'Tidak ada pertandingan untuk filter ini'}</h3><p>{view === 'value' ? 'Lihat tab Pilihan model untuk proyeksi pertandingan. Kandidat value hanya muncul bila liga, tim, odds, dan EV memenuhi syarat.' : 'Coba liga lain atau tampilkan semua pertandingan.'}</p><button type="button" onClick={() => { setSearch(''); setLeague('all'); setMarket('all'); changeView('all'); }}>Reset filter</button></div>}
        {pages > 1 && <nav className="prediction-pagination" aria-label="Halaman pertandingan"><button disabled={activePage === 0} onClick={() => setPage(activePage - 1)}>← Sebelumnya</button><span>{activePage + 1} / {pages}</span><button disabled={activePage + 1 >= pages} onClick={() => setPage(activePage + 1)}>Berikutnya →</button></nav>}
      </section>
      <aside className="prediction-sidebar">
        <section className="prediction-watchlist"><header><div><span className="prediction-eyebrow">PILIHAN ANDA</span><h2>Watchlist pertandingan</h2></div><button type="button" disabled={!saved.some((id) => !lockedIds.has(id))} onClick={() => updateSaved(saved.filter((id) => lockedIds.has(id)))}>Reset</button></header>
          {!operatorToken && <p className="watchlist-note">Hubungkan operator di <a href="/fc/results">Hasil &amp; ROI</a> untuk mengunci pilihan.</p>}
          {!savedChoices.length ? <div className="watchlist-empty"><span aria-hidden="true">☆</span><p>Mulai dari satu pilihan.</p><small>Klik pasar pada kartu pertandingan untuk menyimpannya di sini.</small></div> : <ul>{savedChoices.map((choice) => { const { match, pick, id } = choice; const locked = lockedChoices.find((item) => item.id === id); const confirmed = Boolean(locked?.settlementId); const slipIds = parlays.filter((slip) => slip.legs.some((leg) => `${leg.source_match_id}|${leg.market}|${leg.pick}` === id)).map((slip) => slip.id); return <li key={id}>{!locked && <button type="button" className="watchlist-remove" aria-label={`Hapus ${pickLabel(pick, match)}`} onClick={() => updateSaved(saved.filter((v) => v !== id))}>×</button>}<strong>{match.info.home} vs {match.info.away}</strong><span>{pickLabel(pick, match)} <b>@{formatOdds(pick.odds)}</b></span><small>{formatKickoffWIB(match.info.start_ts)}</small><div className="watchlist-lock-row"><span>{confirmed ? `🔒 Settlement single #${locked?.settlementId} · ${new Date(locked!.lockedAt).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' })} WIB` : locked ? 'Lock lama di perangkat · belum masuk settlement' : slipIds.length ? `🔒 Parlay #${slipIds.join(', #')}` : 'Belum dikunci'}</span>{!confirmed && <button type="button" onClick={() => void lock(choice)}>Kunci sebagai single</button>}</div>{locked && !confirmed && <button type="button" className="watchlist-legacy-remove" onClick={() => { updateLocked(lockedChoices.filter((item) => item.id !== id)); updateSaved(saved.filter((item) => item !== id)); }}>Hapus lock lama</button>}</li>; })}</ul>}
          <div className="watchlist-total"><span>Total pilihan</span><strong>{savedChoices.length} · {lockedChoices.filter((choice) => choice.settlementId).length} single · {parlays.length} parlay</strong></div>
          <div className="watchlist-batch-actions"><button type="button" disabled={locking || !savedChoices.some((choice) => !lockedIds.has(choice.id))} onClick={() => void lockBatch('singles')}>Kunci semua sebagai single</button><button type="button" disabled={locking || savedChoices.filter((choice) => !lockedIds.has(choice.id)).length < 2} onClick={() => void lockBatch('parlay')}>Kunci sebagai parlay</button></div>
          {parlays.length > 0 && <div className="watchlist-parlays"><strong>Parlay terkunci</strong>{parlays.slice(0, 5).map((slip) => <p key={slip.id}>#{slip.id} · {slip.legs.length} leg · @{formatOdds(slip.odds)} · {slip.status}{slip.profit != null ? ` · ${slip.profit > 0 ? '+' : ''}${slip.profit} unit` : ''}</p>)}</div>}
          <p className="watchlist-note">Single dan parlay dicatat serta dihitung terpisah. Lock final sebelum kickoff. Odds parlay adalah perkalian teoretis; beberapa pilihan dalam satu match dapat berkorelasi dan mungkin tidak tersedia sebagai parlay di bookmaker. Lock manual tetap bukan Official.</p><button type="button" className="prediction-copy" disabled={!savedChoices.length} onClick={copy}>Salin ringkasan pilihan ↗</button><p role="status" className="prediction-feedback">{message}</p>
        </section>
        <section className="prediction-guide"><span className="prediction-eyebrow">MEMBACA HASIL</span><h3>Analisis dan kandidat</h3><p><b>Kandidat value</b> hanya muncul bila odds 1xbit lebih tinggi dari harga wajar referensi sharp (Pinnacle, tanpa margin) minimal 2%, dengan odds 1,50–5,00. Tanpa harga referensi tidak ada kandidat value. Kandidat ini belum tervalidasi sebagai Official.</p><p><b>Proyeksi</b> menampilkan arah model untuk pasar lain dan tidak otomatis menjadi pick.</p><p>Hingga dua kandidat dari market berbeda dapat muncul untuk satu match.</p><p className="prediction-guide-foot">Kandidat dicatat untuk evaluasi prospektif.</p></section>
      </aside>
    </div>
  </>;
}
