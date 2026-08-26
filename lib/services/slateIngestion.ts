import { prisma } from '@/lib/db';
import { analyzeGame } from '@/lib/engine/pipeline';
import {
  MlbPitcherStatsProvider,
  MlbBullpenStatsProvider,
  MlbGameFeedProbableStarterProvider,
  MlbScheduleProvider,
  MlbTeamStatsProvider,
  MlbResultsProvider,
} from '@/lib/providers/mlbStatsApi';
import { OneXbitOddsProvider, TheOddsApiProvider } from '@/lib/providers/oddsProvider';
import { EspnCoreProbableStarterProvider } from '@/lib/providers/espnCore';
import { ingestResultAndGrade } from '@/lib/engine/forecast';
import { PARK_FACTORS_2026 } from '@/lib/fixtures/parkFactors2026';
import type { ScheduledGame } from '@/lib/providers/interfaces';

type ProviderEnvelope<T> = {
  provider: string;
  providerId?: string;
  sourceIdentifier?: string;
  retrievedAt: Date;
  effectiveAt?: Date;
  season?: number;
  sourceTimezone?: string;
  rawChecksum: string;
  data: T;
  freshnessState: string;
  validationWarnings: string[];
};

export interface SlateRefreshSummary {
  ok: boolean;
  date: string;
  scheduleSource: 'live' | 'cache';
  scheduleGames: number;
  teamsUpdated: number;
  startersUpdated: number;
  pitcherSnapshots: number;
  teamSnapshots: number;
  bullpenSnapshots: number;
  oddsSnapshots: number;
  starterFallbacks: number;
  missingStarterSides: number;
  analyzed: number;
  analysisErrors: number;
  warnings: string[];
  errors: Array<{ scope: string; message: string }>;
  oddsQuotaRemaining?: string;
}

