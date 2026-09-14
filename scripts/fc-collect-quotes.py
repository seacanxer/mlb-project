"""Bounded quote-only collection; safe to schedule separately from model fitting."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

FC_DIR = Path(__file__).resolve().parents[1] / 'betting-machine-fc'
sys.path.insert(0, str(FC_DIR))
import scraper_1xbit as source
from football_formula_engine.live_quotes import QuoteJournal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-id')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--db', type=Path, default=Path(os.environ.get('FC_QUOTES_DB', FC_DIR / 'live_quotes.db')))
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    journal = QuoteJournal(args.db)
    try:
        ids = [args.fixture_id] if args.fixture_id else [v['I'] for v in source.list_matches()
                  if time.time() < float(v.get('S') or 0) <= time.time() + 86400][:args.limit]
    except Exception as exc:
        print(json.dumps({'status': 'FETCH_FAILED', 'error_type': type(exc).__name__}))
        return 1
    outcomes = []
    for fixture_id in ids:
        try:
            raw = source.get_match(fixture_id)
            captured = time.time()
            if str(raw.get('I')) != str(fixture_id):
                raise ValueError('Fixture mismatch')
            info = {'match_id': str(fixture_id), 'start_ts': raw['S'], 'home': raw['O1'],
                    'away': raw['O2'], 'league': raw['L'], 'source': '1xbit'}
            obs = journal.record(info, source.extract_markets(raw), raw, captured_at=captured)
            outcomes.append({'fixture_id': str(fixture_id), 'status': 'captured',
                             'observation_id': obs['artifact_id'], 'quotes': len(obs['quotes'])})
        except Exception as exc:
            outcomes.append({'fixture_id': str(fixture_id), 'status': 'failed',
                             'error_type': type(exc).__name__})
    print(json.dumps({'status': 'complete' if outcomes else 'NO_FIXTURES', 'outcomes': outcomes,
                      'official_enabled': False}))
    return 1 if any(row['status'] == 'failed' for row in outcomes) else 0


if __name__ == '__main__':
    raise SystemExit(main())
