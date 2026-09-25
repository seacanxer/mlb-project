import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import { timingSafeEqual } from 'node:crypto';
import path from 'node:path';
import { promisify } from 'node:util';

export const dynamic = 'force-dynamic';
const run = promisify(execFile);

function authorized(request: Request): boolean {
  const configured = process.env.FC_LOCK_TOKEN;
  const supplied = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '') ?? '';
  if (!configured || !supplied) return false;
  const a = Buffer.from(configured);
  const b = Buffer.from(supplied);
  return a.length === b.length && timingSafeEqual(a, b);
}

async function ledger(args: string[]) {
  const cwd = process.cwd();
  const script = path.join(cwd, 'scripts', 'fc-manual-lock.py');
  const python = process.env.FC_PYTHON || 'python3';
  try {
    const { stdout } = await run(python, [script, ...args], { cwd, timeout: 20000, maxBuffer: 1024 * 1024 });
    return JSON.parse(stdout.trim().split('\n').at(-1) || '{}');
  } catch (error) {
    const output = (error as { stdout?: string }).stdout?.trim().split('\n').at(-1);
    if (output) {
      try { return JSON.parse(output); } catch { /* Report a generic error. */ }
    }
    return { status: 'error', message: 'Ledger settlement tidak tersedia.' };
  }
}

export async function GET(request: Request) {
  if (!authorized(request)) return NextResponse.json({ message: 'Token operator tidak valid atau belum dikonfigurasi.' }, { status: 401 });
  const result = await ledger(['list']);
  return NextResponse.json(result, { status: result.status === 'ok' ? 200 : 503 });
}

export async function POST(request: Request) {
  if (!authorized(request)) return NextResponse.json({ message: 'Token operator tidak valid atau belum dikonfigurasi.' }, { status: 401 });
  let body: Record<string, unknown>;
  try { body = await request.json(); } catch { return NextResponse.json({ message: 'JSON tidak valid.' }, { status: 400 }); }
  if (body.mode === 'singles' || body.mode === 'parlay') {
    const choices = body.choices;
    if (!Array.isArray(choices) || choices.length < (body.mode === 'parlay' ? 2 : 1) || choices.length > 30 ||
        !choices.every((item) => item && typeof item.match_id === 'string' && item.match_id.length <= 100 &&
          typeof item.market === 'string' && ['1x2', 'ah', 'ou', 'btts'].includes(item.market) &&
          typeof item.pick === 'string' && item.pick.length <= 100 &&
          typeof item.odds === 'number' && Number.isFinite(item.odds))) {
      return NextResponse.json({ message: 'Batch pilihan tidak valid.' }, { status: 400 });
    }
    const result = await ledger(['batch', '--payload', JSON.stringify({ mode: body.mode, choices })]);
    return NextResponse.json(result, { status: result.status === 'locked' ? 200 : 409 });
  }
  const { match_id, market, pick, odds } = body;
  if (typeof match_id !== 'string' || match_id.length > 100 ||
      typeof market !== 'string' || !['1x2', 'ah', 'ou', 'btts'].includes(market) ||
      typeof pick !== 'string' || pick.length > 100 ||
      typeof odds !== 'number' || !Number.isFinite(odds)) {
    return NextResponse.json({ message: 'Pilihan tidak valid.' }, { status: 400 });
  }
  const result = await ledger(['create', '--match-id', match_id, '--market', market, '--pick', pick, '--odds', String(odds)]);
  return NextResponse.json(result, { status: result.status === 'locked' ? 200 : 409 });
}
