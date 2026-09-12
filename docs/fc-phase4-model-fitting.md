# FC Phase 4 — model fitting and artifact versioning

## Status and safety boundary

Phase 4 is engineering-complete for an isolated, reproducible model candidate. It does **not** establish predictive quality, calibration, edge, win rate, or ROI. The candidate and baseline are `unvalidated`, `official_eligible=false`, and not connected to the website, scanner, policy, staking, or ledger. Phase 5 chronological evaluation is mandatory before any approval decision.

## Implemented model

For one competition, with season-specific base rate and home advantage:

```text
log(lambda_home) = mu_season + home_advantage_season * home_indicator
                   + attack_home_team + defence_vulnerability_away_team
log(lambda_away) = mu_season
                   + attack_away_team + defence_vulnerability_home_team
```

Attack and defence-vulnerability effects are centered to sum to zero on every objective evaluation. Positive defence means greater defensive vulnerability. Parameters use L2 shrinkage, and match likelihoods use exponential time weights:

```text
w = exp(-ln(2) * age_days / half_life_days)
```

Only the registered half-life candidates 90, 180, and 365 days are accepted. Phase 4 uses 180 days for the frozen candidate; choosing among them is explicitly deferred to Phase 5 inner validation. The Dixon-Coles rho is fitted with shrinkage toward zero and mapped inside the valid low-score mass interval. Inference re-checks the fixture-specific rho bounds and returns `invalid_model` rather than silently replacing rho or producing a confident projection.

## Frozen artifacts

- Candidate: `dixon_coles_regularized-2f1078c1bb97c70b`
- Baseline: `ratio_baseline-a69a6bc3897beb28`
- Dataset: E0 seasons 2024/25 and 2025/26, 760 results available by cutoff `1779649200` (`2026-05-24 19:00:00Z`)
- Training data SHA-256: `81e741d912dff9f48a279c0bf69db317babc509ebd3471d328729a3b52c67c63`
- Candidate half-life: 180 days; effective sample size: 509.4274
- Optimizer: SciPy SLSQP; 40 iterations; objective 2159.352315259871; fitted rho -0.120490940781
- Identifiability diagnostics: attack sum 0, defence-vulnerability sum 0

The first diagnostic attempt, `dixon_coles_regularized-bfb3bc06a3f4672a`, exposed a reference-team/L-BFGS line-search stall: one iteration and zero team effects. It remains immutable for audit but is explicitly `rejected_engineering` in `phase4-model-registry.json`; it is not the selected Phase 4 candidate.

## Inference and OOD behavior

`project_fixture` is the only artifact-to-score-distribution function for both future live adapters and offline replay. It supports both the DC candidate and ratio baseline.

- A known season and adequately covered teams return `projection_ready_unvalidated`.
- A promoted/unseen team receives the league-mean zero effect and an explicit `projection_only_out_of_domain` reason. It can be displayed as a projection but cannot become official.
- An unknown season is blocked because no season intercept exists.
- Low team coverage is labeled projection-only.
- Invalid artifact hashes, invalid rho, or score-matrix failures fail closed; there is no hidden independent-Poisson fallback.
- Neutral fixtures remove home advantage when the caller supplies verified neutral-venue evidence.

## Reproduce

From `E:/MLB-Project`:

```powershell
$env:PYTHONPATH='betting-machine-fc'
python -m football_formula_engine.fit_cli `
  --csv betting-machine-fc/data/E0_2425.csv --season 2425 `
  --csv betting-machine-fc/data/E0_2526.csv --season 2526 `
  --competition E0 --timezone Europe/London `
  --cutoff 1779649200 --half-life-days 180 `
  --artifact-root betting-machine-fc/football_formula_engine/artifacts
```

The append-only store must report `deduplicated` for both selected artifacts on a repeat run. A new ID or conflict is a reproducibility failure.

## Phase 4 acceptance and remaining work

Engineering acceptance requires deterministic repeated fits, strict result-availability cutoff, a valid artifact hash, converged nontrivial parameters, explicit OOD handling, and common score-distribution inference. These are covered by focused tests and the frozen artifact checks.

Still deferred to Phase 5:

- chronological folds and leakage-safe train/calibration/policy/test splits;
- baseline-vs-DC predictive scoring, calibration, uncertainty refits, and ablation;
- half-life/penalty/rho selection using inner validation only;
- ROI/CLV evaluation, which remains `NOT_EVALUABLE` for the current historical quote manifest because timestamps are absent;
- any model approval, official pick, UI integration, or runtime activation.

Rollback is selecting the retained baseline for analysis or disabling the candidate. No locked pick or legacy artifact is changed.
