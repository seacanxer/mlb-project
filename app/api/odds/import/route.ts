// app/api/odds/import/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@/lib/db';
import { ManualOddsPayload, parseManualRow } from '@/lib/providers/oddsProvider';

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON' }, { status: 400 });
  }

  const parsed = ManualOddsPayload.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: parsed.error.flatten() }, { status: 422 });
  }

  const results = [];
  for (const row of parsed.data) {
    const odds = parseManualRow(row);
    // Verify game exists
    const game = await prisma.game.findUnique({ where: { id: odds.gameId } });
    if (!game) {
      results.push({ gameId: odds.gameId, ok: false, error: 'Game not found' });
      continue;
    }
    await prisma.marketSnapshot.create({
      data: {
        gameId: odds.gameId,
        provider: 'manual-import',
        retrievedAt: new Date(),
        moneylineHome: odds.moneylineHome ?? null,
        moneylineAway: odds.moneylineAway ?? null,
        moneylineHomeOrig: odds.moneylineHomeOrig ?? null,
        moneylineAwayOrig: odds.moneylineAwayOrig ?? null,
        totalLine: odds.totalLine ?? null,
        totalOverDecimal: odds.totalOverDecimal ?? null,
        totalUnderDecimal: odds.totalUnderDecimal ?? null,
        freshnessState: 'fresh',
      },
    });
    results.push({ gameId: odds.gameId, ok: true });
  }

  return NextResponse.json({ ok: true, results });
}
