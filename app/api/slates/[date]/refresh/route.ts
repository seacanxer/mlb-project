// app/api/slates/[date]/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { refreshSlate } from '@/lib/services/slateIngestion';

export async function POST(
  _req: NextRequest,
  { params }: { params: { date: string } }
) {
  const { date } = params;

  try {
    const result = await refreshSlate(date);
    if (result.scheduleGames === 0) {
      return NextResponse.json(
        { ...result, error: `No MLB games scheduled for ${date}` },
        { status: 404 }
      );
    }
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const invalidDate = message.startsWith('Invalid slate date');
    return NextResponse.json(
      { ok: false, date, error: message },
      { status: invalidDate ? 400 : 502 }
    );
  }
}
