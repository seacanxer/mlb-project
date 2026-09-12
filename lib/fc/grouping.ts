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
  /** True for the synthetic pinned "Top Leagues" section. */
  featured?: boolean;
}

export const INTERNATIONAL = 'International';

/**
 * Top 5 liga Eropa yang selalu di-pin di atas (urutan tetap).
 * Cocokkan sebagai pasangan (country, league), case-insensitive.
 */
export const TOP_LEAGUES: Array<{ country: string; league: string }> = [
  { country: 'England', league: 'Premier League' },
  { country: 'Spain', league: 'La Liga' },
  { country: 'Germany', league: 'Bundesliga' },
  { country: 'Italy', league: 'Serie A' },
  { country: 'France', league: 'Ligue 1' },
];

export const TOP_SECTION = 'Top Leagues';

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
  const groups: CountryGroup[] = countries.map(([country, leagues]) => {
    const leagueGroups: LeagueGroup[] = [...leagues.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([league, list]) => ({
        country,
        league,
        matches: [...list].sort((x, y) => startOf(x) - startOf(y)),
      }));
    return { country, leagues: leagueGroups, total: leagueGroups.reduce((n, g) => n + g.matches.length, 0) };
  });

  // Pin Top 5 Europe di seksi tersendiri paling atas (hanya liga yang ada
  // datanya). Grup country asal tidak lagi memuat liga tersebut (no duplikat).
  const featured: LeagueGroup[] = [];
  for (const top of TOP_LEAGUES) {
    const g = groups.find((gr) => gr.country.toLowerCase() === top.country.toLowerCase());
    const lg = g?.leagues.find((l) => l.league.toLowerCase() === top.league.toLowerCase());
    if (lg) featured.push(lg);
  }
  if (featured.length === 0) return groups;
  const featuredKeys = new Set(featured.map((l) => `${l.country}|${l.league}`));
  const rest = groups
    .map((gr) => ({
      ...gr,
      leagues: gr.leagues.filter((l) => !featuredKeys.has(`${l.country}|${l.league}`)),
      total: gr.leagues.filter((l) => !featuredKeys.has(`${l.country}|${l.league}`)).reduce((n, l) => n + l.matches.length, 0),
    }))
    .filter((gr) => gr.leagues.length > 0);
  return [{ country: TOP_SECTION, leagues: featured, total: featured.reduce((n, l) => n + l.matches.length, 0), featured: true }, ...rest];
}
