import { NextResponse } from 'next/server';
import { gradeDetailsCsv, readGradeDetails } from '@/lib/fc/store';

export const dynamic = 'force-dynamic';

/**
 * Full pick-level CSV of every graded projection (newest cron state).
 * Same source as the model-performance report detail table, uncapped.
 * Absent local grades → header-only CSV, never an error.
 */
export async function GET() {
  const csv = gradeDetailsCsv(readGradeDetails());
  return new NextResponse(csv, {
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="fc-model-performance.csv"',
    },
  });
}
