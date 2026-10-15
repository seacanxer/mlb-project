import { describe, expect, it } from 'vitest';
import { isActionable, refreshQuant } from '@/lib/fc/quant';
import { isValue } from '@/lib/fc/predictions';
import type { ForecastPick } from '@/lib/fc/types';

const now = 1900000000;
const pick: ForecastPick = {
  match: 'Home vs Away', league: 'L', market: '1x2', pick: 'Home',
  conservative_ev: .2, is_top_pick: false, selection_status: 'watch', tier: 'watch',
  decision: 'watch', coverage_status: 'full', calibrated_prob: null,
  start_ts: now + 7200, odds: 2, probability: .6, ev: .2, quote_captured_at: now - 10,
  quant: { schema_version: 'fc-quant-v1', status: 'value', reason_codes: [], ev: .2,
    decision_source: 'sharp', market_no_vig_probability: .5, model_positive_payout_probability: .6,
    decision_price_probability: .6, positive_payout_probability: .6, push_probability: 0,
    reference_probability: .6, primary_source_time_status: 'unknown', fair_odds: 1 / .6, edge_probability: .1,
    reference_evidence: { observation_id: 'obs', bookmaker: 'pinnacle', decimal_odds: 1.67,
      captured_at: now - 10, source_updated_at: now - 12, freshness_status: 'verified' },
    kelly: { mode: 'recommendation_only', full_fraction: .2, fractional_multiplier: .25, cap_fraction: .02,
      recommended_fraction: .02, recommended_units: 2, bankroll_units: 100, reason_codes: [] } },
};

describe('FC recommendations expire independently of static scanner files', () => {
  it('accepts fresh evidence but refuses a stale source or primary capture', () => {
    expect(isActionable(pick, now)).toBe(true);
    expect(isActionable(pick, now + 400)).toBe(false);
    const stale = structuredClone(pick);
    stale.quant!.reference_evidence!.source_updated_at = now - 3600;
    expect(isActionable(stale, now)).toBe(false);
    expect(isActionable({ ...pick, quote_captured_at: now + 1 }, now)).toBe(false);
  });
  it('zeroes recommended stake in a copy while preserving audit evidence', () => {
    const result = refreshQuant(pick, now + 400);
    expect(result.quant!.status).toBe('forecast');
    expect(result.quant!.kelly.recommended_fraction).toBe(0);
    expect(result.quant!.kelly.recommended_units).toBe(0);
    expect(pick.quant!.kelly.recommended_units).toBe(2);
    expect(result.gate_reasons).toContain('QUOTE_EXPIRED');
  });
  it('never promotes negative EV or legacy confidence to actionable value', () => {
    expect(isActionable({ ...pick, ev: -.01 }, now)).toBe(false);
    expect(isActionable({ ...pick, quant: undefined }, now)).toBe(false);
    expect(isValue({ ...pick, quant: undefined, ev: -.01, analysis_status: 'value_candidate' })).toBe(false);
    expect(isValue({ ...pick, quant: undefined, ev: .1, analysis_status: 'value_candidate' })).toBe(false);
  });
});
