/**
 * lib/engine/moneyline.ts
 *
 * Moneyline Combo Score v2.0
 *
 * Design rules:
 * - ERA gap <= 0 → SKIP immediately (before scoring)
 * - Score is always calculated and preserved even when a hard gate fires
 * - Warnings are attached separately, never replacing final state
 */

import { computeEra } from '@/lib/utils/innings';
import {
  getEraGapPoints,
  getOffenseTier,
  getFairDecimal,
} from '@/lib/config/modelConfig';
import type { MoneylineConfig } from '@/lib/config/modelConfig';
import type { FinalState, WarningCode, PitcherTrend, HardGateCode } from './types';
import { twoWayNoVigProbabilities } from '@/lib/utils/odds';

// ---------------------------------------------------------------------------
// Input / output types
// ---------------------------------------------------------------------------

export interface GameLogEntry {
  earnedRuns: number;
  outsRecorded: number;
  gameDate: string; // for ordering
}

export interface MoneylineInputs {
  // Starters
  candidateStarterEra: number;
  opponentStarterEra: number;
  candidateStarterOutsRecorded: number; // season total
  candidateStarterGamesStarted: number;
  candidateStarterRole?: string; // 'starter' | 'reliever' | 'opener'
  candidateStarterConfirmed: boolean;
  opponentStarterConfirmed?: boolean;
  candidateStarterName: string;
  candidatePitcherLevelFallback?: boolean;
  opponentPitcherLevelFallback?: boolean;

  // Offense
  candidateAvg: number;
  candidateOps: number;

  // Last-five game logs (chronological, oldest first)
  candidateGameLogs: GameLogEntry[];

  // Market
  candidateDecimalOdds: number | null;
  opponentDecimalOdds?: number | null;
  eraGap?: number; // pre-computed if available

  // Team form
  last10Wins: number;
  last10Losses: number;
  winStreak: number;   // positive = win streak
  lossStreak: number;  // consecutive losses (0 if winning)

  // Context
  gameAlreadyStarted: boolean;
  oddsAreStale: boolean;
  oddsProviderConfigured: boolean;
}

export interface MoneylineResult {
  // Score components
  eraGap: number;
  eraGapPoints: number;
  offensePoints: number;
  offenseAvgLabel: string;
  offenseOpsLabel: string;
  offenseMismatch: boolean;
  gameLogGoodStarts: number;
  gameLogPoints: number;
  trend: PitcherTrend;
  marketAlignmentPoints: number;
  fairDecimal: number | null;
  marketNoVigProbability: number | null;
  marketOverround: number | null;
  confidenceType: 'heuristic-score';
  teamFormPoints: number;

  // Totals
  rawScore: number;
  finalState: FinalState;
  hardGates: HardGateCode[];
  warnings: WarningCode[];
}

export type MoneylineCandidateSide = 'home' | 'away';

/**
 * Pick the stronger candidate after both sides have been evaluated.
 * Actionable tiers win first; for two SKIPs, preserve the side with the
 * positive ERA advantage so the audit trail reflects the intended candidate.
 */
export function selectMoneylineCandidate(
  home: MoneylineResult,
  away: MoneylineResult
): { side: MoneylineCandidateSide; result: MoneylineResult } {
  const stateRank: Record<MoneylineResult['finalState'], number> = {
    T1: 3,
    T2: 2,
    SKIP: 1,
    NEEDS_DATA: 0,
    INVALIDATED: 0,
    NO_BET: 0,
    OVER_LEAN: 0,
    OVER_RISKY: 0,
    OVER_STRONG_GAP: 0,
    UNDER_LEAN: 0,
    UNDER_RISKY: 0,
    UNDER_STRONG_GAP: 0,
  };
  const candidates = [
    { side: 'home' as const, result: home },
    { side: 'away' as const, result: away },
  ];

  candidates.sort((left, right) =>
    stateRank[right.result.finalState] - stateRank[left.result.finalState]
    || Number(right.result.eraGap > 0) - Number(left.result.eraGap > 0)
    || right.result.rawScore - left.result.rawScore
  );
  return candidates[0];
}

// ---------------------------------------------------------------------------
// Sub-calculations (exported for unit testing)
// ---------------------------------------------------------------------------

export function calcEraGap(candidateEra: number, opponentEra: number): number {
  return opponentEra - candidateEra;
}

