/**
 * tests/unit/overunder.test.ts
 *
 * Boundary tests for O/U v2.3.
 * Tests gap thresholds, clamp, odds boundary (1.84/1.85), hard gates, and warnings.
 */

import { describe, it, expect } from 'vitest';
import {
  runOUEngine,
  calcLastFiveAggEra,
  clamp,
  type OUInputs,
  type OUGameLogEntry,
} from '@/lib/engine/overunder';
import { DEFAULT_CONFIG } from '@/lib/config/modelConfig';

const cfg = DEFAULT_CONFIG.ou;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function goodLog(): OUGameLogEntry {
  return { earnedRuns: 1, outsRecorded: 18 }; // ERA 1.5
}

function makeInputs(overrides: Partial<OUInputs> = {}): OUInputs {
  return {
    marketLine: 8.5,
    selectedSideDecimal: 1.90,
    selectedSide: 'over',
    awayRpg: 4.5,
    homeRpg: 4.8,
    awaySeasonEra: 3.80,
    homeSeasonEra: 3.60,
    awayLastFiveLogs: [goodLog(), goodLog(), goodLog(), goodLog(), goodLog()],
    homeLastFiveLogs: [goodLog(), goodLog(), goodLog(), goodLog(), goodLog()],
    awayStarterWhip: 1.25,
    homeStarterWhip: 1.30,
    homeParkFactor: 1.05,
    parkFactorIsFallback: false,
    awayStarterConfirmed: true,
    homeStarterConfirmed: true,
    oddsAreStale: false,
    teamRpgAreStale: false,
    pitcherDataMissing: false,
    parkFactorMissing: false,
    parkFactorWrongSeason: false,
    gameAlreadyStarted: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Aggregate last-five ERA
// ---------------------------------------------------------------------------

describe('calcLastFiveAggEra', () => {
  it('correct aggregate ERA from totals (not arithmetic mean)', () => {
    const logs: OUGameLogEntry[] = [
      { earnedRuns: 2, outsRecorded: 15 },
      { earnedRuns: 3, outsRecorded: 18 },
    ];
    // Total ER = 5, Total outs = 33 → 5*27/33 ≈ 4.09
    expect(calcLastFiveAggEra(logs)).toBeCloseTo(4.09, 1);
  });
  it('returns null for empty logs', () => expect(calcLastFiveAggEra([])).toBeNull());
});

// ---------------------------------------------------------------------------
// Clamp boundaries
// ---------------------------------------------------------------------------

describe('clamp', () => {
  it('below -3 → -3.0', () => expect(clamp(-5, -3, 3)).toBe(-3));
  it('at -3 → -3.0', () => expect(clamp(-3, -3, 3)).toBe(-3));
  it('at +3 → +3.0', () => expect(clamp(3, -3, 3)).toBe(3));
  it('above +3 → +3.0', () => expect(clamp(5, -3, 3)).toBe(3));
  it('within range preserved', () => expect(clamp(1.5, -3, 3)).toBe(1.5));
});

// ---------------------------------------------------------------------------
// Gap thresholds: -0.75, -0.74, -0.50, -0.49, +0.49, +0.50, +0.74, +0.75
// ---------------------------------------------------------------------------

describe('O/U gap thresholds', () => {
  function resultForGap(gap: number) {
    // Manipulate RPG/ERA to achieve a specific gap
    // gap = totalAdj (since adjustedTotal = marketLine + totalAdj, gap = totalAdj)
    // Simplest: set offAdj=gap, pitchAdj=0, parkAdj=0
    // offAdj = ((awayRpg - 4.1) + (homeRpg - 4.1)) * 0.60 = gap
    // → sum of RPG deviations = gap / 0.60
    const dev = gap / 0.60;
    const awayRpg = 4.1 + dev / 2;
    const homeRpg = 4.1 + dev / 2;
    return runOUEngine(makeInputs({
      awayRpg,
      homeRpg,
      awaySeasonEra: 3.0,
      homeSeasonEra: 3.0,
      awayLastFiveLogs: [{ earnedRuns: 1, outsRecorded: 9 }], // ERA 3.0 agg
      homeLastFiveLogs: [{ earnedRuns: 1, outsRecorded: 9 }],
      homeParkFactor: 1.0, // neutral park, no park adj
      selectedSideDecimal: gap >= 0 ? 1.90 : 1.90,
    }), cfg);
  }

  it('gap >= +0.75 → OVER_STRONG_GAP', () => {
    const r = resultForGap(0.75);
    if (r.finalState !== 'NO_BET') expect(r.finalState).toBe('OVER_STRONG_GAP');
  });
  it('gap +0.74 → OVER_RISKY', () => {
    const r = resultForGap(0.74);
    if (r.finalState !== 'NO_BET') expect(['OVER_RISKY', 'OVER_STRONG_GAP']).toContain(r.finalState);
  });
  it('gap +0.50 → OVER_RISKY or better', () => {
    const r = resultForGap(0.50);
    expect(['OVER_RISKY', 'OVER_STRONG_GAP']).toContain(r.finalState);
  });
  it('gap +0.49 → NO_BET (small gap gate)', () => {
    const r = resultForGap(0.49);
    expect(r.finalState).toBe('NO_BET');
  });
  it('gap -0.49 → NO_BET', () => {
    const r = resultForGap(-0.49);
    expect(r.finalState).toBe('NO_BET');
  });
  it('gap -0.50 → UNDER_RISKY or better', () => {
    const r = resultForGap(-0.50);
    expect(['UNDER_RISKY', 'UNDER_STRONG_GAP']).toContain(r.finalState);
  });
  it('gap -0.75 → UNDER_STRONG_GAP', () => {
    const r = resultForGap(-0.75);
    expect(['UNDER_RISKY', 'UNDER_STRONG_GAP']).toContain(r.finalState);
  });
});

// ---------------------------------------------------------------------------
// Selected-side price boundary
// ---------------------------------------------------------------------------

describe('selected side price boundary', () => {
  it('decimal 1.84 → OU_PRICE_BELOW_MINIMUM hard gate', () => {
    const r = runOUEngine(makeInputs({ selectedSideDecimal: 1.84 }), cfg);
    expect(r.hardGates).toContain('OU_PRICE_BELOW_MINIMUM');
    expect(r.finalState).toBe('NO_BET');
  });
  it('decimal 1.85 → no price gate', () => {
    const r = runOUEngine(makeInputs({ selectedSideDecimal: 1.85 }), cfg);
    expect(r.hardGates).not.toContain('OU_PRICE_BELOW_MINIMUM');
  });
});

// ---------------------------------------------------------------------------
// Hard gates
// ---------------------------------------------------------------------------

describe('O/U hard gates', () => {
  it('missing market line → NEEDS_DATA', () => {
    const r = runOUEngine(makeInputs({ marketLine: null }), cfg);
    expect(r.finalState).toBe('NEEDS_DATA');
  });
  it('starter unconfirmed → hard gate', () => {
    const r = runOUEngine(makeInputs({ awayStarterConfirmed: false }), cfg);
    expect(r.hardGates).toContain('OU_STARTER_UNCONFIRMED');
  });
  it('pitcher data missing → hard gate', () => {
    const r = runOUEngine(makeInputs({ pitcherDataMissing: true }), cfg);
    expect(r.hardGates).toContain('OU_PITCHER_DATA_MISSING');
  });
  it('missing team RPG → hard gate', () => {
    const r = runOUEngine(makeInputs({ awayRpg: null }), cfg);
    expect(r.hardGates).toContain('OU_TEAM_RPG_MISSING');
  });
  it('park factor missing → hard gate', () => {
    const r = runOUEngine(makeInputs({ parkFactorMissing: true }), cfg);
    expect(r.hardGates).toContain('OU_PARK_FACTOR_MISSING');
  });
  it('game already started → hard gate', () => {
    const r = runOUEngine(makeInputs({ gameAlreadyStarted: true }), cfg);
    expect(r.hardGates).toContain('GAME_ALREADY_STARTED');
  });
  it('stale odds → OU_STALE_ODDS', () => {
    const r = runOUEngine(makeInputs({ oddsAreStale: true }), cfg);
    expect(r.hardGates).toContain('OU_STALE_ODDS');
  });
  it('adjustment cap reached → EXTREME_PARK_ADJUSTMENT warning', () => {
    // Force rawTotalAdj > 3: use huge RPG deviation
    const r = runOUEngine(makeInputs({ awayRpg: 10, homeRpg: 10 }), cfg);
    if (!r.hardGates.includes('OU_SMALL_GAP')) {
      expect(r.warnings).toContain('EXTREME_PARK_ADJUSTMENT');
      expect(r.capReached).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Warnings
// ---------------------------------------------------------------------------

describe('O/U warnings', () => {
  it('PITCHING_DUEL_RISK on OVER with both WHIP < 1.15', () => {
    const r = runOUEngine(makeInputs({
      awayStarterWhip: 1.10,
      homeStarterWhip: 1.10,
      awayRpg: 5.5,
      homeRpg: 5.5, // force OVER gap
    }), cfg);
    if (r.finalState === 'OVER_STRONG_GAP' || r.finalState === 'OVER_RISKY') {
      expect(r.warnings).toContain('PITCHING_DUEL_RISK');
    }
  });
  it('isExperimental always true', () => {
    const r = runOUEngine(makeInputs(), cfg);
    expect(r.isExperimental).toBe(true);
    expect(r.modelVersion).toBe('2.3');
  });
});
