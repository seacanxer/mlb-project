# FC corners and cards walk-forward report

Date: 2026-09-30
Model: `fc-secondary-counts-v1`
Method: chronological walk-forward by league CSV; each fixture uses only earlier match statistics. Binary outcome is positive settlement (a push is not counted as a win). Brier score is lower-is-better. Baseline is the smoothed historical league hit rate for the same market line and side, computed using only earlier fixtures.

## Results

| League CSV | Market | N | Model Brier | Baseline Brier | Difference | Model log loss | Calibration gap | Observed positive | Mean predicted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| E0_2526 | Total corners | 300 | 0.2478 | 0.2439 | -0.0039 | 0.6887 | -3.3 pp | 50.7% | 54.0% |
| E0_2526 | Corner HDP | 300 | 0.2480 | 0.2584 | +0.0104 | 0.6891 | +2.0 pp | 52.7% | 50.7% |
| E0_2526 | Total cards | 300 | 0.2400 | 0.2388 | -0.0012 | 0.6729 | +0.2 pp | 57.0% | 56.8% |
| E0_2526 | Team cards | 300 | 0.2316 | 0.2299 | -0.0016 | 0.6549 | -3.4 pp | 61.3% | 64.7% |
| SP1_2526 | Total corners | 293 | 0.2454 | 0.2392 | -0.0062 | 0.6839 | +1.3 pp | 55.6% | 54.4% |
| SP1_2526 | Corner HDP | 293 | 0.2479 | 0.2471 | -0.0008 | 0.6889 | +3.4 pp | 54.3% | 50.9% |
| SP1_2526 | Total cards | 293 | 0.2445 | 0.2425 | -0.0020 | 0.6821 | +1.0 pp | 57.0% | 56.0% |
| SP1_2526 | Team cards | 293 | 0.2238 | 0.2208 | -0.0030 | 0.6397 | +1.5 pp | 65.2% | 63.6% |
| D1_2526 | Total corners | 230 | 0.2437 | 0.2423 | -0.0014 | 0.6805 | +4.5 pp | 58.7% | 54.2% |
| D1_2526 | Corner HDP | 230 | 0.2494 | 0.2612 | +0.0119 | 0.6919 | +3.4 pp | 54.3% | 51.0% |
| D1_2526 | Total cards | 230 | 0.2515 | 0.2568 | +0.0053 | 0.6962 | -5.5 pp | 51.3% | 56.8% |
| D1_2526 | Team cards | 230 | 0.2176 | 0.2189 | +0.0013 | 0.6268 | +4.4 pp | 67.4% | 63.0% |
| I1_2526 | Total corners | 298 | 0.2473 | 0.2430 | -0.0043 | 0.6876 | +0.7 pp | 54.7% | 54.0% |
| I1_2526 | Corner HDP | 298 | 0.2491 | 0.2496 | +0.0005 | 0.6913 | +6.2 pp | 57.0% | 50.8% |
| I1_2526 | Total cards | 298 | 0.2428 | 0.2505 | +0.0077 | 0.6786 | -1.3 pp | 55.7% | 57.0% |
| I1_2526 | Team cards | 298 | 0.2377 | 0.2396 | +0.0019 | 0.6694 | -0.8 pp | 62.8% | 63.6% |
| F1_2526 | Total corners | 232 | 0.2500 | 0.2470 | -0.0030 | 0.6932 | -2.9 pp | 51.3% | 54.2% |
| F1_2526 | Corner HDP | 232 | 0.2470 | 0.2624 | +0.0153 | 0.6872 | +5.3 pp | 56.0% | 50.8% |
| F1_2526 | Total cards | 232 | 0.2410 | 0.2369 | -0.0041 | 0.6750 | -1.2 pp | 56.5% | 57.6% |
| F1_2526 | Team cards | 232 | 0.2498 | 0.2490 | -0.0008 | 0.6932 | -5.7 pp | 56.5% | 62.2% |

The handicap sign bug found during the first backtest caused probabilities near 100% for an ordinary small corner advantage. It is fixed and covered by a regression test. Corrected corner-HDP probabilities are now near 50%; its Brier score beats the simple baseline in four leagues and is effectively tied in Spain.

The remaining results do not support calling these forecasts validated picks. Several totals markets underperform the league-rate baseline, despite small absolute Brier differences. These outputs are marked `Proyeksi` and are not presented as value picks. No historical corner/card bookmaker quote feed was found in the existing scraper, so odds, edge, ROI, settlement, and pick locking are unavailable for these markets. The card currently exposes only state B projections; state A will require a verified quote source and sufficient coverage.

The walk-forward skipped 80 (E0), 87 (SP1), 76 (D1), 82 (I1), and 74 (F1) early fixtures before enough prior data was available. These are not failures or fabricated fallbacks; they are state C/unavailable. Coverage outside these five leagues was not included in this report.

The selected 2025–26 CSVs have complete corner, yellow-card, and red-card counts for all rows: E0 380/380, SP1 380/380, D1 306/306, I1 380/380, and F1 306/306. Referee names are present in E0 (380/380) and absent in the other four current-season files (0/380, 0/306, 0/380, 0/306). In those leagues the model widens card uncertainty rather than inventing referee data.

## Verification

- `python -m pytest tests/unit -q`: 30 passed.
- `npm test -- --run`: 233 passed across 21 files.
- `npm run typecheck`: passed.
- `python scripts/fc-secondary-backtest.py` was run separately against each of the five league CSVs above.
- ROI deliberately remains null because no secondary-market odds history is available.
