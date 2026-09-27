# FC pick engine P0 audit — 2026-09-27

Status: audit implementation and provisional ledger analysis ready for review.
**P0 acceptance remains blocked by missing authoritative inputs. P1 is not authorized.**
The requested root `coding-agent-brief-fc-pick-engine.md` is absent. No independently
verified manual-results ledger was provided. The supplied chat instruction defines
the current scope. No production settlement, historical re-settlement, gate,
staking, model coefficient or version changes are included.

## Evidence and reproducibility

Base commit: `51e3c74`. Local `bets.db` contains **0 bets**. The available tracker
snapshot contains **203 unique single picks**, **18 settled**, **185 overdue**
(**91.1330%** of rows). This is a snapshot status ratio, not a measured success rate
from a fresh settlement run. Parlays are excluded from probability calibration:
a slip's multiplied odds do not provide a joint predicted probability.

Local `input_snapshot.json` preserves the relevant fields from that snapshot;
its provenance includes the original file SHA-256. `reliability.json` hashes the
audit input. Both JSON files remain local and are excluded from this PR. All 18 available score/profit pairs agree with payout recomputation
within rounding tolerance; this establishes internal arithmetic consistency only.
There are **0 independent result confirmations**, so the confirmed cohort's Brier,
log loss, win rate and ROI are **unavailable**, not zero.

```powershell
python scripts/fc-p0-audit.py --snapshot betting-machine-fc/tracker_snapshot.json --out reports/fc-p0-audit/reliability.json
python -m pytest tests/unit/test_fc_p0_audit.py betting-machine-fc/football_formula_engine/tests/test_calibration_metrics.py -q
```

The audit reads JSON and writes only its report. It never imports the live scan
entrypoint, calls score feeds, writes a database or executes settlement.

Validation: **12 tests passed** (2026-09-27), including wrong-fixture and legacy
label defect reproducers, provider-side/quarter preservation, matrix orientation,
Asian fair-price invariants, probability buckets, endpoint log loss and existing
calibration metrics. The audit CLI generated the local JSON successfully.

## Locations and concrete findings

| Area | Code | Evidence / conclusion |
|---|---|---|
| Score matrix | `football_formula_engine/score_matrix.py:build_score_matrix` | Rows are home goals, columns away goals. Asymmetric lambda reversal preserves the expected home/away symmetry in a synthetic test. No orientation error found here. |
| Provider mapping | `scraper_1xbit.py:extract_markets`; `scripts/fc-scan-live.py:price_fixture` | O1/O2 map to home/away. Declared 1X2 types 1/2/3 map home/draw/away. AH away prices pair with the negated home line. Tests preserve offered +/−0.25 and O/U 2.25. This checks the adapter contract, not a fresh provider response. |
| EV/fair odds | `football_formula_engine/value.py` | EV = `(odds−1)*(FW+0.5*HW)−(FL+0.5*HL)`; fair odds = `1+loss/win`. Synthetic tests cover 50 AH and 42 O/U contracts, including quarters: EV at fair price is zero within 1e−12. No concrete side inversion found in this code. |
| Fixture matcher — ACTIVE BUG | `scores_flashscore.py:name_keys`, `build_lookup`, `find_result` | Full names are expanded into individual words, then treated as exact keys. A synthetic completed Manchester United–West Brom fixture is returned for Manchester City–West Ham on the same date. No league or stable provider fixture ID is checked in `result_for_bet`. Date tolerance is ±2 days. A matched row is not proof of fixture identity. |
| Legacy labels — ACTIVE BUG | `scripts/fc-settle-live.py:settle_bet` | A historical pick uses the format `Home (team name)`. The current 1X2 handler sends the entire lowercased label into the side dictionary and raises KeyError. There is no per-bet exception boundary in `main`, so one such historical row can abort the run before transaction commit. Reproduced offline with a synthetic label. |
| Historical score schema bug — already fixed | `scripts/fc-settle-live.py:result_for_bet` | Before `51e3c74`, settlement required `score_status=final` and `home_score/away_score`, while both feed adapters emitted `home_goals/away_goals` without that status. Current code accepts the actual schema. The old snapshot cannot prove the corrected code has been run against the VPS ledger. Re-settlement belongs to P1. |
| Report fair odds — ACTIVE REPORT BUG | local untracked `scripts/generate_fc_csv_reports.py` | It exports `1/probability` as fair odds even for push/half markets. Example FW=.4, push=.3, FL=.3 has fair odds 1.75, not 2.50. This is a derived-report error; the current engine uses the correct payout formula. The pre-existing report script was not modified or included in this PR. |
| Parlay partial score visibility | `scripts/fc-settle-live.py:settle_manual_parlays` | No leg is written until all legs have final results. A single unmatched/future leg therefore leaves the entire slip's scores blank. This is an implementation limitation, not evidence every score is unavailable. |
| Market period integrity | `scores_alt.py:_fetch_thesportsdb` | Adapter accepts AET/PEN statuses without retaining the 90-minute score period. Potential wrong-period settlement for ordinary match markets; occurrence in this snapshot is unknown. |

