# FC quality audit and defensive model revision — 9 October 2026

## Inputs and scope

Reviewed the supplied HTML summary and the supplied VPS projection_ledger.jsonl
and projection_grades.jsonl, without mutating those originals or running
production settlement. Inputs contain 12,458 ledger rows and 10,321 grades.
10,505 ledger rows are market alternatives, 895 legacy projections, 768 primary
card picks and 290 secondary card picks. Grading was checked against stored
actual FT scores; independent provider evidence was not fetched in this audit.

## HTML verification

The previous CSV path included all market alternatives and selected the highest
probability per match name/market. Replaying that exact selection reproduces:

| Market | N | Paper ROI |
| --- | ---: | ---: |
| 1X2 | 216 | +0.38% |
| AH | 215 | -10.50% |
| O/U | 216 | -3.41% |
| BTTS | 216 | -11.55% |
| Total | 863 | -6.266% |

Paper profit is -54.079u, matching the HTML's -54.08u. This cohort is **not** the
card's chosen forecasts. Highest-probability selection brings in extreme low-odds
alternative lines and merges separate fixtures with the same match label. Thus
the HTML's distribution of trivial odds cannot be read as the card selection's
distribution. Its Brier pair 0.1743/0.1696 was not reproduced with the correct
binary event: the reconstructed 1X2+BTTS cohort gives 0.2451 vs 0.2360 using
inverse single odds, which include margin. It is not a no-vig benchmark.

## Card-only and temporal audit

Choosing the first recorded pick per home/away/kickoff/market, across provider
IDs, yields 871 graded primary card picks from 219 fixtures. No score-grading
mismatches and no binary EV arithmetic mismatches were found.

| Cohort | N | Hit rate, excluding pushes | Brier | Log loss | Paper ROI |
| --- | ---: | ---: | ---: | ---: | ---: |
| First card pick, all logging times | 871 | 51.47% | 0.2478 | 0.6885 | -5.50% |
| Logged and quoted before kickoff | 345 | 53.39% | 0.2443 | 0.6815 | -3.50% |

526 graded choices in the first cohort fail the prospective timing test. Across
all card ledger entries, the corrected report excludes 727 after-kickoff rows
and removes 246 remaining duplicate entries. It has 980 unique eligible entries:
345 graded and 635 pending. Original ledger/grades remain untouched.

All-card AH ROI is -13.58%, BTTS -7.54%, O/U -1.88%, 1X2 +0.93%. AH contributes
-29.3275u; BTTS -16.439u. Overall all-card bootstrap ROI CI is -13.56% to +2.15%
(5,000 resamples by fixture); prospective CI is -16.41% to +9.40%. The corrected
overall CI includes zero, unlike the different HTML cohort.

All-card probability buckets show realized-minus-predicted gaps of -12.4pp at
0.6–0.7 (n=167) and -14.5pp at 0.7–0.8 (n=57). These are descriptive historical
gaps, not a fitted mapping to deploy. Prospective AH/BTTS/O-U sample sizes are
86/86/87; their respective calibration gaps are +1.6/-3.1/-1.8pp. Aggregate
calibration can mask poor selection within high-EV subsets.

## Implemented changes

1. **Abstain:** primary card choices require positive EV and nonnegative EV after
   the existing 0.02 heuristic penalty. Detailed alternate analysis and goal
   projections remain. This is not a bootstrap lower-bound guarantee.
2. **AH direction:** the requested alignment with the 1X2 favorite is preserved,
   but negative-EV aligned AH is withheld rather than forced onto the card.
3. **Model-market disagreement:** hold primary selections when raw payout-price
   probability differs by more than 15pp from the complete no-vig market. For
   Asian bets the comparison is W/(W+L), W=P(full win)+0.5P(half win),
   L=P(full loss)+0.5P(half loss), not the unconditional chance of positive payout.
4. **AH anchoring:** extend the existing BTTS 50/50 market safety blend to AH in
   payout space. Preserve push mass, quarter lines, and the full/half outcome
   ratios; recompute EV and fair odds. This fixed defensive weight is unvalidated
   and is not described as fitted calibration. 1X2 and O/U probabilities remain
   from the goal matrix; their quality gates still apply.
5. **1X2 display floor:** suppress odds below 1.30 in scanner forecasts, React
   card/detail/value paths and new ledger logging, including cached legacy
   predictions. Exactly 1.30 remains allowed. Do not replace a suppressed favorite
   with an unlikely underdog to fill the card. Historical settled picks remain.
6. **Evaluation integrity:** report/CSV now share card-only, before-kickoff,
   earliest-choice rules. CSV reads nested FT score actuals. Pending is based on
   unique eligible entries, so discarded duplicates cannot inflate it.
7. **Future evidence:** new logs preserve no-vig probability, raw paid-probability,
   raw prediction, chosen weight, adjustment version and payout distribution.
   Scanner formula/policy versions change to identify the new cohort.

## Calibration and replay limits

Only 34 prospective 1X2 and 34 prospective BTTS rows have all complementary odds
from the identical captured quote. On those subsets model/market Brier is
0.2306/0.2341 for 1X2 and 0.2576/0.2579 for BTTS. These small cohorts do not
establish an edge.

The walk-forward experiment requires 30 completed, already-graded training rows
before each prediction. Zero held-out rows meet that timing requirement with
complete quotes. No fitted calibration weights are deployed.

Merely screening stored EV >=2% on the 345 prospective picks leaves 106 with ROI
-4.18% — **not an improvement**, and not a backtest of the new AH formula. A
limited fixed-policy binary replay on complete quotes keeps 7/34 1X2 (+14.31%
paper ROI) and 2/34 BTTS (-4.00%). It retains historical sides and lines, so it
cannot simulate a new full scan or support an accuracy claim. No comparable
full AH replay is available from complete stored distributions/quotes.

The usable next validation cohort must record forecasts before kickoff, full
paired prices, training cutoff and closing quotes. Grade the new version
separately and compare Brier, log loss, ROI CI by fixture, calibration buckets
and CLV. Avoid adopting a tuned weight from this short retrospective window.

## Verification and release

Verification: 323 Python tests passed, 237 Vitest tests passed, TypeScript
typecheck passed, and git diff --check passed. Regression coverage includes quarter payout
anchoring, disagreement holds, abstain, 1.29/1.30 boundaries, first-seen/provider
dedup, after-kickoff exclusion and nested score export.

Settlement DB, actual staking, locks and tracker ROI are unchanged. This work
does not guarantee a higher win rate. It corrects evaluation and removes
demonstrably unsafe forced selections; fewer daily card picks are possible.
Commit/push and VPS deployment have not been performed for this task.

Machine-readable evidence: fc-ledger-quality-audit-2026-10-09.json.
