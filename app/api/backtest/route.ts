// app/api/backtest/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import {
  closingPrice,
  summarizePerformance,
  type PerformanceBet,
  type PriceSide,
} from '@/lib/analytics/performance';

export const dynamic = 'force-dynamic';

export async function GET() {
  const settlements = await prisma.settlement.findMany({
    include: {
      forecast: {
        include: {
          modelRun: {
            include: {
              model: true,
              configVersion: true,
              game: { include: { marketSnapshots: true } },
            },
          },
        },
      },
    },
  });

  type PerformanceRow = PerformanceBet & {
    model: string;
    modelId: string;
    version: string;
    tier: string;
    market: 'moneyline' | 'total';
  };

  const rows: PerformanceRow[] = settlements.map((settlement) => {
    const forecast = settlement.forecast;
    const run = forecast.modelRun;
    const side = forecast.selectedSide as PriceSide;
    return {
      outcome: settlement.outcome,
      marketPrice: forecast.marketPrice,
      closingPrice: closingPrice(run.game.marketSnapshots, run.game.startTimeUtc, side, forecast.lockedAt),
      model: run.model.name,
      modelId: run.modelId,
      version: run.configVersion.semver,
      tier: forecast.finalState,
      market: run.modelId.startsWith('OU_') ? 'total' : 'moneyline',
    };
  });

  const byVersion = new Map<string, PerformanceRow[]>();
  const byMarket = new Map<string, PerformanceRow[]>();
  const byTier = new Map<string, PerformanceRow[]>();

  for (const row of rows) {
    const versionKey = `${row.modelId}@${row.version}`;
    byVersion.set(versionKey, [...(byVersion.get(versionKey) ?? []), row]);
    byMarket.set(row.market, [...(byMarket.get(row.market) ?? []), row]);
    byTier.set(row.tier, [...(byTier.get(row.tier) ?? []), row]);
  }

  const aggregate = (entries: Map<string, PerformanceRow[]>, dimension: 'version' | 'market' | 'tier') =>
    [...entries.entries()].map(([key, bets]) => ({
      key,
      ...(dimension === 'version' ? { model: bets[0].model, version: bets[0].version } : {}),
      ...summarizePerformance(bets),
    }));

  return NextResponse.json({
    ok: true,
    overall: summarizePerformance(rows),
    summary: aggregate(byVersion, 'version'),
    byMarket: aggregate(byMarket, 'market'),
    byTier: aggregate(byTier, 'tier'),
    totalSettlements: settlements.length,
    stakePolicy: 'Flat 1 unit per settled forecast. Win = decimal odds - 1; loss = -1; push = 0; void excluded.',
    clvDefinition: 'Positive CLV means locked decimal odds were better than the last quote observed after lock and before first pitch.',
    note: 'Rows without a valid locked market price are excluded from ROI and reported as missing price.',
    experimentalWarning: 'Unified MLB Totals v4.0 is experimental. Gap labels are not calibrated probabilities.',
  });
}
