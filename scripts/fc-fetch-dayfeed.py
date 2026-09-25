#!/usr/bin/env python3
"""Fetch score-feed results and rebuild the score-only training lanes.

Two score sources are supported (no odds, no fabrication):

* FotMob day feed - one request per calendar date lists every league FotMob
  knows about, so one fetch feeds every configured FotMob league.
* ESPN scoreboard - one request per (slug, date); used for leagues FotMob
  does not carry (opt-in with --espn).

Output files are football-data shaped score files with an honest lane suffix:

    {code}_{season}_dayfeed.csv   <- FotMob
    {code}_{season}_espn.csv      <- ESPN
    {code}_{season}_*.source.json <- provenance sidecar

Registered football-data files are never rewritten: a season is skipped when
an existing football-data/mirror CSV already covers it.

Run:
    python scripts/fc-fetch-dayfeed.py                 # fetch + rebuild all
    python scripts/fc-fetch-dayfeed.py --no-fetch      # rebuild from cache
    python scripts/fc-fetch-dayfeed.py --codes J2,SC1  # subset
    python scripts/fc-fetch-dayfeed.py --espn          # also fetch ESPN lanes
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine import day_feed, espn_feed  # noqa: E402
from football_formula_engine.leagues import (LEAGUES, feed_league_codes,  # noqa: E402
                                             matches_feed_name, season_label)

DATA_DIR = os.path.join(FC_DIR, 'data')
FOTMOB_CACHE = os.path.join(DATA_DIR, '.feed_cache', 'fotmob')
ESPN_CACHE = os.path.join(DATA_DIR, '.feed_cache', 'espn')
DEFAULT_FROM = '2025-07-01'
FIELDS = ('Div', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG')
SOURCE_LABEL = {'dayfeed': 'fotmob-dayfeed', 'espn': 'espn-scoreboard'}
ESPN_SLUGS = {'FAT': 'eng.trophy'}


def parse_date(value, label):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise SystemExit(f'Invalid --{label} date {value!r}; expected YYYY-MM-DD') from exc


def selected_codes(codes):
    if codes:
        wanted = [c.strip().upper() for c in codes.split(',') if c.strip()]
        unknown = [c for c in wanted if c not in LEAGUES]
        if unknown:
            raise SystemExit(f'Unknown league codes: {", ".join(unknown)}')
        return wanted
    return feed_league_codes('fotmob')


def feed_start_month(code):
    league = LEAGUES[code]
    if league.feed:
        return int(league.feed.get('season_start_month') or 7)
    return 7


def local_kickoff(match, tz_name):
    """Local kickoff in the league timezone (FotMob already reports local)."""
    if match.kickoff_local is not None:
        return match.kickoff_local
    if match.kickoff_utc is None:
        return None
    return match.kickoff_utc.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def canonical_team_names(matches_by_code):
    """One display name per upstream team id.

    FotMob spells the same club several ways over a season (an accented and
    an unaccented form, or ``Arsenal Academy`` vs ``Arsenal U21``).  The
    team id is stable, so the most frequent spelling for an id becomes the
    name written to the score-only lane; ties break alphabetically so the
    rebuild is deterministic.
    """
    counts = {}
    for rows in matches_by_code.values():
        for match in rows:
            for team_id, name in ((getattr(match, 'home_id', ''), match.home),
                                  (getattr(match, 'away_id', ''), match.away)):
                if team_id and name:
                    counts.setdefault(team_id, {}).setdefault(name, 0)
                    counts[team_id][name] += 1
    return {team_id: sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            for team_id, names in counts.items()}


def canonical_name(match, side, names):
    team_id = getattr(match, f'{side}_id', '')
    name = getattr(match, side)
    return names.get(team_id, name) if team_id else name


def canonical_collisions(code, rows, names):
    """Two upstream ids that collapse to one written name in this code."""
    seen = {}
    collisions = set()
    for match in rows:
        for side in ('home', 'away'):
            team_id = getattr(match, f'{side}_id', '')
            if not team_id:
                continue
            name = names.get(team_id, getattr(match, side))
            other = seen.setdefault(name, team_id)
            if other != team_id:
                collisions.add((name, tuple(sorted((other, team_id)))))
    return sorted(collisions)


def build_buckets(code, matches, names):
    """Deduplicate feed matches into football-data shaped rows keyed by fixture."""
    league = LEAGUES[code]
    start_month = feed_start_month(code)
    buckets = {}
    for match in matches:
        local = local_kickoff(match, league.tz)
        if local is None:
            continue
        home = canonical_name(match, 'home', names)
        away = canonical_name(match, 'away', names)
        if not home or not away or home == away:
            continue
        row = {'Div': code, 'Date': local.strftime('%d/%m/%Y'),
               'Time': local.strftime('%H:%M'), 'HomeTeam': home,
               'AwayTeam': away, 'FTHG': str(match.home_goals),
               'FTAG': str(match.away_goals)}
        key = (local.strftime('%Y-%m-%d %H:%M'), home, away)
        # Later days overwrite earlier ones, so late score corrections win.
        buckets.setdefault(season_label(local, start_month), {})[key] = row
    return buckets


def collect_fotmob(codes, days):
    matches = day_feed.parse_cache(FOTMOB_CACHE, days)
    configured_ccodes = {LEAGUES[c].feed.get('ccode') for c in codes if LEAGUES[c].feed}
    selected, unmatched = {}, {}
    for match in matches:
        hits = [c for c in codes
                if matches_feed_name(c, ccode=match.ccode, name=match.league_name,
                                     pl_name=match.pl_name)]
        if not hits:
            if match.ccode in configured_ccodes:
                key = f'{match.ccode}: {match.pl_name or match.league_name}'
                unmatched[key] = unmatched.get(key, 0) + 1
            continue
        for code in hits:
            selected.setdefault(code, []).append(match)
    return selected, len(matches), unmatched


def collect_espn(codes):
    selected, parsed = {}, 0
    for code, slug in ESPN_SLUGS.items():
        if code not in codes:
            continue
        rows = espn_feed.parse_cache(ESPN_CACHE, slug)
        if rows:
            parsed += len(rows)
            selected[code] = rows
    return selected, parsed


def registered_seasons_covered(code):
    """Seasons already served by a tracked football-data/mirror file.

    Score-feed lanes this script writes itself are always rebuilt; only
    upstream football-data files are protected from being overwritten.
    """
    return {season for filename, season in LEAGUES[code].csvs
            if not filename.endswith(('_dayfeed.csv', '_espn.csv'))
            and os.path.exists(os.path.join(DATA_DIR, filename))}


def write_lane(code, season, entries, lane, *, dry_run, retrieved_at, days):
    if lane == 'dayfeed' and season in registered_seasons_covered(code):
        return {'skipped': 'REGISTERED_FOOTBALL_DATA_FILE_EXISTS'}
    target = Path(DATA_DIR) / f'{code}_{season}_{lane}.csv'
    rows = sorted(entries.values(), key=lambda r: (r['Date'], r['Time']))
    if not rows:
        if target.exists():
            return {'skipped': 'EMPTY_RESULT_KEPT_EXISTING_FILE'}
        return {'skipped': 'EMPTY_RESULT'}
    if dry_run:
        return {'rows': len(rows), 'dry_run': True, 'path': target.name}
    payload = _csv_bytes(rows)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = target.with_suffix('.csv.tmp')
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    counts = {}
    for row in rows:
        for side in ('HomeTeam', 'AwayTeam'):
            counts[row[side]] = counts.get(row[side], 0) + 1
    provenance = {
        'source': SOURCE_LABEL[lane],
        'feed': (day_feed.FEED_URL.format(date='{YYYYMMDD}') if lane == 'dayfeed'
                 else espn_feed.SCOREBOARD_URL.format(slug='{slug}', day='{YYYYMMDD}')),
        'retrieved_at': int(retrieved_at),
        'source_sha256': digest,
        'rows': len(rows),
        'teams': len(counts),
        'min_team_matches': min(counts.values()) if counts else 0,
        'days': sorted(days),
        'season': season,
        'transformation': 'finished_match_scores_only_no_odds',
        'columns': list(FIELDS),
    }
    target.with_suffix('.source.json').write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'rows': len(rows), 'teams': len(counts),
            'min_team_matches': provenance['min_team_matches'], 'path': target.name}


def _csv_bytes(rows):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--from', dest='date_from', default=DEFAULT_FROM,
                        help=f'start of the fetch window (default {DEFAULT_FROM})')
    parser.add_argument('--to', dest='date_to', default=None,
                        help='end of the fetch window (default: today, UTC)')
    parser.add_argument('--codes', default=None,
                        help='comma separated league codes (default: all FotMob leagues)')
    parser.add_argument('--delay', type=float, default=1.5,
                        help='seconds to sleep before each upstream request')
    parser.add_argument('--refresh-days', type=int, default=3,
                        help='re-fetch the newest N days so late scores land')
    parser.add_argument('--no-fetch', action='store_true',
                        help='rebuild CSVs from the local cache only')
    parser.add_argument('--espn', action='store_true',
                        help='also fetch the ESPN scoreboard lanes')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be written without writing')
    args = parser.parse_args(argv)

    started = time.time()
    today = datetime.now(timezone.utc).date()
    start = parse_date(args.date_from, 'from')
    end = parse_date(args.date_to, 'to') if args.date_to else today
    if end < start:
        raise SystemExit('--to must not be before --from')

    codes = [c for c in selected_codes(args.codes)
             if LEAGUES[c].feed and LEAGUES[c].feed.get('kind') == 'fotmob']
    if not codes:
        raise SystemExit('No FotMob leagues selected')

    fetch = {'fetched': [], 'cached': [], 'failures': []}
    if not args.no_fetch:
        print(f'fetching FotMob {start}..{end} for {len(codes)} leagues',
              file=sys.stderr)
        fetch = day_feed.fetch_range(start, end, cache_dir=FOTMOB_CACHE,
                                     delay=args.delay)
        if args.refresh_days > 0:
            refresh_from = end - timedelta(days=args.refresh_days - 1)
            extra = day_feed.fetch_range(refresh_from, end, cache_dir=FOTMOB_CACHE,
                                         refresh=True, delay=args.delay)
            fetch['failures'].extend(extra['failures'])
        for failure in fetch['failures']:
            print(f'  fetch failed: {failure["day"]} {failure["reason"]}',
                  file=sys.stderr)

    days = day_feed.day_keys(start, end)
    selected, parsed_matches, unmatched = collect_fotmob(codes, days)
    espn_selected, espn_parsed = ({}, 0)
    if args.espn:
        if not args.no_fetch:
            for code, slug in ESPN_SLUGS.items():
                if code not in codes:
                    continue
                day = start
                while day <= end:
                    try:
                        espn_feed.fetch_day(slug, day.strftime('%Y%m%d'),
                                            cache_dir=ESPN_CACHE, delay=args.delay)
                    except Exception as exc:
                        print(f'  ESPN {slug} {day}: {exc}', file=sys.stderr)
                    day += timedelta(days=1)
        espn_selected, espn_parsed = collect_espn(codes)

    names = canonical_team_names({**selected, **espn_selected})
    buckets = {code: build_buckets(code, rows, names)
               for code, rows in selected.items()}
    espn_buckets = {code: build_buckets(code, rows, names)
                    for code, rows in espn_selected.items()}
    collisions = {code: canonical_collisions(code, rows, names)
                  for code, rows in {**selected, **espn_selected}.items()}
    collisions = {code: hits for code, hits in collisions.items() if hits}

    report = {'status': 'ok', 'window': [str(start), str(end)],
              'leagues_selected': codes,
              'fetched_days': len(fetch['fetched']), 'cached_days': len(fetch['cached']),
              'fetch_failures': fetch['failures'], 'parsed_matches': parsed_matches,
              'canonical_teams': len(names),
              'canonical_collisions': collisions,
              'unmatched_leagues': dict(sorted(unmatched.items(),
                                               key=lambda kv: -kv[1])[:25]),
              'leagues': {}}
    now = time.time()
    for code in sorted(set(buckets) | set(espn_buckets)):
        league_report = {}
        for season, entries in sorted(buckets.get(code, {}).items()):
            league_report[season] = write_lane(
                code, season, entries, 'dayfeed', dry_run=args.dry_run,
                retrieved_at=now, days=days)
        for season, entries in sorted(espn_buckets.get(code, {}).items()):
            league_report[f'{season}_espn'] = write_lane(
                code, season, entries, 'espn', dry_run=args.dry_run,
                retrieved_at=now, days=days)
        report['leagues'][code] = league_report

    if espn_parsed:
        report['parsed_espn_matches'] = espn_parsed
    report['seconds'] = round(time.time() - started, 1)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
