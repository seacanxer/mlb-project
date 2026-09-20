'use client';
import { useMemo } from 'react';
import type { DetailedMatch } from '@/lib/fc/types';
import { formatKickoffWIB } from '@/lib/fc/kickoff';
import { groupByCountryLeague } from '@/lib/fc/grouping';

export function ScheduleList({ matches }: { matches: DetailedMatch[] }) {
  const groups = useMemo(() => groupByCountryLeague(matches), [matches]);
  return <div className="fc-schedule-list" aria-label="Jadwal pertandingan">
    {groups.map((country) => <section className="fc-schedule-country" key={country.country}>
      <header><h2>{country.country}</h2><span>{country.total} pertandingan</span></header>
      {country.leagues.map((league) => <div className="fc-schedule-league" key={`${country.country}-${league.league}`}>
        <h3>{league.league}</h3>
        <div className="fc-schedule-rows">{league.matches.map((match) => <div className="fc-schedule-row" key={String(match.info.match_id ?? `${match.info.home}-${match.info.away}-${match.info.start_ts}`)}>
          <time>{formatKickoffWIB(match.info.start_ts)}</time><strong>{match.info.home || 'Home'}</strong><span>vs</span><strong>{match.info.away || 'Away'}</strong>
        </div>)}</div>
      </div>)}
    </section>)}
    {!groups.length && <div className="prediction-empty"><h3>Belum ada jadwal</h3><p>Perbarui analisis untuk memuat fixture terbaru.</p></div>}
  </div>;
}
