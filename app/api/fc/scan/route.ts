import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/**
 * POST /api/fc/scan — live scan (fixtures + odds + DC projections + gated
 * picks). Runs scripts/fc-scan-live.py with the FC venv python when present,
 * refreshing matches_detailed.json, picks.json and config.json scan metadata.
 *
 * Falls back to fixture-only scrape if the engine venv is missing.
 */
const TIMEOUT_MS = 600000;

let running = false;
let last: { at: string; status: string; fixtures?: number; picks?: number; message?: string } | null = null;

function enginePython(): string {
  const venv = path.join(process.cwd(), 'betting-machine-fc', 'venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : 'python3';
}

function runScan(): Promise<{ stdout: string; full: boolean }> {
  const live = path.join(process.cwd(), 'scripts', 'fc-scan-live.py');
  const full = fs.existsSync(live);
  const script = full ? live : path.join(process.cwd(), 'scripts', 'fc-scrape-fixtures.py');
  return new Promise((resolve, reject) => {
    execFile(enginePython(), [script], { timeout: TIMEOUT_MS }, (err, stdout) => {
      if (err) reject(err);
      else resolve({ stdout, full });
    });
  });
}

export async function POST() {
  if (running) {
    return NextResponse.json({ status: 'busy', message: 'Scan sedang berjalan.' }, { status: 409 });
  }
  running = true;
  try {
    const { stdout, full } = await runScan();
    const { readMatches } = await import('@/lib/fc/store');
    const total = readMatches(1, 0).pagination.total;
    let picks: number | undefined;
    if (full) {
      const line = stdout.trim().split('\n').pop() ?? '';
      try {
        const summary = JSON.parse(line) as { picks?: number; status?: string };
        if (summary.status !== 'ok') throw new Error(summary.status ?? 'scan failed');
        picks = summary.picks;
      } catch {
        picks = undefined;
      }
    }
    last = { at: new Date().toISOString(), status: 'done', fixtures: total, picks };
    return NextResponse.json({
      status: 'done',
      fixtures: total,
      picks,
      message: full ? `${total} fixture · ${picks ?? '?'} pick lolos gate.` : `${total} fixture 24 jam ke depan.`,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Scan gagal.';
    last = { at: new Date().toISOString(), status: 'error', message };
    return NextResponse.json({ status: 'error', message }, { status: 502 });
  } finally {
    running = false;
  }
}

export async function GET() {
  return NextResponse.json({ running, last });
}