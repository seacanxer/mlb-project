import { afterEach, describe, expect, it, vi } from 'vitest';
import { MlbBullpenStatsProvider, MlbGameFeedProbableStarterProvider, MlbPitcherStatsProvider, MlbResultsProvider, MlbScheduleProvider } from '@/lib/providers/mlbStatsApi';
import { OneXbitOddsProvider, TheOddsApiProvider } from '@/lib/providers/oddsProvider';
import { EspnCoreProbableStarterProvider } from '@/lib/providers/espnCore';
import type { ScheduledGame } from '@/lib/providers/interfaces';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MlbScheduleProvider', () => {
  it('normalizes MLB string seasons, status details, and hydrated team metadata', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      dates: [{
        games: [{
          gamePk: 123,
          gameDate: '2026-08-24T22:40:00Z',
          season: '2026',
          status: { abstractGameState: 'Preview', detailedState: 'Postponed' },
          teams: {
            home: { team: { id: 116, name: 'Detroit Tigers', abbreviation: 'DET', locationName: 'Detroit', league: { id: 103 }, division: { id: 202 } } },
            away: { team: { id: 139, name: 'Tampa Bay Rays', abbreviation: 'TB', locationName: 'St. Petersburg', league: { id: 103 }, division: { id: 201 } } },
          },
          venue: { id: 2394, name: 'Comerica Park' },
        }],
      }],
    }), { status: 200 })));

    const [result] = await new MlbScheduleProvider().getSchedule('2026-08-24');
    expect(result.data.season).toBe(2026);
    expect(result.data.status).toBe('postponed');
    expect(result.data.homeTeamAbbreviation).toBe('DET');
    expect(result.data.awayDivisionId).toBe(201);
  });
});

describe('MlbResultsProvider', () => {
  it('returns a score only when MLB marks the game final', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      gameData: { status: { abstractGameState: 'Final', detailedState: 'Final' } },
      liveData: { linescore: { teams: { home: { runs: 1 }, away: { runs: 3 } } } },
    }), { status: 200 })));

    const result = await new MlbResultsProvider().getResult('824799');
    expect(result?.data).toMatchObject({
      gameId: '824799', homeScore: 1, awayScore: 3, finalStatus: 'final',
    });
  });

  it('rejects scheduled or partial linescores', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      gameData: { status: { abstractGameState: 'Preview', detailedState: 'Scheduled' } },
      liveData: { linescore: { teams: { home: { runs: null }, away: { runs: null } } } },
    }), { status: 200 })));

    await expect(new MlbResultsProvider().getResult('824235')).resolves.toBeNull();
  });

  it('propagates provider failures instead of treating them as a non-final game', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('unavailable', { status: 503 })));

    await expect(new MlbResultsProvider().getResult('824235'))
      .rejects.toThrow('MLB Stats API request failed after 3 attempts');
  });
});

describe('MlbGameFeedProbableStarterProvider', () => {
  it('uses the authoritative game feed only for a missing side', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      gameData: { probablePitchers: {
        home: { id: 687931, fullName: 'Carson Whisenhunt' },
        away: { id: 695505, fullName: 'Chase Burns' },
      } },
    }), { status: 200 })));
    const game: ScheduledGame = {
      gameId: '823183', date: '2026-08-24', startTimeUtc: new Date('2026-08-25T01:45:00Z'),
      homeTeamId: '137', awayTeamId: '113', venueId: '2395', season: 2026, status: 'scheduled',
      homeTeamName: 'San Francisco Giants', awayTeamName: 'Cincinnati Reds', venueName: 'Oracle Park',
      awayStarterPersonId: '695505', awayStarterName: 'Chase Burns',
    };

    const result = await new MlbGameFeedProbableStarterProvider().getMissingStarters([game]);
    expect(result).toHaveLength(1);
    expect(result[0].data).toMatchObject({ side: 'home', personId: '687931', fullName: 'Carson Whisenhunt' });
    expect(result[0].validationWarnings).toContain('PROBABLE_STARTER_FALLBACK_MLB_GAME_FEED');
  });
});

