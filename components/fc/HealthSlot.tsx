/**
 * components/fc/HealthSlot.tsx
 *
 * Client slot that polls /api/fc/health and renders the FR-4 banner.
 * Failures never wipe page data — banner simply stays hidden/erroneous.
 */
'use client';
import { useFcPoll } from '@/lib/fc/hooks';
import type { HealthResponse } from '@/lib/fc/types';
import { HealthBanner } from './shared';

export function HealthSlot() {
  const { data } = useFcPoll<HealthResponse>('/api/fc/health', 60000);
  return <HealthBanner health={data} />;
}
