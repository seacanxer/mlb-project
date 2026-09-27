import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/**
 * POST /api/fc/scan — live scan (fixtures + odds + DC projections + gated picks).
 * Runs scripts/fc-scan-live.py with the FC venv python when present, refreshing
 * matches_detailed.json, picks.json and config.json scan metadata.
 *
 * The scan takes ~2 minutes, well past the 100s edge timeout of the tunnel proxy,
 * so POST enqueues the work and returns immediately; progress is read via GET.
 */
const SCAN_TIMEOUT_MS = 600000;

let running = false;
let startedAt = 0;
let last: {
  at: string;
  status: string;
  fixtures?: number;
  picks?: number;
  forecasts?: number;
  message?: string;
} | null = null;

function enginePython(): string {
  const venv = path.join(process.cwd(), 'betting-machine-fc', 'venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : 'python3';
}

function runScan(): Promise<{ stdout: string; full: boolean }> {
  const live = path.join(process.cwd(), 'scripts', 'fc-scan-live.py');
  const full = fs.existsSync(live);
  const script = full ? live : path.join(process.cwd(), 'scripts', 'fc-scrape-fixtures.py');
  return new Promise((resolve, reject) => {
    execFile(enginePython(), [script], { timeout: SCAN_TIMEOUT_MS }, (err, stdout) => {
      if (err) reject(err);
      else resolve({ stdout, full });
    });
  });
}

async function runScanInBackground() {
  running = true;
  startedAt = Date.now();
  try {
    const { stdout, full } = await runScan();
    const { readMatches } = await import('@/lib/fc/store');
    const total = readMatches(1, 0).pagination.total;
    let picks: number | undefined;
    let forecasts: number | undefined;
    if (full) {
      const line = stdout.trim().split('\n').pop() ?? '';
      const summary = JSON.parse(line) as { picks?: number; forecasts?: number; status?: string };
      if (summary.status !== 'ok') throw new Error(summary.status ?? 'scan failed');
      picks = summary.picks;
      forecasts = summary.forecasts;
    }
    last = { at: new Date().toISOString(), status: 'done', fixtures: total, picks, forecasts };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Scan gagal.';
    last = { at: new Date().toISOString(), status: 'error', message };
  } finally {
    running = false;
    startedAt = 0;
  }
}

export async function POST() {
  if (running) {
    return NextResponse.json(
      { status: 'busy', message: 'Scan sedang berjalan.' },
      { status: 409 },
    );
  }
  last = { at: new Date().toISOString(), status: 'running' };
  void runScanInBackground();
  return NextResponse.json(
    { status: 'accepted', message: 'Scan dimulai, hasil akan muncul otomatis.' },
    { status: 202 },
  );
}

export async function GET() {
  return NextResponse.json({
    running,
    elapsed_ms: startedAt ? Date.now() - startedAt : null,
    last,
  });
}
