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

## v5.3 — every fixture and every market gets a projection with a confidence tier

v5.0–v5.2 linked card display to value: a market was shown only with EV > 0. Against Pinnacle that rarely happens, so cards lost most markets, and German fixtures without a value pick showed nothing. v5.3 decouples the two.

- **Card projection, every market.** For 1X2, AH, O/U and BTTS the card shows the value candidate if one exists. Otherwise it shows the most likely side on the balanced main line. Nothing is eliminated for lacking value.
- **Confidence.** Confidence is the best-calibrated win probability: Pinnacle no-vig when matched, otherwise 1xbit no-vig. The DC probability stays in `raw_probability`, because the replay found it overconfident.
- **Tiers.** Tier hit rates are historical. The pick is the most likely side at the Pinnacle no-vig price, over 63,000 market-sides:

| Tier | Confidence | Hit rate | ROI (no edge) |
| --- | --- | ---: | ---: |
| TINGGI | ≥ 65% | 74.1% | ≈ -0.4% |
| SEDANG | 55–65% | 60.1% | ≈ -1.9% |
| RENDAH | 45–55% | 51.9% | ≈ -3.1% |
| SPEKULATIF | < 45% | 40.5% | ≈ -3.0% |

- **High tier ≠ profit.** A high tier means a high win rate, not a profit edge. Only `Kandidat value` (EV ≥ 2% against Pinnacle) carries price edge.
- **Market-only lane.** It covers fixtures with no goal model and no sharp market: lower leagues, youth, women, cups, Africa/Asia. It also covers domestic fixtures whose model fails and whose league has no sharp market, such as Regionalliga Bayern with an unmatched team. Score shape and confidence come from 1xbit's own no-vig prices. Every row carries `MARKET_ONLY_NO_REFERENCE` and can never be a value pick. Labels: `decision_mode=market_only`, `formula_version=fc-market-only-v1`, `model_status=MARKET_IMPLIED_NO_EDGE`. The flashscore cross-check is skipped for this lane to keep the scan light.
- **Duplicate fixtures** (same teams and kickoff under different 1xbit IDs) are scanned once and counted in `coverage.duplicates`.
- **Card visibility.** 1X2 projections below 1.30 are no longer hidden. Their tier states the confidence.
- **New sharp competitions.** Copa Sudamericana and Copa Libertadores are added to the sharp reference list.

## v5.4 — confidence source shown on the card

When Pinnacle is missing, a fixture that has a domestic goal model now shows the model's view: the DC goal model pooled 35/65 with market goals, the same blend as v4. The card's pick per market is the model's most likely side. Market-only fixtures still use 1xbit no-vig. Each market cell shows:

- confidence % and tier;
- the source label (`Pinnacle (sharp)`, `Model DC + pasar`, `Model tim nasional + pasar` or `Harga pasar 1xbit`) with that source's historical tier hit rate;
- the 1xbit no-vig view for comparison, plus the model view when the source is Pinnacle.

Tier hit rates by source, from the walk-forward replay:

| Tier | Pinnacle | Model DC + pasar | 1xbit/market no-vig |
| --- | ---: | ---: | ---: |
| TINGGI ≥ 65% | 74.1% | 69.2% | 74.3% |
| SEDANG 55–65% | 60.1% | 57.2% | 59.9% |
| RENDAH 45–55% | 51.9% | 50.9% | 51.4% |
| SPEKULATIF < 45% | 40.5% | 40.2% | 40.5% |

Raw DC alone is not used as confidence. Its TINGGI tier claimed 72.6% and won 60.6%.

The national-team model has no measured hit rate, so the card shows its label without a history figure. Value picks still require Pinnacle.

## v5.5 — compact storage and big-league priority (18 October 2026)

### Storage

