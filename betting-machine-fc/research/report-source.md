# O/U and Asian Handicap Prediction Research

Audience: FC Betting Machine owner and model maintainer
Research date: 4 September 2026 (WIB)
Status: research and design only; no production logic changed

## Scope and assumptions

This research evaluates how the current engine should prioritize football leagues and improve Over/Under (O/U) and Asian Handicap (AH) probabilities. It combines a code-path audit with match-level calculations from completed seasons.

- Winter-season leagues: July 2022 through June 2025 from Adam Gabor's match dataset, sourced from Football-Data.co.uk.
- Sweden: completed 2023, 2024, and 2025 seasons from Nathan Dygant's Swedish football dataset.
- Sweden 2026 check: 142 completed Allsvenskan fixtures through the repository snapshot dated 26 August 2026.
- Current production ROI observations from the previous audit are diagnostic, not proof that any future strategy will be profitable.
- League averages are priors. A high-scoring league is not automatically an Over bet because the bookmaker adjusts both the line and price.

## Executive answer

The preferred O/U and AH focus is statistically sensible, but the current engine is not yet exploiting those markets correctly. It calculates live picks from lambdas fitted to 1X2 prices, while the total inferred directly from O/U prices is displayed but not used. The independent-strength formula also divides normalized attack and defence ratings by the league average a second time, materially depressing expected goals for covered leagues.

The recommended engine is a dual-market, league-aware model:

1. Estimate independent team scoring rates with league-level partial pooling.
2. Infer a market total directly from no-vig O/U prices and a market goal-difference distribution directly from no-vig AH prices.
3. Combine the independent estimate and a separate reference market using weights learned out of sample for each league/market.
4. Produce O/U and AH expected payouts from one coherent score grid, including pushes and half outcomes.
5. Scan broadly, but publish only fixtures that pass league data-quality, model-calibration, price, and uncertainty gates.

## What the league data says

### High-goal candidates

| League | Matches | Goals/match | Over 2.5 | Blind Over ROI* | Interpretation |
|---|---:|---:|---:|---:|---|
| Germany Bundesliga | 918 | 3.175 | 60.9% | -2.55% | Strong, stable high-total prior |
| Netherlands Eredivisie | 918 | 3.095 | 59.5% | -3.88% | Priority league, but the market prices it aggressively |
| Norway Eliteserien | 676 | 3.095 | 60.8% | unavailable | High baseline, greater season variation |
| Germany 2. Bundesliga | 918 | 3.021 | 59.4% | -2.86% | Strong O/U research target |
| Denmark Superliga | 451 | 2.849 | 55.2% | unavailable | Moderate-high and stable |
| Sweden Allsvenskan | 720 | 2.817 | 54.0% | unavailable | Selective rather than automatic Over |

\*Blind ROI means betting every available Over 2.5 at the recorded Bet365 price. Negative results show why goals per match alone is not an edge.

The completed 2025/26 Eredivisie season reached roughly 3.2 goals per match according to the league itself. The local Football-Data file independently produces 3.176 goals per match and 61.8% Over 2.5. The Bundesliga's official 2024/25 review reports 3.13 goals per match; the three-season sample is similarly high at 3.175.

Allsvenskan is not uniformly a “goal rain” league. Its 2023–2025 average was 2.817 with a stable 54.0% Over 2.5 rate. The incomplete 2026 sample increased to 3.042 goals and 56.3% Over 2.5 through 142 finished matches, but it should retain an in-season uncertainty penalty.

### Low-goal candidates

| League | Matches | Goals/match | Over 2.5 | Primary use |
|---|---:|---:|---:|---|
| Spain Segunda | 1,386 | 2.266 | 40.1% | Under candidate |
| Italy Serie B | 1,140 | 2.443 | 45.1% | Under candidate |
| Ireland Premier | 527 | 2.465 | 46.3% | Under candidate if price/settlement are reliable |
| France Ligue 2 | 1,064 | 2.477 | 46.1% | Under candidate |
| Romania Liga I | 732 | 2.500 | 45.4% | Under candidate if data coverage improves |
| England Championship | 1,654 | 2.521 | 46.9% | Selective Under; substantial season movement |

These are Under priors, not instructions to bet every Under. In the same dataset, blind Under strategies generally still lost after bookmaker margin.

### Team variation matters more than the league label

For the completed 2025/26 Eredivisie season, matches involving PSV averaged 4.29 total goals and cleared Over 2.5 in 85.3%; NEC averaged 3.82 and 73.5%; Heracles averaged 3.53 and 70.6%. At the other end, Volendam averaged 2.65, NAC Breda 2.74, and Groningen 2.76.

