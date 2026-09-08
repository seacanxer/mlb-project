"""Chronological O/U 2.5 research on local CSVs; never changes live parameters.

    python evaluate_quality.py --output research/quality-evaluation.json
"""
import argparse
import json
import math
from pathlib import Path
from unittest.mock import patch

import prediction
import scraper_historical as historical
import strength_rating as ratings
from main import analyze_match, select_top_picks
from model import devig, over_prob, strength_lam


def metrics(rows, key):
    n = len(rows)
    if not n:
        return {"n": 0}
    return {"n": n, "brier": sum((r[key] - r['y']) ** 2 for r in rows) / n,
            "log_loss": -sum(math.log(max(1e-9, r[key] if r['y'] else 1-r[key])) for r in rows) / n,
            "mean_predicted": sum(r[key] for r in rows) / n,
            "actual_over": sum(r['y'] for r in rows) / n}


def evaluate(path):
    league = path.stem.split('_')[0]
    rows = [historical.normalize(r) for r in historical.load_rows(path)]
    rows = sorted([r for r in rows if ratings.parse_fd_date(r['date']) and r['fthg'] is not None and r['ftag'] is not None], key=lambda r: ratings.parse_fd_date(r['date']))
    records, prior_predictions = [], []
    train_key, trained = None, None
    for r in rows:
        day = ratings.parse_fd_date(r['date'])
        training = [x for x in rows if ratings.parse_fd_date(x['date']) < day]
        if len(training) < 150:
            continue
        if day.strftime('%Y-%m') != train_key:
            trained = ratings.mle_rating(training)
            train_key = day.strftime('%Y-%m')
            training_end = max(ratings.parse_fd_date(x['date']) for x in training)
        teams, avg, adv = trained
        if r['home'] not in teams or r['away'] not in teams:
            continue
        prices = [r[k] for k in ('odds_home', 'odds_draw', 'odds_away', 'odds_over', 'odds_under')]
        if any(p is None or not math.isfinite(p) or p <= 1 for p in prices):
            continue
        home, away = teams[r['home']], teams[r['away']]
        hist_h, hist_a = strength_lam(home['att'], away['def'], away['att'], home['def'], avg, adv)
        market = {'home': r['home'], 'away': r['away'], 'league': league,
                  'start_ts': day.toordinal()*86400, 'odds_1x2': dict(zip((1,2,3), prices[:3])),
                  'odds_ou': {2.5: {9: prices[3], 10: prices[4]}}, 'odds_ah': {}}
        # Same production projection path with strictly prior-only fitted ratings.
        def blend(h, a, l, mh, ma, weight=.35, season=None):
            return mh*(1-weight)+hist_h*weight, ma*(1-weight)+hist_a*weight, 'market+strength'
        with patch.object(prediction, 'hybrid_lams', blend):
            proj = prediction.build_projection(market)
        p = over_prob(2.5, proj['home'], proj['away'])
        baseline = devig({'over': prices[3], 'under': prices[4]})['over']
        past = [x for x in prior_predictions if x['day'] < day.isoformat()]
        beta = 0.0 if len(past) < 50 else min((0,.25,.5,.75,1), key=lambda b: sum((x['market']+b*(x['model']-x['market'])-x['y'])**2 for x in past))
        calibrated = baseline + beta*(p-baseline)
        candidates = analyze_match(market, proj['home'], proj['away'], projection_meta=proj)
        selected = select_top_picks(candidates, per_match=1, limit=1)
        # Reconstruct pre-quality gates on the same candidates, preserving its
        # equivalent-probability interpretation only for half-goal O/U.
        old = [c for c in candidates if 1.64 <= c['odds'] <= 2.75 and .04 <= c['ev'] <= .25]
        old.sort(key=lambda c: min(c['ev']-.02,.15)/.15*80 + max(0,1-abs(c['odds']-1.95)/.65)*20, reverse=True)
        y = int(r['fthg'] + r['ftag'] > 2.5)
        def net(c):
            return c['odds']-1 if (c['pick'].startswith('Over')) == bool(y) else -1
        record = {'day': day.isoformat(), 'training_end': training_end.isoformat(),
                  'market': baseline, 'model': p, 'calibrated_research': calibrated, 'beta': beta, 'y': y,
                  'old_profit': net(old[0]) if old else None,
                  'quality_profit': net(selected[0]) if selected else None}
        assert training_end < day
        records.append(record)
        prior_predictions.append(record)
    stats = {key: metrics(records, key) for key in ('market','model','calibrated_research')}
    for key in ('old_profit','quality_profit'):
        values = [r[key] for r in records if r[key] is not None]
        stats[key] = {'n': len(values), 'profit_units': sum(values), 'roi_pct': 100*sum(values)/len(values) if values else None}
    return {'league': league, 'metrics': stats, 'rows': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--leagues', nargs='+', default=['E0','D1','SP1'])
    args = parser.parse_args()
    base = Path(__file__).parent
    result = {'scope': 'O/U 2.5 only; monthly expanding prior-only training; local 2025/26 CSV prices have no execution timestamps; no live calibration activation', 'leagues': []}
    for league in args.leagues:
        item = evaluate(base / 'data' / f'{league}_2526.csv')
        result['leagues'].append(item)
        print(json.dumps({'league': league, 'metrics': item['metrics']}), flush=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
