# Product Requirements Document - MLB Analytics Website

Version: 1.0  
Status: Draft for implementation  
Owner: Product  
Default timezone: Asia/Jakarta  
Source of truth: `mlb-website-core-framework.md`

## 1. Product summary

The product is a standalone MLB analytics website for evaluating full-game Moneyline and Over/Under markets. It converts current MLB and market data into deterministic, explainable model outputs while making data quality, formula limitations, and abstention states visible.

The application contains no Hermes or other AI integration. All decisions come from versioned formulas and explicit rules.

## 2. Problem statement

The existing workflow is distributed across multiple markdown files and contains historical formulas, changing thresholds, provider workarounds, and unverified performance claims. A website implementation needs one deterministic source of truth that:

- knows which formulas are current;
- rejects stale, missing, or conflicting data;
- explains every score and adjustment;
- preserves forecasts before games;
- measures real performance without rewriting history.

## 3. Product goals

### G1 - Reliable daily slate

Load the requested MLB slate with normalized game time, probable starters, stats, odds, park factor, freshness, and source state.

### G2 - Deterministic analysis

Run Moneyline Combo Score v2.0 and experimental O/U v2.3 with reproducible intermediate calculations.

### G3 - Safe abstention

Return `NEEDS DATA`, `INVALIDATED`, `SKIP`, or `NO BET` whenever eligibility rules fail.

### G4 - Explainability

Let a user trace every displayed value and conclusion to its source observation and model/configuration version.

### G5 - Honest evaluation

Lock forecasts before games, grade them from official results, and report performance chronologically with sample sizes.

## 4. Non-goals

- Betting execution, wallet management, or sportsbook account integration.
- Parlays, staking recommendations, player props, futures, run-line, or First Five models.
- AI analysis, AI review, chat, Hermes, or LLM features.
- Scraping bypasses, geo-blocking workarounds, or prohibited automation.
- Claims of guaranteed profit or calibrated probability.
- Public social features, comments, leaderboards, or multi-tenant collaboration in MVP.

## 5. Primary user

A single analyst who wants a daily MLB board, transparent calculations, clear reasons to abstain, and a trustworthy performance history.

## 6. Product principles

- No data is better than invented data.
- A model result is not a probability unless calibrated and validated.
- A warning is visible; a hard gate is blocking.
- New information creates a new snapshot and model run.
- The original pregame forecast is immutable.
- Every threshold is configuration, not hidden application logic.

## 7. MVP user journeys

### Journey A - Load and analyze a slate

1. User selects an MLB date.
2. System ingests or loads schedule, starters, stats, odds, and park factors.
3. System normalizes and validates the observations.
4. System displays provider health and missing/stale fields.
5. User runs analysis for all valid games.
6. Daily Slate displays Moneyline tier, O/U signal, abstention state, and warnings.

### Journey B - Inspect one game

1. User opens Match Detail.
2. System shows source timestamps and starter confirmation.
3. System shows each Moneyline factor and the final Combo Score.
4. System shows each O/U adjustment and the final gap.
5. System shows triggered hard gates and warnings.
6. User can open the immutable input snapshot and model/config versions.

### Journey C - Pregame refresh

1. Scheduled job refreshes starters and odds 2-4 hours before first pitch.
2. System compares observations with the latest model run.
3. Starter, venue, or critical line changes invalidate affected unlocked runs.
4. System creates a new input snapshot and reruns the model.
5. UI shows what changed.

### Journey D - Lock and grade a forecast

1. User locks an eligible forecast before first pitch.
2. System records market line, price, inputs, model version, and lock time.
3. After official final status, system ingests the score.
4. System grades the forecast and updates version-specific reporting.

### Journey E - Investigate bad data

1. Data Health shows a failed provider, stale observation, or starter conflict.
2. User opens the issue and sees affected games and fields.
3. User refreshes the provider or imports authorized/manual odds.
4. System validates the new data and creates a new snapshot.

## 8. Functional requirements

