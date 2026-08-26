/**
 * Unified MLB Totals v4.0 — the only active O/U projection.
 *
 * The model is deterministic and intentionally does not claim a calibrated
 * win probability. It combines opponent-adjusted offense and pitching, applies
 * a reliability-shrunk park factor, then shrinks the independent projection
 * toward the current market total.
 */

import type { OUTotalsConfig } from '@/lib/config/modelConfig';
import type { FinalState, HardGateCode, WarningCode } from './types';

export interface OUGameLogEntry {
  earnedRuns: number;
  outsRecorded: number;
}

export interface OUTotalsInputs {
  marketLine: number | null;
  openingTotalLine: number | null;
  overDecimal: number | null;
  underDecimal: number | null;

  leagueRpg: number | null;
  awayRpg: number | null;
  homeRpg: number | null;

  awaySeasonEra: number | null;
  homeSeasonEra: number | null;
  awayStarterWhip: number | null;
  homeStarterWhip: number | null;
  awayStarterOuts: number | null;
  homeStarterOuts: number | null;
  awayStarterGamesStarted: number | null;
  homeStarterGamesStarted: number | null;
  awayLastFiveLogs: OUGameLogEntry[];
  homeLastFiveLogs: OUGameLogEntry[];
  awayPitcherLevelFallback: boolean;
  homePitcherLevelFallback: boolean;

  awayBullpenEra: number | null;
  homeBullpenEra: number | null;
  awayBullpenWhip: number | null;
  homeBullpenWhip: number | null;
  bullpenSourceLimited: boolean;

  homeParkFactor: number | null;
  parkFactorIsFallback: boolean;
  awayStarterConfirmed: boolean;
  homeStarterConfirmed: boolean;

  oddsAreStale: boolean;
  teamDataAreStale: boolean;
  bullpenDataAreStale: boolean;
  parkFactorWrongSeason: boolean;
  gameAlreadyStarted: boolean;
}

