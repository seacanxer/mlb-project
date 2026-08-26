/**
 * lib/providers/mlbStatsApi.ts
 *
 * Concrete adapters for the public MLB Stats API.
 * Implements ScheduleProvider, PitcherStatsProvider, TeamStatsProvider, ResultsProvider.
 */

import crypto from 'crypto';
import { inningsToOuts, outsToInningsDisplay, computeEra } from '@/lib/utils/innings';
import { FreshnessState } from '@/lib/providers/interfaces';
import type {
  ScheduleProvider,
  PitcherStatsProvider,
  TeamStatsProvider,
  BullpenStatsProvider,
  ResultsProvider,
  ScheduledGame,
  PitcherSeasonStats,
  PitcherGameLog,
  TeamSeasonStats,
  BullpenStats,
  GameResultData,
} from '@/lib/providers/interfaces';

const BASE = process.env.MLB_STATS_API_BASE_URL || 'https://statsapi.mlb.com';
const REQUEST_TIMEOUT_MS = 15_000;
const MAX_ATTEMPTS = 3;
const MINOR_LEAGUE_SPORT_IDS = [11, 12, 13, 14] as const;

async function fetchJson(path: string): Promise<unknown> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { Accept: 'application/json', 'User-Agent': 'mlb-analytics/0.1' },
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!res.ok) {
        const error = new Error(`MLB Stats API error ${res.status}: ${path}`);
        if (res.status < 500 && res.status !== 429) throw error;
        lastError = error;
      } else {
        return res.json();
      }
    } catch (error) {
      lastError = error;
      if (error instanceof Error && error.message.includes('error 4') && !error.message.includes('429')) {
        throw error;
      }
    } finally {
      clearTimeout(timeout);
    }

    if (attempt < MAX_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, attempt * 250));
    }
  }

  const cause = lastError instanceof Error && lastError.cause instanceof Error
    ? `; cause=${lastError.cause.message}`
    : '';
  const detail = `${lastError instanceof Error ? lastError.message : String(lastError)}${cause}`;
  throw new Error(`MLB Stats API request failed after ${MAX_ATTEMPTS} attempts: ${path} (${detail})`);
}

function checksum(data: unknown): string {
  return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
}

function makeResult<T>(
  data: T,
  provider: string,
  raw: unknown,
  providerId?: string,
  sourceIdentifier?: string,
  season?: number
) {
  return {
    provider,
    providerId,
    sourceIdentifier,
    retrievedAt: new Date(),
    season,
    sourceTimezone: 'America/New_York',
    rawChecksum: checksum(raw),
    data,
    freshnessState: 'fresh' as FreshnessState,
    validationWarnings: [] as string[],
  };
}

// ---------------------------------------------------------------------------
// Schedule adapter
// ---------------------------------------------------------------------------

export class MlbScheduleProvider implements ScheduleProvider {
  async getSchedule(date: string) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      throw new Error(`Invalid MLB schedule date: ${date}`);
    }
    const path = `/api/v1/schedule?sportId=1&date=${date}&hydrate=probablePitcher,team,venue`;
    const raw = await fetchJson(path);
    const data = raw as any;

    const results: ReturnType<typeof makeResult<ScheduledGame>>[] = [];

    for (const dateEntry of (data.dates ?? [])) {
      for (const g of (dateEntry.games ?? [])) {
        const game: ScheduledGame = {
          gameId: String(g.gamePk),
          date,
          startTimeUtc: new Date(g.gameDate),
          homeTeamId: String(g.teams?.home?.team?.id),
          awayTeamId: String(g.teams?.away?.team?.id),
          venueId: String(g.venue?.id ?? 'unknown'),
          season: Number.parseInt(String(g.season ?? date.slice(0, 4)), 10),
          status: normalizeStatus(g.status?.abstractGameState, g.status?.detailedState),
          homeTeamName: g.teams?.home?.team?.name ?? 'Unknown',
          awayTeamName: g.teams?.away?.team?.name ?? 'Unknown',
          venueName: g.venue?.name ?? 'Unknown',
          homeStarterPersonId: g.teams?.home?.probablePitcher?.id
            ? String(g.teams.home.probablePitcher.id)
            : undefined,
          awayStarterPersonId: g.teams?.away?.probablePitcher?.id
            ? String(g.teams.away.probablePitcher.id)
            : undefined,
          homeStarterName: g.teams?.home?.probablePitcher?.fullName,
          awayStarterName: g.teams?.away?.probablePitcher?.fullName,
          homeTeamAbbreviation: g.teams?.home?.team?.abbreviation,
          awayTeamAbbreviation: g.teams?.away?.team?.abbreviation,
          homeTeamCity: g.teams?.home?.team?.locationName,
          awayTeamCity: g.teams?.away?.team?.locationName,
          homeLeagueId: numberOrUndefined(g.teams?.home?.team?.league?.id),
          awayLeagueId: numberOrUndefined(g.teams?.away?.team?.league?.id),
          homeDivisionId: numberOrUndefined(g.teams?.home?.team?.division?.id),
          awayDivisionId: numberOrUndefined(g.teams?.away?.team?.division?.id),
        };
        results.push(makeResult(game, 'mlb-stats-api', g, String(g.gamePk), path, game.season));
      }
    }
    return results;
  }
}

