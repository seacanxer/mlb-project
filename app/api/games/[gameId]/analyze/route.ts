// app/api/games/[gameId]/analyze/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { analyzeGame } from '@/lib/engine/pipeline';

export async function POST(
  _req: NextRequest,
  { params }: { params: { gameId: string } }
) {
  const result = await analyzeGame(params.gameId);
  if (result.error) {
    return NextResponse.json({ ok: false, error: result.error }, { status: 400 });
  }
  return NextResponse.json({ ok: true, ...result });
}