export async function refreshSlate(date: string): Promise<SlateRefreshSummary> {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(new Date(`${date}T00:00:00Z`).getTime())) {
    throw new Error(`Invalid slate date: ${date}`);
  }

  const summary: SlateRefreshSummary = {
    ok: true,
    date,
    scheduleSource: 'live',
    scheduleGames: 0,
    teamsUpdated: 0,
    startersUpdated: 0,
    pitcherSnapshots: 0,
    teamSnapshots: 0,
    bullpenSnapshots: 0,
    oddsSnapshots: 0,
    starterFallbacks: 0,
    missingStarterSides: 0,
    analyzed: 0,
    analysisErrors: 0,
    warnings: [],
    errors: [],
  };

  const scheduleProvider = new MlbScheduleProvider();
  let games: ScheduledGame[];
  try {
    const scheduleResults = await scheduleProvider.getSchedule(date);
    games = scheduleResults.map((result) => result.data);
    summary.scheduleGames = games.length;
    for (const result of scheduleResults) {
      await persistSchedule(result);
      summary.teamsUpdated += 2;
    }
  } catch (error) {
    games = await loadCachedSchedule(date);
    if (games.length === 0) throw error;
    summary.scheduleSource = 'cache';
    summary.scheduleGames = games.length;
    summary.warnings.push('SCHEDULE_CACHE_FALLBACK');
    summary.errors.push({ scope: 'schedule:mlb-stats-api', message: errorMessage(error) });
  }

  // Odds are independent of MLB stat enrichment. Refresh them immediately so
  // a temporary schedule/stats outage cannot leave an otherwise available
  // market feed stale.
  await refreshOddsForGames(games, summary);

  if (summary.scheduleSource === 'cache') {
    summary.warnings.push('MLB_STAT_ENRICHMENT_SKIPPED_USING_CACHED_INPUTS');
    await analyzeGames(games, summary);
    summary.ok = summary.scheduleGames > 0 && summary.analysisErrors === 0;
    return summary;
  }

  const pitcherProvider = new MlbPitcherStatsProvider();
  const starterSources = await repairMissingProbableStarters(games, pitcherProvider, summary);
  summary.missingStarterSides = games.reduce((count, game) => count
    + (!game.homeStarterPersonId || !game.homeStarterName ? 1 : 0)
    + (!game.awayStarterPersonId || !game.awayStarterName ? 1 : 0), 0);

  // Seed park factors for all venues if not already present for this season
  const season = games.length > 0 ? games[0].season : new Date().getFullYear();
  await seedParkFactors(season);

  const teamProvider = new MlbTeamStatsProvider();
  const uniqueTeams = new Map<string, { teamId: string; season: number; gameId: string }>();
  for (const game of games) {
    uniqueTeams.set(`${game.homeTeamId}:${game.season}`, {
      teamId: game.homeTeamId,
      season: game.season,
      gameId: game.gameId,
    });
    uniqueTeams.set(`${game.awayTeamId}:${game.season}`, {
      teamId: game.awayTeamId,
      season: game.season,
      gameId: game.gameId,
    });
  }

  await mapLimit([...uniqueTeams.values()], 4, async ({ teamId, season, gameId }) => {
    try {
      const result = await teamProvider.getTeamStats(teamId, season);
      const sourceObservationId = await persistObservation(result, 'team_stats', gameId);
      await prisma.teamSnapshot.create({
        data: {
          ...result.data,
          sourceProvider: result.provider,
          sourceObservationId,
          retrievedAt: result.retrievedAt,
          freshnessState: result.freshnessState,
        },
      });
      summary.teamSnapshots += 1;
      summary.warnings.push(...result.validationWarnings.map((warning) => `${warning}:${teamId}`));
    } catch (error) {
      summary.errors.push({ scope: `team:${teamId}`, message: errorMessage(error) });
    }
  });

  const configuredBullpenProvider = (process.env.BULLPEN_PROVIDER ?? '').toLowerCase();
  if (configuredBullpenProvider === 'mlb-roster') {
    const bullpenProvider = new MlbBullpenStatsProvider();
    await mapLimit([...uniqueTeams.values()], 4, async ({ teamId, season, gameId }) => {
      try {
        const result = await bullpenProvider.getTeamBullpen(teamId, season);
        await persistObservation(result, 'bullpen_stats', gameId);
        const latestTeamSnapshot = await prisma.teamSnapshot.findFirst({
          where: { teamId, season },
          orderBy: { retrievedAt: 'desc' },
        });
        if (!latestTeamSnapshot) throw new Error(`Team snapshot missing for bullpen enrichment: ${teamId}`);
        await prisma.teamSnapshot.update({
          where: { id: latestTeamSnapshot.id },
          data: {
            bullpenEra: result.data.era,
            bullpenWhip: result.data.whip,
          },
        });
        summary.bullpenSnapshots += 1;
        summary.warnings.push(...result.validationWarnings.map((warning) => `${warning}:${teamId}`));
      } catch (error) {
        summary.errors.push({ scope: `bullpen:${teamId}`, message: errorMessage(error) });
      }
    });
  } else if (configuredBullpenProvider) {
    summary.warnings.push(`UNSUPPORTED_BULLPEN_PROVIDER:${configuredBullpenProvider}`);
  } else {
    summary.warnings.push('BULLPEN_PROVIDER_NOT_CONFIGURED');
  }

  await mapLimit(games, 3, async (game) => {
    await Promise.all([
      ingestStarter(game, 'home', pitcherProvider, summary, starterSources.get(`${game.gameId}:home`)),
      ingestStarter(game, 'away', pitcherProvider, summary, starterSources.get(`${game.gameId}:away`)),
    ]);
  });

  await analyzeGames(games, summary);

  summary.ok = summary.scheduleGames > 0 && summary.analysisErrors === 0;
  return summary;
}

