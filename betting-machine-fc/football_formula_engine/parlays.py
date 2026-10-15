"""Deterministic parlay preview; never assumes same-game legs are independent."""
from itertools import combinations
import math

from .contracts import number, require
from .markets import PayoutProbabilities, settle_score
from .quant import kelly_from_returns, return_distribution, quant_metrics
from .value import expected_value
from .score_matrix import build_score_matrix
from .sharp_reference import REFERENCE_CAPTURE_SKEW_SECONDS, REFERENCE_MAX_AGE_SECONDS

MAX_LEGS = 8
MAX_RETURN_STATES = 65536


def resolve_choices(matches, choices, *, minimum=2, maximum=MAX_LEGS):
    """Resolve identifiers and expected price only; all math comes from server rows."""
    require(isinstance(choices, list) and minimum <= len(choices) <= maximum, 'Parlay requires 2–8 legs')
    index = {str(m.get('info', {}).get('match_id')): m for m in matches}
    legs, distributions, fixture_keys = [], {}, []
    for choice in choices:
        require(isinstance(choice, dict), 'Invalid choice')
        match = index[str(choice['match_id'])]
        info, analysis = match['info'], match.get('analysis') or {}
        pick = next(p for p in (match.get('market_options') or match.get('projections') or [])
                    if p['market'] == choice['market'] and p['pick'] == choice['pick'])
        odds = pick.get('odds')
        number(odds); number(choice.get('odds'))
        require(odds > 1 and abs(odds-choice['odds']) <= .0001, 'QUOTE_CHANGED')
        require(pick.get('payout') and pick.get('side'), 'PARLAY_RESCAN_REQUIRED')
        names = tuple(' '.join(str(info.get(name, '')).lower().split()) for name in ('home', 'away'))
        require(all(names), 'Fixture team identities required')
        kickoff = float(info['start_ts'])
        event = next((key for teams, stamp, key in fixture_keys if names == teams and abs(kickoff-stamp) <= 60), None)
        if event is None:
            event = '|'.join(names) + '|' + str(int(kickoff))
            fixture_keys.append((names, kickoff, event))
        legs.append({**pick, 'event_key': event, 'match_id': str(info['match_id']),
                     'home': info['home'], 'away': info['away'], 'start_ts': float(info['start_ts']),
                     'quote_captured_at': pick.get('quote_captured_at') or analysis.get('quote_captured_at')})
        goals = analysis.get('model_goals')
        if goals and event not in distributions:
            distributions[event] = build_score_matrix(goals['home'], goals['away'])
    return legs, distributions


def _factor(payout, odds):
    return 1 + expected_value(payout, odds)


def score_joint_returns(distribution, legs):
    """Joint gross returns across one score matrix, retaining Asian refunds."""
    returns = {}
    for home, away, probability in distribution.cells():
        factor = math.prod(_factor(settle_score(p['market'], p['side'], p.get('line_quarters'), home, away),
                                   p['odds']) for p in legs)
        returns[factor] = returns.get(factor, 0.0)+probability
    return [(gross-1, p) for gross, p in returns.items()]


