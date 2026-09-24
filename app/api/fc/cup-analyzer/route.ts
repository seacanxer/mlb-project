import { NextResponse } from 'next/server';
import { readMatches } from '@/lib/fc/store';
import { FC_UI_VERSION } from '@/lib/fc/predictions';

export const dynamic = 'force-dynamic';

const CUP_TOKENS = [
  'fa cup', 'cup', 'beker', 'copa', 'pokal', 'coupe', 'knvb', 'emperors',
  'league cup', 'carabao', 'super cup', 'cup uefa', 'cup. women',
];

function isCup(league: string | undefined | null): boolean {
  const text = (league ?? '').toLowerCase();
  return CUP_TOKENS.some((token) => text.includes(token));
}

/**
 * Standalone cup / no-model fixture view.
 *
 * Read-only research surface for fixtures the production Dixon-Coles model
 * cannot project (cup ties, lower-tier cross-league meetings). This route
 * never writes to picks.json, bets.db or settlement state; it only relabels
 * what readMatches already produced. Nothing here is an official pick - the
 * fallback ladder output is unvalidated by design.
 */
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get('limit') ?? 200);
  const offset = Number(query.get('offset') ?? 0);
  const onlyCups = query.get('cup') === '1';

  const payload = readMatches(
    Number.isFinite(limit) ? limit : 200,
    Number.isFinite(offset) ? offset : 0,
  );

  const matches = Array.isArray(payload.matches) ? payload.matches : [];
  const rows = matches
    .filter((match) => {
      const info = (match?.info ?? {}) as Record<string, unknown> | undefined;
      if (onlyCups && !isCup(info?.league as string)) return false;
      return Boolean(info?.match_id && (info?.home || info?.away));
    })
    .map((match) => {
      const info = (match?.info ?? {}) as Record<string, unknown>;
      const analysis = (match?.analysis ?? {}) as Record<string, unknown>;
      const projections = Array.isArray(match?.projections)
        ? match.projections
        : Array.isArray(match?.picks)
          ? match.picks
          : [];
      return {
        match_id: info.match_id,
        home: info.home,
        away: info.away,
        league: info.league,
        start_ts: info.start_ts,
        is_cup: isCup(info.league as string),
        coverage_status: info.coverage_status ?? 'market_only',
        source: info.source ?? '1xbit',
        analysis_status: analysis.status ?? 'unavailable',
        reason_codes: analysis.reason_codes ?? [],
        model_source:
          analysis.status === 'ready'
            ? (analysis.league_model
                ? `dixon-coles:${String(analysis.league_model)}`
                : 'dixon-coles')
            : 'market-only',
        official_eligible: false,
        expected_goals: analysis.model_goals ?? { home: null, away: null },
        projections,
      };
    });

  const cups = rows.filter((row) => row.is_cup).length;
  const covered = rows.filter((row) => row.coverage_status !== 'market_only').length;

  return NextResponse.json(
    {
      matches: rows,
      total: rows.length,
      cup_matches: cups,
      model_covered: covered,
      market_only: rows.length - covered,
      source: 'dc-per-league-market-catalog',
      fallback_ladder: [
        'production-dixon-coles',
        'fc-historical-strength-v1',
        'competition-prior',
        'market-only',
      ],
      ui_version: FC_UI_VERSION,
      generated_at: new Date().toISOString(),
      official_enabled: false,
      official_reason: 'MODEL_NOT_VALIDATED',
      note: 'Standalone research output. Not the production gate; do not treat as an official pick.',
    },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
