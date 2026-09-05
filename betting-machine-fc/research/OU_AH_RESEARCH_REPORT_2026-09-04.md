# Deep Research: Sharpening O/U and Asian Handicap Picks

Date: 4 September 2026 (WIB)
Project: FC Betting Machine
Scope: formula design and league-selection policy; no production code changed

## Bottom line

O/U and AH should become the engine's core markets. The scanner can inspect every available senior fixture, while the official shortlist should be determined by data quality, league calibration, matchup, line, and price—not by a fixed quota or by league reputation alone.

The current implementation has two structural problems that directly interfere with this goal:

1. Live picks use scoring rates fitted from 1X2 prices. The total fitted from the actual O/U market is calculated but not used for selection.
2. The independent-strength formula applies the league average on the wrong scale and can nearly halve expected total goals for neutral teams.

These defects can make high-scoring competitions such as Eredivisie look like Under opportunities.

## Evidence from completed seasons

Winter leagues use July 2022–June 2025. Sweden uses completed seasons 2023–2025.

### High-goal league priors

| League | Matches | Goals/match | Over 2.5 | Blind Over ROI* |
|---|---:|---:|---:|---:|
| Germany Bundesliga | 918 | 3.175 | 60.9% | -2.55% |
| Netherlands Eredivisie | 918 | 3.095 | 59.5% | -3.88% |
| Norway Eliteserien | 676 | 3.095 | 60.8% | unavailable |
| Germany 2. Bundesliga | 918 | 3.021 | 59.4% | -2.86% |
| Denmark Superliga | 451 | 2.849 | 55.2% | unavailable |
| Sweden Allsvenskan | 720 | 2.817 | 54.0% | unavailable |

\*Blindly betting every recorded Over 2.5. The losses demonstrate that bookmakers already incorporate a league's goal tendency.

Eredivisie's own review reports roughly 3.2 goals per match in 2025/26, consistent with the local dataset's 3.176. Bundesliga's official review reports 3.13 in 2024/25. [Eredivisie](https://eredivisie.nl/nieuws/betaald-voetbal-sluit-seizoen-af-met-mooie-cijfers/), [Bundesliga](https://www.bundesliga.com/en/bundesliga/news/how-germany-compares-to-europe-s-other-top-leagues-2024-25-goals-attendance-32632).

Allsvenskan was high but not extreme: 2.817 goals and 54.0% Over 2.5 over 2023–2025. Its partial 2026 season rose to 3.042 goals and 56.3% Over 2.5 through 142 completed fixtures, so Sweden deserves priority coverage with an in-season uncertainty adjustment.

### Low-goal league priors

| League | Matches | Goals/match | Over 2.5 |
|---|---:|---:|---:|
| Spain Segunda | 1,386 | 2.266 | 40.1% |
| Italy Serie B | 1,140 | 2.443 | 45.1% |
| Ireland Premier | 527 | 2.465 | 46.3% |
| France Ligue 2 | 1,064 | 2.477 | 46.1% |
| Romania Liga I | 732 | 2.500 | 45.4% |
| England Championship | 1,654 | 2.521 | 46.9% |

These leagues should create Under candidates, but only when the offered line and price remain generous after margin removal.

## Netherlands and Sweden need team-level routing

Eredivisie 2025/26 examples:

- PSV matches: 4.29 goals/match; 85.3% Over 2.5.
- NEC: 3.82; 73.5%.
- Heracles: 3.53; 70.6%.
- Volendam: 2.65; NAC Breda: 2.74; Groningen: 2.76.

Allsvenskan 2025 examples:

- Varnamo: 3.50; Sirius: 3.47; Norrkoping: 3.23; Elfsborg: 3.20.
- AIK: 2.43; Halmstad: 2.47; Goteborg: 2.47; Mjallby: 2.50.

Therefore “Netherlands = Over” and “Sweden = Over” are too broad. The correct signal is the interaction between each team's attack, defensive weakness, home/away split, current personnel, and the price already embedded in the main line.

## Formula v3 proposal

### Independent team model

```text
log(lambda_home) = league_baseline + league_home_advantage
                   + home_attack + away_defensive_weakness + context

log(lambda_away) = league_baseline
                   + away_attack + home_defensive_weakness + context
```

Team parameters should use partial pooling, time decay selected per league family, and previous-season priors for promoted teams. Neutral teams must reproduce the league's expected goals baseline.