describe('MlbBullpenStatsProvider', () => {
  it('aggregates pure relievers from outs and counting stats, not decimal IP averages', async () => {
    const stat = (overrides: Record<string, unknown>) => ({
      gamesStarted: 0,
      outs: 32,
      inningsPitched: '10.2',
      earnedRuns: 4,
      baseOnBalls: 5,
      hits: 10,
      strikeOuts: 15,
      gamesPitched: 12,
      ...overrides,
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      roster: [
        { position: { abbreviation: 'P' }, person: { id: 1, stats: [{ splits: [{ season: '2026', stat: stat({}) }] }] } },
        { position: { abbreviation: 'P' }, person: { id: 2, stats: [{ splits: [{ season: '2026', stat: stat({ outs: 30, inningsPitched: '10.0', earnedRuns: 3, baseOnBalls: 2, hits: 8 }) }] }] } },
        { position: { abbreviation: 'P' }, person: { id: 3, stats: [{ splits: [{ season: '2026', stat: stat({ gamesStarted: 1 }) }] }] } },
        { position: { abbreviation: 'P' }, person: { id: 4, stats: [] } },
        { position: { abbreviation: 'C' }, person: { id: 5, stats: [] } },
      ],
    }), { status: 200 })));

    const result = await new MlbBullpenStatsProvider().getTeamBullpen('116', 2026);
    expect(result.data).toMatchObject({
      teamId: '116',
      relievers: 2,
      outsRecorded: 62,
      inningsPitched: '20.2',
      era: 3.05,
      whip: 1.21,
      excludedSwingmen: 1,
      skippedWithoutStats: 1,
    });
    expect(result.validationWarnings).toContain('BULLPEN_EXCLUDES_SWINGMEN:1');
    expect(result.sourceIdentifier).toContain('/api/v1/teams/116/roster?');
  });
});

describe('MlbPitcherStatsProvider official minor-league fallback', () => {
  it('uses season-stamped official MiLB stats when the MLB season split is unpublished', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      const splits = url.includes('sportId=11') ? [{ stat: {
        era: '3.67', whip: '1.22', inningsPitched: '49.0', outs: 147,
        gamesStarted: 10, earnedRuns: 20, baseOnBalls: 18, strikeOuts: 55,
      } }] : [];
      return new Response(JSON.stringify({ stats: [{ splits }] }), { status: 200 });
    }));

    const result = await new MlbPitcherStatsProvider().getSeasonStats('690279', 2026);
    expect(result.provider).toBe('mlb-stats-api:minor-league-fallback:sport-11');
    expect(result.data).toMatchObject({ era: 3.67, inningsPitched: 49, gamesStarted: 10 });
    expect(result.validationWarnings).toContain('MINOR_LEAGUE_SEASON_STATS_NOT_MLB_EQUIVALENT');
  });

  it('fills a short MLB last-five window with official MiLB starts and labels provenance', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      const splits = url.includes('sportId=11')
        ? [
          { date: '2026-08-10', stat: { gamesStarted: 1, inningsPitched: '5.0', earnedRuns: 1 } },
          { date: '2026-08-03', stat: { gamesStarted: 1, inningsPitched: '5.0', earnedRuns: 2 } },
        ]
        : [
          { date: '2026-08-24', stat: { gamesStarted: 1, inningsPitched: '5.0', earnedRuns: 1 } },
          { date: '2026-08-18', stat: { gamesStarted: 1, inningsPitched: '5.0', earnedRuns: 2 } },
          { date: '2026-08-12', stat: { gamesStarted: 1, inningsPitched: '5.0', earnedRuns: 3 } },
        ];
      return new Response(JSON.stringify({ stats: [{ splits }] }), { status: 200 });
    }));

    const results = await new MlbPitcherStatsProvider().getGameLogs('695549', 2026, 5);
    expect(results).toHaveLength(5);
    expect(results.filter((result) => result.provider.includes('minor-league-fallback'))).toHaveLength(2);
    expect(results.some((result) => result.validationWarnings.includes('MINOR_LEAGUE_GAME_LOG_NOT_MLB_EQUIVALENT'))).toBe(true);
  });
});

describe('EspnCoreProbableStarterProvider', () => {
  it('fills only a starter side missing from the MLB schedule', async () => {
    const game: ScheduledGame = {
      gameId: '823183',
      date: '2026-08-24',
      startTimeUtc: new Date('2026-08-25T01:45:00Z'),
      homeTeamId: '137',
      awayTeamId: '113',
      venueId: '2395',
      season: 2026,
      status: 'scheduled',
      homeTeamName: 'San Francisco Giants',
      awayTeamName: 'Cincinnati Reds',
      venueName: 'Oracle Park',
      awayStarterPersonId: '695505',
      awayStarterName: 'Chase Burns',
    };
    const eventRef = 'http://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/events/401816660';
    const athleteRef = 'http://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/seasons/2026/athletes/4626232';
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/events?')) {
        return new Response(JSON.stringify({ items: [{ $ref: eventRef }] }), { status: 200 });
      }
      if (url.includes('/events/401816660')) {
        return new Response(JSON.stringify({
          $ref: eventRef,
          id: '401816660',
          date: '2026-08-25T01:45Z',
          name: 'Cincinnati Reds at San Francisco Giants',
          competitions: [{ competitors: [
            { homeAway: 'home', probables: [{ name: 'probableStartingPitcher', athlete: { $ref: athleteRef } }] },
            { homeAway: 'away', probables: [{ name: 'probableStartingPitcher', athlete: { $ref: 'unused' } }] },
          ] }],
        }), { status: 200 });
      }
      if (url.includes('/athletes/4626232')) {
        return new Response(JSON.stringify({ id: '4626232', fullName: 'Carson Whisenhunt' }), { status: 200 });
      }
      return new Response('{}', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await new EspnCoreProbableStarterProvider().getMissingStarters([game]);
    expect(result).toHaveLength(1);
    expect(result[0].data).toMatchObject({
      gameId: '823183', side: 'home', fullName: 'Carson Whisenhunt', espnAthleteId: '4626232',
    });
    expect(result[0].provider).toBe('espn-core-api');
    expect(result[0].validationWarnings).toContain('PROBABLE_STARTER_FALLBACK_ESPN_CORE');
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('unused'), expect.anything());
  });
});

