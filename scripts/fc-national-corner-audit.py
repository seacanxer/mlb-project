"""Read-only audit of national corner coverage against current bookmaker lines."""
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    scanner = runpy.run_path(str(ROOT / 'scripts/fc-scan-live.py'))
    sc = scanner['sc']
    cache, results = {}, []
    for fixture in sc.list_matches_paginated(window_hours=24, max_pages=6):
        if fixture.get('L') != 'UEFA Nations League':
            continue
        raw = sc.extract_secondary_markets(fixture['I'])
        info = {'match_id': fixture['I'], 'home': fixture['O1'], 'away': fixture['O2'],
                'league': fixture['L'], 'start_ts': fixture['S']}
        book = {'corners_ou': raw.get('odds_corners_ou') or {},
                'corner_hdp': raw.get('odds_corner_ah') or {}}
        analysis = scanner['secondary_analysis'](info, cache, book=book)
        results.append({'info': info, 'analysis': analysis})
        print(info['home'], 'vs', info['away'], analysis['availability'],
              analysis.get('reason'), analysis.get('corners', {}).get('total'))
    day = datetime.now(timezone.utc).date().isoformat()
    path = args.output or ROOT / f'reports/fc-national-corner-coverage-{day}.json'
    path.write_text(json.dumps(results, indent=2, default=str) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
