/**
 * lib/fc/format.ts
 *
 * FC number formatters (brief FR-5). Single-responsibility helpers with
 * null-safe behaviour: null/NaN → "—", never a render crash.
 * Time formatting reuses the canonical `formatWIB` from
 * @/lib/utils/timezone — no second date implementation (brief FR-5).
 */

export const NULL_GLYPH = '—';

/** Odds: 2–3 decimals (brief FR-5). */
export function formatOdds(odds: number | null | undefined): string {
  if (odds === null || odds === undefined || !Number.isFinite(odds)) return NULL_GLYPH;
  return odds.toFixed(2);
}

/** Profit: "+1.85u" / "−1.00u" (brief FR-5). */
export function formatProfit(profit: number | null | undefined): string {
  if (profit === null || profit === undefined || !Number.isFinite(profit)) return NULL_GLYPH;
  const sign = profit > 0 ? '+' : profit < 0 ? '−' : '';
  return `${sign}${Math.abs(profit).toFixed(2)}u`;
}

/** ROI: 1 decimal + caller decides colour (brief FR-5). */
export function formatRoi(roiPct: number | null | undefined): string {
  if (roiPct === null || roiPct === undefined || !Number.isFinite(roiPct)) return NULL_GLYPH;
  return `${roiPct.toFixed(1)}%`;
}

/** Hit rate / win rate: 1 decimal. */
export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NULL_GLYPH;
  return `${value.toFixed(1)}%`;
}

/** EV as percent with sign, e.g. "+4.20%" (model EV is in units). */
export function formatEv(ev: number | null | undefined): string {
  if (ev === null || ev === undefined || !Number.isFinite(ev)) return NULL_GLYPH;
  const sign = ev > 0 ? '+' : ev < 0 ? '−' : '';
  return `${sign}${(Math.abs(ev) * 100).toFixed(2)}%`;
}

/** Probability 0..1 → "58.5%". */
export function formatProb(prob: number | null | undefined): string {
  if (prob === null || prob === undefined || !Number.isFinite(prob)) return NULL_GLYPH;
  return `${(prob * 100).toFixed(1)}%`;
}

/**
 * calibrated_prob display rule (brief §3/DoD): null must NEVER render as a
 * number. Returns null when there is nothing valid to show so the caller can
 * render "—" or hide the field.
 */
export function formatCalibratedProb(calibrated: number | null | undefined): string | null {
  if (calibrated === null || calibrated === undefined || !Number.isFinite(calibrated)) return null;
  return formatProb(calibrated);
}

/** Colour token for ROI/profit values: positive | negative | neutral. */
export function roiTone(value: number | null | undefined): 'positive' | 'negative' | 'neutral' {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
}
