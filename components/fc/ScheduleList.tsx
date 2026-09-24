'use client';
import { useEffect, useMemo, useState } from 'react';
import type { DetailedMatch } from '@/lib/fc/types';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { groupByCountryLeague } from '@/lib/fc/grouping';

type SortMode = 'time' | 'top' | 'league';

export function ScheduleList({ matches }: { matches: DetailedMatch[] }) {
  const [sort, setSort] = useState<SortMode>('time');
  const [closedCountries, setClosedCountries] = useState<Set<string>>(new Set());
  const [closedLeagues, setClosedLeagues] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);
  const groups = useMemo(() => {
    const grouped = groupByCountryLeague(matches);
    if (sort === 'time') {
      for (const country of grouped) for (const league of country.leagues) league.matches.sort((a, b) => Number(a.info.start_ts ?? 0) - Number(b.info.start_ts ?? 0));
    } else if (sort === 'league') {
      for (const country of grouped) country.leagues.sort((a, b) => a.league.localeCompare(b.league));
    }
    return grouped;
  }, [matches, sort]);
  useEffect(() => {
    if (initialized || !groups.length) return;
    setClosedCountries(new Set(groups.filter((group) => !group.featured).map((group) => group.country)));
    setClosedLeagues(new Set(groups.flatMap((group) => group.featured ? [] : group.leagues.map((league) => `${group.country}-${league.league}`))));
    setInitialized(true);
  }, [groups, initialized]);
  const toggleCountry = (key: string) => setClosedCountries((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const toggleLeague = (key: string) => setClosedLeagues((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  return <div className="fc-schedule-list" aria-label="Jadwal pertandingan">
    <div className="fc-schedule-toolbar" role="toolbar" aria-label="Urutkan jadwal">
      <span>Sort by</span>
      <button className={sort === 'time' ? 'active' : ''} onClick={() => setSort('time')}>Waktu</button>
      <button className={sort === 'top' ? 'active' : ''} onClick={() => setSort('top')}>Top Match</button>
      <button className={sort === 'league' ? 'active' : ''} onClick={() => setSort('league')}>League</button>
    </div>
    {groups.map((country) => {
      const countryKey = country.country;
      const countryClosed = closedCountries.has(countryKey);
      return <section className={`fc-schedule-country${countryClosed ? ' is-collapsed' : ''}`} key={countryKey}>
        <button type="button" className="fc-schedule-country-toggle" onClick={() => toggleCountry(countryKey)} aria-expanded={!countryClosed}>
          <span><strong>{country.featured ? '⭐ ' : ''}{country.country}</strong><small>{country.total} pertandingan</small></span><b>{countryClosed ? '＋' : '−'}</b>
        </button>
        {!countryClosed && country.leagues.map((league) => {
          const leagueKey = `${countryKey}-${league.league}`;
          const leagueClosed = closedLeagues.has(leagueKey);
          return <div className={`fc-schedule-league${leagueClosed ? ' is-collapsed' : ''}`} key={leagueKey}>
            <button type="button" className="fc-schedule-league-toggle" onClick={() => toggleLeague(leagueKey)} aria-expanded={!leagueClosed}>
              <span><strong>{league.league}</strong><small>{league.matches.length} pertandingan</small></span><b>{leagueClosed ? '＋' : '−'}</b>
            </button>
            {!leagueClosed && <div className="fc-schedule-rows">{league.matches.map((match) => <div className="fc-schedule-row" key={String(match.info.match_id ?? `${match.info.home}-${match.info.away}-${match.info.start_ts}`)}>
              <time>{formatKickoffWIB(match.info.start_ts)}</time><strong>{match.info.home || 'Home'}</strong><span>vs</span><strong>{match.info.away || 'Away'}</strong>
            </div>)}</div>}
          </div>;
        })}
      </section>;
    })}
    {!groups.length && <div className="prediction-empty"><h3>Belum ada jadwal</h3><p>Perbarui analisis untuk memuat fixture terbaru.</p></div>}
  </div>;
}
