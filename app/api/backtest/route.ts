// app/api/backtest/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET() {
  const settlements = await prisma.settlement.findMany({
    include: {
      forecast: {
        include: {
          modelRun: {
            include: {
              model: true,
              configVersion: true,
            },
          },
        },
      },
    },
  });

  // Aggregate by model + config version
  const byVersion: Record<string, { model: string; version: string; wins: number; losses: number; pushes: number; total: number }> = {};

  for (const s of settlements) {
    const key = `${s.forecast.modelRun.modelId}@${s.forecast.modelRun.configVersion.semver}`;
    if (!byVersion[key]) {
      byVersion[key] = {
        model: s.forecast.modelRun.model.name,
        version: s.forecast.modelRun.configVersion.semver,
        wins: 0, losses: 0, pushes: 0, total: 0,
      };
    }
    byVersion[key].total++;
    if (s.outcome === 'win') byVersion[key].wins++;
    else if (s.outcome === 'loss') byVersion[key].losses++;
    else if (s.outcome === 'push') byVersion[key].pushes++;
  }

  return NextResponse.json({
    ok: true,
    summary: Object.values(byVersion),
    totalSettlements: settlements.length,
    note: 'ROI hidden until price and declared stake policy are configured.',
    experimentalWarning: 'O/U v2.3 is experimental. Gap labels are not calibrated probabilities.',
  });
}
