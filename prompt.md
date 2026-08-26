# Coding-Agent Master Prompt - Standalone MLB Analytics Website

You are a senior full-stack engineer, data engineer, and test engineer. Build a working standalone MLB analytics website from the requirements below.

This product must not include Hermes, LLMs, AI review, chat, model routing, agent gateways, or any AI dependency. Do not add placeholder AI features.

If these files are available in the repository, treat them as the product source of truth:

- `mlb-website-core-framework.md`
- `mlb-website-prd.md`

If this prompt conflicts with an existing repository convention, preserve the repository's working architecture unless that would violate a product requirement. Explain any material deviation.

## 1. Required outcome

Deliver a production-quality vertical slice that:

- loads a daily MLB slate;
- ingests or loads schedule, starters, pitcher stats, team stats, odds, park factors, and results;
- preserves source lineage and freshness;
- runs deterministic Moneyline Combo Score v2.0;
- runs experimental O/U Formula v2.3;
- applies hard `SKIP`, `NO BET`, `NEEDS DATA`, and `INVALIDATED` rules;
- displays every formula input and intermediate calculation;
- locks pregame forecasts and grades them after official results;
- includes versioned configuration and chronological backtesting;
- works end to end with demo fixtures when real odds are unavailable.

Do not stop at a mockup. Implement data contracts, calculation engine, persistence, user interface, tests, and documentation.

## 2. Scope

### Build

- Full-game Moneyline analysis.
- Full-game Over/Under analysis.
- Daily Slate, Match Detail, Data Health, Forecast History, Backtest, and Settings.
- MLB Stats API adapters.
- Authorized odds adapter interface plus manual CSV/JSON import.
- Season/source-stamped park-factor provider.
- Immutable observations, snapshots, model runs, forecasts, revisions, results, and settlements.

### Do not build

- Hermes or any AI integration.
- Parlays, slip builder, staking recommendations, player props, run-line, First Five, or futures.
- Bet placement or sportsbook account integration.
- Football/soccer providers.
- Firecrawl, browser scraping, access-control bypasses, or geo-blocking workarounds.
- Executable legacy v1 formulas.
- Claims of guaranteed profit or calibrated probability.

## 3. Technology

Inspect the repository first. If it has no established stack, use:

- Next.js with TypeScript and App Router;
- Tailwind CSS and accessible headless UI components;
- PostgreSQL with Prisma, with SQLite allowed for a zero-config local demo;
- Zod for every external payload and manual import;
- Vitest for unit/integration tests;
- Playwright for critical browser flows.

Use the currently supported stable versions available to the project. Do not perform a broad dependency rewrite when the repository already has a working stack.

Provide `.env.example` with placeholders only:

```dotenv
DATABASE_URL=
ODDS_PROVIDER=
ODDS_API_KEY=
DEFAULT_TIMEZONE=Asia/Jakarta
```

Never commit credentials or expose them to the browser.

## 4. Architecture

Use provider interfaces:

```ts
interface ScheduleProvider {}
interface PitcherStatsProvider {}
interface TeamStatsProvider {}
interface OddsProvider {}
interface ParkFactorProvider {}
interface ResultsProvider {}
```

Pipeline:

```text
ingest
  -> preserve raw observation
  -> normalize
  -> validate
  -> freshness gate
  -> freeze input snapshot
  -> calculate raw model
  -> apply hard gates
  -> attach warnings
  -> publish analysis/abstention
  -> lock forecast before first pitch
  -> ingest official result
  -> grade settlement
  -> update versioned backtest
```

All jobs must be idempotent. Use provider IDs, effective timestamps, and raw checksums to prevent duplicates. Retry transient provider failures with bounded exponential backoff. Validation failures are not retry loops.

## 5. Source policy

Use the public MLB Stats API for:

```text
/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team
/api/v1/people/search?names={name}&sportId=1
/api/v1/people/{id}/stats?stats=season&season={year}&group=pitching
/api/v1/people/{id}/stats?stats=gameLog&season={year}&group=pitching
/api/v1/teams/{id}/stats?stats=season&season={year}&group=hitting
/api/v1/teams/{id}/stats?stats=season&season={year}&group=pitching
/api/v1/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason
```

For odds, implement an authorized provider interface and manual CSV/JSON import. When no provider is configured, use deterministic fixtures and show `ODDS_PROVIDER_NOT_CONFIGURED`. Never invent current prices.

