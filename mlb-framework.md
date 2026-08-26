# MLB Analytics Website - Core Framework

Version: 1.0  
Status: Standalone website specification  
Default display timezone: Asia/Jakarta  
Primary markets: Moneyline and full-game Over/Under

## 1. Purpose

Build a transparent MLB decision-support website that collects current game data, validates it, runs deterministic formulas, explains every result, abstains when evidence is weak, and tracks forecasts against final results.

The website is not a betting execution product and does not promise profitability. A `SKIP`, `NO BET`, or `NEEDS DATA` result is a valid output.

## 2. Scope decisions

### Included

- Daily MLB schedule and game status.
- Probable and confirmed starting pitchers.
- Pitcher season ERA, WHIP, innings pitched, games started, and last-five game logs.
- Team AVG, OPS, runs per game, record, last ten, and streak.
- Bullpen ERA and WHIP as context and warnings.
- Market Moneyline and full-game total line/price.
- Season-stamped home-venue park factors.
- Moneyline Combo Score v2.0.
- O/U Formula v2.3 as an experimental signal.
- Data freshness, source lineage, hard skip rules, warnings, immutable forecasts, result grading, and chronological backtesting.

### Excluded

- Hermes, LLMs, AI reviewers, model routing, gateways, and provider fallbacks.
- Football/soccer sources, BetExplorer, Firecrawl, and cross-sport workflows.
- Browser or geo-blocking workarounds.
- Automated bookmaker interaction or bet placement.
- Parlays, slip builders, staking advice, player props, futures, First Five, and run-line models in the MVP.
- Old v1 Moneyline and totals formulas as executable strategies.
- Hard-coded 2026 team performance snapshots.
- Historical hit-rate claims that cannot be reconstructed from timestamped forecasts and settled results.
- Subjective bounce-back overrides. Bounce-back indicators may be displayed as context but cannot change the formula.

## 3. Operating principles

1. Zero fabrication: missing data remains missing.
2. Source before score: no model run without source observations and retrieval timestamps.
3. UTC internally: store event times in UTC and display WIB by default.
4. Immutable runs: a model run always points to frozen input snapshots.
5. Visible abstention: weak, stale, incomplete, or conflicting evidence returns `NEEDS DATA`, `INVALIDATED`, `SKIP`, or `NO BET`.
6. Version everything: model rules and threshold settings have semantic versions.
7. Backtest chronologically: evaluate only forecasts locked before first pitch.
8. Separate score from probability: model points and gaps are not calibrated win probabilities.

## 4. End-to-end pipeline

```text
Select slate date
  -> ingest schedule and probable starters
  -> ingest pitcher, team, bullpen, odds, and park data
  -> preserve raw source observations
  -> normalize identifiers, units, and timestamps
  -> validate completeness, freshness, starter role, and conflicts
  -> freeze an input snapshot
  -> calculate Moneyline and O/U features
  -> apply hard gates and caution flags
  -> publish analysis or abstention state
  -> lock forecast before first pitch
  -> ingest final result
  -> grade and add to versioned backtest
```

### Daily timing in WIB

| Window | Purpose | Output |
|---|---|---|
| 22:00-00:00 | Reconnaissance | Preliminary schedule and starters; no final forecast |
| 06:00-08:00 | Main refresh | Current starters, stats, odds, and first model run |
| 2-4 hours pregame | Confirmation | Detect starter/venue/line changes and rerun affected games |
| After all games are final | Grading | Final scores, settled forecasts, updated backtest |

West Coast games may finish later than East Coast games. Result grading must wait for each game's official final status rather than a fixed clock time.

## 5. Provider strategy

### Required provider interfaces

- `ScheduleProvider`
- `PitcherStatsProvider`
- `TeamStatsProvider`
- `OddsProvider`
- `ParkFactorProvider`
- `ResultsProvider`

### Source policy

- Use the public MLB Stats API for schedule, people search, pitcher stats, game logs, team hitting, team pitching, standings, and results.
- Use an authorized odds API or manual CSV/JSON import for Moneyline and O/U prices.
- Store park factors in a season-stamped, source-stamped dataset that can be replaced without a code release.
- Do not ship access-control bypasses or brittle scraping as production dependencies.

### MLB Stats API routes

```text
/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team
/api/v1/people/search?names={name}&sportId=1
/api/v1/people/{id}/stats?stats=season&season={year}&group=pitching
/api/v1/people/{id}/stats?stats=gameLog&season={year}&group=pitching
/api/v1/teams/{id}/stats?stats=season&season={year}&group=hitting
/api/v1/teams/{id}/stats?stats=season&season={year}&group=pitching
/api/v1/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason
```

## 6. Canonical data requirements

Every observation must include:

- provider name;
- provider record ID or source identifier;
- retrieval timestamp;
- effective timestamp or season;
- source timezone when applicable;
- raw payload checksum;
- normalized value;
- freshness state;
- validation warnings.

Important baseball rule: innings pitched notation is not decimal. `5.2 IP` means five innings and two outs. Normalize innings to outs before calculations:

