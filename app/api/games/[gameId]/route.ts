// app/api/games/[gameId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET(
  _req: NextRequest,
  { params }: { params: { gameId: string } }
) {
  const game = await prisma.game.findUnique({
    where: { id: params.gameId },
    include: {
      homeTeam: true,
      awayTeam: true,
      venue: true,
      modelRuns: {
        orderBy: { runAt: 'desc' },
        include: {
          warnings: true,
          inputSnapshot: true,
          configVersion: true,
          forecasts: { include: { revisions: true, settlement: true } },
        },
      },
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 3 },
      probableStarterObservations: { orderBy: { retrievedAt: 'desc' } },
      gameResult: true,
    },
  });

  if (!game) return NextResponse.json({ error: 'Game not found' }, { status: 404 });
  return NextResponse.json(game);
}
