import { describe, expect, it } from 'vitest';
import { runOUV3Engine, type OUV3Inputs } from '@/lib/engine/overunderV3';
import { DEFAULT_OU_V3_CONFIG } from '@/lib/config/modelConfig';

const fiveLogs = Array.from({ length: 5 }, () => ({ earnedRuns: 2, outsRecorded: 18 }));

function inputs(overrides: Partial<OUV3Inputs> = {}): OUV3Inputs {
  return {
    marketLine: 8.5,
    openingTotalLine: 8.5,
    overDecimal: 1.91,
    underDecimal: 1.95,
    leagueRpg: 4.5,
    awayRpg: 4.5,
    homeRpg: 4.5,
    awaySeasonEra: 4.2,
    homeSeasonEra: 4.2,
    awayStarterWhip: 1.30,
    homeStarterWhip: 1.30,
    awayStarterOuts: 300,
    homeStarterOuts: 300,
    awayStarterGamesStarted: 18,
    homeStarterGamesStarted: 18,
    awayLastFiveLogs: fiveLogs,
    homeLastFiveLogs: fiveLogs,
    awayPitcherLevelFallback: false,
    homePitcherLevelFallback: false,
    awayBullpenEra: 4.3,
    homeBullpenEra: 4.3,
    awayBullpenWhip: 1.30,
    homeBullpenWhip: 1.30,
    bullpenSourceLimited: false,
    homeParkFactor: 1,
    parkFactorIsFallback: false,
    awayStarterConfirmed: true,
    homeStarterConfirmed: true,
    oddsAreStale: false,
    teamDataAreStale: false,
    bullpenDataAreStale: false,
    parkFactorWrongSeason: false,
    gameAlreadyStarted: false,
    ...overrides,
  };
}