For Allsvenskan 2025, Varnamo matches averaged 3.50, Sirius 3.47, Norrkoping 3.23, and Elfsborg 3.20. AIK averaged 2.43, Halmstad 2.47, Goteborg 2.47, and Mjallby 2.50. This is why Sweden should be selected through team-style interactions, not a blanket league rule.

## Why the current engine overlooks or misreads those leagues

1. `fit_total_from_ou()` is called, but its fitted total is only stored as `fair_over25`; live selections still use `lam_from_1x2()` lambdas.
2. `strength_lam()` is on the wrong scale. Neutral teams in a league averaging 1.459 goals per team should imply about 2.918 total goals; the current formula yields about 1.420.
3. Sweden, Norway, Denmark, Switzerland, Austria, and Finland are absent from the independent rating map, so these leagues normally fall back to market-only estimates.
4. A fixed global Dixon-Coles rho and fixed 40% strength weight are used across leagues without out-of-sample selection.
5. The selector ranks raw probability heavily even though production results show poor probability calibration.

On the stored Eredivisie odds snapshot dated 29 August 2026, the strength bug pushed estimated totals down to 2.60 for Excelsior–Sparta, 2.96 for AZ–Go Ahead, and 2.85 for PEC–NEC. The resulting candidates leaned toward Under despite O/U market lines around 3.0–3.5. This snapshot is illustrative, not a current match recommendation.

## Recommended formula architecture

### 1. Independent scoring model

Use league-specific intercepts and partial pooling:

```text
log(lambda_home) = mu_league,t + home_adv_league,t
                   + attack_home,t + weakness_away,t + beta * context

log(lambda_away) = mu_league,t
                   + attack_away,t + weakness_home,t + beta * context
```

Attack and defensive weakness should be centered for identifiability. Promoted/new teams should shrink toward the league mean or an adjacent-league prior. Time decay must be selected through walk-forward validation per league family instead of fixed globally.

Useful pre-match context is limited to information available before kickoff: reliable expected-lineup/goalkeeper changes, complete rest schedules including cups, travel, red-card suspensions, and stable shot/xG form. Raw finishing streaks must regress toward expected-goal or shot-quality baselines.

### 2. Fit the markets the user actually bets

- O/U: solve for total intensity `T_market` from the no-vig Over and Under prices at the main Asian total line, using exact push/half-push payouts.
- AH: solve for the goal-difference distribution `D_market` from both handicap prices at the quoted line.
- Convert to coherent team rates when feasible: `lambda_home = (T + D)/2`, `lambda_away = (T - D)/2`, subject to positivity and joint-distribution validation.

Do not use the target bookmaker's own quote both to construct the probability and claim an edge against that same quote. Prefer a sharp/consensus reference market and compare it with the target price. If only one market feed exists, the independent historical model must provide the residual signal and uncertainty should be wider.

### 3. Market-residual calibration

Rather than a fixed 40/60 lambda blend, fit a regularized residual model:

```text
logit(p_final) = logit(p_reference_market)
                 + alpha_league_market
                 + f(model_minus_market,
                     rating_coverage,
                     line,
                     odds,
                     season_phase,
                     lineup_quality)
```

Fit separate calibrators for O/U and AH and preferably for major line families. Weights must be learned only from earlier matches in rolling time splits. Market odds are strong forecasts, while research on combining bookmaker odds with historical Poisson estimates supports treating the market as an informative input rather than ignoring it.

### 4. Distribution and payout layer

Start with a dynamic bivariate Poisson/Dixon-Coles score grid, estimate dependence by league pool, and test its residual dispersion and tail calibration. If high-total tails remain underpredicted, compare against a negative-binomial/Poisson-mixture alternative. Dynamic bivariate Poisson research supports time-varying intensities; bivariate extensions explicitly address correlation between team scores.

For every offered line, rank expected payout—not a synthetic “win probability”:

```text
EV_OU = sum_score P(score) * (settlement_return(total, line, side, odds) - 1)
EV_AH = sum_score P(score) * (settlement_return(margin, line, side, odds) - 1)
```

Quarter lines must be split into adjacent half-lines. Integer lines retain push probability. AH research using large football datasets finds materially different realized loss rates by refund structure, reinforcing the need to model payouts explicitly.

### 5. Selection policy: aggressive scanning, selective publishing

Scan every supported senior fixture, but assign each to one of four states:

- `OFFICIAL`: calibrated positive expected payout, adequate coverage, valid reference price, and healthy settlement feed.
- `WATCHLIST`: plausible edge but insufficient rating or reference-market coverage.
- `SHADOW`: experimental league/model family; tracked but excluded from official ROI.
- `NO BET`: stale/incomplete odds, unsupported team mapping, poor fit, excessive uncertainty, or correlated duplicate exposure.

Suggested launch profile after validation:

