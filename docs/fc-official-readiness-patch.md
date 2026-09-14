# Official readiness patch — 2026-09-14

This patch supplies two historical outer evaluations and prospective quote collection.
It does not approve a model, claim profitable ROI, or deploy the collector to production.

## Completed and verified

- `football_formula_engine.outer_cli` freezes a source-hashed protocol before fitting,
  validates non-overlapping outer targets and result availability, and checkpoints each
  fold, prediction bundle, model, calibration and bootstrap replicate. Failed refits are
  saved separately; restarting resumes successes and failures without replacing them.
- E0 outer targets: last 300 fixtures of 2024/25 and last 300 fixtures of 2025/26.
  The calibration/policy season is respectively 2023/24 and 2024/25. Each fold independently
  selects half-life/calibration using only its earlier policy period. These are historical
  replays of previously inspected data, not two newly untouched holdouts. First-fold outcomes
  may enter the second fold's earlier training/inner periods, as in expanding-window evaluation.
- New `moving_block_refit_v2` refits on the sampled training rows only. The legacy smoke
  implementation added the original training set to its resample, damping variability.
  Historical artifacts remain reproducible under the original method.
- `live_quotes.db` stores immutable quote observations with raw response, provider/bookmaker,
  capture time, source update time when present, signed quarter-lines and fixture metadata.
  Scan captures supported-league quotes before missing-model/team/value gates.
- First qualifying research decision per fixture/policy is stored immutably with its entry
  contract, quote observation, one-unit stake and full model artifact. It is research-only;
  it does not bypass the approved paper/official selector. Later scans cannot rewrite its entry.
- A bounded quote-only command allows independent collection without model fitting or changing
  Today's Pick files. Normal scans also collect quotes. No scheduler has been installed.
- As-of and closing queries exclude future/post-kickoff observations. Missing source timestamps
  remain null. A recently captured quote is not proof of source freshness or bet execution.
- Second-source adapter supports The Odds API event h2h/totals/spreads/BTTS, explicit fixture
  mappings, exact team/event/sport checks and kickoff tolerance. Signed AH lines are preserved.
  Compare only the same market/side/line across distinct bookmakers within bounded capture skew.
  Transport matching is not an approval or proof of bookmaker independence.
- Fixed live O/U pricing: scraper uses integer keys 9/10; pricing previously looked for strings.
- Preserved original Phase 5 spec separately, repairing the pre-existing test mismatch between
  the historical registry and the recently edited evaluation spec.
- Registry reason codes now reflect actual uncertainty/ROI/CLV availability instead of always
  saying uncertainty is unavailable. Prospective approval remains explicitly unimplemented.

## Evaluation checkpoint

Active report: `betting-machine-fc/football_formula_engine/artifacts/outer-v1/outer-evaluations/outer-9822eb4cccabaa13.json`.

| Outer target | Matches | Selected BTTS Brier | League BTTS Brier | Selected O/U Brier | League O/U Brier | Successful refits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024/25 | 300 | 0.254036 | 0.251928 | 0.243574 | 0.247794 | 24/30 |
| 2025/26 | 300 | 0.252748 | 0.246051 | 0.256336 | 0.247901 | 29/30 |

Lower Brier is better. BTTS fails the league baseline in both periods; O/U only beats it in
the first period. Both uncertainty reports remain below the 30-successful-refit floor.
The floor is an engineering minimum, not statistical proof of stable uncertainty.

The first failed calibration refit was reproduced: its projected fixture violates the DC rho
positivity interval (`RHO_INVALID_FOR_FIXTURE`). It is recorded as a failed replicate, not repaired
by clipping probabilities or silently substituting a different sample. A training-only rho-domain
constraint is a candidate for a separately versioned evaluation; changing it needs a new protocol.

Validation: 215 Python tests passed, including quote immutability, first-entry locking, as-of/closing
cutoffs, signed AH lines, source mapping rejection, source matching, integer O/U pricing, real
chronological folds and scan capture despite an unavailable model. A real bounded provider test
captured fixture `748535033` with 43 quotes. Local DB is ignored by Git and is not proof that a
production scheduler is collecting data. Re-running the outer command resumed the checkpoints.

## Commands

From the repository root, PowerShell:

```powershell
$env:PYTHONPATH='betting-machine-fc'
python -m football_formula_engine.outer_cli
python scripts/fc-collect-quotes.py --limit 10
python -m football_formula_engine.second_source --mapping path/to/verified-fixtures.json
python -m pytest betting-machine-fc/football_formula_engine/tests -q -p no:cacheprovider
```

`FC_QUOTES_DB` optionally selects a persistent local database. A server deployment must place it
on persistent storage. The bounded collector samples provider-listed events; use explicit fixture
IDs for targeted near-kickoff capture. A closing quote is only available if collection actually ran
close enough to kickoff; no historical times are manufactured.

Second source requires `FC_SECOND_ODDS_API_KEY`, `FC_SECOND_BOOKMAKER`, and for scan integration
`FC_SECOND_MAPPING_PATH`. Neither key nor bookmaker was configured in this environment. Missing
configuration reports `NOT_CONFIGURED`; no new account or paid subscription was created.
Store credentials in server environment configuration, not in committed files or chat.

Mapping JSON is an array. Example structure only (replace every example value with a verified mapping):

```json
[
  {
    "event_id": "provider-event-id",
    "sport_key": "soccer_epl",
    "source_home": "Exact source home name",
    "source_away": "Exact source away name",
    "fixture": {
      "match_id": "1xbit-fixture-id",
      "start_ts": 1900000000,
      "home": "Canonical home name",
      "away": "Canonical away name"
    }
  }
]
```

Provider contract reference: https://the-odds-api.com/liveapi/guides/v4/

## Remaining evidence and implementation

1. Configure and exercise an actual second bookmaker on matching events; validate source market
   coverage, freshness and fixture mapping. Missing markets remain missing.
2. Deploy and schedule collection, especially near kickoff. Current live proof is one event,
   not a sufficient prospective sample or verified executable-price history.
3. Resolve invalid-rho refits under a newly versioned training constraint; evaluate market quality
   on a frozen protocol. Do not retune on these reported outer results and call them fresh holdouts.
4. Settle the immutable research entries with authoritative results, add payout-aware ROI/CLV
   reporting and uncertainty, and authenticate that evidence into a scoped approval registry.
   Existing offline paper accounting remains separate; the research journal has no settlement bridge yet.
5. Require prospective evidence before production approval. AH still needs its payout-aware
   validation. The UI continues displaying experimental watch candidates, not Official picks.
