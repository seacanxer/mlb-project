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

## v5.1 — high-win tier, line movement, lighter scan

### High-win tier

A value pick whose sharp no-vig probability is at least 55% gets the tier `value_tier=high_win`. It is ranked first and shown as HIGH-WIN in the pick table. The rule itself is unchanged: price beats sharp fair by ≥ 2%. The odds floor is lowered to 1.30 so favourites can qualify.

| Price used in the replay | Tier | Dev | Test |
| --- | --- | --- | --- |
| Best market price (Max) vs Pinnacle | high_win | 128 picks, 70.6% hit, +21.5% ROI, CLV +3.0% | 57 picks, 69.1% hit, +21.2% ROI, CLV +2.8% |
| Best market price (Max) vs Pinnacle | value | 3,055 picks, 35.3% hit, +4.5% ROI | 1,489 picks, 31.9% hit, +1.2% ROI |
| Bet365 vs Pinnacle | high_win | 10 picks, 80% hit | 13 picks, 64% hit |

High win rate is real only together with a price edge. Simply backing favourites gives roughly zero ROI:
- Pinnacle fair ≥ 70%: 80.6% hit, ROI +1.1% (dev) and +0.6% (test).
- Pinnacle fair ≥ 60%: 72–73% hit, ROI +0.3% (dev) and -1.9% (test).

A single soft book rarely beats Pinnacle on favourites, so this tier will be uncommon.

### Line movement (Pinnacle open → close, 115,837 side-rows)

- Betting a favourite **after** it steamed, at the closing price, lost: -0.5% to -7.7% ROI.
- The same picks taken at the **opening** price earned +3.3% to +6.0%. This is closing-line value: the profit belongs to whoever bets before the move, not after.
- The sharp current price already contains the move. v5 captures it by pricing against Pinnacle now.
- Movement is logged as `reference_open_probability` and `reference_move` on every pick for prospective study. It does not gate picks.

### Lighter scan

- The flashscore fixture feed is downloaded once per 5 minutes instead of once per fixture.
- The sharp reference is re-fetched per league once it is 10 minutes old, so long scans do not lose it.

Repository weight: `betting-machine-fc/matches_detailed.json` (18 MB), `picks.json` and `config.json` are scanner outputs. Because they are tracked, every scan dirties the tree that `deploy.sh` refuses to deploy. Untracking them is recommended, but the next `git pull` on the VPS will delete the live copies until the following scan, so plan a scan right after the deploy. `football_formula_engine/artifacts/` (15 MB, 177 files) is Phase 4/5 research output and is not used by the scanner.

## v5.2 — coverage fix (incident 13 October 2026)

Production had 440 fixtures, but 409 stopped at `LEAGUE_MODEL_UNAVAILABLE`. That included all 9 real UEFA Champions League fixtures, which never reached v5 pricing.

| Fix | Behaviour |
| --- | --- |
| Artifact filter | 1xbit "Team vs Player" leagues are dropped at ingestion and counted as `coverage.artifact_rows`. |
| Reference-only lane | Competitions without a goal model but with a sharp market are priced only against Pinnacle. This covers UCL, UEL, UECL and other top leagues listed in `reference_odds.REFERENCE_ONLY_COMPETITIONS`. Score shape comes from the sharp book's implied goals, which is the same construction as the replayed v5 policy. Rows are labelled `decision_mode=reference_only`, `formula_version=fc-reference-only-v1`, `model_status=UNVALIDATED_REFERENCE_ONLY`, `pick_class=reference_only`, and stay non-official. |
| Domestic fallback | When a domestic model cannot project a fixture (model unavailable, team coverage missing, projection blocked), the fixture falls back to the reference-only lane if its league has a sharp market. |
| Pairing | Pairing is kickoff-scoped: kickoff within ±60 s, both teams must score ≥ 0.80, and the best candidate must lead the next by ≥ 0.15. Home/away are never swapped, and an event claimed by two fixtures is dropped. A reviewed alias map covers provider variants such as Inter/Internazionale, RB Leipzig, Sporting, PSV and Bayern. This replaces training-name-only matching, which matched only 1/5, 0/8 and 0/1 fixtures in three domestic leagues. |
| Visible status | Reference-only fixtures without an edge show `REFERENCE_NO_EDGE`; fixtures without a sharp quote show `REFERENCE_UNAVAILABLE`. |
| Output classes | `/api/fc/picks` summary adds `value_v5_count`, `reference_only_count` and `secondary_display_count`. Secondary corner/card rows are tagged `secondary_display`. |
| Odds floor | The API floor is now 1.30, matching v5, so high-win favourites are no longer hidden. |
| League name | The 1xbit label `Turkey. SuperLiga` now maps to T1. |

Diagnostics are in `config.json` under `last_scan_diagnostics.coverage` and `last_scan_diagnostics.sharp_reference.leagues`, keyed by sport key. The latter includes matched/unmatched fixture names.

Still open (P1): a validated UCL club-strength model with its own time-split backtest. Until then, UCL picks remain reference-only.
