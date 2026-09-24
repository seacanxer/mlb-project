#!/usr/bin/env python3
"""Fetch multi-season historical results into betting-machine-fc/data/historical/.

Read-only for the model: the live scan never writes here during a scan.
Sources (verified reachable from this host 2026-09-23):
  - football-data.co.uk  mmz4281/{season}/{LEAGUE}.csv   (scores + odds)
  - engsoccerdata        facup.csv                        (FA Cup scores only)

Honesty rules:
  - A failed download is reported, never replaced by another source.
  - Existing files are never overwritten without --force.
  - The FA Cup lane is written as facup_<season>.csv and is score-only; it
    never carries an odds-bearing filename.
"""
import argparse
import csv
import io
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'betting-machine-fc', 'data')
HIST_DIR = os.path.join(DATA_DIR, 'historical')

LEAGUE_TZ = {
    'E0': 'Europe/London', 'E1': 'Europe/London', 'E2': 'Europe/London',
    'E3': 'Europe/London', 'EC': 'Europe/London',
    'SP1': 'Europe/Madrid', 'SP2': 'Europe/Madrid',
    'D1': 'Europe/Berlin', 'D2': 'Europe/Berlin',
    'I1': 'Europe/Rome', 'I2': 'Europe/Rome',
    'F1': 'Europe/Paris', 'F2': 'Europe/Paris',
    'N1': 'Europe/Amsterdam', 'P1': 'Europe/Lisbon', 'B1': 'Europe/Brussels',
    'T1': 'Europe/Istanbul', 'G1': 'Europe/Athens',
    'SC1': 'Europe/London', 'SC2': 'Europe/London', 'SC3': 'Europe/London',
}
FD_SEASONS = ['2021', '2122', '2223', '2324', '2425']
FACUP_URL = 'https://raw.githubusercontent.com/jalapic/engsoccerdata/master/data-raw/facup.csv'


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def season_label(code):
    return f'{code[0]}{code[1:]}'


def fetch_football_data(league, seasons, force):
    os.makedirs(HIST_DIR, exist_ok=True)
    ok, fail = [], []
    for season in seasons:
        dest = os.path.join(HIST_DIR, f'{league}_{season}.csv')
        if os.path.exists(dest) and not force:
            ok.append((league, season, 'cached'))
            continue
        try:
            payload = fetch(f'https://www.football-data.co.uk/mmz4281/{season}/{league}.csv')
            text = payload.decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(text)))
            complete = [r for r in rows if r.get('HomeTeam') and r.get('AwayTeam')
                        and (r.get('FTHG') or '').isdigit() and (r.get('FTAG') or '').isdigit()
                        and r.get('Time')]
            if len(complete) < 50:
                raise ValueError(f'only {len(complete)} complete rows')
            with open(dest, 'w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            ok.append((league, season, f'{len(complete)} complete'))
        except Exception as exc:
            fail.append((league, season, str(exc)[:120]))
    return ok, fail


def fetch_facup(force, min_season=2008):
    os.makedirs(HIST_DIR, exist_ok=True)
    dest = os.path.join(HIST_DIR, 'facup_results.csv')
    if os.path.exists(dest) and not force:
        return [('FACUP', 'all', 'cached')], []
    try:
        text = fetch(FACUP_URL).decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(text)))
        kept = []
        for row in rows:
            season = row.get('Season') or ''
            if not season.isdigit() or int(season) < min_season:
                continue
            try:
                home_goals = int(row['hgoal'])
                away_goals = int(row['vgoal'])
            except (TypeError, ValueError):
                continue
            kept.append({
                'Date': row.get('Date', ''), 'Season': season,
                'HomeTeam': row.get('home', ''), 'AwayTeam': row.get('visitor', ''),
                'FTHG': home_goals, 'FTAG': away_goals,
                'Round': row.get('round', ''), 'Tie': row.get('tie', ''),
                'AET': row.get('aet', ''), 'Pen': row.get('pen', ''),
                'Neutral': row.get('neutral', ''), 'Venue': row.get('Venue', ''),
                'Tier': row.get('tier', ''), 'division': row.get('division', ''),
            })
        if len(kept) < 100:
            raise ValueError(f'only {len(kept)} usable FA Cup rows')
        with open(dest, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(kept[0].keys()))
            writer.writeheader()
            writer.writerows(kept)
        return [('FACUP', f'{min_season}+', f'{len(kept)} matches')], []
    except Exception as exc:
        return [], [('FACUP', 'all', str(exc)[:160])]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--seasons', nargs='*', default=FD_SEASONS)
    parser.add_argument('--leagues', nargs='*', default=sorted(LEAGUE_TZ))
    parser.add_argument('--facup-min-season', type=int, default=2008)
    parser.add_argument('--facup-only', action='store_true')
    args = parser.parse_args(argv)

    ok, fail = [], []
    if not args.facup_only:
        for league in args.leagues:
            good, bad = fetch_football_data(league, args.seasons, args.force)
            ok.extend(good)
            fail.extend(bad)
    good, bad = fetch_facup(args.force, args.facup_min_season)
    ok.extend(good)
    fail.extend(bad)

    report = {
        'fetched_at': datetime.now(tz=timezone.utc).isoformat(),
        'hist_dir': HIST_DIR,
        'ok': ok,
        'failed': fail,
    }
    print(__import__('json').dumps(report, indent=2, sort_keys=True))
    return 1 if fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
