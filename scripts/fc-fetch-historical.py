#!/usr/bin/env python3
"""Download missing historical CSVs from football-data.co.uk.

Goal (docs/fc-phase5-evaluation.md quality gate): complete the 3-season E0
target so a NEW frozen evaluation spec can use multiple outer test periods.
Also grabs the prior season for every league we already have 2526 data for,
so the formula engine can fit per-league models the same way.

Honest-data rules (engine contracts):
- No substitution or fabrication: a league that fails to download is
  reported, never replaced by another source.
- Existing files are never overwritten (only --force does).
- TLS to football-data.co.uk fails from some networks (see
  betting-machine-fc/data/README.md); the GitHub mirror
  (datasets/football-datasets, PDDL) provides score-only seasons
  (<LEAGUE>_<SEASON>_mirror.csv) as a SEPARATE provenance lane — never
  renamed to impersonate the odds-bearing originals.

Usage:
    python3 scripts/fc-fetch-historical.py               # missing 2324 + 2425
    python3 scripts/fc-fetch-historical.py --season 2324 --league E0
    python3 scripts/fc-fetch-historical.py --verify      # integrity report only
    python3 scripts/fc-fetch-historical.py --mirror E0 2324 2425  # score-only mirror lane
"""
import argparse
import csv
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'betting-machine-fc'))
import scraper_historical as sh  # noqa: E402

DATA_DIR = os.path.join(BASE_DIR, 'betting-machine-fc', 'data')

MIRROR_BASE = 'https://raw.githubusercontent.com/datasets/football-datasets/master/datasets'
MIRROR_LEAGUES = {
    'E0': ('premier-league', 'England Premier League'),
    'SP1': ('la-liga', 'Spain La Liga'),
    'D1': ('bundesliga', 'Germany Bundesliga'),
    'I1': ('serie-a', 'Italy Serie A'),
    'F1': ('ligue-1', 'France Ligue 1'),
}

# Leagues the formula engine pipeline knows about (mirror of data dir).
LEAGUES = {
    'E0': 'England Premier League',
    'E1': 'England Championship',
    'E2': 'England League One',
    'E3': 'England League Two',
    'EC': 'England National League',
    'SP1': 'Spain La Liga',
    'SP2': 'Spain Segunda',
    'D1': 'Germany Bundesliga',
    'D2': 'Germany 2. Bundesliga',
    'I1': 'Italy Serie A',
    'I2': 'Italy Serie B',
    'F1': 'France Ligue 1',
    'F2': 'France Ligue 2',
    'N1': 'Netherlands Eredivisie',
    'P1': 'Portugal Primeira Liga',
    'B1': 'Belgium Jupiler',
    'T1': 'Turkey SuperLiga',
    'G1': 'Greece Super League',
    'SC1': 'Scotland Premiership',
    'SC2': 'Scotland Championship',
    'SC3': 'Scotland League One',
}


def fetch_mirror(league, seasons):
    """Score-only mirror lane (datasets/football-datasets, PDDL).

    Writes <LEAGUE>_<SEASON>_mirror.csv — never an odds-bearing name.
    Fails loudly per league; never fabricates.
    """
    repo_dir, label = MIRROR_LEAGUES[league]
    ok, fail = [], []
    for season in seasons:
        dest = os.path.join(DATA_DIR, f'{league}_{season}_mirror.csv')
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            ok.append((league, season, 'cached'))
            continue
        url = f'{MIRROR_BASE}/{repo_dir}/season-{season}.csv'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(dest, 'wb') as f:
                f.write(data)
            rows, complete = verify(dest)
            if rows < 100 or not complete:
                raise ValueError(f'bad mirror data (rows={rows}, complete={complete})')
            ok.append((league, season, f'{rows} rows'))
        except Exception as exc:
            fail.append((league, season, str(exc)))
    return ok, fail


