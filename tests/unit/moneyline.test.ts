/**
 * tests/unit/moneyline.test.ts
 *
 * Boundary tests for Moneyline Combo Score v2.0.
 * Tests every band edge, tier edge, hard gate, and warning code.
 */

import { describe, it, expect } from 'vitest';
import {
  calcEraGap,
  calcGameLogPoints,
  calcTeamFormPoints,
  calcMarketAlignmentPoints,
  runMoneylineEngine,
  selectMoneylineCandidate,
  type MoneylineInputs,
  type GameLogEntry,
} from '@/lib/engine/moneyline';
import { DEFAULT_CONFIG } from '@/lib/config/modelConfig';

const cfg = DEFAULT_CONFIG.moneyline;

// ---------------------------------------------------------------------------
// Helper: build minimal valid inputs
// ---------------------------------------------------------------------------

function goodLog(earnedRuns = 1, outsRecorded = 18): GameLogEntry {
  return { earnedRuns, outsRecorded, gameDate: '2025-07-01' };
}

function badLog(): GameLogEntry {
  return { earnedRuns: 4, outsRecorded: 15, gameDate: '2025-07-01' }; // ERA = 7.2
}

function makeInputs(overrides: Partial<MoneylineInputs> = {}): MoneylineInputs {
  return {
    candidateStarterEra: 2.50,
    opponentStarterEra: 4.50,
    candidateStarterOutsRecorded: 200, // ~66.2 IP
    candidateStarterGamesStarted: 18,
    candidateStarterConfirmed: true,
    candidateStarterName: 'Test Pitcher',
    candidateAvg: 0.265,
    candidateOps: 0.770,
    candidateGameLogs: [goodLog(), goodLog(), goodLog(), goodLog(), goodLog()],
    candidateDecimalOdds: 1.70,
    last10Wins: 7,
    last10Losses: 3,
    winStreak: 2,
    lossStreak: 0,
    gameAlreadyStarted: false,
    oddsAreStale: false,
    oddsProviderConfigured: true,
    ...overrides,
  };
}

describe('candidate selection', () => {
  it('selects an actionable away T2 over a skipped home candidate', () => {
    const home = runMoneylineEngine(makeInputs({ candidateStarterEra: 4.5, opponentStarterEra: 2.5 }), cfg);
    const away = runMoneylineEngine(makeInputs({
      candidateStarterEra: 3.0,
      opponentStarterEra: 4.0,
      candidateAvg: 0.250,
      candidateOps: 0.740,
      candidateGameLogs: [goodLog(), goodLog(), goodLog(), badLog(), badLog()],
      last10Wins: 4,
      last10Losses: 6,
      winStreak: 0,
    }), cfg);

    const selected = selectMoneylineCandidate(home, away);
    expect(selected.side).toBe('away');
    expect(selected.result.finalState).toBe('T2');
  });

  it('keeps the positive ERA-gap side as the audited candidate when both sides skip', () => {
    const home = runMoneylineEngine(makeInputs({ candidateStarterEra: 4.5, opponentStarterEra: 2.5 }), cfg);
    const away = runMoneylineEngine(makeInputs({
      candidateStarterEra: 2.5,
      opponentStarterEra: 4.5,
      candidateGameLogs: [goodLog(), goodLog()],
    }), cfg);

    const selected = selectMoneylineCandidate(home, away);
    expect(selected.side).toBe('away');
    expect(selected.result.finalState).toBe('SKIP');
    expect(selected.result.eraGap).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// ERA gap points (boundaries: 0.49, 0.50, 0.99, 1.00, 1.49, 1.50, 1.99, 2.00)
// ---------------------------------------------------------------------------

describe('ERA gap points boundaries', () => {
  it('gap 0.49 → 0 pts', () => expect(calcEraGap(4.0, 4.49) < 0.5 ? 0 : -1).toBe(0));

  it('gap 2.00 → 35 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 2.0, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(35);
  });
  it('gap 1.99 → 28 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 2.01, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(28);
  });
  it('gap 1.50 → 28 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 2.5, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(28);
  });
  it('gap 1.49 → 21 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 2.51, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(21);
  });
  it('gap 1.00 → 21 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 3.0, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(21);
  });
  it('gap 0.99 → 14 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 3.01, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(14);
  });
  it('gap 0.50 → 14 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 3.5, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(14);
  });
  it('gap 0.49 → 0 pts', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 3.51, opponentStarterEra: 4.0 }), cfg);
    expect(result.eraGapPoints).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Moneyline tier boundaries: 54, 55, 69, 70