| File | Problem | Fix |
| --- | --- | --- |
| `matches_detailed.json` | Reached 83–400 MB. The cause was 900+ minor-league market-only fixtures, about 50 alternate lines per fixture in `market_options`, full quant blocks on every projection, and pretty-printed JSON. | Minor leagues without a model are no longer stored. `market_options` keeps all 1X2/BTTS sides, both sides of the AH/O-U main line, and value rows. Non-value projections carry a quant stub. JSON is written compact. Today's scan replayed under the new rules: 83.2 MB → 4.2 MB. |
| `live_quotes.db` | Each scan stored the full 1xbit event response per fixture. | The journal stores the identity fields plus a SHA-256 digest and byte count. `scripts/fc-prune-data.py` (dry run by default; `--apply --days 21`) rebuilds the append-only journal, keeping recent and research-referenced observations. Immutability triggers are kept, and the old file is saved as a backup. The same script trims `odds_quotes.jsonl`. |
| Ledgers | `projection_ledger.jsonl` and `projection_grades.jsonl` were re-parsed on every request. | They are now cached on (mtime, size), like the scan artifact. |
| Git | Scan outputs were committed on every refresh. | `matches_detailed.json`, `picks.json` and `odds_quotes.jsonl` are gitignored and untracked. The next `git pull` on the VPS removes the tracked copies, so run a scan right after deploying. |

### Pick priority

`league_tiers.py` assigns each competition a tier:
- **Tier 1:** big five and UEFA club competitions.
- **Tier 2:** other major top flights, big-five second divisions, Libertadores/Sudamericana/AFC Champions League Elite and senior national teams.
- **Tier 3:** everything else.

Rules:
- Tier 3 without a model is not analysed. Tier 3 with a domestic model is display-only (`LEAGUE_TIER_DISPLAY_ONLY`).
- Pinnacle reference credits are spent on tiers 1–2 only.
- One value pick per fixture. Picks are ranked by tier, then high-win, then EV, with at most 12 per scan.
- Corner/card display rows stay on the match card and no longer fill `picks.json`.
- The UI's Top Picks require tier 1–2, and the board sorts big leagues first.

Replay of this combo (v5 sharp rule, tier 1–2, one pick per fixture):

| Price used | Cohort | Dev 2022–24 | Test 2024–26 |
| --- | --- | --- | --- |
| Bet365 | all value | 332 picks, ROI +5.4%, CLV +2.2% | 178 picks, ROI +14.5%, CLV +1.8% |
| Best market price | all value | 2,217 picks, ROI +5.5%, CLV +3.1% | 1,093 picks, ROI +2.0%, CLV +2.8% |
| Best market price | high-win only | 54 picks, 71% hit, ROI +22%, CLV +3.6% | 26 picks, 72% hit, ROI +22%, CLV +3.8% |

### Production finding

The scan of 18 Oct reported `sharp_reference.status = NOT_CONFIGURED`: the scanning process had no Odds API key. Without it the engine can only make market-only projections, never value. The scanner now also reads `FC_*` keys from the repo's `.env.local`/`.env` when the process environment lacks them.

## v5.6 — tie-break study and alternative lines (18 October 2026)

**Question.** Can extra statistics turn a 50/50 market into a pick?

**Test.** A walk-forward logistic model: market no-vig logit as offset, plus team features rolled over the last six matches before kickoff. Fit on 2022–24, tested on 2024–26, on coin-flip markets only (Pinnacle no-vig 45–55%). Features:
- shots on target for/against;
- goals for/against;
- rest days;
- Pinnacle-vs-Bet365 divergence.

**Result.** Log loss improved by at most 0.0007. On the same fixtures:

| Market | Market-side hit | Stats-side hit | When stats flip the side, stats right |
| --- | ---: | ---: | ---: |
| O/U 2.5 dev / test | 52.4% / 52.4% | 52.6% / 52.3% | 51.7% / 49.4% |
| AH main dev / test | 53.0% / 51.1% | 53.6% / 51.7% | 52.4% / 53.0% |

These statistics do not break ties, so they are not used.

**Alternative line.** When the balanced AH or O/U line is below 55%, the card shows an offered alternative line with a clear direction instead: confidence ≥ 60% and odds ≥ 1.40, choosing the highest odds that qualify. Example: Lazio +1.5 instead of a 54% Lazio +1. It is marked `display_status=alt_line` with `main_line_confidence`, and labelled "Line alternatif" on the card.

Limits:
- Tier hit rates were measured on 1X2 and main lines. Alternative lines rely on the same no-vig calibration but have no separate history yet.
- Without a price edge, ROI stays about minus margin.
- 1X2 and BTTS have no alternative lines. When they are coin flips they remain "Seimbang", and the AH alternative is the decision.