def season_codes():
    """Seasons we already hold locally, mapped to the prior-season codes."""
    have = set()
    for fn in os.listdir(DATA_DIR):
        if fn.endswith('.csv'):
            try:
                league, season = fn[:-4].rsplit('_', 1)
                have.add((league, season))
            except ValueError:
                pass
    want = set()
    for league, season in have:
        if season == '2526':
            want.add((league, '2425'))
        elif season == '2425':
            want.add((league, '2324'))
    return sorted(want), sorted(have)


def verify(path):
    """Return (rows, complete) — complete means FTHG/FTAG parse for every row."""
    rows = sh.load_rows(path)
    if not rows:
        return 0, False
    complete = all(
        r.get('HomeTeam') and r.get('AwayTeam')
        and sh.normalize(r)['fthg'] is not None and sh.normalize(r)['ftag'] is not None
        for r in rows
    )
    return len(rows), complete


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', help='Season code, e.g. 2324 (default: all missing)')
    ap.add_argument('--league', help='League code, e.g. E0 (default: all missing)')
    ap.add_argument('--force', action='store_true', help='Overwrite existing files')
    ap.add_argument('--verify', action='store_true', help='Only report integrity of local files')
    ap.add_argument('--mirror', nargs='+', metavar='SEASON',
                    help=f"Fetch score-only mirror seasons for top-5 leagues (e.g. --mirror 2223 2324 2425). Leagues: {', '.join(MIRROR_LEAGUES)}")
    args = ap.parse_args()

    if args.mirror:
        seasons = args.mirror
        print(f'mirror lane (score-only, PDDL): top-5 leagues, seasons {seasons}')
        all_ok, all_fail = [], []
        for league in MIRROR_LEAGUES:
            ok, fail = fetch_mirror(league, seasons)
            all_ok.extend(ok)
            all_fail.extend(fail)
        print('== mirror results ==')
        for league, season, note in all_ok:
            print(f'OK   {league}_{season}_mirror: {note}')
        for league, season, err in all_fail:
            print(f'FAIL {league}_{season}_mirror: {err}')
        return 0 if not all_fail else 1

    if args.verify:
        print('== integrity report ==')
        for fn in sorted(os.listdir(DATA_DIR)):
            if not fn.endswith('.csv'):
                continue
            p = os.path.join(DATA_DIR, fn)
            try:
                rows, complete = verify(p)
                status = 'OK' if complete else 'INCOMPLETE'
            except Exception as exc:
                rows, complete, status = 0, False, f'ERR {exc}'
            print(f'{status:10} {fn:18} rows={rows}')
        return 0

    want, have = season_codes()
    if args.season or args.league:
        want = [(l, s) for (l, s) in want if
                (not args.league or l == args.league) and (not args.season or s == args.season)]

    todo = [(l, s) for (l, s) in want if args.force or (l, s) not in have]
    print(f'targets: {len(want)} missing-season pairs, todo: {len(todo)}')
    ok, fail = [], []
    for league, season in todo:
        try:
            path = sh.download(league, season, out_dir=DATA_DIR, force=args.force)
            rows, complete = verify(path)
            if rows < 100:
                raise ValueError(f'suspiciously few rows ({rows})')
            (ok if complete else fail).append((league, season, rows,
                                               'OK' if complete else 'INCOMPLETE'))
        except Exception as exc:
            fail.append((league, season, 0, str(exc)))

    print('== results ==')
    for league, season, rows, status in ok:
        print(f'OK   {league}_{season}: {rows} rows ({LEAGUES.get(league, "?")})')
    for league, season, rows, status in fail:
        print(f'FAIL {league}_{season}: {status}')

    # Special callout: the Phase 5 blocker season.
    for league, season, rows, status in fail:
        if (league, season) == ('E0', '2324'):
            print('\nE0 2324 still missing — Phase 5 third-season gate stays closed.')
            print('Retry from the VPS (different network path) or fetch manually from:')
            print('  https://www.football-data.co.uk/mmz4281/2324/E0.csv')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
