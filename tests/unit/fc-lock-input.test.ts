import { afterEach, expect, it } from 'vitest';
import { POST } from '@/app/api/fc/locks/route';
const original = process.env.FC_LOCK_TOKEN;
afterEach(() => {
  if (original === undefined) delete process.env.FC_LOCK_TOKEN;
  else process.env.FC_LOCK_TOKEN = original;
});
const request = (body: unknown) => {
  process.env.FC_LOCK_TOKEN = 'test-operator-token';
  return new Request('http://localhost/api/fc/locks', { method: 'POST',
    headers: { Authorization: 'Bearer test-operator-token' }, body: JSON.stringify(body) });
};
it('rejects JSON null instead of throwing a runtime error', async () => {
  expect((await POST(request(null))).status).toBe(400);
});
it('keeps unpriced secondary projections out of settlement locks', async () => {
  expect((await POST(request({ match_id: '1', market: 'corners_ou', pick: 'Over 9.5', odds: null }))).status).toBe(400);
});
it('rejects unpriced legs atomically before invoking the ledger', async () => {
  expect((await POST(request({ mode: 'singles', choices: [
    { match_id: '1', market: 'corners_ou', pick: 'Over 9.5', odds: null },
    { match_id: '2', market: 'ou', pick: 'Over 2.5', odds: 1.9 },
  ] }))).status).toBe(400);
});
