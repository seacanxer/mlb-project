import { describe, expect, it } from 'vitest';
import { DEFAULT_OU_TOTALS_CONFIG } from '@/lib/config/modelConfig';
import { poissonTotalProbabilities, runOUTotalsEngine, type OUTotalsInputs } from '@/lib/engine/overunderUnified';

const fiveLogs = Array.from({ length: 5 }, () => ({ earnedRuns: 2, outsRecorded: 18 }));

function inputs(overrides: Partial<OUTotalsInputs> = {}): OUTotalsInputs {
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

describe('Unified MLB Totals v4', () => {
  it('publishes a complete experimental distribution including integer pushes', () => {
    const half = poissonTotalProbabilities(8.5, 8.5);
    expect(half.over + half.under).toBeCloseTo(1, 8);
    expect(half.push).toBe(0);

    const integer = poissonTotalProbabilities(8, 8);
    expect(integer.over + integer.under + integer.push).toBeCloseTo(1, 8);
    expect(integer.push).toBeGreaterThan(0);
  });
  it('can publish an OVER using the Over price', () => {
    const result = runOUTotalsEngine(inputs({
      awayRpg: 5.7,
      homeRpg: 5.5,
      awaySeasonEra: 5.4,
      homeSeasonEra: 5.2,
      awayBullpenEra: 5.1,
      homeBullpenEra: 5.0,
    }), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.selectedSide).toBe('over');
    expect(result.selectedPrice).toBe(1.91);
    expect(['OVER_RISKY', 'OVER_STRONG_GAP']).toContain(result.finalState);
  });

  it('can publish an UNDER using the Under price', () => {
    const result = runOUTotalsEngine(inputs({
      awayRpg: 3.6,
      homeRpg: 3.7,
      awaySeasonEra: 2.8,
      homeSeasonEra: 2.9,
      awayBullpenEra: 3.0,
      homeBullpenEra: 3.1,
    }), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.selectedSide).toBe('under');
    expect(result.selectedPrice).toBe(1.95);
    expect(['UNDER_RISKY', 'UNDER_STRONG_GAP']).toContain(result.finalState);
  });

  it('averages team scoring and opposing staff allowance on the same run scale', () => {
    const result = runOUTotalsEngine(inputs({
      awayRpg: 5,
      homeRpg: 4,
      awaySeasonEra: 4,
      homeSeasonEra: 5,
      awayBullpenEra: 4,
      homeBullpenEra: 5,
      awayLastFiveLogs: [],
      homeLastFiveLogs: [],
    }), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.awayExpectedRuns).toBeCloseTo(5, 6);
    expect(result.homeExpectedRuns).toBeCloseTo(4, 6);
    expect(result.independentModelTotal).toBeCloseTo(9, 6);
  });

  it('uses 30-59.2 IP as a warning sample instead of an automatic no-bet', () => {
    const result = runOUTotalsEngine(inputs({
      awayStarterOuts: 120,
      homeStarterOuts: 120,
      awayStarterGamesStarted: 8,
      homeStarterGamesStarted: 8,
    }), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.hardGates).not.toContain('OU_STARTER_IP_BELOW_MIN');
    expect(result.warnings).toContain('BORDERLINE_SAMPLE');
  });

  it('still blocks a starter below 30 innings', () => {
    const result = runOUTotalsEngine(inputs({ awayStarterOuts: 60 }), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.hardGates).toContain('OU_STARTER_IP_BELOW_MIN');
    expect(result.finalState).toBe('NO_BET');
  });

  it('does not publish fabricated model probability or EV', () => {
    const result = runOUTotalsEngine(inputs(), DEFAULT_OU_TOTALS_CONFIG);
    expect(result.modelVersion).toBe('4.0.0');
    expect(result.isCalibrated).toBe(false);
    expect(result).not.toHaveProperty('winProbability');
    expect(result).not.toHaveProperty('expectedValue');
  });
});
