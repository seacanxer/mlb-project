/**
 * lib/engine/overunder.ts
 *
 * Over/Under Formula v2.3 — EXPERIMENTAL
 *
 * Gap strength labels are formula-derived, not calibrated probability.
 * Every output MUST show the Experimental badge.
 */

import { computeEra } from '@/lib/utils/innings';
import type { OUConfig } from '@/lib/config/modelConfig';
import type { FinalState, WarningCode, HardGateCode } from './types';

// ---------------------------------------------------------------------------
// Input / output types
// ---------------------------------------------------------------------------

export interface OUGameLogEntry {
  earnedRuns: number;
  outsRecorded: number;
}

export interface OUInputs {
  // Market
  marketLine: number | null;
  selectedSideDecimal: number | null; // decimal odds for the selected Over or Under
  selectedSide: 'over' | 'under' | null;
  overDecimal?: number | null;
  underDecimal?: number | null;

  // Team offense
  awayRpg: number | null;
  homeRpg: number | null;

  // Starters
  awaySeasonEra: number | null;
  homeSeasonEra: number | null;
  awayLastFiveLogs: OUGameLogEntry[]; // last 5 starts
  homeLastFiveLogs: OUGameLogEntry[];

  // Pitchers whip (for PITCHING_DUEL_RISK warning)
  awayStarterWhip: number | null;
  homeStarterWhip: number | null;

  // Park factor (home venue only — applied once)
  homeParkFactor: number | null;
  parkFactorIsFallback: boolean;

  // Starter confirmations
  awayStarterConfirmed: boolean;
  homeStarterConfirmed: boolean;

  // Staleness
  oddsAreStale: boolean;
  teamRpgAreStale: boolean;
  pitcherDataMissing: boolean;
  parkFactorMissing: boolean;
  parkFactorWrongSeason: boolean;

  // Game state
  gameAlreadyStarted: boolean;
}

export interface OUResult {
  isExperimental: true;
  modelVersion: '2.3';

  // Intermediate calculations
  awayLastFiveEra: number | null;
  homeLastFiveEra: number | null;
  offAdj: number | null;
  pitchAdj: number | null;
  parkAdj: number | null;
  rawTotalAdj: number | null;
  totalAdj: number | null; // after clamp
  adjustedTotal: number | null;
  gap: number | null;
  capReached: boolean;
  selectedSide?: 'over' | 'under' | null;
  selectedPrice?: number | null;

  // Decision
  finalState: FinalState;
  hardGates: HardGateCode[];
  warnings: WarningCode[];
}

// ---------------------------------------------------------------------------
// Aggregate last-five ERA (from totals, not arithmetic mean)
// ---------------------------------------------------------------------------

export function calcLastFiveAggEra(logs: OUGameLogEntry[]): number | null {
  if (logs.length === 0) return null;
  const totalEr = logs.reduce((sum, l) => sum + l.earnedRuns, 0);
  const totalOuts = logs.reduce((sum, l) => sum + l.outsRecorded, 0);
  return computeEra(totalEr, totalOuts);
}

// ---------------------------------------------------------------------------
// Clamp
// ---------------------------------------------------------------------------

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// ---------------------------------------------------------------------------
// Main engine
// ---------------------------------------------------------------------------

