import { describe, expect, it } from 'vitest';
import { closingPrice, summarizePerformance } from '@/lib/analytics/performance';

describe('summarizePerformance', () => {
  it('uses flat one-unit returns for every priced market', () => {
    const result = summarizePerformance([
      { outcome: 'win', marketPrice: 1.8, closingPrice: 1.7 },
      { outcome: 'loss', marketPrice: 2.1, closingPrice: 2.2 },
      { outcome: 'push', marketPrice: 1.9, closingPrice: 1.9 },
      { outcome: 'void', marketPrice: 1.9, closingPrice: 1.9 },
    ]);

    expect(result).toMatchObject({
      wins: 1,
      losses: 1,
      pushes: 1,
      voids: 1,
      unitsStaked: 3,
      profitUnits: -0.2,
      roiPct: -6.67,
      pricedSettlements: 3,
      missingPrice: 0,
      closingPriceCoverage: 3,
    });
  });

  it('reports missing prices instead of inventing ROI', () => {
    const result = summarizePerformance([{ outcome: 'win', marketPrice: null }]);
    expect(result.missingPrice).toBe(1);
    expect(result.roiPct).toBeNull();
  });
});

describe('closingPrice', () => {
  it('uses the final valid quote at or before first pitch', () => {
    const firstPitch = new Date('2026-09-05T18:00:00Z');
    const snapshots = [
      { retrievedAt: new Date('2026-09-05T15:00:00Z'), moneylineHome: 2, moneylineAway: 1.8, totalOverDecimal: 1.9, totalUnderDecimal: 1.9 },
      { retrievedAt: new Date('2026-09-05T17:59:00Z'), moneylineHome: 1.85, moneylineAway: 1.95, totalOverDecimal: 1.87, totalUnderDecimal: 1.93 },
      { retrievedAt: new Date('2026-09-05T18:01:00Z'), moneylineHome: 1.7, moneylineAway: 2.1, totalOverDecimal: 1.8, totalUnderDecimal: 2 },
    ];

    expect(closingPrice(snapshots, firstPitch, 'home')).toBe(1.85);
    expect(closingPrice(snapshots, firstPitch, 'under')).toBe(1.93);
    expect(closingPrice(snapshots, firstPitch, 'home', new Date('2026-09-05T18:00:00Z'))).toBeNull();
  });
});
