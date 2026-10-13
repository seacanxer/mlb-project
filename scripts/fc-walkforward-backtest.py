"""Walk-forward historical replay of the live FC goal model.

Stage 1 (this script, ``build``): for every Football-Data league/season with
pre-match odds, refit the production Dixon-Coles model weekly using only
results available before that week, project each fixture and infer the
market-implied goal rates from the same pre-match book. One JSON line per
fixture is written so that decision policies can be replayed cheaply.

Stage 2 (``evaluate``): replay the live decision policy and alternatives over
the stored projections, pricing 1X2, O/U 2.5 and the main Asian handicap line
at historical pre-match prices and grading on the final score.

Historical Football-Data prices are not the 1xbit quotes used live and carry
no capture timestamps. The replay measures the formula's behaviour against a
real, large, out-of-sample market history; it is not a live ROI record.

Usage:
    python scripts/fc-walkforward-backtest.py build --out /tmp/fc_wf.jsonl
    python scripts/fc-walkforward-backtest.py evaluate --records /tmp/fc_wf.jsonl
"""
import argparse
import csv
import json
import math
import os
import sys
from multiprocessing import Pool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine.data import load_football_data_csv  # noqa: E402
from football_formula_engine.leagues import LEAGUES  # noqa: E402
from football_formula_engine.market_goals import infer_market_goals  # noqa: E402
from football_formula_engine.model import FitConfig, fit_dixon_coles, project_fixture  # noqa: E402

SEASONS = ['2021', '2122', '2223', '2324', '2425', '2526']
TEST_SEASONS = ['2223', '2324', '2425', '2526']
WEEK = 7 * 86400

ODDS_FIELDS = {
    # pre-match
    'b365_1x2': ('B365H', 'B365D', 'B365A'), 'ps_1x2': ('PSH', 'PSD', 'PSA'),
    'avg_1x2': ('AvgH', 'AvgD', 'AvgA'), 'max_1x2': ('MaxH', 'MaxD', 'MaxA'),
    'b365_ou': ('B365>2.5', 'B365<2.5'), 'ps_ou': ('P>2.5', 'P<2.5'),
    'avg_ou': ('Avg>2.5', 'Avg<2.5'), 'max_ou': ('Max>2.5', 'Max<2.5'),
    'b365_ah': ('B365AHH', 'B365AHA'), 'ps_ah': ('PAHH', 'PAHA'),
    'avg_ah': ('AvgAHH', 'AvgAHA'), 'max_ah': ('MaxAHH', 'MaxAHA'),
    # closing
    'psc_1x2': ('PSCH', 'PSCD', 'PSCA'), 'b365c_1x2': ('B365CH', 'B365CD', 'B365CA'),
    'psc_ou': ('PC>2.5', 'PC<2.5'), 'b365c_ou': ('B365C>2.5', 'B365C<2.5'),
    'psc_ah': ('PCAHH', 'PCAHA'), 'b365c_ah': ('B365CAHH', 'B365CAHA'),
}


def history_path(code, season):
    for path in (os.path.join(FC_DIR, 'data', 'historical', f'{code}_{season}.csv'),
                 os.path.join(FC_DIR, 'data', f'{code}_{season}.csv')):
        if os.path.exists(path):
            return path
    return None


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 1.0 else None


def read_raw_rows(path):
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as handle:
        return list(csv.DictReader(handle))


def row_odds(row):
    odds = {}
    for key, fields in ODDS_FIELDS.items():
        values = [number(row.get(field)) for field in fields]
        if all(values):
            odds[key] = values
    for key in ('AHh', 'AHCh'):
        try:
            value = float(row.get(key))
            if math.isfinite(value) and abs(value * 4 - round(value * 4)) < 1e-8:
                odds[key] = value
        except (TypeError, ValueError):
            pass
    return odds


def book(odds, prefix):
    one = odds.get(f'{prefix}_1x2')
    ou = odds.get(f'{prefix}_ou')
    if not one or not ou:
        return None
    return {'odds_1x2': {1: one[0], 2: one[1], 3: one[2]},
            'odds_ou': {'2.5': {9: ou[0], 10: ou[1]}}}


