/**
 * O/U v3.0 — EXPERIMENTAL, market-anchored staff run model.
 *
 * It produces a transparent projected total and a gap label. It deliberately
 * does not emit a probability or EV: those require an out-of-sample calibrated
 * run distribution and settled historical forecasts.
 */

import { calcLastFiveAggEra, clamp, type OUGameLogEntry } from './overunder';
import type { OUV3Config } from '@/lib/config/modelConfig';
import type { FinalState, HardGateCode, WarningCode } from './types';

export interface OUV3Inputs {
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

export interface OUV3Result {
  isExperimental: true;
  isCalibrated: false;
  modelVersion: '3.1.0';
  selectedSide: 'over' | 'under' | null;
  selectedPrice: number | null;
  marketLine: number | null;
  openingTotalLine: number | null;
  lineMovement: number | null;
  noVigOverProbability: number | null;
  noVigUnderProbability: number | null;
  leagueRpg: number | null;
  awayLastFiveEra: number | null;
  homeLastFiveEra: number | null;
  awayBlendedStarterEra: number | null;
  homeBlendedStarterEra: number | null;
  awayExpectedStarterIp: number | null;
  homeExpectedStarterIp: number | null;
  awayStaffRunsAllowed: number | null;
  homeStaffRunsAllowed: number | null;
  awayOffenseFactor: number | null;
  homeOffenseFactor: number | null;
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

function expectedStarterIp(outs: number, starts: number, config: OUV3Config): number {
  return clamp(outs / 3 / starts, config.minStarterIpPerGame, config.maxStarterIpPerGame);
}

function blendedEra(
  seasonEra: number,
  recentEra: number | null,
  recentStarts: number,
  config: OUV3Config,
): number {
  if (recentEra === null || recentStarts === 0) return seasonEra;
  const sampleScale = Math.min(recentStarts / 5, 1);
  const recentWeight = config.starterRecentWeight * sampleScale;
  const seasonWeight = config.starterSeasonWeight + config.starterRecentWeight * (1 - sampleScale);
  return seasonEra * seasonWeight + recentEra * recentWeight;
}

function staffRuns(starterEra: number, starterIp: number, bullpenEra: number): number {
  return starterEra * (starterIp / 9) + bullpenEra * ((9 - starterIp) / 9);
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
  const decisionOnlyGates: HardGateCode[] = [
    'OU_SMALL_GAP',
    'OU_PRICE_BELOW_MINIMUM',
    'OU_EXCESSIVE_LINE_MOVE',
  ];
  if (hardGates.some((gate) => !decisionOnlyGates.includes(gate))) return 0;
  const penalties: Partial<Record<WarningCode, number>> = {
    PARK_FACTOR_FALLBACK: 10,
    OU_RECENT_SAMPLE_INCOMPLETE: 8,
    OU_BULLPEN_SOURCE_LIMITED: 6,
    OU_CONTEXT_NOT_MODELED: 8,
    OU_LINE_MOVE: 8,
    OU_MODEL_MARKET_OUTLIER: 15,
    OU_ERA_WHIP_DIVERGENCE: 6,
    OU_PRICE_BELOW_ACTIONABLE: 0,
    OU_PITCHER_LEVEL_FALLBACK: 25,
    BORDERLINE_SAMPLE: 12,
  };
  return Math.max(0, 100 - warnings.reduce((sum, warning) => sum + (penalties[warning] ?? 4), 0));
}

function emptyResult(
  inputs: OUV3Inputs,
  hardGates: HardGateCode[],
  warnings: WarningCode[],
): OUV3Result {
  return {
    isExperimental: true,
    isCalibrated: false,
    modelVersion: '3.1.0',
    selectedSide: null,
    selectedPrice: null,
    marketLine: inputs.marketLine,
    openingTotalLine: inputs.openingTotalLine,
    lineMovement: inputs.marketLine !== null && inputs.openingTotalLine !== null
      ? inputs.marketLine - inputs.openingTotalLine : null,
    noVigOverProbability: null,
    noVigUnderProbability: null,
    leagueRpg: inputs.leagueRpg,
    awayLastFiveEra: null,
    homeLastFiveEra: null,
    awayBlendedStarterEra: null,
    homeBlendedStarterEra: null,
    awayExpectedStarterIp: null,
    homeExpectedStarterIp: null,
    awayStaffRunsAllowed: null,
    homeStaffRunsAllowed: null,
    awayOffenseFactor: null,
    homeOffenseFactor: null,
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

export function runOUV3Engine(inputs: OUV3Inputs, config: OUV3Config): OUV3Result {
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

  // WHIP is a diagnostic cross-check, not double-counted as another run estimate.
  if (
    (inputs.awayStarterWhip !== null && (
      (inputs.awaySeasonEra! <= 3.50 && inputs.awayStarterWhip >= 1.40) ||
      (inputs.awaySeasonEra! >= 5.00 && inputs.awayStarterWhip <= 1.15)
    )) ||
    (inputs.homeStarterWhip !== null && (
      (inputs.homeSeasonEra! <= 3.50 && inputs.homeStarterWhip >= 1.40) ||
      (inputs.homeSeasonEra! >= 5.00 && inputs.homeStarterWhip <= 1.15)
    ))
  ) warnings.push('OU_ERA_WHIP_DIVERGENCE');

  const awayStaffRunsAllowed = staffRuns(awayStarterEra, awayStarterIp, inputs.awayBullpenEra!);
  const homeStaffRunsAllowed = staffRuns(homeStarterEra, homeStarterIp, inputs.homeBullpenEra!);
  const awayRawOffenseFactor = clamp(inputs.awayRpg! / inputs.leagueRpg!, 0.80, 1.20);
  const homeRawOffenseFactor = clamp(inputs.homeRpg! / inputs.leagueRpg!, 0.80, 1.20);
  const awayOffenseFactor = 1 + (awayRawOffenseFactor - 1) * config.offenseFactorWeight;
  const homeOffenseFactor = 1 + (homeRawOffenseFactor - 1) * config.offenseFactorWeight;
  const parkReliability = inputs.parkFactorIsFallback
    ? config.fallbackParkReliability : config.authoritativeParkReliability;
  const effectiveParkFactor = 1 + (inputs.homeParkFactor! - 1) * parkReliability;

  const independentModelTotal = (
    homeStaffRunsAllowed * awayOffenseFactor +
    awayStaffRunsAllowed * homeOffenseFactor
  ) * effectiveParkFactor;
  const projectedTotal = inputs.marketLine! * config.marketPriorWeight
    + independentModelTotal * (1 - config.marketPriorWeight);
  const gap = projectedTotal - inputs.marketLine!;

  if (Math.abs(independentModelTotal - inputs.marketLine!) > config.modelMarketOutlierMax) {
    warnings.push('OU_MODEL_MARKET_OUTLIER');
  }

  let selectedSide: 'over' | 'under' | null = null;
  let selectedPrice: number | null = null;
  let priceBelowActionable = false;
  let finalState: FinalState = 'NO_BET';
  if (Math.abs(gap) >= config.leanGapMin) {
    selectedSide = gap > 0 ? 'over' : 'under';
    selectedPrice = selectedSide === 'over' ? inputs.overDecimal : inputs.underDecimal;
    if (selectedPrice === null) hardGates.push('OU_LINE_MISSING');
    else if (Math.abs(gap) >= config.riskyGapMin && selectedPrice < config.minSelectedPrice) {
      priceBelowActionable = true;
      warnings.push('OU_PRICE_BELOW_ACTIONABLE');
    }

    if (hardGates.length === 0) {
      const absGap = Math.abs(gap);
      if (absGap < config.riskyGapMin) {
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      } else if (gap >= config.strongGapMin) finalState = 'OVER_STRONG_GAP';
      else if (gap > 0) finalState = 'OVER_RISKY';
      else if (gap <= -config.strongGapMin) finalState = 'UNDER_STRONG_GAP';
      else finalState = 'UNDER_RISKY';

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
        priceBelowActionable &&
        finalState !== 'OVER_LEAN' && finalState !== 'UNDER_LEAN'
      ) {
        finalState = gap > 0 ? 'OVER_LEAN' : 'UNDER_LEAN';
      }
    }
  } else {
    hardGates.push('OU_SMALL_GAP');
  }

  const noVig = noVigProbabilities(inputs.overDecimal, inputs.underDecimal);
  return {
    isExperimental: true,
    isCalibrated: false,
    modelVersion: '3.1.0',
    selectedSide,
    selectedPrice,
    marketLine: inputs.marketLine,
    openingTotalLine: inputs.openingTotalLine,
    lineMovement,
    noVigOverProbability: noVig.over,
    noVigUnderProbability: noVig.under,
    leagueRpg: inputs.leagueRpg,
    awayLastFiveEra,
    homeLastFiveEra,
    awayBlendedStarterEra: awayStarterEra,
    homeBlendedStarterEra: homeStarterEra,
    awayExpectedStarterIp: awayStarterIp,
    homeExpectedStarterIp: homeStarterIp,
    awayStaffRunsAllowed,
    homeStaffRunsAllowed,
    awayOffenseFactor,
    homeOffenseFactor,
    rawParkFactor: inputs.homeParkFactor,
    effectiveParkFactor,
    independentModelTotal,
    projectedTotal,
    gap,
    dataQualityScore: qualityScore(warnings, hardGates),
    missingContexts: ['weather', 'roof', 'confirmed_lineups', 'umpire', 'bullpen_workload'],
    finalState,
    hardGates,
    warnings,
  };
}
