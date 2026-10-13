import { describe, expect, it } from 'vitest';
import { pickClass } from '@/lib/fc/store';
import type { FcPick } from '@/lib/fc/types';

const base = { match: 'A vs B', league: 'L', start_ts: 0, pick: 'Home', odds: 2, probability: 0.5,
  ev: 0.03, conservative_ev: 0.03, is_top_pick: false, selection_status: 'watch', tier: 'watch',
  decision: 'watch', coverage_status: 'full', calibrated_prob: null } as const;

describe('pickClass', () => {
  it('uses the engine class when present', () => {
    expect(pickClass({ ...base, market: '1x2', pick_class: 'reference_only' } as FcPick)).toBe('reference_only');
  });
  it('treats corner/card rows from older scans as display-only', () => {
    expect(pickClass({ ...base, market: 'corners_ou' } as FcPick)).toBe('secondary_display');
    expect(pickClass({ ...base, market: '1x2' } as FcPick)).toBe('value_v5');
  });
});
