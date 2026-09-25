/**
 * lib/fc/parlay.ts — pure label helpers for manual parlay slips and legs.
 *
 * Kept separate from the UI so settlement labels stay unit-testable and the
 * results page can only mirror statuses, never recompute them.
 */
import type { ParlayLeg } from './types';

export type LegOutcome = 'W' | 'L' | 'P' | null;

const OUTCOMES: Record<string, LegOutcome> = { won: 'W', lost: 'L', push: 'P' };

/** Snapshot stores snake_case results ('won'|'lost'|'push'|'pending'). */
export function legOutcome(result: string | null | undefined): LegOutcome {
  if (!result) return null;
  return OUTCOMES[result.toLowerCase()] ?? null;
}

/** Slip status uses the same vocabulary as leg results. */
export function slipOutcome(status: string | null | undefined): LegOutcome {
  return legOutcome(status);
}

export function outcomeChipClass(outcome: LegOutcome): string {
  if (outcome === 'W') return 'chip-fc-win';
  if (outcome === 'L') return 'chip-fc-loss';
  if (outcome === 'P') return 'chip-fc-push';
  return '';
}

export function slipStatusLabel(status: string | null | undefined): string {
  const key = (status ?? '').toLowerCase();
  if (key === 'won') return 'Menang';
  if (key === 'lost') return 'Kalah';
  if (key === 'push') return 'Push';
  if (key === 'pending') return 'Menunggu skor';
  return status || '-';
}

/** Match label for a leg, falling back to "Home vs Away" when match is empty. */
export function legMatchLabel(leg: ParlayLeg): string {
  if (leg.match && leg.match.trim()) return leg.match;
  if (leg.home || leg.away) return `${leg.home ?? '?'} vs ${leg.away ?? '?'}`;
  return '-';
}
