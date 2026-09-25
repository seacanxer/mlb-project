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
