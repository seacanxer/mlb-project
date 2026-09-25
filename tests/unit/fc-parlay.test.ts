import { describe, expect, it } from 'vitest';
import { legMatchLabel, legOutcome, outcomeChipClass, slipOutcome, slipStatusLabel } from '@/lib/fc/parlay';
import type { ParlayLeg } from '@/lib/fc/types';

describe('parlay label helpers', () => {
  it('maps snapshot statuses to table glyphs', () => {
    expect(legOutcome('won')).toBe('W');
    expect(legOutcome('lost')).toBe('L');
    expect(legOutcome('push')).toBe('P');
    expect(slipOutcome('won')).toBe('W');
    expect(slipOutcome('lost')).toBe('L');
    expect(slipOutcome('push')).toBe('P');
  });

  it('never invents an outcome for pending or unknown statuses', () => {
    expect(legOutcome('pending')).toBeNull();
    expect(legOutcome(undefined)).toBeNull();
    expect(legOutcome(null)).toBeNull();
    expect(legOutcome('')).toBeNull();
    expect(legOutcome('rain_delay')).toBeNull();
    expect(slipOutcome('pending')).toBeNull();
    expect(slipOutcome(undefined)).toBeNull();
  });

  it('keeps chip classes identical to the settled results table', () => {
    expect(outcomeChipClass('W')).toBe('chip-fc-win');
    expect(outcomeChipClass('L')).toBe('chip-fc-loss');
    expect(outcomeChipClass('P')).toBe('chip-fc-push');
    expect(outcomeChipClass(null)).toBe('');
  });

  it('translates slip status to Indonesian labels without losing pending state', () => {
    expect(slipStatusLabel('pending')).toBe('Menunggu skor');
    expect(slipStatusLabel('won')).toBe('Menang');
    expect(slipStatusLabel('lost')).toBe('Kalah');
    expect(slipStatusLabel('push')).toBe('Push');
    expect(slipStatusLabel(undefined)).toBe('-');
    expect(slipStatusLabel('')).toBe('-');
  });

  it('builds a match label from home/away when the row has no match string', () => {
    const base = { market: 'ou', pick: 'Over 2.5', odds: 1.91 } as ParlayLeg;
    expect(legMatchLabel({ ...base, match: 'Home vs Away' })).toBe('Home vs Away');
    expect(legMatchLabel({ ...base, match: '', home: 'Home', away: 'Away' })).toBe('Home vs Away');
    expect(legMatchLabel({ ...base, home: 'Home' })).toBe('Home vs ?');
    expect(legMatchLabel(base)).toBe('-');
  });
});