```text
5.0 IP = 15 outs
5.1 IP = 16 outs
5.2 IP = 17 outs
5.3 IP = invalid
```

## 7. Data freshness defaults

All values are configurable and versioned.

| Data | Default policy |
|---|---|
| Schedule and status | Refresh for every slate load and scheduled job |
| Probable starter | Recheck on main refresh and 2-4 hours pregame |
| Odds | Display age; refresh on main and pregame runs |
| Team offense/form | Stale after 24 hours |
| Bullpen season data | Stale after 24 hours |
| Pitcher season/logs | Refresh after completed games and before model run |
| Park factor | Must match current season or be explicitly marked fallback |

Any critical stale input blocks a forecast. Overnight odds cannot be silently reused as a final pregame price.

## 8. Moneyline framework - Combo Score v2.0

### 8.1 Candidate definition

Calculate a score for each team, but a team is Moneyline-eligible only when its starter has a positive ERA advantage:

```text
EraGap = OpponentStarterERA - CandidateStarterERA
```

`EraGap > 0` means the candidate starter has the lower ERA. A candidate with `EraGap <= 0` is `SKIP`, even if offense or team form is strong. This prevents negative-ERA-gap favorites from becoming recommended legs.

### 8.2 Total score

```text
ComboScore = EraGapPoints
           + OffensePoints
           + GameLogPoints
           + MarketAlignmentPoints
           + TeamFormPoints
```

Maximum: 100 points.

| Factor | Maximum |
|---|---:|
| ERA gap | 35 |
| Offense quality | 25 |
| Pitcher last five | 20 |
| Market alignment | 10 |
| Team form | 10 |

### 8.3 ERA gap points

Evaluate exact numeric values rather than rounded display values.

| ERA gap | Points |
|---|---:|
| `>= 2.00` | 35 |
| `>= 1.50 and < 2.00` | 28 |
| `>= 1.00 and < 1.50` | 21 |
| `>= 0.50 and < 1.00` | 14 |
| `< 0.50` | 0 |

### 8.4 Offense points

Score AVG and OPS independently, then use the lower of the two scores. This conservative rule resolves mixed tiers without guessing.

| Tier | AVG rule | OPS rule | Points |
|---|---|---|---:|
| Elite | `> .260` | `> .760` | 25 |
| Good | `.250-.260` | `.730-.760` | 20 |
| Average | `.240-.249` | `.720-.729` | 15 |
| Bad | `.230-.239` | `.700-.719` | 10 |
| Terrible | `< .230` | `< .700` | 5 |

If AVG and OPS tiers differ, add `OFFENSE_TIER_MISMATCH`.

### 8.5 Pitcher last-five points

For each of the last five valid starts:

```text
GameERA = EarnedRuns * 27 / OutsRecorded
GoodStart = GameERA < 4.00
```

| Good starts | Points |
|---:|---:|
| 5 | 20 |
| 4 | 16 |
| 3 | 12 |
| 2 | 8 |
| 1 | 4 |
| 0 | 0 |

Require five valid starts for the primary model. Fewer than five returns `SKIP: INSUFFICIENT_GAME_LOG`.

Trend is display-only:

- `HOT`: last-three game ERA is improving.
- `COLD`: last-three game ERA is worsening.
- `MIXED`: neither sequence is monotonic.

Trend cannot override hard gates.

### 8.6 Market alignment points

This is a heuristic, not calibrated fair pricing. Keep its anchors in versioned configuration.

Default fair-price anchors:

| ERA gap | Fair decimal odds |
|---|---:|
| `>= 3.00` | 1.35 |
| `>= 2.00 and < 3.00` | 1.50 |
| `>= 1.00 and < 2.00` | 1.65 |
| `< 1.00` | Not defined; 0 points and warning |

Let `PriceDifference = CandidateDecimalOdds - FairDecimalOdds`.

| Condition | Points |
|---|---:|
| Candidate market price is at or shorter than fair | 10 |
| Difference `> 0 and < 0.20` | 8 |
| Difference `>= 0.20 and <= 0.30` | 6 |
| Difference `> 0.30` | 4 |
| Market makes the ERA-disadvantaged side favorite | 0 and hard `SKIP` |

### 8.7 Team form points

Evaluate in order and use the first matching complete rule:

| Condition | Points |
|---|---:|
| Last-ten wins `>= 8` and win streak `>= 3` | 10 |
| Last-ten wins `>= 6` and win streak `>= 1` | 8 |
| Last-ten wins `>= 5` | 6 |
| Last-ten wins `>= 4` and loss streak `<= 2` | 4 |
| Otherwise | 2 |

### 8.8 Website tiers

The original base framework used T1 at 70. Later operational review recommended a stricter backbone. Because this website has no AI reviewer, use one conservative tier set:

| Score | Output |
|---|---|
| `>= 75` | T1 - strongest formula-qualified candidate |
| `55-74` | T2 - watchlist only |
| `< 55` | SKIP |

T1 is a score tier, not an 80 percent probability or a guarantee.

### 8.9 Moneyline hard skips

Return `SKIP` when any condition is true:

