import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { zonedDayBoundsUtc } from '@/lib/utils/timezone';
import { flatUnitProfit, settlementSummary, type SettlementOutcome } from '@/lib/aiFinalPickMath';

const OUTCOMES = new Set(['pending', 'win', 'loss', 'push', 'void']);

function validDate(value: string | null): value is string {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

async function listPicks(date: string) {
  const picks = await prisma.aiFinalPick.findMany({
    where: { slateDateWib: date },
    include: { game: { include: { awayTeam: true, homeTeam: true, gameResult: true } } },
    orderBy: [{ aiRating: 'desc' }, { createdAt: 'asc' }],
  });
  return { date, picks, summary: settlementSummary(picks) };
}

export async function GET(req: NextRequest) {
  const date = req.nextUrl.searchParams.get('date');
  if (!validDate(date)) return NextResponse.json({ error: 'Valid date is required' }, { status: 400 });
  return NextResponse.json(await listPicks(date));
}

function canonicalPick(game: any, result: any) {
  const text = String(result.pick || '').trim();
  const normalized = text.toLowerCase();
  const market = game.marketSnapshots?.[0];
  if (!market) return null;

  const awayName = String(game.awayTeam.name).toLowerCase();
  const homeName = String(game.homeTeam.name).toLowerCase();
  if ((normalized.includes('away') || normalized.includes(awayName)) && normalized.includes('ml')) {
    return market.moneylineAway > 1
      ? { market: 'moneyline', selection: `${game.awayTeam.name} ML`, marketLine: null, decimalOdds: market.moneylineAway }
      : null;
  }
  if ((normalized.includes('home') || normalized.includes(homeName)) && normalized.includes('ml')) {
    return market.moneylineHome > 1
      ? { market: 'moneyline', selection: `${game.homeTeam.name} ML`, marketLine: null, decimalOdds: market.moneylineHome }
      : null;
  }

  const total = normalized.match(/\b(over|under)\s+(\d+(?:\.\d+)?)/);
  if (!total || market.totalLine == null || Math.abs(Number(total[2]) - market.totalLine) > 0.001) return null;
  const side = total[1];
  const decimalOdds = side === 'over' ? market.totalOverDecimal : market.totalUnderDecimal;
  return decimalOdds > 1
    ? { market: 'total', selection: `${side === 'over' ? 'Over' : 'Under'} ${market.totalLine}`, marketLine: market.totalLine, decimalOdds }
    : null;
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null) as { date?: string; results?: any[] } | null;
  if (!validDate(body?.date ?? null) || !Array.isArray(body?.results)) {
    return NextResponse.json({ error: 'date and results are required' }, { status: 400 });
  }
  const date = body.date as string;

  const bounds = zonedDayBoundsUtc(date);
  const games = await prisma.game.findMany({
    where: { startTimeUtc: { gte: bounds.start, lt: bounds.end } },
    include: {
      awayTeam: true,
      homeTeam: true,
      marketSnapshots: { orderBy: { retrievedAt: 'desc' }, take: 1 },
    },
  });
  const gamesById = new Map(games.map((game) => [game.id, game]));

  const accepted = body.results
    .filter((entry) => entry?.result?.source === 'llm' && entry.result.actionable !== false)
    .map((entry) => {
      const game = gamesById.get(String(entry.gameId));
      if (!game) return null;
      const canonical = canonicalPick(game, entry.result);
      const rating = Math.round(Number(entry.result.confidence));
      const rationale = String(entry.result.reason || '').trim();
      if (!canonical || !Number.isFinite(rating) || rating < 55 || rating > 100 || !rationale) return null;
      return {
        slateDateWib: date,
        gameId: game.id,
        ...canonical,
        classification: entry.result.framework?.actionable && entry.result.verdict === 'AGREE'
          ? 'framework_confirmed'
          : 'ai_only',
        frameworkState: String(entry.result.framework?.state || 'NO_ACTIONABLE_SIGNAL'),
        frameworkScore: entry.result.framework?.score == null ? null : Number(entry.result.framework.score),
        aiModel: String(entry.result.model || entry.result.requestedModel || 'unknown'),
        aiRating: rating,
        aiVerdict: String(entry.result.verdict || 'ABSTAIN'),
        rationale,
      };
    })
    .filter((pick): pick is NonNullable<typeof pick> => pick !== null)
    .sort((a, b) => b.aiRating - a.aiRating)
    .slice(0, 5);

  const settled = await prisma.aiFinalPick.findMany({
    where: { slateDateWib: date, status: { not: 'pending' } },
    select: { gameId: true },
  });
  const settledGameIds = new Set(settled.map((pick) => pick.gameId));
  const newPicks = accepted.filter((pick) => !settledGameIds.has(pick.gameId));

  await prisma.$transaction([
    prisma.aiFinalPick.deleteMany({ where: { slateDateWib: date, status: 'pending' } }),
    prisma.aiFinalPick.createMany({ data: newPicks }),
  ]);

  return NextResponse.json({ ...(await listPicks(date)), rejected: body.results.length - accepted.length });
}

export async function PATCH(req: NextRequest) {
  const body = await req.json().catch(() => null) as { id?: string; outcome?: string; note?: string } | null;
  const outcome = String(body?.outcome || '').toLowerCase();
  if (!body?.id || !OUTCOMES.has(outcome)) {
    return NextResponse.json({ error: 'id and valid outcome are required' }, { status: 400 });
  }
  const existing = await prisma.aiFinalPick.findUnique({ where: { id: body.id } });
  if (!existing) return NextResponse.json({ error: 'AI final pick not found' }, { status: 404 });

  const pick = await prisma.aiFinalPick.update({
    where: { id: body.id },
    data: {
      status: outcome,
      profitUnits: flatUnitProfit(outcome as SettlementOutcome, existing.decimalOdds),
      settledAt: outcome === 'pending' ? null : new Date(),
      settlementNote: String(body.note || '').trim().slice(0, 300) || null,
    },
  });
  return NextResponse.json({ pick });
}