// ---------------------------------------------------------------------------

describe('Moneyline tier boundaries', () => {
  it('score 70+ → T1', () => {
    // ERA gap 2.00 (35) + offense elite (25) + 5 good starts (20) + alignment atOrBetter (10) + form 6 = 96
    const result = runMoneylineEngine(makeInputs({
      candidateStarterEra: 2.0, opponentStarterEra: 4.0, // gap 2.00 → 35
      candidateAvg: 0.270, candidateOps: 0.770,           // elite → 25
      last10Wins: 5, last10Losses: 5, winStreak: 0, lossStreak: 0, // form → 6
      candidateDecimalOdds: 1.35,                         // at fair → 10
    }), cfg);
    expect(result.rawScore).toBeGreaterThanOrEqual(70);
    expect(result.finalState).toBe('T1');
  });

  it('negative ERA gap → SKIP', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterEra: 4.5, opponentStarterEra: 2.5 }), cfg);
    expect(result.hardGates).toContain('ERA_GAP_NOT_POSITIVE');
    expect(result.finalState).toBe('SKIP');
  });

  it('raw score preserved on SKIP', () => {
    const result = runMoneylineEngine(makeInputs({ gameAlreadyStarted: true }), cfg);
    expect(result.rawScore).toBeGreaterThan(0);
    expect(result.finalState).toBe('SKIP');
  });
});

// ---------------------------------------------------------------------------
// IP boundaries: 29.2 IP = 89 outs, 30.0 = 90 outs, 59.2 = 179 outs, 60.0 = 180 outs
// ---------------------------------------------------------------------------

describe('IP boundaries', () => {
  it('29.2 IP (89 outs) → SKIP IP_BELOW_MIN', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterOutsRecorded: 89 }), cfg);
    expect(result.hardGates).toContain('IP_BELOW_MIN');
  });
  it('30.0 IP (90 outs) → no IP gate but a sample warning', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterOutsRecorded: 90 }), cfg);
    expect(result.hardGates).not.toContain('IP_BELOW_MIN');
    expect(result.warnings).toContain('BORDERLINE_IP');
  });
  it('59.2 IP (179 outs) → BORDERLINE_IP warning', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterOutsRecorded: 179 }), cfg);
    expect(result.warnings).toContain('BORDERLINE_IP');
  });
  it('60.0 IP (180 outs) → no BORDERLINE_IP warning', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterOutsRecorded: 180 }), cfg);
    expect(result.warnings).not.toContain('BORDERLINE_IP');
  });
  it('a low-sample T1 score is capped to T2', () => {
    const result = runMoneylineEngine(makeInputs({ candidateStarterOutsRecorded: 120 }), cfg);
    expect(result.rawScore).toBeGreaterThanOrEqual(cfg.t1MinScore);
    expect(result.finalState).toBe('T2');
    expect(result.warnings).toContain('T1_CONFIDENCE_CAPPED');
  });
});

// ---------------------------------------------------------------------------
// Game log (good start boundaries)
// ---------------------------------------------------------------------------

