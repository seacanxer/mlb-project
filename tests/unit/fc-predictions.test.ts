import { describe, it, expect, vi, beforeEach } from 'vitest';
import { forecastPicks, isValue } from '@/lib/fc/predictions';
import type { DetailedMatch, ForecastPick } from '@/lib/fc/types';
import { readPicks } from '@/lib/fc/store';
import { GET } from '@/app/api/fc/analyzer/route';

const files = vi.hoisted(() => new Map<string, string>());
vi.mock('node:fs', () => ({ default: {
  existsSync: () => true,
  readFileSync: (path: string) => files.get(path.split(/[/\\]/).pop()!) || '[]',
} }));
const pick = { market: 'ou', pick: 'Over 2.5', start_ts: 4102444800, odds: 1.9, probability: .6, ev: .14, conservative_ev: .12, coverage_status: 'full', decision: 'watch', tier: 'watch', is_top_pick: false } as ForecastPick;

beforeEach(() => files.clear());

describe('FC predictions use available evidence', () => {
  it('never counts full ratings as Official approval', () => {
    files.set('picks.json', JSON.stringify([pick]));
    const response = readPicks({});
    expect(response.summary.official_count).toBe(0);
    expect(response.summary.watch_count).toBe(1);
  });
  it('retains below-value forecasts without inventing missing market predictions', () => {
    const forecast = { ...pick, analysis_status: 'forecast', gate_reasons: ['EV_BELOW_VALUE_THRESHOLD'] } as ForecastPick;
    const match: DetailedMatch = { info: {}, projections: [forecast] };
    expect(forecastPicks(match)).toEqual([forecast]);
    expect(isValue(forecast)).toBe(false);
    expect(forecastPicks({ info: { home: 'Unknown', league: 'Japan. J1 League' } })).toEqual([]);
  });
  it('analyzer preserves real league results and has no generic rating fallback or league whitelist', async () => {
    files.set('matches_detailed.json', JSON.stringify([
      { info: { match_id: '1', league: 'England. Championship', start_ts: 4102444800 }, projections: [pick] },
      { info: { match_id: '2', league: 'Japan. J1 League', start_ts: 4102444800 }, projections: [], analysis: { status: 'unavailable', reason_codes: ['LEAGUE_MODEL_UNAVAILABLE'] } },
    ]));
    const response = await GET(new Request('http://localhost/api/fc/analyzer'));
    const body = await response.json();
    expect(body.matches).toHaveLength(2);
    expect(body.matches[0].projections[0].probability).toBe(.6);
    expect(body.matches[1].projections).toEqual([]);
    expect(body.matches[1].analysis.model_goals).toBeUndefined();
    expect(body.official_enabled).toBe(false);
    expect(body.ui_version).toBe('fc-market-board-v2');
  });
});
