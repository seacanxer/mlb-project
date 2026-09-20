import { test, expect, type Page } from '@playwright/test';
import type { DetailedMatch, ForecastPick } from '../../lib/fc/types';

const start = Math.floor(Date.now() / 1000) + 7200;
const fixture = (id: string, home: string, away: string, league: string, projections = true): DetailedMatch => {
  const picks: ForecastPick[] = ([['1x2', 'Home', .58, 1.9, .102], ['ah', 'AH Home -0.5', .58, 1.95, .131], ['ou', 'Over 2.5', .61, 1.82, .1102], ['btts', 'BTTS Yes', .52, 1.78, -.0744]] as const).map(([market, pick, probability, odds, ev]) => ({
    match_id: id, match: `${home} vs ${away}`, home, away, league, start_ts: start, market, pick,
    probability, odds, ev, conservative_ev: ev - .02, fair_odds: 1 / probability, is_top_pick: false,
    selection_status: 'watch', tier: 'watch', decision: 'watch', coverage_status: 'full', calibrated_prob: null,
    analysis_status: ev > .03 ? 'value_candidate' : 'forecast', gate_reasons: ev > .03 ? [] : ['EV_BELOW_VALUE_THRESHOLD'],
  }));
  return { info: { match_id: id, home, away, league, start_ts: start, coverage_status: projections ? 'full' : 'market_only' }, projections: projections ? picks : [],
    qualified_picks: projections ? picks.filter((p) => p.ev > .03) : [], market_options: projections ? picks : [],
    analysis: { status: projections ? 'ready' : 'unavailable', reason_codes: projections ? [] : ['TEAM_UNMATCHED'], official_enabled: false, official_reason: 'MODEL_NOT_VALIDATED', model_goals: projections ? { home: 1.92, away: 1.28 } : undefined, league_model: 'E0' } };
};
const matches = [fixture('101', 'Arsenal', 'Brighton & Hove Albion', 'England. Premier League'), fixture('102', 'Internazionale Milano', 'Fiorentina', 'Italy. Serie A'), fixture('103', 'Unknown United', 'Example City', 'Japan. J1 League', false)];

async function mockApi(page: Page, rows = matches) {
  await page.route('**/api/fc/matches?*', (route) => route.fulfill({ json: { matches: rows, count: rows.length, pagination: { total: rows.length, limit: 200, offset: 0 } } }));
  await page.route('**/api/fc/health', (route) => route.fulfill({ json: { engine_offline: false, formula_version: 'dc-loglink-time-decay-v1', scan_state: { diagnostics: {}, last_scan_time: null } } }));
}

test('four-market board, unavailable state, filters and saved selections work', async ({ page }) => {
  await mockApi(page);
  await page.goto('/fc/schedule');
  await expect(page.getByRole('heading', { name: 'Daftar Prediksi Pertandingan' })).toBeVisible();
  await expect(page.locator('.prediction-card')).toHaveCount(3);
  await expect(page.locator('.prediction-card').first().locator('.prediction-selection')).toHaveCount(4);
  await expect(page.locator('.prediction-card').last().locator('.prediction-selection')).toHaveCount(0);
  await expect(page.getByText('Identitas tim belum cocok dengan histori liga.').first()).toBeVisible();
  await expect(page.locator('.fc-navigation .active')).toHaveCount(1);
  await page.getByRole('button', { name: 'Simpan Over 2.5', exact: true }).first().click();
  await expect(page.locator('.prediction-watchlist li')).toHaveCount(1);
  await page.reload();
  await expect(page.locator('.prediction-watchlist li')).toHaveCount(1);
  await page.getByRole('button', { name: 'Value picks', exact: true }).click();
  await expect(page.locator('.prediction-card')).toHaveCount(2);
  await expect(page.locator('.prediction-card').first().locator('.prediction-selection')).toHaveCount(3);
  await page.getByLabel('Cari pertandingan', { exact: true }).fill('No such team');
  await expect(page.getByText('Tidak ada pertandingan untuk filter ini')).toBeVisible();
  await page.getByRole('button', { name: 'Reset filter' }).click();
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/fc-market-board-desktop.png', fullPage: true });
});

test('mobile board has no horizontal overflow and all markets remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/fc/schedule');
  await expect(page.locator('.prediction-card').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Simpan Over 2.5', exact: true }).first().click();
  await expect(page.locator('.prediction-watchlist li')).toHaveCount(1);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/fc-market-board-mobile.png', fullPage: true });
});

test('all FC entry points use the new board and empty fixtures remain honest', async ({ page }) => {
  await mockApi(page, []);
  for (const [path, title] of [['/fc', 'Value Picks'], ['/fc/analyzer', 'Analisis Pasar'], ['/fc/schedule', 'Prediksi Pertandingan']]) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.locator('[data-ui-version="fc-market-board-v2"]')).toBeVisible();
    await expect(page.locator('.prediction-card')).toHaveCount(0);
    await expect(page.locator('.fc-navigation .active')).toHaveCount(1);
  }
});
