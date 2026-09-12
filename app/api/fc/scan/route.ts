import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import path from 'node:path';

/**
 * POST /api/fc/scan — fixture-only scrape (jadwal 24 jam dari 1xbit).
 * NO model logic, NO picks: runs scripts/fc-scrape-fixtures.py server-side
 * and refreshes betting-machine-fc/matches_detailed.json.
 *
 * NOTE: this is intentionally narrower than the deleted engine's
 * POST /api/scan (full projection+selection). Full analysis triggers stay
 * disabled in the UI until the engine is restored (see lib/fc/types.ts §6).
 */
const TIMEOUT_MS = 180000;

let running = false;
let last: { at: string; status: string; fixtures?: number; message?: string } | null = null;

function runScrape(): Promise<number> {
  return new Promise((resolve, reject) => {
    const script = path.join(process.cwd(), 'scripts', 'fc-scrape-fixtures.py');
    const child = execFile('python3', [script], { timeout: TIMEOUT_MS }, (err) => {
      if (err) reject(err);
      else resolve(0);
    });
    // Last-resort guard; execFile timeout already kills on expiry.
    child.on('error', reject);
  });
}

export async function POST() {
  if (running) {
    return NextResponse.json({ status: 'busy', message: 'Scrape jadwal sedang berjalan.' }, { status: 409 });
  }
  running = true;
  try {
    await runScrape();
    const { readMatches } = await import('@/lib/fc/store');
    const total = readMatches(1, 0).pagination.total;
    last = { at: new Date().toISOString(), status: 'done', fixtures: total };
    return NextResponse.json({ status: 'done', fixtures: total, message: `${total} fixture 24 jam ke depan.` });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Scrape gagal.';
    last = { at: new Date().toISOString(), status: 'error', message };
    return NextResponse.json({ status: 'error', message }, { status: 502 });
  } finally {
    running = false;
  }
}

export async function GET() {
  return NextResponse.json({ running, last });
}
