/**
 * tests/unit/innings.test.ts
 * Tests for inningsToOuts and computeEra boundary values.
 */

import { describe, it, expect } from 'vitest';
import { inningsToOuts, computeEra, outsToInningsDisplay, InningsParseError } from '@/lib/utils/innings';

describe('inningsToOuts', () => {
  it('5.0 IP → 15 outs', () => expect(inningsToOuts('5.0')).toBe(15));
  it('5.1 IP → 16 outs', () => expect(inningsToOuts('5.1')).toBe(16));
  it('5.2 IP → 17 outs', () => expect(inningsToOuts('5.2')).toBe(17));
  it('rejects 5.3 IP', () => expect(() => inningsToOuts('5.3')).toThrow(InningsParseError));
  it('0.0 IP → 0 outs', () => expect(inningsToOuts('0.0')).toBe(0));
  it('1.2 IP → 5 outs', () => expect(inningsToOuts('1.2')).toBe(5));
  it('9.0 IP → 27 outs', () => expect(inningsToOuts('9.0')).toBe(27));
  it('handles numeric 5.2', () => expect(inningsToOuts(5.2)).toBe(17));
  it('rejects NaN', () => expect(() => inningsToOuts('abc')).toThrow(InningsParseError));
});

describe('computeEra', () => {
  it('standard ERA calculation', () => {
    expect(computeEra(3, 15)).toBeCloseTo(5.4); // 3*27/15 = 5.4
  });
  it('0 outs with runs → Infinity', () => expect(computeEra(1, 0)).toBe(Infinity));
  it('0 outs with 0 runs → 0', () => expect(computeEra(0, 0)).toBe(0));
  it('perfect game ERA', () => expect(computeEra(0, 27)).toBe(0));
  it('GameERA < 4.00 is a good start', () => {
    const era = computeEra(2, 17); // 2*27/17 ≈ 3.18
    expect(era).toBeLessThan(4.0);
  });
  it('GameERA >= 4.00 is not a good start', () => {
    const era = computeEra(2, 10); // 2*27/10 = 5.4
    expect(era).toBeGreaterThanOrEqual(4.0);
  });
});

describe('outsToInningsDisplay', () => {
  it('15 outs → 5.0', () => expect(outsToInningsDisplay(15)).toBe('5.0'));
  it('16 outs → 5.1', () => expect(outsToInningsDisplay(16)).toBe('5.1'));
  it('17 outs → 5.2', () => expect(outsToInningsDisplay(17)).toBe('5.2'));
  it('27 outs → 9.0', () => expect(outsToInningsDisplay(27)).toBe('9.0'));
  it('0 outs → 0.0', () => expect(outsToInningsDisplay(0)).toBe('0.0'));
});
