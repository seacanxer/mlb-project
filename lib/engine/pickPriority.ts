/**
 * Presentation order for MLB picks. Every model signal remains available;
 * this is a review order based on the settled cohorts, not a probability,
 * staking recommendation, or new eligibility gate.
 */
export type PickPriority = 'primary' | 'review' | 'caution' | 'none';

const ORDER: Record<PickPriority, number> = {
  primary: 0,
  review: 1,
  caution: 2,
  none: 3,
};

export function priorityForPick(state?: string | null, side?: string | null): PickPriority {
  if (state === 'T1') return 'primary';
  if (state === 'T2') return side === 'away' ? 'review' : 'caution';
  if (state === 'UNDER_RISKY' || state === 'UNDER_LEAN') return 'caution';
  if (state === 'OVER_RISKY' || state === 'OVER_LEAN' ||
      state === 'OVER_STRONG_GAP' || state === 'UNDER_STRONG_GAP') return 'review';
  return 'none';
}

export function priorityForGame(mlState?: string | null, mlSide?: string | null, ouState?: string | null): PickPriority {
  const ml = priorityForPick(mlState, mlSide);
  const ou = priorityForPick(ouState);
  return ORDER[ml] <= ORDER[ou] ? ml : ou;
}

export function priorityOrder(priority: PickPriority): number {
  return ORDER[priority];
}

export const PRIORITY_LABEL: Record<PickPriority, string> = {
  primary: 'T1 · prioritas',
  review: 'Bandingkan',
  caution: 'Perlu kehati-hatian',
  none: 'Belum ada pick',
};
