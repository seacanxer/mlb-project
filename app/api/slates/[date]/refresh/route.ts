// app/api/slates/[date]/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { refreshSlate } from '@/lib/services/slateIngestion';

// In-memory job tracker (for optional status polling)
const refreshJobs = new Map<string, { status: 'pending' | 'done' | 'error'; startedAt: Date; finishedAt?: Date; result?: any }>();

export async function POST(
  req: NextRequest,
  { params }: { params: { date: string } }
) {
  const { date } = params;

  // Validate date format
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || isNaN(new Date(`${date}T00:00:00Z`).getTime())) {
    return NextResponse.json(
      { ok: false, date, error: 'Invalid date format' },
      { status: 400 }
    );
  }

  // Check if already running
  const existing = refreshJobs.get(date);
  if (existing && existing.status === 'pending') {
    return NextResponse.json(
      { queued: true, date, jobId: date, status: 'already_running' },
      { status: 202 }
    );
  }

  // Mark as pending
  refreshJobs.set(date, { status: 'pending', startedAt: new Date() });

  // Run refresh in background — don't await
  setImmediate(async () => {
    try {
      console.log(`[REFRESH] Starting background refresh for ${date}...`);
      const result = await refreshSlate(date);
      console.log(`[REFRESH] Completed for ${date}: scheduleGames=${result.scheduleGames}, oddsSnapshots=${result.oddsSnapshots}, warnings=${result.warnings.length}`);
      refreshJobs.set(date, { status: 'done', startedAt: refreshJobs.get(date)!.startedAt, finishedAt: new Date(), result });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`[REFRESH] Failed for ${date}:`, message);
      refreshJobs.set(date, { status: 'error', startedAt: refreshJobs.get(date)!.startedAt, finishedAt: new Date(), result: { error: message } });
    }
  });

  // Return immediately (202 Accepted)
  return NextResponse.json(
    { queued: true, date, jobId: date, status: 'pending' },
    { status: 202 }
  );
}
