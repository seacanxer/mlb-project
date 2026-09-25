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
 * payout math + fc-snapshot.py), so tracker_snapshot.json carries fresh
 * `settled`, `manual_summary` and `manual_parlay_summary` for the Hasil & ROI
 * page. Same operator token gate as /api/fc/locks when FC_LOCK_TOKEN is
 * configured; without a token (local dev) the lock API is closed anyway.
 */
export const dynamic = 'force-dynamic';
const run = promisify(execFile);
const TIMEOUT_MS = 180000;

interface SettleSummary {
  status?: string;
  message?: string;
  settled?: number;
  parlay_settled?: number;
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
  const remaining = summary.remaining ?? summary.pending ?? 0;
  if (singles + parlays > 0) return `${singles} pick dan ${parlays} parlay diselesaikan.`;
  if (remaining > 0) return `Belum ada skor final — ${remaining} pick masih menunggu skor.`;
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
    const { status, message, summary } = await settle();
    last = { at: new Date().toISOString(), status, message };
    return NextResponse.json({
      status,
      message,
      settled: summary.settled ?? 0,
      parlay_settled: summary.parlay_settled ?? 0,
      remaining: summary.remaining ?? summary.pending ?? 0,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Settlement gagal.';
    last = { at: new Date().toISOString(), status: 'error', message };
    return NextResponse.json({ status: 'error', message }, { status: 502 });
  } finally {
    running = false;
  }
}
