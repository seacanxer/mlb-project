# FC patch progress

## Current checkpoint

- Phase/subphase: **Phase 6C — verified paper selection, ledger and settlement**.
- Status engineering: **Phase 6 offline scope complete; preceding Phase 1–5 checkpoints retained with their documented evaluation limitations**.
- Status model approval: **not implemented / not validated / not activated**.
- Base: branch `codex/rebuild-patch`, commit `c6563df`.
- Scoped 1B additions: `lib/fc/contracts-v2.ts`, `betting-machine-fc/football_formula_engine/{__init__.py,contracts.py,ports.py,tests/test_contracts.py}`, `tests/fixtures/fc-v2-{contract,cases}.json`, `tests/unit/fc-contracts-v2.test.ts`, `docs/fc-phase1b-contracts.md`; this progress document updated.
- Scoped 1C additions: `betting-machine-fc/football_formula_engine/{config.json,__main__.py,smoke.py,tests/test_smoke.py}` and `docs/fc-phase1c-runbook.md`.
- Scoped Phase 2 additions: `data.py`, `data_cli.py`, `ingestion.py`, `snapshot_store.py`, `requirements.txt`, Phase 2 manifest/tests/documentation; `ports.py` aligned.
- Scoped Phase 3 additions: `baseline.py`, `score_matrix.py`, `markets.py`, `value.py`, `math_cli.py`, mathematical/property tests and Phase 3 documentation.
- Scoped Phase 4 additions: `model.py`, `fit_cli.py`, NumPy/SciPy requirements, frozen candidate/baseline artifacts, registry, fitting/artifact tests and Phase 4 documentation.
- Scoped Phase 5 additions: frozen evaluation spec, coherent calibration, proper metrics, chronological evaluation CLI, moving-block refit checkpoints, prediction/evaluation/uncertainty/validation artifacts, Phase 5 tests and documentation.
- Integration-safe build fix: `lib/fc/store.ts` now enumerates four static legacy artifact paths; no v2 reader activation. A temporary attempted Next config exclusion was removed after proving ineffective.
- Source changes: isolated data, fitting, evaluation, policy and local paper ledger; not wired to live UI/reader. Commit and push requested for the accumulated Phase 1–6 work; no deploy requested.
- Schema: `fc-contract-v2`; model/evaluation artifacts carry hashes. Contract harness fixtures remain explicitly synthetic.
- Completed outputs: [baseline](E:/MLB-Project/docs/fc-phase1a-baseline.md), [schema decisions and limitations](E:/MLB-Project/docs/fc-phase1b-contracts.md), shared test vectors.
- Completed 1C output: [offline command, recovery protocol, dataset/evaluation plan](E:/MLB-Project/docs/fc-phase1c-runbook.md). Smoke prints input/config/implementation fingerprints; actual fitting was added in Phase 4.
- Completed Phase 2 output: [data integrity checkpoint](E:/MLB-Project/docs/fc-phase2-data-integrity.md) and reproducible E0 2025/26 manifest.
- Completed Phase 3 output: [deterministic math checkpoint](E:/MLB-Project/docs/fc-phase3-deterministic-math.md), four-market projection CLI and payout-aware value functions.
- Completed Phase 4 output: [model fitting checkpoint](E:/MLB-Project/docs/fc-phase4-model-fitting.md), candidate `dixon_coles_regularized-2f1078c1bb97c70b` and baseline `ratio_baseline-a69a6bc3897beb28`.
- Completed Phase 5 output: [evaluation checkpoint](E:/MLB-Project/docs/fc-phase5-evaluation.md), evaluation `evaluation-61c14ceaa9f16466`, uncertainty `uncertainty-218e8b1a6786cbee`, validation `validation-57cebeb53aecbdab`.
- Completed Phase 6 output: [paper policy and ledger](E:/MLB-Project/docs/fc-phase6-paper-policy-ledger.md), `policy.py`, `ledger.py`, `paper_cli.py` and append-only synthetic NO_BET checkpoint. No real bets generated.
- Last completed numerical run: E0 chronological calibration/policy/untouched-test evaluation with 300 untouched-test fixtures and eight resumable bootstrap smoke refits. Overall and every market remain non-official.

