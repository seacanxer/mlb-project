import { describe, expect, it } from 'vitest';
import { formatKickoffWIB, isFutureKickoff, kickoffCountdown } from '@/lib/fc/kickoff';

describe('fc kickoff helpers (single WIB source, brief FR-5)', () => {
  it('formats epoch seconds as "09 Sep 2026 · 22:30 WIB"', () => {
    // 2026-09-09T15:30:00Z == 22:30 WIB (UTC+7)
    expect(formatKickoffWIB(1788967800)).toBe('09 Sep 2026 · 22:30 WIB');
  });

  it('accepts ISO strings identically', () => {
    expect(formatKickoffWIB('2026-09-09T15:30:00Z')).toBe('09 Sep 2026 · 22:30 WIB');
  });

  it('returns em-dash for null/invalid, never crashes', () => {
    expect(formatKickoffWIB(null)).toBe('—');
    expect(formatKickoffWIB(undefined)).toBe('—');
    expect(formatKickoffWIB(-5)).toBe('—');
    expect(formatKickoffWIB('not-a-date')).toBe('—');
  });

  it('counts down to kickoff deterministically', () => {
    const now = new Date('2026-09-09T10:00:00Z').getTime();
    expect(kickoffCountdown(1788967800, now)).toBe('in 5h 30m');
    expect(kickoffCountdown(now / 1000 + 20 * 60, now)).toBe('in 20m');
    expect(kickoffCountdown(now / 1000 - 60, now)).toBe('started');
    expect(kickoffCountdown(null, now)).toBe('—');
  });

  it('only future kickoffs are visible (brief DoD)', () => {
    const now = new Date('2026-09-09T10:00:00Z').getTime();
    expect(isFutureKickoff(1788967800, now)).toBe(true);
    expect(isFutureKickoff(now / 1000 - 1, now)).toBe(false);
    expect(isFutureKickoff(null, now)).toBe(false);
  });
});
