# MLB pick priority dry test — 24 September 2026

Source: `reports/mlb_tracker_snapshot.json`, generated 24 September 2026. It contains 167 settled picks from 26 August through 23 September. The report's historical model versions are not identifiable in this snapshot; the exporter now records the configuration version and quote timestamp for future runs.

## Change under test

- Keep every existing Moneyline and Totals signal, eligibility rule, and automatic lock. Reorder the Daily Slate by a review priority derived from the published tier and selected side.
- T1 is primary. T2 away and Over signals are review. T2 home and Under Lean/Risky are caution. These are ordinal labels, not calibrated probabilities.
- Make the O/U diagnostic probability distribution use the same market-shrunk total as the published projection. This leaves the gap, final state, and number of picks unchanged. Version the output as 4.0.1.

## Retrospective time split

Run `npm run dry:mlb-priority`. The script separates picks before 15 September from picks on or after that date. It asserts that each pick remains in exactly one priority group.

| Period | All picks | Primary T1 | Review | Caution |
| --- | --- | --- | --- | --- |
| 26 Aug–14 Sep | 85, 47W, 55.3%, -2.09u | 38, 24W, 63.2%, +1.12u | 26, 15W, 57.7%, +2.04u | 21, 8W, 38.1%, -5.25u |
| 15–23 Sep | 82, 43W, 52.4%, -4.76u | 22, 15W, 68.2%, +1.49u | 37, 18W, 48.6%, -1.62u | 23, 10W, 43.5%, -4.63u |

The later period is a chronological diagnostic, not a prospective trial. The same report informed the choice of groups; no performance guarantee follows from it. The ranking preserves all 167 historical selections and does not change the production pick gate.

## Rejected formula shortcut

Simply reversing the Moneyline market-alignment points was checked against the selected-pick ledger. It would move 9 historical T2 picks into T1, with only 3 wins among those 9, and drop 2 T2 picks below the minimum score. It was not enabled. The ledger lacks all unselected candidates, so it cannot validate a replacement scoring formula or its effect on daily volume.

## Next dry test

After each settled slate, regenerate the snapshot, rerun the command, and compare newly locked picks by configuration version and priority. Record pick count per day, win/loss/push, flat-unit ROI, odds age at the model input, and score/line. Evaluate the final regular-season days separately from postseason games. Reconsider the ranking only after genuinely new outcomes are available.