Park factors must come from a replaceable, season-stamped, source-stamped dataset. Do not hard-code disputed historical values in calculation code.

## 6. Canonical data model

Implement at least:

- `Game`
- `Team`
- `Person`
- `Venue`
- `SourceObservation`
- `ProbableStarterObservation`
- `PitcherSnapshot`
- `PitcherGameLogStart`
- `TeamSnapshot`
- `MarketSnapshot`
- `ParkFactorSnapshot`
- `ModelDefinition`
- `ModelConfigVersion`
- `InputSnapshot`
- `ModelRun`
- `ModelWarning`
- `Forecast`
- `ForecastRevision`
- `GameResult`
- `Settlement`

Every source observation includes provider, provider ID/source identifier, `retrievedAt`, `effectiveAt` or season, source timezone where relevant, raw checksum, normalized data, freshness state, and validation warnings.

A model run references immutable input snapshot IDs. Never silently use newer data in an existing run.

## 7. Time and baseball normalization

- Store all event timestamps in UTC.
- Display Asia/Jakarta by default.
- Never assume a source is already ET or WIB; capture or configure source timezone.
- Correctly handle date rollover.

Baseball innings are not decimals:

```text
5.0 IP -> 15 outs
5.1 IP -> 16 outs
5.2 IP -> 17 outs
5.3 IP -> validation error
```

Build a tested innings-to-outs utility and use outs in every ERA calculation.

## 8. Freshness defaults

Store these as versioned configuration:

- team offense/form: stale after 24 hours;
- bullpen season data: stale after 24 hours;
- starter: recheck on main refresh and 2-4 hours before first pitch;
- odds: show age and refresh on main and pregame runs;
- pitcher season/logs: refresh before model run;
- park factor: must match the current season or be explicitly marked fallback.

Critical stale data blocks a forecast.

## 9. Moneyline model - Combo Score v2.0

Evaluate both teams, but a team is eligible only with a positive starter ERA advantage:

```text
EraGap = OpponentStarterERA - CandidateStarterERA
```

If `EraGap <= 0`, final state is `SKIP`.

```text
ComboScore = EraGapPoints
           + OffensePoints
           + GameLogPoints
           + MarketAlignmentPoints
           + TeamFormPoints
```

Maximum: 100.

### 9.1 ERA gap points

```text
gap >= 2.00              -> 35
1.50 <= gap < 2.00       -> 28
1.00 <= gap < 1.50       -> 21
0.50 <= gap < 1.00       -> 14
gap < 0.50               -> 0
```

### 9.2 Offense points

Score AVG and OPS separately and use the lower score:

```text
Elite:   AVG > .260       / OPS > .760       -> 25
Good:    AVG .250-.260    / OPS .730-.760    -> 20
Average: AVG .240-.249    / OPS .720-.729    -> 15
Bad:     AVG .230-.239    / OPS .700-.719    -> 10
Terrible: below Bad minimums                -> 5
```

If the two metrics produce different tiers, emit `OFFENSE_TIER_MISMATCH`.

### 9.3 Last-five points

For each valid start:

```text
GameERA = EarnedRuns * 27 / OutsRecorded
GoodStart = GameERA < 4.00
```

```text
5 good -> 20
4 good -> 16
3 good -> 12
2 good -> 8
1 good -> 4
0 good -> 0
```

Require five valid starts. Fewer than five returns `SKIP: INSUFFICIENT_GAME_LOG`.

Calculate display-only trend from the last three starts:

- monotonically improving game ERA -> `HOT`;
- monotonically worsening -> `COLD`;
- otherwise -> `MIXED`.

Trend cannot override a hard gate.

### 9.4 Market alignment

Keep the anchors in configuration:

```text
ERA gap >= 3.00          -> fair decimal 1.35
2.00 <= gap < 3.00      -> fair decimal 1.50
1.00 <= gap < 2.00      -> fair decimal 1.65
gap < 1.00              -> undefined, 0 points + warning
```

```text
candidate odds <= fair odds        -> 10
difference > 0 and < 0.20          -> 8
difference >= 0.20 and <= 0.30     -> 6
difference > 0.30                  -> 4
market favors ERA-disadvantaged side -> 0 and SKIP
```

Call this a heuristic. Do not label it calibrated fair value or win probability.

### 9.5 Team form

Evaluate in order and take the first complete match:

```text
last-ten wins >= 8 and W3+         -> 10
last-ten wins >= 6 and W1+         -> 8
last-ten wins >= 5                 -> 6
last-ten wins >= 4 and loss streak <= 2 -> 4
otherwise                          -> 2
```

