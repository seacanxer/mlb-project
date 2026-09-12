# FC Phase 1C — Offline smoke and checkpoint runbook

## Scope

Phase 1 is complete for the local foundation: baseline, isolated cross-language contracts, persistence interfaces, shared synthetic fixtures, disabled configuration, and deterministic offline smoke with a verified checkpoint protocol. No live route, scheduler, database, or model pipeline is activated. This does not complete training/backtest resume machinery or production atomic snapshot publication; those belong to later phases.

## Default-off configuration

[Engine configuration](E:/MLB-Project/betting-machine-fc/football_formula_engine/config.json) is separate from the legacy FC config. The only supported mode is `offline_smoke`. `engine_enabled`, `official_enabled`, and `staking_enabled` must be literal false; true, zero, null, or the string "false" are rejected. Storage remains explicitly `unconfigured` pending deployment evidence.

The command never executes bookmaker calls, training, staking, pick publication, or settlement. No environment variable can silently enable those features. The Python executable is chosen by the operator's command, not by a network request. Local tests used Python 3.13.14; deployment runtime compatibility must be checked before integration.

## Run the smoke check

Working directory: `E:/MLB-Project/betting-machine-fc`.

```powershell
python -m football_formula_engine
```

Exit 0 means disabled config and the synthetic projection contract validated. Output explicitly includes `model_fitted=false` and `official_enabled=false`. Exit 1 returns a JSON error. Invalid command-line usage exits through argparse. The default command writes only stdout, not source snapshots or databases.

For a persistent checkpoint, choose a NEW file in an existing writable directory:

```powershell
python -m football_formula_engine --checkpoint E:/MLB-Project/docs/fc-phase1-smoke.local.json
python -m football_formula_engine --checkpoint E:/MLB-Project/docs/fc-phase1-smoke.local.json --resume
```

The example file is not created by this documentation. Automated tests exercise this roundtrip in temporary directories. Reusing an existing path without --resume fails rather than overwriting it. After changing input/config/implementation, use a new checkpoint filename; do not force the old run to match.

## Checkpoint semantics and failure handling

- Completion records contain deterministic SHA-256 fingerprints of input, configuration, and ordered implementation bytes, plus schema and completed validation units. Hashes are computed from files, unlike the synthetic data_hash in the fixture.
- --resume reruns the offline checks and compares the complete record. It verifies compatibility; it does not skip computation, continue model training, or claim a model was fitted.
- Publication writes/fsyncs a unique temporary file, then atomically creates the requested checkpoint using a same-filesystem hard link. Existing targets are never overwritten. The temporary file is removed on ordinary success/failure.
- Filesystems without hard-link support fail closed. A process kill before publication may leave an orphan temporary file, but not a valid checkpoint. There is no automatic sweeping/deletion of other files.
- Corrupt/partial/mismatched checkpoints are errors. An orphan temporary file is never consulted during resume. --resume without a checkpoint path is invalid.
- This is not a production crash-durability guarantee: filesystem directory persistence, multiwriter locking, reader run pinning, DB transactions, and deployment crash tests remain future implementation work.
- Scope of fingerprint: the smoke implementation, Python contracts, TS contracts, fixture and config. It is not an environment/dependency lock or full training artifact provenance manifest.

## Dataset and evaluation preregistration for the next phases

These are decisions before tuning, not completed evaluations:

1. Inventory all available league/season files, team mappings, score status, source columns, and odds timestamps. Preserve raw input and hashes. Do not import/fetch or impute missing prices merely to fill a target dataset.
2. Initial dataset target: one league with at least three consecutive seasons if available, followed by additional leagues. The baseline inventory shows many 2025/26 files and an earlier England season; it does not establish three-season coverage or historical BTTS quotes. Missing coverage must be reported and sourced legitimately before ROI evaluation.
3. Freeze an as-of data manifest and exact chronological train/calibration/policy-validation/test boundaries after inventory and before fitting. Keep all candidates from one fixture in one split. Closing information is reference-only if unavailable at decision time.
4. Compare league-average Poisson, ratio baseline, regularized independent Poisson, DC, identity calibration, and the coherent-calibration challenger. Half-life candidates remain 90/180/365 days per Formula Final; choose on inner periods, not final holdout.
5. Record experiment families, folds, seed, resource/time limits and block-bootstrap design before the full run. Calibrated parameters, number of bootstrap replicates, and block lengths are not inferred from this smoke test; finalize them in the evaluation design using data coverage and development diagnostics, not test ROI.
6. EV_lower quantile 0.10 is a preregistered initial policy, not a proven optimum. Preserve NO BET, one official per fixture, paper flat-unit and no shadow promotion. Registry approval and real quote freshness must be trusted server-side evidence, not caller flags.
7. Report log loss/Brier/reliability, payout-aware net ROI, confidence intervals, drawdown and CLV coverage. Without time-correct entry quotes, ROI/CLV is NOT_EVALUABLE. Segment release remains gated by Formula Final and forward confirmation, never by sample count alone.

## Verification and handoff

From `E:/MLB-Project`:

```powershell
python -m pytest betting-machine-fc/football_formula_engine/tests -q -p no:cacheprovider
npm.cmd run test -- tests/unit
npm.cmd run typecheck
```

Tests cover paired contract vectors, disabled config, deterministic smoke, create/resume, mismatch detection, corrupt/duplicate/nonfinite JSON, no-overwrite, and simulated publish failure. Browser E2E and production build have not been run at this foundation checkpoint; no UI changed. Actual process-kill and deployment persistence tests are not claimed.

Next bounded task: Phase 2A identity/time/as-of data normalization using existing inputs, then 2B/2C quote provenance/persistence. Backend selection remains pending durable-storage/writer verification; pure offline data work can proceed. No migrations, deployment, commit, or push are authorized implicitly by completing Phase 1.
