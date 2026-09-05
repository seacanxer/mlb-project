import { describe, expect, it } from 'vitest';
import { isOfficialForecastState } from '@/lib/engine/forecast';

describe('official forecast policy', () => {
  it('tracks only T1 and strong totals as official picks', () => {
    expect(isOfficialForecastState('T1')).toBe(true);
    expect(isOfficialForecastState('OVER_STRONG_GAP')).toBe(true);
    expect(isOfficialForecastState('UNDER_STRONG_GAP')).toBe(true);
  });

  it('keeps T2, risky and lean signals out of official settlement', () => {
    for (const state of ['T2', 'OVER_RISKY', 'UNDER_RISKY', 'OVER_LEAN', 'UNDER_LEAN', 'NO_BET']) {
      expect(isOfficialForecastState(state)).toBe(false);
    }
  });
});
