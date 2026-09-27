# P1 staging: settlement and fixture integrity

User authorized continuation after P0 on 27 September 2026. This branch is
stacked on P0; no ledger or production staking was changed.

## Implemented

- Complete team names and explicit symmetric aliases replace shared-word keys.
- Both feeds reject ambiguous matches, prefer the exact date and allow at most
  one day of provider timezone drift. Home/away orientation remains fixed.
- Primary feed retains repeated encounters rather than overwriting older games.
- Legacy `Home (Team)` labels settle correctly; invalid sides and non-quarter
  lines are rejected. Payout precision is retained to eight decimals.
- One invalid contract does not abort the entire settlement loop.
- Each available parlay leg can update while other legs await scores; a slip
  enters ROI only after all legs settle. Conditional single updates preserve
  repeat-run behavior.
- Settlement requires an explicit 90-minute period. TheSportsDB FT rows retain
  period/status; AET/PEN and missing statuses are rejected. FlashScore list scores
  lack period evidence and remain unresolved. OpenLigaDB period is also unknown.
- Offline replay reads an explicit result export, deduplicates contracts, never
  updates SQLite, and reports exclusions rather than guessing results.

## Recorded validation

`python -m pytest tests/unit/test_fc_p0_audit.py tests/unit/test_fc_p1_integrity.py betting-machine-fc/football_formula_engine/tests/test_calibration_metrics.py -q`

**17 tests passed.** Synthetic coverage includes wrong-team rejection, date
ambiguity, normalization, team categories, quarter payouts, invalid contracts,
repeatable replay, and rejection of extra-time scores.

Read-only public feed retrieval returned **3,874 FlashScore rows and 74 alternate
rows (3,948 total)**. Replay against **203 unique historical singles** found
**32 candidate fixture matches**, but their export lacked explicit 90-minute
final-result evidence. **171** had no unique fixture result. Thus verified
settlements **0**, unresolved **203 (100%)**; the <10% target is **not achieved**.
This is a dry-run coverage result, not a new production overdue measurement.
Retrieved raw results stay local and gitignored.

Verified cohort n=0: win rate, ROI, Brier and log loss are **unavailable**, not
zero. The earlier 18-row provisional P0 metrics remain unchanged; no model
improvement has been demonstrated.

## Remaining evidence and phase boundary

Need an authoritative production ledger export and historical FT 90-minute
results, including fixture identity/date/league and source period evidence.
Public list scores alone cannot establish that period. Same-day doubleheaders
without distinct kickoff/fixture identifiers remain deliberately ambiguous.

P1 historical re-settlement and success target remain incomplete. P2/P3 model
ranking, bootstrap gates and staking are not started: they must follow P1's
validated historical cohort. No production settlement, deployment or main merge
has run. This draft requires further data work before production use.
