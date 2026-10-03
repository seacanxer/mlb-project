import { NextResponse } from 'next/server';
import { readModelPerformance } from '@/lib/fc/store';

export const dynamic = 'force-dynamic';

/**
 * Model skill report (all scan projections, graded vs actuals).
 * Read-only mirror of reports/fc-model-performance.json — never money,
 * never derived from the ROI tracker.
 */
export async function GET() {
  return NextResponse.json(readModelPerformance());
}
