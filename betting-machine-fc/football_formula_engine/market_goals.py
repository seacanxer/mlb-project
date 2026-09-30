"""Pre-match market anchor for conservative goal projections.

The market anchor is a regularizer, not an independent source of value. It
reduces extreme historical projections before the same live prices are valued.
"""
import math

from scipy.optimize import minimize

from .markets import match_odds, over_under
from .score_matrix import build_score_matrix
from .value import proportional_no_vig


def infer_market_goals(markets):
    """Infer home/away expected goals from complete 1X2 and O/U books."""
    one = markets.get('odds_1x2') or {}
    try:
        target_1x2 = proportional_no_vig([one[1], one[2], one[3]])
    except (KeyError, TypeError, ValueError):
        return None
    totals = []
    for raw_line, sides in (markets.get('odds_ou') or {}).items():
        try:
            line = float(raw_line)
            quarters = line * 4
            if not quarters.is_integer() or not (2 <= quarters <= 22):
                continue
            over_price = sides.get(9, sides.get('9'))
            under_price = sides.get(10, sides.get('10'))
            target = proportional_no_vig([over_price, under_price])[0]
            totals.append((int(quarters), target))
        except (KeyError, TypeError, ValueError):
            continue
    if not totals:
        return None

    def objective(log_lambdas):
        home, away = math.exp(log_lambdas[0]), math.exp(log_lambdas[1])
        distribution = build_score_matrix(home, away, 0.0)
        result = match_odds(distribution)
        predicted = (result['home'].full_win, result['draw'].full_win,
                     result['away'].full_win)
        loss = 3.0 * sum((actual - expected) ** 2
                         for actual, expected in zip(predicted, target_1x2))
        for quarters, expected in totals:
            payout = over_under(distribution, 'over', quarters)
            effective = payout.full_win + 0.5 * payout.half_win
            loss += (effective - expected) ** 2
        return loss / (3.0 + len(totals))

    fitted = minimize(objective, (math.log(1.5), math.log(1.1)),
                      method='L-BFGS-B', bounds=((math.log(.05), math.log(6.0)),) * 2)
    if not fitted.success or not math.isfinite(float(fitted.fun)):
        return None
    home, away = math.exp(float(fitted.x[0])), math.exp(float(fitted.x[1]))
    return {'home': home, 'away': away, 'total': home + away,
            'fit_loss': float(fitted.fun), 'total_lines': len(totals)}


def blend_goal_projection(model_home, model_away, market, market_weight=0.65):
    """Geometric pool avoids negative rates and tempers model overconfidence."""
    if market is None:
        return model_home, model_away
    if not 0 <= market_weight <= 1:
        raise ValueError('market_weight must be between zero and one')
    home = math.exp((1 - market_weight) * math.log(model_home)
                    + market_weight * math.log(market['home']))
    away = math.exp((1 - market_weight) * math.log(model_away)
                    + market_weight * math.log(market['away']))
    return home, away
