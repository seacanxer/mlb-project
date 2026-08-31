/**
 * lib/engine/forecast.ts
 *
 * Forecast locking and grading.
 * - Lock is only allowed before first pitch.
 * - A locked forecast is immutable; later data creates a revision.
 * - Grading produces a Settlement with win/loss/push outcome.
 */

import { prisma } from '@/lib/db';
import { isGameStarted, mlbScheduleDate } from '@/lib/utils/timezone';

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

  const existingGameModelForecast = await prisma.forecast.findFirst({
    where: {
      modelRun: { gameId: run.gameId, modelId: run.modelId },
    },
    orderBy: { lockedAt: 'asc' },
  });
  if (existingGameModelForecast) {
    throw new ForecastError(`A ${run.modelId} pick is already locked for this game`);
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

  const output = JSON.parse(run.outputJson as string) as Record<string, unknown>;
  const expectedSide = run.modelId.startsWith('OU_')
    ? String(output.selectedSide ?? (run.finalState.startsWith('UNDER') ? 'under' : 'over'))
    : String(output.candidate === 'away' ? 'away' : 'home');
  if (opts.selectedSide && opts.selectedSide !== expectedSide) {
    throw new ForecastError(`Selected side does not match the published pick (${expectedSide})`);
  }
  const selectedSide = expectedSide;

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
      marketPrice: selectedSide === 'over'
        ? (market?.totalOverDecimal ?? null)
        : selectedSide === 'under'
        ? (market?.totalUnderDecimal ?? null)
        : selectedSide === 'away'
        ? (market?.moneylineAway ?? null)
        : (market?.moneylineHome ?? null),
      selectedSide,
      finalState: run.finalState,
      notes: opts.notes ?? null,
    },
  });

  return forecast.id;
}

export interface AutoLockSummary {
  date: string;
  eligible: number;
  locked: number;
  alreadyLocked: number;
  errors: Array<{ runId: string; message: string }>;
}

/** Lock the latest published ML and unified O/U actionable pick per game. */
export async function autoLockActionableForecasts(date: string): Promise<AutoLockSummary> {
  const summary: AutoLockSummary = {
    date,
    eligible: 0,
    locked: 0,
    alreadyLocked: 0,
    errors: [],
  };
  const games = await prisma.game.findMany({
    where: { date },
    include: {
      modelRuns: {
        where: {
          isInvalidated: false,
          modelId: { in: ['ML_COMBO_V2', 'OU_UNIFIED'] },
        },
        orderBy: { runAt: 'desc' },
        include: { forecasts: true },
      },
    },
  });

  const actionable = new Set([
    'T1', 'T2',
    'OVER_RISKY', 'OVER_STRONG_GAP',
    'UNDER_RISKY', 'UNDER_STRONG_GAP',
  ]);

  for (const game of games) {
    for (const modelId of ['ML_COMBO_V2', 'OU_UNIFIED']) {
      const run = game.modelRuns.find((candidate) => candidate.modelId === modelId);
      if (!run || !actionable.has(run.finalState)) continue;
      summary.eligible += 1;

      const existing = await prisma.forecast.findFirst({
        where: { modelRun: { gameId: game.id, modelId } },
        select: { id: true },
      });
      if (existing) {
        summary.alreadyLocked += 1;
        continue;
      }

      try {
        await lockForecast(run.id, { notes: 'Locked from slate action' });
        summary.locked += 1;
      } catch (error) {
        summary.errors.push({
          runId: run.id,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  return summary;
}

export interface AutoLockUpcomingResult {
  state: 'no_upcoming' | 'too_early' | 'locking';
  firstStartUtc?: string;
  lockAtUtc?: string;
  minutesLeft?: number;
  dates?: Array<{ date: string; eligible: number; locked: number; alreadyLocked: number; errors: string[] }>;
}

/**
 * Auto-lock every actionable pick once we are within `leadMinutes` of the
 * earliest (first) pitch of an upcoming slate. Runs repeatedly from the
 * worker; dedupe inside autoLockActionableForecasts makes it idempotent.
 */
export async function autoLockUpcoming(leadMinutes = 60): Promise<AutoLockUpcomingResult> {
  const now = new Date();

  // All games that haven't started yet (any upcoming slate)
  const games = await prisma.game.findMany({
    where: {
      startTimeUtc: { gt: now },
      status: { notIn: ['final', 'postponed', 'cancelled'] },
    },
    orderBy: { startTimeUtc: 'asc' as const },
    select: { id: true, startTimeUtc: true, date: true },
  });

  if (games.length === 0) {
    return { state: 'no_upcoming' };
  }

  const firstStart = games[0].startTimeUtc;
  const lockAt = new Date(firstStart.getTime() - leadMinutes * 60_000);
  if (now < lockAt) {
    return {
      state: 'too_early',
      firstStartUtc: firstStart.toISOString(),
      lockAtUtc: lockAt.toISOString(),
      minutesLeft: Math.max(0, Math.floor((lockAt.getTime() - now.getTime()) / 60_000)),
    };
  }

  // In the lock window: group upcoming games by MLB (ET) slate date and lock
  // each slate whose earliest pitch is within the lead window.
  const byDate = new Map<string, Date>();
  for (const game of games) {
    const slateDate = mlbScheduleDate(game.startTimeUtc);
    const current = byDate.get(slateDate);
    if (!current || game.startTimeUtc < current) byDate.set(slateDate, game.startTimeUtc);
  }

  const dates: AutoLockUpcomingResult['dates'] = [];
  for (const [date, earliestStart] of byDate) {
    const slateWindowStart = new Date(earliestStart.getTime() - leadMinutes * 60_000);
    if (now < slateWindowStart) continue;
    const summary = await autoLockActionableForecasts(date);
    dates.push({
      date,
      eligible: summary.eligible,
      locked: summary.locked,
      alreadyLocked: summary.alreadyLocked,
      errors: summary.errors.map((e) => e.message),
    });
  }

  return {
    state: 'locking',
    firstStartUtc: firstStart.toISOString(),
    lockAtUtc: lockAt.toISOString(),
    dates,
  };
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
