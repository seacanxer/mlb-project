"""Sharp-reference pricing: value is the primary price against a sharp book's fair odds.

Walk-forward replay (scripts/fc-walkforward-backtest.py, 27,390 fixtures,
2022/23-2025/26) found that disagreement between the Dixon-Coles goal model
and the market carries no predictive information: picks chosen from it lost
6-8% with negative closing-line value in every market, side, odds and EV band.
Prices above a sharp book's no-vig fair price were the only selection with
positive closing-line value in every season.

In this mode the decision probability is the reference book's no-vig
probability for the identical contract. The goal model only supplies the
full/half/push shape for split Asian lines; the effective win probability
W/(W+L) is set to the reference value. Contracts without a complete
reference pair are not priced.
"""
from .contracts import number, require
from .value import proportional_no_vig

REFERENCE_VERSION = 'sharp-reference-v1'
# Selection constants from the walk-forward replay; see docs/fc-sharp-reference-v5.md.
REFERENCE_EV_GATE = 0.02
REFERENCE_ODDS_FLOOR = 1.30
REFERENCE_ODDS_CAP = 5.0
# Larger apparent edges against a sharp book are stale or mismatched quotes.
REFERENCE_EV_CAP = 0.25
REFERENCE_MAX_AGE_SECONDS = 900
REFERENCE_CAPTURE_SKEW_SECONDS = 300
# High-win tier: value picks the sharp book already rates >= 55% likely.
# Replay (best market price vs Pinnacle fair): 68-71% hit, +21% ROI, +3% CLV
# in both dev and test; at a single soft book they are rare.
HIGH_WIN_MIN_PROBABILITY = 0.55
# Line-movement lookback: earliest reference quote kept for open-vs-now.
MOVEMENT_LOOKBACK_SECONDS = 3 * 86400

_COMPLEMENTS = {
    '1x2': (('home', 'draw', 'away'),),
    'btts': (('yes', 'no'),),
    'ou': (('over', 'under'),),
}


def latest_reference_quotes(observations, bookmaker):
    """Newest quote per contract from one bookmaker. Observations are newest-first."""
    require(bool(bookmaker), 'Reference bookmaker required')
    latest = {}
    for obs in observations:
        if str(obs.get('bookmaker', '')).lower() != bookmaker.lower():
            continue
        for quote in obs.get('quotes') or []:
            key = (quote['market'], quote['side'], quote['line_quarters'])
            if key not in latest:
                latest[key] = {'decimal_odds': float(quote['decimal_odds']),
                               'observation_id': obs.get('artifact_id'),
                               'captured_at': obs.get('captured_at'),
                               'source_updated_at': obs.get('source_updated_at')}
    return latest


def fair_probabilities(quotes):
    """No-vig fair probability per contract, only where the full complementary set exists.

    AH contracts are keyed by each side's own handicap: home line q pairs with
    away line -q.
    """
    fair = {}
    by_market = {}
    for (market, side, line), quote in quotes.items():
        by_market.setdefault(market, {})[(side, line)] = quote['decimal_odds']
    for market in ('1x2', 'btts'):
        prices = by_market.get(market, {})
        sides = _COMPLEMENTS[market][0]
        if all((side, None) in prices for side in sides):
            probs = proportional_no_vig([prices[(side, None)] for side in sides])
            for side, probability in zip(sides, probs):
                fair[(market, side, None)] = probability
    totals = by_market.get('ou', {})
    for (side, line), _price in totals.items():
        if side != 'over' or ('under', line) not in totals:
            continue
        over, under = proportional_no_vig([totals[('over', line)], totals[('under', line)]])
        fair[('ou', 'over', line)] = over
        fair[('ou', 'under', line)] = under
    handicaps = by_market.get('ah', {})
    for (side, line), _price in handicaps.items():
        if side != 'home' or ('away', -line) not in handicaps:
            continue
        home, away = proportional_no_vig([handicaps[('home', line)], handicaps[('away', -line)]])
        fair[('ah', 'home', line)] = home
        fair[('ah', 'away', -line)] = away
    return fair


