import { describe, expect, it } from 'vitest';
import { GET } from '@/app/api/fc/model-performance/route';

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
});
