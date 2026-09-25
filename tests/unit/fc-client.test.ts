import { afterEach, describe, expect, it, vi } from 'vitest';
import { FcApiError, fcPost } from '@/lib/fc/client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('fcPost', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the parsed JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'done', message: 'ok' })));
    await expect(fcPost('/api/fc/scan')).resolves.toEqual({ status: 'done', message: 'ok' });
  });

  it('explains an HTML answer instead of surfacing a JSON parse error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<!DOCTYPE html><html><body>404</body></html>', {
      status: 404,
      headers: { 'Content-Type': 'text/html' },
    })));
    const error = (await fcPost('/api/fc/scan').catch((err: unknown) => err)) as FcApiError;
    expect(error).toBeInstanceOf(FcApiError);
    expect(error.status).toBe(404);
    expect(error.message).toContain('halaman HTML');
  });

  it('surfaces the server message for a JSON error body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'error', message: 'Scan gagal.' }, 502)));
    await expect(fcPost('/api/fc/scan')).rejects.toThrow('Scan gagal.');
  });

  it('only sets a JSON content type when a body is given', async () => {
    const mock = vi.fn(async (_path: string, init?: RequestInit) => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', mock);
    await fcPost('/api/fc/locks', { match_id: '1' }, { Authorization: 'Bearer token' });
    const init = mock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers.Authorization).toBe('Bearer token');
    expect(init.method).toBe('POST');
  });

  it('posts without a body for endpoints that trigger work', async () => {
    const mock = vi.fn(async (_path: string, init?: RequestInit) => jsonResponse({ status: 'done' }));
    vi.stubGlobal('fetch', mock);
    await fcPost('/api/fc/scan', undefined, {}, 1000);
    const init = mock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeUndefined();
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });
});
