'use client';
import { useEffect, useMemo, useState } from 'react';
import type { DetailedMatch, ForecastPick, Market } from '@/lib/fc/types';
import { forecastPicks, isValue, matchKey, pickLabel, PREDICTION_MARKETS, reasonLabel } from '@/lib/fc/predictions';
import { formatEv, formatOdds, formatProb } from '@/lib/fc/format';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { splitLeague } from '@/lib/fc/grouping';

export type BoardView = 'all' | 'ready' | 'value' | 'unavailable' | 'saved';
type Choice = { match: DetailedMatch; pick: ForecastPick; id: string };
const choiceId = (match: DetailedMatch, pick: ForecastPick) => `${matchKey(match)}|${pick.market}|${pick.pick}`;
const STORAGE_KEY = 'fc-prediction-watchlist-v2';
const PAGE_SIZE = 24;

function choicesFor(match: DetailedMatch, valueOnly = false): ForecastPick[] {
  return valueOnly ? (match.qualified_picks ?? []).filter(isValue) : forecastPicks(match);
}

function PredictionCard({ match, market, valueOnly, saved, onToggle }: {
  match: DetailedMatch; market: string; valueOnly: boolean; saved: string[]; onToggle: (m: DetailedMatch, p: ForecastPick) => void;
}) {
  const info = match.info;
  const projections = choicesFor(match, valueOnly);
  const goals = match.analysis?.model_goals;
  const available = projections.length > 0;
  const reasons = match.analysis?.reason_codes.length ? match.analysis.reason_codes : ['RESCAN_REQUIRED'];
  const options = (match.market_options ?? projections).filter((p) => market === 'all' || p.market === market);
  const cells = PREDICTION_MARKETS.filter((m) => market === 'all' || m.key === market);
  return <article className={`prediction-card${available ? '' : ' prediction-card-empty'}`}>
    <header className="prediction-meta">
      <span className="prediction-league"><span aria-hidden="true">◈</span> {info.league || 'Liga belum tersedia'}</span>
      <time>{formatKickoffWIB(info.start_ts)}</time>
      <span className={`prediction-status ${available ? 'is-ready' : ''}`}>{available ? 'Model tersedia' : 'Data belum lengkap'}</span>
    </header>
    <div className="prediction-main">
      <div className="prediction-teams">
        <div><span className="team-monogram" aria-hidden="true">{(info.home || '?').slice(0, 2).toUpperCase()}</span><strong>{info.home || 'Home —'}</strong></div>
        <span className="prediction-versus">VS</span>
        <div><span className="team-monogram team-away" aria-hidden="true">{(info.away || '?').slice(0, 2).toUpperCase()}</span><strong>{info.away || 'Away —'}</strong></div>
      </div>
      <div className="prediction-market-grid" style={{ '--market-count': cells.length } as React.CSSProperties}>
        {cells.map(({ key, label }) => {
          const pick = projections.find((p) => p.market === key);
          const selected = pick && saved.includes(choiceId(match, pick));
          return <div className={`prediction-market market-${key}`} key={key}>
            <div className="prediction-market-heading">{label}</div>
            {pick ? <button type="button" className={`prediction-selection${selected ? ' is-saved' : ''}`} aria-pressed={Boolean(selected)} aria-label={`${selected ? 'Hapus' : 'Simpan'} ${pickLabel(pick, match)}`} onClick={() => onToggle(match, pick)}>
              <strong>{pickLabel(pick, match)}</strong>
              <span className="prediction-odds">@{formatOdds(pick.odds)} <span>{selected ? '✓' : '+'}</span></span>
              <small>P(menang) {formatProb(pick.probability)}</small>
              <span className={`prediction-tag ${isValue(pick) ? 'is-value' : ''}`}>{isValue(pick) ? '🔒 Top Pick' : 'Proyeksi'}</span>
            </button> : <div className="prediction-no-market"><strong>—</strong><small>{available ? 'Pasar belum tersedia' : 'Menunggu data'}</small></div>}
          </div>;
        })}
      </div>
    </div>
    <div className="prediction-footer">
      {available ? <span>Gol model <b>{goals ? `${goals.home.toFixed(2)} – ${goals.away.toFixed(2)}` : '—'}</b><span className="prediction-divider">/</span>{match.analysis?.league_model || projections[0]?.league_model || 'Model liga'}<span className="prediction-divider">/</span><span>Belum tervalidasi</span></span> : <span>{reasonLabel(reasons[0])}</span>}
      {available && <span className="prediction-hint">Klik pilihan untuk menyimpan</span>}
    </div>
    <details className="prediction-details">
      <summary>{available ? 'Detail analisis & alternatif line' : 'Lihat kebutuhan data'} <span aria-hidden="true">↗</span></summary>
      <div className="prediction-explanation">
        <p>{available ? '1X2 menampilkan hasil paling mungkin. AH dan O/U memakai line dengan harga pasar paling seimbang; kedua sisi dihitung dengan model liga yang sama. Pilihan dengan EV tertinggi tersedia di tab Value.' : reasons.map(reasonLabel).join(' ')}</p>
        <p>Official: {reasonLabel(match.analysis?.official_reason || 'MODEL_NOT_VALIDATED')} Probabilitas menang menghitung menang penuh dan setengah menang; EV memperhitungkan push dan hasil setengah.</p>
        {match.analysis?.quote_captured_at && <p>Odds 1xbit diambil: {formatKickoffWIB(match.analysis.quote_captured_at)}. Harga dapat berubah.</p>}
        {match.analysis?.model_data_as_of && <p>Hasil terakhir pada data model: {formatKickoffWIB(match.analysis.model_data_as_of)}.</p>}
        {available && match.analysis?.reason_codes.map((code) => <p key={code}>{reasonLabel(code)}</p>)}
      </div>
      {options.length > 0 && <div className="prediction-options-wrap"><table className="prediction-options"><thead><tr><th>Pasar / pilihan</th><th>Odds</th><th>P(menang)</th><th>Fair odds</th><th>EV</th><th>Status</th><th>Simpan</th></tr></thead><tbody>{options.map((p, i) => <tr key={`${p.market}-${p.pick}-${i}`}>
        <td>{p.market.toUpperCase()} · {pickLabel(p, match)}</td><td>{formatOdds(p.odds)}</td><td>{formatProb(p.probability)}</td><td>{formatOdds(p.fair_odds)}</td><td className={p.ev > 0 ? 'positive' : ''}>{formatEv(p.ev)}</td>
        <td>{isValue(p) ? '🔒 Top Pick' : p.gate_reasons?.map(reasonLabel).join(' ') || 'Proyeksi model'}</td>
        <td><button type="button" onClick={() => onToggle(match, p)} aria-label={`Simpan alternatif ${pickLabel(p, match)}`} aria-pressed={saved.includes(choiceId(match, p))}>{saved.includes(choiceId(match, p)) ? '✓' : '+'}</button></td>
      </tr>)}</tbody></table></div>}
    </details>
  </article>;
}

