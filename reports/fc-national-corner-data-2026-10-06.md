# National corner coverage — 6 October 2026

## Cause and changes

The scanner rejected INT_MEN before loading secondary statistics because national
teams were not registered club leagues. The global dayfeed was not a scoped
national training source. A dedicated INT_MEN_stat_history.csv now feeds the
corner/card model. UEFA Nations League statistics were fetched directly from
FotMob match pages; finals/playoffs, women/youth and club National League are
excluded. Existing effective-sample thresholds remain unchanged.

The importer now supports historical date backfills, portable paths, correct
output directories, normalized retry identities, concurrent date feeds and
visible failure counts. The all-league refresh includes the national backfill.
Explicit provider aliases cover Czech Republic/Czechia and Republic of North
Macedonia/North Macedonia. No production settlement or staking was changed.

## Measured result

- 582 completed matches with actual corners; 7 older match pages lacked readable
  statistics after retries; zero date-feed failures. Source metadata records IDs.
- Initial 266-row snapshot covered 4/10 scheduled UEFA fixtures. With backfill
  since 2020 and aliases, 10/10 produce corner projections.
- All 10 UEFA fixtures had real offered corner totals and handicap odds on 1xbit.
- Live fixture/odds replay is recorded in fc-national-corner-coverage-2026-10-06.json.
- Python full suite: 313 passed before final metadata/alias refinements; final
  verification is recorded in the task response.

| Fixture | Total corner projection |
| --- | ---: |
| Kazakhstan–Faroe Islands | 9.44 |
| Albania–San Marino | 9.21 |
| Belarus–Finland | 8.86 |
| Croatia–Spain | 9.22 |
| England–Czech Republic | 9.13 |
| Estonia–Iceland | 8.60 |
| Luxembourg–Bulgaria | 8.99 |
| Moldova–Slovakia | 9.29 |
| Scotland–Slovenia | 8.26 |
| Switzerland–North Macedonia | 8.71 |

These are count projections, not observed corner counts or validated win rates.
Pricing uses actual offered lines. This audit bypasses final scanner selection
and does not assert that every offered line qualifies as a value/Official pick.
Older observations remain downweighted by the existing appearance decay. Some
national games take place at neutral venues: venue effects need separate future
validation; missing referee data remains explicit. This dataset does not prove
coverage for other national competitions.

## VPS refresh after deploying these changes

From the repository root using the FC environment:

```bash
betting-machine-fc/venv/bin/python scripts/fc-fetch-match-stats.py --code INT_MEN --names 'UEFA Nations League' --national-backfill --days 45 --workers 8
betting-machine-fc/venv/bin/python scripts/fc-national-corner-audit.py
betting-machine-fc/venv/bin/python scripts/fc-scan-live.py
```

The committed history is usable immediately. Refresh exits 1 with status partial
when stats are missing, while preserving valid downloaded rows; check metadata.
Run the existing scheduled scanner after refresh to replace cached UI analysis.
The normal all-league refresh now includes this same national path.

Schedule: https://www.uefa.com/uefanationsleague/
Statistics: https://www.fotmob.com/