## Verification

Run in `E:/MLB-Project`:

```powershell
python -m pytest betting-machine-fc/football_formula_engine/tests -q -p no:cacheprovider
npm.cmd run test -- tests/unit
npm.cmd run typecheck
```

Final Phase 2/3 verification: **161 Python tests pass**, **215 TypeScript unit tests pass**, TypeScript typecheck passes, Python compileall passes, `git diff --check` passes, and the Next.js production build passes. Build reports three pre-existing React hook warnings in AI Picker, FC Schedule and FC Results. The first build attempt exposed an unreadable `.pytest_cache`; static allowlisting in the FC artifact reader removed the dynamic directory trace and the final build passed without deleting the cache. Browser E2E was not run because the existing assertions target the previous `/fc` page contract. No model accuracy or ROI improvement is claimed.

Final Phase 4 verification: **174 Python tests pass**, the frozen E0 fit reproduces the same candidate and baseline IDs with append-only `deduplicated` publication, **215 TypeScript unit tests pass**, TypeScript typecheck and Python compileall pass, `git diff --check` has no errors, and the Next.js production build passes with the same three pre-existing hook warnings. No model accuracy, calibration, win-rate, or ROI improvement is claimed before Phase 5.

Final Phase 5 verification: **185 Python tests pass**, **215 TypeScript unit tests pass**, TypeScript typecheck, Python compileall and `git diff --check` pass, and the Next.js production build passes with the same three pre-existing hook warnings. Evaluation/model/calibration/prediction artifacts reproduce as `deduplicated`; eight bootstrap checkpoints resume without refitting and uncertainty/validation artifacts deduplicate. Quality remains `not_approved`, not hidden by the engineering pass.

## Outstanding constraints

- Phase 6 verification: 203 Python tests and 215 TypeScript tests pass; typecheck and compileall pass. Transaction rollback, abrupt process exit, concurrent duplicate writes, restart, result corrections, all payout categories and null empty ROI verified. Production persistence remains undecided.

- Today's Pick still redirects to Schedule; scanner is fixture-only; the fitted candidate is unvalidated and inactive; there is no v2 picks.json.
- Deployment durable storage, writer concurrency, scheduler and Python command remain unverified. Do not choose production persistence by assumption.
- E0 2025/26 contains no timed historical quote snapshots and no BTTS odds; all four market ROI statuses remain NOT_EVALUABLE for this manifest.
- E2E assertions reflect a previous Today's Pick page; source mismatch recorded, tests not executed.
- Preserve pre-existing untracked `.claude/` and the two planning/research documents.

## Resume

Next bounded task: **Phase 7 — API/UI integration behind disabled flags**, following [plan](E:/MLB-Project/docs/fc-patch-phase-plan-v2.md). The Phase 5 registry has no approved segment; policy returns NO_BET. Production adapter must verify evidence provenance before using the internal paper selection/locking interfaces.

Rollback: no live runtime rollback needed; the new modules are not connected to routes. Do not delete existing snapshots or ledger. Synthetic fixtures must never be published as real picks.

## Phase status

| Subphase | State |
|---|---|
| 1A baseline | verified locally |
| 1B schema and harness | verified locally; deployment storage backend remains explicitly unresolved |
| 1C smoke/default-off/checkpoint protocol | verified locally; 25 additional Python tests |
| 2 data integrity/snapshots | verified locally for offline boundary/store; live collector and production storage deliberately inactive |
| 3 deterministic four-market math | verified locally; projection-only |
| 4 fitted model/artifacts | verified locally; candidate remains unvalidated and inactive |
| 5 evaluation/calibration/uncertainty | engineering verified; model quality **not approved** |
| 6 policy, paper ledger, settlement | verified locally; NO_BET with current registry; no runtime activation |
| 7–8 UI and release | not started |
| 9 optional improvements | deferred |

Implemented smoke checkpoint only verifies compatible completed offline checks. Durable training manifests, production snapshot publication, process-kill durability and actual storage backend still require their planned implementation and tests. These are deferred production capabilities, not hidden Phase 1 successes.