describe('O/U v3 staff run model', () => {
  it('shrinks the independent total toward the market prior', () => {
    const result = runOUV3Engine(inputs({
      awaySeasonEra: 6,
      homeSeasonEra: 6,
      awayBullpenEra: 5.5,
      homeBullpenEra: 5.5,
    }), DEFAULT_OU_V3_CONFIG);
    expect(result.independentModelTotal).not.toBeNull();
    expect(result.projectedTotal!).toBeGreaterThan(8.5);
    expect(result.projectedTotal!).toBeLessThan(result.independentModelTotal!);
  });

  it('resolves OVER first and downgrades a low Over price to LEAN', () => {
    const result = runOUV3Engine(inputs({
      awaySeasonEra: 6,
      homeSeasonEra: 6,
      awayBullpenEra: 5.5,
      homeBullpenEra: 5.5,
      overDecimal: 1.84,
      underDecimal: 2.10,
    }), DEFAULT_OU_V3_CONFIG);
    expect(result.selectedSide).toBe('over');
    expect(result.selectedPrice).toBe(1.84);
    expect(result.warnings).toContain('OU_PRICE_BELOW_ACTIONABLE');
    expect(result.finalState).toBe('OVER_LEAN');
  });

  it('resolves UNDER first and downgrades a low Under price to LEAN', () => {
    const result = runOUV3Engine(inputs({
      awaySeasonEra: 2.2,
      homeSeasonEra: 2.2,
      awayBullpenEra: 2.6,
      homeBullpenEra: 2.6,
      overDecimal: 2.10,
      underDecimal: 1.84,
    }), DEFAULT_OU_V3_CONFIG);
    expect(result.selectedSide).toBe('under');
    expect(result.selectedPrice).toBe(1.84);
    expect(result.warnings).toContain('OU_PRICE_BELOW_ACTIONABLE');
    expect(result.finalState).toBe('UNDER_LEAN');
  });

  it('requires bullpen data', () => {
    const result = runOUV3Engine(inputs({ awayBullpenEra: null }), DEFAULT_OU_V3_CONFIG);
    expect(result.hardGates).toContain('OU_BULLPEN_DATA_MISSING');
    expect(result.finalState).toBe('NO_BET');
  });

  it('blocks a one-run or larger total-line move', () => {
    const result = runOUV3Engine(inputs({ openingTotalLine: 7.5 }), DEFAULT_OU_V3_CONFIG);
    expect(result.hardGates).toContain('OU_EXCESSIVE_LINE_MOVE');
  });

  it('attenuates a fallback park factor', () => {
    const fallback = runOUV3Engine(inputs({
      homeParkFactor: 1.2,
      parkFactorIsFallback: true,
    }), DEFAULT_OU_V3_CONFIG);
    const authoritative = runOUV3Engine(inputs({
      homeParkFactor: 1.2,
      parkFactorIsFallback: false,
    }), DEFAULT_OU_V3_CONFIG);
    expect(fallback.effectiveParkFactor).toBeCloseTo(1.07, 5);
    expect(authoritative.effectiveParkFactor).toBeCloseTo(1.15, 5);
    expect(fallback.warnings).toContain('PARK_FACTOR_FALLBACK');
  });

  it('does not publish a fabricated calibrated probability', () => {
    const result = runOUV3Engine(inputs(), DEFAULT_OU_V3_CONFIG);
    expect(result.isExperimental).toBe(true);
    expect(result.isCalibrated).toBe(false);
    expect(result).not.toHaveProperty('winProbability');
    expect(result).not.toHaveProperty('expectedValue');
  });

  it('normalizes the two market prices to no-vig probabilities', () => {
    const result = runOUV3Engine(inputs({ overDecimal: 1.91, underDecimal: 1.95 }), DEFAULT_OU_V3_CONFIG);
    expect(result.noVigOverProbability! + result.noVigUnderProbability!).toBeCloseTo(1, 10);
  });

  it('uses LEAN to preserve direction below the actionable threshold', () => {
    const result = runOUV3Engine(inputs(), {
      ...DEFAULT_OU_V3_CONFIG,
      leanGapMin: 0.10,
      riskyGapMin: 0.50,
    });
    expect(['OVER_LEAN', 'UNDER_LEAN']).toContain(result.finalState);
    expect(result.selectedSide).not.toBeNull();
    expect(result.hardGates).not.toContain('OU_SMALL_GAP');
  });

  it('keeps a genuinely tiny gap as NO BET', () => {
    const result = runOUV3Engine(inputs(), {
      ...DEFAULT_OU_V3_CONFIG,
      leanGapMin: 0.30,
    });
    expect(Math.abs(result.gap ?? 999)).toBeLessThan(0.30);
    expect(result.finalState).toBe('NO_BET');
    expect(result.hardGates).toContain('OU_SMALL_GAP');
  });

  it('caps an otherwise actionable tier when input quality is below minimum', () => {
    const result = runOUV3Engine(inputs({
      awaySeasonEra: 2.2,
      homeSeasonEra: 2.2,
      awayBullpenEra: 2.6,
      homeBullpenEra: 2.6,
      awayStarterOuts: 210,
      homeStarterOuts: 210,
      parkFactorIsFallback: true,
      bullpenSourceLimited: true,
    }), DEFAULT_OU_V3_CONFIG);
    expect(result.warnings).toContain('OU_CONFIDENCE_CAPPED');
    expect(['OVER_LEAN', 'UNDER_LEAN']).toContain(result.finalState);
  });

  it('flags official minor-league pitcher fallback and never promotes it above lean', () => {
    const result = runOUV3Engine(inputs({
      awaySeasonEra: 2.2,
      homeSeasonEra: 2.2,
      awayBullpenEra: 2.6,
      homeBullpenEra: 2.6,
      awayStarterOuts: 210,
      homeStarterOuts: 210,
      awayPitcherLevelFallback: true,
    }), DEFAULT_OU_V3_CONFIG);
    expect(result.warnings).toContain('OU_PITCHER_LEVEL_FALLBACK');
    expect(['OVER_LEAN', 'UNDER_LEAN', 'NO_BET']).toContain(result.finalState);
  });

  it('reports the revised version', () => {
    expect(runOUV3Engine(inputs(), DEFAULT_OU_V3_CONFIG).modelVersion).toBe('3.1.0');
  });
});
