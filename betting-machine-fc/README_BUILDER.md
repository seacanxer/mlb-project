# FOOTBALL BETTING RECOMMENDATION ENGINE — BLUEPRINT & BUILD SPEC

Version 1.0 · Author: Hermes Agent · Date: 2026-08-29
Purpose: this document + the reference code in this repo is ALL the coding agent
needs to build a production football betting pick engine.

---

## 1. PRODUCT REQUIREMENT (USER — verbatim intent)

Build a website / machine / pipeline that recommends football betting picks.

- **Markets**: 1X2 (match result), Asian Handicap (AH), Total Goals Over/Under (O/U), BTTS.
- **Odds floor**: NEVER recommend odds below **1.66**. Anything below is rejected outright.
- **Method**: professional sports-bettor approach with HIGH ROI. Statistical, zero sentiment.
- **Deliverable shape (user convention)**: Python tool, no comments/docstrings in production files,
  `config.json` user-editable, delivered as a zip. Site is a bonus layer on top (the model + pipeline
  is the core).

## 2. ARCHITECTURE (what the agent must build)

```
┌────────────────────────────────────────────────────────────────────┐
│  DATA LAYER (scrapers / fetchers)                                  │
│   · Live odds: 1xbit LineFeed API (reverse-engineered, no auth)    │
│   · Historical: football-data.co.uk (per-league CSV, closing odds) │
│   · Stats/xG (optional upgrade): Understat / API-Football          │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  MODEL LAYER                                                       │
│   · Dixon-Coles bivariate Poisson (ρ = -0.13)                      │
│   · Lambda derivation: blend bookmaker (OU + WP) + team strength   │
│   · Market pricing: 1X2, AH (quarter split), O/U (push-aware),     │
│     BTTS (DC-corrected)                                            │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  SELECTION LAYER                                                   │
│   · Odds floor 1.66 hard filter                                    │
│   · EV > 0 threshold (+2% recommended)                             │
│   · Kelly-fraction staking (≤10% cap) + flat 2% fallback           │
│   · SGP correlation guard for multi-leg                            │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  OUTPUT LAYER                                                      │
│   · picks.json (machine-readable)                                   │
│   · optional web dashboard (Flask/FastAPI + minimal HTML)           │
└────────────────────────────────────────────────────────────────────┘
```

## 3. CORE FORMULAS (implemented + unit-tested in `model.py`)

All formulas below are reference implementations in `model.py`; the coding agent
should port them (no comments/docstrings per convention, but keep the SAME math).

### 3.1 Poisson + Dixon-Coles
```
P(X=x, Y=y) = Pois(x; λ_h) · Pois(y; λ_a) · τ(x,y)
τ(0,0) = 1 - λ_h·λ_a·ρ
τ(1,0) = 1 + λ_a·ρ        τ(0,1) = 1 + λ_h·ρ
τ(1,1) = 1 - ρ
τ = 1 otherwise            ρ = -0.13 (range -0.20..-0.10)
```
- Truncate scorelines at 10 goals; renormalize.
- P(HomeWin) = Σ P(x>y), P(Draw) = Σ P(x=y), P(AwayWin) = Σ P(x<y).

### 3.2 Asian Handicap payout table (per sub-leg, stake=1)
For handicap h (home perspective): split into legs:
- h ∈ ℤ or h.5 → single leg
- h.25 → legs (h-0.25, h+0.25)
- h.75 → legs (h-0.25, h+0.25)

Per-leg result vs home goal margin m: `adjusted = m + leg` — win if >0, push if ==0, lose if <0.
Return = average across legs of {odds on win, 1.0 on push, 0 on loss}.

Verified vectors (odds 1.95):
| home -0.75 | margin +2 → 1.95 | +1 → 1.475 | 0 → 0.0 | -1 → 0.0 |
| home -0.25 | margin 0 → 0.5   | +1 → 1.95 |
| home +0.25 | margin 0 → 1.475  |
| away +0.25 | margin 0 → 1.475  | home +0.75 margin 0 → 1.95 |

### 3.3 O/U (Total Goals)
- λ_total = λ_h + λ_a
- Over 2.5: P(total ≥ 3) = 1 - Σ_{k=0}^{2} Pois(k; λ_total)
- Under 2.5: P(total ≤ 2) = Σ_{k=0}^{2} Pois(k; λ_total)
- Integer lines (e.g. 2.0): Over wins >2, Under wins <2, =2 pushes (money back).
- Quarter lines (2.25/2.75): split like AH into halves with push handling per leg.
- `total_ev()` in model.py implements the full push/half-stake EV — use it, not naive formulas.

### 3.4 BTTS (Dixon-Coles corrected)
```
P(BTTS yes) = 1 - P(0,0) - P(home 0) - P(away 0)   [from full DC matrix]
```
The DC τ correction redistributes mass toward 0-0/1-1 (draws up ~3%), so BTTS
is computed from the exact matrix, NOT the naive (1-e^-λh)(1-e^-λa).

### 3.5 Lambda derivation (critical — do NOT skip)
Use bookmaker OU odds for total goals, and 1X2 only for home/away split:
```
fair_over = (1/OverOdds) / ((1/OverOdds) + (1/UnderOdds))
λ_total   = argmin_λ |P_over(2.5; λ) - fair_over|    (grid 0.1..6.0)
λ_h       = λ_total · P_home / (P_home + P_away)      (margin-removed P)
λ_a       = λ_total · P_away / (P_home + P_away)
```
NEVER derive λ from WP alone (juice → circular → fake negative EV).
Optional upgrade: blend 30-50% with team-strength xG lambdas (Understat) for sharper edges.