Quote freshness: `get_match` performs an HTTP fetch without a client response cache;
the scan verifies ID, kickoff and both teams, then rejects decisions more than
300 seconds after capture or after kickoff. However, receipt time is not provider
price-generation time. **203/203 historical rows lack quote timestamps and formula
versions**, so stale historical odds and attribution to `fc-coherent-dc-v1` cannot
be confirmed or ruled out. No claim is made that these 203 rows came from v1.

**51/203 placed-at timestamps lack timezone offsets.** Some look post-kickoff if
interpreted as UTC, but that interpretation is not established. No confirmed
post-kickoff count can be inferred from them. This corrects the preliminary
observation made during exploration.

Quarter lines: **114 AH/O/U picks use whole/half lines; 0 use quarter lines** in
this snapshot. The current extraction and pricing loops preserve integer quarter
units and enumerate complete offered pairs. `catalog.select_markets` deliberately
chooses the most price-balanced display line, while value ranking uses
`conservative_ev`. It is not rounding quarters to halves. Provider raw offers for
these historical picks are missing, so absence at the source vs selection cannot
be resolved. No P2 implementation is included.

## Provisional calibration — not independently verified

For current engine semantics, `probability = P(full win OR half win)`.
Reliability therefore scores the event **positive payout**: full/half wins are 1;
pushes, half losses and full losses are 0. Excluding pushes from Brier/log loss
would condition the outcome while leaving the forecast unconditional. Legacy
probability semantics are unproven, so these metrics remain provisional.

| Probability bucket | n | Mean predicted | Realized positive payout | Gap realized − predicted |
|---|---:|---:|---:|---:|
| [30%,40%) | 1 | 32.21% | 0.00% | −32.21 pp |
| [40%,50%) | 5 | 45.51% | 0.00% | −45.51 pp |
| [50%,60%) | 11 | 54.09% | 72.73% | +18.63 pp |
| [60%,70%) | 1 | 64.77% | 0.00% | −64.77 pp |

18 rows: **8 wins / 8 losses / 2 pushes**, decided win rate **50.00%**,
positive-payout frequency **44.44%**, profit **−0.757 units**, ROI **−4.2056%**,
**Brier 0.226241**, **log loss 0.645262**, ECE **0.294156**.
The JSON also gives per-market metrics. Empty cohorts use null metrics. Log loss
clips endpoint probabilities to [1e−15, 1−1e−15].

The 18 selected rows cannot substantiate the stated 70–80% manually confirmed loss
rate. The 185 unresolved rows, shared-fixture dependence, unverified result matches,
and tiny buckets prevent a population-level calibration verdict. Do not retrain a
calibrator on these figures or interpret ECE from these small buckets as stable.

## Recommendation and phase boundary

There are proven pipeline bugs, including a reproducible wrong-fixture match and
a historical-label crash. Systematic model overconfidence remains **unresolved**;
the largest available bucket actually wins more often than its average forecast.
The engine's payout-aware EV/fair-price formula has not failed the audited synthetic
checks, while the CSV report's fair-price formula is demonstrably inappropriate
for Asian payouts.

Before P0 acceptance: supply the missing brief and authoritative manual outcomes
with pick/fixture identity, score, date, 90-minute period and evidence source;
obtain a read-only export of the actual production ledger with model/quote lineage.
Re-run reliability on verified outcomes and report its sample coverage separately.
Only after explicit human confirmation may P1 fix matching, re-settle in staging,
and measure the <10% overdue target. P2/P3 and production settlement remain out of
scope. This PR must not be merged as a production settlement fix.
