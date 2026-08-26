// app/api/slates/[date]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET(
  _req: NextRequest,
  { params }: { params: { date: string } }
) {
  const { date } = params;

  try {
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
  } catch (error: any) {
    console.error('[API /api/slates/[date] error]:', error);
    return NextResponse.json(
      { error: error?.message || 'Database query error', date, games: [] },
      { status: 500 }
    );
  }
}
