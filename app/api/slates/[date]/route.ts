// app/api/slates/[date]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { MlbScheduleProvider } from '@/lib/providers/mlbStatsApi';
import { shiftDateOnly, zonedDayBoundsUtc } from '@/lib/utils/timezone';

function validTimeZone(value: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: { date: string } }
) {
  const { date } = params;
  const requestedTimezone = req.nextUrl.searchParams.get('timezone');
  if (requestedTimezone && !validTimeZone(requestedTimezone)) {
    return NextResponse.json({ error: 'Invalid timezone' }, { status: 400 });
  }
  const utcBounds = requestedTimezone ? zonedDayBoundsUtc(date, requestedTimezone) : null;

  // 1. Try fetching from Database first if available
  try {
    const dbGames = await prisma.game.findMany({
      where: utcBounds
        ? { startTimeUtc: { gte: utcBounds.start, lt: utcBounds.end } }
        : { date },
      include: {
        homeTeam: true,
        awayTeam: true,
        venue: true,
        modelRuns: {
          orderBy: { runAt: 'desc' },
          include: {
            warnings: true,
            forecasts: { include: { settlement: true } },
          },
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

    if (dbGames && dbGames.length > 0) {
      return NextResponse.json(
        { date, games: dbGames, source: 'database' },
        {
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        }
      );
    }
  } catch (dbError: any) {
    console.warn('[API /api/slates/[date]] DB fetch failed, falling back to live MLB Stats API:', dbError?.message);
  }

  // 2. Fallback to Live MLB Stats API
  try {
    const scheduleProvider = new MlbScheduleProvider();
    const scheduleDates = requestedTimezone
      ? [shiftDateOnly(date, -1), date, shiftDateOnly(date, 1)]
      : [date];
    const scheduleResults = await Promise.all(scheduleDates.map((scheduleDate) => scheduleProvider.getSchedule(scheduleDate)));
    const seenGames = new Set<string>();
    const liveResults = scheduleResults.flat().filter((item) => {
      if (seenGames.has(item.data.gameId)) return false;
      seenGames.add(item.data.gameId);
      if (!utcBounds) return true;
      const start = item.data.startTimeUtc.getTime();
      return start >= utcBounds.start.getTime() && start < utcBounds.end.getTime();
    });

    const formattedGames = liveResults.map((item) => {
      const g = item.data;
      return {
        id: g.gameId,
        date: g.date,
        startTimeUtc: g.startTimeUtc,
        status: g.status,
        season: g.season,
        homeTeamId: g.homeTeamId,
        awayTeamId: g.awayTeamId,
        venueId: g.venueId,
        homeTeam: {
          id: g.homeTeamId,
          name: g.homeTeamName,
          abbreviation: g.homeTeamAbbreviation || g.homeTeamName.slice(0, 3).toUpperCase(),
          city: g.homeTeamCity || '',
        },
        awayTeam: {
          id: g.awayTeamId,
          name: g.awayTeamName,
          abbreviation: g.awayTeamAbbreviation || g.awayTeamName.slice(0, 3).toUpperCase(),
          city: g.awayTeamCity || '',
        },
        venue: {
          id: g.venueId,
          name: g.venueName,
          city: g.homeTeamCity || '',
        },
        probableStarterObservations: [
          {
            side: 'away',
            retrievedAt: new Date().toISOString(),
            person: {
              id: g.awayStarterPersonId || 'away-sp',
              name: g.awayStarterName || 'TBD',
              fullName: g.awayStarterName || 'TBD',
            },
          },
          {
            side: 'home',
            retrievedAt: new Date().toISOString(),
            person: {
              id: g.homeStarterPersonId || 'home-sp',
              name: g.homeStarterName || 'TBD',
              fullName: g.homeStarterName || 'TBD',
            },
          },
        ],
        // MLB Stats API has no betting market. Do not manufacture odds when
        // the database/odds provider is unavailable.
        marketSnapshots: [],
        modelRuns: [],
      };
    });

    return NextResponse.json(
      { date, timezone: requestedTimezone ?? undefined, games: formattedGames, source: 'live-mlb-api' },
      {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      }
    );
  } catch (liveError: any) {
    console.error('[API /api/slates/[date]] Live fetch error:', liveError);
    return NextResponse.json(
      { error: liveError?.message || 'Failed to retrieve slate games', date, games: [] },
      {
        status: 500,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      }
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}