def reference_snapshot(observations, bookmaker, decision_at, *, max_age_seconds=REFERENCE_MAX_AGE_SECONDS,
                       primary_captured_at=None, max_skew_seconds=REFERENCE_CAPTURE_SKEW_SECONDS):
    """Newest complete same-observation market, with both clocks checked.

    Never combine a newly posted side with an older opposite side, resurrect
    removed lines, or treat capture time as the bookmaker's update time.
    Historical/latest_reference_quotes remains a non-validating read helper.
    """
    number(decision_at); number(max_age_seconds); number(max_skew_seconds)
    require(bookmaker.lower() not in ('1xbit', '1xbet'), 'Reference must be a distinct bookmaker')
    require(max_age_seconds > 0 and max_skew_seconds >= 0, 'Invalid freshness window')
    if primary_captured_at is not None:
        number(primary_captured_at)
    seen, accepted, rejected = set(), {}, []
    ordered = sorted((o for o in observations if str(o.get('bookmaker', '')).lower() == bookmaker.lower()),
                     key=lambda o: o.get('captured_at') or 0, reverse=True)
    for obs in ordered:
        groups = {}
        for q in obs.get('quotes') or []:
            market, side, line = q['market'], q['side'], q['line_quarters']
            canonical = -line if market == 'ah' and side == 'away' else line
            groups.setdefault((market, canonical), []).append(q)
        for group, rows in groups.items():
            if group in seen:
                continue
            seen.add(group)
            reason = None
            captured, updated = obs.get('captured_at'), obs.get('source_updated_at')
            if type(captured) not in (float, int) or not 0 <= decision_at-captured <= max_age_seconds:
                reason = 'REFERENCE_CAPTURE_EXPIRED'
            elif type(updated) not in (float, int):
                reason = 'REFERENCE_SOURCE_TIME_UNKNOWN'
            elif not 0 < updated <= captured or not 0 <= decision_at-updated <= max_age_seconds:
                reason = 'REFERENCE_SOURCE_EXPIRED'
            elif primary_captured_at is not None and abs(primary_captured_at-captured) > max_skew_seconds:
                reason = 'REFERENCE_CAPTURE_SKEW'
            elif any(q.get('period', 'full_time_90_minutes') != 'full_time_90_minutes' for q in rows):
                reason = 'REFERENCE_PERIOD_MISMATCH'
            market_quotes = {(q['market'], q['side'], q['line_quarters']): {
                'decimal_odds': q['decimal_odds'], 'observation_id': obs.get('artifact_id'),
                'captured_at': captured, 'source_updated_at': updated,
                'bookmaker': bookmaker, 'provider': obs.get('provider'), 'freshness_status': 'verified'}
                for q in rows}
            if reason is None:
                if len(market_quotes) != len(rows) or len(fair_probabilities(market_quotes)) != len(rows):
                    reason = 'REFERENCE_COMPLETE_MARKET_UNAVAILABLE'
            if reason:
                rejected.append({'market': group[0], 'line_quarters': group[1], 'reason': reason})
            else:
                accepted.update(market_quotes)
    fair = fair_probabilities(accepted)
    return {'quotes': accepted, 'fair': fair, 'rejected_groups': rejected,
            'reason_codes': sorted({r['reason'] for r in rejected}) or ([] if fair else ['REFERENCE_UNAVAILABLE'])}


def reference_gate_reasons(odds, ev):
    reasons = []
    if not (REFERENCE_ODDS_FLOOR <= odds <= REFERENCE_ODDS_CAP):
        reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
    if ev < REFERENCE_EV_GATE:
        reasons.append('EV_BELOW_VALUE_THRESHOLD')
    if ev > REFERENCE_EV_CAP:
        reasons.append('REFERENCE_EDGE_IMPLAUSIBLE')
    return reasons


def value_tier(reference_probability):
    return 'high_win' if reference_probability >= HIGH_WIN_MIN_PROBABILITY else 'value'


def reference_movement(observations, bookmaker):
    """Earliest and latest no-vig probability per contract from one bookmaker.

    Observations may be in any order. Returns {contract: (open, now)}. This is
    recorded for prospective evaluation only: the replay showed the sharp
    current price already contains the move, and backing a move after it
    happened did not beat the closing line.
    """
    snapshots = sorted((obs for obs in observations
                        if str(obs.get('bookmaker', '')).lower() == bookmaker.lower()),
                       key=lambda obs: obs.get('captured_at') or 0)
    if not snapshots:
        return {}
    first = fair_probabilities(latest_reference_quotes(snapshots, bookmaker))
    last = fair_probabilities(latest_reference_quotes(list(reversed(snapshots)), bookmaker))
    return {key: (first[key], last[key]) for key in last if key in first}


def quotes_to_markets(quotes):
    """Reference quotes -> scanner market dict (1X2 and O/U only) for goal inference."""
    markets = {'odds_1x2': {}, 'odds_ou': {}}
    for (market, side, line), quote in quotes.items():
        if market == '1x2':
            markets['odds_1x2'][{'home': 1, 'draw': 2, 'away': 3}[side]] = quote['decimal_odds']
        elif market == 'ou' and line is not None:
            markets['odds_ou'].setdefault(str(line / 4), {})['9' if side == 'over' else '10'] = quote['decimal_odds']
    return markets
