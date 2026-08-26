# MLB Analytics Website

A **standalone, deterministic** MLB analytics website. No AI, no Hermes, no LLMs. All decisions come from versioned formulas and explicit rules.

> **Disclaimer**: T1/T2 are score tiers, not win probabilities or profit guarantees. Unified MLB Totals v4.0 is experimental — gap labels describe formula output, not calibrated confidence. A `SKIP`, `NO BET`, or `NEEDS DATA` result is a valid output.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 14 (App Router) + TypeScript |
| Styling | Tailwind CSS + custom CSS design system |
| Database | PostgreSQL via Prisma |
| Validation | Zod on every external payload and import |
| Unit tests | Vitest |
| Browser tests | Playwright |

---

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Copy env file
cp .env.example .env.local
# Edit .env.local: set DATABASE_URL and DIRECT_URL for PostgreSQL

# 3. Create database and run migrations
npx prisma migrate dev

# 4. Seed demo fixtures (12 scenarios)
npx tsx prisma/seed.ts

# 5. Start dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Daily Workflow

| Time (WIB) | Action |
|---|---|
| 22:00–00:00 | Reconnaissance — check slate, no final forecast |
| 06:00–08:00 | Main refresh — click ↻ on Daily Slate |
| 2–4 h pregame | Confirmation — refresh again before locking |
| After games final | Results — POST /api/results/refresh to grade |

### Locking a Forecast

1. Verify starters are confirmed and odds are fresh.
2. Use **Lock ML/O/U** beside one pick, or **Lock All Picks** for the slate. Results also has a bulk lock button.
3. Locks are immutable and only allowed before first pitch; one authoritative lock is retained per game/model.
4. Use **Fetch Final Scores** on Results after games finish. Official MLB scores auto-grade WIN/LOSS/PUSH.

On an off-day, use **Find next MLB slate** to scan forward up to 30 days and load
the first scheduled slate automatically.

---

## Formulas

### Moneyline Combo Score v2.0

```
EraGap = OpponentStarterERA - CandidateStarterERA
ComboScore = EraGapPoints + OffensePoints + GameLogPoints + MarketAlignmentPoints + TeamFormPoints

T1: score >= 70 (subject to sample-size and market-disagreement confidence caps)
T2: score 55–74
SKIP: score < 55 or any hard gate
```

- **ERA Gap Points** (max 35): 5-band table from 0.49 → 0 pts to ≥ 2.00 → 35 pts
- **Offense Points** (max 25): Lower of AVG-tier and OPS-tier scores
- **Pitcher Last Five** (max 20): Per-start `GameERA = ER * 27 / outs`; good start < 4.00
- **Market Alignment** (max 10): Heuristic anchors vs candidate price
- **Team Form** (max 10): Last-10 record and current streak

### Unified MLB Totals v4.0 — ⚗ Experimental

```
BlendedStarterERA = 70% season ERA + 30% aggregate last-five ERA
StaffRuns = starter contribution + bullpen contribution + capped WHIP adjustment
AwayRuns = 50% AwayRPG + 50% HomeStaffRunsAllowed
HomeRuns = 50% HomeRPG + 50% AwayStaffRunsAllowed
IndependentTotal = (AwayRuns + HomeRuns) * reliability-adjusted park factor
ProjectedTotal = 50% CurrentMarketTotal + 50% IndependentTotal
Gap = ProjectedTotal - CurrentMarketTotal
```

| Gap | Signal |
|---|---|
| ≥ +0.80 | OVER — strong model gap |
| +0.40 to +0.79 | OVER — RISKY |
| +0.25 to +0.39 | OVER — LEAN (watchlist only) |
| −0.24 to +0.24 | NO BET |
| −0.39 to −0.25 | UNDER — LEAN (watchlist only) |
| −0.79 to −0.40 | UNDER — RISKY |
| ≤ −0.80 | UNDER — strong model gap |

Minimum selected-side decimal odds: **1.85**.

---

## Providers

### MLB Stats API (no key required)

The following public routes are used automatically:

```
/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team
/api/v1/people/{id}/stats?stats=season&season={year}&group=pitching
/api/v1/people/{id}/stats?stats=gameLog&season={year}&group=pitching
/api/v1/teams/{id}/stats?stats=season&season={year}&group=hitting
/api/v1/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason
/api/v1.1/game/{gamePk}/feed/live
```

The live feed is used for results because it exposes both the official game
status and linescore. A result is stored and graded only when MLB reports
`abstractGameState: Final`; scheduled, live, empty, or partial linescores are ignored.

### Odds Provider

Configure in `.env.local`:

```dotenv
ODDS_PROVIDER=the-odds-api
ODDS_API_KEY=your-key
ODDS_REGIONS=us
# Optional: pin one bookmaker key (otherwise the freshest returned book is used)
ODDS_BOOKMAKER=
```

The refresh uses The Odds API's `baseball_mlb` feed with `h2h,totals` markets and matches
events to MLB game IDs by home team, away team, and start time. A key is required and API
usage may be metered by your provider plan. If it is not configured, the UI shows
`ODDS_PROVIDER_NOT_CONFIGURED`; schedule and official stats still load, and you can use
**manual import** instead:

An optional unofficial adapter supplied by the user is also available:

```dotenv
ODDS_PROVIDER=1xbit
ODDS_1XBIT_DOMAINS=https://1xbit.com
```

