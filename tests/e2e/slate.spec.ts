/**
 * tests/e2e/slate.spec.ts
 * Playwright E2E: Daily Slate smoke tests.
 */

import { test, expect } from '@playwright/test';

test.describe('Daily Slate', () => {
  test('loads the daily slate page', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Daily Slate' })).toBeVisible();
    await expect(page.getByLabel('Slate date')).toBeVisible();
    await expect(page.getByRole('button', { name: /Refresh/i })).toBeVisible();
  });

  test('shows demo fixtures for 2025-08-25', async ({ page }) => {
    await page.goto('/');
    // Set date to demo seed date
    await page.locator('#slate-date').fill('2025-08-25');
    await page.waitForTimeout(500);
    // Table should appear or empty state
    const table = page.getByRole('table', { name: 'Daily slate' });
    const empty = page.getByText('No games found');
    await expect(table.or(empty)).toBeVisible({ timeout: 5000 });
  });

  test('nav links are present', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Daily Slate' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Data Health' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Forecast History' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Backtest' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  });
});

test.describe('Data Health', () => {
  test('loads provider status', async ({ page }) => {
    await page.goto('/data-health');
    await expect(page.getByRole('heading', { name: 'Data Health' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Provider status' })).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('mlb-stats-api')).toBeVisible();
  });
});

test.describe('Settings', () => {
  test('shows ERA gap points table', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('table', { name: /ERA gap points/i })).toBeVisible();
    // 35 pts should be in the table
    await expect(page.getByText('35')).toBeVisible();
  });

  test('shows O/U parameters', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('O/U v2.3')).toBeVisible();
    await expect(page.getByText('±3')).toBeVisible();
  });
});

test.describe('Backtest', () => {
  test('loads backtest page', async ({ page }) => {
    await page.goto('/backtest');
    await expect(page.getByRole('heading', { name: 'Backtest Dashboard' })).toBeVisible();
    // Either the table or the empty state should be present
    const tableOrEmpty = page.getByRole('table').or(page.getByText('No settled forecasts'));
    await expect(tableOrEmpty).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Forecast History', () => {
  test('loads forecast history page', async ({ page }) => {
    await page.goto('/forecast-history');
    await expect(page.getByRole('heading', { name: 'Forecast History' })).toBeVisible();
  });
});
