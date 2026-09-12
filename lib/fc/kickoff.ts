/**
 * lib/fc/kickoff.ts
 *
 * THE single WIB formatter for FC pages (brief FR-5: one helper, no second
 * date implementation). Wraps the canonical `formatWIB` from
 * @/lib/utils/timezone with the FC display format
 * "09 Sep 2026 · 22:30 WIB". Accepts engine epoch seconds OR ISO strings.
 */
import { formatWIB } from '@/lib/utils/timezone';

export const KICKOFF_FORMAT = "dd MMM yyyy · HH:mm 'WIB'";

function toDate(ts: number | string | null | undefined): Date | null {
  if (ts === null || ts === undefined) return null;
  if (typeof ts === 'number') {
    if (!Number.isFinite(ts) || ts <= 0) return null;
    // Engine writes seconds; tolerate accidental milliseconds.
    const ms = ts < 1e12 ? ts * 1000 : ts;
    return new Date(ms);
  }
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "09 Sep 2026 · 22:30 WIB" or "—" for null/invalid (never crashes). */
export function formatKickoffWIB(ts: number | string | null | undefined): string {
  const d = toDate(ts);
  if (!d) return '—';
  return formatWIB(d, KICKOFF_FORMAT);
}

/** Countdown "starts in Xh Ym" / "live-ish" / "started". Pure helper (testable). */
export function kickoffCountdown(ts: number | string | null | undefined, nowMs = Date.now()): string {
  const d = toDate(ts);
  if (!d) return '—';
  const diffMs = d.getTime() - nowMs;
  if (diffMs <= 0) return 'started';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `in ${hours}h ${mins % 60}m`;
  return `in ${Math.floor(hours / 24)}d ${hours % 24}h`;
}

/** Engine pick/schedule visibility rule: only future kickoffs (brief DoD). */
export function isFutureKickoff(ts: number | string | null | undefined, nowMs = Date.now()): boolean {
  const d = toDate(ts);
  if (!d) return false;
  return d.getTime() > nowMs;
}
