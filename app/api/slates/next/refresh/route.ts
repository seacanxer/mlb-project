import { NextRequest, NextResponse } from 'next/server';
import { MlbScheduleProvider } from '@/lib/providers/mlbStatsApi';
import { refreshSlate } from '@/lib/services/slateIngestion';

export async function POST(req: NextRequest) {
  const from = req.nextUrl.searchParams.get('from') ?? new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from)) {
    return NextResponse.json({ ok: false, error: `Invalid start date: ${from}` }, { status: 400 });
  }

  const provider = new MlbScheduleProvider();
  const start = new Date(`${from}T00:00:00Z`);
  try {
    for (let offset = 0; offset <= 30; offset += 1) {
      const candidate = new Date(start.getTime() + offset * 86_400_000).toISOString().slice(0, 10);
      const games = await provider.getSchedule(candidate);
      if (games.length > 0) {
        return NextResponse.json(await refreshSlate(candidate));
      }
    }
    return NextResponse.json(
      { ok: false, error: `No MLB games found in the 30 days starting ${from}` },
      { status: 404 }
    );
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : String(error) },
      { status: 502 }
    );
  }
}
