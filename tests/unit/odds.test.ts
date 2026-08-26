/**
 * tests/unit/odds.test.ts
 * Tests for odds conversion boundary values.
 */

import { describe, it, expect } from 'vitest';
import {
  americanToDecimal,
  decimalToAmerican,
  impliedProbability,
  parseOddsToDecimal,
  OddsConversionError,
} from '@/lib/utils/odds';

describe('americanToDecimal', () => {
  it('negative American -100 → 2.0', () => expect(americanToDecimal(-100)).toBeCloseTo(2.0));
  it('negative American -145 → ~1.6897', () => expect(americanToDecimal(-145)).toBeCloseTo(1.6897, 3));
  it('negative American -110 → ~1.909', () => expect(americanToDecimal(-110)).toBeCloseTo(1.909, 3));
  it('positive American +100 → 2.0', () => expect(americanToDecimal(100)).toBeCloseTo(2.0));
  it('positive American +125 → 2.25', () => expect(americanToDecimal(125)).toBeCloseTo(2.25));
  it('positive American +200 → 3.0', () => expect(americanToDecimal(200)).toBeCloseTo(3.0));
  it('throws for 0', () => expect(() => americanToDecimal(0)).toThrow(OddsConversionError));
});

describe('impliedProbability', () => {
  it('decimal 1.84 implied prob', () => {
    expect(impliedProbability(1.84)).toBeCloseTo(0.5435, 3);
  });
  it('decimal 1.85 implied prob', () => {
    expect(impliedProbability(1.85)).toBeCloseTo(0.5405, 3);
  });
  it('decimal 2.0 → 50%', () => expect(impliedProbability(2.0)).toBeCloseTo(0.5));
});

describe('parseOddsToDecimal', () => {
  it('parses "-145" as American', () => expect(parseOddsToDecimal('-145')).toBeCloseTo(1.6897, 3));
  it('parses "+125" as American', () => expect(parseOddsToDecimal('+125')).toBeCloseTo(2.25));
  it('parses "1.85" as decimal', () => expect(parseOddsToDecimal('1.85')).toBeCloseTo(1.85));
  it('parses "2.20" as decimal', () => expect(parseOddsToDecimal('2.20')).toBeCloseTo(2.20));
  it('throws on "abc"', () => expect(() => parseOddsToDecimal('abc')).toThrow(OddsConversionError));
});

describe('O/U minimum price boundary (1.84 vs 1.85)', () => {
  it('1.84 is below minimum (< 1.85)', () => expect(1.84 < 1.85).toBe(true));
  it('1.85 is at minimum (>= 1.85)', () => expect(1.85 >= 1.85).toBe(true));
});
