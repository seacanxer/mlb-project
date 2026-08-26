// app/api/slates/[date]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET(
  _req: NextRequest,
  { params }: { params: { date: string } }
) {
  const { date } = params;

  const games = await prisma.game.findMany({
    where: { date },
    include: {
      homeTeam: true,
      awayTeam: true,
      venue: true,
      modelRuns: {
        orderBy: { runAt: 'desc' },
        include: { warnings: true },
      },
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 },
      probableStarterObservations: {
        orderBy: { retrievedAt: 'desc' },
        include: { person: true },
      },
      gameResult: true,
    },
    orderBy: { startTimeUtc: 'asc' },
  });

  return NextResponse.json({ date, games });
}
