import { NextResponse } from 'next/server';
import { readHealth } from '@/lib/fc/store';
import { FC_UI_VERSION } from '@/lib/fc/predictions';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({ ...readHealth(), ui_version: FC_UI_VERSION, build_commit: process.env.NEXT_PUBLIC_BUILD_COMMIT || 'unknown' }, { headers: { 'Cache-Control': 'no-store' } });
}
