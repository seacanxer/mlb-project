"""Read-only, temporal audit of immutable projection ledger and supplied grades."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'betting-machine-fc'))
from football_formula_engine.markets import settle_score
from football_formula_engine.markets import PayoutProbabilities
from football_formula_engine.market_safety import anchor_payout, MODEL_WEIGHTS, MAX_MODEL_MARKET_GAP
from football_formula_engine.value import expected_value, proportional_no_vig

grader = runpy.run_path(str(ROOT/'scripts/fc-grade-projections.py'))
audit_ns = runpy.run_path(str(ROOT/'scripts/fc-quality-audit.py'))


def timestamp(value):
    try:
        if isinstance(value, (int,float)):
            return float(value)
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError, TypeError):
        return None


def audit(entries, grades):
    grade_by_id = {g['ledger_id']: g for g in grades}
    legacy_by_id = {e['ledger_id']:e for e in entries}
    legacy_csv = {}
    for g in grades:
        e = legacy_by_id.get(g['ledger_id'],{})
        market = g.get('market') or e.get('market')
        key = (g.get('match') or e.get('match') or '',market)
        p = g.get('model_probability',e.get('probability')) or 0
        if market not in ('1x2','ah','ou','btts'):
            continue
        prior = legacy_csv.get(key)
        if prior is None or p > prior[0]:
            legacy_csv[key] = (p,e,g)
    legacy_rows = []
    for probability,e,g in legacy_csv.values():
        actual = g.get('actual') or {}
        try:
            payout = settle_score(e['market'],e['side'],e.get('line_quarters'),actual['home_goals'],actual['away_goals'])
            legacy_rows.append({**e,'kickoff_ts':e['start_ts'],'model_probability':probability,
                'outcome':grader['payout_label'](payout)[0], '_profit':expected_value(payout,float(e['odds']))})
        except (KeyError,TypeError,ValueError):
            pass
    legacy_binary = [r for r in legacy_rows if r['market'] in ('1x2','btts')]
    # Rebuild no-vig ONLY from complementary sides of the exact same captured
    # quote. A single inverse price must not masquerade as a market benchmark.
    books = defaultdict(dict)
    for e in entries:
        if e.get('market') not in ('1x2','btts') or timestamp(e.get('quote_captured_at')) is None:
            continue
        key = (e.get('match_id'),e['market'],timestamp(e['quote_captured_at']))
        if e.get('odds') is not None:
            books[key][e.get('side')] = e['odds']
    selected = {}
    for e in entries:
        if not grader['is_card_row'](e):
            continue
        key = (grader['report_fixture_key'](e),e['market'])
        if key not in selected or grader['first_seen_key'](e) < grader['first_seen_key'](selected[key]):
            selected[key] = e
    rows, missing, mismatches, ev_mismatches = [], 0, [], []
    for e in selected.values():
        g = grade_by_id.get(e['ledger_id'])
        if not g or e['market'] not in ('1x2','ah','ou','btts'):
            continue
        actual = g.get('actual') or {}
        try:
            payout = settle_score(e['market'],e['side'],e.get('line_quarters'),actual['home_goals'],actual['away_goals'])
            outcome = grader['payout_label'](payout)[0]
            if outcome != g['outcome']:
                mismatches.append({'ledger_id':e['ledger_id'], 'reported':g['outcome'], 'actual':outcome})
                continue
            first_seen, capture = timestamp(e.get('first_seen_at')), timestamp(e.get('quote_captured_at'))
            row = {**e, 'kickoff_ts':e['start_ts'], 'outcome':outcome,
                   'model_probability':e['probability'], '_profit':expected_value(payout,float(e['odds'])),
                   '_prospective':first_seen is not None and capture is not None and first_seen<e['start_ts'] and capture<e['start_ts']}
            row['_result_available_at'] = max(timestamp(g.get('graded_at')) or float('inf'), e['start_ts']+6300)
            sides = ('home','draw','away') if e['market']=='1x2' else ('yes','no')
            complete = books.get((e.get('match_id'),e['market'],capture),{})
            if e['market'] in ('1x2','btts') and all(s in complete for s in sides):
                row['_market_probability'] = proportional_no_vig([complete[s] for s in sides])[sides.index(e['side'])]
            rows.append(row)
            if e['market'] in ('1x2','btts') and e.get('ev') is not None and abs(e['probability']*e['odds']-1-e['ev'])>.002:
                ev_mismatches.append(e['ledger_id'])
        except (KeyError,TypeError,ValueError):
            missing += 1
    metrics = audit_ns['metrics']
    markets = sorted({r['market'] for r in rows})
    prospective = [r for r in rows if r['_prospective']]
    def cohort(group):
        return {'overall':metrics(group), 'by_market':{m:metrics([r for r in group if r['market']==m]) for m in markets}}
    benchmark = [r for r in prospective if '_market_probability' in r]
    benchmark_stats = {}
    walk_forward = {}
    safety_replay = {}
    for market in ('1x2','btts'):
        group = [r for r in benchmark if r['market']==market]
        benchmark_stats[market] = {'n':len(group),
            'model_brier':sum((r['probability']-int(r['outcome']=='win'))**2 for r in group)/len(group) if group else None,
            'market_brier':sum((r['_market_probability']-int(r['outcome']=='win'))**2 for r in group)/len(group) if group else None}
        replay, held = [], Counter()
        for r in group:
            raw = r.get('raw_probability') if r.get('raw_probability') is not None else r['probability']
            adjusted, raw_price = anchor_payout(PayoutProbabilities(full_win=raw,full_loss=1-raw),
                                               r['_market_probability'], MODEL_WEIGHTS.get(market,1))
            ev = expected_value(adjusted,r['odds'])
            if market=='1x2' and r['odds']<1.3:
                held['low_odds'] += 1
            elif abs(raw_price-r['_market_probability'])>MAX_MODEL_MARKET_GAP:
                held['model_market_gap'] += 1
            elif ev-.02<0:
                held['nonpositive_conservative_ev'] += 1
            else:
                replay.append({**r,'model_probability':adjusted.full_win})
        safety_replay[market] = {'input_n':len(group),'held':dict(held),
                                'kept_metrics':metrics(replay), 'baseline_metrics':metrics(group)}
        folds = []
        for test in sorted(group,key=lambda r:timestamp(r['first_seen_at'])):
            training = [r for r in group if r['_result_available_at'] < timestamp(test['first_seen_at'])]
            if len(training)<30:
                continue
            weights = (0,.25,.5,.75,1)
            def loss(w):
                return sum((w*r['probability']+(1-w)*r['_market_probability']-int(r['outcome']=='win'))**2 for r in training)/len(training)
            weight = min(weights,key=lambda w:(loss(w),w))
            predicted = weight*test['probability']+(1-weight)*test['_market_probability']
            y = int(test['outcome']=='win')
            folds.append({'weight':weight,'model_loss':(test['probability']-y)**2,'anchored_loss':(predicted-y)**2})
        walk_forward[market] = {'eligible_complete_quote_rows':len(group),'oos_n':len(folds),
            'weights_used':dict(Counter(str(f['weight']) for f in folds)),
            'raw_brier':sum(f['model_loss'] for f in folds)/len(folds) if folds else None,
            'anchored_brier':sum(f['anchored_loss'] for f in folds)/len(folds) if folds else None,
            'deploy_fitted_weights':False,
            'reason':'Insufficient independent out-of-sample sample; fixed safety weights remain unvalidated.'}
    buckets = []
    for i in range(10):
        group = [r for r in rows if min(int(r['model_probability']*10),9)==i]
        if group:
            buckets.append({'lower':i/10,'upper':(i+1)/10,**metrics(group)})
    return {'input_entries':len(entries),'input_grades':len(grades),'input_source_counts':dict(Counter(e.get('source') for e in entries)),
            'unique_card_entries':len(selected), 'scored_card_rows':len(rows),'unscored_or_secondary':missing,
            'post_kickoff_or_missing_timing':len(rows)-len(prospective),
            'grading_mismatches':mismatches,'binary_ev_formula_mismatches':ev_mismatches,
            'legacy_csv_highest_probability_all_sources':audit_ns['metrics'](legacy_rows),
            'legacy_csv_binary_only':{**audit_ns['metrics'](legacy_binary),
                'inverse_single_odds_brier':sum((1/r['odds']-int(r['outcome']=='win'))**2 for r in legacy_binary)/len(legacy_binary) if legacy_binary else None,
                'benchmark_note':'Inverse single odds includes bookmaker margin; not a no-vig market benchmark.'},
            'legacy_csv_by_market':{m:audit_ns['metrics']([r for r in legacy_rows if r['market']==m]) for m in ('1x2','ah','ou','btts')},
            'prospective_complete_quote_benchmark':benchmark_stats,
            'walk_forward_weight_experiment':walk_forward,
            'fixed_safety_policy_binary_replay':safety_replay,
            'all_confirmed':cohort(rows),'prospective_timestamps_only':cohort(prospective),
            'calibration_buckets':buckets,
            'ev_filters':{str(t):metrics([r for r in rows if r.get('ev') is not None and r['ev']>=t]) for t in (0,.03,.05,.1)},
            'negative_ev_count':sum(r.get('ev') is not None and r['ev']<0 for r in rows),
            'prospective_positive_ev_screen_only':metrics([r for r in prospective if r.get('ev') is not None and r['ev']>=.02
                and (r['market']!='1x2' or r['odds']>=1.3)]),
            'by_version':{v:metrics([r for r in rows if r.get('formula_version')==v]) for v in sorted({r.get('formula_version') or 'unknown' for r in rows})},
            'limitations':['Scores checked against supplied actuals, not independent provider refetch.',
                           'Prospective timestamps do not establish historical training cutoff or closing-line value.',
                           'After-event logged rows are not out-of-sample validation.',
                           'Binary safety replay retains historical side and line; not a new full scan or independently validated model backtest.',
                           'Flat 1u paper ROI does not modify or replace tracker ROI.']}, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--grades',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'reports/fc-ledger-quality-audit-2026-10-09.json')
    args = parser.parse_args()
    entries = grader['load_jsonl'](str(args.ledger))
    grades = grader['load_jsonl'](str(args.grades))
    report, _ = audit(entries,grades)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('input_entries','input_grades','scored_card_rows','post_kickoff_or_missing_timing','grading_mismatches','binary_ev_formula_mismatches','all_confirmed','prospective_timestamps_only')},indent=2))


if __name__ == '__main__':
    main()