export function runOUEngine(inputs: OUInputs, config: OUConfig): OUResult {
  const hardGates: HardGateCode[] = [];
  const warnings: WarningCode[] = [];

  // --- Hard gates ---
  if (inputs.gameAlreadyStarted) hardGates.push('GAME_ALREADY_STARTED');
  const anyTotalPrice = inputs.overDecimal ?? inputs.underDecimal ?? inputs.selectedSideDecimal;
  if (inputs.marketLine === null || anyTotalPrice === null) hardGates.push('OU_LINE_MISSING');
  // Legacy callers provided only one already-selected price. Preserve their
  // boundary gate; new callers provide both prices and are checked after the
  // formula resolves Over versus Under.
  if (
    inputs.overDecimal === undefined && inputs.underDecimal === undefined &&
    inputs.selectedSideDecimal !== null && inputs.selectedSideDecimal < config.minSelectedPrice
  ) hardGates.push('OU_PRICE_BELOW_MINIMUM');
  if (!inputs.awayStarterConfirmed || !inputs.homeStarterConfirmed) hardGates.push('OU_STARTER_UNCONFIRMED');
  if (inputs.pitcherDataMissing) hardGates.push('OU_PITCHER_DATA_MISSING');
  if (inputs.awayRpg === null || inputs.homeRpg === null || inputs.teamRpgAreStale) hardGates.push('OU_TEAM_RPG_MISSING');
  if (inputs.parkFactorMissing || inputs.parkFactorWrongSeason) hardGates.push('OU_PARK_FACTOR_MISSING');
  if (inputs.oddsAreStale) hardGates.push('OU_STALE_ODDS');

  // --- Park factor fallback warning ---
  if (inputs.parkFactorIsFallback) warnings.push('PARK_FACTOR_FALLBACK');

  // If critical gates fired, return early with no calculations
  if (hardGates.length > 0) {
    return {
      isExperimental: true,
      modelVersion: '2.3',
      awayLastFiveEra: null,
      homeLastFiveEra: null,
      offAdj: null,
      pitchAdj: null,
      parkAdj: null,
      rawTotalAdj: null,
      totalAdj: null,
      adjustedTotal: null,
      gap: null,
      capReached: false,
      finalState: inputs.marketLine === null ? 'NEEDS_DATA' : 'NO_BET',
      hardGates,
      warnings,
    };
  }

  // --- Calculations (all inputs validated above) ---
  const awayLastFiveEra = calcLastFiveAggEra(inputs.awayLastFiveLogs);
  const homeLastFiveEra = calcLastFiveAggEra(inputs.homeLastFiveLogs);

  if (awayLastFiveEra === null || homeLastFiveEra === null) {
    return {
      isExperimental: true,
      modelVersion: '2.3',
      awayLastFiveEra,
      homeLastFiveEra,
      offAdj: null,
      pitchAdj: null,
      parkAdj: null,
      rawTotalAdj: null,
      totalAdj: null,
      adjustedTotal: null,
      gap: null,
      capReached: false,
      finalState: 'NEEDS_DATA',
      hardGates: [...hardGates, 'OU_PITCHER_DATA_MISSING'],
      warnings,
    };
  }

  const awayRpg = inputs.awayRpg!;
  const homeRpg = inputs.homeRpg!;
  const awaySeasonEra = inputs.awaySeasonEra!;
  const homeSeasonEra = inputs.homeSeasonEra!;
  const parkFactor = inputs.homeParkFactor!;
  const marketLine = inputs.marketLine!;

  const offAdj =
    ((awayRpg - config.offenseBaseline) + (homeRpg - config.offenseBaseline)) * config.offenseWeight;

  const pitchAdj =
    ((awayLastFiveEra - awaySeasonEra) + (homeLastFiveEra - homeSeasonEra)) * config.pitchingWeight;

  const parkAdj = (parkFactor - 1.0) * marketLine * config.parkWeight;

  const rawTotalAdj = offAdj + pitchAdj + parkAdj;
  const totalAdj = clamp(rawTotalAdj, config.clampMin, config.clampMax);
  const capReached = totalAdj !== rawTotalAdj;
  if (capReached) warnings.push('EXTREME_PARK_ADJUSTMENT');

  const adjustedTotal = marketLine + totalAdj;
  const gap = adjustedTotal - marketLine; // = totalAdj

  // Gap gate: |gap| < 0.50
  if (Math.abs(gap) < 0.50) {
    hardGates.push('OU_SMALL_GAP');
    return {
      isExperimental: true,
      modelVersion: '2.3',
      awayLastFiveEra,
      homeLastFiveEra,
      offAdj,
      pitchAdj,
      parkAdj,
      rawTotalAdj,
      totalAdj,
      adjustedTotal,
      gap,
      capReached,
      finalState: 'NO_BET',
      hardGates,
      warnings,
    };
  }

  // Resolve the recommended side first, then validate that side's price. The
  // legacy selectedSideDecimal fallback keeps older callers/tests compatible.
  const selectedSide = gap > 0 ? 'over' : 'under';
  const selectedPrice = selectedSide === 'over'
    ? (inputs.overDecimal ?? inputs.selectedSideDecimal)
    : (inputs.underDecimal ?? inputs.selectedSideDecimal);
  if (selectedPrice === null) hardGates.push('OU_LINE_MISSING');
  else if (selectedPrice < config.minSelectedPrice) hardGates.push('OU_PRICE_BELOW_MINIMUM');
  if (hardGates.length > 0) {
    return {
      isExperimental: true,
      modelVersion: '2.3',
      awayLastFiveEra,
      homeLastFiveEra,
      offAdj,
      pitchAdj,
      parkAdj,
      rawTotalAdj,
      totalAdj,
      adjustedTotal,
      gap,
      capReached,
      selectedSide,
      selectedPrice,
      finalState: 'NO_BET',
      hardGates,
      warnings,
    };
  }

  // Pitching duel risk warning (OVER only)
  if (
    gap > 0 &&
    inputs.awayStarterWhip !== null &&
    inputs.homeStarterWhip !== null &&
    inputs.awayStarterWhip < 1.15 &&
    inputs.homeStarterWhip < 1.15
  ) {
    warnings.push('PITCHING_DUEL_RISK');
  }

  // Determine final state
  let finalState: FinalState;
  if (gap >= config.strongGapMin) {
    finalState = 'OVER_STRONG_GAP';
  } else if (gap >= config.riskyGapMin) {
    finalState = 'OVER_RISKY';
  } else if (gap <= -config.strongGapMin) {
    finalState = 'UNDER_STRONG_GAP';
  } else if (gap <= -config.riskyGapMin) {
    finalState = 'UNDER_RISKY';
  } else {
    finalState = 'NO_BET';
  }

  return {
    isExperimental: true,
    modelVersion: '2.3',
    awayLastFiveEra,
    homeLastFiveEra,
    offAdj,
    pitchAdj,
    parkAdj,
    rawTotalAdj,
    totalAdj,
    adjustedTotal,
    gap,
    capReached,
    selectedSide,
    selectedPrice,
    finalState,
    hardGates,
    warnings,
  };
}