export type GameFeedProbableStarter = {
  gameId: string;
  side: 'home' | 'away';
  personId: string;
  fullName: string;
};

/** Authoritative game-level fallback when the hydrated schedule is incomplete. */
export class MlbGameFeedProbableStarterProvider {
  async getMissingStarters(games: ScheduledGame[]) {
    const results: ReturnType<typeof makeResult<GameFeedProbableStarter>>[] = [];
    for (const game of games) {
      const missingHome = !game.homeStarterPersonId || !game.homeStarterName;
      const missingAway = !game.awayStarterPersonId || !game.awayStarterName;
      if (!missingHome && !missingAway) continue;

      const path = `/api/v1.1/game/${game.gameId}/feed/live`;
      const raw = await fetchJson(path);
      const probablePitchers = (raw as any)?.gameData?.probablePitchers ?? {};
      for (const side of ['home', 'away'] as const) {
        if ((side === 'home' && !missingHome) || (side === 'away' && !missingAway)) continue;
        const pitcher = probablePitchers[side];
        if (!pitcher?.id || !pitcher?.fullName) continue;
        const result = makeResult<GameFeedProbableStarter>(
          {
            gameId: game.gameId,
            side,
            personId: String(pitcher.id),
            fullName: String(pitcher.fullName),
          },
          'mlb-stats-api:game-feed',
          raw,
          `${game.gameId}:${side}:${pitcher.id}`,
          path,
          game.season
        );
        result.validationWarnings.push('PROBABLE_STARTER_FALLBACK_MLB_GAME_FEED');
        results.push(result);
      }
    }
    return results;
  }
}

// ---------------------------------------------------------------------------
// Bullpen adapter — active-roster pitchers with zero season starts
// ---------------------------------------------------------------------------

export class MlbBullpenStatsProvider implements BullpenStatsProvider {
  async getTeamBullpen(teamId: string, season: number) {
    if (!/^\d+$/.test(teamId) || !Number.isInteger(season)) {
      throw new Error(`Invalid bullpen request: team=${teamId}, season=${season}`);
    }

    // Hydrating season stats on the roster reduces the ZIP's 13+ requests per
    // team to one official MLB Stats API request per team.
    const hydrate = `person(stats(group=[pitching],type=[season],season=${season}))`;
    const query = new URLSearchParams({ rosterType: 'active', season: String(season), hydrate });
    const path = `/api/v1/teams/${teamId}/roster?${query.toString()}`;
    const raw = await fetchJson(path) as any;
    const pitchers = (raw.roster ?? []).filter((entry: any) => entry.position?.abbreviation === 'P');

    let outsRecorded = 0;
    let earnedRuns = 0;
    let walks = 0;
    let hits = 0;
    let strikeouts = 0;
    let gamesPitched = 0;
    let relievers = 0;
    let excludedSwingmen = 0;
    let skippedWithoutStats = 0;

    for (const entry of pitchers) {
      const splits = (entry.person?.stats ?? []).flatMap((stats: any) => stats.splits ?? []);
      const split = splits.find((candidate: any) => String(candidate.season ?? season) === String(season)) ?? splits[0];
      const stat = split?.stat;
      if (!stat) {
        skippedWithoutStats += 1;
        continue;
      }
      if (Number(stat.gamesStarted ?? 0) > 0) {
        excludedSwingmen += 1;
        continue;
      }

      let outs = Number(stat.outs);
      if (!Number.isInteger(outs) || outs < 0) {
        try {
          outs = inningsToOuts(String(stat.inningsPitched ?? '0.0'));
        } catch {
          skippedWithoutStats += 1;
          continue;
        }
      }
      if (outs === 0) {
        skippedWithoutStats += 1;
        continue;
      }

      outsRecorded += outs;
      earnedRuns += Number(stat.earnedRuns ?? 0);
      walks += Number(stat.baseOnBalls ?? 0);
      hits += Number(stat.hits ?? 0);
      strikeouts += Number(stat.strikeOuts ?? 0);
      gamesPitched += Number(stat.gamesPitched ?? 0);
      relievers += 1;
    }

    if (relievers === 0 || outsRecorded === 0) {
      throw new Error(`No qualifying active-roster reliever stats for MLB team ${teamId}`);
    }

    const data: BullpenStats = {
      teamId,
      season,
      era: Number(((earnedRuns * 27) / outsRecorded).toFixed(2)),
      whip: Number((((walks + hits) * 3) / outsRecorded).toFixed(2)),
      inningsPitched: outsToInningsDisplay(outsRecorded),
      outsRecorded,
      relievers,
      gamesPitched,
      earnedRuns,
      walks,
      hits,
      strikeouts,
      excludedSwingmen,
      skippedWithoutStats,
    };
    const result = makeResult(
      data,
      'mlb-stats-api:active-roster-pure-relievers',
      raw,
      teamId,
      path,
      season
    );
    result.validationWarnings.push('BULLPEN_ACTIVE_ROSTER_AT_FETCH_TIME');
    if (excludedSwingmen > 0) result.validationWarnings.push(`BULLPEN_EXCLUDES_SWINGMEN:${excludedSwingmen}`);
    if (skippedWithoutStats > 0) result.validationWarnings.push(`BULLPEN_PLAYERS_WITHOUT_STATS:${skippedWithoutStats}`);
    return result;
  }
}

function numberOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function normalizeStatus(state?: string, detailedState?: string): ScheduledGame['status'] {
  const detail = detailedState?.toLowerCase() ?? '';
  if (detail.includes('postponed')) return 'postponed';
  if (detail.includes('cancelled') || detail.includes('canceled')) return 'cancelled';
  switch (state) {
    case 'Live': return 'in_progress';
    case 'Final': return 'final';
    case 'Preview': return 'scheduled';
    case 'Postponed': return 'postponed';
    default: return 'scheduled';
  }
}

// ---------------------------------------------------------------------------
// Pitcher stats adapter
// ---------------------------------------------------------------------------

export class MlbPitcherStatsProvider implements PitcherStatsProvider {
  async findPersonByName(fullName: string, season: number) {
    const query = new URLSearchParams({ names: fullName, sportIds: '1' });
    const path = `/api/v1/people/search?${query.toString()}`;
    const raw = await fetchJson(path);
    const normalizedName = fullName.toLowerCase().replace(/[^a-z0-9]/g, '');
    const matches = ((raw as any)?.people ?? []).filter((person: any) =>
      String(person.fullName ?? '').toLowerCase().replace(/[^a-z0-9]/g, '') === normalizedName
      && person.active !== false
      && person.primaryPosition?.type === 'Pitcher'
    );
    if (matches.length !== 1) return null;

    const person = matches[0];
    const data = { personId: String(person.id), fullName: String(person.fullName) };
    const result = makeResult(data, 'mlb-stats-api:person-search', raw, data.personId, path, season);
    result.validationWarnings.push('PLAYER_ID_MATCHED_BY_EXACT_NAME');
    return result;
  }

  async getSeasonStats(personId: string, season: number) {
    const path = `/api/v1/people/${personId}/stats?stats=season&season=${season}&group=pitching`;
    const raw = await fetchJson(path);
    const splits = (raw as any)?.stats?.[0]?.splits ?? [];
    const s = splits[0]?.stat;

    if (!s) {
      const minorFallback = await this.getMinorLeagueSeasonStats(personId, season);
      if (minorFallback) return minorFallback;
      return {
        provider: 'mlb-stats-api',
        providerId: personId,
        sourceIdentifier: path,
        retrievedAt: new Date(),
        season,
        sourceTimezone: 'America/New_York',
        rawChecksum: checksum(raw),
        data: null as unknown as PitcherSeasonStats,
        freshnessState: 'missing' as FreshnessState,
        validationWarnings: ['NO_SEASON_STATS'],
      };
    }

    let outsRecorded = 0;
    const warnings: string[] = [];
    try {
      outsRecorded = inningsToOuts(String(s.inningsPitched));
    } catch {
      warnings.push('INVALID_INNINGS_NOTATION');
    }

    const data: PitcherSeasonStats = {
      personId,
      season,
      era: parseFloat(s.era ?? '0'),
      whip: parseFloat(s.whip ?? '0'),
      inningsPitched: parseFloat(s.inningsPitched ?? '0'),
      outsRecorded,
      gamesStarted: s.gamesStarted ?? 0,
      earnedRuns: s.earnedRuns ?? 0,
      walks: s.baseOnBalls ?? 0,
      strikeouts: s.strikeOuts ?? 0,
    };

    return { ...makeResult(data, 'mlb-stats-api', raw, personId, path, season), validationWarnings: warnings };
  }

