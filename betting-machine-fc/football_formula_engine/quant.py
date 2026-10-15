"""Explicit probability semantics and payout-aware, recommendation-only Kelly.

Fractions are fractions of bankroll; EV is a return per unit (not a percent).
No function in this module places a wager or mutates bankroll/settlement.
"""
from .contracts import number, require
from .value import effective_win_loss, expected_value, fair_odds
from .sharp_reference import reference_gate_reasons

QUANT_VERSION = 'fc-quant-v1'


def return_distribution(payout, odds):
    number(odds)
    require(odds > 1, 'Invalid decimal odds')
    return [(odds-1, payout.full_win), ((odds-1)/2, payout.half_win),
            (0.0, payout.push), (-0.5, payout.half_loss), (-1.0, payout.full_loss)]


def kelly_from_returns(outcomes, *, fraction=0.25, cap=0.02, bankroll_units=None, eligible=True):
    """Maximize E log(1+fR), then fractionalize and cap at <=3% bankroll.

    Unlike binary Kelly, this accounts for half-win, half-loss and push. The
    full-Kelly optimum is constrained to [0,1); recommendations are not stakes.
    """
    for value in (fraction, cap):
        number(value)
    require(0 < fraction <= 1 and 0 < cap <= .03, 'Invalid Kelly fraction/cap')
    if bankroll_units is not None:
        number(bankroll_units)
        require(bankroll_units > 0, 'Bankroll units must be positive')
    require(bool(outcomes), 'Return distribution required')
    for ret, probability in outcomes:
        number(ret); number(probability)
        require(ret >= -1 and 0 <= probability <= 1, 'Invalid return distribution')
    require(abs(sum(p for _, p in outcomes)-1) <= 1e-8, 'Invalid return mass')
    ev = sum(r*p for r, p in outcomes)
    full = 0.0
    if ev > 1e-12:
        lo, hi = 0.0, 1-1e-12
        for _ in range(90):
            mid = (lo+hi)/2
            derivative = sum(p*r/(1+mid*r) for r, p in outcomes if p)
            if derivative > 0:
                lo = mid
            else:
                hi = mid
        full = (lo+hi)/2
    recommended = min(full*fraction, cap) if eligible else 0.0
    return {'mode': 'recommendation_only', 'full_fraction': full,
            'fractional_multiplier': fraction, 'cap_fraction': cap,
            'recommended_fraction': recommended,
            'recommended_units': recommended*bankroll_units if bankroll_units is not None else None,
            'bankroll_units': bankroll_units,
            'reason_codes': (['NOT_ELIGIBLE'] if not eligible else ['NO_POSITIVE_EV'] if ev <= 1e-12 else [])}


def fractional_kelly(payout, odds, **kwargs):
    return kelly_from_returns(return_distribution(payout, odds), **kwargs)


def quant_metrics(payout, odds, *, market_no_vig=None, model_probability=None,
                  reference_probability=None, reference_evidence=None,
                  decision_source='model', gate_reasons=(), bankroll_units=None):
    for probability in (market_no_vig, model_probability, reference_probability):
        if probability is not None:
            number(probability)
            require(0 <= probability <= 1, 'Invalid probability')
    win, loss = effective_win_loss(payout)
    price_probability = win/(win+loss) if win+loss else None
    ev = expected_value(payout, odds)
    reasons = list(dict.fromkeys([*gate_reasons, *reference_gate_reasons(odds, ev)]))
    if ev <= 1e-12:
        reasons.append('NO_POSITIVE_EV')
    if not reference_evidence or reference_evidence.get('freshness_status') != 'verified':
        reasons.append('REFERENCE_EVIDENCE_UNAVAILABLE')
    if (reference_probability is None or price_probability is None or
            abs(reference_probability-price_probability) > 1e-8 or decision_source != 'sharp'):
        reasons.append('DECISION_REFERENCE_MISMATCH')
    eligible = not reasons and ev > 1e-12
    return {'schema_version': QUANT_VERSION,
            'status': 'value' if eligible else 'pass' if ev <= 1e-12 else 'forecast',
            'reason_codes': list(dict.fromkeys(reasons)), 'decision_source': decision_source,
            'market_no_vig_probability': market_no_vig,
            'model_positive_payout_probability': model_probability,
            'decision_price_probability': price_probability,
            'positive_payout_probability': payout.full_win+payout.half_win,
            'push_probability': payout.push, 'reference_probability': reference_probability,
            'reference_evidence': reference_evidence,
            'primary_source_time_status': 'unknown',
            'ev': ev, 'fair_odds': fair_odds(payout),
            'edge_probability': price_probability-market_no_vig
                if price_probability is not None and market_no_vig is not None else None,
            'kelly': fractional_kelly(payout, odds, bankroll_units=bankroll_units, eligible=eligible)}
