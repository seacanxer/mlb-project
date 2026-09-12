import { describe, expect, it } from 'vitest';
import fixture from '../fixtures/fc-v2-contract.json';
import cases from '../fixtures/fc-v2-cases.json';
import { DEFAULT_V2_CAPABILITIES, snapshotSchema } from '@/lib/fc/contracts-v2';

describe('isolated v2 contract shared vectors', () => {
  for (const vector of cases) {
    it(vector.name, () => {
      const input = structuredClone(fixture);
      for (const [path, value] of vector.changes) {
        const keys = String(path).split('.');
        let target = input as unknown as Record<string, unknown>;
        for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
        target[keys[keys.length - 1]] = value;
      }
      expect(snapshotSchema.safeParse(input).success).toBe(vector.valid);
    });
  }
  it('defaults do not enable official picks', () => {
    expect(DEFAULT_V2_CAPABILITIES.official_enabled).toBe(false);
    expect(Object.isFrozen(DEFAULT_V2_CAPABILITIES)).toBe(true);
  });
  it.each([NaN, Infinity, -Infinity])('rejects non-finite price %s', decimal_odds => {
    expect(snapshotSchema.safeParse({ ...fixture, quote: { ...fixture.quote, decimal_odds } }).success).toBe(false);
  });
});
