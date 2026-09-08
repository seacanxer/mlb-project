# FC analysis engine: quality audit and patch

Date: 2026-09-08. Scope: local Python/SQLite FC engine and its five analysis surfaces. No production deployment or production database mutation was performed. This is a correctness/noise-reduction patch, **not a validated profitable strategy**.

## Executive finding

Increasing filters is not a substitute for calibration. The engine had inconsistent calculations between menus, unsupported adjustments, shadow promotion, and mutable recommendation locks. These make a displayed edge and historical ROI difficult to trust. Fixing them improves integrity, but the historical evaluation below does not establish profitable ROI. Empty shortlists are acceptable; volume is not a target.

## Findings and implemented changes

| Area | Failure mechanism | Local patch |
|---|---|---|
| Formula | Attack/defence normalization changed fitted goal intensity without re-estimating intercepts. | Refit home/away intercepts after normalization and final rating clamps; invalidate old rating caches with `poisson-intercept-v2`. Preserve intercept precision. Formula version `ou-ah-v4.1.0`. |
| Formula / Match Prediction | Separate 9x9 and 11x11 score matrices; integer pushes counted as Under wins; quarter lines not consistently stake-aware. | Shared normalized 11x11 matrix; explicit full win, half win, push, half loss, full loss; fair price and EV use stake payouts. Reject invalid inputs/DC distributions. |
| Top Picks | Shadow noise and multiple exposures on a fixture; full coverage alone treated as quality. | Default excludes shadow. Require independent team ratings (`market+strength`), paired market prices, positive conservative EV, odds gates; at most one pick per fixture. Shadow remains explicit research-only selector opt-in. |
| Match Prediction | Highest outcome probability labelled a recommendation without checking price; invented lambda/squad defaults and extra home multiplier. | Offered-price candidates must pass shared policy. Manual adjustments are scenario-only and cannot recommend bets. Missing inputs fail explicitly (API 422); unsupported squad adjustment disabled. Old formula/started fixtures cannot recommend. |
| Market Intel | Elo path could promote shadow coverage to full and used a separate recommendation policy. | Shared projection and candidate selector; remove coverage promotion; stale legacy recommendations sanitized even under explicit filters. Single-book observations remain WATCH, not independent market confirmation. 24-hour scan. |
| Parlay Picks | Controlled fill relaxed tier gates to populate slips. | Remove fill; insufficient candidates remain insufficient. Future, rated, policy-qualified legs only. Explain independence and push/half-outcome limitations of joint probability. Tier names avoid implying safety. |
| Model detail | Raw diagnostic candidates displayed as official picks. | Only shared-policy-qualified, future candidates displayed as recommendations; show source, formula, coverage, unvalidated status and stress EV. |
| ROI provenance | A later scan could replace a pending lock with a higher-EV selection/price. | Immutable fixture locks plus `bet_audit` snapshot for new locks. Old records remain untouched. Current candidates are not falsely labelled locked when an existing lock differs. |
| Cross-menu consistency | Extra fatigue multipliers applied outside projection in only some paths. | Remove the unvalidated post-projection multiplier; schedule ledger remains. No fabricated fatigue advantage. |

The quality policy tests four scoring-rate perturbations: (−10%,−10%), (+10%,+10%), (−10%,+10%), (+10%,−10%). Minimum stressed EV must still clear the conservative threshold. This is an engineering robustness test, **not** a confidence interval, fitted calibration, or established optimal threshold. It may suppress valid bets as well as noise.

## Research rationale