### 8.1 Slate and ingestion

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | User can select a slate date. | Must |
| FR-002 | System retrieves MLB schedule and probable starters. | Must |
| FR-003 | System retrieves pitcher season stats and last-five game logs. | Must |
| FR-004 | System retrieves team hitting, team pitching, standings, and results. | Must |
| FR-005 | System accepts Moneyline and O/U data from an authorized provider or manual CSV/JSON import. | Must |
| FR-006 | System loads season-stamped home-venue park factors. | Must |
| FR-007 | Provider jobs are idempotent and avoid duplicate observations. | Must |
| FR-008 | System preserves raw payload checksum and normalized observation. | Must |

### 8.2 Normalization and validation

| ID | Requirement | Priority |
|---|---|---|
| FR-020 | Store all game times in UTC and display WIB by default. | Must |
| FR-021 | Normalize pitcher/team/provider identifiers. | Must |
| FR-022 | Normalize baseball IP to outs and reject invalid `.3` notation. | Must |
| FR-023 | Detect missing, stale, and conflicting critical fields. | Must |
| FR-024 | Validate probable starter role with games started and available role data. | Must |
| FR-025 | Starter or venue changes invalidate affected model runs. | Must |
| FR-026 | Every observation includes provider, retrieved time, effective time/season, and freshness. | Must |

### 8.3 Moneyline engine

| ID | Requirement | Priority |
|---|---|---|
| FR-040 | Calculate ERA gap from the candidate perspective. | Must |
| FR-041 | Calculate ERA gap points using configured bands. | Must |
| FR-042 | Calculate AVG and OPS offense tiers independently and use the lower score. | Must |
| FR-043 | Calculate each recent-start ERA from earned runs and outs. | Must |
| FR-044 | Require five valid recent starts and calculate game-log points. | Must |
| FR-045 | Calculate market-alignment points from versioned fair-price anchors. | Must |
| FR-046 | Calculate team-form points using ordered complete conditions. | Must |
| FR-047 | Return Combo Score and T1/T2/SKIP tier. | Must |
| FR-048 | Apply every Moneyline hard skip after calculation and preserve both raw score and final state. | Must |

### 8.4 Totals engine

| ID | Requirement | Priority |
|---|---|---|
| FR-060 | Calculate last-five aggregate ERA from total ER and outs. | Must |
| FR-061 | Calculate offense adjustment. | Must |
| FR-062 | Calculate pitcher-form adjustment. | Must |
| FR-063 | Calculate park adjustment from the home venue only. | Must |
| FR-064 | Clamp total adjustment to minus/plus 3.0. | Must |
| FR-065 | Calculate Adjusted Total and Gap. | Must |
| FR-066 | Apply gap and minimum-price rules. | Must |
| FR-067 | Label every O/U result experimental. | Must |
| FR-068 | Bullpen information may create warnings but cannot change v2.3 arithmetic. | Must |

### 8.5 Analysis output

| ID | Requirement | Priority |
|---|---|---|
| FR-080 | Daily Slate shows all games and current analysis state. | Must |
| FR-081 | Match Detail shows source lineage and every intermediate calculation. | Must |
| FR-082 | Hard gates and warnings use separate visual treatment. | Must |
| FR-083 | Every analysis shows model and config version. | Must |
| FR-084 | Every market value shows retrieval time and age. | Must |
| FR-085 | User can export a slate or model run as JSON and CSV. | Should |

### 8.6 Forecasting and results

| ID | Requirement | Priority |
|---|---|---|
| FR-100 | User can lock an eligible forecast only before first pitch. | Must |
| FR-101 | Locked forecast stores frozen inputs, line, price, and version. | Must |
| FR-102 | Later refresh creates a revision and never overwrites a locked forecast. | Must |
| FR-103 | System retrieves official final score and grades Moneyline/totals outcome. | Must |
| FR-104 | Push/void states are supported when the market line permits them. | Must |
| FR-105 | Backtest reports split by model and config version and show sample size. | Must |

### 8.7 Configuration

| ID | Requirement | Priority |
|---|---|---|
| FR-120 | Formula thresholds and freshness windows are stored in versioned configuration. | Must |
| FR-121 | Editing configuration creates a new immutable config version. | Must |
| FR-122 | Existing forecasts continue to reference their original config. | Must |
| FR-123 | Park-factor data is replaceable without source-code changes. | Must |

## 9. Calculation rules

Implement the formulas and hard gates exactly as defined in `mlb-website-core-framework.md`.

