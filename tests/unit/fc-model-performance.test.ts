import { describe, expect, it } from 'vitest';
import { GET } from '@/app/api/fc/model-performance/route';
import { GET as GET_CSV } from '@/app/api/fc/model-performance/csv/route';

describe('FC model-performance route', () => {
  it('serves a model-skill report shape, never ROI fields', async () => {
    const response = await GET();
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({ by_market: expect.any(Object) });
    expect(typeof body.note).toBe('string');
    expect(body.note).toContain('Bukan ROI');
    // Money fields must never leak into this report.
    const serialized = JSON.stringify(body);
    expect(serialized).not.toContain('profit_units');
    expect(serialized).not.toContain('roi_pct');
  });

  it('serves a full-detail CSV download with a stable header', async () => {
    const response = await GET_CSV();
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toContain('text/csv');
    expect(response.headers.get('Content-Disposition')).toContain(
      'fc-model-performance.csv',
    );
    const text = await response.text();
    const [header] = text.split('\n');
    expect(header).toBe(
      'match,league,market,pick,side,line,model_probability,odds,ev,outcome,score,home_goals,away_goals,kickoff,kickoff_ts,graded_at',
    );
  });
});
