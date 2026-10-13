# FC decision formula v5 — sharp reference (13 October 2026)

## Why v4 was retired

**Live tracker** (`betting-machine-fc/tracker_snapshot.json`, 197 settled single picks, September 2026): -19.4u, ROI -9.8% (-25.4u including six manual 16-leg parlays). Claimed EV ran backwards against results:

| Claimed EV | Picks | Profit |
| --- | ---: | ---: |
| 3–10% | 68 | +10.4u |
| 10–25% | 79 | -13.1u |
| ≥ 25% | 45 | -13.4u (23% hit rate) |

**Walk-forward replay** (`scripts/fc-walkforward-backtest.py`):
- 27,390 Football-Data fixtures from 77 league-seasons, 2022/23–2025/26.
- The production Dixon-Coles fit (H180) is refit every week with only the results available before that week.
- The v4 goal blend (65% market goals, geometric pool), AH payout anchoring, gates and card/value selection are replayed exactly. Card selection calls `catalog.select_markets`, and the vectorised payout code matches the engine to within 1e-8.
- The bet price is Bet365 pre-match. CLV is measured against Pinnacle closing no-vig.

| v4 value picks | Picks | Hit | ROI | 90% CI | CLV |
| --- | ---: | ---: | ---: | --- | ---: |
| 2022–24 (dev) | 5,062 | 46.7% | -8.1% | -10.4 to -5.9 | -4.1% |
| 2024–26 (test) | 4,895 | 47.9% | -6.3% | -8.5 to -3.9 | -4.6% |

No variant of the v4 formula fixed this. Variants tried:
- market weights 0.80, 0.90 and 1.00;
- an 8% EV cap and a 4% EV gate;
- a 7pp disagreement cap;
- 50% anchoring of 1X2 and O/U.

Every market, side, odds band and EV band showed negative CLV. The model also had a strong Under bias: 5,190 Under picks against 954 Over.

### Root cause

On 22,415 fixtures, the result was regressed on the logit of Pinnacle's no-vig probability plus the logit difference between DC and Pinnacle:

| Event | Coefficient on the DC − market difference |
| --- | --- |
| Home win | -0.051 ± 0.029 |
| Away win | -0.064 ± 0.031 |
| Over 2.5 | -0.074 ± 0.028 |

When DC disagrees with the sharp market, outcomes move slightly *away* from DC. Its "EV" is therefore noise, and the biggest claimed edges are the biggest errors.

## v5 rule

- The decision probability is the sharp book's no-vig probability for the identical contract (`sharp_reference.py`).
- AH and O/U split lines keep the goal model's full/half/push shape, with W/(W+L) set to the reference.
- A value pick requires:
  - EV ≥ 2% at the 1xbit price;
  - odds between 1.50 and 5.00;
  - EV ≤ 25% (anything larger is treated as a stale or mismatched quote);
  - a reference quote no older than 15 minutes.
- Without a reference, a contract stays a displayed forecast with `REFERENCE_UNAVAILABLE` and is never a value pick.
- Replay proxy: Bet365 price against Pinnacle pre-match fair.

| v5 value picks | Picks | Hit | Avg odds | ROI | 90% CI | CLV (beat close) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 2022–24 (dev) | 584 | 33.0% | 3.47 | +5.3% | -5.4 to +16.5 | +2.3% (65%) |
| 2024–26 (test) | 304 | 32.0% | 3.44 | +5.5% | -10.9 to +21.1 | +2.0% (68%) |

ROI was positive in each season: +0.3%, +10.2%, +3.8% and +10.3%. CLV was positive in every season and market.

Two caveats:
- The confidence intervals include zero. CLV is the more stable evidence.
- Hit rate is **lower** than v4 because many picks are underdogs. Judge v5 by ROI and CLV, not by hit rate.

Volume is low: about 11 picks per league-season with Bet365 prices. The live volume depends on how often 1xbit's price beats Pinnacle, and must be measured prospectively.

## Operation

1. Set `FC_REFERENCE_ODDS_API_KEY` (The Odds API). `FC_REFERENCE_BOOKMAKER` defaults to `pinnacle` and `FC_REFERENCE_REGIONS` defaults to `eu`.
2. Each scan makes one request per supported league (`reference_odds.SPORT_KEYS`), costing 3 credits per league.
3. Events are attached to a 1xbit fixture only when:
   - both teams resolve, via the scanner's conservative `match_team`, to the same league training names; and
   - the kickoffs agree within 60 seconds.
4. Quotes are recorded in the immutable QuoteJournal under the 1xbit fixture ID.
5. `config.json` → `last_scan_diagnostics.sharp_reference` reports per-league matching and the number of fixtures priced.
6. Rollback: set `FC_DECISION_MODE=model_blend`.

New ledger rows carry `decision_mode`, `reference_probability` and `reference_bookmaker`, and use formula version `fc-sharp-reference-v5`. Grade v5 separately from v4.

## Reproduce

```bash
python scripts/fc-walkforward-backtest.py build --out /tmp/fc_wf.jsonl     # ~35 min, 2 workers
python scripts/fc-walkforward-backtest.py evaluate --records /tmp/fc_wf.jsonl
```

Six league-season jobs fail closed: the strict CSV loader rejects malformed archive cells in E0 2122, N1 2223, SP2 2526 and T1 2425. Those jobs are excluded rather than repaired.

## Limits

- Football-Data prices have no capture timestamps. Bet365 is a proxy for 1xbit, and the replay covers 1X2, O/U 2.5 and the main AH line only (no BTTS or alternate lines).
- Corner and card markets are not changed by this patch.
- Official remains disabled.
