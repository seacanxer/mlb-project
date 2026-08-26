/**
 * lib/engine/pipeline.ts
 *
 * Full analysis pipeline:
 * ingest → freeze InputSnapshot → run ML + O/U engines → apply gates → publish ModelRun
 */

import { prisma } from '@/lib/db';
import { DEFAULT_CONFIG, DEFAULT_OU_TOTALS_CONFIG, type AppModelConfig, type OUTotalsConfig } from '@/lib/config/modelConfig';
import { runMoneylineEngine, selectMoneylineCandidate } from '@/lib/engine/moneyline';
import { runOUTotalsEngine, type OUTotalsInputs, type OUGameLogEntry } from '@/lib/engine/overunderUnified';
import { ageHours, isGameStarted } from '@/lib/utils/timezone';
import type { MoneylineInputs, GameLogEntry } from '@/lib/engine/moneyline';

export interface PipelineResult {
  gameId: string;
  mlRunId: string | null;
  ouRunId: string | null;
  error?: string;
}

/**
 * Analyze one game: build input snapshot, run both engines, persist ModelRuns.
 */
export async function analyzeGame(gameId: string): Promise<PipelineResult> {
  const [mlConfig, ouConfigRecord] = await Promise.all([
    ensureMoneylineModelConfig(),
    ensureOUTotalsModelConfig(),
  ]);

  // --- Load game ---
  const game = await prisma.game.findUnique({
    where: { id: gameId },
    include: { homeTeam: true, awayTeam: true, venue: true },
  });
  if (!game) return { gameId, mlRunId: null, ouRunId: null, error: 'Game not found' };

  if (!mlConfig || !ouConfigRecord) {
    return { gameId, mlRunId: null, ouRunId: null, error: 'No active model config found' };
  }
  const config = parseAppConfig(mlConfig.configJson);
  const ouConfig = parseOUTotalsConfig(ouConfigRecord.configJson);

  // --- Load latest snapshots ---
  const homeSnap = await prisma.pitcherSnapshot.findFirst({
    where: { personId: { in: await getStarterIds(gameId, 'home') }, season: game.season },
    orderBy: { retrievedAt: 'desc' },
  });
  const awaySnap = await prisma.pitcherSnapshot.findFirst({
    where: { personId: { in: await getStarterIds(gameId, 'away') }, season: game.season },
    orderBy: { retrievedAt: 'desc' },
  });
  const homeTeamSnap = await prisma.teamSnapshot.findFirst({
    where: { teamId: game.homeTeamId, season: game.season },
    orderBy: { retrievedAt: 'desc' },
  });
  const awayTeamSnap = await prisma.teamSnapshot.findFirst({
    where: { teamId: game.awayTeamId, season: game.season },
    orderBy: { retrievedAt: 'desc' },
  });
  const market = await prisma.marketSnapshot.findFirst({
    where: { gameId },
    orderBy: { retrievedAt: 'desc' },
  });
  const openingMarket = await prisma.marketSnapshot.findFirst({
    where: { gameId, totalLine: { not: null } },
    orderBy: { retrievedAt: 'asc' },
  });
  const parkFactor = await prisma.parkFactorSnapshot.findFirst({
    where: { venueId: game.venueId, season: game.season },
    orderBy: { createdAt: 'desc' },
  });
  const homeStarter = await prisma.probableStarterObservation.findFirst({
    where: { gameId, side: 'home' },
    orderBy: { retrievedAt: 'desc' },
  });
  const awayStarter = await prisma.probableStarterObservation.findFirst({
    where: { gameId, side: 'away' },
    orderBy: { retrievedAt: 'desc' },
  });

  // --- Load game logs ---
  const homeLogIds = homeStarter ? await getRecentGameLogIds(homeStarter.personId, game.season) : [];
  const awayLogIds = awayStarter ? await getRecentGameLogIds(awayStarter.personId, game.season) : [];
  const homeLogRecords = await prisma.pitcherGameLogStart.findMany({
    where: { id: { in: homeLogIds } },
    orderBy: { gameDate: 'asc' },
  });
  const awayLogRecords = await prisma.pitcherGameLogStart.findMany({
    where: { id: { in: awayLogIds } },
    orderBy: { gameDate: 'asc' },
  });

  // --- Freeze InputSnapshot ---
  const inputSnapshot = await prisma.inputSnapshot.create({
    data: {
      gameId,
      pitcherSnapshotHomeId: homeSnap?.id,
      pitcherSnapshotAwayId: awaySnap?.id,
      teamSnapshotHomeId: homeTeamSnap?.id,
      teamSnapshotAwayId: awayTeamSnap?.id,
      marketSnapshotId: market?.id,
      parkFactorSnapshotId: parkFactor?.id,
      gameLogStartsHome: JSON.stringify(homeLogIds),
      gameLogStartsAway: JSON.stringify(awayLogIds),
      probableStarterHomeId: homeStarter?.id,
      probableStarterAwayId: awayStarter?.id,
    },
  });

  // --- Freshness checks ---
  const oddsStale = !market || ageHours(market.retrievedAt) > config.moneyline.oddsStaleHours;
  const ouOddsStale = !market || ageHours(market.retrievedAt) > ouConfig.oddsStaleHours;
  const homeTeamStale = !homeTeamSnap || ageHours(homeTeamSnap.retrievedAt) > config.moneyline.teamStatsStaleHours;
  const awayTeamStale = !awayTeamSnap || ageHours(awayTeamSnap.retrievedAt) > config.moneyline.teamStatsStaleHours;
  const gameStarted = isGameStarted(game.startTimeUtc);
  const leagueRpg = await getLeagueRpgBaseline(game.season);
  const homePitcherLevelFallback = Boolean(
    homeSnap?.sourceProvider.includes('minor-league-fallback')
    || homeLogRecords.some((log) => log.sourceProvider.includes('minor-league-fallback'))
  );
  const awayPitcherLevelFallback = Boolean(
    awaySnap?.sourceProvider.includes('minor-league-fallback')
    || awayLogRecords.some((log) => log.sourceProvider.includes('minor-league-fallback'))
  );

  // --- Build ML inputs for both sides, then select the stronger candidate ---
  const homeGameLogs: GameLogEntry[] = homeLogRecords.map((l) => ({
    earnedRuns: l.earnedRuns,
    outsRecorded: l.outsRecorded,
    gameDate: l.gameDate,
  }));
  const awayGameLogs: GameLogEntry[] = awayLogRecords.map((l) => ({
    earnedRuns: l.earnedRuns,
    outsRecorded: l.outsRecorded,
    gameDate: l.gameDate,
  }));

  const homeMLInputs: MoneylineInputs = {
    candidateStarterEra: homeSnap?.era ?? 99,
    opponentStarterEra: awaySnap?.era ?? 0,
    candidateStarterOutsRecorded: homeSnap?.outsRecorded ?? 0,
    candidateStarterGamesStarted: homeStarter?.gamesStarted ?? 0,
    candidateStarterRole: homeStarter?.roleLabel ?? undefined,
    candidateStarterConfirmed: homeStarter?.confirmationStatus === 'confirmed',
    opponentStarterConfirmed: awayStarter?.confirmationStatus === 'confirmed',
    candidateStarterName: homeSnap?.personId ?? 'Unknown',
    candidatePitcherLevelFallback: homePitcherLevelFallback,
    opponentPitcherLevelFallback: awayPitcherLevelFallback,
    candidateAvg: homeTeamSnap?.avg ?? 0,
    candidateOps: homeTeamSnap?.ops ?? 0,
    candidateGameLogs: homeGameLogs,
    candidateDecimalOdds: market?.moneylineHome ?? null,
    last10Wins: homeTeamSnap?.last10Wins ?? 0,
    last10Losses: homeTeamSnap?.last10Losses ?? 0,
    winStreak: Math.max(homeTeamSnap?.currentStreak ?? 0, 0),
    lossStreak: Math.abs(Math.min(homeTeamSnap?.currentStreak ?? 0, 0)),
    gameAlreadyStarted: gameStarted,
    oddsAreStale: oddsStale,
    oddsProviderConfigured: !!(process.env.ODDS_PROVIDER),
  };

  const homeMLResult = runMoneylineEngine(homeMLInputs, config.moneyline);
  const awayMLInputs: MoneylineInputs = {
    candidateStarterEra: awaySnap?.era ?? 99,
    opponentStarterEra: homeSnap?.era ?? 0,
    candidateStarterOutsRecorded: awaySnap?.outsRecorded ?? 0,
    candidateStarterGamesStarted: awayStarter?.gamesStarted ?? 0,
    candidateStarterRole: awayStarter?.roleLabel ?? undefined,
    candidateStarterConfirmed: awayStarter?.confirmationStatus === 'confirmed',
    opponentStarterConfirmed: homeStarter?.confirmationStatus === 'confirmed',
    candidateStarterName: awaySnap?.personId ?? 'Unknown',
    candidatePitcherLevelFallback: awayPitcherLevelFallback,
    opponentPitcherLevelFallback: homePitcherLevelFallback,
    candidateAvg: awayTeamSnap?.avg ?? 0,
    candidateOps: awayTeamSnap?.ops ?? 0,
    candidateGameLogs: awayGameLogs,
    candidateDecimalOdds: market?.moneylineAway ?? null,
    last10Wins: awayTeamSnap?.last10Wins ?? 0,
    last10Losses: awayTeamSnap?.last10Losses ?? 0,
    winStreak: Math.max(awayTeamSnap?.currentStreak ?? 0, 0),
    lossStreak: Math.abs(Math.min(awayTeamSnap?.currentStreak ?? 0, 0)),
    gameAlreadyStarted: gameStarted,
    oddsAreStale: oddsStale,
    oddsProviderConfigured: !!(process.env.ODDS_PROVIDER),
  };
  const awayMLResult = runMoneylineEngine(awayMLInputs, config.moneyline);
  const selectedML = selectMoneylineCandidate(homeMLResult, awayMLResult);
  const selectedMLResult = selectedML.result;
  const selectedTeam = selectedML.side === 'home' ? game.homeTeam : game.awayTeam;
  const selectedOdds = selectedML.side === 'home' ? market?.moneylineHome : market?.moneylineAway;

  // --- O/U inputs ---
  const homeOULogs: OUGameLogEntry[] = homeLogRecords.map((l) => ({
    earnedRuns: l.earnedRuns,
    outsRecorded: l.outsRecorded,
  }));
  const awayOULogs: OUGameLogEntry[] = awayLogRecords.map((l) => ({
    earnedRuns: l.earnedRuns,
    outsRecorded: l.outsRecorded,
  }));

  const ouInputs: OUTotalsInputs = {
    marketLine: market?.totalLine ?? null,
    openingTotalLine: openingMarket?.totalLine ?? null,
    overDecimal: market?.totalOverDecimal ?? null,
    underDecimal: market?.totalUnderDecimal ?? null,
    leagueRpg,
    awayRpg: awayTeamStale ? null : (awayTeamSnap?.runsPerGame ?? null),
    homeRpg: homeTeamStale ? null : (homeTeamSnap?.runsPerGame ?? null),
    awaySeasonEra: awaySnap?.era ?? null,
    homeSeasonEra: homeSnap?.era ?? null,
    awayStarterWhip: awaySnap?.whip ?? null,
    homeStarterWhip: homeSnap?.whip ?? null,
    awayStarterOuts: awaySnap?.outsRecorded ?? null,
    homeStarterOuts: homeSnap?.outsRecorded ?? null,
    awayStarterGamesStarted: awaySnap?.gamesStarted ?? awayStarter?.gamesStarted ?? null,
    homeStarterGamesStarted: homeSnap?.gamesStarted ?? homeStarter?.gamesStarted ?? null,
    awayLastFiveLogs: awayOULogs,
    homeLastFiveLogs: homeOULogs,
    awayPitcherLevelFallback,
    homePitcherLevelFallback,
    awayBullpenEra: awayTeamSnap?.bullpenEra ?? null,
    homeBullpenEra: homeTeamSnap?.bullpenEra ?? null,
    awayBullpenWhip: awayTeamSnap?.bullpenWhip ?? null,
    homeBullpenWhip: homeTeamSnap?.bullpenWhip ?? null,
    bullpenSourceLimited: [awayTeamSnap?.sourceProvider, homeTeamSnap?.sourceProvider]
      .some((source) => !source || source.includes('mlb') || source.includes('scraper')),
    homeParkFactor: parkFactor?.factor ?? null,
    parkFactorIsFallback: Boolean(parkFactor?.isFallback || parkFactor?.source === 'historical-avg'),
    awayStarterConfirmed: awayStarter?.confirmationStatus === 'confirmed',
    homeStarterConfirmed: homeStarter?.confirmationStatus === 'confirmed',
    oddsAreStale: ouOddsStale,
    teamDataAreStale: homeTeamStale || awayTeamStale,
    bullpenDataAreStale: homeTeamStale || awayTeamStale,
    parkFactorWrongSeason: parkFactor ? parkFactor.season !== game.season : false,
    gameAlreadyStarted: gameStarted,
  };
  const ouResult = runOUTotalsEngine(ouInputs, ouConfig);

  // --- Persist ML ModelRun ---
  const mlRun = await prisma.modelRun.create({
    data: {
      gameId,
      modelId: 'ML_COMBO_V2',
      configVersionId: mlConfig.id,
      inputSnapshotId: inputSnapshot.id,
      finalState: selectedMLResult.finalState,
      rawScore: selectedMLResult.rawScore,
      outputJson: JSON.stringify({
        ...selectedMLResult,
        candidate: selectedML.side,
        candidateTeamId: selectedTeam.id,
        candidateTeamName: selectedTeam.name,
        candidateDecimalOdds: selectedOdds ?? null,
        evaluatedCandidates: {
          home: {
            rawScore: homeMLResult.rawScore,
            finalState: homeMLResult.finalState,
            eraGap: homeMLResult.eraGap,
            hardGates: homeMLResult.hardGates,
          },
          away: {
            rawScore: awayMLResult.rawScore,
            finalState: awayMLResult.finalState,
            eraGap: awayMLResult.eraGap,
            hardGates: awayMLResult.hardGates,
          },
        },
      }),
    },
  });

  // Attach warnings
  for (const w of selectedMLResult.warnings) {
    await prisma.modelWarning.create({
      data: { modelRunId: mlRun.id, code: w, severity: 'warning', message: w },
    });
  }
  for (const g of selectedMLResult.hardGates) {
    await prisma.modelWarning.create({
      data: { modelRunId: mlRun.id, code: g, severity: 'warning', message: `Hard gate: ${g}` },
    });
  }

  // --- Persist the single authoritative O/U ModelRun ---
  const ouRun = await prisma.modelRun.create({
    data: {
      gameId,
      modelId: 'OU_UNIFIED',
      configVersionId: ouConfigRecord.id,
      inputSnapshotId: inputSnapshot.id,
      finalState: ouResult.finalState,
      rawGap: ouResult.gap ?? undefined,
      outputJson: JSON.stringify(ouResult),
    },
  });

  for (const w of ouResult.warnings) {
    await prisma.modelWarning.create({
      data: { modelRunId: ouRun.id, code: w, severity: 'warning', message: w },
    });
  }
  for (const g of ouResult.hardGates) {
    await prisma.modelWarning.create({
      data: { modelRunId: ouRun.id, code: g, severity: 'warning', message: `Hard gate: ${g}` },
    });
  }

  return { gameId, mlRunId: mlRun.id, ouRunId: ouRun.id };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let moneylineConfigPromise: ReturnType<typeof ensureMoneylineModelConfigOnce> | null = null;

function ensureMoneylineModelConfig() {
  if (!moneylineConfigPromise) {
    moneylineConfigPromise = ensureMoneylineModelConfigOnce().catch((error) => {
      moneylineConfigPromise = null;
      throw error;
    });
  }
  return moneylineConfigPromise;
}

async function ensureMoneylineModelConfigOnce() {
  await prisma.modelDefinition.upsert({
    where: { id: 'ML_COMBO_V2' },
    create: {
      id: 'ML_COMBO_V2',
      name: 'Moneyline Combo Score',
      version: '2.1',
      description: 'Moneyline Combo Score v2.1 — deterministic scoring with explicit confidence caps.',
      isActive: true,
    },
    update: {
      version: '2.1',
      description: 'Moneyline Combo Score v2.1 — deterministic scoring with explicit confidence caps.',
    },
  });
  const existing = await prisma.modelConfigVersion.findFirst({
    where: { modelId: 'ML_COMBO_V2', semver: DEFAULT_CONFIG.version },
    orderBy: { createdAt: 'desc' },
  });
  if (existing?.isActive) return existing;

  return prisma.$transaction(async (tx) => {
    await tx.modelConfigVersion.updateMany({
      where: { modelId: 'ML_COMBO_V2', isActive: true },
      data: { isActive: false },
    });
    if (existing) {
      return tx.modelConfigVersion.update({
        where: { id: existing.id },
        data: { isActive: true },
      });
    }
    return tx.modelConfigVersion.create({
      data: {
        modelId: 'ML_COMBO_V2',
        semver: DEFAULT_CONFIG.version,
        configJson: JSON.stringify(DEFAULT_CONFIG),
        isActive: true,
        createdBy: 'pipeline-bootstrap',
      },
    });
  });
}

async function getStarterIds(gameId: string, side: 'home' | 'away'): Promise<string[]> {
  const obs = await prisma.probableStarterObservation.findMany({
    where: { gameId, side },
    select: { personId: true },
  });
  return obs.map((o) => o.personId);
}

async function getRecentGameLogIds(personId: string, season: number): Promise<string[]> {
  const logs = await prisma.pitcherGameLogStart.findMany({
    where: { personId, season },
    orderBy: { gameDate: 'desc' },
    take: 5,
    select: { id: true },
  });
  return logs.map((l) => l.id);
}

let ouTotalsConfigPromise: ReturnType<typeof ensureOUTotalsModelConfigOnce> | null = null;

function ensureOUTotalsModelConfig() {
  if (!ouTotalsConfigPromise) {
    ouTotalsConfigPromise = ensureOUTotalsModelConfigOnce().catch((error) => {
      ouTotalsConfigPromise = null;
      throw error;
    });
  }
  return ouTotalsConfigPromise;
}

async function ensureOUTotalsModelConfigOnce() {
  await prisma.modelDefinition.upsert({
    where: { id: 'OU_UNIFIED' },
    create: {
      id: 'OU_UNIFIED',
      name: 'Unified MLB Totals',
      version: '4.0',
      description: 'Single market-anchored offense and pitching totals model. Experimental and not calibrated.',
      isActive: true,
    },
    update: { version: '4.0', isActive: true },
  });
  await prisma.modelDefinition.updateMany({
    where: { id: { in: ['OU_V2_3', 'OU_V3'] } },
    data: { isActive: false },
  });
  await prisma.modelConfigVersion.updateMany({
    where: { modelId: { in: ['OU_V2_3', 'OU_V3'] }, isActive: true },
    data: { isActive: false },
  });
  const existing = await prisma.modelConfigVersion.findFirst({
    where: { modelId: 'OU_UNIFIED', semver: DEFAULT_OU_TOTALS_CONFIG.version },
    orderBy: { createdAt: 'desc' },
  });
  if (existing) {
    if (!existing.isActive) {
      return prisma.modelConfigVersion.update({ where: { id: existing.id }, data: { isActive: true } });
    }
    return existing;
  }
  return prisma.modelConfigVersion.create({
    data: {
      modelId: 'OU_UNIFIED',
      semver: DEFAULT_OU_TOTALS_CONFIG.version,
      configJson: JSON.stringify(DEFAULT_OU_TOTALS_CONFIG),
      isActive: true,
      createdBy: 'pipeline-bootstrap',
    },
  });
}

function parseAppConfig(configJson: string): AppModelConfig {
  try {
    const parsed = JSON.parse(configJson) as Partial<AppModelConfig>;
    return {
      ...DEFAULT_CONFIG,
      ...parsed,
      moneyline: { ...DEFAULT_CONFIG.moneyline, ...(parsed.moneyline ?? {}) },
      ou: { ...DEFAULT_CONFIG.ou, ...(parsed.ou ?? {}) },
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}

function parseOUTotalsConfig(configJson: string): OUTotalsConfig {
  try {
    return { ...DEFAULT_OU_TOTALS_CONFIG, ...(JSON.parse(configJson) as Partial<OUTotalsConfig>) };
  } catch {
    return DEFAULT_OU_TOTALS_CONFIG;
  }
}

async function getLeagueRpgBaseline(season: number): Promise<number | null> {
  const snapshots = await prisma.teamSnapshot.findMany({
    where: { season },
    orderBy: { retrievedAt: 'desc' },
    select: { teamId: true, runsPerGame: true },
  });
  const latestByTeam = new Map<string, number>();
  for (const snapshot of snapshots) {
    if (!latestByTeam.has(snapshot.teamId)) latestByTeam.set(snapshot.teamId, snapshot.runsPerGame);
  }
  if (latestByTeam.size < 20) return null;
  const values = [...latestByTeam.values()];
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}
