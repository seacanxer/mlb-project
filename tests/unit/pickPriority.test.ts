import { describe, expect, it } from 'vitest';
import { priorityForGame, priorityForPick } from '@/lib/engine/pickPriority';

describe('MLB daily pick review order', () => {
  it('keeps an available T1 ahead of weaker cohorts while retaining their labels', () => {
    expect(priorityForPick('T1', 'home')).toBe('primary');
    expect(priorityForPick('T2', 'away')).toBe('review');
    expect(priorityForPick('T2', 'home')).toBe('caution');
    expect(priorityForPick('UNDER_RISKY', 'under')).toBe('caution');
    expect(priorityForGame('T2', 'home', 'OVER_RISKY')).toBe('review');
  });
});
