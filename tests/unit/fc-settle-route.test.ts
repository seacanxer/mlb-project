import { afterEach, describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '@/app/api/fc/settle/route';

function request(headers: Record<string, string> = {}) {
  return new NextRequest('http://localhost/api/fc/settle', { method: 'POST', headers });
}

describe('FC settle route safeguards', () => {
  const originalToken = process.env.FC_LOCK_TOKEN;

  afterEach(() => {
    if (originalToken === undefined) delete process.env.FC_LOCK_TOKEN;
    else process.env.FC_LOCK_TOKEN = originalToken;
  });

  it('reports idle settlement status without spawning the job', async () => {
    const response = await GET();
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ running: false });
  });

  it('rejects a missing operator token when FC_LOCK_TOKEN is configured', async () => {
    process.env.FC_LOCK_TOKEN = 'correct-horse-battery-staple';
    const response = await POST(request());
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({ status: 'error' });
  });

  it('rejects a wrong operator token without leaking the configured one', async () => {
    process.env.FC_LOCK_TOKEN = 'correct-horse-battery-staple';
    const response = await POST(request({ Authorization: 'Bearer wrong-token' }));
    expect(response.status).toBe(401);
    const body = await response.json();
    expect(JSON.stringify(body)).not.toContain('correct-horse-battery-staple');
  });
});
