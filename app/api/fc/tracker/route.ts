import { NextResponse } from 'next/server';
import { readTracker } from '@/lib/fc/store';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json(readTracker());
}