"""Validate odds-movement signals on graded live projections.

Joins betting-machine-fc/projection_ledger.jsonl with projection_grades.jsonl
by ledger_id and reports, per movement_signal (and per pick class), the
number of graded picks, hit rate (half win counts as win, push excluded) and
flat-stake ROI at the logged 1xbit price. Run it after a few weeks of scans
with the Pinnacle reference active; a signal earns a role in pick gating only
if it beats 'flat' consistently with enough picks.

    python scripts/fc-movement-report.py [--min-n 30] [--json]
"""
import argparse
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC = os.path.join(ROOT, 'betting-machine-fc')
PAYOUT = {'win': 1.0, 'half_win': 0.5, 'push': 0.0, 'half_loss': -0.5, 'loss': -1.0}


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def profit(outcome, odds):
    if outcome in ('win', 'half_win'):
        return (odds - 1) * PAYOUT[outcome]
    return PAYOUT[outcome]


def report(ledger, grades, min_n=30):
    entries = {row['ledger_id']: row for row in ledger if row.get('ledger_id')}
    buckets = defaultdict(lambda: {'n': 0, 'decisive': 0, 'wins': 0, 'profit': 0.0})
    for grade in {g['ledger_id']: g for g in grades if g.get('ledger_id')}.values():
        entry = entries.get(grade['ledger_id'])
        outcome = grade.get('outcome')
        if not entry or outcome not in PAYOUT or not entry.get('odds'):
            continue
        signal = entry.get('movement_signal') or 'not_logged'
        for key in (('all', signal), (entry.get('pick_class') or 'unknown', signal)):
            b = buckets[key]
            b['n'] += 1
            b['profit'] += profit(outcome, float(entry['odds']))
            if outcome != 'push':
                b['decisive'] += 1
                b['wins'] += outcome in ('win', 'half_win')
    rows = []
    for (cohort, signal), b in sorted(buckets.items()):
        rows.append({'cohort': cohort, 'signal': signal, 'n': b['n'],
                     'hit_rate': round(b['wins'] / b['decisive'], 4) if b['decisive'] else None,
                     'roi': round(b['profit'] / b['n'], 4) if b['n'] else None,
                     'enough_data': b['n'] >= min_n})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--min-n', type=int, default=30)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    rows = report(read_jsonl(os.path.join(FC, 'projection_ledger.jsonl')),
                  read_jsonl(os.path.join(FC, 'projection_grades.jsonl')), args.min_n)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'cohort':18s} {'signal':15s} {'n':>6s} {'hit':>7s} {'roi':>8s}")
    for r in rows:
        hit = f"{100 * r['hit_rate']:.1f}%" if r['hit_rate'] is not None else '-'
        roi = f"{100 * r['roi']:+.1f}%" if r['roi'] is not None else '-'
        flag = '' if r['enough_data'] else '  (sedikit data)'
        print(f"{r['cohort']:18s} {r['signal']:15s} {r['n']:6d} {hit:>7s} {roi:>8s}{flag}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
