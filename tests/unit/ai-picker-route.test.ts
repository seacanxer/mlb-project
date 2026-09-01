import { afterEach, describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '@/app/api/pick/route';

function request(body: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/pick', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

const baseBody = {
  gameId: 'game-1',
  away: 'Away Club',
  home: 'Home Club',
  model: 'test/model',
};

describe('AI picker route safeguards', () => {
  const originalPickerUrl = process.env.PICKER_SERVICE_URL;
  const originalRouterUrl = process.env.NINEROUTER_API_BASE;

  afterEach(() => {
    if (originalPickerUrl === undefined) delete process.env.PICKER_SERVICE_URL;
    else process.env.PICKER_SERVICE_URL = originalPickerUrl;
    if (originalRouterUrl === undefined) delete process.env.NINEROUTER_API_BASE;
    else process.env.NINEROUTER_API_BASE = originalRouterUrl;
  });

  it('rejects incomplete matchup input', async () => {
    const response = await POST(request({ gameId: 'game-1' }));
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({ ok: false });
  });

  it('does not call external AI when the framework has no actionable signal', async () => {
    process.env.PICKER_SERVICE_URL = 'http://127.0.0.1:1/should-not-be-called';
    const response = await POST(request(baseBody));
    const payload = await response.json();
    expect(payload).toMatchObject({
      ok: true,
      pick: 'NO PICK',
      source: 'not-run',
      verdict: 'ABSTAIN',
      framework: { actionable: false },
    });
  });

  it('reports unconfigured AI without copying an actionable framework pick', async () => {
    delete process.env.PICKER_SERVICE_URL;
    delete process.env.NINEROUTER_API_BASE;
    const response = await POST(request({
      ...baseBody,
      analysis: {
        moneyline: {
          finalState: 'T1',
          rawScore: 82,
          candidateTeamName: 'Home Club',
        },
      },
    }));
    const payload = await response.json();
    expect(payload).toMatchObject({
      pick: 'AI UNAVAILABLE',
      source: 'unavailable',
      verdict: 'UNAVAILABLE',
      actionable: false,
      framework: { pick: 'Home ML (Home Club)', actionable: true },
      warnings: ['EXTERNAL_MODEL_NOT_CONFIGURED'],
    });
  });
});
