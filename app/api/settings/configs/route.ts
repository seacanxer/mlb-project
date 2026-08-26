// app/api/settings/configs/route.ts
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET() {
  const configs = await prisma.modelConfigVersion.findMany({
    orderBy: [{ modelId: 'asc' }, { createdAt: 'desc' }],
  });
  return NextResponse.json({ configs });
}
