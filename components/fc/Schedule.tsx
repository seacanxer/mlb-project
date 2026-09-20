/**
 * components/fc/Schedule.tsx
 *
 * Today's Schedule as a sportsbook-style match list: Country → League →
 * matches, with collapsible league subgroups ("display matches (N)").
 * One markup serves desktop + mobile (stacked rows, no separate table).
 */
'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import type { DetailedMatch } from '@/lib/fc/types';
import { formatEv, formatOdds, formatProb } from '@/lib/fc/format';
import { formatKickoffWIB, kickoffCountdown } from '@/lib/fc/kickoff';
import { groupByCountryLeague } from '@/lib/fc/grouping';
import { CoverageBadge, StatusBadge } from './shared';

function fixtureTitle(m: DetailedMatch): string {
  const info = m.info ?? {};
  const home = (info['home'] as string) ?? '';
  const away = (info['away'] as string) ?? '';
  if (home || away) return `${home || '?'} vs ${away || '?'}`;
  return '—';
}

function hasPick(m: DetailedMatch): boolean {
  return (m.qualified_picks?.length ?? 0) > 0 || (m.picks?.length ?? 0) > 0;
}

function MatchRow({ m, showLeague = false }: { m: DetailedMatch; showLeague?: boolean }) {
  const info = m.info ?? {};
  const picks = m.qualified_picks ?? [];
  const pick = hasPick(m);
  const markets = [
    { key: '1x2', label: '1X2' }, { key: 'ah', label: 'Asian HDP' },
    { key: 'ou', label: 'O/U' }, { key: 'btts', label: 'BTTS' },
  ];
  return (
    <li className={`fc-prediction-card${pick ? ' fc-prediction-card-ready' : ''}`}>
      <div className="fc-prediction-meta">
        <span>{showLeague && `${info['league'] ?? 'Liga belum tersedia'} · `}{formatKickoffWIB(info['start_ts'] as number)}</span>
        <span className="fc-prediction-badges"><CoverageBadge coverage={info['coverage_status'] as string | undefined} />
          {picks.length ? <StatusBadge decision={picks[0].decision} isTop={picks[0].is_top_pick} /> : <span className="chip chip-fc-na">Belum ada pick</span>}
        </span>
      </div>
      <div className="fc-prediction-body">
        <div className="fc-prediction-teams">
          <strong>{String(info['home'] || 'Tim tuan rumah belum tersedia')}</strong>
          <span className="fc-prediction-vs">VS</span>
          <strong>{String(info['away'] || 'Tim tamu belum tersedia')}</strong>
          <small>{kickoffCountdown(info['start_ts'] as number)}</small>
        </div>
        <div className="fc-prediction-markets" aria-label={`Prediksi ${fixtureTitle(m)}`}>
          {markets.map(({ key, label }) => {
            const selected = picks.filter((p) => p.market?.toLowerCase() === key)
              .sort((a, b) => Number(b.rank_score ?? b.ev ?? 0) - Number(a.rank_score ?? a.ev ?? 0))[0];
            return <div key={key} className={`fc-prediction-market${selected ? ' has-pick' : ''}`}>
              <span>{label}</span>
              <strong>{selected?.pick ?? '—'}</strong>
              <small>{selected ? `${formatOdds(selected.odds)} · Prob ${formatProb(selected.probability)}` : info['coverage_status'] === 'market_only' ? 'Jadwal saja' : 'Tidak ada pick lolos gate'}</small>
            </div>;
          })}
        </div>
      </div>
      <div className="fc-prediction-foot">
        <span>{picks.length ? `${picks.length} pick lolos gate · EV terbaik ${formatEv(Math.max(...picks.map((p) => p.ev)))}` : 'Belum ada rekomendasi untuk pertandingan ini.'}</span>
        {picks.length > 0 && <Link href="/fc">Lihat daftar pick →</Link>}
      </div>
    </li>
  );
}

type SortMode = 'league' | 'time';

