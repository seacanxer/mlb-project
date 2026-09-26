# FC manual settlement locks and coverage

## Deployment

Set `FC_LOCK_TOKEN` to a long random operator secret in the VPS environment,
restart the Next.js service, and enter the token in the FC watchlist. The token
stays in browser session storage, not in the repository or a public build
variable. The Next.js process must be able to write `betting-machine-fc/bets.db`
and `tracker_snapshot.json`.

Selecting a card adds it to the watchlist. **Kunci ke settlement** sends the
fixture ID, market, pick and displayed odds to `/api/fc/locks`. The server
resolves all other fields from the current scan and rejects expired quotes,
changed odds, and post-kickoff requests. It inserts one immutable manual bet
per fixture and market into `bets.db`. `fc-settle-live.py` settles that row;
`fc-snapshot.py` gives manual rows priority over duplicate legacy auto rows.
Scanner runs no longer insert new automatic bets. Older automatic bets remain
in the historical ROI cohort and are labeled `legacy_auto` in snapshots.

Browser-only locks created before this change remain visible as **belum masuk
settlement**. They require a new server lock while the fixture and quote are
still current. They are never backdated into the ledger.

## Batch single and parlay locks

The watchlist now offers **Kunci semua sebagai single** and **Kunci sebagai
parlay**. A batch validates every current fixture, quote and price before one
database transaction, so an invalid leg cannot leave a partial single batch.
Parlay requires at least two legs and writes one manual slip with frozen legs
and theoretical multiplied odds to `parlay_slips` and `parlay_legs`. It does not
insert the legs into `bets`; the main ROI counts each settled parlay as one
flat 1-unit wager alongside singles, and the market breakdown keeps a separate
`Parlay` row.
The same selection may intentionally be locked in both modes and is then two
separate exposures. Repeating the identical parlay returns its existing slip.

The FC settlement job settles manual parlay slips after every leg has a final
score. Each leg's gross return is multiplied; a push returns 1, half loss 0.5,
and half win `(odds + 1) / 2`. The tracker exposes
`manual_parlay_summary` and `manual_parlays` in the Hasil & ROI page. A settled
slip contributes to the headline ROI, hit rate, count, results table and equity
curve. Each
entry in `manual_parlays` embeds its frozen `legs` (kickoff, league, match,
market, pick, odds, FT score, per-leg result and multiplied return), so the
page can open a detail popup for a slip without re-querying the ledger. The
VPS must run the updated `scripts/fc-settle-live.py` and
`scripts/fc-snapshot.py`.
For legs from one match, the combined odds are a theoretical record and may
not be offered or priced the same way by a bookmaker.

## Refreshing settlement from the UI

The Hasil & ROI page has an active **Refresh settlement** button
(`POST /api/fc/settle`). It shells out to `scripts/fc-settle-live.py` with the
engine interpreter (VPS venv, else `FC_PYTHON`, else system python), waits up
to three minutes, then ALWAYS rebuilds `tracker_snapshot.json` with
`scripts/fc-snapshot.py` — so `manual_parlays[].legs` and the KPI cards stay
fresh even when a score feed is unreachable (the settle script only rebuilds
the snapshot on its own success path). A partial result returns HTTP 200 with
`status: "partial"` and an honest message: snapshot updated, settlement
failed. The page then re-reads the tracker. The button is disabled only while
the engine is offline (`picks.json` and `matches_detailed.json` both missing)
and requires the same `FC_LOCK_TOKEN` bearer token as the lock API when that
token is configured.

Nothing in the repository schedules settlement, so refresh it manually or add
a cron job on the VPS:

```bash
*/10 * * * * cd /path/to/repo && ./betting-machine-fc/venv/bin/python scripts/fc-settle-live.py >> /tmp/fc-settle.log 2>&1
```

A slip stays `pending` ("Menunggu skor") until every leg reports a final score
and at least 1h45m have passed since kickoff; feeds are FlashScore first, then
TheSportsDB/OpenLigaDB for major leagues.

## Why the 2026-09-25 scan showed 401 unsupported fixtures

The snapshot contains 437 fixtures and 424 without projections: 401 have no
mapped league model, 12 have unresolved team history, 10 national fixtures fail
the market disagreement check, and one quote capture failed. The 401 span many
competition levels and categories: Romanian Liga 3, Mexican fourth division,
Czech third/fourth divisions, Japanese J2, youth competitions and others.
The fixture/odds feed is not a finished-results training feed.

The scanner can fit only competitions with verified historical results and an
exact competition identity. On this update, the Scottish football-data CSV
codes were corrected (`SC1` Championship, `SC2` League One, `SC3` League Two),
three Championship seasons were used for team coverage, and safe name aliases
were added. National teams without enough non-neutral history are now reported
as `TEAM_LOW_COVERAGE`; clubs absent from the league history are
`TEAM_COVERAGE_MISSING`.

To reduce the remaining unsupported count, acquire season results for each
specific competition or division, verify the source rights and historical
cutoff, map provider fixture/team IDs, then run chronological evaluation before
opening value or Official gates. Do not map youth, women, reserve, and lower
divisions onto senior or top-division artifacts. TheSportsDB's free
`eventsseason` response for 2025 and 2026 J2 yielded only five events per
season during the 2026-09-25 check, insufficient for a league model.