### 9.6 Final tiers

Because there is no AI reviewer, use the stricter operational threshold:

```text
T1: score >= 75
T2: score 55-74
SKIP: score < 55 or any hard gate
```

T1 is not a probability or guarantee.

### 9.7 Moneyline hard skips

- starter TBD, undecided, unconfirmed, or conflicting;
- starter `GS = 0`, reliever, or opener;
- season IP below 60;
- fewer than five valid recent starts;
- candidate offense AVG below .220;
- three or more recent starts with game ERA `>= 4.00`;
- ERA gap zero or negative;
- market favorite is ERA-disadvantaged side;
- price missing or stale;
- critical input missing or stale;
- game already started.

Preserve raw score even when a hard gate changes the final state.

### 9.8 Moneyline warnings

- IP from 60 through 90;
- offense AVG below .230 with ERA gap below 2.00;
- game-log score <= 4;
- large price movement;
- bullpen weakness/workload;
- non-critical source mismatch.

## 10. O/U model - v2.3 experimental

Always show an `Experimental` badge. Gap strength is not proven confidence.

Required inputs:

- market total line and selected-side decimal price;
- away/home R/G;
- both starter season ERA;
- both starter last-five aggregate ERA;
- home-venue park factor;
- starter confirmation and freshness.

Compute last-five aggregate ERA:

```text
LastFiveERA = TotalEarnedRuns * 27 / TotalOutsRecorded
```

Formula:

```text
OffAdj = ((AwayRPG - 4.1) + (HomeRPG - 4.1)) * 0.60

PitchAdj = ((AwayLastFiveERA - AwaySeasonERA)
          + (HomeLastFiveERA - HomeSeasonERA)) * 0.50

ParkAdj = (HomeParkFactor - 1.0) * MarketLine * 2.5

RawTotalAdj = OffAdj + PitchAdj + ParkAdj
TotalAdj = clamp(RawTotalAdj, -3.0, +3.0)
AdjustedTotal = MarketLine + TotalAdj
Gap = AdjustedTotal - MarketLine
```

Use the home venue park factor exactly once.

Minimum selected-side decimal odds: 1.85.

```text
Gap >= +0.75             -> OVER, strong model gap
+0.50 <= Gap < +0.75     -> OVER, RISKY
-0.50 < Gap < +0.50      -> NO BET
-0.75 < Gap <= -0.50     -> UNDER, RISKY
Gap <= -0.75             -> UNDER, strong model gap
selected price < 1.85    -> NO BET
```

Hard gates:

- missing line or selected price;
- unconfirmed/changed/conflicting starter;
- missing season or last-five pitcher data;
- missing/stale team R/G;
- missing/wrong-season/wrong-venue park factor;
- stale odds;
- game already started;
- absolute gap below 0.50;
- selected price below 1.85.

Warnings:

- both starters WHIP below 1.15 on an OVER: `PITCHING_DUEL_RISK`;
- IP 60-90: `BORDERLINE_SAMPLE`;
- large line movement: `LINE_MOVEMENT`;
- bullpen uncertainty: `BULLPEN_CONTEXT_RISK`;
- adjustment cap reached: `EXTREME_PARK_ADJUSTMENT`.

Bullpen data is context only. Do not add it to v2.3 arithmetic.

## 11. Odds utilities

Implement with full precision and round only for display:

```text
negative American -> decimal = 1 + 100 / abs(american)
positive American -> decimal = 1 + american / 100
implied probability = 1 / decimal odds
```

Preserve original format and original price.

## 12. Final-state model

Use typed states, not free-form strings:

- `NEEDS_DATA`
- `INVALIDATED`
- `SKIP`
- `NO_BET`
- `T2`
- `T1`
- `OVER_RISKY`
- `OVER_STRONG_GAP`
- `UNDER_RISKY`
- `UNDER_STRONG_GAP`

Warnings are separate typed codes. A warning does not replace a final state.

## 13. Required screens

### Daily Slate

- date selector and refresh progress;
- game start in WIB;
- starter confirmation;
- market price age;
- Moneyline raw score and final tier/state;
- total line, gap, and O/U state;
- warning/hard-gate count;
- data-health summary.

### Match Detail

