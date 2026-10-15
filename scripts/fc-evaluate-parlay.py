#!/usr/bin/env python3
"""Read-only parlay preview from the current server scan. No DB writes or feeds."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.parlays import evaluate_parlay, resolve_choices, build_value_parlays


def preview(payload, matches_path=None):
    if not isinstance(payload, dict):
        raise ValueError('Invalid portfolio request')
    matches = json.loads(Path(matches_path or os.environ.get('FC_MATCHES_PATH',
        ROOT / 'betting-machine-fc/matches_detailed.json')).read_text(encoding='utf-8'))
    bankroll = os.environ.get('FC_BANKROLL_UNITS')
    bankroll = float(bankroll) if bankroll else None
    if payload.get('mode') == 'build':
        choices = [{'match_id': str(m['info']['match_id']), 'market': p['market'],
                    'pick': p['pick'], 'odds': p['odds']}
                   for m in matches for p in m.get('qualified_picks') or []
                   if (p.get('quant') or {}).get('status') == 'value' and p.get('payout') and p.get('odds')]
        if not choices:
            return {'status': 'ok', 'proposals': [], 'source': 'server_scan', 'official_enabled': False}
        legs, _ = resolve_choices(matches, choices[:200], minimum=1, maximum=200)
        return {'status': 'ok', 'proposals': build_value_parlays(legs, now=time.time(), bankroll_units=bankroll),
                'source': 'server_scan', 'official_enabled': False}
    legs, distributions = resolve_choices(matches, payload.get('choices'))
    return evaluate_parlay(legs, now=time.time(), fixture_distributions=distributions,
                           bankroll_units=bankroll)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(preview(json.loads(args.payload)), allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print(json.dumps({'status': 'blocked', 'eligible': False,
                          'reason_codes': ['PARLAY_RESCAN_OR_VALID_SELECTION_REQUIRED'],
                          'message': 'Perbarui analisis dan pilih kembali 2–8 leg dengan odds yang tersedia.'}))
        raise SystemExit(1)
