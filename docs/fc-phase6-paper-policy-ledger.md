# Phase 6 — paper selection, immutable ledger, settlement

Phase 6 implements the isolated offline policy and paper accounting path. No segment in the current Phase 5 registry is approved, so the checkpoint produces NO_BET, zero locks and null ROI. This is expected, not a provider failure or a zero-return backtest.

## Selection

`policy.select_candidates` evaluates supplied contracts across all four markets and all supplied sides/lines. It reprices each bootstrap payout distribution at the entry odds, computes q10 net return, checks exact snapshot and league/market/line evidence binding, and ranks positive lower-EV candidates. One candidate per fixture is allowed; ties use newest quote, contract ID and quote ID. There is no pick quota and `is_top_pick` always remains false in this paper phase.

Stale/missing quotes, reference-only closing quotes, data diagnostics, unapproved model segments and missing uncertainty block selection. Missing uncertainty remains null. Evidence is an internal trusted adapter input; arbitrary JSON claiming approval is not a production authorization mechanism. Phase 5 provides no acceptable evidence today. A future production adapter must authenticate provenance and registry scope before supplying this input.

`payout_samples` are five-category payout vectors, not binary probabilities. The 30-sample floor is only a necessary engineering requirement in addition to the adapter's explicit uncertainty status; it is not proof of statistical reliability. Phase 6 supports a zero-commission sportsbook contract. Other fee models need an explicit versioned contract before use.

## Ledger and revisions

`ledger.PaperLedger` uses a separate local SQLite database and only paper tables. It stores the complete immutable selected snapshot and flat one-unit stake semantics. A unique fixture constraint prevents repeated generation from choosing another contract or price for an already locked game. Identical retries deduplicate; conflicting locks fail.

Settlement reuses Phase 3 payout math. Final results require source, fixture, integer scores and observation time. Void requires an explicit reason. Pending results are not settleable. Each correction appends a revision and uses compare-and-swap against the expected current revision; older events cannot roll back newer results. Tracker uses only the latest revision per lock and separately counts the complete audit trail.

Tracker ROI is net profit divided by all settled one-unit stakes, including push and void; pending stakes are excluded. No settled paper bets yields null ROI. Formula/calibration/policy cohorts are reported separately; legacy bets are not imported or combined.

SQLite is the offline/replay backend only. Production shared storage, scheduler and UI wiring remain later-phase work.

## Verification and checkpoint

The Phase 6 tests cover all payout outcomes, exact Asian half outcomes, missing uncertainty, stale/mismatched evidence, deterministic fixture selection, restart, concurrent lock/settlement retries, conflicting corrections, void denominator, transactional rollback and abrupt process exit before commit.

Run from the repository root:

```powershell
$env:PYTHONPATH='betting-machine-fc'
python -m football_formula_engine.paper_cli --artifact-root betting-machine-fc/football_formula_engine/artifacts
python -m pytest betting-machine-fc/football_formula_engine/tests -q -p no:cacheprovider
```

The CLI publishes `artifacts/phase6/paper-checkpoint-v1.json` through the append-only store. It explicitly labels its input synthetic and creates no real picks. Replay must deduplicate without changing content.

Phase 7 is API/UI integration behind disabled feature flags. Model approval still requires further evaluation and prospective quote evidence; implementing the ledger does not change that gate.
