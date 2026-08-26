import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { DEFAULT_CONFIG } from '@/lib/config/modelConfig';
import { ageHours, mlbScheduleDate } from '@/lib/utils/timezone';

export const dynamic = 'force-dynamic';

type CoverageStatus = 'ok' | 'missing' | 'stale' | 'unconfirmed' | 'fallback' | 'partial' | 'pending';

const FIELD_META = [
  { key: 'schedule', label: 'Schedule', usedBy: 'Pipeline', required: true },
  { key: 'starters', label: 'Probable Starters', usedBy: 'ML + O/U', required: true },
  { key: 'pitching', label: 'ERA / WHIP / IP / GS', usedBy: 'ML + O/U', required: true },
  { key: 'lastFive', label: 'Pitcher Last 5', usedBy: 'ML + O/U', required: true },
  { key: 'offense', label: 'AVG / OPS / RPG / Form', usedBy: 'ML + O/U', required: true },
  { key: 'moneyline', label: 'Moneyline Odds', usedBy: 'ML', required: true },
  { key: 'totals', label: 'Total Line + O/U Odds', usedBy: 'O/U', required: true },
  { key: 'bullpen', label: 'Bullpen ERA / WHIP', usedBy: 'O/U v3', required: true },
  { key: 'park', label: 'Park Factor', usedBy: 'O/U', required: true },
  { key: 'result', label: 'Final Score', usedBy: 'Settlement', required: false },
] as const;

const BLOCKING_STATUSES = new Set<CoverageStatus>(['missing', 'stale', 'unconfirmed']);

function combinedStatus(statuses: CoverageStatus[]): CoverageStatus {
  const priority: CoverageStatus[] = ['missing', 'stale', 'unconfirmed', 'partial', 'fallback', 'pending', 'ok'];
  return priority.find((status) => statuses.includes(status)) ?? 'missing';
}

function snapshotStatus(
  snapshot: { retrievedAt: Date; freshnessState?: string; sourceProvider?: string; provider?: string } | null,
  staleHours: number
): CoverageStatus {
  if (!snapshot) return 'missing';
  if (snapshot.freshnessState === 'stale' || ageHours(snapshot.retrievedAt) > staleHours) return 'stale';
  const provider = snapshot.sourceProvider ?? snapshot.provider ?? '';
  if (provider.includes('minor-league-fallback')) return 'fallback';
  return 'ok';
}

function parseNormalizedData(value: string | undefined): Record<string, any> | null {
  if (!value) return null;
  try {
    return JSON.parse(value) as Record<string, any>;
  } catch {
    return null;
  }
}

