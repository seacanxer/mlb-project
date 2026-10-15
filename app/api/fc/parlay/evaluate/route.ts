import { NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';
import { z } from 'zod';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
const run = promisify(execFile);
const schema = z.union([z.object({ mode: z.literal('build') }).strict(), z.object({ choices: z.array(z.object({
  match_id: z.string().min(1).max(100), market: z.string().min(1).max(30),
  pick: z.string().min(1).max(100), odds: z.number().finite().gt(1),
}).strict()).min(2).max(8) }).strict()]);

/** Read-only preview. Clients supply identifiers, never probabilities or EV. */
export async function POST(request: Request) {
  let parsed: ReturnType<typeof schema.safeParse>;
  try { parsed = schema.safeParse(await request.json()); }
  catch { return NextResponse.json({ message: 'JSON tidak valid.' }, { status: 400 }); }
  if (!parsed.success) return NextResponse.json({ message: 'Pilih 2–8 leg dengan odds yang valid.' }, { status: 400 });
  const venv = path.join(process.cwd(), 'betting-machine-fc', 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const python = process.env.FC_PYTHON || (fs.existsSync(venv) ? venv : process.platform === 'win32' ? 'python' : 'python3');
  try {
    const { stdout } = await run(python, [path.join(process.cwd(), 'scripts', 'fc-evaluate-parlay.py'),
      '--payload', JSON.stringify(parsed.data)], { cwd: process.cwd(), timeout: 15000, maxBuffer: 1024 * 1024 });
    return NextResponse.json(JSON.parse(stdout.trim().split('\n').at(-1)!));
  } catch (error) {
    const stdout = (error as { stdout?: string }).stdout;
    if (stdout) {
      try { return NextResponse.json(JSON.parse(stdout.trim().split('\n').at(-1)!), { status: 409 }); }
      catch { /* Do not expose runtime paths or credentials. */ }
    }
    return NextResponse.json({ message: 'Evaluasi parlay tidak tersedia.' }, { status: 503 });
  }
}