### Moneyline summary

```text
EraGap = OpponentStarterERA - CandidateStarterERA
ComboScore = EraGapPoints + OffensePoints + GameLogPoints + MarketAlignmentPoints + TeamFormPoints

T1: >= 75
T2: 55-74
SKIP: < 55 or any hard gate
```

### O/U summary

```text
OffAdj = ((AwayRPG - 4.1) + (HomeRPG - 4.1)) * 0.60
PitchAdj = ((AwayLastFiveERA - AwaySeasonERA) + (HomeLastFiveERA - HomeSeasonERA)) * 0.50
ParkAdj = (HomeParkFactor - 1.0) * MarketLine * 2.5
TotalAdj = clamp(OffAdj + PitchAdj + ParkAdj, -3.0, +3.0)
AdjustedTotal = MarketLine + TotalAdj
Gap = AdjustedTotal - MarketLine
```

O/U requires selected-side decimal odds of at least 1.85 and complete fresh inputs.

## 10. Data model

### Core entities

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

### Required relationships

- A `Game` has home/away teams, venue, UTC start, and status.
- An `InputSnapshot` contains immutable references to all observations used for one game analysis.
- A `ModelRun` references one input snapshot, one model definition, and one config version.
- A `Forecast` references one model run and captures a pregame market snapshot.
- A `Settlement` references one forecast and one official game result.

## 11. Application pages

### 11.1 Daily Slate

- Date picker and refresh status.
- Provider/data-health summary.
- Game time in WIB with UTC available.
- Starter names and confirmation status.
- Moneyline price, Combo Score, tier, and hard-gate state.
- O/U line, price, gap, signal, and experimental badge.
- Warning count, last refresh, and Match Detail link.

### 11.2 Match Detail

- Game and market header.
- Source lineage and freshness.
- Starter comparison.
- Moneyline factor cards totaling to Combo Score.
- O/U adjustment cards totaling to Gap.
- Hard gates and warnings.
- Model/config version and input snapshot identifier.
- Forecast and revision history.

### 11.3 Data Health

- Provider status and last success.
- Missing/stale/conflicting observations.
- Affected games.
- Retry/import action.
- No secret or raw credential display.

### 11.4 Forecast History

- Locked forecasts and revisions.
- Original line/price and lock time.
- Final result and settlement.
- Filters for model, tier/signal, date, and result.

### 11.5 Backtest Dashboard

- Sample size, win/loss/push.
- Hit rate by model/config version.
- Performance by tier, gap band, odds band, month, and home/away.
- ROI only when captured prices and a declared stake rule exist.
- Maximum drawdown and losing streak when ROI is enabled.
- Experimental warning for O/U v2.3.

### 11.6 Settings

- Freshness windows.
- Moneyline bands and tier thresholds.
- O/U thresholds, minimum odds, and clamp.
- Fair-price anchor table.
- Park-factor dataset version.
- Default timezone.
- Read-only configuration-version history.

## 12. API and background jobs

Suggested application endpoints:

```text
POST /api/slates/{date}/refresh
GET  /api/slates/{date}
POST /api/games/{gameId}/refresh
GET  /api/games/{gameId}
POST /api/games/{gameId}/analyze
POST /api/model-runs/{runId}/lock
GET  /api/model-runs/{runId}
POST /api/odds/import
POST /api/results/refresh
GET  /api/backtest
GET  /api/data-health
```

Jobs:

- nightly reconnaissance;
- main morning refresh;
- per-game pregame refresh;
- live status/result polling with bounded frequency;
- post-final settlement;
- stale-observation detection.

All jobs must be idempotent, observable, retry transient failures with bounded exponential backoff, and avoid retry loops for validation errors.

## 13. Non-functional requirements

### Reliability

- One provider failure cannot corrupt existing snapshots.
- Partial data is visible but cannot create an eligible forecast.
- Duplicate jobs do not duplicate forecasts or observations.

### Performance

- Cached Daily Slate response target: under 500 ms.
- Match Detail target: under 750 ms from stored data.
- Provider refresh runs asynchronously and reports progress.

### Security

- Provider credentials are server-side environment variables.
- No secrets in logs, browser bundles, exports, screenshots, or committed files.
- Validate every external payload and manual import.
- Rate-limit mutation endpoints.