const TOP_MARKET_TERMS = ['premier league', 'la liga', 'bundesliga', 'serie a', 'ligue 1', 'champions league', 'europa league', 'conference league', 'uefa champions', 'uefa europa', 'uefa conference', 'j1 league', 'j league', 'k league', 'liga 1', 'indonesia', 'afc champions'];
function isTopMarketLeague(match: DetailedMatch): boolean {
  const { country, league } = splitLeague(match.info.league);
  const text = `${country} ${league}`.toLowerCase();
  return TOP_MARKET_TERMS.some((term) => text.includes(term));
}

export function PredictionBoard({ matches, initialView = 'all', marketScope = 'all', valueOnly = false }: { matches: DetailedMatch[]; initialView?: BoardView; marketScope?: 'all' | 'top'; valueOnly?: boolean }) {
  const [view, setView] = useState<BoardView>(initialView);
  const [search, setSearch] = useState('');
  const [league, setLeague] = useState('all');
  const [market, setMarket] = useState<string>('all');
  const [sort, setSort] = useState('time');
  const [page, setPage] = useState(0);
  const [saved, setSaved] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  useEffect(() => {
    try { const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); if (Array.isArray(stored)) setSaved(stored.filter((v): v is string => typeof v === 'string')); } catch { /* Storage is optional. */ }
  }, []);
  const updateSaved = (next: string[]) => { setSaved(next); try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { setMessage('Pilihan tersimpan untuk sesi ini; penyimpanan perangkat tidak tersedia.'); } };
  const toggle = (m: DetailedMatch, p: ForecastPick) => {
    const id = choiceId(m, p);
    const prefix = `${matchKey(m)}|${p.market}|`;
    updateSaved(saved.includes(id) ? saved.filter((v) => v !== id) : [...saved.filter((v) => !v.startsWith(prefix)), id]);
  };
  const scopedMatches = marketScope === 'top' ? matches.filter(isTopMarketLeague) : matches;
  const savedChoices = useMemo(() => {
    const unique = new Map<string, Choice>();
    scopedMatches.forEach((match) => [...forecastPicks(match), ...(match.qualified_picks ?? []), ...(match.market_options ?? [])].forEach((pick) => {
      const id = choiceId(match, pick); if (saved.includes(id)) unique.set(id, { match, pick, id });
    }));
    return [...unique.values()];
  }, [scopedMatches, saved]);
  const leagues = useMemo(() => [...new Set(matches.map((m) => m.info.league).filter((v): v is string => Boolean(v)))].sort(), [matches]);
  const ready = matches.filter((m) => forecastPicks(m).length > 0).length;
  const values = matches.reduce((n, m) => n + (m.qualified_picks ?? []).filter(isValue).length, 0);
  const selectedKeys = new Set(savedChoices.map(({ match }) => matchKey(match)));
  const filtered = scopedMatches.filter((m) => {
    const picks = choicesFor(m, valueOnly || view === 'value');
    if (view === 'ready' && !picks.length) return false;
    if (view === 'value' && !picks.length) return false;
    if (view === 'unavailable' && forecastPicks(m).length) return false;
    if (view === 'saved' && !selectedKeys.has(matchKey(m))) return false;
    if (league !== 'all' && m.info.league !== league) return false;
    if (market !== 'all' && !picks.some((p) => p.market === market)) return false;
    const hay = `${m.info.home} ${m.info.away} ${m.info.league}`.toLowerCase();
    return hay.includes(search.trim().toLowerCase());
  }).sort((a, b) => sort === 'value' ? Math.max(0, ...(b.qualified_picks ?? []).map((p) => p.ev)) - Math.max(0, ...(a.qualified_picks ?? []).map((p) => p.ev)) : Number(a.info.start_ts || 0) - Number(b.info.start_ts || 0));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const activePage = Math.min(page, pages - 1);
  const changeView = (next: BoardView) => { setView(next); setPage(0); };
  const copy = async () => {
    try { await navigator.clipboard.writeText(savedChoices.map(({ match, pick }) => `${match.info.home} vs ${match.info.away} | ${pickLabel(pick, match)} @${formatOdds(pick.odds)} | EV ${formatEv(pick.ev)} | ${formatKickoffWIB(match.info.start_ts)} | ${isValue(pick) ? '🔒 Top Pick' : 'Proyeksi'}`).join('\n')); setMessage('Ringkasan berhasil disalin.'); } catch { setMessage('Clipboard tidak tersedia. Pilihan tetap tersimpan di daftar.'); }
  };

  return <>
    <div className="prediction-stats">
      <div><span>Pertandingan mendatang</span><strong>{matches.length}</strong><small>Fixture dari sumber utama</small></div>
      <div><span>Siap dianalisis</span><strong>{ready}<em>match</em></strong><small>Memiliki hasil model</small></div>
      <div><span>Top Picks</span><strong className="positive">{values}</strong><small>🔒 Auto-locked untuk ROI</small></div>
      <div><span>Perlu data tambahan</span><strong>{matches.length - ready}</strong><small>Alasan tersedia per match</small></div>
    </div>
    <div className="prediction-workspace">
      <section className="prediction-content" aria-label="Daftar Prediksi Pertandingan">
        <div className="prediction-view-tabs" role="group" aria-label="Jenis hasil">
          {([['all', 'Semua pertandingan'], ['ready', 'Ada analisis'], ['value', 'Top Picks 🔒'], ['unavailable', 'Perlu data'], ['saved', `Tersimpan (${savedChoices.length})`]] as [BoardView, string][]).map(([key, label]) => <button key={key} type="button" aria-pressed={view === key} onClick={() => changeView(key)}>{label}</button>)}
        </div>
        <div className="prediction-filters">
          <label className="prediction-search"><span>Cari pertandingan</span><input type="search" placeholder="Cari tim atau liga…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} /></label>
          <label><span>Liga</span><select value={league} onChange={(e) => { setLeague(e.target.value); setPage(0); }}><option value="all">Semua liga</option>{leagues.map((l) => <option key={l}>{l}</option>)}</select></label>
          <label><span>Urutkan</span><select value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }}><option value="time">Kickoff terdekat</option><option value="value">EV tertinggi</option></select></label>
        </div>
        <div className="prediction-list-heading"><div><h2>Daftar Prediksi Pertandingan</h2><p>{filtered.length} pertandingan · waktu Indonesia Barat</p></div><div className="prediction-market-tabs" role="group" aria-label="Market"><button type="button" aria-pressed={market === 'all'} onClick={() => { setMarket('all'); setPage(0); }}>Semua</button>{PREDICTION_MARKETS.map((m) => <button key={m.key} type="button" aria-pressed={market === m.key} onClick={() => { setMarket(m.key); setPage(0); }}>{m.label}</button>)}</div></div>
        <div className="prediction-list">{filtered.slice(activePage * PAGE_SIZE, (activePage + 1) * PAGE_SIZE).map((m) => <PredictionCard key={matchKey(m)} match={m} market={market} valueOnly={view === 'value'} saved={saved} onToggle={toggle} />)}</div>
        {!filtered.length && <div className="prediction-empty"><span aria-hidden="true">⌕</span><h3>Tidak ada pertandingan untuk filter ini</h3><p>Coba liga lain atau tampilkan semua pertandingan.</p><button type="button" onClick={() => { setSearch(''); setLeague('all'); setMarket('all'); changeView('all'); }}>Reset filter</button></div>}
        {pages > 1 && <nav className="prediction-pagination" aria-label="Halaman pertandingan"><button disabled={activePage === 0} onClick={() => setPage(activePage - 1)}>← Sebelumnya</button><span>{activePage + 1} / {pages}</span><button disabled={activePage + 1 >= pages} onClick={() => setPage(activePage + 1)}>Berikutnya →</button></nav>}
      </section>
      <aside className="prediction-sidebar">
        <section className="prediction-watchlist"><header><div><span className="prediction-eyebrow">PILIHAN ANDA</span><h2>Watchlist pertandingan</h2></div><button type="button" disabled={!saved.length} onClick={() => updateSaved([])}>Reset</button></header>
          {!savedChoices.length ? <div className="watchlist-empty"><span aria-hidden="true">☆</span><p>Mulai dari satu pilihan.</p><small>Klik pasar pada kartu pertandingan untuk menyimpannya di sini.</small></div> : <ul>{savedChoices.map(({ match, pick, id }) => <li key={id}><button type="button" aria-label={`Hapus ${pickLabel(pick, match)}`} onClick={() => updateSaved(saved.filter((v) => v !== id))}>×</button><strong>{match.info.home} vs {match.info.away}</strong><span>{pickLabel(pick, match)} <b>@{formatOdds(pick.odds)}</b></span><small>{formatKickoffWIB(match.info.start_ts)}</small></li>)}</ul>}
          <div className="watchlist-total"><span>Total pilihan</span><strong>{savedChoices.length}</strong></div><p className="watchlist-note">Pilihan tersimpan di perangkat ini. Beberapa pasar dari match yang sama saling berkorelasi.</p><button type="button" className="prediction-copy" disabled={!savedChoices.length} onClick={copy}>Salin ringkasan pilihan ↗</button><p role="status" className="prediction-feedback">{message}</p>
        </section>
        <section className="prediction-guide"><span className="prediction-eyebrow">MEMBACA HASIL</span><h3>Curated picks, auto-tracked.</h3><p><b>🔒 Top Pick</b> memenuhi gate odds 1.60–2.50, EV ≥ 1%. Otomatis di-lock untuk pelacakan ROI.</p><p><b>Proyeksi</b> menampilkan arah model untuk pasar lain — tidak di-lock.</p><p><b>Max 2 pick per match</b> dari market berbeda. Pick ke-2 hanya muncul jika analisanya kuat.</p><p className="prediction-guide-foot">Semua Top Pick langsung masuk ke Hasil & ROI tracker.</p></section>
      </aside>
    </div>
  </>;
}