async function refreshOddsForGames(
  games: ScheduledGame[],
  summary: SlateRefreshSummary,
): Promise<void> {
  const configuredOddsProvider = (process.env.ODDS_PROVIDER ?? '').toLowerCase();
  if (configuredOddsProvider !== 'the-odds-api' && configuredOddsProvider !== '1xbit') {
    if (configuredOddsProvider) summary.warnings.push(`UNSUPPORTED_ODDS_PROVIDER:${configuredOddsProvider}`);
    else summary.warnings.push('ODDS_PROVIDER_NOT_CONFIGURED');
    return;
  }

  try {
    const oddsProvider = configuredOddsProvider === '1xbit'
      ? new OneXbitOddsProvider()
      : new TheOddsApiProvider();
    const oddsResult = await oddsProvider.getOddsForGames(games);
    summary.warnings.push(...oddsResult.warnings);
    summary.oddsQuotaRemaining = oddsResult.quotaRemaining;
    for (const result of oddsResult.odds) {
      await persistObservation(result, 'odds', result.data.gameId);
      summary.warnings.push(...result.validationWarnings.map(
        (warning) => `${warning}:${result.data.gameId}`
      ));
      await prisma.marketSnapshot.create({
        data: {
          gameId: result.data.gameId,
          provider: result.provider,
          retrievedAt: result.quoteUpdatedAt,
          moneylineHome: result.data.moneylineHome,
          moneylineAway: result.data.moneylineAway,
          moneylineHomeOrig: result.data.moneylineHomeOrig,
          moneylineAwayOrig: result.data.moneylineAwayOrig,
          totalLine: result.data.totalLine,
          totalOverDecimal: result.data.totalOverDecimal,
          totalUnderDecimal: result.data.totalUnderDecimal,
          freshnessState: result.freshnessState,
        },
      });
      summary.oddsSnapshots += 1;
    }
  } catch (error) {
    summary.errors.push({ scope: `odds:${configuredOddsProvider}`, message: errorMessage(error) });
  }
}

async function analyzeGames(games: ScheduledGame[], summary: SlateRefreshSummary): Promise<void> {
  const analysis = await Promise.allSettled(games.map((game) => analyzeGame(game.gameId)));
  for (const result of analysis) {
    if (result.status === 'fulfilled' && !result.value.error) {
      summary.analyzed += 1;
    } else {
      summary.analysisErrors += 1;
      const message = result.status === 'rejected'
        ? errorMessage(result.reason)
        : result.value.error ?? 'Unknown analysis error';
      summary.errors.push({ scope: 'analysis', message });
    }
  }
}

async function loadCachedSchedule(date: string): Promise<ScheduledGame[]> {
  const cached = await prisma.game.findMany({
    where: { date },
    include: {
      homeTeam: true,
      awayTeam: true,
      venue: true,
      probableStarterObservations: {
        orderBy: { retrievedAt: 'desc' },
        include: { person: true },
      },
    },
    orderBy: { startTimeUtc: 'asc' },
  });

  return cached.map((game) => {
    const homeStarter = game.probableStarterObservations.find((starter) => starter.side === 'home');
    const awayStarter = game.probableStarterObservations.find((starter) => starter.side === 'away');
    return {
      gameId: game.id,
      date: game.date,
      startTimeUtc: game.startTimeUtc,
      homeTeamId: game.homeTeamId,
      awayTeamId: game.awayTeamId,
      venueId: game.venueId,
      season: game.season,
      status: game.status as ScheduledGame['status'],
      homeTeamName: game.homeTeam.name,
      awayTeamName: game.awayTeam.name,
      venueName: game.venue.name,
      homeStarterPersonId: homeStarter?.personId,
      awayStarterPersonId: awayStarter?.personId,
      homeStarterName: homeStarter?.person.fullName,
      awayStarterName: awayStarter?.person.fullName,
      homeTeamAbbreviation: game.homeTeam.abbreviation,
      awayTeamAbbreviation: game.awayTeam.abbreviation,
      homeTeamCity: game.homeTeam.city,
      awayTeamCity: game.awayTeam.city,
      homeLeagueId: game.homeTeam.leagueId,
      awayLeagueId: game.awayTeam.leagueId,
      homeDivisionId: game.homeTeam.divisionId,
      awayDivisionId: game.awayTeam.divisionId,
    };
  });
}

async function persistSchedule(result: ProviderEnvelope<ScheduledGame>): Promise<void> {
  const game = result.data;
  await prisma.$transaction(async (tx) => {
    await tx.team.upsert({
      where: { id: game.homeTeamId },
      create: teamCreateData(game, 'home'),
      update: teamUpdateData(game, 'home'),
    });
    await tx.team.upsert({
      where: { id: game.awayTeamId },
      create: teamCreateData(game, 'away'),
      update: teamUpdateData(game, 'away'),
    });
    await tx.venue.upsert({
      where: { id: game.venueId },
      create: { id: game.venueId, name: game.venueName, city: 'Unknown' },
      update: { name: game.venueName },
    });
    await tx.game.upsert({
      where: { id: game.gameId },
      create: {
        id: game.gameId,
        date: game.date,
        startTimeUtc: game.startTimeUtc,
        status: game.status,
        homeTeamId: game.homeTeamId,
        awayTeamId: game.awayTeamId,
        venueId: game.venueId,
        season: game.season,
      },
      update: {
        date: game.date,
        startTimeUtc: game.startTimeUtc,
        status: game.status,
        homeTeamId: game.homeTeamId,
        awayTeamId: game.awayTeamId,
        venueId: game.venueId,
        season: game.season,
      },
    });
  });
  await persistObservation(result, 'schedule', game.gameId);
}

