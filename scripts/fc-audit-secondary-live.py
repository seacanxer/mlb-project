#!/usr/bin/env python3
"""Read-only secondary scan: no picks.json, ledger, settlement or stake writes."""
import argparse
import json
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'betting-machine-fc'))
import scraper_1xbit as provider


def audit_fixture(info, scanner, cache):
    raw = provider.extract_secondary_markets(info['match_id'])
    fetch = raw.get('secondary_fetch') or {}
    book = {'corners_ou': raw.get('odds_corners_ou'), 'corner_hdp': raw.get('odds_corner_ah'),
            'captured_at': {key: data.get('captured_at') for key, data in fetch.get('markets', {}).items()}}
    result = scanner['secondary_analysis'](info, cache, book=book)
    match = {'info': info, 'analysis': {'secondary_markets': result}}
    picks = scanner['publish_secondary_picks'](match, time.time())
    return {'info': info, 'fetch': fetch, 'analysis': result, 'picks': picks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--match-id', type=int)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--window-hours', type=float, default=24)
    parser.add_argument('--output', help='Optional separate audit artifact (never the live scan output)')
    args = parser.parse_args()
    if args.limit < 1 or not 0 < args.window_hours <= 168:
        parser.error('limit >= 1 and window-hours in (0,168] required')
    scanner = runpy.run_path(str(ROOT/'scripts/fc-scan-live.py'))
    cache, results = {}, []
    fixtures = ([provider.get_match(args.match_id)] if args.match_id else
                provider.list_matches_paginated(window_hours=args.window_hours, max_pages=3))
    supported = 0
    for fixture in fixtures:
        info = provider.extract_markets(fixture)
        preliminary = scanner['secondary_analysis'](info, cache)
        if preliminary.get('availability') != 'B' and not args.match_id:
            continue
        supported += 1
        if len(results) < args.limit:
            results.append(audit_fixture(info, scanner, cache))
    report = {'read_only': True, 'fixtures_seen': len(fixtures), 'projectable_fixtures': supported,
              'fixtures_audited': len(results), 'results': results}
    encoded = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
    if args.output:
        target = Path(args.output).resolve()
        if not target.is_relative_to(ROOT/'reports'):
            parser.error('Audit output must be inside reports/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding='utf-8')
    print(json.dumps({'read_only': True, 'fixtures_seen': len(fixtures), 'projectable_fixtures': supported,
        'fixtures_audited': len(results), 'results': [
            {'match': f"{r['info']['home']} vs {r['info']['away']}",
             'corners': r['analysis'].get('corners'), 'cards': r['analysis'].get('cards'),
             'fetch': r['fetch'], 'picks': [{'market': p['market'], 'pick': p['pick'],
                 'odds': p['odds'], 'line_source': p['line_source'], 'ev': p['ev']} for p in r['picks']]}
            for r in results]}, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
