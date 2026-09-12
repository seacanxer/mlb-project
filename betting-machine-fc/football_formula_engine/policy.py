"""Phase 6 pure selection policy. Paper simulation only; no official publisher."""
import copy
from collections import Counter

import numpy as np

from .contracts import require, validate_snapshot
from .markets import PayoutProbabilities
from .value import expected_value

POLICY_VERSION = 'fc-paper-policy-v1'


def select_candidates(snapshots, evidence, *, decision_at, max_age_seconds=300):
    """Evidence is supplied by the trusted evaluation adapter, never UI flags.

    Each prediction ID binds evidence to the complete input snapshot and exact
    league/market/line. Bootstrap payout samples reprice the actual entry odds.
    Phase 5 currently supplies no approved evidence, producing NO BET.
    """
    require(type(decision_at) is int, 'Invalid decision time')
    require(type(max_age_seconds) is int and max_age_seconds >= 0, 'Invalid freshness limit')
    decisions, seen = [], set()
    for source in snapshots:
        snapshot = copy.deepcopy(validate_snapshot(source))
        f, c, q, p = (snapshot[k] for k in ('fixture', 'contract', 'quote', 'prediction'))
        key = (c['contract_id'], q['quote_id'] if q else None)
        require(key not in seen, 'Duplicate contract/quote input')
        seen.add(key)
        reasons = []
        if snapshot['decision_at'] != decision_at or decision_at >= f['kickoff_utc']:
            reasons.append('DECISION_TIME_INVALID')
        if not q or q['freshness'] != 'fresh' or decision_at - q['captured_at'] > max_age_seconds:
            reasons.append('QUOTE_UNAVAILABLE_OR_STALE')
        if q and q['is_closing']:
            reasons.append('REFERENCE_QUOTE_NOT_EXECUTION')
        if snapshot['diagnostics'] or not snapshot['capabilities']['schedule_available']:
            reasons.append('DATA_QUALITY_UNVERIFIED')
        proof = evidence.get(p['prediction_id']) if p else None
        bound = bool(proof and proof.get('snapshot') == source
                     and proof.get('segment') == [f['competition_id'], c['market'], c['line_quarters']])
        if not bound or proof.get('validation_status') != 'approved':
            reasons.append('MODEL_SEGMENT_NOT_APPROVED')
        samples = proof.get('payout_samples', []) if bound else []
        lower = None
        ev = expected_value(PayoutProbabilities(**p['payout']), q['decimal_odds']) if p and q else None
        if not bound or proof.get('uncertainty_status') != 'available' or len(samples) < 30:
            reasons.append('UNCERTAINTY_UNAVAILABLE')
        elif q:
            returns = [expected_value(PayoutProbabilities(**sample), q['decimal_odds']) for sample in samples]
            lower = float(np.quantile(returns, .10))
            if lower <= 0:
                reasons.append('NONPOSITIVE_EV_LOWER')
        if p:
            p.update(ev_net=ev if ev is not None else p['ev_net'], ev_lower=lower,
                     uncertainty_status='available' if lower is not None else 'unavailable',
                     validation_status='approved' if bound and proof.get('validation_status') == 'approved' else 'unvalidated')
        snapshot['capabilities'].update(official_enabled=False,
            model_validated=bool(p and p['validation_status'] == 'approved'))
        snapshot['decision'] = {'status': 'blocked' if reasons else 'paper_candidate',
            'policy_version': POLICY_VERSION, 'is_top_pick': False, 'reason_codes': reasons}
        decisions.append(snapshot)
    eligible = sorted((s for s in decisions if s['decision']['status'] == 'paper_candidate'),
                      key=lambda s: (-s['prediction']['ev_lower'], -s['quote']['captured_at'],
                                     s['contract']['contract_id'], s['quote']['quote_id']))
    fixtures, selected = set(), []
    for snapshot in eligible:
        fixture = snapshot['fixture']['fixture_id']
        if fixture in fixtures:
            snapshot['decision'].update(status='blocked', reason_codes=['FIXTURE_EXPOSURE_LIMIT'])
        else:
            fixtures.add(fixture)
            selected.append(snapshot)
    for snapshot in decisions:
        validate_snapshot(snapshot)
    return {'policy_version': POLICY_VERSION, 'official_enabled': False,
            'status': 'PAPER_CANDIDATES' if selected else 'NO_BET', 'selected': selected,
            'decisions': decisions, 'rejection_counts': dict(Counter(
                reason for s in decisions for reason in s['decision']['reason_codes']))}