function teamCreateData(game: ScheduledGame, side: 'home' | 'away') {
  const name = side === 'home' ? game.homeTeamName : game.awayTeamName;
  const abbreviation = side === 'home' ? game.homeTeamAbbreviation : game.awayTeamAbbreviation;
  return {
    id: side === 'home' ? game.homeTeamId : game.awayTeamId,
    name,
    abbreviation: abbreviation ?? name.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase(),
    city: (side === 'home' ? game.homeTeamCity : game.awayTeamCity) ?? 'Unknown',
    leagueId: (side === 'home' ? game.homeLeagueId : game.awayLeagueId) ?? 0,
    divisionId: (side === 'home' ? game.homeDivisionId : game.awayDivisionId) ?? 0,
  };
}

function teamUpdateData(game: ScheduledGame, side: 'home' | 'away') {
  const create = teamCreateData(game, side);
  const { id: _id, ...update } = create;
  return update;
}

async function repairMissingProbableStarters(
  games: ScheduledGame[],
  pitcherProvider: MlbPitcherStatsProvider,
  summary: SlateRefreshSummary
): Promise<Map<string, { provider: string; confirmationStatus: 'confirmed' | 'probable' }>> {
  const sources = new Map<string, { provider: string; confirmationStatus: 'confirmed' | 'probable' }>();
  const hasMissingSide = games.some((game) =>
    !game.homeStarterPersonId || !game.homeStarterName
    || !game.awayStarterPersonId || !game.awayStarterName
  );
  if (!hasMissingSide) return sources;

  try {
    const feedResults = await new MlbGameFeedProbableStarterProvider().getMissingStarters(games);
    for (const result of feedResults) {
      const game = games.find((candidate) => candidate.gameId === result.data.gameId);
      if (!game) continue;
      await persistObservation(result, 'probable_starter', game.gameId);
      if (result.data.side === 'home') {
        game.homeStarterPersonId = result.data.personId;
        game.homeStarterName = result.data.fullName;
      } else {
        game.awayStarterPersonId = result.data.personId;
        game.awayStarterName = result.data.fullName;
      }
      sources.set(`${game.gameId}:${result.data.side}`, {
        provider: result.provider,
        confirmationStatus: 'confirmed',
      });
      summary.starterFallbacks += 1;
      summary.warnings.push(...result.validationWarnings.map(
        (warning) => `${warning}:${game.gameId}:${result.data.side}`
      ));
    }
  } catch (error) {
    summary.errors.push({ scope: 'starter-fallback:mlb-game-feed', message: errorMessage(error) });
  }

  let fallbackResults;
  try {
    fallbackResults = await new EspnCoreProbableStarterProvider().getMissingStarters(games);
  } catch (error) {
    summary.errors.push({ scope: 'starter-fallback:espn-core', message: errorMessage(error) });
    return sources;
  }

  for (const result of fallbackResults) {
    const game = games.find((candidate) => candidate.gameId === result.data.gameId);
    if (!game) continue;
    await persistObservation(result, 'probable_starter', game.gameId);
    summary.warnings.push(...result.validationWarnings.map(
      (warning) => `${warning}:${game.gameId}:${result.data.side}`
    ));

    try {
      const identity = await pitcherProvider.findPersonByName(result.data.fullName, game.season);
      if (!identity) {
        summary.warnings.push(
          `PROBABLE_STARTER_ID_UNRESOLVED:${game.gameId}:${result.data.side}:${result.data.fullName}`
        );
        continue;
      }
      await persistObservation(identity, 'player_identity', game.gameId);

      if (result.data.side === 'home') {
        game.homeStarterPersonId = identity.data.personId;
        game.homeStarterName = identity.data.fullName;
      } else {
        game.awayStarterPersonId = identity.data.personId;
        game.awayStarterName = identity.data.fullName;
      }
      sources.set(`${game.gameId}:${result.data.side}`, {
        provider: result.provider,
        confirmationStatus: 'probable',
      });
      summary.starterFallbacks += 1;
      summary.warnings.push(...identity.validationWarnings.map(
        (warning) => `${warning}:${identity.data.personId}`
      ));
    } catch (error) {
      summary.errors.push({
        scope: `starter-fallback-identity:${game.gameId}:${result.data.side}`,
        message: errorMessage(error),
      });
    }
  }

  return sources;
}

