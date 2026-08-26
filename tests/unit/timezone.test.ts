import { describe, expect, it } from 'vitest';
import { formatWIB, gameDate, mlbScheduleDate } from '@/lib/utils/timezone';

describe('MLB slate date versus WIB display date', () => {
  it('keeps an evening US game on the MLB date while WIB rolls to next day', () => {
    const firstPitch = '2026-08-25T01:40:00Z';
    expect(mlbScheduleDate(firstPitch)).toBe('2026-08-24');
    expect(gameDate(firstPitch)).toBe('2026-08-25');
    expect(formatWIB(firstPitch, 'dd/MM HH:mm')).toBe('25/08 08:40');
  });

  it('uses New York date instead of UTC for the default MLB calendar', () => {
    const afterUtcMidnight = '2026-08-25T00:30:00Z';
    expect(mlbScheduleDate(afterUtcMidnight)).toBe('2026-08-24');
  });
});
