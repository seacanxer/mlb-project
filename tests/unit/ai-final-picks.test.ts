import { describe, expect, it } from 'vitest';
import { flatUnitProfit, parlayRecommendations, settlementSummary } from '@/lib/aiFinalPickMath';

describe('AI final pick tracking', () => {
  it('grades flat one-unit outcomes', () => {
    expect(flatUnitProfit('win', 1.9)).toBe(0.9);
    expect(flatUnitProfit('loss', 3.5)).toBe(-1);
    expect(flatUnitProfit('push', 1.9)).toBe(0);
    expect(flatUnitProfit('pending', 1.9)).toBeNull();
  });

  it('calculates realized ROI from wins and losses only', () => {
    expect(settlementSummary([
      { status: 'win', profitUnits: 0.9 },
      { status: 'loss', profitUnits: -1 },
      { status: 'push', profitUnits: 0 },
      { status: 'pending', profitUnits: null },
    ])).toMatchObject({ settled: 3, netUnits: -0.1, roi: -5 });
  });

  it('builds parlays only from pending picks with valid odds', () => {
    const rows = parlayRecommendations([
      { id: 'a', status: 'pending', decimalOdds: 1.8 },
      { id: 'b', status: 'pending', decimalOdds: 2 },
      { id: 'c', status: 'win', decimalOdds: 1.9 },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].odds).toBeCloseTo(3.6);
  });
});