### Use O/U and AH market information directly

- Fit total intensity from the no-vig O/U prices at the quoted main line.
- Fit expected goal difference from both sides of the no-vig AH market.
- Use those two dimensions to construct coherent home and away scoring rates.
- Use an independent reference/consensus price when measuring value; do not fit and claim edge against the exact same bookmaker quote.

### Learn the historical-versus-market weight

Replace the fixed 40% strength blend with a calibrated residual model:

```text
logit(final_probability) = logit(reference_market_probability)
                           + league_market_bias
                           + model_market_difference
                           + coverage_and_context_adjustments
```

Weights must be learned in chronological walk-forward tests separately for O/U and AH. Research supports dynamic team strengths and combining historical scoring models with bookmaker information. [Koopman–Lit dynamic bivariate Poisson](https://doi.org/10.1111/rssa.12042), [Egidi–Pauli–Torelli historical/odds model](https://arxiv.org/abs/1802.08848).

### Score distribution and exact Asian payouts

Use one joint score grid for both markets. Begin with a dynamic bivariate Poisson/Dixon-Coles model, estimate dependence by league pool, and compare its total-goal tail calibration with a negative-binomial or Poisson-mixture alternative. Bivariate Poisson models explicitly address dependence between the two scores. [Karlis–Ntzoufras](https://doi.org/10.1111/1467-9884.00366).

Rank each offered line by expected payout:

```text
EV_OU = sum P(score) * (OU_settlement_return - 1)
EV_AH = sum P(score) * (AH_settlement_return - 1)
```

This preserves full pushes, half wins, and half losses. A large UCD study found different loss rates among AH refund structures, so AH cannot be reduced to a binary win probability. [Hegarty–Whelan](https://www.ucd.ie/economics/t4media/WP23_13.pdf).

## League-selection policy

### Tier A: full ratings and priority scanning

- High-total O/U: Bundesliga, Eredivisie, 2. Bundesliga, Allsvenskan, Denmark Superliga.
- Low-total O/U: Spain Segunda, Serie B, Ligue 2, England Championship.
- AH: prioritize senior leagues with deep line history and reliable identifiers. Average goals should not determine AH eligibility.

### Tier B: shadow until coverage and settlement improve

Norway Eliteserien, Switzerland Super League, Belgium First Division A, Scotland Premiership, Finland Veikkausliiga, Romania Liga I, and Ireland Premier.

### Exclude from official ROI initially

Youth, reserve, NCAA, ad-hoc regional competitions, and any league with unreliable settlement or team matching.

## Aggressive operating profile

- Scan every supported senior fixture.
- Publish O/U and AH only.
- Maximum one official position per fixture.
- Allow up to 18 official picks per scan, without forcing the quota to be filled.
- Track an approximate 65% O/U / 35% AH mix, but never force market allocation.
- Prefer main-line prices around 1.75–2.10 until evidence supports wider bands.
- Rank by uncertainty-adjusted EV, price freshness, and league reliability.
- Classify non-qualified opportunities as `WATCHLIST`, `SHADOW`, or `NO BET` instead of silently discarding them.

## Production acceptance tests

Before activating Formula v3:

1. Replay the exact live pipeline chronologically, including extraction, selection, Asian settlement, and flat-unit ROI.
2. Compare market-only, historical-only, and hybrid residual models.
3. Measure probability calibration, score-grid likelihood, flat-unit ROI, closing-line value, drawdown, and coverage.
4. Break results down by league, market, Asian line type, odds band, rating coverage, and formula version.
5. Promote only improvements that remain positive across multiple forward folds.
6. Persist model/formula version, lambda source, reference price, market-fit error, and rating coverage with every pick.

## Sources and limitations

The calculations use the public [Club Football Match Data](https://github.com/xgabora/Club-Football-Match-Data-2000-2025), [Swedish Football Dataset](https://github.com/Mongosaurusrex/swedish-football-dataset), and the 2026 [Allsvenskan official-fantasy data mirror](https://github.com/TopMarx/allsvenskan). Data completeness varies by league, and several Scandinavian leagues lack historical O/U/AH prices in the research dataset. Those samples identify scoring priors, not proven betting edges.

No formula guarantees profit. The objective is to retain broad scanning while making the official shortlist smaller, calibrated, reproducible, and honest about uncertainty.
