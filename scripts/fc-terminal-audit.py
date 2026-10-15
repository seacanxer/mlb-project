#!/usr/bin/env python3
"""Offline phase-1 terminal/quant audit. Never fetches, scans, locks or settles.

Reads committed snapshots and runs synthetic probes in a disposable database.
Only --out and the temporary database under its parent are written.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FC = ROOT / 'betting-machine-fc'
sys.path.insert(0, str(FC))
from football_formula_engine.live_quotes import QuoteJournal
from football_formula_engine.markets import PayoutProbabilities, settle_score
from football_formula_engine.score_matrix import build_score_matrix
from football_formula_engine.sharp_reference import fair_probabilities, latest_reference_quotes, reference_gate_reasons
from football_formula_engine.value import expected_value


def load(path):
    raw = path.read_bytes()
    return json.loads(raw), {'path': path.relative_to(ROOT).as_posix(),
                             'sha256': hashlib.sha256(raw).hexdigest()}


def probe(directory):
    now = 1_900_000_000
    info = {'match_id': 'audit-synthetic', 'home': 'Home', 'away': 'Away',
            'league': 'Audit', 'start_ts': now + 86400}
    with tempfile.TemporaryDirectory(prefix='fc-audit-', dir=directory) as temp:
        journal = QuoteJournal(Path(temp) / 'quotes.db')
        obs = journal.record(info, {'odds_1x2': {1: 2.0, 2: 4.0, 3: 4.0},
                                   'odds_ou': {'2.5': {'9': 2.0, '10': 2.0}}}, {},
                             captured_at=now-5, source_updated_at=now-3600,
                             bookmaker='pinnacle', provider='audit')
        quotes = latest_reference_quotes(journal.as_of(info['match_id'], now,
                                         max_age_seconds=900), 'pinnacle')
        fair = fair_probabilities(quotes)
        ev = expected_value(PayoutProbabilities(full_win=fair[('1x2', 'home', None)],
                            full_loss=1-fair[('1x2', 'home', None)]), 2.1)
        first = {'market': '1x2', 'side': 'home', 'line_quarters': None, 'decimal_odds': 2.0}
        second = {'market': 'ou', 'side': 'over', 'line_quarters': 10, 'decimal_odds': 2.0}
        one = journal.record_research_decision(obs['artifact_id'], first,
                    decision_at=now, policy_id='audit', model={})
        two = journal.record_research_decision(obs['artifact_id'], second,
                    decision_at=now, policy_id='audit', model={})
    dist = build_score_matrix(1.5, 1.1)
    home = away = joint = 0.0
    for h, a, probability in dist.cells():
        x = settle_score('1x2', 'home', None, h, a).full_win
        y = settle_score('ah', 'away', -2, h, a).full_win
        home += probability*x
        away += probability*y
        joint += probability*x*y
    payout = PayoutProbabilities(full_win=.4, half_win=.2, push=.1, half_loss=.1, full_loss=.2)
    return {
        'stale_reference': {'captured_age_seconds': 5, 'source_age_seconds': 3600,
                            'configured_max_age_seconds': 900,
                            'accepted_contracts': len(fair), 'ev_at_2_1': ev,
                            'gate_reasons': reference_gate_reasons(2.1, ev)},
        'research_identity': {'second_contract_requested': second, 'second_contract_returned': two['contract'],
                              'same_artifact_id': one['artifact_id'] == two['artifact_id']},
        'same_match_parlay': {'legs': ['Home 1X2', 'Away -0.5 AH'],
                             'independence_product': home*away, 'score_matrix_joint': joint,
                             'note': 'Synthetic contradiction; no ticket was locked.'},
        'split_line_ev': {'payout': payout.__dict__, 'odds': 2.0,
                          'positive_payout_probability': .6,
                          'payout_aware_ev': expected_value(payout, 2.0),
                          'binary_shortcut_ev': .6*2.0-1},
    }


def audit(out):
    matches, match_source = load(FC / 'matches_detailed.json')
    performance, performance_source = load(ROOT / 'reports/fc-model-performance.json')
    tracker, tracker_source = load(FC / 'tracker_snapshot.json')
    config, config_source = load(FC / 'config.json')
    diagnostics = config.get('last_scan_diagnostics') or {}
    reference = diagnostics.get('sharp_reference') or {}
    primary = [p for m in matches for p in m.get('projections', [])
               if p.get('market') in ('1x2', 'ah', 'ou', 'btts')]
    top = [p for p in primary if (p.get('odds') or 0) >= 1.4 and
           (p.get('confidence_tier') == 'TINGGI' or (p.get('confidence') or 0) >= .65)]
    value = [p for m in matches for p in m.get('qualified_picks', [])]
    low_1x2 = [p for p in primary if p['market'] == '1x2' and 1 < (p.get('odds') or 0) < 1.3]
    mismatch, naive_errors, confidence_diffs = [], [], []
    for p in primary:
        if p.get('payout') and p.get('odds'):
            actual = expected_value(PayoutProbabilities(**p['payout']), p['odds'])
            if abs(actual - p['ev']) > .000051:
                mismatch.append({'match_id': p.get('match_id'), 'market': p['market'], 'stored': p['ev'], 'actual': actual})
            if p['market'] in ('ah', 'ou'):
                naive_errors.append(abs(p['probability']*p['odds']-1-actual))
        if p.get('confidence') is not None and p.get('probability') is not None:
            confidence_diffs.append(abs(p['confidence']-p['probability']))
    logger = runpy.run_path(str(ROOT / 'scripts/fc-log-projections.py'))
    logged = logger['collect_rows'](matches, '2026-10-15T00:00:00+00:00')
    logs_low = [p for p in logged if p['market'] == '1x2' and 1 < (p.get('odds') or 0) < 1.3]
    ids = {}
    for p in value:
        identity = p.get('research_decision_id')
        if identity:
            ids.setdefault(identity, set()).add((p.get('match_id'), p.get('market'), p.get('pick')))
    full_local_ledgers = {name: (FC / name).exists() for name in ('projection_ledger.jsonl', 'projection_grades.jsonl')}
    result = {
        'audit_version': 'fc-terminal-phase1-v1', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'sources': [match_source, performance_source, tracker_source, config_source],
        'scope': 'Offline committed snapshots, not a live deployment or prospective validation.',
        'snapshot': {
            'fixtures': len(matches), 'lanes': dict(Counter((m.get('analysis') or {}).get('lane', 'unknown') for m in matches)),
            'primary_projections': len(primary), 'qualified_picks': len(value),
            'confidence_sources': dict(Counter(p.get('confidence_source', 'unknown') for p in primary)),
            'top_confidence_odds_1_4': len(top), 'top_ev_nonpositive': sum(p.get('ev', 0) <= 0 for p in top),
            'top_not_value': sum(not p.get('is_value') for p in top),
            'top_ev_range': [min((p['ev'] for p in top), default=None), max((p['ev'] for p in top), default=None)],
            'low_odds_1x2_displayable': len(low_1x2), 'low_odds_1x2_logged': len(logs_low),
            'confidence_probability_gap_gt_1pp': sum(d > .01 for d in confidence_diffs),
            'confidence_probability_max_gap': max(confidence_diffs, default=0),
            'payout_ev_mismatches': mismatch, 'binary_ev_max_absolute_error_asian': max(naive_errors, default=0),
            'shared_research_ids_different_contracts': sum(len(v) > 1 for v in ids.values()),
            'projection_quote_timestamp_range': [min((p.get('quote_captured_at') or 0 for p in primary), default=0),
                                                 max((p.get('quote_captured_at') or 0 for p in primary), default=0)],
        },
        'scan_diagnostics': {
            'coverage': diagnostics.get('coverage'), 'skipped': diagnostics.get('skipped'),
            'sharp_reference': {
                'status': reference.get('status'), 'fixtures_priced': reference.get('fixtures_priced'),
                'leagues': {key: {field: value.get(field) for field in ('status','error_type','fixtures')}
                            for key, value in (reference.get('leagues') or {}).items()},
            },
        },
        'performance': {k: performance.get(k) for k in ('generated_at','ledger_entries','graded','pending','unique_fixtures','overall','by_market')},
        'available_recent_details': len(performance.get('recent', [])),
        'full_local_ledgers': full_local_ledgers,
        'tracker': {k: tracker.get(k) for k in ('summary','manual_summary','manual_parlay_summary')},
        'synthetic_reproductions': probe(out.parent),
        'limitations': ['No new live feed, independent result verification or retraining.',
                        'Aggregate performance mixes formula versions; it is not a v5 holdout result.',
                        'Pending does not mean overdue. Full ledgers are required to recompute the entire cohort.',
                        'UI findings are source-code audit, not a new browser screenshot review.'],
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = audit(args.out)
    print(json.dumps({'output': str(args.out), 'snapshot': result['snapshot'],
                      'synthetic_reproductions': result['synthetic_reproductions']}, indent=2))
