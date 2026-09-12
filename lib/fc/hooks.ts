/**
 * lib/fc/hooks.ts
 *
 * Polling hooks for FC pages.
 *
 * Design note (brief §10.1 prescribed SWR): SWR is not installed in this
 * repo and no new runtime dependency could be verified in this environment
 * (no Node locally; VPS runs `npm install` at deploy). This hook implements
 * the required behaviour — 60s polling, pause when tab hidden, resume when
 * visible, abort on unmount — with the platform fetch API only. Swapping to
 * SWR later is a drop-in change at these call sites.
 */
'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { fcGet } from './client';

export interface PollState<T> {
  data: T | null;
  loading: boolean;
  error: string;
  refreshedAt: number | null;
  refresh: () => void;
}

export function useFcPoll<T>(path: string | null, intervalMs = 60000, timeoutMs = 15000): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [error, setError] = useState('');
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!path) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(path, { signal: ctrl.signal, cache: 'no-store' });
      const text = await res.text();
      let body: unknown;
      try {
        body = JSON.parse(text);
      } catch {
        throw new Error(`Server error (${res.status})`);
      }
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      if (ctrl.signal.aborted) return;
      setData(body as T);
      setError('');
      setRefreshedAt(Date.now());
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Failed to load, try again.');
    } finally {
      clearTimeout(timer);
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [path, timeoutMs]);

  useEffect(() => {
    if (!path) return;
    void load();
    const id = window.setInterval(() => {
      if (!document.hidden) void load(); // pause while tab hidden (brief FR-1)
    }, intervalMs);
    const onVisible = () => {
      if (!document.hidden) void load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      abortRef.current?.abort();
    };
  }, [path, intervalMs, load]);

  return { data, loading, error, refreshedAt, refresh: load };
}

/** Lightweight GET via the shared client (one-shot, e.g. verify script use). */
export async function fetchFc<T>(path: string): Promise<T> {
  return fcGet<T>(path);
}