Combining historical and bookmaker information has methodological precedent, but using market inputs is not independent proof of edge against the same market. Egidi, Pauli and Torelli fit a hierarchical Poisson mixture and evaluate a subsequent season after historical training. Our implementation is not a replication of their hierarchical model. [Primary paper](https://arxiv.org/abs/1802.08848).

Calibration deserves explicit evaluation alongside accuracy and ROI. Walsh and Joshi study calibration-based selection in sports betting, but their experiment is NBA-based; its performance numbers cannot be transferred to this football engine. [Primary paper](https://arxiv.org/abs/2303.06021).

Therefore the evaluation compares Brier score and log loss to a no-vig market baseline, uses past-only training, and leaves research calibration inactive in the live engine.

## Chronological local evaluation

Reproduce from `betting-machine-fc`:

```powershell
python evaluate_quality.py --output research/quality-evaluation-refit.json
```

Inputs: local football-data-style `E0_2526.csv`, `D1_2526.csv`, `SP1_2526.csv`. O/U 2.5 only. At least 150 preceding matches, monthly expanding rating fits. Every rating training date precedes its evaluated fixture date. Research residual shrinkage selects its coefficient using only earlier-date outcomes and is **not activated live**.

| League | Evaluated matches | Market Brier ↓ | Refit model Brier ↓ | Quality bets | Quality profit |
|---|---:|---:|---:|---:|---:|
| EPL | 230 | 0.248790 | 0.252983 | 0 | 0 units; ROI unavailable |
| Bundesliga | 156 | 0.218673 | 0.220574 | 2 | −2 units; ROI −100% |
| La Liga | 229 | 0.251680 | 0.250001 | 0 | 0 units; ROI unavailable |

615 evaluated matches do **not** mean 615 selected bets. There are only two quality bets; both lost. The model underperforms the market Brier baseline in two of three leagues. La Liga's small Brier improvement does not establish tradable profit. Aggregate selected ROI is −100% on two bets, far too little evidence to infer a stable long-run rate.

The pre-refit diagnostic output (`quality-evaluation.json`) is retained to expose sensitivity, not to select the best-looking result: 33 quality bets returned +7.44 units before the intercept fix. That apparent profit collapsed after a mathematical correction. Cherry-picking that earlier output would misrepresent the final patch.

The `old_profit` comparison reconstructs old thresholds on the same refit candidates. It is **not** an exact replay of deployed historical software. CSV prices have no captured execution timestamps or available-liquidity guarantee. The test does not validate AH, parlays, line movement, live API reliability, or every supported league. Built-in historical backtests should not be assumed leakage-free based on this separate evaluator. No bootstrap confidence interval or untouched multi-season final holdout was completed.

## Release and further validation

The patch is suitable for review and paper tracking, not a claim of production ROI improvement. It intentionally permits zero picks. Do not loosen gates merely to restore daily volume, and do not call WATCH an official recommendation.

Before describing the engine as profitable:

1. Collect timestamped model inputs, offered odds, fixture identity, formula/policy versions, settled outcomes and closing prices. New lock snapshots begin provenance capture; they do not reconstruct old missing data.
2. Add multiple seasons and expanding chronological folds; tune decay, shrinkage, home advantage and low-score dependence only on training/validation windows. Keep a final season untouched.
3. Evaluate calibration/reliability, Brier, log loss, ROI uncertainty, drawdown and closing-line value by league and market. Require enough selected observations; no arbitrary daily pick quota.
4. Validate AH and quarter-line calibration separately. Parlay independence is an approximation even with different fixtures; avoid interpreting product probabilities as calibrated slip profit probability.
5. Paper-track the exact new formula/policy with immutable flat-unit locks. Version-separate new results from legacy ROI. Promote only after out-of-sample evidence exceeds the market baseline and holds up under realistic execution assumptions.

## Verification

- 88 Python tests pass in an isolated temporary SQLite database.
- JavaScript syntax check passes; client O/U integer/quarter-line payout regression passes.
- Tests cover distribution consistency, Asian settlements, rating intercepts, no fabricated inputs, no Elo shadow promotion, immutable locks, missing-input API 422 and legacy Intel suppression.
- Full visual browser QA and deployment were not performed. Production behavior changes only after deployment and a fresh scan/rebuilt rating cache.