export function ScheduleTable({ matches }: { matches: DetailedMatch[] }) {
  const [search, setSearch] = useState('');
  const [league, setLeague] = useState('all');
  const leagues = useMemo(() => [...new Set(matches.map((m) => String(m.info?.['league'] ?? '')).filter(Boolean))].sort(), [matches]);
  const filtered = useMemo(() => matches.filter((m) => {
    const info = m.info ?? {};
    const query = search.trim().toLowerCase();
    return (league === 'all' || info['league'] === league) && (!query || [info['home'], info['away'], info['league']].some((v) => String(v ?? '').toLowerCase().includes(query)));
  }), [matches, league, search]);
  const groups = useMemo(() => groupByCountryLeague(filtered), [filtered]);
  // Track user toggles only. Default state:
  //   featured (Top 5 Europe) = expanded, other leagues = collapsed
  const [overrides, setOverrides] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortMode>('time');

  const flat = useMemo(
    () => [...filtered].sort((a, b) => Number(a.info?.['start_ts'] ?? 0) - Number(b.info?.['start_ts'] ?? 0)),
    [filtered],
  );
  const next = flat.find((m) => Number(m.info?.['start_ts'] ?? 0) * 1000 > Date.now());

  const toggle = (key: string) => {
    setOverrides((prev) => {
      const nextSet = new Set(prev);
      if (nextSet.has(key)) nextSet.delete(key);
      else nextSet.add(key);
      return nextSet;
    });
  };

  return (
    <div>
      <div className="fc-predictions-head"><div><h2>Daftar Prediksi Pertandingan</h2><p>Setiap pertandingan menampilkan empat pasar. Prediksi hanya muncul jika lolos gate model.</p></div><span>{filtered.length} pertandingan</span></div>
      <div className="fc-predictions-toolbar">
        <label>Cari pertandingan<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cari tim atau liga" /></label>
        <label>Liga<select value={league} onChange={(e) => setLeague(e.target.value)}><option value="all">Semua liga</option>{leagues.map((l) => <option key={l} value={l}>{l}</option>)}</select></label>
      </div>
      {filtered.length === 0 && <p className="fc-predictions-empty">Tidak ada pertandingan yang cocok dengan pencarian.</p>}
      {next && (
        <p className="fc-next" role="status">
          Laga terdekat: <strong>{fixtureTitle(next)}</strong> · {kickoffCountdown(next.info?.['start_ts'] as number)}
        </p>
      )}
      <div className="fc-scanrow" role="group" aria-label="Urutkan jadwal">
        <button
          type="button"
          className={`btn btn-ghost btn-sm${sort === 'league' ? ' fc-sort-active' : ''}`}
          onClick={() => setSort('league')}
          aria-pressed={sort === 'league'}
        >
          🏆 Sort by Liga
        </button>
        <button
          type="button"
          className={`btn btn-ghost btn-sm${sort === 'time' ? ' fc-sort-active' : ''}`}
          onClick={() => setSort('time')}
          aria-pressed={sort === 'time'}
        >
          🕒 Sort by Time
        </button>
      </div>
      {sort === 'time' ? (
        <ul className="fc-matchlist fc-matchlist-flat" aria-label="Jadwal urut waktu">
          {flat.map((m, i) => (
            <MatchRow
              key={`${(m.info?.['match_id'] as string) ?? i}-${m.info?.['start_ts']}`}
              m={m}
              showLeague
            />
          ))}
        </ul>
      ) : (
      groups.map((country) => (
        <section key={country.country} aria-label={country.country} className="fc-country">
          <h2 className="fc-country-head">
            {country.featured ? '⭐ ' : ''}{country.country.toUpperCase()}
            <span className="muted"> · {country.total} match</span>
          </h2>
          {country.leagues.map((lg) => {
            const key = `${country.country}|${lg.league}`;
            const defaultOpen = country.featured === true;
            const open = overrides.has(key) ? !defaultOpen : defaultOpen;
            return (
              <div key={key} className="fc-league">
                <button
                  type="button"
                  className="fc-league-head"
                  aria-expanded={open}
                  onClick={() => toggle(key)}
                >
                  <span className="fc-league-name">{lg.league}</span>
                  <span className="muted">display matches ({lg.matches.length})</span>
                  <span aria-hidden="true">{open ? '▾' : '▸'}</span>
                </button>
                {open && (
                  <ul className="fc-matchlist">
                    {lg.matches.map((m, i) => (
                      <MatchRow
                        key={`${(m.info?.['match_id'] as string) ?? i}-${m.info?.['start_ts']}`}
                        m={m}
                      />
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </section>
      ))
      )}
    </div>
  );
}