export function calcGameLogPoints(
  logs: GameLogEntry[],
  config: MoneylineConfig
): { goodStarts: number; points: number; trend: PitcherTrend } {
  if (logs.length < config.minGoodStartsRequired) {
    return { goodStarts: 0, points: 0, trend: 'MIXED' };
  }

  const last5 = logs.slice(-5);
  const eras = last5.map((l) => computeEra(l.earnedRuns, l.outsRecorded));
  const goodStarts = eras.filter((e) => e < 4.0).length;

  const pointsTable: Record<number, number> = { 5: 20, 4: 16, 3: 12, 2: 8, 1: 4, 0: 0 };
  const points = pointsTable[goodStarts] ?? 0;

  // Trend from last 3 starts (display only)
  const last3 = eras.slice(-3);
  let trend: PitcherTrend = 'MIXED';
  if (last3.length === 3) {
    if (last3[0] > last3[1] && last3[1] > last3[2]) trend = 'HOT';   // ERA decreasing
    else if (last3[0] < last3[1] && last3[1] < last3[2]) trend = 'COLD'; // ERA increasing
  }

  return { goodStarts, points, trend };
}

export function calcTeamFormPoints(
  last10Wins: number,
  winStreak: number,
  lossStreak: number
): number {
  if (last10Wins >= 8 && winStreak >= 3) return 10;
  if (last10Wins >= 6 && winStreak >= 1) return 8;
  if (last10Wins >= 5) return 6;
  if (last10Wins >= 4 && lossStreak <= 2) return 4;
  return 2;
}

export function calcMarketAlignmentPoints(
  eraGap: number,
  candidateDecimal: number,
  config: MoneylineConfig
): { points: number; fairDecimal: number | null; hardGateMarket: boolean } {
  const fairDecimal = getFairDecimal(eraGap, config);

  if (fairDecimal === null) {
    // ERA gap < 1.00: undefined anchor → 0 points + warning
    return { points: 0, fairDecimal: null, hardGateMarket: false };
  }

  const diff = candidateDecimal - fairDecimal;

  if (diff <= 0) {
    // Candidate price <= fair (favorite or at fair) → 10 points
    return { points: config.alignmentPoints.atOrBetter, fairDecimal, hardGateMarket: false };
  }
  if (diff < 0.2) {
    return { points: config.alignmentPoints.diff0to20, fairDecimal, hardGateMarket: false };
  }
  if (diff <= 0.3) {
    return { points: config.alignmentPoints.diff20to30, fairDecimal, hardGateMarket: false };
  }
  // diff > 0.30
  return { points: config.alignmentPoints.diffOver30, fairDecimal, hardGateMarket: false };
}

// ---------------------------------------------------------------------------
// Main engine
// ---------------------------------------------------------------------------