describe('TheOddsApiProvider', () => {
  const game: ScheduledGame = {
    gameId: '123',
    date: '2026-08-24',
    startTimeUtc: new Date('2026-08-24T22:40:00Z'),
    homeTeamId: '116',
    awayTeamId: '139',
    venueId: '2394',
    season: 2026,
    status: 'scheduled',
    homeTeamName: 'Detroit Tigers',
    awayTeamName: 'Tampa Bay Rays',
    venueName: 'Comerica Park',
  };

  it('maps moneyline and total markets to the MLB game id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      id: 'odds-event-1',
      commence_time: '2026-08-24T22:40:00Z',
      home_team: 'Detroit Tigers',
      away_team: 'Tampa Bay Rays',
      bookmakers: [{
        key: 'testbook',
        title: 'Test Book',
        last_update: '2026-08-24T20:00:00Z',
        markets: [
          { key: 'h2h', outcomes: [{ name: 'Detroit Tigers', price: 1.8 }, { name: 'Tampa Bay Rays', price: 2.05 }] },
          { key: 'totals', outcomes: [{ name: 'Over', price: 1.91, point: 8.5 }, { name: 'Under', price: 1.91, point: 8.5 }] },
        ],
      }],
    }]), { status: 200, headers: { 'x-requests-remaining': '497' } }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await new TheOddsApiProvider({ apiKey: 'test', baseUrl: 'https://odds.example' }).getOddsForGames([game]);
    expect(result.odds).toHaveLength(1);
    expect(result.odds[0].data).toMatchObject({
      gameId: '123', moneylineHome: 1.8, moneylineAway: 2.05,
      totalLine: 8.5, totalOverDecimal: 1.91, totalUnderDecimal: 1.91,
    });
    expect(result.odds[0].provider).toBe('the-odds-api:testbook');
    expect(result.quotaRemaining).toBe('497');
    const requestedUrl = String(fetchMock.mock.calls[0][0]);
    expect(requestedUrl).toContain('commenceTimeFrom=2026-08-24T16%3A40%3A00Z');
    expect(requestedUrl).toContain('commenceTimeTo=2026-08-25T04%3A40%3A00Z');
    expect(requestedUrl).not.toContain('.000Z');
  });

  it('does not call the paid provider without an API key', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const result = await new TheOddsApiProvider({ apiKey: '' }).getOddsForGames([game]);
    expect(result.warnings).toEqual(['ODDS_API_KEY_MISSING']);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('OneXbitOddsProvider', () => {
  const game: ScheduledGame = {
    gameId: '824235',
    date: '2026-08-24',
    startTimeUtc: new Date('2026-08-24T22:40:00Z'),
    homeTeamId: '116',
    awayTeamId: '139',
    venueId: '2394',
    season: 2026,
    status: 'scheduled',
    homeTeamName: 'Detroit Tigers',
    awayTeamName: 'Tampa Bay Rays',
    venueName: 'Comerica Park',
  };

  it('filters non-MLB games and maps O1 home/O2 away to the MLB game id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      Success: true,
      Value: [
        {
          I: 746695918,
          L: 'USA. MLB',
          O1: 'Detroit Tigers',
          O2: 'Tampa Bay Rays',
          S: Math.floor(game.startTimeUtc.getTime() / 1000),
          E: [
            { G: 1, T: 1, C: 2.177 },
            { G: 1, T: 3, C: 1.782 },
            { G: 17, T: 9, P: 7.5, C: 1.909 },
            { G: 17, T: 10, P: 7.5, C: 2.013 },
          ],
        },
        {
          I: 999,
          L: 'Japan. NPB',
          O1: 'Example Home',
          O2: 'Example Away',
          S: Math.floor(game.startTimeUtc.getTime() / 1000),
          E: [],
        },
      ],
    }), { status: 200 })));

    const result = await new OneXbitOddsProvider({ domains: ['https://odds.example'] })
      .getOddsForGames([game]);
    expect(result.odds).toHaveLength(1);
    expect(result.odds[0].data).toMatchObject({
      gameId: '824235',
      moneylineHome: 2.177,
      moneylineAway: 1.782,
      totalLine: 7.5,
      totalOverDecimal: 1.909,
      totalUnderDecimal: 2.013,
    });
    expect(result.odds[0].provider).toBe('1xbit-linefeed-unofficial');
    expect(result.odds[0].validationWarnings).toContain('UNOFFICIAL_REVERSE_ENGINEERED_ODDS_SOURCE');
  });
});
