/**
 * lib/config/modelConfig.ts
 *
 * Default versioned configuration for Moneyline v2.1 and O/U v2.3.
 * All thresholds live here — never buried in calculation code.
 */

export interface EraGapBand {
  minGap: number; // inclusive
  maxGap: number | null; // null means infinity
  points: number;
}

export interface OffenseTier {
  label: string;
  minAvg: number;
  maxAvg: number | null;
  minOps: number;
  maxOps: number | null;
  points: number;
}

export interface MarketAlignmentAnchor {
  minGap: number;
  maxGap: number | null;
  fairDecimal: number;
}

export interface MoneylineConfig {
  // ERA gap points table (descending order, first match wins)
  eraGapBands: EraGapBand[];
  // Offense tiers (Elite → Terrible)
  offenseTiers: OffenseTier[];
  // Fair-price anchors for market alignment
  marketAlignmentAnchors: MarketAlignmentAnchor[];
  // Tier thresholds
  t1MinScore: number;
  t2MinScore: number;
  // Hard skip constants
  minSeasonIp: number;          // below this → SKIP
  minWarnIp: number;            // below this → warning
  minGoodStartsRequired: number; // must have this many valid starts
  minCandidateAvg: number;       // below this → SKIP
  maxBadStartsAllowed: number;   // >= this many bad starts → SKIP
  maxT1DecimalOdds: number;      // higher prices may qualify only for T2
  // Market alignment scoring
  alignmentPoints: {
    atOrBetter: number;
    diff0to20: number;
    diff20to30: number;
    diffOver30: number;
  };
  // Freshness windows (hours)
  teamStatsStaleHours: number;
  bullpenStaleHours: number;
  oddsStaleHours: number;
}

export interface OUConfig {
  // Offense baseline RPG
  offenseBaseline: number;
  offenseWeight: number;
  pitchingWeight: number;
  parkWeight: number;
  clampMin: number;
  clampMax: number;
  // Gap thresholds
  strongGapMin: number;
  riskyGapMin: number;
  // Minimum price
  minSelectedPrice: number;
  // Freshness
  oddsStaleHours: number;
}

/**
 * O/U v3 is intentionally separate from v2.3. These are transparent priors
 * for an experimental model; they are not claimed to be backtest-optimised.
 */
export interface OUV3Config {
  version: '3.1.0';
  starterSeasonWeight: number;
  starterRecentWeight: number;
  offenseFactorWeight: number;
  marketPriorWeight: number;
  authoritativeParkReliability: number;
  fallbackParkReliability: number;
  minStarterIpPerGame: number;
  maxStarterIpPerGame: number;
  minSeasonIp: number;
  warnSeasonIp: number;
  minSelectedPrice: number;
  oddsStaleHours: number;
  leanGapMin: number;
  riskyGapMin: number;
  strongGapMin: number;
  minRiskyDataQuality: number;
  minStrongDataQuality: number;
  lineMoveWarn: number;
  lineMoveHard: number;
  modelMarketOutlierMax: number;
}

/**
 * The single active totals model. Older OU_V2_3 and OU_V3 records remain in
 * the database as immutable history, but the pipeline no longer publishes
 * parallel totals formulas.
 */
export interface OUTotalsConfig {
  version: '4.0.0';
  starterSeasonWeight: number;
  starterRecentWeight: number;
  offenseProjectionWeight: number;
  marketPriorWeight: number;
  whipBaseline: number;
  whipRunsWeight: number;
  maxWhipRunAdjustment: number;
  authoritativeParkReliability: number;
  fallbackParkReliability: number;
  minStarterIpPerGame: number;
  maxStarterIpPerGame: number;
  minSeasonIp: number;
  warnSeasonIp: number;
  minSelectedPrice: number;
  oddsStaleHours: number;
  leanGapMin: number;
  riskyGapMin: number;
  strongGapMin: number;
  minRiskyDataQuality: number;
  minStrongDataQuality: number;
  lineMoveWarn: number;
  lineMoveHard: number;
  modelMarketOutlierMax: number;
}

export interface AppModelConfig {
  version: string;
  createdAt: string;
  moneyline: MoneylineConfig;
  ou: OUConfig;
}

// ---------------------------------------------------------------------------
// Default configuration v2.0.0
// ---------------------------------------------------------------------------

