# Unified MLB Totals v4.0

Status: experimental, deterministic, not calibrated, and not approved for
automatic staking.

## Single active calculation

1. Estimate each starter's expected innings from season IP/GS, clamped to
   4.5-6.5 innings.
2. Blend starter ERA using 70% season form and up to 30% aggregate last-five
   form. Missing recent starts return their weight to the season sample.
3. Combine starter and bullpen run allowance over nine innings. ERA remains the
   main run estimator; starter and bullpen WHIP supply only a small capped
   baserunner adjustment to avoid double counting.
4. Estimate each team's runs as an equal blend of its season RPG and the
   opposing pitching staff's run allowance.
5. Apply the home park factor once. Current authoritative factors receive 75%
   reliability; historical fallbacks receive 35% reliability.
6. Blend the independent total 50/50 with the current market total.
7. Select OVER when the projected total is above the market and UNDER when it
   is below, then validate that exact side's decimal price.

```text
AwayRuns = 0.50 * AwayRPG + 0.50 * HomeStaffRunsAllowed
HomeRuns = 0.50 * HomeRPG + 0.50 * AwayStaffRunsAllowed
IndependentTotal = (AwayRuns + HomeRuns) * EffectiveParkFactor
ProjectedTotal = 0.50 * MarketTotal + 0.50 * IndependentTotal
Gap = ProjectedTotal - MarketTotal
```

## Decision bands

- absolute gap below 0.25: NO BET
- 0.25-0.39: LEAN, directional watchlist only
- 0.40-0.79: RISKY, shadow/watchlist only while calibration is incomplete
- 0.80 or more: STRONG, subject to quality caps
- selected-side decimal price below 1.85: downgrade to LEAN

Thirty innings are required. A 30-59.2 IP starter is a borderline sample and
cannot receive unrestricted confidence. Missing starters, total/price, team
RPG, bullpen ERA, park factor, or stale odds remain hard gates.

The engine also publishes an experimental Poisson Over/Under/Push distribution
and its difference from the no-vig market probability. It is a diagnostic only;
the legacy gap and data-quality gates remain authoritative until rolling
out-of-sample calibration is available.

## Why the formula changed

The archived v3 model multiplied a pitching-only total by a shrunk offense
ratio. When the day's starting pitchers were strong, this could shift nearly
the entire slate toward UNDER. V4 puts actual team scoring and opposing staff
allowance on the same runs/game scale and gives each equal weight. It does not
force equal OVER/UNDER counts; it removes the built-in direction bias.

Historical OU_V2_3 and OU_V3 runs remain immutable for audit purposes, while
new analysis creates only OU_UNIFIED runs.
