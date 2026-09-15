'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

type Pick = { match?: string; home?: string; away?: string; league?: string; start_ts?: number; market?: string; pick?: string; odds?: number; probability?: number; ev?: number; };
type Match = { info?: { home?: string; away?: string; league?: string; start_ts?: number }; picks?: Pick[] };

function pct(v?: number) { return typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—'; }
function kickoff(v?: number) { return v ? new Date(v * 1000).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta', dateStyle: 'short', timeStyle: 'short' }) : '—'; }
function find(picks: Pick[] | undefined, market: string) { return (picks ?? []).find((p) => p.market === market); }
const TOP_LEAGUES = [/^England\. Premier League$/i, /^Spain\. La Liga$/i, /^Germany\. Bundesliga$/i, /^Italy\. Serie A$/i, /^France\. Ligue 1$/i, /^Japan\. J1 League$/i, /^South Korea\. K-League 1$/i, /^Saudi Arabia\. Professional League$/i, /^China\. Super League$/i, /^Australia\. A-League$/i];
function isTopLeague(league?: string) { return Boolean(league && TOP_LEAGUES.some((pattern) => pattern.test(league.trim()))); }

export default function AiMatchAnalyzer() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [onlyConsensus, setOnlyConsensus] = useState(false);

  useEffect(() => {
    fetch('/api/fc/matches?limit=500')
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((d) => setMatches(d.matches ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const rows = useMemo(() => matches.filter((m) => isTopLeague(m.info?.league)).map((m) => {
    const picks = m.picks ?? [];
    const ah = find(picks, 'ah');
    const ou = find(picks, 'ou');
    const btts = find(picks, 'btts');
    const available = [ah, ou, btts].filter(Boolean) as Pick[];
    const avg = available.length ? available.reduce((s, p) => s + (p.probability ?? 0), 0) / available.length : 0;
    return { m, ah, ou, btts, avg, consensus: available.length >= 2 && avg >= 0.56 };
  }).filter((r) => !onlyConsensus || r.consensus), [matches, onlyConsensus]);

  return <main className="fc-page">
    <div className="page-header"><div><h1 className="page-title">🤖 AI Match Analyzer</h1><p className="page-subtitle">AH · Over/Under · BTTS — analisa standalone untuk match mendatang</p></div><Link className="btn btn-ghost" href="/fc">← Today&apos;s Pick</Link></div>
    <div className="card" style={{ marginBottom: '1rem' }}><strong>Model preview</strong><p className="muted">Mesin menggabungkan proyeksi gol, handicap, total gol, BTTS, dan odds 1xbit. Output ini terpisah dari official/watch gate dan belum mengubah database.</p><label><input type="checkbox" checked={onlyConsensus} onChange={(e) => setOnlyConsensus(e.target.checked)} /> Tampilkan consensus saja</label></div>
    {loading && <div className="card">Memuat fixture dan market…</div>}
    {error && <div className="card">Gagal memuat: {error}</div>}
    {!loading && !error && rows.length === 0 && <div className="card">Belum ada fixture dengan data analyzer.</div>}
    <div className="fc-analyzer-grid">{rows.map(({ m, ah, ou, btts, avg, consensus }, i) => <article className={`card fc-analyzer-card${consensus ? ' is-consensus' : ''}`} key={`${m.info?.home}-${m.info?.away}-${i}`}>
      <div className="fc-card-head"><span className="muted">{m.info?.league ?? '—'}</span><span className="badge">{consensus ? 'Consensus' : 'Analysis'}</span></div>
      <h2>{m.info?.home ?? '—'} vs {m.info?.away ?? '—'}</h2><p className="muted">Kickoff WIB: {kickoff(m.info?.start_ts)}</p>
      <div className="fc-analyzer-lines"><div><b>AH</b><span>{ah?.pick ?? '—'}</span><small>{pct(ah?.probability)} · {ah?.odds ? `@${ah.odds}` : 'no odds'}</small></div><div><b>O/U</b><span>{ou?.pick ?? '—'}</span><small>{pct(ou?.probability)} · {ou?.odds ? `@${ou.odds}` : 'no odds'}</small></div><div><b>BTTS</b><span>{btts?.pick ?? '—'}</span><small>{pct(btts?.probability)} · {btts?.odds ? `@${btts.odds}` : 'no odds'}</small></div></div>
      <div className="fc-card-foot"><span>AI confidence: <strong>{pct(avg)}</strong></span><span className="muted">Standalone · no auto-lock</span></div>
    </article>)}</div>
  </main>;
}