  async getGameLogs(personId: string, season: number, lastN = 5) {
    const path = `/api/v1/people/${personId}/stats?stats=gameLog&season=${season}&group=pitching`;
    const raw = await fetchJson(path);
    const splits: any[] = (raw as any)?.stats?.[0]?.splits ?? [];

    const sorted = [...splits]
      .filter((split) => Number(split.stat?.gamesStarted ?? 0) > 0)
      .sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    const mlbLogs = sorted.map((split) => {
      const s = split.stat;
      let outsRecorded = 0;
      const warnings: string[] = [];
      try {
        outsRecorded = inningsToOuts(String(s.inningsPitched));
      } catch {
        warnings.push('INVALID_INNINGS_NOTATION');
      }
      const earnedRuns = s.earnedRuns ?? 0;
      const gameEra = computeEra(earnedRuns, outsRecorded);
      const log: PitcherGameLog = {
        personId,
        gameDate: split.date,
        season,
        earnedRuns,
        outsRecorded,
        gameEra,
        isGoodStart: gameEra < 4.0,
      };
      return { ...makeResult(log, 'mlb-stats-api', split, personId, path, season), validationWarnings: warnings };
    });

    if (mlbLogs.length >= lastN) return mlbLogs.slice(0, lastN);

    const fallbackLogs = [];
    for (const sportId of MINOR_LEAGUE_SPORT_IDS) {
      const minorPath = `/api/v1/people/${personId}/stats?stats=gameLog&season=${season}&group=pitching&sportId=${sportId}`;
      const minorRaw = await fetchJson(minorPath);
      const minorSplits: any[] = (minorRaw as any)?.stats?.[0]?.splits ?? [];
      for (const split of minorSplits) {
        if (Number(split.stat?.gamesStarted ?? 0) <= 0 || !split.date) continue;
        let outsRecorded = 0;
        try {
          outsRecorded = inningsToOuts(String(split.stat.inningsPitched));
        } catch {
          continue;
        }
        if (outsRecorded <= 0) continue;
        const earnedRuns = Number(split.stat.earnedRuns ?? 0);
        const log: PitcherGameLog = {
          personId,
          gameDate: split.date,
          season,
          earnedRuns,
          outsRecorded,
          gameEra: computeEra(earnedRuns, outsRecorded),
          isGoodStart: computeEra(earnedRuns, outsRecorded) < 4.0,
        };
        const result = makeResult(
          log,
          `mlb-stats-api:minor-league-fallback:sport-${sportId}`,
          split,
          `${personId}:${split.date}:${sportId}`,
          minorPath,
          season
        );
        result.validationWarnings.push('MINOR_LEAGUE_GAME_LOG_NOT_MLB_EQUIVALENT');
        fallbackLogs.push(result);
      }
      if (mlbLogs.length + fallbackLogs.length >= lastN) break;
    }

    return [...mlbLogs, ...fallbackLogs]
      .sort((a, b) => new Date(b.data.gameDate).getTime() - new Date(a.data.gameDate).getTime())
      .filter((result, index, all) => all.findIndex((candidate) => candidate.data.gameDate === result.data.gameDate) === index)
      .slice(0, lastN);
  }