export async function GET(req: NextRequest) {
  const requestedDate = req.nextUrl.searchParams.get('date') ?? mlbScheduleDate();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(requestedDate)) {
    return NextResponse.json({ error: 'Invalid date. Expected YYYY-MM-DD.' }, { status: 400 });
  }

  const games = await prisma.game.findMany({
    where: { date: requestedDate },
    orderBy: { startTimeUtc: 'asc' },
    include: {
      homeTeam: true,
      awayTeam: true,
      venue: true,
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 },
      probableStarterObservations: {
        orderBy: { retrievedAt: 'desc' },
        include: { person: true },
      },
      gameResult: true,
    },
  });

  const rows = await Promise.all(games.map(async (game) => {
    const homeStarter = game.probableStarterObservations.find((item) => item.side === 'home') ?? null;
    const awayStarter = game.probableStarterObservations.find((item) => item.side === 'away') ?? null;

    const [
      homePitcher,
      awayPitcher,
      homeTeam,
      awayTeam,
      homeLogs,
      awayLogs,
      park,
      homeBullpenObservation,
      awayBullpenObservation,
    ] = await Promise.all([
      homeStarter ? prisma.pitcherSnapshot.findFirst({
        where: { personId: homeStarter.personId, season: game.season }, orderBy: { retrievedAt: 'desc' },
      }) : null,
      awayStarter ? prisma.pitcherSnapshot.findFirst({
        where: { personId: awayStarter.personId, season: game.season }, orderBy: { retrievedAt: 'desc' },
      }) : null,
      prisma.teamSnapshot.findFirst({
        where: { teamId: game.homeTeamId, season: game.season }, orderBy: { retrievedAt: 'desc' },
      }),
      prisma.teamSnapshot.findFirst({
        where: { teamId: game.awayTeamId, season: game.season }, orderBy: { retrievedAt: 'desc' },
      }),
      homeStarter ? prisma.pitcherGameLogStart.findMany({
        where: { personId: homeStarter.personId, season: game.season },
        orderBy: { gameDate: 'desc' },
        take: 5,
        select: { sourceProvider: true },
      }) : [],
      awayStarter ? prisma.pitcherGameLogStart.findMany({
        where: { personId: awayStarter.personId, season: game.season },
        orderBy: { gameDate: 'desc' },
        take: 5,
        select: { sourceProvider: true },
      }) : [],
      prisma.parkFactorSnapshot.findFirst({
        where: { venueId: game.venueId, season: game.season }, orderBy: { createdAt: 'desc' },
      }),
      prisma.sourceObservation.findFirst({
        where: { providerId: game.homeTeamId, season: game.season, dataType: 'bullpen_stats' },
        orderBy: { retrievedAt: 'desc' },
      }),
      prisma.sourceObservation.findFirst({
        where: { providerId: game.awayTeamId, season: game.season, dataType: 'bullpen_stats' },
        orderBy: { retrievedAt: 'desc' },
      }),
    ]);

    const market = game.marketSnapshots[0] ?? null;
    const homeLogCount = homeLogs.length;
    const awayLogCount = awayLogs.length;
    const logsUseLevelFallback = [...homeLogs, ...awayLogs]
      .some((log) => log.sourceProvider.includes('minor-league-fallback'));
    const homeLogsUseLevelFallback = homeLogs
      .some((log) => log.sourceProvider.includes('minor-league-fallback'));
    const awayLogsUseLevelFallback = awayLogs
      .some((log) => log.sourceProvider.includes('minor-league-fallback'));
    const starterStatus: CoverageStatus = !homeStarter || !awayStarter
      ? 'missing'
      : homeStarter.confirmationStatus !== 'confirmed' || awayStarter.confirmationStatus !== 'confirmed'
      ? 'unconfirmed'
      : 'ok';
    const pitchingStatus = combinedStatus([
      snapshotStatus(homePitcher, DEFAULT_CONFIG.moneyline.teamStatsStaleHours),
      snapshotStatus(awayPitcher, DEFAULT_CONFIG.moneyline.teamStatsStaleHours),
    ]);
    const teamStatus = combinedStatus([
      snapshotStatus(homeTeam, DEFAULT_CONFIG.moneyline.teamStatsStaleHours),
      snapshotStatus(awayTeam, DEFAULT_CONFIG.moneyline.teamStatsStaleHours),
    ]);
    const marketFreshness = snapshotStatus(market, DEFAULT_CONFIG.moneyline.oddsStaleHours);
    const moneylineStatus: CoverageStatus = !market?.moneylineHome || !market?.moneylineAway
      ? 'missing'
      : marketFreshness;
    const totalsStatus: CoverageStatus = market?.totalLine == null
      || market.totalOverDecimal == null
      || market.totalUnderDecimal == null
      ? 'missing'
      : marketFreshness;
    const homeBullpen = parseNormalizedData(homeBullpenObservation?.normalizedData);
    const awayBullpen = parseNormalizedData(awayBullpenObservation?.normalizedData);
    const bullpenStatus: CoverageStatus = homeTeam?.bullpenEra == null
      || homeTeam.bullpenWhip == null
      || awayTeam?.bullpenEra == null
      || awayTeam.bullpenWhip == null
      ? 'missing'
      : combinedStatus([
        snapshotStatus(homeBullpenObservation, DEFAULT_CONFIG.moneyline.bullpenStaleHours),
        snapshotStatus(awayBullpenObservation, DEFAULT_CONFIG.moneyline.bullpenStaleHours),
      ]);
    const resultStatus: CoverageStatus = game.gameResult
      ? 'ok'
      : game.status === 'final'
      ? 'missing'
      : 'pending';
    const parkIsFallback = Boolean(park?.isFallback || park?.source === 'historical-avg');

    const data = {
      schedule: {
        status: 'ok' as CoverageStatus,
        gameStatus: game.status,
        startTimeUtc: game.startTimeUtc,
        venue: game.venue.name,
      },
      starters: {
        status: starterStatus,
        away: awayStarter ? {
          name: awayStarter.person.fullName,
          confirmation: awayStarter.confirmationStatus,
          role: awayStarter.roleLabel,
        } : null,
        home: homeStarter ? {
          name: homeStarter.person.fullName,
          confirmation: homeStarter.confirmationStatus,
          role: homeStarter.roleLabel,
        } : null,
      },
      pitching: {
        status: pitchingStatus,
        away: awayPitcher ? {
          era: awayPitcher.era,
          whip: awayPitcher.whip,
          inningsPitched: awayPitcher.inningsPitched,
          gamesStarted: awayPitcher.gamesStarted,
          provider: awayPitcher.sourceProvider,
        } : null,
        home: homePitcher ? {
          era: homePitcher.era,
          whip: homePitcher.whip,
          inningsPitched: homePitcher.inningsPitched,
          gamesStarted: homePitcher.gamesStarted,
          provider: homePitcher.sourceProvider,
        } : null,
      },
      lastFive: {
        status: homeLogCount === 0 || awayLogCount === 0
          ? 'missing' as CoverageStatus
          : homeLogCount < 5 || awayLogCount < 5
          ? 'partial' as CoverageStatus
          : logsUseLevelFallback
          ? 'fallback' as CoverageStatus
          : 'ok' as CoverageStatus,
        awayCount: Math.min(awayLogCount, 5),
        homeCount: Math.min(homeLogCount, 5),
        awayLevelFallback: awayLogsUseLevelFallback,
        homeLevelFallback: homeLogsUseLevelFallback,
      },
      offense: {
        status: teamStatus,
        away: awayTeam ? {
          avg: awayTeam.avg,
          ops: awayTeam.ops,
          runsPerGame: awayTeam.runsPerGame,
          last10: `${awayTeam.last10Wins}-${awayTeam.last10Losses}`,
          streak: awayTeam.currentStreak,
        } : null,
        home: homeTeam ? {
          avg: homeTeam.avg,
          ops: homeTeam.ops,
          runsPerGame: homeTeam.runsPerGame,
          last10: `${homeTeam.last10Wins}-${homeTeam.last10Losses}`,
          streak: homeTeam.currentStreak,
        } : null,
      },
      moneyline: {
        status: moneylineStatus,
        away: market?.moneylineAway ?? null,
        home: market?.moneylineHome ?? null,
        provider: market?.provider ?? null,
        retrievedAt: market?.retrievedAt ?? null,
      },
      totals: {
        status: totalsStatus,
        line: market?.totalLine ?? null,
        over: market?.totalOverDecimal ?? null,
        under: market?.totalUnderDecimal ?? null,
        provider: market?.provider ?? null,
      },
      bullpen: {
        status: bullpenStatus,
        required: true,
        away: awayTeam ? {
          era: awayTeam.bullpenEra,
          whip: awayTeam.bullpenWhip,
          relievers: awayBullpen?.relievers ?? null,
          inningsPitched: awayBullpen?.inningsPitched ?? null,
          provider: awayBullpenObservation?.provider ?? null,
        } : null,
        home: homeTeam ? {
          era: homeTeam.bullpenEra,
          whip: homeTeam.bullpenWhip,
          relievers: homeBullpen?.relievers ?? null,
          inningsPitched: homeBullpen?.inningsPitched ?? null,
          provider: homeBullpenObservation?.provider ?? null,
        } : null,
      },
      park: {
        status: !park ? 'missing' as CoverageStatus : parkIsFallback ? 'fallback' as CoverageStatus : 'ok' as CoverageStatus,
        factor: park?.factor ?? null,
        source: park?.source ?? null,
        isFallback: park ? parkIsFallback : null,
      },
      result: {
        status: resultStatus,
        awayScore: game.gameResult?.awayScore ?? null,
        homeScore: game.gameResult?.homeScore ?? null,
        finalStatus: game.gameResult?.finalStatus ?? null,
      },
    };

    const blockingIssues = FIELD_META
      .filter((field) => field.required && BLOCKING_STATUSES.has(data[field.key].status))
      .map((field) => ({ label: field.label, status: data[field.key].status }));
    const missingRequired = FIELD_META
      .filter((field) => field.required && data[field.key].status === 'missing')
      .map((field) => field.label);
    const qualityIssues = FIELD_META
      .filter((field) => data[field.key].status === 'fallback' || data[field.key].status === 'partial')
      .map((field) => `${field.label} ${data[field.key].status}`);
    const optionalMissing = FIELD_META
      .filter((field) => !field.required && data[field.key].status === 'missing')
      .map((field) => field.label);

    return {
      gameId: game.id,
      date: game.date,
      startTimeUtc: game.startTimeUtc,
      status: game.status,
      awayTeam: { id: game.awayTeam.id, name: game.awayTeam.name, abbreviation: game.awayTeam.abbreviation },
      homeTeam: { id: game.homeTeam.id, name: game.homeTeam.name, abbreviation: game.homeTeam.abbreviation },
      data,
      blockingIssues,
      missingRequired,
      qualityIssues,
      optionalMissing,
      readyForAnalysis: blockingIssues.length === 0,
    };
  }));

  const fieldCoverage = FIELD_META.map((field) => {
    const statuses = rows.map((row) => row.data[field.key].status);
    return {
      ...field,
      ok: statuses.filter((status) => status === 'ok').length,
      missing: statuses.filter((status) => status === 'missing').length,
      stale: statuses.filter((status) => status === 'stale').length,
      unconfirmed: statuses.filter((status) => status === 'unconfirmed').length,
      fallback: statuses.filter((status) => status === 'fallback').length,
      pending: statuses.filter((status) => status === 'pending').length,
      partial: statuses.filter((status) => status === 'partial').length,
    };
  });

  return NextResponse.json({
    date: requestedDate,
    generatedAt: new Date().toISOString(),
    summary: {
      totalGames: rows.length,
      readyForAnalysis: rows.filter((row) => row.readyForAnalysis).length,
      blockedMatches: rows.filter((row) => !row.readyForAnalysis).length,
      requiredMissingFields: rows.reduce((sum, row) => sum + row.missingRequired.length, 0),
      fallbackFields: rows.reduce((sum, row) => sum + row.qualityIssues.length, 0),
      qualityFields: rows.reduce((sum, row) => sum + row.qualityIssues.length, 0),
      optionalMissingFields: rows.reduce((sum, row) => sum + row.optionalMissing.length, 0),
    },
    fieldCoverage,
    games: rows,
  });
}
