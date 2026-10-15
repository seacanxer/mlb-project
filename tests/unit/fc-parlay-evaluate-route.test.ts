import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ run: vi.fn() }));
vi.mock('node:child_process', () => ({ execFile: Object.assign(vi.fn(),
  { [Symbol.for('nodejs.util.promisify.custom')]: mocks.run }) }));
import { POST } from '@/app/api/fc/parlay/evaluate/route';
const choices = [{ match_id: '1', market: 'ou', pick: 'Over 2.5', odds: 1.9 },
  { match_id: '2', market: '1x2', pick: 'Home', odds: 2 }];
const request = (body: unknown) => new Request('http://localhost/api/fc/parlay/evaluate',
  { method: 'POST', body: JSON.stringify(body) });
beforeEach(() => { mocks.run.mockReset(); });
it('rejects client probability/EV injection before invoking the engine', async () => {
  expect((await POST(request({ choices: [{ ...choices[0], probability: .99 }, choices[1]] }))).status).toBe(400);
  expect(mocks.run).not.toHaveBeenCalled();
});
it('returns a read-only server assessment', async () => {
  mocks.run.mockResolvedValue({ stdout: '{"status":"blocked","eligible":false}' });
  const response = await POST(request({ choices }));
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ status: 'blocked', eligible: false });
  expect(mocks.run.mock.calls[0][1][0]).toContain('fc-evaluate-parlay.py');
});
it('sanitizes subprocess failures', async () => {
  mocks.run.mockRejectedValue(new Error('secret-path-and-token'));
  const response = await POST(request({ choices }));
  expect(response.status).toBe(503);
  expect(JSON.stringify(await response.json())).not.toContain('secret');
});
it('rejects null and oversized portfolios before spawning Python', async () => {
  expect((await POST(request(null))).status).toBe(400);
  expect((await POST(request({ choices: Array(9).fill(choices[0]) }))).status).toBe(400);
  expect(mocks.run).not.toHaveBeenCalled();
});
it('builds suggestions from server candidates without client probabilities', async () => {
  mocks.run.mockResolvedValue({ stdout: '{"status":"ok","proposals":[]}' });
  const response = await POST(request({ mode: 'build' }));
  expect(response.status).toBe(200);
  expect(mocks.run.mock.calls[0][1].at(-1)).toBe('{"mode":"build"}');
});