### 3.6 EV & filters
```
EV = P_true · Odds - 1
ACCEPT iff Odds ≥ 1.66 AND EV > 0.02 (recommended) AND market horizon sane.
```

## 4. DATA SOURCES (validated live 2026-08-29)

### 4.1 LIVE ODDS — 1xbit LineFeed (reverse-engineered, no auth, plain curl) ✅
- Base: `https://1xbit.com/service-api/LineFeed/`
- List: `BestGamesExtZip?sports=1&count=50&lng=en&mode=1&country=169`
  → JSON `Value[]` with `I` (match id), `WP` (win probs), no team names.
- Detail: `GetGameZip?id={I}&lng=en&country=169`
  → full match: `O1`/`O2` (teams), `S` (epoch), `L` (league), `E[]` odds:
  - **Group 1 (T=1/2/3) = 1X2**
  - **Group 17 (T=9/10, P=line) = O/U ALL LINES** (2.5, 3.5, etc.)
  - **Group 2 T=7 = AH HOME odds (P=home handicap), T=8 = AH AWAY odds**
  - Group 11 = correct score; Group 19 = HT; G2665 = corners; G2667 = cards
- BTTS: NOT labeled in 1xbit (G829 is NOT btts — verified). Derive via model, or
  cross-check with The Odds API `btts` market or API-Football `/predictions`.
- Rate: sleep ≥0.15s between GetGameZip calls; ~50 matches per BestGames call.

### 4.2 HISTORICAL — football-data.co.uk ✅
- URL: `https://www.football-data.co.uk/mmz4281/{season}/{league}.csv`
  season `2425`, `2526`, league `E0` (ENG), `SP1` (ESP), `D1` (GER), `I1` (ITA), `F1` (FRA)...
- Columns needed: FTHG, FTAG (results), B365H/D/A, B365>2.5, B365<2.5, AHh, B365AHH, B365AHA.
- Every row = a closed market. Backtest: run model → pick → compare vs actual → ROI.

### 4.3 STATS/xG (optional upgrade)
- Understat (Playwright, `window.teamsData`), API-Football free tier, statz.ai refs.

## 5. PIPELINE STEPS (exact order for the coding agent)

Phase A — Core engine (do first, test with `tests/test_formulas.py`):
1. Port `model.py`: Poisson, DC τ, 1X2, AH (quarter), O/U (push), BTTS, λ derivation, EV.
2. Keep the unit tests; all 12 must pass (vectors locked).

Phase B — Data:
3. `scraper_1xbit.py` live odds → normalized dict (already in repo, port it).
4. `scraper_historical.py` historical CSV → normalized dict rows.

Phase C — Selection & backtest:
5. Selection: EV>0 (+2% rec), odds≥1.66, stake = 2% flat or fractional Kelly (cap 10%).
6. Backtest harness over ≥2 seasons, ≥3 leagues; report ROI/hit-rate/avg-odds by market.
7. **Requirement**: model must show positive ROI on backtest BEFORE going live. If not,
   tighten filter (raise EV bar, raise min odds), don't ship.

Phase D — Output:
8. `picks.json` + optional simple web dashboard (`app.py` Flask + `templates/index.html`).
9. Wrap in zip with `config.json` + short README.

## 6. REPO CONTENTS (reference implementation included)

```
betting-machine-fc/
  model.py                # Dixon-Coles engine (12 unit tests passing)
  scraper_1xbit.py        # live odds scraper (validated vs 1xbit)
  scraper_historical.py   # historical CSV scraper
  main.py                 # pipeline orchestrator (config.json driven)
  config.json             # min_odds 1.66, min_ev 0.0, source toggle
  eval_backtest.py        # validation + backtest reporting
  strategy/bankroll.py    # Kelly + Monte Carlo sanity
  tests/test_formulas.py  # 12 unit tests, all passing
  demo_scan.py            # live demo scan (Liverpool example)
```

## 7. QA CHECKLIST (coding agent must verify)

- [ ] `python3 tests/test_formulas.py` → 12 passed
- [ ] Live demo scan runs, shows BET/REJECT correctly vs 1.66 floor
- [ ] Backtest over 2+ seasons shows positive ROI by market (or tightened)
- [ ] No pick output with odds < 1.66 or EV ≤ 0
- [ ] O/U integer line push handled; quarter lines split; AH payout table correct
- [ ] config.json editable without touching code
- [ ] zip contains model + scrapers + main + tests + README

## 8. PRO TIP — LONGSHOT NOISE (from live validation 2026-08-29)

Live run over 205 matches qualified picks at every longshot AH line (odds 3.5–8.1)
because model EV stays positive on high-odds tails. That is variance noise, not edge:
a +35% EV at odds 7.0 needs hundreds of bets to realize. Professional approach:

1. **Primary window: odds 1.66–3.00.** Highest signal:noise, sane staking.
2. Treat AH lines with |line| > 2.0 as informational only — do NOT bet longshot AH
   by default (unless deliberately building a lottery-style portfolio).
3. EV threshold: use +2% (0.02) in production, not >0 — kills the longshot tail noise.
4. Backtest hit-rate per market: if hit-rate < 45% at avg odds > 2.5, that market is
   variance-heavy; cap exposure or drop it.
5. Staking: flat 2% until 200+ sample; then fractional Kelly (cap 10%).

## 9. REFERENCES
- Full source inventory + pitfalls: sports-data-pipeline skill (references/endpoint-inventory.md,
  references/1xbit-odds-mapping.md, references/analysis-framework.md)
- Validation: 1xbit live tested 2026-08-29; football-data.co.uk live tested 2026-08-29.