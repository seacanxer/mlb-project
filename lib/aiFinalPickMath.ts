export type SettlementOutcome = 'pending' | 'win' | 'loss' | 'push' | 'void';

export function flatUnitProfit(outcome: SettlementOutcome, decimalOdds: number | null): number | null {
  if (outcome === 'pending') return null;
  if (outcome === 'loss') return -1;
  if (outcome === 'push' || outcome === 'void') return 0;
  return decimalOdds != null && decimalOdds > 1 ? Number((decimalOdds - 1).toFixed(4)) : null;
}

export function settlementSummary(picks: Array<{ status: string; profitUnits: number | null }>) {
  const settled = picks.filter((pick) => pick.status !== 'pending');
  const graded = settled.filter((pick) => pick.status === 'win' || pick.status === 'loss');
  const netUnits = settled.reduce((sum, pick) => sum + (pick.profitUnits ?? 0), 0);
  return {
    total: picks.length,
    pending: picks.length - settled.length,
    settled: settled.length,
    wins: picks.filter((pick) => pick.status === 'win').length,
    losses: picks.filter((pick) => pick.status === 'loss').length,
    pushes: picks.filter((pick) => pick.status === 'push').length,
    netUnits: Number(netUnits.toFixed(2)),
    roi: graded.length ? Number(((netUnits / graded.length) * 100).toFixed(2)) : null,
  };
}

export function parlayRecommendations<T extends { decimalOdds: number | null; status: string }>(picks: T[]) {
  const eligible = picks.filter((pick) => pick.decimalOdds != null && pick.decimalOdds > 1 && pick.status === 'pending');
  const definitions = [
    { label: '2-Leg Core', legs: eligible.slice(0, 2) },
    { label: '3-Leg Balanced', legs: eligible.slice(0, 3) },
    { label: '2-Leg Alternate', legs: eligible.length >= 3 ? [eligible[0], eligible[2]] : [] },
  ];
  return definitions
    .filter((row) => row.legs.length === (row.label.startsWith('3-') ? 3 : 2))
    .map((row) => {
      const odds = row.legs.reduce((value, leg) => value * Number(leg.decimalOdds), 1);
      return { ...row, odds, implied: 100 / odds };
    });
}