- O/U and AH only.
- At most one official position per fixture.
- No fixed requirement to fill a quota; allow up to 18 official picks per scan.
- About 65% O/U and 35% AH as monitoring targets, not forced quotas.
- Prefer main lines between roughly 1.75 and 2.10 until calibration demonstrates otherwise.
- Rank by lower confidence bound of EV, then price freshness and league reliability.
- Keep youth, reserve, NCAA, and poorly settled competitions in shadow mode.

## League routing proposal

### Tier A: build full ratings and prioritize scanning

- O/U high side: Bundesliga, Eredivisie, 2. Bundesliga, Allsvenskan, Denmark Superliga.
- O/U low side: Spain Segunda, Serie B, Ligue 2, England Championship.
- AH: liquid senior leagues with reliable line histories; league inclusion should depend on AH calibration and closing-price quality, not average goals.

### Tier B: selective/shadow until coverage is strong

- Norway Eliteserien, Switzerland Super League, Belgium First Division A, Scotland Premiership, Finland Veikkausliiga, Romania Liga I, Ireland Premier.

### Exclude from official output for now

- Youth, reserve, NCAA, ad-hoc regional divisions, and competitions with unreliable match identifiers or settlement coverage.

## Validation requirements before production

1. Walk-forward replay that uses the exact live extraction, model, selector, payout, and settlement functions.
2. Baselines: no-vig market, market-only, historical-only, and hybrid residual model.
3. Metrics: log loss/Brier where applicable, reliability curve, ranked probability score or score-grid log likelihood, flat-unit ROI, CLV, maximum drawdown, and coverage.
4. Report by league, market, line family, odds band, model version, rating coverage, and season phase.
5. Promotion rule: positive calibrated edge across multiple chronological folds, not only aggregate ROI.
6. Persist `model_version`, `formula_version`, `lambda_source`, market-fit error, reference price, rating coverage, and scan ID with every pick.

## Material limitations

- The multi-league source is a public research dataset derived primarily from Football-Data.co.uk, not an official league database, and field completeness varies by league.
- Swedish historical data is scraped from Transfermarkt; the 2026 snapshot comes from a repository that mirrors the official Fantasy Allsvenskan API.
- Some league samples lack O/U or AH prices, so goal rates can identify priors but not historical betting edge.
- Current-season samples can move materially. League tiers must be recomputed regularly without fitting on future data.
- No model can guarantee satisfying returns; the target is better calibration and disciplined identification of positive expected payout.

## Claim-to-source ledger

| Claim family | Source | Publisher/author | Date | URL | Access note |
|---|---|---|---|---|---|
| Multi-league match and odds data | Club Football Match Data | Adam Gabor | 2025 | https://github.com/xgabora/Club-Football-Match-Data-2000-2025 | Repository cloned 4 Sep 2026; calculations reproduced locally |
| Swedish completed seasons | Swedish Football Dataset | Nathan Dygant | 2025 | https://github.com/Mongosaurusrex/swedish-football-dataset | Repository cloned 4 Sep 2026 |
| Sweden 2026 fixtures | Allsvenskan fantasy data mirror | TopMarx / official Fantasy Allsvenskan API | snapshot 26 Aug 2026 | https://github.com/TopMarx/allsvenskan | 142 finished fixtures in snapshot |
| Eredivisie 2025/26 average | Season closing statistics | Eredivisie | 27 May 2026 | https://eredivisie.nl/nieuws/betaald-voetbal-sluit-seizoen-af-met-mooie-cijfers/ | Official league page |
| Bundesliga 2024/25 average | European comparison | Bundesliga | 12 Jun 2025 | https://www.bundesliga.com/en/bundesliga/news/how-germany-compares-to-europe-s-other-top-leagues-2024-25-goals-attendance-32632 | Official league page |
| League style and imbalance | Performance and playing styles in 35 leagues | CIES Football Observatory | Oct 2017 | https://football-observatory.com/IMG/pdf/mr28en.pdf | Older structural evidence only |
| Dynamic score rates | Dynamic bivariate Poisson model | Koopman and Lit | 2015 | https://doi.org/10.1111/rssa.12042 | Peer-reviewed primary research |
| Correlated scores | Bivariate Poisson sports model | Karlis and Ntzoufras | 2003 | https://doi.org/10.1111/1467-9884.00366 | Peer-reviewed primary research |
| Historical plus market blend | Combining historical data and bookmakers' odds | Egidi, Pauli, Torelli | 2018 | https://arxiv.org/abs/1802.08848 | Primary preprint |
| AH refund structure | Do Gamblers Understand Complex Bets? | Hegarty and Whelan, UCD | May 2023 | https://www.ucd.ie/economics/t4media/WP23_13.pdf | University working paper |
| Probability calibration | Model selection: accuracy or calibration? | Hubacek, Sourek, Zelezny | 2023 | https://arxiv.org/abs/2303.06021 | Primary preprint |
