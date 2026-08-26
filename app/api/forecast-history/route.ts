// app/api/forecast-history/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET() {
  const forecasts = await prisma.forecast.findMany({
    orderBy: { lockedAt: 'desc' },
    include: {
      settlement: true,
      revisions: true,
      modelRun: { include: { model: true, configVersion: true } },
    },
  });
  return NextResponse.json({ forecasts });
}