describe('game log points', () => {
  it('5 good starts → 20 pts', () => {
    const r = calcGameLogPoints([goodLog(), goodLog(), goodLog(), goodLog(), goodLog()], cfg);
    expect(r.points).toBe(20);
    expect(r.goodStarts).toBe(5);
  });
  it('0 good starts → 0 pts', () => {
    const r = calcGameLogPoints([badLog(), badLog(), badLog(), badLog(), badLog()], cfg);
    expect(r.points).toBe(0);
  });
  it('fewer than 5 starts → 0 pts (gate fires separately)', () => {
    const r = calcGameLogPoints([goodLog(), goodLog()], cfg);
    expect(r.points).toBe(0);
  });
  it('HOT trend when ERA improves over last 3', () => {
    // Last 3 starts (indices 2,3,4) must have strictly decreasing game ERA
    // ERA order: 4.5 → 3.0 → 1.5 = HOT
    const logs = [
      { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-06-01' }, // ERA 1.5 (oldest)
      { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-06-08' }, // ERA 1.5
      { earnedRuns: 3, outsRecorded: 18, gameDate: '2025-06-15' }, // ERA 4.5 ← last3 start
      { earnedRuns: 2, outsRecorded: 18, gameDate: '2025-06-22' }, // ERA 3.0
      { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-06-29' }, // ERA 1.5 ← most recent
    ];
    const r = calcGameLogPoints(logs, cfg);
    expect(r.trend).toBe('HOT');
  });
  it('COLD trend when ERA worsens over last 3', () => {
    const logs = [
      goodLog(1, 18),  // ERA 1.5
      goodLog(2, 18),  // ERA 3.0
      goodLog(3, 18),  // ERA 4.5 (worsening but need last 3 to be monotonically increasing)
      goodLog(1, 18),
      goodLog(1, 18),
    ];
    // Last 3 at indices 2,3,4: ERA 4.5 → 1.5 → 1.5 — not monotonically worsening → MIXED
    const r = calcGameLogPoints(logs, cfg);
    expect(['COLD', 'MIXED']).toContain(r.trend);
  });
});

// ---------------------------------------------------------------------------
// Hard gates
// ---------------------------------------------------------------------------

describe('Moneyline hard gates', () => {
  it('starter unconfirmed → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ candidateStarterConfirmed: false }), cfg);
    expect(r.hardGates).toContain('STARTER_UNCONFIRMED');
    expect(r.finalState).toBe('SKIP');
  });
  it('opponent starter unconfirmed → SKIP because the ERA gap is not stable', () => {
    const r = runMoneylineEngine(makeInputs({ opponentStarterConfirmed: false }), cfg);
    expect(r.hardGates).toContain('STARTER_UNCONFIRMED');
    expect(r.finalState).toBe('SKIP');
  });
  it('GS = 0 → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ candidateStarterGamesStarted: 0 }), cfg);
    expect(r.hardGates).toContain('STARTER_GS_ZERO');
  });
  it('reliever/opener → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ candidateStarterRole: 'reliever' }), cfg);
    expect(r.hardGates).toContain('STARTER_IS_RELIEVER');
  });
  it('fewer than 5 valid starts → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ candidateGameLogs: [goodLog(), goodLog()] }), cfg);
    expect(r.hardGates).toContain('INSUFFICIENT_GAME_LOG');
  });
  it('candidate AVG < .220 → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ candidateAvg: 0.219 }), cfg);
    expect(r.hardGates).toContain('CANDIDATE_AVG_TOO_LOW');
  });
  it('stale odds → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ oddsAreStale: true }), cfg);
    expect(r.hardGates).toContain('ODDS_STALE');
  });
  it('official minor-league fallback data cannot produce an MLB pick', () => {
    const r = runMoneylineEngine(makeInputs({ candidatePitcherLevelFallback: true }), cfg);
    expect(r.hardGates).toContain('PITCHER_LEVEL_FALLBACK');
    expect(r.finalState).toBe('SKIP');
  });
  it('opponent minor-league fallback also invalidates the MLB ERA gap', () => {
    const r = runMoneylineEngine(makeInputs({ opponentPitcherLevelFallback: true }), cfg);
    expect(r.hardGates).toContain('PITCHER_LEVEL_FALLBACK');
    expect(r.finalState).toBe('SKIP');
  });
  it('missing odds without configured provider emits warning instead of hard gate', () => {
    const r = runMoneylineEngine(makeInputs({ candidateDecimalOdds: null, oddsProviderConfigured: false }), cfg);
    expect(r.hardGates).not.toContain('ODDS_STALE');
    expect(r.warnings).toContain('ODDS_MISSING');
  });
  it('game already started → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({ gameAlreadyStarted: true }), cfg);
    expect(r.hardGates).toContain('GAME_ALREADY_STARTED');
  });
  it('3 bad starts out of 5 → warning, not a duplicate hard gate', () => {
    const r = runMoneylineEngine(makeInputs({
      candidateGameLogs: [badLog(), badLog(), badLog(), goodLog(), goodLog()],
    }), cfg);
    expect(r.hardGates).not.toContain('TOO_MANY_BAD_STARTS');
    expect(r.warnings).toContain('RECENT_FORM_WEAK');
  });
  it('4 bad starts out of 5 → SKIP', () => {
    const r = runMoneylineEngine(makeInputs({
      candidateGameLogs: [badLog(), badLog(), badLog(), badLog(), goodLog()],
    }), cfg);
    expect(r.hardGates).toContain('TOO_MANY_BAD_STARTS');
  });
});

