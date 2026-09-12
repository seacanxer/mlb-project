import { NextResponse } from 'next/server';
import { readPicks } from '@/lib/fc/store';

function num(v: string | null, fallback?: number): number | undefined {
  if (v === null || v === '') return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sp = url.searchParams;
  return NextResponse.json(
    readPicks({
      market: sp.get('market') ?? undefined,
      league: sp.get('league') ?? undefined,
      min_odds: num(sp.get('min_odds')),
      max_odds: num(sp.get('max_odds')),
      min_ev: num(sp.get('min_ev')),
      search: sp.get('search') ?? undefined,
      sort_by: sp.get('sort_by') ?? undefined,
      sort_order: sp.get('sort_order') ?? undefined,
      limit: num(sp.get('limit'), 50),
      offset: num(sp.get('offset'), 0),
    }),
  );
}