- starter is TBD, undecided, unconfirmed, or conflicting across current sources;
- probable starter has `GS = 0` or is classified as a reliever/opener;
- candidate starter season innings are below 60;
- fewer than five valid recent starts;
- candidate offense AVG is below .220;
- three or more of the last five starts have game ERA `>= 4.00`;
- ERA gap is zero or negative;
- market favorite is the ERA-disadvantaged side;
- Moneyline price is missing or stale;
- any critical input is missing or stale;
- game already started.

### 8.10 Moneyline cautions

Warnings do not automatically change the score:

- season IP from 60 through 90;
- offense AVG below .230 with ERA gap below 2.00;
- game-log score of four or zero;
- large price movement since the first snapshot;
- bullpen weakness or recent bullpen workload;
- source mismatch that is non-critical but unresolved.

## 9. Totals framework - O/U v2.3

### 9.1 Status

O/U v2.3 is experimental. Its labels describe formula-gap strength, not demonstrated predictive confidence. Every totals output must display the model version, current backtest sample size, and warning status.

### 9.2 Required inputs

- Market full-game total line.
- Decimal price for the selected Over or Under.
- Away and home runs per game.
- Away and home starter season ERA.
- Away and home starter last-five aggregate ERA.
- Home venue park factor.
- Starter confirmation and data freshness.

Calculate last-five aggregate ERA from totals, not the arithmetic mean of per-start ERA:

```text
LastFiveERA = TotalEarnedRuns * 27 / TotalOutsRecorded
```

### 9.3 Formula

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

The home venue park factor is applied once. Never average home and away park factors.

### 9.4 Decision rules

Minimum selected-side decimal odds: 1.85.

| Gap | Output |
|---|---|
| `>= +0.75` | OVER - strong model gap |
| `+0.50 to +0.74` | OVER - RISKY |
| `-0.49 to +0.49` | NO BET |
| `-0.74 to -0.50` | UNDER - RISKY |
| `<= -0.75` | UNDER - strong model gap |

If the selected-side price is below 1.85, return `NO BET: PRICE_BELOW_MINIMUM` regardless of gap.

### 9.5 Totals hard gates

Return `NEEDS DATA`, `INVALIDATED`, or `NO BET` when:

- the market line or selected-side price is missing;
- either starter is unconfirmed, changed, or conflicting;
- either starter lacks the required season or last-five data;
- team R/G is missing or stale;
- park factor is missing, from the wrong season, or attached to the wrong venue;
- odds are stale or the game already started;
- absolute gap is below 0.50;
- selected-side odds are below 1.85.

### 9.6 Totals warnings

- Both starters WHIP below 1.15 on an OVER signal: `PITCHING_DUEL_RISK`.
- Starter IP between 60 and 90: `BORDERLINE_SAMPLE`.
- Large total-line movement: `LINE_MOVEMENT`.
- Bullpen uncertainty or workload: `BULLPEN_CONTEXT_RISK`.
- Extreme park adjustment or cap reached: `EXTREME_PARK_ADJUSTMENT`.
- Strong model gap with weak historical model performance: always keep the experimental badge.

Bullpen metrics are context only in v2.3 and must not be silently added to the formula.

## 10. Odds utilities

```text
Negative American to decimal = 1 + 100 / abs(american)
Positive American to decimal = 1 + american / 100
Implied probability = 1 / decimalOdds
```

Preserve the original odds and calculate with full precision. Round only for display.

## 11. Output contract

Every game analysis must return:

- game and UTC/WIB start time;
- home and away teams;
- confirmed starters and source timestamps;
- market line and prices with retrieval time;
- model and configuration versions;
- each raw formula input;
- each intermediate calculation;
- raw score or gap;
- final state: `T1`, `T2`, `SKIP`, `OVER`, `UNDER`, `RISKY`, `NO BET`, `NEEDS DATA`, or `INVALIDATED`;
- triggered hard rules;
- warnings;
- locked forecast timestamp when applicable.

## 12. Forecast and backtest logic

1. A forecast is eligible for grading only if locked before first pitch.
2. New data after a locked forecast creates a revision; it never overwrites the original.
3. A starter or venue change invalidates all affected unlocked runs and creates a new run after refresh.
4. Backtests are split by model version and configuration version.
5. Every performance statistic displays sample size.
6. Hit rate alone is insufficient. Capture historical price and a declared flat-stake rule before reporting ROI.
7. Do not report Brier score until the system produces calibrated probabilities.
8. Include maximum drawdown and consecutive-loss distribution when ROI is available.

## 13. Minimum website screens

1. Daily Slate.
2. Match Detail.
3. Data Health.
4. Forecast History.
5. Backtest Dashboard.
6. Model Settings and version history.

No parlay builder is required for the MVP.

## 14. Definition of done

- The application runs with deterministic demo fixtures when real odds are unavailable.
- Every formula boundary and hard gate is unit tested.
- Every visible number traces to a source observation.
- Stale or missing critical data cannot produce an eligible forecast.
- O/U v2.3 is visibly experimental.
- No Hermes, LLM, or AI-review code exists.
- No secret is committed or exposed to the browser.
- Production build, lint, type checks, unit tests, and critical browser tests pass.

