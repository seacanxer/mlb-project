// app/api/results/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { ingestResultAndGrade, gradeForecast } from '@/lib/engine/forecast';
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

    // ── catch-up: grade pending forecasts for games already marked final ──
    const finalGames = await prisma.game.findMany({
      where: { date, status: 'final' },
      select: { id: true },
    });
    const finalIds = finalGames.map(g => g.id);
    // ensure every final game has a GameResult (ingest missing scores from provider)
    for (const gid of finalIds) {
      const existing = await prisma.gameResult.findUnique({ where: { gameId: gid } });
      if (existing) continue;
      const provResult = await provider.getResult(gid);
      const r = provResult?.data;
      if (r && r.finalStatus === 'final') {
        const graded = await ingestResultAndGrade(gid, r.homeScore, r.awayScore);
        forecastsGraded += graded.settledCount;
        settled.push({ gameId: gid, ...graded });
      }
    }
    // grade any remaining pending forecasts for final games
    const pendingForecasts = await prisma.forecast.findMany({
      where: {
        modelRun: { gameId: { in: finalIds } },
        settlement: null,
        lockedAt: { gte: new Date(0) },
      },
      include: { modelRun: { include: { game: true } } },
    });
    for (const fc of pendingForecasts) {
      const gameResult = await prisma.gameResult.findUnique({
        where: { gameId: fc.modelRun.gameId },
      });
      if (!gameResult) continue;
      await gradeForecast(fc.id, gameResult.id);
      forecastsGraded++;
      settled.push({ gameId: fc.modelRun.gameId, gameResultId: gameResult.id, settledCount: 1 });
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