export function runMoneylineEngine(
  inputs: MoneylineInputs,
  config: MoneylineConfig
): MoneylineResult {
  const hardGates: HardGateCode[] = [];
  const warnings: WarningCode[] = [];

  // --- Hard gate: game already started ---
  if (inputs.gameAlreadyStarted) hardGates.push('GAME_ALREADY_STARTED');

  // --- Hard gate: starter status ---
  if (!inputs.candidateStarterConfirmed || inputs.opponentStarterConfirmed === false) {
    hardGates.push('STARTER_UNCONFIRMED');
  }
  if (inputs.candidateStarterGamesStarted === 0) hardGates.push('STARTER_GS_ZERO');
  if (inputs.candidateStarterRole === 'reliever' || inputs.candidateStarterRole === 'opener') {
    hardGates.push('STARTER_IS_RELIEVER');
  }
  // The ERA gap depends on both starters. A fallback on either side makes the
  // matchup comparison non-MLB-equivalent, even when the selected candidate's
  // own stats are MLB data.
  if (inputs.candidatePitcherLevelFallback || inputs.opponentPitcherLevelFallback) {
    hardGates.push('PITCHER_LEVEL_FALLBACK');
  }

  // --- Hard gate: IP ---
  const outsRecorded = inputs.candidateStarterOutsRecorded;
  const fullInnings = outsRecorded / 3;
  if (fullInnings < config.minSeasonIp) hardGates.push('IP_BELOW_MIN');
  else if (fullInnings < config.minWarnIp) warnings.push('BORDERLINE_IP');

  // --- Hard gate: game log ---
  if (inputs.candidateGameLogs.length < config.minGoodStartsRequired) {
    hardGates.push('INSUFFICIENT_GAME_LOG');
  }

  // --- Hard gate: candidate AVG ---
  if (inputs.candidateAvg < config.minCandidateAvg) hardGates.push('CANDIDATE_AVG_TOO_LOW');

  // --- ERA gap ---
  const eraGap = inputs.eraGap ?? calcEraGap(inputs.candidateStarterEra, inputs.opponentStarterEra);
  if (eraGap <= 0) hardGates.push('ERA_GAP_NOT_POSITIVE');

  // --- Odds ---
  if (!inputs.oddsProviderConfigured) warnings.push('ODDS_PROVIDER_NOT_CONFIGURED');
  if (inputs.oddsAreStale && inputs.oddsProviderConfigured) {
    // Odds were configured but the data is stale — hard gate
    hardGates.push('ODDS_STALE');
  } else if (inputs.candidateDecimalOdds === null) {
    // No odds at all — warning only (model runs without market alignment points)
    warnings.push('ODDS_MISSING');
  }

  // --- Score calculation (always runs, even if gates will fire) ---
  const eraGapPoints = eraGap > 0 ? getEraGapPoints(eraGap, config) : 0;

  const offenseResult = getOffenseTier(inputs.candidateAvg, inputs.candidateOps, config);
  if (offenseResult.mismatch) warnings.push('OFFENSE_TIER_MISMATCH');

  const gameLogResult = calcGameLogPoints(inputs.candidateGameLogs, config);
  if (gameLogResult.goodStarts <= 1) warnings.push('LOW_GAME_LOG_SCORE');

  let badStarts = 0;
  // Recent form is already represented in game-log points. Three bad starts
  // now produce a warning; only four or five are severe enough to hard gate.
  if (inputs.candidateGameLogs.length >= config.minGoodStartsRequired) {
    badStarts = inputs.candidateGameLogs
      .slice(-5)
      .filter((l) => computeEra(l.earnedRuns, l.outsRecorded) >= 4.0).length;
    if (badStarts >= config.maxBadStartsAllowed) hardGates.push('TOO_MANY_BAD_STARTS');
    else if (badStarts === config.maxBadStartsAllowed - 1) warnings.push('RECENT_FORM_WEAK');
  }

  // Additional warnings
  if (inputs.candidateAvg < 0.23 && eraGap < 2.0) warnings.push('LOW_AVG_SMALL_ERA_GAP');

  const alignmentResult =
    inputs.candidateDecimalOdds !== null
      ? calcMarketAlignmentPoints(eraGap, inputs.candidateDecimalOdds, config)
      : { points: 0, fairDecimal: null, hardGateMarket: false };
  const market = twoWayNoVigProbabilities(
    inputs.candidateDecimalOdds,
    inputs.opponentDecimalOdds ?? null,
  );

  if (alignmentResult.fairDecimal === null && eraGap >= 1.0) {
    warnings.push('UNDEFINED_MARKET_ANCHOR');
  }

  const teamFormPoints = calcTeamFormPoints(
    inputs.last10Wins,
    inputs.winStreak,
    inputs.lossStreak
  );

  const rawScore =
    eraGapPoints +
    offenseResult.points +
    gameLogResult.points +
    alignmentResult.points +
    teamFormPoints;

  // Market disagreement is risk information, not proof that the data-driven
  // side is invalid. Preserve it as a warning and prevent T1 promotion.
  const marketDisagreement = inputs.candidateDecimalOdds !== null
    && inputs.candidateDecimalOdds > config.maxT1DecimalOdds;
  if (marketDisagreement) warnings.push('MARKET_DISAGREEMENT');

  const lowSample = fullInnings < config.minWarnIp;

  // --- Determine final state ---
  let finalState: FinalState;
  if (hardGates.length > 0) {
    finalState = 'SKIP';
  } else if (rawScore >= config.t1MinScore) {
    if (lowSample || marketDisagreement) {
      finalState = 'T2';
      warnings.push('T1_CONFIDENCE_CAPPED');
    } else {
      finalState = 'T1';
    }
  } else if (rawScore >= config.t2MinScore) {
    finalState = 'T2';
  } else {
    finalState = 'SKIP';
  }

  return {
    eraGap,
    eraGapPoints,
    offensePoints: offenseResult.points,
    offenseAvgLabel: offenseResult.avgLabel,
    offenseOpsLabel: offenseResult.opsLabel,
    offenseMismatch: offenseResult.mismatch,
    gameLogGoodStarts: gameLogResult.goodStarts,
    gameLogPoints: gameLogResult.points,
    trend: gameLogResult.trend,
    marketAlignmentPoints: alignmentResult.points,
    fairDecimal: alignmentResult.fairDecimal,
    marketNoVigProbability: market.first,
    marketOverround: market.overround,
    confidenceType: 'heuristic-score',
    teamFormPoints,
    rawScore,
    finalState,
    hardGates,
    warnings,
  };
}