async function ingestStarter(
  game: ScheduledGame,
  side: 'home' | 'away',
  provider: MlbPitcherStatsProvider,
  summary: SlateRefreshSummary,
  fallbackSource?: { provider: string; confirmationStatus: 'confirmed' | 'probable' }
): Promise<void> {
  const personId = side === 'home' ? game.homeStarterPersonId : game.awayStarterPersonId;
  const fullName = side === 'home' ? game.homeStarterName : game.awayStarterName;
  if (!personId || !fullName) {
    summary.warnings.push(`PROBABLE_STARTER_MISSING:${game.gameId}:${side}`);
    return;
  }

  try {
    await prisma.person.upsert({
      where: { id: personId },
      create: { id: personId, fullName, position: 'Pitcher' },
      update: { fullName, position: 'Pitcher' },
    });
    const starterObservation = await prisma.probableStarterObservation.create({
      data: {
        gameId: game.gameId,
        personId,
        side,
        confirmationStatus: fallbackSource?.confirmationStatus ?? 'confirmed',
        retrievedAt: new Date(),
        sourceProvider: fallbackSource?.provider ?? 'mlb-stats-api',
      },
    });
    summary.startersUpdated += 1;

    const [seasonResult, logsResult] = await Promise.allSettled([
      provider.getSeasonStats(personId, game.season),
      provider.getGameLogs(personId, game.season, 5),
    ]);

    if (seasonResult.status === 'fulfilled' && seasonResult.value.freshnessState !== 'missing') {
      const result = seasonResult.value;
      const sourceObservationId = await persistObservation(result, 'pitcher_stats', game.gameId);
      await prisma.pitcherSnapshot.create({
        data: {
          ...result.data,
          sourceProvider: result.provider,
          sourceObservationId,
          retrievedAt: result.retrievedAt,
          freshnessState: result.freshnessState,
        },
      });
      await prisma.probableStarterObservation.update({
        where: { id: starterObservation.id },
        data: {
          gamesStarted: result.data.gamesStarted,
          roleLabel: result.data.gamesStarted === 0 ? 'reliever' : 'starter',
        },
      });
      summary.pitcherSnapshots += 1;
      summary.warnings.push(...result.validationWarnings.map((warning) => `${warning}:${personId}`));
    } else {
      const message = seasonResult.status === 'rejected'
        ? errorMessage(seasonResult.reason)
        : `No season stats for ${personId}`;
      summary.errors.push({ scope: `pitcher-season:${personId}`, message });
    }

    if (logsResult.status === 'fulfilled') {
      for (const result of logsResult.value) {
        const sourceObservationId = await persistObservation(result, 'pitcher_game_log', game.gameId);
        const existing = await prisma.pitcherGameLogStart.findFirst({
          where: { personId, season: game.season, gameDate: result.data.gameDate },
        });
        const values = {
          earnedRuns: result.data.earnedRuns,
          outsRecorded: result.data.outsRecorded,
          gameEra: result.data.gameEra,
          isGoodStart: result.data.isGoodStart,
          sourceProvider: result.provider,
          sourceObservationId,
          retrievedAt: result.retrievedAt,
        };
        if (existing) {
          await prisma.pitcherGameLogStart.update({ where: { id: existing.id }, data: values });
        } else {
          await prisma.pitcherGameLogStart.create({
            data: { personId, season: game.season, gameDate: result.data.gameDate, ...values },
          });
        }
      }
    } else {
      summary.errors.push({ scope: `pitcher-logs:${personId}`, message: errorMessage(logsResult.reason) });
    }
  } catch (error) {
    summary.errors.push({ scope: `starter:${game.gameId}:${side}`, message: errorMessage(error) });
  }
}

