import { NextResponse } from 'next/server';
import { readHealth } from '@/lib/fc/store';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json(readHealth());
}