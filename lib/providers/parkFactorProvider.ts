/**
 * lib/providers/parkFactorProvider.ts
 *
 * Season-stamped park factor provider backed by the database.
 * The dataset is replaceable via the Settings page without a code release.
 */

import { prisma } from '@/lib/db';
import type { ParkFactorProvider, ParkFactorData } from '@/lib/providers/interfaces';

export class DbParkFactorProvider implements ParkFactorProvider {
  async getParkFactor(venueId: string, season: number): Promise<ParkFactorData | null> {
    // Prefer exact season match; fall back to most recent season marked as fallback
    const exact = await prisma.parkFactorSnapshot.findFirst({
      where: { venueId, season, isFallback: false },
      orderBy: { createdAt: 'desc' },
    });

    if (exact) {
      return {
        venueId: exact.venueId,
        season: exact.season,
        factor: exact.factor,
        source: exact.source,
        isFallback: false,
      };
    }

    // Fallback: most recent available season
    const fallback = await prisma.parkFactorSnapshot.findFirst({
      where: { venueId },
      orderBy: [{ season: 'desc' }, { createdAt: 'desc' }],
    });

    if (fallback) {
      return {
        venueId: fallback.venueId,
        season: fallback.season,
        factor: fallback.factor,
        source: fallback.source,
        isFallback: true,
      };
    }

    return null;
  }
}
