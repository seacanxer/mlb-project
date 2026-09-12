"""Payout-aware fair price, expected return, and scoped proportional de-vig."""
import math

from .contracts import number, require


def effective_win_loss(payout):
    return (payout.full_win + 0.5 * payout.half_win,
            payout.full_loss + 0.5 * payout.half_loss)


def fair_odds(payout, *, win_commission=0.0):
    number(win_commission); require(0 <= win_commission < 1, 'Invalid commission')
    win, loss = effective_win_loss(payout)
    if win == 0:
        return None
    effective_gain = 1 - win_commission
    require(effective_gain > 0, 'No positive win payout')
    return 1 + loss / (win * effective_gain)


def expected_value(payout, decimal_odds, *, win_commission=0.0):
    number(decimal_odds); number(win_commission)
    require(decimal_odds > 1 and 0 <= win_commission < 1, 'Invalid price/cost')
    win, loss = effective_win_loss(payout)
    return (decimal_odds - 1) * (1 - win_commission) * win - loss


def proportional_no_vig(odds):
    require(type(odds) in (list, tuple) and len(odds) >= 2, 'Complete market requires at least two prices')
    implied = []
    for price in odds:
        number(price); require(price > 1, 'Invalid decimal odds')
        implied.append(1 / price)
    booksum = sum(implied)
    require(booksum > 0, 'Invalid booksum')
    return tuple(value / booksum for value in implied)
