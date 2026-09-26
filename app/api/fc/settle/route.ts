import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import { timingSafeEqual } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

/**
 * POST /api/fc/settle — refresh settlement from the results feeds.
 *
 * Runs scripts/fc-settle-live.py (FlashScore → TheSportsDB/OpenLigaDB, then
 * payout math), then ALWAYS rebuilds tracker_snapshot.json with
 * scripts/fc-snapshot.py — so `manual_parlays[].legs` and the KPI cards stay
 * fresh even when a score feed fails (the settle script only rebuilds the
 * snapshot on its own success path). Same operator token gate as
 * /api/fc/locks when FC_LOCK_TOKEN is configured; without a token (local
 * dev) the lock API is closed anyway.
 */
export const dynamic = 'force-dynamic';
const run = promisify(execFile);
const TIMEOUT_MS = 180000;
const SNAPSHOT_TIMEOUT_MS = 60000;

interface SettleSummary {
  status?: string;
  message?: string;
  settled?: number;
  parlay_settled?: number;
  pending_parlays?: number;
  remaining?: number;
  pending?: number;
}

let running = false;
let last: { at: string; status: string; message?: string } | null = null;

function authorized(request: Request): boolean {
  const configured = process.env.FC_LOCK_TOKEN;
  if (!configured) return true;
  const supplied = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '') ?? '';
  const a = Buffer.from(configured);
  const b = Buffer.from(supplied);
  return a.length === b.length && timingSafeEqual(a, b);
}

function settlePython(): string {
  const venv = path.join(process.cwd(), 'betting-machine-fc', 'venv', 'bin', 'python');
  if (fs.existsSync(venv)) return venv;
  if (process.env.FC_PYTHON) return process.env.FC_PYTHON;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function summaryMessage(summary: SettleSummary): string {
  const singles = summary.settled ?? 0;
  const parlays = summary.parlay_settled ?? 0;
  const pendingParlays = summary.pending_parlays ?? 0;
  const remaining = summary.remaining ?? summary.pending ?? 0;
  if (singles + parlays > 0) {
    const settled = `${singles} pick dan ${parlays} parlay diselesaikan.`;
    return remaining > 0 || pendingParlays > 0
      ? `${settled} ${remaining} pick dan ${pendingParlays} parlay masih menunggu skor.`
      : settled;
  }
  if (remaining > 0 || pendingParlays > 0) return `Belum ada skor final yang cocok — ${remaining} pick dan ${pendingParlays} parlay masih menunggu skor.`;
  return 'Tidak ada settlement tertunda.';
}

async function settle(): Promise<{ status: string; message: string; summary: SettleSummary }> {
  const script = path.join(process.cwd(), 'scripts', 'fc-settle-live.py');
  try {
    const { stdout } = await run(settlePython(), [script], { timeout: TIMEOUT_MS, maxBuffer: 1024 * 1024 });
    const line = stdout.trim().split('\n').at(-1) ?? '';
    if (!line) throw new Error('Settlement tidak menghasilkan keluaran.');
    const summary = JSON.parse(line) as SettleSummary;
    if (summary.status !== 'ok') throw new Error(summary.message ?? 'Settlement gagal.');
    return { status: 'done', message: summaryMessage(summary), summary };
  } catch (error) {
    const output = (error as { stdout?: string }).stdout?.trim().split('\n').at(-1);
    if (output) {
      try {
        const summary = JSON.parse(output) as SettleSummary;
        if (summary.status === 'ok') return { status: 'done', message: summaryMessage(summary), summary };
      } catch { /* Report the failure below instead. */ }
    }
    throw error instanceof Error ? error : new Error('Settlement gagal.');
  }
}

/** Rebuild tracker_snapshot.json regardless of feed availability. */
async function refreshSnapshot(): Promise<void> {
  const script = path.join(process.cwd(), 'scripts', 'fc-snapshot.py');
  const db = path.join(process.cwd(), 'betting-machine-fc', 'bets.db');
  try {
    await run(settlePython(), [script, '--db', db], { timeout: SNAPSHOT_TIMEOUT_MS, maxBuffer: 1024 * 1024 });
  } catch (error) {
    throw new Error(`Snapshot gagal diperbarui: ${error instanceof Error ? error.message : 'error'}`);
  }
}

export async function GET() {
  return NextResponse.json({ running, last });
}

export async function POST(request: Request) {
  if (!authorized(request)) {
    return NextResponse.json({ status: 'error', message: 'Token operator tidak valid atau belum dikonfigurasi.' }, { status: 401 });
  }
  if (running) {
    return NextResponse.json({ status: 'busy', message: 'Settlement sedang berjalan.' }, { status: 409 });
  }
  running = true;
  try {
    let settleError: Error | null = null;
    let summary: SettleSummary = {};
    try {
      const result = await settle();
      summary = result.summary;
    } catch (error) {
      settleError = error instanceof Error ? error : new Error('Settlement gagal.');
    }

    let snapshotError: Error | null = null;
    try {
      await refreshSnapshot();
    } catch (error) {
      snapshotError = error instanceof Error ? error : new Error('Snapshot gagal diperbarui.');
    }

    if (settleError && snapshotError) {
      const message = `${settleError.message} ${snapshotError.message}`;
      last = { at: new Date().toISOString(), status: 'error', message };
      return NextResponse.json({ status: 'error', message }, { status: 502 });
    }

    const base = {
      settled: summary.settled ?? 0,
      parlay_settled: summary.parlay_settled ?? 0,
      pending_parlays: summary.pending_parlays ?? 0,
      remaining: summary.remaining ?? summary.pending ?? 0,
    };
    if (settleError) {
      // Snapshot rebuilt anyway: parlay legs and cards are fresh, scores are not.
      const message = `Snapshot tracker diperbarui, tetapi settlement gagal: ${settleError.message}`;
      last = { at: new Date().toISOString(), status: 'partial', message };
      return NextResponse.json({ status: 'partial', message, ...base });
    }
    const warning = snapshotError ? ` ⚠ ${snapshotError.message}` : '';
    const message = `${summaryMessage(summary)}${warning}`;
    last = { at: new Date().toISOString(), status: 'done', message };
    return NextResponse.json({ status: 'done', message, ...base });
  } finally {
    running = false;
  }
}
