"""Verify local graded forecast detail without touching settlement or staking."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.markets import settle_score
from football_formula_engine.value import expected_value

LABELS = {'full_win': 'win', 'half_win': 'half_win', 'push': 'push',
          'half_loss': 'half_loss', 'full_loss': 'loss'}


def metrics(rows):
    if not rows:
        return {'n': 0}
    profits = [row['_profit'] for row in rows]
    y = [int(row['outcome'] in ('win', 'half_win')) for row in rows]
    p = [float(row['model_probability']) for row in rows]
    decided = sum(row['outcome'] != 'push' for row in rows)
    fixtures = defaultdict(list)
    for row in rows:
        fixtures[(row.get('match'), row.get('kickoff_ts'))].append(row['_profit'])
    sums = np.array([sum(values) for values in fixtures.values()])
    counts = np.array([len(values) for values in fixtures.values()])
    rng = np.random.default_rng(20261009)
    resamples = rng.integers(0, len(sums), size=(5000, len(sums)))
    ci = np.percentile(100 * sums[resamples].sum(axis=1) / counts[resamples].sum(axis=1), [2.5, 97.5]) if len(sums)>=5 else None
    return {'n': len(rows), 'fixtures': len(fixtures), 'profit_units': sum(profits),
            'paper_roi_pct': 100 * sum(profits) / len(rows),
            'roi_fixture_bootstrap_95_pct': ci.tolist() if ci is not None else None,
            'hit_rate': sum(y) / decided if decided else None,
            'positive_payout_rate': sum(y) / len(rows),
            'brier': sum((a-b)**2 for a, b in zip(p, y)) / len(rows),
            'log_loss': sum(-b*math.log(max(1e-12,a))-(1-b)*math.log(max(1e-12,1-a)) for a,b in zip(p,y))/len(rows),
            'mean_predicted': sum(p) / len(rows),
            'calibration_gap': (sum(y)-sum(p)) / len(rows)}


def audit(report, summary=None):
    verified, mismatches, excluded = [], [], []
    for raw in report.get('recent') or []:
        row = dict(raw)
        try:
            line = row.get('line')
            lq = None if line is None else int(round(float(line)*4))
            if line is not None and abs(float(line)*4-lq) > 1e-8:
                raise ValueError('Invalid quarter line')
            payout = settle_score(row['market'], row['side'], lq,
                                  row['home_goals'], row['away_goals'])
            actual = next(label for key, label in LABELS.items() if getattr(payout,key) == 1)
            if actual != row['outcome']:
                mismatches.append({'match': row['match'], 'market': row['market'],
                                   'reported': row['outcome'], 'recomputed': actual})
                continue
            row['_profit'] = expected_value(payout, float(row['odds']))
            if not 0 <= float(row['model_probability']) <= 1:
                raise ValueError('Invalid probability')
            verified.append(row)
        except (ValueError, TypeError, KeyError, StopIteration) as exc:
            excluded.append({'match': row.get('match'), 'reason': str(exc)})
    as_reported = metrics(verified)
    unique = {}
    for row in verified:
        unique.setdefault((row.get('match'), row.get('kickoff_ts'), row['market']), row)
    duplicates_removed = len(verified)-len(unique)
    verified = list(unique.values())
    markets = sorted({row['market'] for row in verified})
    buckets = []
    for index in range(10):
        group = [row for row in verified if min(int(row['model_probability']*10),9) == index]
        if group:
            buckets.append({'lower': index/10, 'upper': (index+1)/10, **metrics(group)})
    result = {'scope': 'available recent local detail; flat 1u paper returns, not locked-pick ROI',
              'report_generated_at': report.get('generated_at'),
              'report_total_graded': report.get('graded'), 'available_detail': len(report.get('recent') or []),
              'grading_mismatches': mismatches, 'excluded': excluded,
              'full_ledger_available': (ROOT/'betting-machine-fc/projection_ledger.jsonl').exists(),
              'full_grades_available': (ROOT/'betting-machine-fc/projection_grades.jsonl').exists(),
              'duplicates_removed_in_detail': duplicates_removed,
              'detail_dedup_policy': 'first occurrence in exported detail; original first_seen unavailable',
              'as_reported_detail': as_reported,
              'overall': metrics(verified),
              'by_market': {market: metrics([r for r in verified if r['market']==market]) for market in markets},
              'buckets': buckets,
              'ev_filters': {str(t): metrics([r for r in verified if r.get('ev') is not None and r['ev']>=t]) for t in (0,.03,.05,.1)},
              'low_1x2_odds': metrics([r for r in verified if r['market']=='1x2' and r['odds']<1.3]),
              'negative_ev_count': sum(r.get('ev') is not None and r['ev']<0 for r in verified),
              'limitations': ['Grades checked against stored FT scores, not independently fetched result evidence.',
                             'Full report ROI, HTML confidence intervals and full-cohort buckets cannot be reconstructed from 100 detail rows.',
                             'Only one side price stored; inverse odds is not a verified no-vig market benchmark.',
                             'No weight fitting or accuracy claim from these small selected cohorts.']}
    if summary:
        result['html_claims'] = {key: summary[key] for key in ('tot','brier','mk')}
        result['html_local_count_difference'] = report['graded']-summary['tot']['n']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--report', type=Path, default=ROOT/'reports/fc-model-performance.json')
    parser.add_argument('--out', type=Path, default=ROOT/'reports/fc-quality-audit-2026-10-09.json')
    args = parser.parse_args()
    summary = None
    if args.html:
        match = re.search(r'const D=(\{.*?\});', args.html.read_text(encoding='utf-8'), re.S)
        summary = json.loads(match.group(1)) if match else None
    result = audit(json.loads(args.report.read_text(encoding='utf-8')), summary)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('available_detail','grading_mismatches','overall','by_market','negative_ev_count','low_1x2_odds')}, indent=2))


if __name__ == '__main__':
    main()
