/** Read-only retrospective check of the MLB pick review order. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { priorityForPick, type PickPriority } from '../lib/engine/pickPriority';

interface SettledPick {
  gameDate: string;
  tier: string;
  selectedSide: string;
  status: string;
  profitUnits: number;
}

const snapshotPath = resolve(process.argv[2] ?? 'reports/mlb_tracker_snapshot.json');
const holdoutStart = process.argv[3] ?? '2026-09-15';
const snapshot = JSON.parse(readFileSync(snapshotPath, 'utf8')) as { settled: SettledPick[] };
const settled = snapshot.settled.filter((pick) => pick.status === 'win' || pick.status === 'loss');

function summarize(picks: SettledPick[]) {
  const wins = picks.filter((pick) => pick.status === 'win').length;
  const profit = picks.reduce((sum, pick) => sum + pick.profitUnits, 0);
  return {
    picks: picks.length,
    wins,
    winRatePct: picks.length ? Number((wins / picks.length * 100).toFixed(1)) : null,
    profitUnits: Number(profit.toFixed(2)),
    roiPct: picks.length ? Number((profit / picks.length * 100).toFixed(1)) : null,
  };
}

const result = {
  snapshot: snapshotPath,
  holdoutStart,
  note: 'Retrospective ranking only. All historical selections remain visible; this is not a forecast of future win rate.',
  periods: {} as Record<string, Record<string, ReturnType<typeof summarize>>>,
};

for (const [name, picks] of [
  ['earlier', settled.filter((pick) => pick.gameDate < holdoutStart)],
  ['later', settled.filter((pick) => pick.gameDate >= holdoutStart)],
] as const) {
  const groups: Record<string, ReturnType<typeof summarize>> = { all: summarize(picks) };
  for (const priority of ['primary', 'review', 'caution', 'none'] as PickPriority[]) {
    groups[priority] = summarize(picks.filter((pick) => priorityForPick(pick.tier, pick.selectedSide) === priority));
  }
  const total = groups.primary.picks + groups.review.picks + groups.caution.picks + groups.none.picks;
  if (total !== groups.all.picks) throw new Error(`Ranking lost ${groups.all.picks - total} picks in ${name}`);
  result.periods[name] = groups;
}

console.log(JSON.stringify(result, null, 2));