def _contradiction(legs):
    # Every payout regime of the supported score contracts is represented by
    # this finite grid (beyond the largest total/margin threshold + 3).
    if any(p['market'] not in ('1x2', 'ah', 'ou', 'btts') for p in legs):
        return False
    bound = max([4]+[abs(p.get('line_quarters') or 0)//4+3 for p in legs])
    if bound > 24:
        return False
    return all(math.prod(_factor(settle_score(p['market'], p['side'], p.get('line_quarters'), h, a),
                                  p['odds']) for p in legs) == 0
               for h in range(bound+1) for a in range(bound+1))


def evaluate_parlay(legs, *, now, bankroll_units=None, fixture_distributions=None):
    number(now)
    require(isinstance(legs, list) and 2 <= len(legs) <= MAX_LEGS, 'Parlay requires 2–8 legs')
    reasons, assessed, groups, identities = [], [], {}, set()
    for leg in legs:
        require(isinstance(leg.get('event_key'), str) and bool(leg['event_key']), 'Fixture identity required')
        fixture = leg['event_key']
        identity = (fixture, leg['market'], leg['side'], leg.get('line_quarters'))
        if identity in identities:
            reasons.append('DUPLICATE_PARLAY_LEG')
        identities.add(identity)
        odds = leg.get('odds')
        number(odds); require(odds > 1, 'Unpriced parlay leg')
        number(leg['start_ts']); number(leg['quote_captured_at'])
        payout = PayoutProbabilities(**leg['payout'])
        if leg['market'] in ('1x2', 'btts'):
            require(leg.get('line_quarters') is None, 'Unexpected binary line')
        if leg['market'] in ('1x2', 'ah', 'ou', 'btts'):
            settle_score(leg['market'], leg['side'], leg.get('line_quarters'), 0, 0)
        ev = expected_value(payout, odds)
        quant = leg.get('quant') or {}
        evidence = quant.get('reference_evidence') or {}
        errors = []
        if now >= leg['start_ts']-60:
            errors.append('KICKOFF_TOO_CLOSE')
        if not 0 <= now-leg['quote_captured_at'] <= 300:
            errors.append('QUOTE_EXPIRED')
        captured, updated = evidence.get('captured_at'), evidence.get('source_updated_at')
        if (evidence.get('freshness_status') != 'verified' or
                type(captured) not in (int, float) or type(updated) not in (int, float) or
                not 0 <= now-captured <= REFERENCE_MAX_AGE_SECONDS or not 0 < updated <= captured or
                not 0 <= now-updated <= REFERENCE_MAX_AGE_SECONDS or
                abs(captured-leg['quote_captured_at']) > REFERENCE_CAPTURE_SKEW_SECONDS):
            errors.append('REFERENCE_EVIDENCE_UNAVAILABLE')
        if quant.get('schema_version') != 'fc-quant-v1' or quant.get('status') != 'value' or quant.get('reason_codes'):
            errors.append('PARLAY_LEG_NOT_VALUE')
        recalculated = quant_metrics(payout, odds, reference_probability=quant.get('reference_probability'),
            reference_evidence=evidence, decision_source=quant.get('decision_source'))
        if recalculated['status'] != 'value' or type(quant.get('ev')) not in (float, int) or abs(quant['ev']-ev) > 1e-8:
            errors.append('QUANT_PAYOUT_MISMATCH')
        if ev <= .02+1e-12:
            errors.append('PARLAY_LEG_EV_NOT_ABOVE_2_PERCENT')
        if ev > .25:
            errors.append('REFERENCE_EDGE_IMPLAUSIBLE')
        reasons.extend(errors)
        groups.setdefault(fixture, []).append(leg)
        assessed.append({'event_key': fixture, 'match_id': leg.get('match_id'), 'pick': leg.get('pick'),
                         'home': leg.get('home'), 'away': leg.get('away'), 'odds': odds,
                         'start_ts': leg['start_ts'], 'market': leg['market'], 'side': leg['side'],
                         'line_quarters': leg.get('line_quarters'), 'ev': ev,
                         'payout': payout.__dict__, 'quote_captured_at': leg['quote_captured_at'],
                         **({'quant': quant} if quant.get('schema_version') == 'fc-quant-v1' else {}),
                         'reason_codes': list(dict.fromkeys(errors))})
    correlated = {key: rows for key, rows in groups.items() if len(rows) > 1}
    scenarios = []
    for key, rows in correlated.items():
        reasons.append('SAME_MATCH_JOINT_PRICE_UNVERIFIED')
        if _contradiction(rows):
            reasons.append('PARLAY_CONTRADICTION')
        dist = (fixture_distributions or {}).get(key)
        if dist is not None and all(p['market'] in ('1x2', 'ah', 'ou', 'btts') for p in rows):
            outcomes = score_joint_returns(dist, rows)
            scenarios.append({'event_key': key, 'status': 'unvalidated_model_scenario',
                'ev_at_product_odds': sum(r*p for r, p in outcomes),
                'positive_return_probability': sum(p for r, p in outcomes if r > 0)})
    combined_odds = math.prod(p['odds'] for p in legs)
    require(math.isfinite(combined_odds), 'Invalid combined odds')
    result = {'schema_version': 'fc-parlay-quant-v1', 'eligible': False, 'status': 'blocked',
              'reason_codes': sorted(set(reasons)), 'legs': assessed, 'combined_odds': combined_odds,
              'price_source': 'product_of_observed_leg_odds', 'executable_quote_verified': False,
              'dependence_assumption': 'same_match_unverified' if correlated else 'independent_fixtures',
              'ev': None, 'positive_return_probability': None, 'all_legs_positive_probability': None,
              'kelly': None, 'same_match_scenarios': scenarios, 'official_enabled': False}
    if correlated:
        return result
    # Convolve gross multipliers: pushes refund; half losses return 0.5.
    gross = {1.0: 1.0}
    for leg in legs:
        next_gross = {}
        for factor, probability in gross.items():
            for ret, p in return_distribution(PayoutProbabilities(**leg['payout']), leg['odds']):
                if p:
                    key = factor*(1+ret)
                    next_gross[key] = next_gross.get(key, 0.0)+probability*p
        if len(next_gross) > MAX_RETURN_STATES:
            result['reason_codes'].append('PAYOUT_STATE_SPACE_LIMIT')
            return result
        gross = next_gross
    outcomes = [(factor-1, probability) for factor, probability in gross.items()]
    ev = sum(ret*p for ret, p in outcomes)
    if ev <= 0:
        result['reason_codes'].append('NO_POSITIVE_PARLAY_EV')
    eligible = not result['reason_codes']
    result.update(eligible=eligible, status='value' if eligible else 'blocked', ev=ev,
        positive_return_probability=sum(p for ret, p in outcomes if ret > 1e-12),
        all_legs_positive_probability=math.prod(
            p['payout']['full_win']+p['payout']['half_win'] for p in legs),
        kelly=kelly_from_returns(outcomes, bankroll_units=bankroll_units, eligible=eligible))
    return result


def build_value_parlays(candidates, *, now, limit=5, bankroll_units=None):
    """Bounded research proposals, ranked by conditional EV; no automatic locks."""
    require(type(limit) is int and 1 <= limit <= 10, 'Invalid proposal limit')
    by_event = {}
    for leg in sorted(candidates, key=lambda p: expected_value(PayoutProbabilities(**p['payout']), p['odds']), reverse=True):
        if (leg.get('quant', {}).get('status') == 'value' and
                0 <= now-leg['quote_captured_at'] <= 300 and now < leg['start_ts']-60):
            by_event.setdefault(leg['event_key'], leg)
    pool = list(by_event.values())[:18]
    proposals = []
    for size in (2, 3):
        for legs in combinations(pool, size):
            result = evaluate_parlay(list(legs), now=now, bankroll_units=bankroll_units)
            if result['eligible']:
                proposals.append(result)
    return sorted(proposals, key=lambda r: r['ev'], reverse=True)[:limit]