def build_job(args):
    code, season = args
    seasons = [SEASONS[SEASONS.index(season) - 1], season]
    tz = LEAGUES[code].tz
    matches, raw = [], {}
    for train_season in seasons:
        path = history_path(code, train_season)
        if not path:
            continue
        try:
            normalized, _ = load_football_data_csv(path, competition_id=code,
                                                   season=train_season, timezone_name=tz)
        except Exception as exc:  # malformed archive: report, never fabricate
            return {'code': code, 'season': season, 'error': f'{train_season}: {exc}', 'records': []}
        matches.extend(normalized)
        if train_season == season:
            rows = read_raw_rows(path)
            for match in normalized:
                raw[match.fixture_id] = rows[match.source_row - 2] if match.source_row >= 2 else {}
    targets = sorted((m for m in matches if m.season == season and m.home_goals is not None),
                     key=lambda m: m.kickoff_utc)
    if not targets:
        return {'code': code, 'season': season, 'error': 'no target matches', 'records': []}
    records = []
    index = 0
    while index < len(targets):
        week_start = targets[index].kickoff_utc
        week = []
        while index < len(targets) and targets[index].kickoff_utc < week_start + WEEK:
            week.append(targets[index])
            index += 1
        cutoff = week_start - 3600
        fit_error = None
        try:
            artifact = fit_dixon_coles(matches, cutoff_utc=cutoff, config=FitConfig())
        except Exception as exc:
            artifact = None
            fit_error = str(exc)[:120]
        for match in week:
            record = {'code': code, 'season': season, 'kickoff': match.kickoff_utc,
                      'home': match.home_team_name, 'away': match.away_team_name,
                      'hg': match.home_goals, 'ag': match.away_goals}
            odds = row_odds(raw.get(match.fixture_id, {}))
            record['odds'] = odds
            if artifact is None:
                record['model_status'] = 'fit_failed:' + fit_error
                record['dc'] = None
            else:
                proj = project_fixture(artifact, home_team_id=match.home_team_id,
                                       away_team_id=match.away_team_id, season=season)
                record['model_status'] = proj.status
                record['model_reasons'] = list(proj.reason_codes)
                record['dc'] = ([proj.lambda_home, proj.lambda_away, proj.rho]
                                if proj.distribution is not None else None)
            for prefix in ('b365', 'ps', 'avg'):
                mk = book(odds, prefix)
                goals = infer_market_goals(mk) if mk else None
                record[f'mg_{prefix}'] = [goals['home'], goals['away']] if goals else None
            records.append(record)
    return {'code': code, 'season': season, 'error': None, 'records': records}


def build(out_path, codes, workers):
    jobs = [(code, season) for code in codes for season in TEST_SEASONS
            if history_path(code, season) and history_path(code, SEASONS[SEASONS.index(season) - 1])]
    print(f'{len(jobs)} league-season jobs', file=sys.stderr)
    with open(out_path, 'w', encoding='utf-8') as handle, Pool(workers) as pool:
        for result in pool.imap_unordered(build_job, jobs):
            for record in result['records']:
                handle.write(json.dumps(record, separators=(',', ':')) + '\n')
            handle.flush()
            print(f"  {result['code']} {result['season']}: {len(result['records'])} records"
                  + (f" ERROR {result['error']}" if result['error'] else ''), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--out', required=True)
    b.add_argument('--codes', default='')
    b.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2)))
    e = sub.add_parser('evaluate')
    e.add_argument('--records', required=True)
    args = parser.parse_args(argv)
    if args.command == 'build':
        codes = [c for c in args.codes.split(',') if c] or sorted(
            code for code, league in LEAGUES.items() if league.source == 'football-data')
        build(args.out, codes, args.workers)
    else:
        from fc_walkforward_policy import evaluate_main  # noqa: E402
        evaluate_main(args.records)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
