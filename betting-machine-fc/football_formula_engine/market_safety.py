"""Conservative market anchoring, not a fitted calibration model.

For Asian lines the benchmark is conditional on paid win/loss stakes. Preserve
push mass and full/half outcome ratios instead of treating 1/probability as fair
odds. The fixed weights need prospective validation before Official use.
"""
from .markets import PayoutProbabilities
from .value import effective_win_loss

SHRINK_VERSION = 'payout-market-shrink-v2'
MODEL_WEIGHTS = {'ah': 0.5, 'btts': 0.5}
MAX_MODEL_MARKET_GAP = 0.15


def anchor_payout(payout, market_probability, model_weight):
    if not 0 <= model_weight <= 1 or not 0 < market_probability < 1:
        raise ValueError('Invalid anchoring input')
    win, loss = effective_win_loss(payout)
    raw = win / (win + loss) if win + loss else None
    if raw is None or win == 0 or loss == 0 or model_weight == 1:
        return payout, raw
    win_mass = payout.full_win + payout.half_win
    loss_mass = payout.full_loss + payout.half_loss
    win_factor, loss_factor = win / win_mass, loss / loss_mass
    target = model_weight * raw + (1-model_weight) * market_probability
    adjusted_win_mass = target * loss_factor * (1-payout.push) / (
        (1-target)*win_factor + target*loss_factor)
    a = adjusted_win_mass / win_mass
    b = (1-payout.push-adjusted_win_mass) / loss_mass
    return PayoutProbabilities(full_win=payout.full_win*a, half_win=payout.half_win*a,
                              push=payout.push, half_loss=payout.half_loss*b,
                              full_loss=payout.full_loss*b), raw