- source lineage and freshness;
- starter comparison;
- five Moneyline factor scores;
- O/U OffAdj, PitchAdj, ParkAdj, cap, AdjustedTotal, and Gap;
- hard gates and warnings;
- model/config/input-snapshot IDs;
- forecast/revision/result history.

### Data Health

- provider last success/failure;
- stale, missing, and conflicting fields;
- affected games;
- retry and manual odds import.

### Forecast History

- locked forecast, original line/price, revisions, result, settlement.

### Backtest

- sample size and win/loss/push;
- split by model/config version, tier/signal, gap band, odds band, month;
- ROI only when price and declared stake policy exist;
- maximum drawdown and losing streak when ROI is enabled;
- experimental warning for O/U.

### Settings

- versioned thresholds and freshness;
- fair-price anchors;
- park-factor dataset version;
- timezone;
- immutable configuration history.

## 14. API behavior

Implement equivalent server routes/actions for:

```text
refresh slate by date
read slate
refresh one game
analyze one game or slate
lock model run as forecast
import authorized/manual odds
refresh results
read data health
read backtest
```

Never overwrite a locked forecast. A new observation creates a new input snapshot and model run.

## 15. Demo fixtures

Provide deterministic fixtures for at least:

1. valid T1 Moneyline candidate;
2. T2 candidate;
3. negative ERA-gap `SKIP`;
4. starter `GS = 0` `SKIP`;
5. fewer-than-five-starts `SKIP`;
6. stale odds `NEEDS_DATA`;
7. O/U strong Over gap;
8. O/U risky Under gap;
9. O/U `NO_BET` near zero;
10. O/U adjustment capped at +3.0 or -3.0;
11. starter change invalidation;
12. push settlement on an integer total.

## 16. Tests

Unit test every exact boundary:

- ERA gap: 0.49, 0.50, 0.99, 1.00, 1.49, 1.50, 1.99, 2.00;
- ML tier: 54, 55, 74, 75;
- IP: 59.2, 60.0, 89.2, 90.0;
- odds: American negative/positive, decimal 1.84 and 1.85;
- O/U gap: -0.75, -0.74, -0.50, -0.49, +0.49, +0.50, +0.74, +0.75;
- adjustment clamp: below -3, at -3, at +3, above +3;
- IP parsing: 5.0, 5.1, 5.2, invalid 5.3;
- timezone rollover and provider timezone configuration;
- every hard gate, warning code, invalidation, push, and revision rule.

Add integration tests for ingestion-to-analysis and forecast-to-settlement. Add Playwright tests for Daily Slate, Match Detail, stale-data abstention, locking, and backtest visibility.

## 17. Acceptance criteria

- No fabricated value can appear.
- Every visible value traces to a source observation.
- Every result shows model/config version and source age.
- Missing/stale critical data blocks eligibility.
- Raw score remains visible when a hard gate creates `SKIP`.
- O/U always displays `Experimental`.
- Starter/venue change invalidates affected runs.
- Forecast cannot be locked after first pitch.
- Locked forecast cannot be overwritten.
- App works with demo fixtures and manual odds import.
- No Hermes, LLM, AI-review, or chat dependency exists.
- No secret is in logs, client code, screenshots, exports, or committed files.
- Lint, type checks, unit tests, integration tests, browser tests, and production build pass.
- README explains setup, formulas, providers, limitations, daily workflow, and how to replace fixtures with authorized data.

## 18. Design

Use a data-dense but calm visual system:

- navy for structure;
- blue for information;
- amber for warnings;
- red for blocking states;
- green only for validated data or settled success, never guaranteed future outcomes.

Meet WCAG 2.1 AA. Support keyboard navigation, mobile layouts, loading states, empty states, and recoverable errors. Do not communicate state by color alone.

## 19. Implementation sequence

1. Inspect the repository and report the current architecture.
2. Write a concise implementation plan and data-contract proposal.
3. Add schema, model/config registry, and provider interfaces.
4. Add fixtures and normalization utilities.
5. Implement Moneyline/O/U engines, hard gates, warnings, and tests.
6. Build Daily Slate, Match Detail, and Data Health.
7. Add forecast locking, revisions, results, and settlements.
8. Add Backtest and Settings.
9. Run formatting, lint, type checks, tests, accessibility checks, and production build.
10. Report changed files, test evidence, unresolved production-provider decisions, and exact setup steps.

Use reasonable fixture-backed assumptions when production credentials or provider choices are unavailable. Do not invent live data. Stop and ask only when a missing decision would materially change the architecture or create external cost/risk.


