// app/api/results/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get('date') ?? new Date().toISOString().slice(0, 10);

  const games = await prisma.game.findMany({
    where: { date },
    include: {
      homeTeam: true,
      awayTeam: true,
      venue: true,
      gameResult: true,
      modelRuns: {
        where: { isInvalidated: false },
        orderBy: { runAt: 'desc' },
        include: {
          forecasts: {
            include: { settlement: true },
          },
          warnings: true,
        },
      },
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 },
    },
    orderBy: { startTimeUtc: 'asc' },
  });

  return NextResponse.json({ date, games });
}
