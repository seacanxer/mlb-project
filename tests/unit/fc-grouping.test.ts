import { describe, expect, it } from 'vitest';
import { groupByCountryLeague, INTERNATIONAL, splitLeague, TOP_SECTION } from '@/lib/fc/grouping';
import type { DetailedMatch } from '@/lib/fc/types';

function match(league: string, start_ts: number, home = 'H', away = 'A'): DetailedMatch {
  return { info: { league, start_ts, home, away } };
}

describe('fc league grouping', () => {
  it('splits "Country. League" and bare competition names', () => {
    expect(splitLeague('England. Premier League')).toEqual({ country: 'England', league: 'Premier League' });
    expect(splitLeague('Spain. Segunda Division')).toEqual({ country: 'Spain', league: 'Segunda Division' });
    expect(splitLeague('Club Friendlies')).toEqual({ country: INTERNATIONAL, league: 'Club Friendlies' });
    expect(splitLeague(null)).toEqual({ country: INTERNATIONAL, league: 'Unknown' });
  });

  it('groups by country then league, matches sorted by kickoff', () => {
    const groups = groupByCountryLeague([
      match('England. Championship', 300),
      match('Portugal. Primeira Liga', 100),
      match('England. Championship', 200),
      match('Club Friendlies', 150),
    ]);
    expect(groups.map((g) => g.country)).toEqual(['England', 'Portugal', INTERNATIONAL]);
    expect(groups[0].total).toBe(2);
    expect(groups[0].leagues[0].matches.map((m) => m.info?.['start_ts'])).toEqual([200, 300]);
    expect(groups[2].leagues[0].league).toBe('Club Friendlies');
  });

  it('returns empty array for empty input', () => {
    expect(groupByCountryLeague([])).toEqual([]);
  });

  it('pins Top 5 Europe in a top section without duplicates', () => {
    const groups = groupByCountryLeague([
      match('England. Championship', 300),
      match('Spain. La Liga', 100),
      match('England. Premier League', 200),
      match('Italy. Serie A', 150),
    ]);
    expect(groups[0].country).toBe(TOP_SECTION);
    expect(groups[0].featured).toBe(true);
    expect(groups[0].leagues.map((l) => l.league)).toEqual(['Premier League', 'La Liga', 'Serie A']);
    // Country groups no longer contain the featured leagues.
    const england = groups.find((g) => g.country === 'England');
    expect(england?.leagues.map((l) => l.league)).toEqual(['Championship']);
    expect(groups.find((g) => g.country === 'Italy')).toBeUndefined();
  });
});
