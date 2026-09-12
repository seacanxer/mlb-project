/**
 * lib/fc/client.ts
 *
 * Typed fetch wrapper for the same-origin FC read API (`/api/fc/*`).
 * Same-origin by design (brief §6.5/§13.7): no API key in the browser, no
 * CORS exposure — the browser only talks to the Next.js host, which reads
 * engine files server-side.
 */
import type { ApiErrorShape } from './types';

export class FcApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'FcApiError';
    this.status = status;
  }
}

const DEFAULT_TIMEOUT_MS = 15000;

export function apiErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const b = body as ApiErrorShape;
    if (typeof b.detail === 'string' && b.detail) return b.detail;
    if (typeof b.error === 'string' && b.error) return b.error;
    if (typeof b.message === 'string' && b.message) return b.message;
  }
  return fallback;
}

/** GET JSON with explicit timeout; throws FcApiError (never returns HTML). */
export async function fcGet<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { signal: ctrl.signal, cache: 'no-store' });
    const text = await res.text();
    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch {
      throw new FcApiError(`Server error (${res.status})`, res.status);
    }
    if (!res.ok) {
      throw new FcApiError(apiErrorMessage(body, `Request failed (${res.status})`), res.status);
    }
    return body as T;
  } catch (err) {
    if (err instanceof FcApiError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new FcApiError('Request timed out, try again.', 408);
    }
    throw new FcApiError('Failed to load, try again.', 0);
  } finally {
    clearTimeout(timer);
  }
}

export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}
