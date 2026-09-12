/**
 * lib/fc/grouping.ts
 *
 * Pure grouping for the Schedule match list (sportsbook-style):
 * Country → League → matches (kickoff ascending). No React, fully testable.
 *
 * 1xbit league strings look like "England. Premier League" (Country. League)
 * or a bare competition name ("Club Friendlies", "CAF Champions League")
 * which falls under the "International" country bucket.
 */
import type { DetailedMatch } from './types';

export interface LeagueGroup {
  country: string;
  league: string;
  matches: DetailedMatch[];
}

export interface CountryGroup {
  country: string;
  leagues: LeagueGroup[];
  total: number;
}

export const INTERNATIONAL = 'International';

/** "England. Premier League" → {England, Premier League}; bare → {International, raw}. */
export function splitLeague(raw: unknown): { country: string; league: string } {
  if (typeof raw !== 'string' || !raw.trim()) return { country: INTERNATIONAL, league: 'Unknown' };
  const dot = raw.indexOf('.');
  if (dot > 0) {
    const country = raw.slice(0, dot).trim();
    const league = raw.slice(dot + 1).trim();
    if (country && league) return { country, league };
  }
  return { country: INTERNATIONAL, league: raw.trim() };
}

function startOf(m: DetailedMatch): number {
  const s = m.info?.['start_ts'];
  return typeof s === 'number' && Number.isFinite(s) ? s : Number.POSITIVE_INFINITY;
}

/** Group + sort: countries A–Z (International last), leagues A–Z, matches by kickoff. */
export function groupByCountryLeague(matches: DetailedMatch[]): CountryGroup[] {
  const byCountry = new Map<string, Map<string, DetailedMatch[]>>();
  for (const m of matches) {
    const { country, league } = splitLeague(m.info?.['league']);
    let leagues = byCountry.get(country);
    if (!leagues) {
      leagues = new Map();
      byCountry.set(country, leagues);
    }
    const list = leagues.get(league);
    if (list) list.push(m);
    else leagues.set(league, [m]);
  }
  const countries = [...byCountry.entries()].sort(([a], [b]) => {
    if (a === INTERNATIONAL) return 1;
    if (b === INTERNATIONAL) return -1;
    return a.localeCompare(b);
  });
  return countries.map(([country, leagues]) => {
    const leagueGroups: LeagueGroup[] = [...leagues.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([league, list]) => ({
        country,
        league,
        matches: [...list].sort((x, y) => startOf(x) - startOf(y)),
      }));
    return { country, leagues: leagueGroups, total: leagueGroups.reduce((n, g) => n + g.matches.length, 0) };
  });
}
