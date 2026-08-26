/**
 * lib/engine/forecast.ts
 *
 * Forecast locking and grading.
 * - Lock is only allowed before first pitch.
 * - A locked forecast is immutable; later data creates a revision.
 * - Grading produces a Settlement with win/loss/push outcome.
 */

import { prisma } from '@/lib/db';
import { isGameStarted } from '@/lib/utils/timezone';

export class ForecastError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ForecastError';
  }
}

/**
 * Lock a model run as a forecast.
 * Throws ForecastError if the game has already started or run is already locked.
 */
export async function lockForecast(
  modelRunId: string,
  opts: { selectedSide?: string; notes?: string } = {}
): Promise<string> {
  const run = await prisma.modelRun.findUnique({
    where: { id: modelRunId },
    include: { game: true, forecasts: true },
  });
  if (!run) throw new ForecastError('Model run not found');
  if (run.isLocked) throw new ForecastError('This model run is already locked');
  if (run.isInvalidated) throw new ForecastError('Cannot lock an invalidated model run');
  const actionableStates = new Set([
    'T1', 'T2',
    'OVER_RISKY', 'OVER_STRONG_GAP',
    'UNDER_RISKY', 'UNDER_STRONG_GAP',
  ]);
  if (!actionableStates.has(run.finalState)) {
    throw new ForecastError('Only actionable T1/T2 or O/U RISKY/STRONG signals can be locked');
  }

  // Pre-first-pitch gate
  if (isGameStarted(run.game.startTimeUtc)) {
    throw new ForecastError('Cannot lock a forecast after first pitch');
  }

  // Get market snapshot at lock time
  const market = await prisma.marketSnapshot.findFirst({
    where: { gameId: run.gameId },
    orderBy: { retrievedAt: 'desc' },
  });

  // Mark run as locked
  await prisma.modelRun.update({
    where: { id: modelRunId },
    data: { isLocked: true },
  });

  // Create Forecast record
  const forecast = await prisma.forecast.create({
    data: {
      modelRunId,
      lockedAt: new Date(),
      marketLine: market?.totalLine ?? null,
      marketPrice: opts.selectedSide === 'over'
        ? (market?.totalOverDecimal ?? null)
        : opts.selectedSide === 'under'
        ? (market?.totalUnderDecimal ?? null)
        : opts.selectedSide === 'away'
        ? (market?.moneylineAway ?? null)
        : (market?.moneylineHome ?? null),
      selectedSide: opts.selectedSide ?? null,
      finalState: run.finalState,
      notes: opts.notes ?? null,
    },
  });

  return forecast.id;
}

/**
 * Grade a forecast against official result.
 * Moneyline: win if candidate team won; push impossible on ML.
 * Totals: win/loss/push based on total vs market line.
 */
export async function gradeForecast(
  forecastId: string,
  gameResultId: string
): Promise<string> {
  const forecast = await prisma.forecast.findUnique({
    where: { id: forecastId },
    include: { modelRun: { include: { game: true } } },
  });
  if (!forecast) throw new ForecastError('Forecast not found');

  const result = await prisma.gameResult.findUnique({ where: { id: gameResultId } });
  if (!result) throw new ForecastError('Game result not found');

  const outputJson = JSON.parse(forecast.modelRun.outputJson as string) as Record<string, unknown>;
  const isOuModel = forecast.modelRun.finalState.startsWith('OVER') ||
    forecast.modelRun.finalState.startsWith('UNDER') ||
    forecast.modelRun.finalState === 'NO_BET';

  let outcome: 'win' | 'loss' | 'push' | 'void' | 'pending' = 'pending';

  if (isOuModel) {
    const line = forecast.marketLine;
    if (line !== null) {
      const totalRuns = result.homeScore + result.awayScore;
      const side = forecast.selectedSide;
      if (totalRuns === line) {
        outcome = 'push'; // integer total push
      } else if (side === 'over') {
        outcome = totalRuns > line ? 'win' : 'loss';
      } else if (side === 'under') {
        outcome = totalRuns < line ? 'win' : 'loss';
      }
    }
  } else {
    // Moneyline: determine candidate side from outputJson
    const candidate = (outputJson.candidate as string) ?? 'home';
    const homeWon = result.homeScore > result.awayScore;
    outcome = (candidate === 'home' && homeWon) || (candidate === 'away' && !homeWon) ? 'win' : 'loss';
  }

  const settlement = await prisma.settlement.create({
    data: {
      forecastId,
      gameResultId,
      outcome,
      gradeNotes: `${result.homeScore}-${result.awayScore} (${forecast.modelRun.game.homeTeamId} vs ${forecast.modelRun.game.awayTeamId})`,
    },
  });

  return settlement.id;
}

/**
 * Ingest official game result and auto-grade all pending forecasts for this game.
 */
export async function ingestResultAndGrade(
  gameId: string,
  homeScore: number,
  awayScore: number
): Promise<{ gameResultId: string; settledCount: number }> {
  const existing = await prisma.gameResult.findUnique({ where: { gameId } });
  const gameResult = existing ?? await prisma.gameResult.create({
    data: {
      gameId,
      homeScore,
      awayScore,
      finalStatus: 'final',
      officialAt: new Date(),
      sourceProvider: 'mlb-stats-api',
      retrievedAt: new Date(),
    },
  });

  // Update game status
  await prisma.game.update({ where: { id: gameId }, data: { status: 'final' } });

  // Grade all locked, unsettled forecasts for this game
  const pendingForecasts = await prisma.forecast.findMany({
    where: {
      modelRun: { gameId },
      settlement: null,
    },
    include: { modelRun: true },
  });

  let settledCount = 0;
  for (const fc of pendingForecasts) {
    await gradeForecast(fc.id, gameResult.id);
    settledCount++;
  }

  return { gameResultId: gameResult.id, settledCount };
}
