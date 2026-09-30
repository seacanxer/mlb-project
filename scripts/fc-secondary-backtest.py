#!/usr/bin/env python3
"""Walk-forward, no-leakage descriptive backtest for corner/card projections."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.secondary_markets import load_stat_rows, project_fixture


def _metrics(records):
    if not records:
        return {'n': 0, 'brier': None, 'log_loss': None, 'observed_positive_rate': None,
                'mean_predicted': None, 'calibration_gap': None,
                'baseline_brier': None, 'model_brier_improvement': None, 'roi': None}
    outcomes = [record['outcome'] for record in records]
    predictions = [record['probability'] for record in records]
    eps = 1e-15
    brier = sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(records)
    log_loss = -sum(y * math.log(min(1 - eps, max(eps, p)))
                    + (1 - y) * math.log(min(1 - eps, max(eps, 1 - p)))
                    for p, y in zip(predictions, outcomes)) / len(records)
    rate = sum(outcomes) / len(records)
    baseline = [record['baseline_probability'] for record in records
                if record.get('baseline_probability') is not None]
    baseline_brier = (sum((p - record['outcome']) ** 2 for p, record in
                          ((record['baseline_probability'], record) for record in records)
                          if p is not None) / len(baseline)) if baseline else None
    return {'n': len(records), 'brier': brier, 'log_loss': log_loss,
            'observed_positive_rate': rate, 'mean_predicted': sum(predictions) / len(predictions),
            'calibration_gap': rate - sum(predictions) / len(predictions),
            'baseline_brier': baseline_brier,
            'model_brier_improvement': baseline_brier - brier if baseline_brier is not None else None,
            'roi': None}


def _outcome(row, market, pick):
    if market == 'corners_ou':
        if row['home_corners'] is None or row['away_corners'] is None:
            return None
        actual = row['home_corners'] + row['away_corners']
        return int(actual > pick['line'] if pick['side'] == 'over' else actual < pick['line'])
    if market == 'cards_ou':
        if any(row.get(key) is None for key in ('home_yellow', 'away_yellow', 'home_red', 'away_red')):
            return None
        actual = row['home_yellow'] + row['away_yellow'] + 2 * (row['home_red'] + row['away_red'])
        return int(actual > pick['line'] if pick['side'] == 'over' else actual < pick['line'])
    if market == 'team_cards_ou':
        side = pick['team']
        if row.get(f'{side}_yellow') is None or row.get(f'{side}_red') is None:
            return None
        actual = row[f'{side}_yellow'] + 2 * row[f'{side}_red']
        return int(actual > pick['line'] if pick['side'] == 'over' else actual < pick['line'])
    if row['home_corners'] is None or row['away_corners'] is None:
        return None
    diff = row['home_corners'] - row['away_corners']
    margin = diff + pick['line'] if pick['side'] == 'home' else -diff + pick['line']
    return int(margin > 0)


def _baseline(rows, target, market, pick):
    prior = [row for row in rows if row['date'] < target['date']]
    outcomes = [result for row in prior if (result := _outcome(row, market, pick)) is not None]
    return (sum(outcomes) + 1) / (len(outcomes) + 2) if outcomes else None


def backtest(rows):
    records = {'corners_ou': [], 'corner_hdp': [], 'cards_ou': [], 'team_cards_ou': []}
    skipped = {'insufficient_prior_stats': 0, 'missing_target_stats': 0}
    for target in rows:
        if any(target.get(key) is None for key in ('home_goals', 'away_goals')):
            skipped['missing_target_stats'] += 1
            continue
        kickoff = int(__import__('datetime').datetime.combine(
            target['date'], __import__('datetime').time.min,
            tzinfo=__import__('datetime').timezone.utc).timestamp())
        projection = project_fixture(rows, target['home'], target['away'], kickoff)
        if projection['availability'] == 'C':
            skipped['insufficient_prior_stats'] += 1
            continue
        for pick in projection['markets']:
            market = pick['market']
            if market not in records:
                continue
            outcome = _outcome(target, market, pick)
            if outcome is None:
                continue
            probability = pick['probability']
            records[market].append({'probability': probability, 'outcome': outcome,
                                    'baseline_probability': _baseline(rows, target, market, pick)})
    return {'mode': 'walk_forward_pre_kickoff', 'model_version': 'fc-secondary-counts-v1',
            'rows': len(rows), 'skipped': skipped,
            'by_market': {market: _metrics(values) for market, values in records.items()},
            'roi_claim': 'unavailable_no_historical_secondary_market_odds'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, nargs='+')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    report = backtest(load_stat_rows(args.csv))
    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding='utf-8')
    print(rendered)
