/**
 * lib/utils/timezone.ts
 *
 * Timezone helpers.
 * - All database storage: UTC
 * - All display: Asia/Jakarta (WIB, UTC+7) by default
 * - Source timezone is captured per observation, not assumed
 */

import { formatInTimeZone, toZonedTime, fromZonedTime } from 'date-fns-tz';
import { addDays, format, parseISO } from 'date-fns';

export const DEFAULT_DISPLAY_TZ = process.env.DEFAULT_TIMEZONE ?? 'Asia/Jakarta';
export const UTC_TZ = 'UTC';
export const MLB_SCHEDULE_TZ = 'America/New_York';

/**
 * Format a UTC Date or ISO string for display in WIB (or configured tz).
 */
export function formatWIB(
  date: Date | string,
  fmt: string = 'yyyy-MM-dd HH:mm zzz',
  tz: string = DEFAULT_DISPLAY_TZ
): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return formatInTimeZone(d, tz, fmt);
}

/**
 * Format a UTC Date or ISO string for UTC display.
 */
export function formatUTC(date: Date | string, fmt: string = 'yyyy-MM-dd HH:mm zzz'): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return formatInTimeZone(d, UTC_TZ, fmt);
}

/**
 * Convert a date string in a source timezone to UTC Date.
 * Use this when a provider gives times in a non-UTC timezone.
 */
export function sourceToUtc(dateStr: string, sourceTz: string): Date {
  return fromZonedTime(dateStr, sourceTz);
}

/**
 * Get the "game date" string (YYYY-MM-DD) in a given timezone from a UTC datetime.
 * Important for handling date rollover when a WIB game date differs from ET game date.
 */
export function gameDate(utcDate: Date | string, tz: string = DEFAULT_DISPLAY_TZ): string {
  const d = typeof utcDate === 'string' ? parseISO(utcDate) : utcDate;
  return formatInTimeZone(d, tz, 'yyyy-MM-dd');
}

/** Return today's calendar date in WIB (or another explicit display timezone). */
export function currentDisplayDate(now: Date = new Date(), tz: string = DEFAULT_DISPLAY_TZ): string {
  return formatInTimeZone(now, tz, 'yyyy-MM-dd');
}

/**
 * Shift a date-only value without passing through the host machine timezone.
 * Parsing `YYYY-MM-DD` with `new Date()` can move the visible day on non-UTC hosts.
 */
export function shiftDateOnly(date: string, days: number): string {
  const parsed = parseISO(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) throw new Error(`Invalid date: ${date}`);
  return format(addDays(parsed, days), 'yyyy-MM-dd');
}

/** UTC bounds for one calendar day in the requested timezone. */
export function zonedDayBoundsUtc(date: string, tz: string = DEFAULT_DISPLAY_TZ): { start: Date; end: Date } {
  const nextDate = shiftDateOnly(date, 1);
  return {
    start: fromZonedTime(`${date}T00:00:00`, tz),
    end: fromZonedTime(`${nextDate}T00:00:00`, tz),
  };
}

/**
 * Official MLB schedule date. MLB schedule queries are grouped by the US
 * baseball calendar, while the same first pitch can fall on the next WIB day.
 */
export function mlbScheduleDate(date: Date | string = new Date()): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return formatInTimeZone(d, MLB_SCHEDULE_TZ, 'yyyy-MM-dd');
}

/**
 * Returns true if the given UTC datetime is in the past (game has started).
 */
export function isGameStarted(startTimeUtc: Date | string): boolean {
  const d = typeof startTimeUtc === 'string' ? parseISO(startTimeUtc) : startTimeUtc;
  return d <= new Date();
}

/**
 * Compute the age of an observation in minutes from now.
 */
export function ageMinutes(retrievedAt: Date | string): number {
  const d = typeof retrievedAt === 'string' ? parseISO(retrievedAt) : retrievedAt;
  return Math.floor((Date.now() - d.getTime()) / 60_000);
}

/**
 * Compute the age of an observation in hours from now.
 */
export function ageHours(retrievedAt: Date | string): number {
  return ageMinutes(retrievedAt) / 60;
}
