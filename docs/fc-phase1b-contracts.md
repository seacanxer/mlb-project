# FC Phase 1B — Boundary contracts and isolated harness

## Implementation decision

Schema ID: `fc-contract-v2`. The new Python package and TypeScript validator are isolated from all live routes. They validate input/output shape and cross-field consistency only; they do not fit a model, price a contract, verify a bookmaker quote, approve a segment, or generate a pick.

Authoritative executable boundaries:

- [TypeScript/Zod](E:/MLB-Project/lib/fc/contracts-v2.ts).
- [Python/stdlib](E:/MLB-Project/betting-machine-fc/football_formula_engine/contracts.py).
- [Shared synthetic fixture](E:/MLB-Project/tests/fixtures/fc-v2-contract.json) and [accept/reject vectors](E:/MLB-Project/tests/fixtures/fc-v2-cases.json).

Both implementations must pass the same vectors before changing this version. Fixture values are synthetic: the score probabilities, EV, hash and quote do not represent any model forecast or executable bet. Existing legacy FcPick types remain unchanged.

## Frozen boundary decisions

| Record | Contract |
|---|---|
| Fixture | Stable fixture/competition/team IDs, season, kickoff in UTC epoch seconds; distinct teams |
| Market contract | Stable ID; fixture reference; 1x2/ou/ah/btts; selected side; regulation period only |
| Asian/total line | Integer quarter-units: home -0.75 = -3, total 2.25 = 9; AH signed from selected team's perspective |
| Binary line | Null for 1X2/BTTS; totals nonnegative; unsupported side/period rejected |
| Quote | Immutable ID, contract reference, provider/bookmaker, available/captured timestamps, decimal odds >1, freshness and closing flags |
| Prediction | ID, formula/calibration version, SHA-256-shaped data hash, cutoff, five payout probabilities summing to one, finite net/lower EV |
| Uncertainty | Unavailable means ev_lower=null, not zero; available requires finite ev_lower |
| Decision | Projection/paper/official candidate/official locked/blocked; policy version, top flag, reason codes |
| Capabilities | Schedule, prediction, model validation, official enablement kept separate |
| Diagnostics | Typed missing/corrupt/invalid/stale/unavailable with message |

Objects reject unknown fields, numeric strings, booleans as numbers, nonfinite numbers, and noncanonical identifiers. UTC seconds are integral, bounded to year 2100 to catch accidental milliseconds. Cutoff/capture may not exceed the recorded decision time; quote availability may not exceed capture. This schema bounds timestamps; actual historical point-in-time provenance remains Phase 2 work.

Paper candidates require prediction, fresh quote, pre-kickoff decision, and positive available EV_lower. Official decisions additionally require approved model status and enabled official capability; top cannot be projection/watch/paper. The boundary checks declared evidence, not its authenticity. Real publishing must consult the trusted registry and runtime config, not trust caller-provided booleans. `official_locked` here describes an origin decision; it does not implement or prove a ledger lock, and decision_at remains the original decision time after kickoff.

Hash format validation is not hash verification. EV/payout consistency with price/fees will be enforced by the shared pricing implementation in Phase 3; no pricing formula is duplicated here. Missing quote or prediction is allowed for projection-only input and never becomes an official candidate. Schedule availability is independent of prediction availability.

## Runtime and persistence decisions

Python production code uses stdlib only at this checkpoint; pytest is an existing test prerequisite. TypeScript uses the existing direct zod dependency. No dependency install or version upgrade performed. Development validation uses `python -m pytest` with the inspected local Python 3.13.14; this does not prove Python 3.11 compatibility in CI yet.

Package location: `betting-machine-fc/football_formula_engine/`. [Persistence ports](E:/MLB-Project/betting-machine-fc/football_formula_engine/ports.py) define immutable snapshots, complete-run publication, and idempotent settlement revision boundaries. No implementation or active database migration exists. Durable deployment disk/writer concurrency are not verified, so the production storage backend remains an explicit release dependency, not an assumed SQLite choice. No changes to Prisma/MLB storage.

Live `python3` subprocess selection is unchanged. Phase 1C should introduce a deterministic offline validator/smoke command and explicitly disabled engine configuration; production executable selection must be deployment-configured and validated before wiring the scan route. Do not run arbitrary executable names from request payloads.

## Verification and limits

Run from `E:/MLB-Project`:

```powershell
python -m pytest betting-machine-fc/football_formula_engine/tests -q -p no:cacheprovider
npm.cmd run test -- tests/unit
npm.cmd run typecheck
```

The paired tests cover four markets, references, time leakage, invalid line units, payout mass, capability consistency, and official gates. Tests do not demonstrate model accuracy, immutable storage, atomic writes, complete-run recovery, UI integration, or performance/ROI. Those mechanisms remain in later subphases.

## Resume and rollback

Next: 1C offline smoke/default-off configuration and checkpoint protocol. Continue using the same fixture and reject any attempt to label its synthetic predictions as real. No live reader imports the new modules; rollback does not require a database or UI change. Preserve the existing snapshots, user .claude directory, and prior documents. Do not commit/push/deploy without instruction.
