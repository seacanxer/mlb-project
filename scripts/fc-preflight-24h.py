#!/usr/bin/env python3
"""Read-only 24-hour FC coverage audit before fetching odds or publishing picks."""
import argparse
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / 'scripts' / 'fc-scan-live.py'
spec = importlib.util.spec_from_file_location('fc_scan_for_preflight', SCAN_PATH)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
from football_formula_engine.national_teams import (MODEL_CODE as NATIONAL_CODE,
    load_results as load_national_results, resolve_fixture as resolve_national_fixture,
    nonneutral_baseline_coverage)


def audit(matches, now, hours=24):
    future = [m for m in matches if 0 < float((m.get('info') or {}).get('start_ts') or 0) - now <= hours * 3600]
    leagues = Counter()
    unmatched = Counter()
    modelable = []
    seen_fixtures = set()
    duplicate_fixtures = 0
    supported = 0
    teams_cache = {}
    for match in future:
        info = match['info']
        league = info.get('league') or 'Unknown league'
        code = scan.model_code(league)
        if code is None:
            leagues[league] += 1
            continue
        supported += 1
        if code == NATIONAL_CODE:
            if code not in teams_cache:
                source = ROOT / 'betting-machine-fc' / 'data' / 'international_results.csv'
                if source.exists():
                    matches, neutral_ids, _counts, _latest = load_national_results(source, int(now))
                    teams_cache[code] = nonneutral_baseline_coverage(matches, neutral_ids)[1]
                else:
                    teams_cache[code] = {}
            teams = teams_cache[code]
            resolved = resolve_national_fixture(info.get('home'), info.get('away'), teams)
            home, away = resolved if resolved else (None, None)
        else:
            teams = teams_cache.setdefault(code, scan.csv_teams(code))
            home = scan.match_team(info.get('home'), teams)
            away = scan.match_team(info.get('away'), teams)
        if not home or not away:
            for name, found in ((info.get('home'), home), (info.get('away'), away)):
                if not found:
                    unmatched[f'{code}: {name or "Unknown"}'] += 1
            continue
        fixture_key = (code, home, away, int(float(info['start_ts'])))
        if fixture_key in seen_fixtures:
            duplicate_fixtures += 1
            continue
        seen_fixtures.add(fixture_key)
        modelable.append({'match_id': str(info.get('match_id')), 'league': league,
                          'home': info.get('home'), 'away': info.get('away'),
                          'start_ts': info.get('start_ts'), 'league_model': code})
    verdict = (f'NO_FIXTURES_{hours}H' if not future else
               f'NO_SUPPORTED_LEAGUE_{hours}H' if not supported else
               f'NO_MATCHED_TEAMS_{hours}H' if not modelable else f'MODELABLE_FIXTURES_{hours}H')
    return {'verdict': verdict, 'window_hours': hours, 'fixtures': len(future),
            'supported_league_fixtures': supported, 'modelable_team_fixtures': len(modelable),
            'duplicate_modelable_fixtures': duplicate_fixtures,
            'unsupported_leagues': dict(leagues.most_common()),
            'unmatched_teams': dict(unmatched.most_common()),
            'modelable_fixtures': modelable,
            'value_pick_status': 'NOT_EVALUATED_NO_LIVE_ODDS' if modelable else 'NO_MODELABLE_FIXTURES',
            'official_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matches', type=Path, default=ROOT / 'betting-machine-fc' / 'matches_detailed.json')
    parser.add_argument('--now', type=float, default=time.time())
    parser.add_argument('--hours', type=int, choices=(24, 72), default=24)
    args = parser.parse_args()
    with args.matches.open(encoding='utf-8') as handle:
        matches = json.load(handle)
    print(json.dumps(audit(matches, args.now, args.hours), ensure_ascii=False))


if __name__ == '__main__':
    main()
