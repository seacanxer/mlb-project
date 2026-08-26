/**
 * lib/utils/innings.ts
 *
 * Baseball innings-pitched normalization.
 * IP notation is NOT decimal: 5.2 IP means 5 innings and 2 outs (17 outs total).
 * The fractional part must be 0, 1, or 2 — never 3 or higher.
 */

export class InningsParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'InningsParseError';
  }
}

/**
 * Convert an innings-pitched string (e.g. "5.2") to total outs.
 * Throws InningsParseError for invalid notation (e.g. "5.3").
 */
export function inningsToOuts(ip: string | number): number {
  const raw = typeof ip === 'number' ? ip : parseFloat(ip);
  if (isNaN(raw)) {
    throw new InningsParseError(`Invalid innings pitched value: "${ip}"`);
  }

  const whole = Math.floor(raw);
  // Use string-based fractional extraction to avoid floating-point noise
  const str = String(typeof ip === 'string' ? ip : ip.toFixed(1));
  const dotIndex = str.indexOf('.');
  const fraction = dotIndex >= 0 ? parseInt(str.slice(dotIndex + 1), 10) : 0;

  if (fraction > 2) {
    throw new InningsParseError(
      `Invalid innings notation "${ip}": fractional outs must be 0, 1, or 2 (got .${fraction})`
    );
  }

  return whole * 3 + fraction;
}

/**
 * Compute ERA from earned runs and outs recorded.
 * ERA = (EarnedRuns * 27) / OutsRecorded
 * Returns Infinity when outsRecorded is 0.
 */
export function computeEra(earnedRuns: number, outsRecorded: number): number {
  if (outsRecorded === 0) return earnedRuns > 0 ? Infinity : 0;
  return (earnedRuns * 27) / outsRecorded;
}

/**
 * Convert total outs back to display innings (e.g. 17 → "5.2").
 */
export function outsToInningsDisplay(outs: number): string {
  const whole = Math.floor(outs / 3);
  const remainder = outs % 3;
  return remainder === 0 ? `${whole}.0` : `${whole}.${remainder}`;
}
