#!/usr/bin/env python3
"""Offline replay against an explicit results export; never updates a ledger."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
import scores_flashscore

settle_bet = runpy.run_path(str(ROOT / 'scripts/fc-settle-live.py'))['settle_bet']


def replay(snapshot, results):
    # Complete names/aliases, date disambiguation and period validation apply
    # exactly as in production. An export's provenance must be reviewed separately.
    lookup = {}
    for row in results:
        for h in scores_flashscore.name_keys(row.get('home', '')):
            for a in scores_flashscore.name_keys(row.get('away', '')):
                lookup.setdefault((h, a), []).append(row)
    unique = {}
    for bucket in ('settled', 'overdue', 'locked', 'live'):
        for row in snapshot.get(bucket, []):
            if row.get('market') == 'parlay':
                continue
            key = (row.get('source_match_id') or (row.get('home'), row.get('away'), row.get('start_ts')),
                   row.get('market'), row.get('pick'))
            unique.setdefault(key, row)
    reasons, outcomes = Counter(), []
    for bet in unique.values():
        try:
            kickoff = datetime.fromtimestamp(bet['start_ts'], timezone.utc).date()
            row = scores_flashscore.find_result(bet['home'], bet['away'], lookup, kickoff)
            if row is None:
                reasons['no_unique_fixture_result'] += 1
                continue
            # An offline export must explicitly identify the settled period.
            if row.get('period') != '90min' or str(row.get('status', '')).lower() not in ('ft', 'final'):
                reasons['unverified_90min_final'] += 1
                continue
            hg, ag = row['home_goals'], row['away_goals']
            if not isinstance(hg, int) or not isinstance(ag, int) or min(hg, ag) < 0:
                raise ValueError('Invalid score')
            result = settle_bet(bet['market'], bet['pick'], bet['odds'], hg, ag)
            if result is None:
                raise ValueError('Invalid contract')
            won, profit = result
            outcomes.append({'probability': bet.get('probability'), 'outcome': int(profit > 0),
                             'profit': profit, 'result_verified': True})
        except (KeyError, ValueError, TypeError, OverflowError):
            reasons['invalid_contract_or_fixture'] += 1
    from football_formula_engine.reliability import reliability_report
    return {'mode': 'offline_dry_run', 'historical_singles': len(unique),
            'result_rows': len(results), 'matched': len(outcomes), 'unresolved': sum(reasons.values()),
            'unresolved_pct': 100 * sum(reasons.values()) / len(unique) if unique else None,
            'reasons': dict(reasons), 'performance_export_cohort': reliability_report(outcomes)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = replay(json.loads(args.snapshot.read_text(encoding='utf-8')),
                    json.loads(args.results.read_text(encoding='utf-8')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, allow_nan=False))
