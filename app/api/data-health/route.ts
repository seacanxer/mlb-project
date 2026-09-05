// app/api/data-health/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { currentDisplayDate } from '@/lib/utils/timezone';

export const dynamic = 'force-dynamic';

export async function GET() {
  const staleThresholdHours = 24;
  const cutoff = new Date(Date.now() - staleThresholdHours * 3600_000);
  const oddsCutoff = new Date(Date.now() - 4 * 3600_000);
  const todayWib = currentDisplayDate();
  const activeWindowStart = new Date(Date.now() - 6 * 3600_000);
  const activeGames = await prisma.game.findMany({
    where: {
      status: { in: ['scheduled', 'in_progress'] },
      startTimeUtc: { gte: activeWindowStart },
    },
    include: {
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 },
      homeTeam: { include: { snapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 } } },
      awayTeam: { include: { snapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 } } },
      probableStarterObservations: { orderBy: { retrievedAt: 'desc' } },
    },
  });

  const staleMarkets = activeGames.filter((game) => {
    const latest = game.marketSnapshots[0];
    return !latest || latest.freshnessState !== 'fresh' || latest.retrievedAt < oddsCutoff;
  }).length;
  const activeTeamSnapshots = new Map<string, Date | null>();
  for (const game of activeGames) {
    activeTeamSnapshots.set(game.homeTeamId, game.homeTeam.snapshots[0]?.retrievedAt ?? null);
    activeTeamSnapshots.set(game.awayTeamId, game.awayTeam.snapshots[0]?.retrievedAt ?? null);
  }
  const staleTeamStats = [...activeTeamSnapshots.values()].filter(
    (retrievedAt) => !retrievedAt || retrievedAt < cutoff
  ).length;
  let unconfirmedStarters = 0;
  for (const game of activeGames) {
    for (const side of ['home', 'away']) {
      const latest = game.probableStarterObservations.find((starter) => starter.side === side);
      if (!latest || latest.confirmationStatus !== 'confirmed') unconfirmedStarters += 1;
    }
  }

  return NextResponse.json({
    ok: true,
    summary: {
      staleMarkets,
      staleTeamStats,
      unconfirmedStarters,
      scheduledGames: activeGames.length,
      scope: 'latest snapshots for active games only',
      asOfWib: todayWib,
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
