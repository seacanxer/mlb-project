"""All four markets and Asian settlement derived from one score distribution."""
from dataclasses import dataclass
import math

from .contracts import ContractError, require


@dataclass(frozen=True)
class PayoutProbabilities:
    full_win: float = 0.0
    half_win: float = 0.0
    push: float = 0.0
    half_loss: float = 0.0
    full_loss: float = 0.0

    def __post_init__(self):
        values = (self.full_win, self.half_win, self.push, self.half_loss, self.full_loss)
        require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values), 'Invalid payout probability')
        require(abs(sum(values) - 1) <= 1e-8, 'Payout mass invalid')

    @property
    def mass(self):
        return self.full_win + self.half_win + self.push + self.half_loss + self.full_loss


def _binary(probability):
    return PayoutProbabilities(full_win=probability, full_loss=1 - probability)


def match_odds(distribution):
    home = draw = away = 0.0
    for x, y, p in distribution.cells():
        if x > y: home += p
        elif x == y: draw += p
        else: away += p
    return {'home': _binary(home), 'draw': _binary(draw), 'away': _binary(away)}


def btts(distribution):
    yes = sum(p for x, y, p in distribution.cells() if x > 0 and y > 0)
    return {'yes': _binary(yes), 'no': _binary(1 - yes)}


def _component_result(measure_quarters):
    if measure_quarters > 0: return 'win'
    if measure_quarters < 0: return 'loss'
    return 'push'


def _split_quarters(line_quarters):
    require(type(line_quarters) is int and type(line_quarters) is not bool, 'Line must use integer quarter-units')
    return (line_quarters - 1, line_quarters + 1) if abs(line_quarters) % 2 else (line_quarters, line_quarters)


def _combined_outcome(first, second):
    pair = tuple(sorted((first, second)))
    mapping = {
        ('win', 'win'): 'full_win', ('push', 'win'): 'half_win',
        ('push', 'push'): 'push', ('loss', 'push'): 'half_loss', ('loss', 'loss'): 'full_loss',
    }
    if pair not in mapping:
        raise ContractError('Invalid split settlement combination')
    return mapping[pair]


def _aggregate(distribution, outcome_for_score):
    values = {key: 0.0 for key in ('full_win', 'half_win', 'push', 'half_loss', 'full_loss')}
    for home, away, probability in distribution.cells():
        values[outcome_for_score(home, away)] += probability
    result = PayoutProbabilities(**values)
    require(abs(result.mass - 1) <= 1e-8, 'Payout mass invalid')
    return result


def asian_handicap(distribution, side, line_quarters):
    require(side in ('home', 'away'), 'Invalid AH side')
    components = _split_quarters(line_quarters)
    def outcome(home, away):
        margin_quarters = 4 * ((home - away) if side == 'home' else (away - home))
        return _combined_outcome(*(_component_result(margin_quarters + line) for line in components))
    return _aggregate(distribution, outcome)


def over_under(distribution, side, line_quarters):
    require(side in ('over', 'under'), 'Invalid O/U side')
    require(type(line_quarters) is int and type(line_quarters) is not bool and line_quarters >= 0, 'Invalid total line')
    components = _split_quarters(line_quarters)
    def outcome(home, away):
        total_quarters = 4 * (home + away)
        measures = (total_quarters - line for line in components) if side == 'over' else (line - total_quarters for line in components)
        return _combined_outcome(*(_component_result(value) for value in measures))
    return _aggregate(distribution, outcome)


def settle_score(market, side, line_quarters, home_goals, away_goals):
    class PointMass:
        def cells(self): return iter(((home_goals, away_goals, 1.0),))
    require(type(home_goals) is int and home_goals >= 0 and type(away_goals) is int and away_goals >= 0, 'Invalid score')
    if market == 'ah': return asian_handicap(PointMass(), side, line_quarters)
    if market == 'ou': return over_under(PointMass(), side, line_quarters)
    if market == '1x2': return match_odds(PointMass())[side]
    if market == 'btts': return btts(PointMass())[side]
    raise ContractError('Unknown market')
