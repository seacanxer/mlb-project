// scripts/worker.ts
//
// Standalone background data worker for MLB Analytics.
// Runs on configurable cron schedules to keep the database fresh.
//
// Usage:
//   npm run worker        - Start cron-based background worker
//   npm run worker:once   - Run a single immediate refresh cycle
//
// Environment variables:
//   WORKER_SLATE_CRON      Cron expression for slate refresh (default: every 3 hours)
//   WORKER_RESULTS_CRON    Cron expression for results/grading (default: every 6 hours)
//   WORKER_STARTUP_REFRESH Run immediate refresh on startup (default: "true")
//   WORKER_LOOKBACK_DAYS   How many days back to check for unsettled results (default: "3")

import cron from 'node-cron';
import { refreshSlate, refreshResults } from '../lib/services/slateIngestion';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SLATE_CRON = process.env.WORKER_SLATE_CRON ?? '0 */3 * * *';
const RESULTS_CRON = process.env.WORKER_RESULTS_CRON ?? '30 */6 * * *';
const STARTUP_REFRESH = (process.env.WORKER_STARTUP_REFRESH ?? 'true') === 'true';
const LOOKBACK_DAYS = parseInt(process.env.WORKER_LOOKBACK_DAYS ?? '3', 10);
const IS_ONCE = process.argv.includes('--once');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function todayET(): string {
  // MLB schedule dates are in Eastern Time
  const now = new Date();
  const etFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return etFormatter.format(now); // YYYY-MM-DD
}

function dateOffset(baseDate: string, offsetDays: number): string {
  const d = new Date(`${baseDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function timestamp(): string {
  return new Date().toISOString().slice(11, 19);
}

function log(tag: string, message: string): void {
  console.log(`[${timestamp()}] [${tag}] ${message}`);
}

function logError(tag: string, message: string, error?: unknown): void {
  const detail = error instanceof Error ? error.message : String(error ?? '');
  console.error(`[${timestamp()}] [${tag}] ❌ ${message}${detail ? ': ' + detail : ''}`);
}

// ---------------------------------------------------------------------------
// Refresh cycle
// ---------------------------------------------------------------------------

async function runSlateRefresh(): Promise<void> {
  const date = todayET();
  log('SLATE', `Refreshing slate for ${date}...`);

  try {
    const result = await refreshSlate(date);
    log('SLATE', [
      `✅ ${result.scheduleGames} games`,
      `${result.pitcherSnapshots} pitcher snapshots`,
      `${result.teamSnapshots} team snapshots`,
      `${result.bullpenSnapshots} bullpen snapshots`,
      `${result.oddsSnapshots} odds snapshots`,
      `${result.analyzed} analyzed`,
      result.analysisErrors > 0 ? `⚠ ${result.analysisErrors} analysis errors` : '',
      result.warnings.length > 0 ? `⚠ ${result.warnings.length} warnings` : '',
    ].filter(Boolean).join(' | '));

    if (result.errors.length > 0) {
      for (const err of result.errors.slice(0, 5)) {
        logError('SLATE', `[${err.scope}] ${err.message}`);
      }
      if (result.errors.length > 5) {
        log('SLATE', `  ... and ${result.errors.length - 5} more errors`);
      }
    }
  } catch (error) {
    logError('SLATE', `Slate refresh failed for ${date}`, error);
  }
}

async function runResultsRefresh(): Promise<void> {
  const today = todayET();
  log('RESULTS', `Checking results for last ${LOOKBACK_DAYS} days...`);

  let totalSettled = 0;

  for (let offset = 0; offset >= -LOOKBACK_DAYS; offset--) {
    const date = dateOffset(today, offset);
    try {
      const result = await refreshResults(date);
      if (result.settled > 0) {
        log('RESULTS', `  ${date}: ${result.settled} games settled`);
        totalSettled += result.settled;
      }
      if (result.errors.length > 0) {
        for (const err of result.errors) {
          logError('RESULTS', `  ${date} [${err.gameId}]`, new Error(err.message));
        }
      }
    } catch (error) {
      logError('RESULTS', `Results refresh failed for ${date}`, error);
    }
  }

  log('RESULTS', `✅ Total settled: ${totalSettled}`);
}

async function runFullCycle(): Promise<void> {
  log('WORKER', '━━━ Starting full refresh cycle ━━━');
  await runSlateRefresh();
  await runResultsRefresh();
  log('WORKER', '━━━ Refresh cycle complete ━━━');
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('');
  console.log('  ⚾ MLB Analytics Data Worker');
  console.log('  ════════════════════════════════');
  console.log(`  Mode:           ${IS_ONCE ? 'Single run (--once)' : 'Cron scheduler'}`);
  console.log(`  Slate cron:     ${SLATE_CRON}`);
  console.log(`  Results cron:   ${RESULTS_CRON}`);
  console.log(`  Lookback days:  ${LOOKBACK_DAYS}`);
  console.log(`  Startup refresh: ${STARTUP_REFRESH}`);
  console.log(`  Odds provider:  ${process.env.ODDS_PROVIDER || '(not configured)'}`);
  console.log(`  Bullpen provider: ${process.env.BULLPEN_PROVIDER || '(not configured)'}`);
  console.log('');

  if (IS_ONCE) {
    await runFullCycle();
    process.exit(0);
  }

  // Validate cron expressions
  if (!cron.validate(SLATE_CRON)) {
    console.error(`Invalid WORKER_SLATE_CRON: "${SLATE_CRON}"`);
    process.exit(1);
  }
  if (!cron.validate(RESULTS_CRON)) {
    console.error(`Invalid WORKER_RESULTS_CRON: "${RESULTS_CRON}"`);
    process.exit(1);
  }

  // Schedule cron jobs
  cron.schedule(SLATE_CRON, () => {
    runSlateRefresh().catch((error) => logError('CRON', 'Unhandled slate refresh error', error));
  }, { timezone: 'America/New_York' });
  log('CRON', `Slate refresh scheduled: ${SLATE_CRON} (ET)`);

  cron.schedule(RESULTS_CRON, () => {
    runResultsRefresh().catch((error) => logError('CRON', 'Unhandled results refresh error', error));
  }, { timezone: 'America/New_York' });
  log('CRON', `Results refresh scheduled: ${RESULTS_CRON} (ET)`);

  // Startup refresh
  if (STARTUP_REFRESH) {
    log('WORKER', 'Running startup refresh...');
    await runFullCycle();
  }

  log('WORKER', '🟢 Worker is running. Press Ctrl+C to stop.');

  // Graceful shutdown
  const shutdown = () => {
    log('WORKER', '🔴 Shutting down...');
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((error) => {
  console.error('Fatal worker error:', error);
  process.exit(1);
});