async function persistObservation<T>(
  result: ProviderEnvelope<T>,
  dataType: string,
  gameId?: string
): Promise<string | undefined> {
  const existing = await prisma.sourceObservation.findFirst({
    where: {
      provider: result.provider,
      providerId: result.providerId,
      rawChecksum: result.rawChecksum,
    },
    select: { id: true },
  });
  if (existing) {
    // The provider can legitimately return an unchanged payload on a later
    // refresh.  The checksum uniqueness constraint prevents a duplicate raw
    // row, but the successful retrieval is still new freshness evidence.
    // Refresh the observation metadata so unchanged bullpen/team payloads do
    // not become "stale" immediately after a successful scrape.
    await prisma.sourceObservation.update({
      where: { id: existing.id },
      data: {
        retrievedAt: result.retrievedAt,
        effectiveAt: result.effectiveAt,
        sourceIdentifier: result.sourceIdentifier,
        sourceTimezone: result.sourceTimezone,
        freshnessState: result.freshnessState,
        normalizedData: JSON.stringify(result.data),
        validationWarnings: JSON.stringify(result.validationWarnings),
      },
    });
    return existing.id;
  }

  const observation = await prisma.sourceObservation.create({
    data: {
      gameId,
      provider: result.provider,
      providerId: result.providerId,
      sourceIdentifier: result.sourceIdentifier,
      retrievedAt: result.retrievedAt,
      effectiveAt: result.effectiveAt,
      season: result.season,
      sourceTimezone: result.sourceTimezone,
      rawChecksum: result.rawChecksum,
      normalizedData: JSON.stringify(result.data),
      freshnessState: result.freshnessState,
      validationWarnings: JSON.stringify(result.validationWarnings),
      dataType,
    },
  });
  return observation.id;
}

async function mapLimit<T>(items: T[], limit: number, worker: (item: T) => Promise<void>): Promise<void> {
  let nextIndex = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const item = items[nextIndex];
      nextIndex += 1;
      await worker(item);
    }
  });
  await Promise.all(workers);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// ---------------------------------------------------------------------------
// Park factor seeding
// ---------------------------------------------------------------------------

async function seedParkFactors(season: number): Promise<void> {
  for (const pf of PARK_FACTORS_2026) {
    // Only seed if the venue already exists in the database
    const venue = await prisma.venue.findUnique({ where: { id: pf.venueId } });
    if (!venue) continue;

    const existing = await prisma.parkFactorSnapshot.findFirst({
      where: { venueId: pf.venueId, season },
    });
    if (!existing) {
      await prisma.parkFactorSnapshot.create({
        data: {
          venueId: pf.venueId,
          season,
          factor: pf.factor,
          source: pf.source,
          // Historical averages are placeholders even when stamped for the
          // current season; they are not authoritative current-season data.
          isFallback: true,
        },
      });
    } else if (existing.source === 'historical-avg' && !existing.isFallback) {
      await prisma.parkFactorSnapshot.update({
        where: { id: existing.id },
        data: { isFallback: true },
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Results refresh (used by worker)
// ---------------------------------------------------------------------------

export interface ResultsRefreshSummary {
  ok: boolean;
  date: string;
  gamesChecked: number;
  settled: number;
  errors: Array<{ gameId: string; message: string }>;
}

export async function refreshResults(date: string): Promise<ResultsRefreshSummary> {
  const summary: ResultsRefreshSummary = {
    ok: true,
    date,
    gamesChecked: 0,
    settled: 0,
    errors: [],
  };

  const games = await prisma.game.findMany({
    where: { date, status: { not: 'final' } },
    select: { id: true },
  });

  summary.gamesChecked = games.length;
  const provider = new MlbResultsProvider();

  for (const game of games) {
    try {
      const result = await provider.getResult(game.id);
      if (!result) continue;
      const r = result.data;
      if (r.finalStatus === 'final') {
        const graded = await ingestResultAndGrade(game.id, r.homeScore, r.awayScore);
        summary.settled += 1;
      }
    } catch (error) {
      summary.errors.push({ gameId: game.id, message: errorMessage(error) });
    }
  }

  summary.ok = summary.errors.length === 0;
  return summary;
}