export const DEFAULT_CONFIG: AppModelConfig = {
  version: '2.1.0',
  createdAt: new Date().toISOString(),

  moneyline: {
    eraGapBands: [
      { minGap: 2.0, maxGap: null, points: 35 },
      { minGap: 1.5, maxGap: 2.0, points: 28 },
      { minGap: 1.0, maxGap: 1.5, points: 21 },
      { minGap: 0.5, maxGap: 1.0, points: 14 },
      { minGap: 0.0, maxGap: 0.5, points: 0 },
    ],
    offenseTiers: [
      { label: 'Elite',   minAvg: 0.260, maxAvg: null,  minOps: 0.760, maxOps: null,  points: 25 },
      { label: 'Good',    minAvg: 0.250, maxAvg: 0.260, minOps: 0.730, maxOps: 0.760, points: 20 },
      { label: 'Average', minAvg: 0.240, maxAvg: 0.250, minOps: 0.720, maxOps: 0.730, points: 15 },
      { label: 'Bad',     minAvg: 0.230, maxAvg: 0.240, minOps: 0.700, maxOps: 0.720, points: 10 },
      { label: 'Terrible', minAvg: 0.0, maxAvg: 0.230, minOps: 0.0,   maxOps: 0.700, points: 5 },
    ],
    marketAlignmentAnchors: [
      { minGap: 3.0, maxGap: null, fairDecimal: 1.35 },
      { minGap: 2.0, maxGap: 3.0, fairDecimal: 1.50 },
      { minGap: 1.0, maxGap: 2.0, fairDecimal: 1.65 },
    ],
    t1MinScore: 70,
    t2MinScore: 55,
    minSeasonIp: 30,
    minWarnIp: 60,
    minGoodStartsRequired: 5,
    minCandidateAvg: 0.220,
    maxBadStartsAllowed: 4,
    maxT1DecimalOdds: 2.0,
    alignmentPoints: {
      atOrBetter: 10,
      diff0to20: 8,
      diff20to30: 6,
      diffOver30: 4,
    },
    teamStatsStaleHours: 24,
    bullpenStaleHours: 24,
    oddsStaleHours: 4,
  },

  ou: {
    offenseBaseline: 4.1,
    offenseWeight: 0.60,
    pitchingWeight: 0.50,
    parkWeight: 2.5,
    clampMin: -3.0,
    clampMax: 3.0,
    strongGapMin: 0.75,
    riskyGapMin: 0.50,
    minSelectedPrice: 1.85,
    oddsStaleHours: 4,
  },
};

export const DEFAULT_OU_V3_CONFIG: OUV3Config = {
  version: '3.1.0',
  starterSeasonWeight: 0.75,
  starterRecentWeight: 0.25,
  offenseFactorWeight: 0.50,
  marketPriorWeight: 0.60,
  authoritativeParkReliability: 0.75,
  fallbackParkReliability: 0.35,
  minStarterIpPerGame: 4.5,
  maxStarterIpPerGame: 6.5,
  minSeasonIp: 60,
  warnSeasonIp: 90,
  minSelectedPrice: 1.85,
  oddsStaleHours: 1,
  leanGapMin: 0.30,
  riskyGapMin: 0.50,
  strongGapMin: 0.90,
  minRiskyDataQuality: 70,
  minStrongDataQuality: 80,
  lineMoveWarn: 0.50,
  lineMoveHard: 1.00,
  modelMarketOutlierMax: 2.00,
};

export const DEFAULT_OU_TOTALS_CONFIG: OUTotalsConfig = {
  version: '4.0.0',
  starterSeasonWeight: 0.70,
  starterRecentWeight: 0.30,
  // The independent projection gives equal voice to actual team scoring and
  // opponent pitching. This removes the old structural low-total bias caused
  // by multiplying a pitching-only estimate by a heavily shrunk offense ratio.
  offenseProjectionWeight: 0.50,
  // The market remains a strong prior, but no longer dominates the estimate.
  marketPriorWeight: 0.50,
  whipBaseline: 1.30,
  whipRunsWeight: 0.75,
  maxWhipRunAdjustment: 0.25,
  authoritativeParkReliability: 0.75,
  fallbackParkReliability: 0.35,
  minStarterIpPerGame: 4.5,
  maxStarterIpPerGame: 6.5,
  minSeasonIp: 30,
  warnSeasonIp: 60,
  minSelectedPrice: 1.85,
  oddsStaleHours: 1,
  leanGapMin: 0.25,
  riskyGapMin: 0.40,
  strongGapMin: 0.80,
  minRiskyDataQuality: 70,
  minStrongDataQuality: 85,
  lineMoveWarn: 0.50,
  lineMoveHard: 1.00,
  modelMarketOutlierMax: 2.50,
};

// ---------------------------------------------------------------------------
// Config lookup helpers
// ---------------------------------------------------------------------------

export function getEraGapPoints(gap: number, config: MoneylineConfig): number {
  for (const band of config.eraGapBands) {
    if (gap >= band.minGap && (band.maxGap === null || gap < band.maxGap)) {
      return band.points;
    }
  }
  return 0;
}

export function getOffenseTier(
  avg: number,
  ops: number,
  config: MoneylineConfig
): { avgPoints: number; opsPoints: number; avgLabel: string; opsLabel: string; points: number; mismatch: boolean } {
  const getTier = (value: number, useAvg: boolean) => {
    for (const tier of config.offenseTiers) {
      const min = useAvg ? tier.minAvg : tier.minOps;
      const max = useAvg ? tier.maxAvg : tier.maxOps;
      if (value >= min && (max === null || value < max)) {
        return tier;
      }
    }
    return config.offenseTiers[config.offenseTiers.length - 1];
  };

  const avgTier = getTier(avg, true);
  const opsTier = getTier(ops, false);
  const mismatch = avgTier.label !== opsTier.label;
  // AVG and OPS are correlated but distinct offense signals. Taking only the
  // weaker tier double-penalized a one-band mismatch; use an equal composite
  // and retain the mismatch warning for transparency.
  const points = Math.round((avgTier.points + opsTier.points) / 2);

  return {
    avgPoints: avgTier.points,
    opsPoints: opsTier.points,
    avgLabel: avgTier.label,
    opsLabel: opsTier.label,
    points,
    mismatch,
  };
}

export function getFairDecimal(eraGap: number, config: MoneylineConfig): number | null {
  for (const anchor of config.marketAlignmentAnchors) {
    if (eraGap >= anchor.minGap && (anchor.maxGap === null || eraGap < anchor.maxGap)) {
      return anchor.fairDecimal;
    }
  }
  return null; // gap < 1.00: undefined
}
