# FC model-performance audit — 6 October 2026

Source: repository report generated 2026-10-06T11:40:06Z, commit b8db751. No production settlement or staking was run.

## Evidence

The report contains 1,123 projection entries, 790 graded and 333 pending. Binary markets: 1X2 112/194 wins (57.73%, Brier 0.2401), BTTS 92/191 (48.17%, Brier 0.2521). BTTS predicted 57.04% on average: an 8.87 percentage point gap. These are displayed projections, not an Official or locked-pick cohort.

Asian outcomes are AH 61 W, 22 HW, 21 HL, 81 L, 16 push; O/U 86 W, 17 HW, 17 HL, 77 L, 7 push. Counting any positive payout as a win gives AH 83/185 = 44.86% and O/U 103/197 = 52.28%. Across markets there are 390 positive-payout results out of 767 non-push results: **50.85%**, not the report's 52.35%. The old overall denominator subtracted push twice.

The old AH/O/U Brier compared P(full-win + half-win) to a fractional outcome that assigned 0.5 to both half-win and half-loss and excluded push. These are different events. Historical Asian Brier/calibration gaps must be recomputed from the original grades; they cannot justify parameter fitting as reported. The revised report scores the positive-payout event including push, and reports log loss separately from hit rate.

The local checkout has the aggregate report and 100 recent detail rows, representing only 18 distinct match/kickoff pairs. The complete projection ledger and grades are absent. Repeated lines/sides from one fixture are correlated. A chronological, fixture-separated training/validation split and authoritative result-evidence audit cannot be reconstructed from these aggregates. No verified full-history ROI or improvement percentage is claimed.

## Changes and interpretation

- Correct aggregate denominators, deduplicate grades by ledger ID, and align Brier/log loss/calibration with the prediction event.
- BTTS research revision: blend the raw score-model binary probability 50/50 with the complete same-market no-vig quote. Yes/no still sum to one; preserve raw probability and adjustment provenance. This is conservative shrinkage, **not a fitted or validated calibration curve**. Keep Official disabled. It may reduce overconfidence but may also remove useful edges; prospective evaluation is required.
- Corner pricing: use all offered complete pairs, retain quarter lines, evaluate payout-aware fair odds and EV, and subtract the same 0.02 uncertainty penalty as primary markets. Display a balanced offered line and choose its side by EV, rather than maximizing raw probability across extreme lines.
- Preserve corner AH's own quoted price, compute pair-scoped no-vig, and publish the same selected offer to both card analysis and projection output. Display actual price, line and EV, or an explicit missing-price state.
- Do not assume TI=10 card quotes are yellow=1/red=2 booking points; unverified card units are not priceable.

## Verification and deployment

Run tests for quarter payout pricing, complementary BTTS shrinkage, push denominators and half-outcome calibration. Refresh the scan and projection performance report on the VPS after deployment. Existing published reports and snapshots are historical and are not retroactively rewritten by this patch.

Run the revised grader on the VPS with its full ledger. Compare pre/post cohorts by formula version using fixture-separated observations, complete prices, Brier/log loss and locked-pick ROI. Do not tune to the same 18-fixture recent detail sample or treat a single scan as accuracy evidence.
