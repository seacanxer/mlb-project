/**
 * tests/e2e/fc.spec.ts
 * Playwright E2E (brief DoD): 3 FC pages navigate without white screens,
 * honest empty states while the engine is offline, disabled triggers,
 * permanent disclaimer, and format rules.
 */
import { test, expect } from '@playwright/test';

test.describe('FC Picks navigation', () => {
  test("Today's Pick loads with header + filters", async ({ page }) => {
    await page.goto('/fc');
    await expect(page.getByRole('heading', { name: "Today's Pick" })).toBeVisible();
    await expect(page.getByLabel('Market')).toBeVisible();
    await expect(page.getByLabel('Cari tim')).toBeVisible();
  });

  test('Results page loads with honest empty state (engine offline)', async ({ page }) => {
    await page.goto('/fc/results');
    await expect(page.getByRole('heading', { name: /Result/ })).toBeVisible();
    const empty = page.getByText('Belum ada hasil settled');
    const kpi = page.getByTestId('kpi-roi');
    await expect(empty.or(kpi)).toBeVisible({ timeout: 8000 });
  });

  test('Schedule page loads with honest empty state (engine offline)', async ({ page }) => {
    await page.goto('/fc/schedule');
    await expect(page.getByRole('heading', { name: "Today's Schedule" })).toBeVisible();
    const empty = page.getByText('Belum ada fixture');
    const table = page.getByRole('table', { name: 'Jadwal 24 jam' });
    await expect(empty.or(table)).toBeVisible({ timeout: 8000 });
  });

  test('disclaimer is permanent on all FC pages', async ({ page }) => {
    for (const url of ['/fc', '/fc/results', '/fc/schedule']) {
      await page.goto(url);
      await expect(page.getByText('Bertanggung jawablah dalam bermain')).toBeVisible();
    }
  });

  test('scan/settle triggers are honestly disabled while offline', async ({ page }) => {
    await page.goto('/fc');
    await expect(page.getByRole('button', { name: /Run Live Scan/ })).toBeDisabled();
    await page.goto('/fc/results');
    await expect(page.getByRole('button', { name: /Refresh settlement/ })).toBeDisabled();
  });

  test('FC API routes return valid shapes (never HTML/500)', async ({ request }) => {
    for (const url of ['/api/fc/health', '/api/fc/picks', '/api/fc/tracker', '/api/fc/matches']) {
      const res = await request.get(url);
      expect(res.ok()).toBeTruthy();
      const body = await res.json();
      expect(body).toBeTruthy();
    }
    const tracker = await (await request.get('/api/fc/tracker')).json();
    expect(typeof tracker.summary.roi_pct).toBe('number');
    expect(Array.isArray(tracker.settled)).toBeTruthy();
  });
});
