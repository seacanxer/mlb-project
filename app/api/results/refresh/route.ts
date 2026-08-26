// app/api/results/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { ingestResultAndGrade } from '@/lib/engine/forecast';
import { prisma } from '@/lib/db';
import { MlbResultsProvider } from '@/lib/providers/mlbStatsApi';

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const date: string = body.date ?? new Date().toISOString().slice(0, 10);

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json(
      { ok: false, date, error: 'Invalid date format. Use YYYY-MM-DD.' },
      { status: 400 }
    );
  }

  try {
    const games = await prisma.game.findMany({
      where: { date, status: { not: 'final' } },
      select: { id: true },
    });

    const provider = new MlbResultsProvider();
    const settled = [];
    let forecastsGraded = 0;

    for (const game of games) {
      const result = await provider.getResult(game.id);
      if (!result) continue;
      const r = result.data;
      if (r.finalStatus === 'final') {
        const graded = await ingestResultAndGrade(game.id, r.homeScore, r.awayScore);
        forecastsGraded += graded.settledCount;
        settled.push({ gameId: game.id, ...graded });
      }
    }

    return NextResponse.json({
      ok: true,
      date,
      checkedGames: games.length,
      finalGamesUpdated: settled.length,
      forecastsGraded,
      settled,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      {
        ok: false,
        date,
        error: `Final-score refresh failed: ${detail}`,
      },
      { status: 502 }
    );
  }
}
