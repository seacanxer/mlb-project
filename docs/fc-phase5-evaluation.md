# FC Phase 5 — chronological evaluation, calibration, and uncertainty

## Outcome

Phase 5 is engineering-complete, but the Formula Final candidate is **not approved**. The evaluation succeeded as an audit: it selected the best preregistered inner-period configuration, evaluated it once on the untouched test, preserved negative results, and kept `official_enabled=false`.

The strongest honest conclusion is mixed:

- The selected DC candidate improves score log loss and 1X2 Brier versus the ratio baseline.
- It only narrowly improves score log loss versus league-average Poisson.
- It is materially worse than league-average Poisson for BTTS and O/U 2.5 Brier.
- No historical ROI or CLV is defensible because the available quotes have no decision-time timestamps.
- The local dataset has two seasons, not the three-season target. Football-Data lists E0 2023/24, but its download endpoint rejected this environment's TLS requests and later returned rate limiting. No substitute data was fabricated.

## Frozen protocol

The complete protocol is stored in `evaluation_spec.json` before running the test:

| Stage | Season | Warmup/training cutoff | Evaluation matches |
|---|---|---:|---:|
| Calibration | 2024/25 | first 100 matches | next 99 |
| Policy validation | 2024/25 | first 199 matches | remaining 181 |
| Untouched test | 2025/26 | prior season + first 80 matches | remaining 300 |

Boundaries require every target kickoff to occur after the training result-availability cutoff. Same-kickoff matches cannot appear on opposite sides of a cutoff. All candidates from a fixture remain in the same split.

The preregistered candidates were:

- half-life: 90, 180, 365 days;
- calibration: identity or coherent exponential tilt;
- tilt L2: 1, 5, 20;
- primary selection metric: policy-validation score log loss.

Policy validation selected half-life 365 with identity calibration at score log loss `3.075326278599`. The nearest tilt challenger, H365/L2=20, scored `3.075630265466`; therefore calibration coefficients correctly remained zero rather than forcing complexity.

## Untouched-test results

All values below cover the same 300 E0 2025/26 fixtures.

| Model | Score log loss | 1X2 Brier | BTTS Brier | O/U 2.5 Brier |
|---|---:|---:|---:|---:|
| Selected DC, H365, identity | 2.947677 | 0.637169 | 0.256070 | 0.262745 |
| Regularized independent Poisson | 2.950527 | 0.637776 | 0.256801 | 0.262745 |
| Ratio baseline | 3.091031 | 0.670677 | 0.267693 | 0.261185 |
| League-average Poisson | 2.951102 | 0.659951 | **0.244679** | **0.246848** |

DC's rho improves the joint score/1X2 result slightly over its rho=0 ablation. However, both team-strength models underpredict BTTS Yes and Over 2.5 on this test: selected-candidate bias is `-0.076108` for BTTS and `-0.075810` for Over. This is precisely why selection cannot rely only on aggregate score likelihood or a win-rate narrative.

## Coherent calibration

The implemented challenger follows the frozen Formula Final:

```text
P_cal(x,y) proportional to P_base(x,y) * exp(c dot g(x,y))
g = [I(total<=2), I(home win), I(draw), I(BTTS yes)]
```

Coefficients are fitted by penalized score log loss using calibration predictions only. The calibrated matrix is renormalized once, every market is derived from that same matrix, and the tail bound is conservatively expanded by the tilt spread. Independent per-market probability patches are not allowed.

## Bootstrap uncertainty

Eight deterministic moving-block refits were written as independent append-only checkpoints. This validates interruption/resume behavior and produced the following smoke quantiles:

| Metric | q10 | median | q90 |
|---|---:|---:|---:|
| Score log loss | 2.980557 | 3.022875 | 3.070412 |
| 1X2 Brier | 0.641746 | 0.653343 | 0.662676 |
| BTTS Brier | 0.259287 | 0.264976 | 0.273156 |
| O/U 2.5 Brier | 0.265104 | 0.273115 | 0.288342 |

The preregistered minimum is 30 successful refits, so the result is explicitly `UNCERTAINTY_UNAVAILABLE_INSUFFICIENT_REPLICATES`. These are parameter-refit diagnostics, not ROI confidence intervals or proof of profitable betting.

## Artifacts and decisions

- Evaluation: `evaluation-61c14ceaa9f16466`
- Selected pre-test model: `dixon_coles_regularized-29d19964b6c40c9f`
- Selected calibration: `coherent-tilt-36263b93397bb7f3` (`identity`)
- Uncertainty: `uncertainty-218e8b1a6786cbee`
- Validation registry: `validation-57cebeb53aecbdab`

Segment decisions:

- 1X2: `paper_only_not_approved`.
- BTTS: `not_approved`, worse than league-average baseline.
- O/U 2.5: `not_approved`, worse than league-average baseline.
- AH: `not_evaluated`; binary shortcuts are not valid for five-outcome Asian payouts.

Phase 6 may implement the policy and ledger fail-closed, but this registry must generate no official candidates. A new quality evaluation requires a newly frozen spec, a third season or multiple outer periods, enough bootstrap refits, and point-in-time executable quotes for ROI/CLV. The current untouched-test result must not be reused for retuning.

## Reproduce and resume

```powershell
$env:PYTHONPATH='betting-machine-fc'
python -m football_formula_engine.evaluation_cli
python -m football_formula_engine.uncertainty_cli --evaluation-id evaluation-61c14ceaa9f16466
```

The first command must deduplicate the evaluation, model, calibration, and prediction artifacts on repeat. The second resumes all eight replicate checkpoints and deduplicates the uncertainty and validation artifacts.