export interface OUTotalsResult {
  isExperimental: true;
  isCalibrated: false;
  modelVersion: '4.0.0';
  formulaName: 'Unified MLB Totals';
  selectedSide: 'over' | 'under' | null;
  selectedPrice: number | null;
  marketLine: number | null;
  openingTotalLine: number | null;
  lineMovement: number | null;
  noVigOverProbability: number | null;
  noVigUnderProbability: number | null;
  leagueRpg: number | null;
  awayRpg: number | null;
  homeRpg: number | null;
  awayLastFiveEra: number | null;
  homeLastFiveEra: number | null;
  awayBlendedStarterEra: number | null;
  homeBlendedStarterEra: number | null;
  awayExpectedStarterIp: number | null;
  homeExpectedStarterIp: number | null;
  awayStaffRunsAllowed: number | null;
  homeStaffRunsAllowed: number | null;
  awayExpectedRuns: number | null;
  homeExpectedRuns: number | null;
  whipRunAdjustment: number | null;
  rawParkFactor: number | null;
  effectiveParkFactor: number | null;
  independentModelTotal: number | null;
  projectedTotal: number | null;
  gap: number | null;
  dataQualityScore: number;
  missingContexts: string[];
  finalState: FinalState;
  hardGates: HardGateCode[];
  warnings: WarningCode[];
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function calcLastFiveAggEra(logs: OUGameLogEntry[]): number | null {
  const valid = logs.filter((log) => log.outsRecorded > 0);
  if (valid.length === 0) return null;
  const earnedRuns = valid.reduce((sum, log) => sum + log.earnedRuns, 0);
  const outs = valid.reduce((sum, log) => sum + log.outsRecorded, 0);
  return earnedRuns * 27 / outs;
}

function expectedStarterIp(outs: number, starts: number, config: OUTotalsConfig): number {
  return clamp(outs / 3 / starts, config.minStarterIpPerGame, config.maxStarterIpPerGame);
}

function blendedEra(
  seasonEra: number,
  recentEra: number | null,
  recentStarts: number,
  config: OUTotalsConfig,
): number {
  if (recentEra === null || recentStarts === 0) return seasonEra;
  const sampleScale = Math.min(recentStarts / 5, 1);
  const recentWeight = config.starterRecentWeight * sampleScale;
  const seasonWeight = config.starterSeasonWeight + config.starterRecentWeight * (1 - sampleScale);
  return seasonEra * seasonWeight + recentEra * recentWeight;
}

function whipAdjustment(
  whip: number | null,
  innings: number,
  config: OUTotalsConfig,
): number {
  if (whip === null) return 0;
  return clamp(
    (whip - config.whipBaseline) * config.whipRunsWeight * (innings / 9),
    -config.maxWhipRunAdjustment,
    config.maxWhipRunAdjustment,
  );
}

function staffRuns(
  starterEra: number,
  starterWhip: number | null,
  starterIp: number,
  bullpenEra: number,
  bullpenWhip: number | null,
  config: OUTotalsConfig,
): { runs: number; whipAdjustment: number } {
  const bullpenIp = 9 - starterIp;
  const adjustment = whipAdjustment(starterWhip, starterIp, config)
    + whipAdjustment(bullpenWhip, bullpenIp, config);
  return {
    runs: starterEra * (starterIp / 9) + bullpenEra * (bullpenIp / 9) + adjustment,
    whipAdjustment: adjustment,
  };
}

function noVigProbabilities(over: number | null, under: number | null) {
  if (over === null || under === null || over <= 1 || under <= 1) {
    return { over: null, under: null };
  }
  const overRaw = 1 / over;
  const underRaw = 1 / under;
  const total = overRaw + underRaw;
  return { over: overRaw / total, under: underRaw / total };
}

function qualityScore(warnings: WarningCode[], hardGates: HardGateCode[]): number {
  const decisionOnly = new Set<HardGateCode>([
    'OU_SMALL_GAP',
    'OU_PRICE_BELOW_MINIMUM',
    'OU_EXCESSIVE_LINE_MOVE',
  ]);
  if (hardGates.some((gate) => !decisionOnly.has(gate))) return 0;
  const penalties: Partial<Record<WarningCode, number>> = {
    PARK_FACTOR_FALLBACK: 8,
    OU_RECENT_SAMPLE_INCOMPLETE: 8,
    OU_BULLPEN_SOURCE_LIMITED: 5,
    OU_CONTEXT_NOT_MODELED: 5,
    OU_LINE_MOVE: 8,
    OU_MODEL_MARKET_OUTLIER: 12,
    OU_ERA_WHIP_DIVERGENCE: 5,
    OU_PRICE_BELOW_ACTIONABLE: 0,
    OU_PITCHER_LEVEL_FALLBACK: 25,
    OU_WHIP_PARTIAL: 4,
    OU_CONFIDENCE_CAPPED: 0,
    BORDERLINE_SAMPLE: 10,
  };
  return Math.max(0, 100 - warnings.reduce((sum, warning) => sum + (penalties[warning] ?? 3), 0));
}

function emptyResult(
  inputs: OUTotalsInputs,
  hardGates: HardGateCode[],
  warnings: WarningCode[],
): OUTotalsResult {
  return {
    isExperimental: true,
    isCalibrated: false,
    modelVersion: '4.0.0',
    formulaName: 'Unified MLB Totals',
    selectedSide: null,
    selectedPrice: null,
    marketLine: inputs.marketLine,
    openingTotalLine: inputs.openingTotalLine,
    lineMovement: inputs.marketLine !== null && inputs.openingTotalLine !== null
      ? inputs.marketLine - inputs.openingTotalLine : null,
    noVigOverProbability: null,
    noVigUnderProbability: null,
    leagueRpg: inputs.leagueRpg,
    awayRpg: inputs.awayRpg,
    homeRpg: inputs.homeRpg,
    awayLastFiveEra: null,
    homeLastFiveEra: null,
    awayBlendedStarterEra: null,
    homeBlendedStarterEra: null,
    awayExpectedStarterIp: null,
    homeExpectedStarterIp: null,
    awayStaffRunsAllowed: null,
    homeStaffRunsAllowed: null,
    awayExpectedRuns: null,
    homeExpectedRuns: null,
    whipRunAdjustment: null,
    rawParkFactor: inputs.homeParkFactor,
    effectiveParkFactor: null,
    independentModelTotal: null,
    projectedTotal: null,
    gap: null,
    dataQualityScore: qualityScore(warnings, hardGates),
    missingContexts: ['weather', 'roof', 'confirmed_lineups', 'umpire', 'bullpen_workload'],
    finalState: inputs.marketLine === null ? 'NEEDS_DATA' : 'NO_BET',
    hardGates,
    warnings,
  };
}

export function runOUTotalsEngine(inputs: OUTotalsInputs, config: OUTotalsConfig): OUTotalsResult {
  const hardGates: HardGateCode[] = [];
  const warnings: WarningCode[] = ['OU_CONTEXT_NOT_MODELED'];

  if (inputs.gameAlreadyStarted) hardGates.push('GAME_ALREADY_STARTED');
  if (inputs.marketLine === null) hardGates.push('OU_LINE_MISSING');
  if (!inputs.awayStarterConfirmed || !inputs.homeStarterConfirmed) hardGates.push('OU_STARTER_UNCONFIRMED');
  if (
    inputs.awaySeasonEra === null || inputs.homeSeasonEra === null ||
    inputs.awayStarterOuts === null || inputs.homeStarterOuts === null ||
    !inputs.awayStarterGamesStarted || !inputs.homeStarterGamesStarted
  ) hardGates.push('OU_PITCHER_DATA_MISSING');
  if (inputs.awayRpg === null || inputs.homeRpg === null || inputs.leagueRpg === null || inputs.teamDataAreStale) {
    hardGates.push('OU_TEAM_RPG_MISSING');
  }
  if (inputs.awayBullpenEra === null || inputs.homeBullpenEra === null || inputs.bullpenDataAreStale) {
    hardGates.push('OU_BULLPEN_DATA_MISSING');
  }
  if (inputs.homeParkFactor === null || inputs.parkFactorWrongSeason) hardGates.push('OU_PARK_FACTOR_MISSING');
  if (inputs.oddsAreStale) hardGates.push('OU_STALE_ODDS');

  const awaySeasonIp = (inputs.awayStarterOuts ?? 0) / 3;
  const homeSeasonIp = (inputs.homeStarterOuts ?? 0) / 3;
  if (awaySeasonIp < config.minSeasonIp || homeSeasonIp < config.minSeasonIp) {
    hardGates.push('OU_STARTER_IP_BELOW_MIN');
  } else if (awaySeasonIp < config.warnSeasonIp || homeSeasonIp < config.warnSeasonIp) {
    warnings.push('BORDERLINE_SAMPLE');
  }

  if (inputs.parkFactorIsFallback) warnings.push('PARK_FACTOR_FALLBACK');
  if (inputs.bullpenSourceLimited) warnings.push('OU_BULLPEN_SOURCE_LIMITED');
  if (inputs.awayLastFiveLogs.length < 5 || inputs.homeLastFiveLogs.length < 5) {
    warnings.push('OU_RECENT_SAMPLE_INCOMPLETE');
  }
  if (inputs.awayPitcherLevelFallback || inputs.homePitcherLevelFallback) {
    warnings.push('OU_PITCHER_LEVEL_FALLBACK');
  }
  if (
    inputs.awayStarterWhip === null || inputs.homeStarterWhip === null ||
    inputs.awayBullpenWhip === null || inputs.homeBullpenWhip === null
  ) warnings.push('OU_WHIP_PARTIAL');

  const lineMovement = inputs.marketLine !== null && inputs.openingTotalLine !== null
    ? inputs.marketLine - inputs.openingTotalLine : null;
  if (lineMovement !== null && Math.abs(lineMovement) >= config.lineMoveHard) {
    hardGates.push('OU_EXCESSIVE_LINE_MOVE');
  } else if (lineMovement !== null && Math.abs(lineMovement) >= config.lineMoveWarn) {
    warnings.push('OU_LINE_MOVE');
  }

  if (hardGates.length > 0) return emptyResult(inputs, hardGates, warnings);

  const awayLastFiveEra = calcLastFiveAggEra(inputs.awayLastFiveLogs);
  const homeLastFiveEra = calcLastFiveAggEra(inputs.homeLastFiveLogs);
  const awayStarterIp = expectedStarterIp(inputs.awayStarterOuts!, inputs.awayStarterGamesStarted!, config);
  const homeStarterIp = expectedStarterIp(inputs.homeStarterOuts!, inputs.homeStarterGamesStarted!, config);
  const awayStarterEra = blendedEra(inputs.awaySeasonEra!, awayLastFiveEra, inputs.awayLastFiveLogs.length, config);
  const homeStarterEra = blendedEra(inputs.homeSeasonEra!, homeLastFiveEra, inputs.homeLastFiveLogs.length, config);

  if (
    (inputs.awayStarterWhip !== null && Math.abs(inputs.awaySeasonEra! - 4.25) > 1 && Math.abs(inputs.awayStarterWhip - config.whipBaseline) > 0.15) ||
    (inputs.homeStarterWhip !== null && Math.abs(inputs.homeSeasonEra! - 4.25) > 1 && Math.abs(inputs.homeStarterWhip - config.whipBaseline) > 0.15)
  ) warnings.push('OU_ERA_WHIP_DIVERGENCE');

  const awayStaff = staffRuns(
    awayStarterEra, inputs.awayStarterWhip, awayStarterIp,
    inputs.awayBullpenEra!, inputs.awayBullpenWhip, config,
  );
  const homeStaff = staffRuns(
    homeStarterEra, inputs.homeStarterWhip, homeStarterIp,
    inputs.homeBullpenEra!, inputs.homeBullpenWhip, config,
  );

  // Each team's run estimate averages what its offense actually scores with
  // what the opposing starter/bullpen allows. Equal weighting avoids a baked-in
  // OVER or UNDER direction while keeping every term on the same runs/game scale.
  const pitchingWeight = 1 - config.offenseProjectionWeight;
  const awayExpectedRuns = inputs.awayRpg! * config.offenseProjectionWeight
    + homeStaff.runs * pitchingWeight;
  const homeExpectedRuns = inputs.homeRpg! * config.offenseProjectionWeight
    + awayStaff.runs * pitchingWeight;

  const parkReliability = inputs.parkFactorIsFallback
    ? config.fallbackParkReliability : config.authoritativeParkReliability;
  const effectiveParkFactor = 1 + (inputs.homeParkFactor! - 1) * parkReliability;
  const independentModelTotal = (awayExpectedRuns + homeExpectedRuns) * effectiveParkFactor;
  const projectedTotal = inputs.marketLine! * config.marketPriorWeight
    + independentModelTotal * (1 - config.marketPriorWeight);
  const gap = projectedTotal - inputs.marketLine!;

  if (Math.abs(independentModelTotal - inputs.marketLine!) > config.modelMarketOutlierMax) {
    warnings.push('OU_MODEL_MARKET_OUTLIER');
  }

  let selectedSide: 'over' | 'under' | null = null;
  let selectedPrice: number | null = null;
  let finalState: FinalState = 'NO_BET';
  const absGap = Math.abs(gap);

  if (absGap < config.leanGapMin) {
    hardGates.push('OU_SMALL_GAP');
  } else {
    selectedSide = gap > 0 ? 'over' : 'under';
    selectedPrice = selectedSide === 'over' ? inputs.overDecimal : inputs.underDecimal;
    if (selectedPrice === null) {
      hardGates.push('OU_LINE_MISSING');
    } else {
      if (absGap < config.riskyGapMin) {
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      } else if (absGap >= config.strongGapMin) {
        finalState = gap > 0 ? 'OVER_STRONG_GAP' : 'UNDER_STRONG_GAP';
      } else {
        finalState = gap > 0 ? 'OVER_RISKY' : 'UNDER_RISKY';
      }

      if (selectedPrice < config.minSelectedPrice && absGap >= config.riskyGapMin) {
        warnings.push('OU_PRICE_BELOW_ACTIONABLE');
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      }

      const preCapQuality = qualityScore(warnings, hardGates);
      if (
        (finalState === 'OVER_STRONG_GAP' || finalState === 'UNDER_STRONG_GAP') &&
        preCapQuality < config.minStrongDataQuality
      ) {
        warnings.push('OU_CONFIDENCE_CAPPED');
        finalState = gap > 0 ? 'OVER_RISKY' : 'UNDER_RISKY';
      }
      if (
        (finalState === 'OVER_RISKY' || finalState === 'UNDER_RISKY') &&
        preCapQuality < config.minRiskyDataQuality
      ) {
        if (!warnings.includes('OU_CONFIDENCE_CAPPED')) warnings.push('OU_CONFIDENCE_CAPPED');
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      }
      if (
        (inputs.awayPitcherLevelFallback || inputs.homePitcherLevelFallback) &&
        finalState !== 'OVER_LEAN' && finalState !== 'UNDER_LEAN'
      ) {
        if (!warnings.includes('OU_CONFIDENCE_CAPPED')) warnings.push('OU_CONFIDENCE_CAPPED');
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      }
    }
  }

  const noVig = noVigProbabilities(inputs.overDecimal, inputs.underDecimal);
  return {
    isExperimental: true,
    isCalibrated: false,
    modelVersion: '4.0.0',
    formulaName: 'Unified MLB Totals',
    selectedSide,
    selectedPrice,
    marketLine: inputs.marketLine,
    openingTotalLine: inputs.openingTotalLine,
    lineMovement,
    noVigOverProbability: noVig.over,
    noVigUnderProbability: noVig.under,
    leagueRpg: inputs.leagueRpg,
    awayRpg: inputs.awayRpg,
    homeRpg: inputs.homeRpg,
    awayLastFiveEra,
    homeLastFiveEra,
    awayBlendedStarterEra: awayStarterEra,
    homeBlendedStarterEra: homeStarterEra,
    awayExpectedStarterIp: awayStarterIp,
    homeExpectedStarterIp: homeStarterIp,
    awayStaffRunsAllowed: awayStaff.runs,
    homeStaffRunsAllowed: homeStaff.runs,
    awayExpectedRuns,
    homeExpectedRuns,
    whipRunAdjustment: awayStaff.whipAdjustment + homeStaff.whipAdjustment,
    rawParkFactor: inputs.homeParkFactor,
    effectiveParkFactor,
    independentModelTotal,
    projectedTotal,
    gap,
    dataQualityScore: qualityScore(warnings, hardGates),
    missingContexts: ['weather', 'roof', 'confirmed_lineups', 'umpire', 'bullpen_workload'],
    finalState: hardGates.length > 0 ? 'NO_BET' : finalState,
    hardGates,
    warnings,
  };
}