It is deliberately labeled `1xbit-linefeed-unofficial`, filters the mixed
baseball feed to `USA. MLB`, and requires both teams plus start time to match the
authoritative MLB schedule. The feed has no quote-update timestamp and is a
reverse-engineered endpoint, so every observation carries explicit data-quality
warnings. Do not treat it as equivalent to a licensed odds feed.

```bash
curl -X POST http://localhost:3000/api/odds/import \
  -H "Content-Type: application/json" \
  -d '[{"gameId":"GAME_ID","moneylineHomeOrig":"-130","moneylineAwayOrig":"+110","totalLine":8.5,"totalOverOrig":"-110","totalUnderOrig":"-110"}]'
```

Accepts American (`-145`, `+125`) or decimal (`1.69`) odds strings. **Credentials are never exposed to the browser.**

### Bullpen Provider

Enable the official MLB active-roster aggregation in `.env.local`:

```dotenv
BULLPEN_PROVIDER=mlb-roster
```

The provider hydrates season pitching stats in one roster request per team,
keeps active-roster pitchers with zero season starts, and aggregates ERA/WHIP
from exact outs, earned runs, hits, and walks. It does not average individual
ERA/WHIP values or parse baseball IP notation as a decimal.

This is an active-roster, pure-reliever approximation. Pitchers with one or
more season starts are excluded because the public season endpoint does not
separate their starting and relief innings. Each observation records
`BULLPEN_ACTIVE_ROSTER_AT_FETCH_TIME` and the number of excluded swingmen, so
historical refreshes must not be mistaken for historical roster snapshots.

The **Analysis Data → Refresh & Scrape** button runs schedule, team, bullpen,
pitcher, odds, analysis, and final-result refreshes for the selected slate.

### Park Factors

Stored in `ParkFactorSnapshot` table, seeded via `prisma/seed.ts`. Replace by inserting a new row for the current season — no code release required. The engine uses the exact-season row and falls back to the most recent, marking it as a fallback.

The MLB schedule, live-feed, The Odds API, and ESPN scoreboard endpoints do not
provide a validated park-factor metric. Do not derive one from venue identity,
weather, or a single-game score. A season-stamped external dataset is still required.

### ESPN Quality Fallback

`https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard` can be
useful as a secondary schedule/score cross-check, but it is not an authoritative
replacement for MLB data. It currently returns HTTP 403 from this project's local
worker environment, so it is not wired as an automatic dependency.

---

## Demo Fixtures

12 deterministic scenarios are seeded automatically:

| # | Scenario | Expected ML | Expected O/U |
|---|---|---|---|
| 1 | T1 strong candidate | T1 | NO_BET |
| 2 | T2 watchlist | T2 | NO_BET |
| 3 | Negative ERA gap | SKIP | NO_BET |
| 4 | GS=0 reliever | SKIP | NO_BET |
| 5 | < 5 starts | SKIP | NO_BET |
| 6 | Stale odds | SKIP | NO_BET |
| 7 | O/U strong Over | SKIP | OVER_STRONG_GAP |
| 8 | O/U risky Under | SKIP | UNDER_RISKY |
| 9 | O/U near zero | SKIP | NO_BET |
| 10 | O/U cap +3.0 | SKIP | OVER_STRONG_GAP |
| 11 | Starter change | INVALIDATED | INVALIDATED |
| 12 | Push settlement | T2 | NO_BET |

Load them by visiting `/` and selecting **2025-08-25**.

---

## Running Tests

```bash
# Unit tests (99 boundary tests)
npm test

# Type check
npm run typecheck

# Lint
npm run lint

# Production build
npm run build

# Browser tests (requires running dev server)
npx playwright install chromium
npm run test:e2e
```

---

## Limitations

- **Unified MLB Totals v4.0 is experimental.** No calibrated track record yet. Gap labels are not probabilities.
- **Park factors** in demo fixtures are approximate. Provide a season-stamped authoritative dataset for production.
- **Backtest ROI** is hidden until a flat-stake policy and full price history are configured.
- The app does not place bets, manage funds, or integrate with any sportsbook.
- No output from this app is a guarantee of profit.

---

## Production Deployment

1. Set `DATABASE_URL` to a PostgreSQL connection string.
2. Run `npx prisma migrate deploy`.
3. Set `ODDS_PROVIDER` and `ODDS_API_KEY`.
4. Run `npm run build && npm start`.
5. Configure a cron or scheduled job to call `/api/slates/{date}/refresh` and `/api/results/refresh`.

---

## Architecture

```
lib/
  config/modelConfig.ts     ← Versioned thresholds (single source of truth)
  engine/
    moneyline.ts            ← Combo Score v2.0
    overunderUnified.ts     ← single active Unified MLB Totals v4.0 engine
    types.ts                ← FinalState, WarningCode, HardGateCode enums
    pipeline.ts             ← Ingest → snapshot → run → publish
    forecast.ts             ← Lock, grade, settle
  providers/
    interfaces.ts           ← 6 typed provider interfaces
    mlbStatsApi.ts          ← MLB Stats API adapters
    oddsProvider.ts         ← Stub + manual import
    parkFactorProvider.ts   ← DB-backed season-stamped dataset
  utils/
    innings.ts              ← IP → outs normalization (tested)
    odds.ts                 ← American ↔ decimal conversion (tested)
    timezone.ts             ← UTC storage, WIB display
  fixtures/demoFixtures.ts  ← 12 deterministic scenarios
prisma/schema.prisma        ← 19-entity canonical data model
app/                        ← Next.js App Router pages + API routes
tests/unit/                 ← 99 boundary tests (Vitest)
tests/e2e/                  ← Playwright browser tests
```
