#!/usr/bin/env python3
"""P0 offline audit. Reads a snapshot; never writes a ledger or calls a feed."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.markets import settle_score
from football_formula_engine.value import expected_value
from football_formula_engine.reliability import reliability_report


def audit(snapshot):
    rows = [r for bucket in ('settled', 'overdue', 'locked', 'live') for r in snapshot.get(bucket, [])
            if r.get('market') != 'parlay' and r.get('settlement_kind') != 'parlay']
    unique = {}
    for row in rows:
        key = (row.get('source_match_id') or (row.get('home'), row.get('away'), row.get('start_ts')),
               row.get('market'), row.get('pick'))
        unique.setdefault(key, row)
    ledger, mismatches, invalid = [], [], []
    for row in unique.values():
        if not row.get('settled') or row.get('home_score') is None or row.get('away_score') is None:
            continue
        try:
            market, label = row['market'].lower(), row['pick'].lower()
            side = ('over' if 'over' in label else 'under') if market == 'ou' else (
                'home' if 'home' in label else 'away') if market == 'ah' else (
                'yes' if 'yes' in label else 'no') if market == 'btts' else label.split(' ', 1)[0]
            line = re.search(r'([+-]?\d+(?:\.\d+)?)$', label) if market in ('ah', 'ou') else None
            q = float(line.group(1)) * 4 if line else None
            if market in ('ah', 'ou') and (q is None or q != int(q)):
                raise ValueError('Invalid quarter line')
            payout = settle_score(market, side, int(q) if q is not None else None,
                                  row['home_score'], row['away_score'])
            profit = expected_value(payout, row['odds'])
            if row.get('profit') is None or abs(profit - row['profit']) > 0.011:
                mismatches.append(row['id'])
                continue
            ledger.append({'id': row['id'], 'market': market, 'probability': row.get('probability'),
                           'outcome': int(profit > 0), 'profit': profit, 'result_verified': True})
        except (KeyError, TypeError, ValueError):
            invalid.append(row.get('id'))
    timezone_unknown, after_kickoff = [], []
    for row in unique.values():
        try:
            placed = datetime.fromisoformat(row['placed_at'].replace('Z', '+00:00'))
            if placed.tzinfo is None:
                timezone_unknown.append(row['id'])
                continue
            if placed.timestamp() >= row['start_ts']:
                after_kickoff.append(row['id'])
        except (KeyError, TypeError, ValueError):
            timezone_unknown.append(row.get('id'))
    line_types = Counter()
    for row in unique.values():
        if row.get('market') in ('ah', 'ou'):
            match = re.search(r'([+-]?\d+(?:\.\d+)?)$', row.get('pick', ''))
            if match:
                q = float(match.group(1)) * 4
                line_types['quarter' if q.is_integer() and int(q) % 2 else 'whole_half'] += 1
    overdue = sum(r.get('timing_status', r.get('settlement_status')) == 'overdue' for r in unique.values())
    return {'input_count': len(rows), 'unique_count': len(unique), 'duplicates': len(rows) - len(unique),
            'overdue': overdue, 'overdue_pct': 100 * overdue / len(unique) if unique else None,
            'ledger_cohort_provisional': reliability_report(ledger),
            'by_market_provisional': {m: reliability_report([r for r in ledger if r['market'] == m])
                                      for m in sorted({r['market'] for r in ledger})},
            'independently_verified_cohort': reliability_report([]),
            'settlement_profit_mismatch_ids': mismatches, 'invalid_score_ids': invalid,
            'placed_at_timezone_unknown_ids': timezone_unknown,
            'confirmed_post_kickoff_ids': after_kickoff,
            'missing_quote_timestamp': sum(not r.get('quote_captured_at') for r in unique.values()),
            'missing_formula_version': sum(not r.get('formula_version') for r in unique.values()),
            'line_types': dict(line_types),
            'limitations': ['Ledger score consistency is not independent fixture-result verification.',
                           'Legacy probability semantics and model version are not proven.',
                           'Do not treat the selected settled subset as representative of overdue picks.',
                           'No authenticated manual confirmations were supplied.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'betting-machine-fc/tracker_snapshot.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.snapshot.read_bytes()
    report = audit(json.loads(raw))
    report['source_sha256'] = hashlib.sha256(raw).hexdigest()
    report['source_path'] = str(args.snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
