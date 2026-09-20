import { NextResponse } from 'next/server';
import { readMatches } from '@/lib/fc/store';
import { FC_UI_VERSION } from '@/lib/fc/predictions';

export const dynamic = 'force-dynamic';

/** Analyzer is a view of the same per-league engine output as the schedule.
 * No generic ratings, duplicated Poisson model, or fabricated confidence. */
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get('limit') ?? 200);
  const offset = Number(query.get('offset') ?? 0);
  return NextResponse.json({
    ...readMatches(Number.isFinite(limit) ? limit : 200, Number.isFinite(offset) ? offset : 0),
    source: 'dc-per-league-market-catalog',
    ui_version: FC_UI_VERSION,
    generated_at: new Date().toISOString(),
    official_enabled: false,
    official_reason: 'MODEL_NOT_VALIDATED',
  }, { headers: { 'Cache-Control': 'no-store' } });
}
