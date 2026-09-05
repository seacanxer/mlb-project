/**
 * lib/utils/odds.ts
 *
 * Odds conversion utilities.
 * All calculations use full precision; round only at the display layer.
 */

export class OddsConversionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OddsConversionError';
  }
}

/**
 * Convert American odds to decimal odds.
 * Negative American: decimal = 1 + 100 / abs(american)
 * Positive American: decimal = 1 + american / 100
 */
export function americanToDecimal(american: number): number {
  if (american === 0) throw new OddsConversionError('American odds cannot be 0');
  if (american < 0) {
    return 1 + 100 / Math.abs(american);
  }
  return 1 + american / 100;
}

/**
 * Convert decimal odds to American odds.
 */
export function decimalToAmerican(decimal: number): number {
  if (decimal < 1) throw new OddsConversionError('Decimal odds must be >= 1');
  if (decimal === 1) return -Infinity;
  if (decimal >= 2) {
    return Math.round((decimal - 1) * 100);
  }
  return Math.round(-100 / (decimal - 1));
}

/**
 * Compute implied probability from decimal odds.
 * impliedProbability = 1 / decimalOdds
 */
export function impliedProbability(decimal: number): number {
  if (decimal <= 0) throw new OddsConversionError('Decimal odds must be positive');
  return 1 / decimal;
}

/** Remove the bookmaker margin from a complete two-way decimal market. */
export function twoWayNoVigProbabilities(
  firstDecimal: number | null,
  secondDecimal: number | null,
): { first: number | null; second: number | null; overround: number | null } {
  if (
    firstDecimal === null || secondDecimal === null ||
    !Number.isFinite(firstDecimal) || !Number.isFinite(secondDecimal) ||
    firstDecimal <= 1 || secondDecimal <= 1
  ) return { first: null, second: null, overround: null };

  const firstRaw = 1 / firstDecimal;
  const secondRaw = 1 / secondDecimal;
  const total = firstRaw + secondRaw;
  return {
    first: firstRaw / total,
    second: secondRaw / total,
    overround: total - 1,
  };
}

/**
 * Parse an odds string that could be American ("-145", "+125") or decimal ("1.69").
 * Returns decimal odds always.
 */
export function parseOddsToDecimal(raw: string): number {
  const trimmed = raw.trim();
  const num = parseFloat(trimmed);
  if (isNaN(num)) throw new OddsConversionError(`Cannot parse odds: "${raw}"`);

  // Detect format: if starts with + or -, or integer >= 100 / <= -100 → American
  if (trimmed.startsWith('+') || trimmed.startsWith('-')) {
    return americanToDecimal(num);
  }
  // Pure decimal: value like 1.85 (>= 1.01 and no sign prefix)
  if (num >= 1.01) {
    return num;
  }
  throw new OddsConversionError(`Ambiguous odds value: "${raw}"`);
}

/**
 * Compute price difference: candidate decimal - fair decimal.
 * Positive means candidate is longer (worse value) than fair.
 */
export function priceDifference(candidateDecimal: number, fairDecimal: number): number {
  return candidateDecimal - fairDecimal;
}
