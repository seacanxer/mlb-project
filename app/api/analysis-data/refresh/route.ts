import { NextRequest, NextResponse } from 'next/server';
import { refreshResults, refreshSlate } from '@/lib/services/slateIngestion';

export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function POST(req: NextRequest) {
  let date = '';
  try {
    const body = await req.json() as { date?: string };
    date = body.date ?? '';
  } catch {
    return NextResponse.json({ ok: false, error: 'A JSON body with date is required.' }, { status: 400 });
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ ok: false, error: 'Invalid date. Expected YYYY-MM-DD.' }, { status: 400 });
  }

  try {
    const slate = await refreshSlate(date);
    if (slate.scheduleGames === 0) {
      return NextResponse.json({ ok: false, slate, error: `No MLB games scheduled for ${date}` }, { status: 404 });
    }
    const results = await refreshResults(date);
    return NextResponse.json({
      ok: slate.ok && results.ok,
      date,
      slate,
      results,
    }, { status: slate.ok && results.ok ? 200 : 207 });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      date,
      error: error instanceof Error ? error.message : String(error),
    }, { status: 502 });
  }
}
