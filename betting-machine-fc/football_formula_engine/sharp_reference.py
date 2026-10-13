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
from .contracts import require
from .value import proportional_no_vig

REFERENCE_VERSION = 'sharp-reference-v1'
# Selection constants from the walk-forward replay; see docs/fc-sharp-reference-v5.md.
REFERENCE_EV_GATE = 0.02
REFERENCE_ODDS_FLOOR = 1.5
REFERENCE_ODDS_CAP = 5.0
# Larger apparent edges against a sharp book are stale or mismatched quotes.
REFERENCE_EV_CAP = 0.25
REFERENCE_MAX_AGE_SECONDS = 900

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


def reference_gate_reasons(odds, ev):
    reasons = []
    if not (REFERENCE_ODDS_FLOOR <= odds <= REFERENCE_ODDS_CAP):
        reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
    if ev < REFERENCE_EV_GATE:
        reasons.append('EV_BELOW_VALUE_THRESHOLD')
    if ev > REFERENCE_EV_CAP:
        reasons.append('REFERENCE_EDGE_IMPLAUSIBLE')
    return reasons
