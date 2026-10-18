import type { ForecastPick } from './types';
const CAPTURE_SKEW_SECONDS = 300;

/** Recheck cached scan recommendations at read time; all values are epoch seconds. */
export function quantFreshnessReasons(pick: ForecastPick, now = Date.now() / 1000): string[] {
  const q = pick.quant;
  if (!q || q.schema_version !== 'fc-quant-v1') return ['QUANT_RESCAN_REQUIRED'];
  const reasons: string[] = [];
  const captured = Number(pick.quote_captured_at);
  if (!Number.isFinite(captured) || captured <= 0 || now - captured < 0 || now - captured > 300) reasons.push('QUOTE_EXPIRED');
  if (!Number.isFinite(pick.start_ts) || now >= pick.start_ts - 60) reasons.push('KICKOFF_TOO_CLOSE');
  const ref = q.reference_evidence;
  if (!ref || ref.freshness_status !== 'verified' ||
      !Number.isFinite(ref.captured_at) || !Number.isFinite(ref.source_updated_at) ||
      ref.source_updated_at <= 0 || ref.source_updated_at > ref.captured_at ||
      now - ref.captured_at < 0 || now - ref.captured_at > 900 ||
      now - ref.source_updated_at < 0 || now - ref.source_updated_at > 900 ||
      Math.abs(ref.captured_at - captured) > CAPTURE_SKEW_SECONDS) reasons.push('REFERENCE_EVIDENCE_UNAVAILABLE');
  return reasons;
}

export function isActionable(pick: ForecastPick, now = Date.now() / 1000): boolean {
  const q = pick.quant;
  // The scan writes a quant stub (schema_version/status/decision_source only) on
  // non-value rows, so reason_codes/ev may be absent — a stub can never be actionable.
  const codes = q?.reason_codes ?? [];
  if (!q || q.status !== 'value' || codes.length > 0) return false;
  return Number.isFinite(q.ev) && (q.ev as number) > 0 &&
    Number.isFinite(pick.ev) && (pick.ev ?? 0) > 0 && quantFreshnessReasons(pick, now).length === 0;
}

export function refreshQuant<T extends ForecastPick>(pick: T, now = Date.now() / 1000): T {
  const q = pick.quant;
  if (!q) return pick;
  const reasons = quantFreshnessReasons(pick, now);
  if (!reasons.length) return pick;
  // Stub rows (non-value, written by the compact scan) carry no reason_codes/ev/kelly.
  const codes = q.reason_codes ?? [];
  const kelly = q.kelly;
  return { ...pick, is_value: false, analysis_status: 'forecast', is_top_pick: false,
    selection_status: 'watch', tier: 'watch', decision: 'watch', kelly_pct: 0, suggested_stake: 0,
    gate_reasons: [...new Set([...(pick.gate_reasons ?? []), ...reasons])],
    quant: { ...q, status: (q.ev ?? 0) <= 0 ? 'pass' : 'forecast',
      reason_codes: [...new Set([...codes, ...reasons])],
      kelly: kelly ? { ...kelly, recommended_fraction: 0,
        recommended_units: kelly.bankroll_units == null ? null : 0,
        reason_codes: [...new Set([...kelly.reason_codes, ...reasons])] } : kelly } };
}
