export type SettledOutcome = 'win' | 'loss' | 'push' | 'void' | 'pending';

export interface PerformanceBet {
  outcome: SettledOutcome | string;
  marketPrice: number | null;
  closingPrice?: number | null;
}

export interface PerformanceSummary {
  wins: number;
  losses: number;
  pushes: number;
  voids: number;
  total: number;
  pricedSettlements: number;
  missingPrice: number;
  unitsStaked: number;
  profitUnits: number;
  roiPct: number | null;
  averageOdds: number | null;
  closingPriceCoverage: number;
  averageClvPct: number | null;
}

function validDecimal(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 1;
}

/**
 * Flat one-unit settlement accounting. Pushes consume one unit of turnover and
 * return it; void bets are excluded because no stake remains at risk.
 */
export function summarizePerformance(bets: PerformanceBet[]): PerformanceSummary {
  let wins = 0;
  let losses = 0;
  let pushes = 0;
  let voids = 0;
  let missingPrice = 0;
  let unitsStaked = 0;
  let profitUnits = 0;
  let oddsTotal = 0;
  let pricedSettlements = 0;
  const clvValues: number[] = [];

  for (const bet of bets) {
    if (bet.outcome === 'win') wins += 1;
    else if (bet.outcome === 'loss') losses += 1;
    else if (bet.outcome === 'push') pushes += 1;
    else if (bet.outcome === 'void') voids += 1;
    else continue;

    if (bet.outcome === 'void') continue;
    if (!validDecimal(bet.marketPrice)) {
      missingPrice += 1;
      continue;
    }

    pricedSettlements += 1;
    unitsStaked += 1;
    oddsTotal += bet.marketPrice;
    if (bet.outcome === 'win') profitUnits += bet.marketPrice - 1;
    else if (bet.outcome === 'loss') profitUnits -= 1;

    if (validDecimal(bet.closingPrice)) {
      // Positive means the locked price beat the closing price.
      clvValues.push((bet.marketPrice / bet.closingPrice - 1) * 100);
    }
  }

  const roundedProfit = Number(profitUnits.toFixed(4));
  return {
    wins,
    losses,
    pushes,
    voids,
    total: wins + losses + pushes + voids,
    pricedSettlements,
    missingPrice,
    unitsStaked,
    profitUnits: roundedProfit,
    roiPct: unitsStaked > 0 ? Number((roundedProfit / unitsStaked * 100).toFixed(2)) : null,
    averageOdds: pricedSettlements > 0 ? Number((oddsTotal / pricedSettlements).toFixed(3)) : null,
    closingPriceCoverage: clvValues.length,
    averageClvPct: clvValues.length > 0
      ? Number((clvValues.reduce((sum, value) => sum + value, 0) / clvValues.length).toFixed(2))
      : null,
  };
}

export type PriceSide = 'home' | 'away' | 'over' | 'under' | null;

export interface MarketPriceSnapshot {
  retrievedAt: Date;
  moneylineHome: number | null;
  moneylineAway: number | null;
  totalOverDecimal: number | null;
  totalUnderDecimal: number | null;
}

export function selectedPrice(snapshot: MarketPriceSnapshot | undefined, side: PriceSide): number | null {
  if (!snapshot || !side) return null;
  if (side === 'home') return snapshot.moneylineHome;
  if (side === 'away') return snapshot.moneylineAway;
  if (side === 'over') return snapshot.totalOverDecimal;
  return snapshot.totalUnderDecimal;
}

/** Latest observed quote no later than first pitch. */
export function closingPrice(
  snapshots: MarketPriceSnapshot[],
  firstPitch: Date,
  side: PriceSide,
  after?: Date,
): number | null {
  const snapshot = [...snapshots]
    .filter((item) => (
      item.retrievedAt <= firstPitch
      && (!after || item.retrievedAt >= after)
      && validDecimal(selectedPrice(item, side))
    ))
    .sort((left, right) => right.retrievedAt.getTime() - left.retrievedAt.getTime())[0];
  return selectedPrice(snapshot, side);
}
