import { NextResponse } from 'next/server';
import { autoLockActionableForecasts } from '@/lib/engine/forecast';

export async function POST(
  _request: Request,
  { params }: { params: { date: string } },
) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(params.date)) {
    return NextResponse.json({ ok: false, error: 'Invalid slate date' }, { status: 400 });
  }
  const summary = await autoLockActionableForecasts(params.date);
  return NextResponse.json({ ok: summary.errors.length === 0, ...summary });
}