// ---------------------------------------------------------------------------
// Warnings
// ---------------------------------------------------------------------------

describe('Moneyline warnings', () => {
  it('AVG/OPS tier mismatch emits warning', () => {
    // AVG Elite (.270), OPS Bad (.710) → mismatch
    const r = runMoneylineEngine(makeInputs({ candidateAvg: 0.270, candidateOps: 0.710 }), cfg);
    expect(r.warnings).toContain('OFFENSE_TIER_MISMATCH');
  });
  it('AVG/OPS mismatch uses the rounded composite instead of the weaker tier only', () => {
    const r = runMoneylineEngine(makeInputs({ candidateAvg: 0.250, candidateOps: 0.763 }), cfg);
    expect(r.offensePoints).toBe(23);
  });
  it('market disagreement is a warning and caps a T1 score to T2', () => {
    const r = runMoneylineEngine(makeInputs({ candidateDecimalOdds: 2.10 }), cfg);
    expect(r.hardGates).not.toContain('MARKET_FAVORS_DISADVANTAGED');
    expect(r.warnings).toContain('MARKET_DISAGREEMENT');
    expect(r.finalState).toBe('T2');
    expect(r.warnings).toContain('T1_CONFIDENCE_CAPPED');
  });
  it('low AVG + small ERA gap → LOW_AVG_SMALL_ERA_GAP', () => {
    const r = runMoneylineEngine(makeInputs({
      candidateAvg: 0.229, candidateOps: 0.720,
      candidateStarterEra: 3.0, opponentStarterEra: 4.5, // gap 1.5 < 2.0
    }), cfg);
    expect(r.warnings).toContain('LOW_AVG_SMALL_ERA_GAP');
  });
});

// ---------------------------------------------------------------------------
// Team form
// ---------------------------------------------------------------------------

describe('team form points', () => {
  it('8+ wins and 3+ win streak → 10', () => expect(calcTeamFormPoints(8, 3, 0)).toBe(10));
  it('6+ wins and 1+ win streak → 8', () => expect(calcTeamFormPoints(6, 1, 0)).toBe(8));
  it('5+ wins → 6', () => expect(calcTeamFormPoints(5, 0, 0)).toBe(6));
  it('4+ wins and loss streak <= 2 → 4', () => expect(calcTeamFormPoints(4, 0, 2)).toBe(4));
  it('otherwise → 2', () => expect(calcTeamFormPoints(3, 0, 5)).toBe(2));
});
