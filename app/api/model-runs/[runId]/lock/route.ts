// app/api/model-runs/[runId]/lock/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { lockForecast, ForecastError } from '@/lib/engine/forecast';

export async function POST(
  req: NextRequest,
  { params }: { params: { runId: string } }
) {
  try {
    const body = await req.json().catch(() => ({}));
    const forecastId = await lockForecast(params.runId, {
      selectedSide: body.selectedSide,
      notes: body.notes,
    });
    return NextResponse.json({ ok: true, forecastId });
  } catch (err) {
    if (err instanceof ForecastError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 400 });
    }
    throw err;
  }
}
