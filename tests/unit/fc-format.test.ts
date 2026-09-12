import { describe, expect, it } from 'vitest';
import {
  formatCalibratedProb,
  formatEv,
  formatOdds,
  formatProb,
  formatProfit,
  formatRoi,
  roiTone,
} from '@/lib/fc/format';

describe('fc number formatters (brief FR-5)', () => {
  it('formats odds with 2 decimals', () => {
    expect(formatOdds(1.9)).toBe('1.90');
    expect(formatOdds(2.755)).toBe('2.75'); // toFixed, no hidden rounding-up in UI
  });

  it('formats profit with sign + unit', () => {
    expect(formatProfit(1.85)).toBe('+1.85u');
    expect(formatProfit(-1)).toBe('−1.00u');
    expect(formatProfit(0)).toBe('0.00u');
  });

  it('formats ROI with 1 decimal', () => {
    expect(formatRoi(12.34)).toBe('12.3%');
    expect(formatRoi(-4)).toBe('-4.0%');
    expect(formatRoi(0)).toBe('0.0%');
  });

  it('formats EV as signed percent', () => {
    expect(formatEv(0.042)).toBe('+4.20%');
    expect(formatEv(-0.01)).toBe('−1.00%');
  });

  it('formats probability 0..1 as percent', () => {
    expect(formatProb(0.585)).toBe('58.5%');
  });

  it('never renders null/NaN as a number', () => {
    expect(formatOdds(null)).toBe('—');
    expect(formatOdds(NaN)).toBe('—');
    expect(formatProfit(undefined)).toBe('—');
    expect(formatRoi(null)).toBe('—');
    expect(formatEv(null)).toBe('—');
    expect(formatProb(undefined)).toBe('—');
  });

  it('never renders calibrated_prob null as a number (DoD)', () => {
    expect(formatCalibratedProb(null)).toBeNull();
    expect(formatCalibratedProb(undefined)).toBeNull();
    expect(formatCalibratedProb(0.61)).toBe('61.0%');
  });

  it('classifies ROI tone incl. zero/push as neutral', () => {
    expect(roiTone(0.5)).toBe('positive');
    expect(roiTone(-0.5)).toBe('negative');
    expect(roiTone(0)).toBe('neutral');
    expect(roiTone(null)).toBe('neutral');
    expect(roiTone(NaN)).toBe('neutral');
  });
});
