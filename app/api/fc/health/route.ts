import { NextResponse } from 'next/server';
import { readHealth } from '@/lib/fc/store';

export async function GET() {
  return NextResponse.json(readHealth());
}
