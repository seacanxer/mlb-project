import { describe, expect, it } from 'vitest';
import {
  currentDisplayDate,
  formatWIB,
  gameDate,
  mlbScheduleDate,
  shiftDateOnly,
  zonedDayBoundsUtc,
} from '@/lib/utils/timezone';

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

  it('uses the WIB calendar for the picker date', () => {
    const now = new Date('2026-09-01T18:30:00Z');
    expect(currentDisplayDate(now)).toBe('2026-09-02');
  });

  it('shifts date-only values without host-timezone rollover', () => {
    expect(shiftDateOnly('2026-03-01', -1)).toBe('2026-02-28');
    expect(shiftDateOnly('2026-12-31', 1)).toBe('2027-01-01');
  });

  it('creates exact UTC boundaries for a WIB calendar day', () => {
    const bounds = zonedDayBoundsUtc('2026-09-02');
    expect(bounds.start.toISOString()).toBe('2026-09-01T17:00:00.000Z');
    expect(bounds.end.toISOString()).toBe('2026-09-02T17:00:00.000Z');
  });
});