  private async getMinorLeagueSeasonStats(personId: string, season: number) {
    for (const sportId of MINOR_LEAGUE_SPORT_IDS) {
      const path = `/api/v1/people/${personId}/stats?stats=season&season=${season}&group=pitching&sportId=${sportId}`;
      const raw = await fetchJson(path);
      const splits: any[] = (raw as any)?.stats?.[0]?.splits ?? [];
      if (splits.length === 0) continue;

      // When a player changed clubs, MLB returns a teamless aggregate plus the
      // team splits. Prefer that aggregate so innings are not double counted.
      const split = splits.find((candidate) => !candidate.team) ?? splits[0];
      const stat = split?.stat;
      if (!stat) continue;
      let outsRecorded = Number(stat.outs);
      if (!Number.isInteger(outsRecorded) || outsRecorded <= 0) {
        try {
          outsRecorded = inningsToOuts(String(stat.inningsPitched));
        } catch {
          continue;
        }
      }
      const data: PitcherSeasonStats = {
        personId,
        season,
        era: Number.parseFloat(stat.era ?? '0'),
        whip: Number.parseFloat(stat.whip ?? '0'),
        inningsPitched: Number.parseFloat(stat.inningsPitched ?? '0'),
        outsRecorded,
        gamesStarted: Number(stat.gamesStarted ?? 0),
        earnedRuns: Number(stat.earnedRuns ?? 0),
        walks: Number(stat.baseOnBalls ?? 0),
        strikeouts: Number(stat.strikeOuts ?? 0),
      };
      const result = makeResult(
        data,
        `mlb-stats-api:minor-league-fallback:sport-${sportId}`,
        raw,
        `${personId}:${sportId}`,
        path,
        season
      );
      result.validationWarnings.push('MINOR_LEAGUE_SEASON_STATS_NOT_MLB_EQUIVALENT');
      return result;
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// Team stats adapter
// ---------------------------------------------------------------------------

export class MlbTeamStatsProvider implements TeamStatsProvider {
  private standingsBySeason = new Map<number, Promise<unknown>>();

  async getTeamStats(teamId: string, season: number) {
    let standingsPromise = this.standingsBySeason.get(season);
    if (!standingsPromise) {
      standingsPromise = fetchJson(`/api/v1/standings?leagueId=103,104&season=${season}&standingsTypes=regularSeason`);
      this.standingsBySeason.set(season, standingsPromise);
    }
    const [hittingRaw, standingsRaw] = await Promise.all([
      fetchJson(`/api/v1/teams/${teamId}/stats?stats=season&season=${season}&group=hitting`),
      standingsPromise,
    ]);

    const hittingStats = (hittingRaw as any)?.stats?.[0]?.splits?.[0]?.stat;
    const warnings: string[] = [];

    // Find team in standings
    let wins = 0, losses = 0, last10Wins = 0, last10Losses = 0, streak = 0;
    for (const record of (standingsRaw as any)?.records ?? []) {
      for (const entry of record.teamRecords ?? []) {
        if (String(entry.team?.id) === teamId) {
          wins = entry.wins ?? 0;
          losses = entry.losses ?? 0;
          const l10 = entry.records?.splitRecords?.find((r: any) => r.type === 'lastTen');
          last10Wins = l10?.wins ?? 0;
          last10Losses = l10?.losses ?? 0;
          const streakEntry = entry.streak;
          if (streakEntry) {
            streak = streakEntry.streakType === 'wins'
              ? streakEntry.streakNumber
              : -streakEntry.streakNumber;
          }
        }
      }
    }

    if (!hittingStats) {
      warnings.push('NO_HITTING_STATS');
    }

    const data: TeamSeasonStats = {
      teamId,
      season,
      avg: parseFloat(hittingStats?.avg ?? '0'),
      ops: parseFloat(hittingStats?.ops ?? '0'),
      runsPerGame: parseFloat(hittingStats?.runs ?? '0') / Math.max(wins + losses, 1),
      wins,
      losses,
      last10Wins,
      last10Losses,
      currentStreak: streak,
    };

    return {
      ...makeResult(data, 'mlb-stats-api', { hittingRaw, standingsRaw }, teamId, undefined, season),
      validationWarnings: warnings,
    };
  }
}

// ---------------------------------------------------------------------------
// Results adapter
// ---------------------------------------------------------------------------

export class MlbResultsProvider implements ResultsProvider {
  async getResult(gameId: string) {
    const path = `/api/v1.1/game/${gameId}/feed/live`;
    const raw = await fetchJson(path);
    const g = raw as any;
    const abstractState = String(g.gameData?.status?.abstractGameState ?? '');
    const detailedState = String(g.gameData?.status?.detailedState ?? '');

    // An available feed for a game that is not final is a valid empty result.
    // Transport/provider failures must propagate so callers do not report a
    // successful refresh while leaving completed games marked as scheduled.
    if (abstractState !== 'Final') return null;

    const homeScore = g.liveData?.linescore?.teams?.home?.runs;
    const awayScore = g.liveData?.linescore?.teams?.away?.runs;
    if (!Number.isInteger(homeScore) || !Number.isInteger(awayScore)) return null;

    const data: GameResultData = {
      gameId,
      homeScore,
      awayScore,
      finalStatus: 'final',
      officialAt: new Date(),
    };
    return {
      ...makeResult(data, 'mlb-stats-api', raw, gameId, path),
      validationWarnings: detailedState.toLowerCase().includes('final')
        ? []
        : [`UNUSUAL_FINAL_STATUS:${detailedState || 'UNKNOWN'}`],
    };
  }
}
