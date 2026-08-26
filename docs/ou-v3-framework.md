# MLB Totals O/U v3.1 — Experimental Framework

Status: experimental, not calibrated, not approved for automatic staking.

## Why v2.3 was replaced in the active display

V2.3 adjusted the market line with three heuristics. Its park term could dominate
the result, it omitted bullpen quality, recent ERA was not shrunk, and the
pipeline always supplied the Over price even when the formula selected Under.
V2.3 remains stored as a legacy comparator; V3 is a parallel model and does not
rewrite historical runs.

## V3 calculation pipeline

1. Treat the latest total as the market prior.
2. Estimate each starter's innings from season IP per start, clamped to 4.5–6.5.
3. Blend season ERA (75%) and aggregate last-five ERA (25%). When fewer than five
   recent starts are available, the missing recent weight returns to season ERA.
4. Build each pitching staff's expected runs allowed:

   `starter ERA × starter IP / 9 + bullpen ERA × remaining IP / 9`

5. Scale the opposing staff estimate by a shrunk team RPG factor. Extreme team
   factors are clamped and only half of the deviation from league average is used.
6. Apply the park factor once. A historical fallback receives 35% reliability;
   a current authoritative factor receives 75% reliability.
7. Blend independent total (40%) with market total (60%). This recognises the
   market as a strong prior and reduces unstable disagreement from incomplete data.
8. Resolve Over or Under from the sign of the gap, then validate that exact side's
   price. This fixes the V2.3 Under/Over-price mismatch.

The thresholds are provisional configuration, not fitted constants:

- absolute gap below 0.30: NO BET
- 0.30–0.49: LEAN (directional information only; cannot be locked)
- 0.50–0.89: RISKY
- 0.90 or more: STRONG GAP
- selected price below 1.85: downgrade to LEAN; never lock as a bet

V3.1 changes only the decision tiers; the projected-total formula and 60/40
market/model weighting are unchanged. This avoids fitting the projection to one
slate merely to manufacture more signals. Data quality below 80 caps STRONG to
RISKY, and below 70 caps RISKY to LEAN.

## Hard gates

- game already started
- missing/stale total or selected-side price (freshness: one hour)
- unconfirmed starter
- missing starter ERA/IP/GS or season IP below 60
- missing/stale team RPG
- missing/stale bullpen ERA
- missing/wrong-season park factor
- opening-to-current total move of at least one run
- gap below threshold or selected-side price below minimum

## Warnings and uncertainty

- 60–89 starter IP is a borderline sample
- fewer than five recent starts reduces recent-form weight
- fallback park factors are attenuated
- limited bullpen source is disclosed
- a 0.5–0.99 run line move is disclosed
- independent model disagreement above two runs is disclosed
- weather, roof, confirmed lineups, umpire and bullpen workload are explicitly
  reported as missing context until dedicated snapshots exist

The data-quality score describes input coverage. It is not a win probability.
The normalized bookmaker Over/Under probabilities are market reference only and
are not presented as model probabilities.

## Evidence behind the architecture

- MLB's expected statistics use quality of contact and xwOBA-derived measures;
  xERA should replace plain ERA when a reliable Statcast ingestion path is added:
  <https://baseballsavant.mlb.com/expected_statistics>
- MLB runs are overdispersed, so a fitted Negative Binomial distribution is a
  better probability-stage candidate than a simple Poisson assumption:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC8282683/>
- Temperature has a material relationship with run scoring, batting average,
  slugging and home runs, supporting a future weather/roof module:
  <https://journals.ametsoc.org/view/journals/wcas/5/4/wcas-d-13-00002_1.xml>
- Recent reliever workload affects velocity and decays over subsequent days,
  supporting bullpen-availability features rather than bullpen ERA alone:
  <https://ideas.repec.org/a/bpj/jqsprt/v14y2018i2p57-64n4.html>
- Large-scale strategy testing finds MLB betting markets difficult to beat after
  multiple-testing correction. This supports market shrinkage and strict
  out-of-sample validation:
  <https://www.tandfonline.com/doi/abs/10.1080/00036846.2024.2364115>
- Calibration can be more useful than raw classification accuracy for betting
  model selection:
  <https://arxiv.org/abs/2303.06021>

## Validation required before probabilities or staking

1. Persist official final scores and closing total/price for every analyzed game.
2. Freeze pregame snapshots at consistent horizons (for example T-6h and T-30m).
3. Fit distribution parameters only on a training window; never choose them from
   the test window.
4. Evaluate walk-forward by date using MAE/RMSE for totals, calibration/Brier or
   log loss for probabilities, closing-line value, yield and maximum drawdown.
5. Compare V3 against simple baselines: closing market line, opening line and V2.3.
6. Correct for multiple strategy/threshold trials and retain NO BET when the
   uncertainty interval crosses the market line.
7. Only after calibration passes should stake sizing be added, initially with a
   hard cap and fractional Kelly. Until then, the system publishes no stake.
