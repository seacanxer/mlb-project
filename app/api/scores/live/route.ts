// app/api/scores/live/route.ts
//
// Proxy endpoint: fetch live/current scores directly from MLB Stats API
// for all games on a given date. Does NOT write to DB.
// Returns lightweight score objects for quick UI polling.

import { NextRequest, NextResponse } from 'next/server';

const BASE = process.env.MLB_STATS_API_BASE_URL || 'https://statsapi.mlb.com';

interface LiveScore {
  gameId: string;
  status: 'scheduled' | 'in_progress' | 'final' | 'postponed' | 'cancelled';
  inning?: number;
  inningHalf?: 'top' | 'bottom';
  homeScore: number | null;
  awayScore: number | null;
  homeTeamName?: string;
  awayTeamName?: string;
  abstractState: string;
  detailedState: string;
}

async function fetchScheduleLive(date: string): Promise<LiveScore[]> {
  const path = `/api/v1/schedule?sportId=1&date=${date}&hydrate=linescore,team`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: 'application/json', 'User-Agent': 'mlb-analytics/0.1' },
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`MLB API error ${res.status}`);
    const raw = await res.json() as any;

    const scores: LiveScore[] = [];
    for (const dateEntry of (raw.dates ?? [])) {
      for (const g of (dateEntry.games ?? [])) {
        const abstract = String(g.status?.abstractGameState ?? '');
        const detailed = String(g.status?.detailedState ?? '');
        const linescore = g.linescore;

        let status: LiveScore['status'] = 'scheduled';
        const detailLower = detailed.toLowerCase();
        if (detailLower.includes('postponed')) status = 'postponed';
        else if (detailLower.includes('cancel')) status = 'cancelled';
        else if (abstract === 'Final') status = 'final';
        else if (abstract === 'Live') status = 'in_progress';

        scores.push({
          gameId: String(g.gamePk),
          status,
          inning: linescore?.currentInning ?? undefined,
          inningHalf: linescore?.inningHalf === 'Top' ? 'top' : linescore?.inningHalf === 'Bottom' ? 'bottom' : undefined,
          homeScore: linescore?.teams?.home?.runs ?? null,
          awayScore: linescore?.teams?.away?.runs ?? null,
          homeTeamName: g.teams?.home?.team?.name,
          awayTeamName: g.teams?.away?.team?.name,
          abstractState: abstract,
          detailedState: detailed,
        });
      }
    }
    return scores;
  } finally {
    clearTimeout(timeout);
  }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get('date') ?? new Date().toISOString().slice(0, 10);

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format. Use YYYY-MM-DD.' }, { status: 400 });
  }

  try {
    const scores = await fetchScheduleLive(date);
    return NextResponse.json({ date, scores });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to fetch live scores' },
      { status: 502 }
    );
  }
}
