import { describe, expect, it } from 'vitest';
import { isOfficialForecastState } from '@/lib/engine/forecast';

describe('official forecast policy', () => {
  it('tracks all approved forecast states from the current policy', () => {
    for (const state of ['T1', 'T2', 'OVER_STRONG_GAP', 'UNDER_STRONG_GAP', 'OVER_LEAN', 'UNDER_LEAN', 'OVER_RISKY', 'UNDER_RISKY']) {
      expect(isOfficialForecastState(state)).toBe(true);
    }
  });

  it('keeps unapproved states out of official settlement', () => {
    for (const state of ['NO_BET', 'SKIP', 'UNKNOWN']) {
      expect(isOfficialForecastState(state)).toBe(false);
    }
  });
});