### Accessibility

- WCAG 2.1 AA color contrast.
- Keyboard navigation for all controls and tables.
- Status is communicated with text/icon, not color alone.
- Responsive tables offer readable mobile cards or horizontal scrolling.

### Observability

- Structured logs with request/job IDs.
- Provider latency, failure count, and last-success metrics.
- Model-run count by final state.
- No secret or full sensitive header logging.

## 14. Design direction

- Data-dense, calm, and operational.
- Navy for structure, blue for information, amber for caution, red for blocking, green only for validated data or settled success.
- Never use green or celebratory language to imply guaranteed future outcomes.
- Prioritize tables on desktop and compact cards on mobile.
- Keep formula details one click away from every result.

## 15. Acceptance criteria

### Data and pipeline

- [ ] A selected date loads a complete demo slate.
- [ ] All observations show source and retrieval time.
- [ ] UTC/WIB rollover is correct.
- [ ] `5.2 IP` converts to 17 outs and `5.3 IP` is rejected.
- [ ] Starter conflict invalidates the affected run.
- [ ] Stale critical input blocks an eligible forecast.

### Moneyline

- [ ] Every score band and boundary is unit tested.
- [ ] Mixed AVG/OPS tier uses the lower score and emits a warning.
- [ ] Fewer than five starts returns `SKIP`.
- [ ] Negative/zero ERA gap returns `SKIP`.
- [ ] T1 begins at 75 and T2 covers 55-74.
- [ ] Raw score remains visible when a hard gate changes final state.

### Totals

- [ ] Last-five ERA uses aggregate ER and outs.
- [ ] Home park factor is applied exactly once.
- [ ] Adjustment is capped to plus/minus 3.0.
- [ ] Every gap boundary and odds 1.84/1.85 are tested.
- [ ] Missing input or price returns abstention.
- [ ] Every totals output shows `Experimental`.

### Forecast and backtest

- [ ] Forecast cannot be locked after first pitch.
- [ ] A later refresh cannot overwrite the locked forecast.
- [ ] Push/void settlement works.
- [ ] Reports split by model/config version and display sample size.
- [ ] ROI is hidden until prices and stake policy exist.

### Delivery quality

- [ ] Demo fixtures support normal, missing-data, stale-data, starter-change, and totals-cap scenarios.
- [ ] Unit, integration, browser, accessibility, lint, type, and production-build checks pass.
- [ ] README documents setup, providers, limitations, daily workflow, and model formulas.
- [ ] Repository contains no Hermes or AI-review integration.

## 16. Recommended implementation phases

### Phase 1 - Foundation

- Data schema, model/config registry, provider interfaces, demo fixtures.
- Odds conversion and baseball innings utilities.

### Phase 2 - Deterministic engine

- Moneyline and O/U calculation packages.
- Hard gates, warnings, boundary tests, and golden fixtures.

### Phase 3 - Daily product slice

- Daily Slate, Match Detail, Data Health, refresh jobs, manual odds import.

### Phase 4 - Forecast history

- Locking, revisions, results, grading, and Forecast History.

### Phase 5 - Backtest and settings

- Performance reporting, config versioning, park-factor dataset management, exports.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Odds source unavailable | Manual import and demo fixtures; do not fabricate |
| Starter changes late | Pregame refresh and automatic invalidation |
| Park factors disagree | Season/source versioning and visible dataset metadata |
| Formula looks like probability | Use score/gap language and explicit disclaimer |
| Small samples appear convincing | Show sample size and version-specific results |
| Stale data creates false signal | Critical freshness gates |
| MLB API schema changes | Provider adapters, Zod validation, raw snapshot retention |
| O/U underperforms | Experimental badge, transparent backtest, no confidence claim |

## 18. Open implementation decisions

These choices must be confirmed before production connection, but they do not block a fixture-backed MVP:

1. Authorized production odds provider.
2. Authoritative park-factor source and update schedule.
3. Production database and hosting environment.
4. Whether the application remains single-user or later adds authentication.
5. Exact line-movement threshold that creates a warning or invalidation.
6. Whether ROI reporting will use a flat one-unit stake.

