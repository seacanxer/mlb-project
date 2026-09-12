import { NextResponse } from 'next/server';
import { readMatches } from '@/lib/fc/store';

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sp = url.searchParams;
  const limit = Number(sp.get('limit') ?? 50);
  const offset = Number(sp.get('offset') ?? 0);
  return NextResponse.json(
    readMatches(Number.isFinite(limit) ? limit : 50, Number.isFinite(offset) ? offset : 0),
  );
}
