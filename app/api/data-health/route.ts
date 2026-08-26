// app/api/data-health/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { ageHours } from '@/lib/utils/timezone';

export const dynamic = 'force-dynamic';

export async function GET() {
  const staleThresholdHours = 24;
  const cutoff = new Date(Date.now() - staleThresholdHours * 3600_000);

  const staleMarkets = await prisma.marketSnapshot.count({
    where: { freshnessState: 'stale' },
  });
  const staleTeamStats = await prisma.teamSnapshot.count({
    where: { retrievedAt: { lt: cutoff } },
  });
  const unconfirmedStarters = await prisma.probableStarterObservation.count({
    where: { confirmationStatus: { in: ['tbd', 'conflicting'] } },
  });
  const recentGames = await prisma.game.count({
    where: { status: 'scheduled', date: { gte: new Date().toISOString().slice(0, 10) } },
  });

  return NextResponse.json({
    ok: true,
    summary: {
      staleMarkets,
      staleTeamStats,
      unconfirmedStarters,
      scheduledGames: recentGames,
    },
    providers: [
      { name: 'mlb-stats-api', status: 'configured', note: 'Public API — no key required' },
      {
        name: 'odds-provider',
        status: process.env.ODDS_PROVIDER ? 'configured' : 'not_configured',
        note: process.env.ODDS_PROVIDER
          ? `Provider: ${process.env.ODDS_PROVIDER}`
          : 'ODDS_PROVIDER_NOT_CONFIGURED — use manual import',
      },
    ],
    timestamp: new Date().toISOString(),
  });
}
