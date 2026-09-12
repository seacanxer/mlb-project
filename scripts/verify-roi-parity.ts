/**
 * scripts/verify-roi-parity.ts (brief §10.2 — wajib sebelum M3 ditutup)
 *
 * Dashboard adalah CERMIN, bukan kalkulator kedua: skrip ini membuktikan
 * angka ROI yang dirender di /fc/results identik dengan GET /api/fc/tracker
 * mentah (1 desimal, tanpa transformasi).
 *
 * Usage (di VPS / CI, saat dev server jalan):
 *   npx tsx scripts/verify-roi-parity.ts --base-url http://localhost:3000
 */
import { chromium } from '@playwright/test';

async function main() {
  const baseUrl = process.argv.find((a) => a.startsWith('--base-url='))?.split('=')[1] ?? 'http://localhost:3000';

  const trackerRes = await fetch(`${baseUrl}/api/fc/tracker`);
  if (!trackerRes.ok) throw new Error(`tracker fetch failed (${trackerRes.status})`);
  const tracker = (await trackerRes.json()) as { summary: { roi_pct: number; settled_picks: number } };
  const expected = Number(tracker.summary.roi_pct).toFixed(1);

  const browser = await chromium.launch();
  try {
    const pg = await browser.newPage();
    await pg.goto(`${baseUrl}/fc/results`, { waitUntil: 'networkidle' });
    if (tracker.summary.settled_picks === 0) {
      await pg.getByText('Belum ada hasil settled').waitFor({ timeout: 10000 });
      console.log('ROI parity: SKIP (no settled bets — empty state honest, nothing to compare).');
      return;
    }
    const kpi = pg.getByTestId('kpi-roi');
    await kpi.waitFor({ timeout: 10000 });
    const rendered = ((await kpi.textContent()) ?? '').replace('%', '').trim();
    if (rendered !== expected) {
      throw new Error(`ROI parity GAGAL: UI menampilkan ${rendered}%, tracker mentah ${expected}%`);
    }
    console.log(`ROI parity OK: ${expected}%`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
